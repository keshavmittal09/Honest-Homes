"""Re-download documents for projects whose JSON was captured but whose files were not.

A project counts as "captured" once its API responses are on disk, so the
incremental skip in fetch_detail_api will never revisit it. That is correct for
the structured data — but if the document downloads were refused at the time (the
server answers 403 "Restricted due to multiple requests" when pushed too hard),
those projects are left permanently with a full paper trail listed and no files
behind it, and nothing would ever go back for them.

This pass finds exactly those projects and fetches only their documents, reusing
the same token and the same polite pacing. It never re-requests the JSON.

    python -m collector.run_detail_assist     # if the token has expired
    python -m collector.backfill_docs
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .fetch_detail_api import (
    OUT_ROOT, _download_docs, _reference, _token_seconds_left, _Throttled, keep_awake,
)


def gaps() -> list[tuple[str, Path, dict]]:
    """(rera_id, capture_dir, api_record) for captures with refs but no files."""
    out = []
    for f in sorted(OUT_ROOT.glob("*/*.api.json")):
        try:
            api = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not (isinstance(api, dict) and api.get("rera_id") and api.get("documents")):
            continue
        rid = api["rera_id"]
        ddir = f.parent / "docs" / rid
        have = len(os.listdir(ddir)) if ddir.is_dir() else 0
        if have == 0:
            out.append((rid, f.parent, api))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doc-delay", type=float, default=0.8)
    ap.add_argument("--max-docs", type=int, default=25)
    ap.add_argument("--reserve", type=int, default=90)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    todo = gaps()
    if not todo:
        print("No gaps — every captured project already has its documents.")
        return
    if args.limit:
        todo = todo[:args.limit]

    token, _ = _reference()
    print(f"Token good for ~{_token_seconds_left(token) // 60} min")
    print(f"Projects missing documents: {len(todo)}\n")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    keep_awake(True)

    fixed = total = strikes = 0
    for i, (rid, cap_dir, api) in enumerate(todo, 1):
        left = _token_seconds_left(token)
        if left <= args.reserve:
            print(f"\n-- stopping: token expiring ({left}s left)")
            break
        jobs = {d["documentId"]: d["fileName"] for d in api["documents"]
                if d.get("documentId") and d.get("fileName")}
        try:
            n, written = _download_docs(jobs, cap_dir / "docs" / rid, headers,
                                        delay=args.doc_delay, max_docs=args.max_docs)
            strikes = 0
        except _Throttled:
            n, written = 0, []
            strikes += 1
            print(f"[{i}/{len(todo)}] {rid} THROTTLED — backing off 60s")
            time.sleep(60)
            if strikes >= 3:
                print("-- server is still throttling; stopping so we stay polite.")
                break
            continue

        # Record which references actually landed, so the site can link only those.
        for d in api["documents"]:
            d["downloaded"] = d.get("fileName") and any(
                w.endswith(d["fileName"].replace(" ", "_")[:60]) or w in written for w in written)
        (cap_dir / f"{rid}.api.json").write_text(
            json.dumps(api, ensure_ascii=False, indent=2), encoding="utf-8")

        total += n
        fixed += 1 if n else 0
        print(f"[{i}/{len(todo)}] {api.get('project_name','')[:32]:34s} {rid} "
              f"refs={len(jobs):<4} downloaded={n:<3} ~{left // 60}min left")

    print(f"\nBackfilled {fixed}/{len(todo)} projects, {total} documents.")
    if fixed:
        print("\nNext:")
        print('  python -c "from engine.detail import build_parsed_snapshot as b; print(b())"')


if __name__ == "__main__":
    main()
