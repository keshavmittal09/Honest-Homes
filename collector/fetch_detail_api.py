"""Fetch full project detail data + documents via the MahaRERA public API.

The detail page is a public REST API gated by a single "public view" token that a
human obtains by solving ONE captcha (see run_detail_assist.py, which records the
token in <RID>.api.json). With that token we can fetch any project's full data by
projectId and download every document by its DMS reference — no per-project captcha.

It is INCREMENTAL and resumable: projects already captured (in any dated capture
directory) are skipped, and the run stops by itself shortly before the token
expires rather than dying mid-project. So the workflow is simply:

    python -m collector.run_detail_assist      # solve ONE captcha, then close it
    python -m collector.fetch_detail_api       # runs until the token dies

    # then publish what it collected:
    python -c "from engine.detail import build_parsed_snapshot as b; print(b())"
    python -m collector.upload_docs

Repeat whenever you can spare a captcha; each run picks up where the last stopped.

Useful flags:
    --districts Pune,Thane    do those districts first
    --limit 50                cap the run
    --refetch                 re-fetch projects already captured
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .run_detail import _load_index, _targets

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "data" / "snapshots" / "detail"
HOST = "https://maharerait.maharashtra.gov.in"
DMS_URL = f"{HOST}/api/maha-rera-dms-service/batch-job/downloadDocumentForPublicView"
# DMS references are a UUID, optionally carrying a document version suffix
# ("dafae48c-...-4507f3dd1cba;0.1"). The suffix form is used by exactly the
# documents that matter most on a complaint — the signed order and the hearing
# roznama — so a bare 36-char match silently skipped them.
UUID = re.compile(r"^[0-9a-fA-F-]{36}(;[0-9.]+)?$")
_VIEW = re.compile(r"/view/(\d+)")

# Download pacing, set from CLI flags in main(). Module-level so _fetch_one can
# stay a plain function.
_DOC_DELAY = 0.7
_MAX_DOCS = 0
_IMPORTANT_ONLY = False


class _TokenDead(Exception):
    """The public-view token stopped being accepted mid-run."""


def keep_awake(on: bool = True) -> None:
    """Stop Windows sleeping mid-run (no-op elsewhere).

    A token costs a human captcha and lives ~90 minutes of WALL CLOCK time, not
    90 minutes of runtime — so if the machine sleeps, the token dies unused. That
    happened once and burned ~80 minutes of a solve.
    """
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ES_AWAYMODE_REQUIRED = 0x00000040   # survives Modern Standby on laptops
        flags = ((ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
                 if on else ES_CONTINUOUS)
        if ctypes.windll.kernel32.SetThreadExecutionState(flags) == 0 and on:
            # away-mode is refused on some builds; fall back to plain idle suppression
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:
        pass          # not Windows, or not permitted — the run still works


def already_captured() -> set[str]:
    """Every RERA id we already hold a completed API capture for, across ALL dates.

    Only the dict form counts: that is what this script writes. The list form is a
    raw browser interception from run_detail_assist, which holds the token but not
    a full endpoint sweep.
    """
    done: set[str] = set()
    for f in OUT_ROOT.glob("*/*.api.json"):
        try:
            api = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(api, dict) and api.get("rera_id") and api.get("endpoints"):
            done.add(api["rera_id"])
    return done


def _reference() -> tuple[str, list[str]]:
    """(token, endpoint_paths): the freshest token, the widest endpoint list.

    Scans every capture directory rather than just the newest: the token lives in
    the browser capture from run_detail_assist, which is often not the directory
    this run writes to. The endpoint list is pooled across all captures because
    any single browser session may have been closed before the page finished
    calling everything.
    """
    best: tuple[int, str, list[str]] | None = None
    all_paths: set[str] = set()
    for f in OUT_ROOT.glob("*/*.api.json"):
        try:
            api = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(api, list):          # dict form carries no raw auth response
            continue
        tok, paths = None, []
        for a in api:
            if not isinstance(a, dict) or not isinstance(a.get("url"), str):
                continue
            if "authenticatePublic" in a["url"]:
                try:
                    tok = a["json"]["responseObject"]["accessToken"]
                except (KeyError, TypeError):
                    pass
            p = urlparse(a["url"]).path
            if "/public/projectregistartion/" in p or "/complaint/" in p or "/reatappeal/" in p:
                if p not in paths:
                    paths.append(p)
        if paths:
            all_paths.update(paths)
        if tok and paths:
            left = _token_seconds_left(tok)
            if best is None or left > best[0]:
                best = (left, tok, paths)

    if best and best[0] > 60:
        # The token comes from the freshest capture, but the endpoint list is the
        # union of every capture we hold. A browser session that was closed a
        # moment early yields a short list -- one such token carried 31 of the 42
        # paths, silently dropping extensions and geo-tagging, which are exactly
        # what the delivery score and the amenity directories are built on. The
        # endpoints are stable across projects, so the union is safe: an endpoint
        # that does not apply to a project simply returns nothing.
        merged = list(best[2]) + [p for p in sorted(all_paths) if p not in set(best[2])]
        if len(merged) > len(best[2]):
            print(f"Endpoints: {len(best[2])} in the newest capture, "
                  f"{len(merged)} after merging every capture we hold")
        return best[1], merged
    raise SystemExit(
        "No usable token found — the last one has expired.\n\n"
        "  1. python -m collector.run_detail_assist\n"
        "  2. solve ONE captcha in the Edge window, let the page finish loading\n"
        "  3. re-run this script; it will resume where it left off.")


def _token_seconds_left(tok: str) -> int:
    try:
        pl = tok.split(".")[1]
        pl += "=" * (-len(pl) % 4)
        return int(json.loads(base64.urlsafe_b64decode(pl))["exp"] - time.time())
    except Exception:
        return -1


def _collect_doc_jobs(api_by_ep: dict) -> dict[str, str]:
    """Every (documentId -> fileName) referenced anywhere in the responses."""
    jobs: dict[str, str] = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and v and k.lower().endswith("dmsrefno") and UUID.match(v):
                    pref = re.sub(r"dmsrefno$", "", k, flags=re.I)
                    fn = None
                    for cand in (pref + "FileName", pref + "DMSFileName", pref + "DmsFileName",
                                 "documentFileName", "documentName"):
                        if isinstance(o.get(cand), str) and o.get(cand):
                            fn = o[cand]; break
                    jobs.setdefault(v, fn or (v + ".pdf"))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(api_by_ep)
    return jobs


class _Throttled(Exception):
    """MahaRERA's DDoS guard rejected us; back off rather than push through."""


