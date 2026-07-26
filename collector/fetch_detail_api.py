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


class _TokenDead(Exception):
    """The public-view token stopped being accepted mid-run."""


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
    """(token, endpoint_paths) from whichever capture holds the longest-lived token.

    Scans every capture directory rather than just the newest: the token lives in
    the browser capture from run_detail_assist, which is often not the directory
    this run writes to.
    """
    best: tuple[int, str, list[str]] | None = None
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
        if tok and paths:
            left = _token_seconds_left(tok)
            if best is None or left > best[0]:
                best = (left, tok, paths)

    if best and best[0] > 60:
        return best[1], best[2]
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


def _download_docs(jobs: dict[str, str], out: Path, headers: dict) -> int:
    out.mkdir(parents=True, exist_ok=True)
    ok = 0
    with httpx.Client(timeout=60, verify=False) as c:
        for did, fn in jobs.items():
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", fn)[:120] or did
            if "." not in safe:
                safe += ".pdf"
            p, k = out / safe, 1
            while p.exists():
                p, k = out / f"{k}_{safe}", k + 1
            try:
                r = c.post(DMS_URL, json={"documentId": did, "fileName": fn}, headers=headers)
                if r.status_code == 200 and len(r.content) > 200:
                    p.write_bytes(r.content)
                    ok += 1
            except Exception:
                pass
    return ok


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
    n_docs = _download_docs(docs, cap_dir / "docs" / rid, headers)
    out = {
        "rera_id": rid, "project_id": pid, "project_name": row.get("project_name", ""),
        "promoter_name": row.get("promoter_name", ""),
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "endpoints": api_by_ep,
        "documents": [{"documentId": d, "fileName": f} for d, f in docs.items()],
    }
    (cap_dir / f"{rid}.api.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_ep = sum(1 for v in api_by_ep.values() if isinstance(v, dict) and v.get("status") == "1")
    return {"rera_id": rid, "name": row.get("project_name", ""),
            "endpoints_ok": ok_ep, "docs": n_docs}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="max projects this run (0 = as many as the token allows)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between projects (polite)")
    ap.add_argument("--reserve", type=int, default=90,
                    help="stop this many seconds before the token expires")
    ap.add_argument("--districts", default="",
                    help="comma-separated districts to do first, e.g. 'Pune,Thane'")
    ap.add_argument("--refetch", action="store_true",
                    help="re-fetch projects already captured (off by default)")
    args = ap.parse_args()

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
    summary: list[dict] = []
    stopped = "queue exhausted"

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
                print(f"[{i}/{len(queue)}] {res['name'][:34]:36s} {rid} "
                      f"endpoints={res['endpoints_ok']}/{len(endpoints)} "
                      f"docs={res['docs']:<3} ~{remaining // 60}min left")
                time.sleep(args.delay)
    except _TokenDead:
        stopped = "token rejected (401)"
    except KeyboardInterrupt:
        stopped = "interrupted"

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
