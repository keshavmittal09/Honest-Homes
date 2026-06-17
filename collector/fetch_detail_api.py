"""Fetch full project detail data + documents via the MahaRERA public API.

The detail page is a public REST API gated by a single "public view" token that a
human obtains by solving ONE captcha (see run_detail_assist.py, which records the
token in <RID>.api.json). With that token we can fetch any project's full data by
projectId and download every document by its DMS reference — no per-project captcha.

Usage:
    python -m collector.fetch_detail_api                 # first 10 index projects
    python -m collector.fetch_detail_api --limit 10

Reads the token + endpoint list from the most recent browser capture
(data/snapshots/detail/<date>/*.api.json). If the token has expired, solve one
fresh captcha with run_detail_assist.py to mint a new one.
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
UUID = re.compile(r"^[0-9a-fA-F-]{36}$")
_VIEW = re.compile(r"/view/(\d+)")


def _latest_capture_dir() -> Path:
    dirs = sorted(x for x in OUT_ROOT.glob("*") if x.is_dir() and x.name != ".assist")
    if not dirs:
        raise SystemExit("No prior capture found. Solve one captcha with run_detail_assist first.")
    return dirs[-1]


def _reference(cap_dir: Path) -> tuple[str, list[str]]:
    """Return (token, endpoint_paths) from a reference *.api.json with an accessToken."""
    for f in cap_dir.glob("*.api.json"):
        api = json.loads(f.read_text(encoding="utf-8"))
        tok = None
        paths: list[str] = []
        for a in api:
            if "authenticatePublic" in a["url"]:
                try:
                    tok = a["json"]["responseObject"]["accessToken"]
                except Exception:
                    pass
            p = urlparse(a["url"]).path
            if "/public/projectregistartion/" in p or "/complaint/" in p or "/reatappeal/" in p:
                if p not in paths:
                    paths.append(p)
        if tok:
            return tok, paths
    raise SystemExit("No accessToken in any capture. Re-mint with run_detail_assist.")


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between projects (polite)")
    args = ap.parse_args()

    index = _load_index()
    targets = _targets("collector/targets.txt", index, args.limit)
    cap_dir = _latest_capture_dir()
    token, endpoints = _reference(cap_dir)
    left = _token_seconds_left(token)
    if left < 60:
        raise SystemExit(f"Token expired/expiring ({left}s). Solve one captcha with run_detail_assist to re-mint.")
    print(f"Token valid ~{left}s; {len(endpoints)} endpoints; {len(targets)} projects -> {cap_dir}")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}

    summary = []
    with httpx.Client(timeout=45, verify=False) as c:
        for i, rid in enumerate(targets, 1):
            row = index.get(rid, {})
            url = row.get("detail_url", "")
            name = row.get("project_name", "")
            m = _VIEW.search(url)
            if not m:
                print(f"[{i}/{len(targets)}] {rid} — no projectId in detail_url, skip"); continue
            pid = int(m.group(1))

            # promoter user-profile id (some endpoints need it)
            upid = None
            api_by_ep: dict[str, dict] = {}
            for path in endpoints:
                ep = path.rsplit("/", 1)[-1]
                body = {"projectId": pid}
                if "romoter" in ep and upid:
                    body["userProfileId"] = upid
                try:
                    r = c.post(HOST + path, json=body, headers=headers)
                    if r.status_code == 401:
                        raise SystemExit("Token expired mid-run — re-mint with run_detail_assist.")
                    if r.headers.get("content-type", "").startswith("application/json"):
                        j = r.json()
                        api_by_ep[ep] = j
                        if ep == "getProjectAndAssociatedPromoterDetails" and isinstance(j.get("responseObject"), dict):
                            blob = json.dumps(j["responseObject"])
                            mm = re.search(r'"userProfileId"\s*:\s*(\d+)', blob)
                            if mm:
                                upid = int(mm.group(1))
                except SystemExit:
                    raise
                except Exception:
                    pass

            docs = _collect_doc_jobs(api_by_ep)
            n_docs = _download_docs(docs, cap_dir / "docs" / rid, headers)

            out = {
                "rera_id": rid, "project_id": pid, "project_name": name,
                "promoter_name": row.get("promoter_name", ""),
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "endpoints": {k: v for k, v in api_by_ep.items()},
                "documents": [{"documentId": d, "fileName": f} for d, f in docs.items()],
            }
            (cap_dir / f"{rid}.api.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            ok_ep = sum(1 for v in api_by_ep.values() if isinstance(v, dict) and v.get("status") == "1")
            summary.append({"rera_id": rid, "name": name, "endpoints_ok": ok_ep, "docs": n_docs})
            print(f"[{i}/{len(targets)}] {name} ({rid}) pid={pid}: endpoints_ok={ok_ep}/{len(endpoints)} docs={n_docs}")
            time.sleep(args.delay)

    (cap_dir / "api_snapshot.json").write_text(
        json.dumps({"captured_at": cap_dir.name, "projects": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone. {len(summary)} projects. Index: {cap_dir / 'api_snapshot.json'}")


if __name__ == "__main__":
    main()