def _doc_priority(fn: str) -> int:
    """0 = fetch first. Uses the same labelling the site displays.

    A large project references several hundred documents — mostly per-year
    professional certificates and KYC scans. The ones a buyer actually checks are
    few, so those are fetched first and the long tail is optional. This keeps us
    well inside the server's tolerance and inside the storage budget.
    """
    from engine.detail import label_document
    lab = label_document(fn)
    # Complaint papers rank above everything: they are the evidence behind the
    # worst facts we publish about a project, so they must never be the ones cut
    # by the per-project cap.
    if lab.get("category") == "Complaint papers":
        return 0
    return 1 if lab.get("important") else (2 if lab.get("category") == "Plans" else 3)


def _download_docs(jobs: dict[str, str], out: Path, headers: dict,
                   delay: float = 0.7, max_docs: int = 0,
                   important_only: bool = False) -> tuple[int, list[str]]:
    """Download documents politely. Returns (count, filenames written).

    MahaRERA answers 403 "Restricted due to multiple requests send in short
    time(DDoS)" when hit hard, and the previous version fired every reference for
    a project back-to-back with no pause at all — 481 POSTs in a row for one
    project — which cost us 88% of all documents. Now: a pause between each, and
    a 403 backs off and then abandons the project rather than pushing through.
    """
    out.mkdir(parents=True, exist_ok=True)
    order = sorted(jobs.items(), key=lambda kv: (_doc_priority(kv[1]), kv[1]))
    if important_only:
        order = [kv for kv in order if _doc_priority(kv[1]) <= 1]
    if max_docs:
        # Complaint papers (priority 0) are never cut by the cap: they are the
        # evidence behind the worst findings we publish, and a project with 40
        # complaints has 40 orders that all matter. The cap only limits the
        # ordinary paperwork behind them.
        must = [kv for kv in order if _doc_priority(kv[1]) == 0]
        rest = [kv for kv in order if _doc_priority(kv[1]) != 0]
        order = must + rest[:max_docs]

    ok, written, strikes = 0, [], 0
    with httpx.Client(timeout=60, verify=False) as c:
        for did, fn in order:
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", fn)[:120] or did
            if "." not in safe:
                safe += ".pdf"
            p, k = out / safe, 1
            while p.exists():
                p, k = out / f"{k}_{safe}", k + 1
            try:
                r = c.post(DMS_URL, json={"documentId": did, "fileName": fn}, headers=headers)
                if r.status_code == 403:
                    strikes += 1
                    if strikes >= 3:
                        raise _Throttled()
                    time.sleep(20 * strikes)          # back off, then try once more
                    continue
                if r.status_code == 200 and len(r.content) > 200:
                    p.write_bytes(r.content)
                    written.append(p.name)
                    ok += 1
                    strikes = 0
            except _Throttled:
                raise
            except Exception:
                pass
            time.sleep(delay)
    return ok, written


