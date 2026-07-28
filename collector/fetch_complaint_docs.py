"""Download the papers behind every complaint: orders, hearing records, warrants.

These are the evidence for the most serious facts the site publishes about a
project — a signed order, the roznama from the hearing, and the recovery warrant
naming an amount. They are referenced by every complaint but were previously
unmatched by the document rules, so they sorted to the bottom of the priority
list and were cut by the per-project cap. Most projects hold none of them.

This pass walks the captured complaint records directly and fetches only those
documents, for every project already captured, using the same polite pacing.

    python -m collector.run_detail_assist       # if the token has expired
    python -m collector.fetch_complaint_docs
    python -c "from engine.detail import build_parsed_snapshot as b; print(b())"
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from engine.detail import parse_complaints, _sanitised
from .fetch_detail_api import (
    OUT_ROOT, DMS_URL, _reference, _token_seconds_left, _Throttled, keep_awake,
)

import httpx

_RID = re.compile(r"^P\d{11}$")


def _doc_dirs(raw: Path) -> dict[str, Path]:
    """rera_id -> its document folder, wherever the area-sorting put it."""
    root = raw / "docs"
    if not root.is_dir():
        return {}
    return {d.name: d for d in root.rglob("*") if d.is_dir() and _RID.match(d.name)}


def wanted(api: dict) -> list[tuple[str, str]]:
    """(dmsRef, fileName) for every order / roznama / warrant on this project."""
    out: list[tuple[str, str]] = []
    for c in parse_complaints(api, api.get("promoter_name") or ""):
        o = c.get("order") or {}
        if o.get("ref") and o.get("file"):
            out.append((o["ref"], o["file"]))
        w = c.get("warrant") or {}
        if w.get("ref") and w.get("file"):
            out.append((w["ref"], w["file"]))
        for m in c.get("nonCompliance") or []:
            if m.get("roznamaRef") and m.get("roznamaFile"):
                out.append((m["roznamaRef"], m["roznamaFile"]))
    seen, uniq = set(), []
    for ref, fn in out:
        if ref not in seen:
            seen.add(ref)
            uniq.append((ref, fn))
    return uniq


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doc-delay", type=float, default=0.8)
    ap.add_argument("--reserve", type=int, default=90)
    ap.add_argument("--limit", type=int, default=0, help="max projects this run")
    args = ap.parse_args()

    jobs: list[tuple[str, Path, list[tuple[str, str]]]] = []
    for raw in sorted(d for d in OUT_ROOT.glob("*") if d.is_dir() and d.name != ".assist"):
        dirs = _doc_dirs(raw)
        for f in sorted(raw.glob("*.api.json")):
            try:
                api = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not (isinstance(api, dict) and api.get("endpoints")):
                continue
            rid = api["rera_id"]
            want = wanted(api)
            if not want:
                continue
            dest = dirs.get(rid) or (raw / "docs" / rid)
            missing = [(r, fn) for r, fn in want if not (dest / _sanitised(fn)).is_file()]
            if missing:
                jobs.append((rid, dest, missing))

    total_missing = sum(len(m) for _, _, m in jobs)
    if not jobs:
        print("Every complaint document is already on disk.")
        return
    if args.limit:
        jobs = jobs[:args.limit]

    token, _ = _reference()
    print(f"Token good for ~{_token_seconds_left(token) // 60} min")
    print(f"Projects missing complaint papers: {len(jobs)}")
    print(f"Documents to fetch: {total_missing}\n")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    keep_awake(True)

    got = strikes = 0
    try:
        with httpx.Client(timeout=60, verify=False) as c:
            for i, (rid, dest, missing) in enumerate(jobs, 1):
                left = _token_seconds_left(token)
                if left <= args.reserve:
                    print(f"\n-- stopping: token expiring ({left}s left)")
                    break
                dest.mkdir(parents=True, exist_ok=True)
                n = 0
                for ref, fn in missing:
                    p = dest / _sanitised(fn)
                    if p.is_file():
                        continue
                    try:
                        r = c.post(DMS_URL, json={"documentId": ref, "fileName": fn},
                                   headers=headers)
                        if r.status_code == 403:
                            strikes += 1
                            if strikes >= 3:
                                raise _Throttled()
                            time.sleep(20 * strikes)
                            continue
                        if r.status_code == 200 and len(r.content) > 200:
                            p.write_bytes(r.content)
                            n += 1
                            strikes = 0
                    except _Throttled:
                        raise
                    except Exception:
                        pass
                    time.sleep(args.doc_delay)
                got += n
                print(f"[{i}/{len(jobs)}] {rid} {n}/{len(missing)} complaint papers "
                      f"~{left // 60}min left")
    except _Throttled:
        print("\n-- server throttling; stopping to stay polite.")
    finally:
        keep_awake(False)

    print(f"\nFetched {got} complaint documents.")
    print('Next: python -c "from engine.detail import build_parsed_snapshot as b; print(b())"')


if __name__ == "__main__":
    main()