def _fetch_one(c, rid: str, row: dict, endpoints: list[str], headers: dict,
               cap_dir: Path) -> dict | None:
    """Fetch every endpoint + document for one project. Raises _TokenDead on 401."""
    m = _VIEW.search(row.get("detail_url", "") or "")
    if not m:
        return None
    pid = int(m.group(1))

    upid = None                       # promoter user-profile id (some endpoints need it)
    api_by_ep: dict[str, dict] = {}
    for path in endpoints:
        ep = path.rsplit("/", 1)[-1]
        body = {"projectId": pid}
        if "romoter" in ep and upid:
            body["userProfileId"] = upid
        try:
            r = c.post(HOST + path, json=body, headers=headers)
            if r.status_code == 401:
                raise _TokenDead()
            if r.headers.get("content-type", "").startswith("application/json"):
                j = r.json()
                api_by_ep[ep] = j
                if ep == "getProjectAndAssociatedPromoterDetails" and isinstance(j.get("responseObject"), dict):
                    mm = re.search(r'"userProfileId"\s*:\s*(\d+)', json.dumps(j["responseObject"]))
                    if mm:
                        upid = int(mm.group(1))
        except _TokenDead:
            raise
        except Exception:
            pass

    docs = _collect_doc_jobs(api_by_ep)
    throttled = False
    try:
        n_docs, written = _download_docs(
            docs, cap_dir / "docs" / rid, headers,
            delay=_DOC_DELAY, max_docs=_MAX_DOCS, important_only=_IMPORTANT_ONLY)
    except _Throttled:
        n_docs, written, throttled = 0, [], True

    # Record EVERY referenced document, downloaded or not. The metadata is tiny and
    # lets the site list the full paper trail and link out for anything we did not
    # pull down, instead of pretending those documents do not exist.
    out = {
        "rera_id": rid, "project_id": pid, "project_name": row.get("project_name", ""),
        "promoter_name": row.get("promoter_name", ""),
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "endpoints": api_by_ep,
        "throttled": throttled,
        "documents": [{"documentId": d, "fileName": f,
                       "downloaded": re.sub(r"[^A-Za-z0-9._-]", "_", f)[:120] in written}
                      for d, f in docs.items()],
    }
    (cap_dir / f"{rid}.api.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_ep = sum(1 for v in api_by_ep.values() if isinstance(v, dict) and v.get("status") == "1")
    return {"rera_id": rid, "name": row.get("project_name", ""),
            "endpoints_ok": ok_ep, "docs": n_docs, "refs": len(docs),
            "throttled": throttled}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="max projects this run (0 = as many as the token allows)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between projects (polite)")
    ap.add_argument("--reserve", type=int, default=90,
                    help="stop this many seconds before the token expires")
    ap.add_argument("--districts", default="",
                    help="comma-separated districts to do first, e.g. 'Pune,Thane'")
    ap.add_argument("--region", default="",
                    help="restrict this run to one region's pincodes, e.g. "
                         "'kharghar-panvel'. Unlike --districts (which only "
                         "reorders), this drops everything outside the region.")
    ap.add_argument("--refetch", action="store_true",
                    help="re-fetch projects already captured (off by default)")
    ap.add_argument("--doc-delay", type=float, default=0.7,
                    help="seconds between document downloads (server 403s if too fast)")
    ap.add_argument("--max-docs", type=int, default=25,
                    help="max documents per project (0 = all); the long tail is "
                         "per-year certificates and KYC scans")
    ap.add_argument("--important-only", action="store_true",
                    help="only the documents a buyer checks (certificates, "
                         "agreement, IOD, title)")
    args = ap.parse_args()

    global _DOC_DELAY, _MAX_DOCS, _IMPORTANT_ONLY
    _DOC_DELAY, _MAX_DOCS, _IMPORTANT_ONLY = args.doc_delay, args.max_docs, args.important_only

    index = _load_index()
    token, endpoints = _reference()

    # Never spend a token on work already done — each token costs a human captcha.
    done = set() if args.refetch else already_captured()

    ordered = [r for r in _targets("collector/targets.txt", index, 10_000_000) or []]
    seen = set(ordered)
    rest = [r for r in index if r not in seen]
    if args.districts:
        want = {d.strip().lower() for d in args.districts.split(",") if d.strip()}
        rest.sort(key=lambda r: ((index[r].get("district") or "").lower() not in want, r))
    queue = [r for r in ordered + rest
             if r not in done and index.get(r, {}).get("detail_url")]
    if args.region:
        # A token is scarce, so a priority region means *only* that region --
        # sorting it first would still spend the tail of the token elsewhere.
        from collector.regions import region as _region
        pins = _region(args.region)["pincodes"]
        want = set(pins)
        before = len(queue)
        queue = [r for r in queue
                 if str(index.get(r, {}).get("pincode") or "") in want]
        # Order by the region's pincode list, not index order. Filtering alone
        # spread the first token across the whole region and finished none of
        # it; the point of a priority area is to complete one area at a time.
        rank = {p: i for i, p in enumerate(pins)}
        queue.sort(key=lambda r: (rank.get(str(index.get(r, {}).get("pincode") or ""), 99), r))
        print(f"Region {args.region}: {len(queue)} of {before} queued projects match")
        for p in pins:
            n = sum(1 for r in queue if str(index.get(r, {}).get("pincode") or "") == p)
            if n:
                print(f"    {p}: {n} remaining")
    if args.limit:
        queue = queue[:args.limit]

    cap_dir = OUT_ROOT / time.strftime("%Y-%m-%d")     # this run gets its own dated dir
    cap_dir.mkdir(parents=True, exist_ok=True)

    left = _token_seconds_left(token)
    print(f"Token good for ~{left // 60} min (stopping with {args.reserve}s reserve)")
    print(f"Already captured : {len(done)} projects — skipped")
    print(f"Queue            : {len(queue)} projects -> {cap_dir}\n")
    if not queue:
        print("Nothing left to fetch.")
        return

    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    keep_awake(True)          # the token expires on wall-clock time, not runtime
    summary: list[dict] = []
    stopped = "queue exhausted"
    throttle_hits = 0

    try:
        with httpx.Client(timeout=45, verify=False) as c:
            for i, rid in enumerate(queue, 1):
                remaining = _token_seconds_left(token)
                if remaining <= args.reserve:
                    stopped = f"token expiring ({remaining}s left)"
                    break
                res = _fetch_one(c, rid, index.get(rid, {}), endpoints, headers, cap_dir)
                if res is None:
                    print(f"[{i}/{len(queue)}] {rid} — no projectId in detail_url, skipped")
                    continue
                summary.append(res)
                flag = " THROTTLED" if res.get("throttled") else ""
                print(f"[{i}/{len(queue)}] {res['name'][:34]:36s} {rid} "
                      f"endpoints={res['endpoints_ok']}/{len(endpoints)} "
                      f"docs={res['docs']:<3} ~{remaining // 60}min left{flag}")
                if res.get("throttled"):
                    throttle_hits += 1
                    if throttle_hits >= 3:
                        stopped = "server throttling us (403) — backing off"
                        break
                    time.sleep(45)
                else:
                    throttle_hits = 0
                time.sleep(args.delay)
    except _TokenDead:
        stopped = "token rejected (401)"
    except KeyboardInterrupt:
        stopped = "interrupted"
    finally:
        keep_awake(False)

    (cap_dir / "api_snapshot.json").write_text(
        json.dumps({"captured_at": cap_dir.name, "stopped_because": stopped,
                    "projects": summary}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nStopped: {stopped}")
    print(f"Captured this run: {len(summary)} projects, {sum(p['docs'] for p in summary)} documents")
    print(f"Total captured now: {len(done) + len(summary)} projects")
    if summary:
        print("\nNext:")
        print('  python -c "from engine.detail import build_parsed_snapshot as b; print(b())"')
        print("  python -m collector.upload_docs")


if __name__ == "__main__":
    main()
