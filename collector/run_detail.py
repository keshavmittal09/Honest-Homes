"""Human-in-the-loop Tier-2 detail collector (captcha-safe).

You solve the captcha; this script does everything else. It opens each project's
MahaRERA detail page in a real Edge window, waits for you to solve the captcha and
let the details load, then auto-captures + parses + stores ALL data on the page.
The script NEVER touches the captcha — that stays a human action, honouring the
"no bulk captcha-defeat" rule.

Usage (run in your own terminal, not headless):
    python -m collector.run_detail                # first 10 index projects
    python -m collector.run_detail --targets collector/targets.txt
    python -m collector.run_detail --limit 10 --force

Output (per project) under data/snapshots/detail/<YYYY-MM-DD>/:
    <RERA_ID>.html   raw captured page
    <RERA_ID>.json   everything we could extract (parse_detail)
plus a snapshot.json index of the run.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from .parse_detail import extract_detail

ROOT = Path(__file__).resolve().parent.parent
INDEX_GLOB = ROOT / "data" / "snapshots" / "index"
OUT_ROOT = ROOT / "data" / "snapshots" / "detail"


def _load_index() -> dict[str, dict]:
    """rera_id -> index row (needs detail_url, project_name, promoter_name)."""
    dirs = sorted(d for d in INDEX_GLOB.glob("*") if d.is_dir())
    if not dirs:
        raise SystemExit("No index snapshot found — run the index collector first.")
    rows_path = dirs[-1] / "rows.jsonl"
    by_id: dict[str, dict] = {}
    with open(rows_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = r.get("rera_id")
            if rid:
                by_id[rid] = r
    return by_id


def _targets(path: str | None, index: dict[str, dict], limit: int) -> list[str]:
    ids: list[str] = []
    if path and Path(path).exists():
        # utf-8-sig: the file is edited on Windows and picks up a BOM, which would
        # otherwise glue itself to the first id ("﻿P50500000005") so that id
        # never matches the index and is retried on every run.
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                ids.append(line)
    if not ids:  # default: first N from the index (good enough for a first run)
        ids = list(index.keys())
    # de-dup, keep order, cap
    seen, picked = set(), []
    for rid in ids:
        if rid not in seen:
            seen.add(rid)
            picked.append(rid)
        if len(picked) >= limit:
            break
    return picked


def _summary(data: dict) -> str:
    kv = data.get("key_values", {})
    return (f"headings={len(data.get('headings', []))} "
            f"tables={len(data.get('tables', []))} "
            f"fields={len(kv)} docs={len(data.get('document_links', []))} "
            f"text={data.get('text_length', 0)} chars")


def main() -> None:
    ap = argparse.ArgumentParser(description="Human-in-the-loop MahaRERA detail collector")
    ap.add_argument("--targets", default="collector/targets.txt",
                    help="file of RERA IDs (one per line); falls back to first --limit index rows")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--force", action="store_true", help="re-capture even if already saved")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Playwright is not installed. Run:\n"
            "    pip install playwright\n"
            "(uses your installed Edge — no extra browser download needed)."
        )

    index = _load_index()
    targets = _targets(args.targets, index, args.limit)
    if not targets:
        raise SystemExit("No targets to collect.")

    out_dir = OUT_ROOT / datetime.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nCollecting {len(targets)} project detail page(s) into {out_dir}")
    print("A real Edge window will open. For each project: solve the captcha if shown,")
    print("wait until the project details are visible (open any tabs you want), then\n"
          "press Enter back here. Type 's' + Enter to skip one.\n")

    captured: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, channel="msedge")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        for i, rid in enumerate(targets, 1):
            row = index.get(rid, {})
            url = row.get("detail_url") or ""
            name = row.get("project_name", "(unknown)")
            json_path = out_dir / f"{rid}.json"
            if json_path.exists() and not args.force:
                print(f"[{i}/{len(targets)}] {rid} {name} — already captured, skipping.")
                continue
            if not url:
                print(f"[{i}/{len(targets)}] {rid} — no detail_url in index, skipping.")
                continue

            print(f"[{i}/{len(targets)}] {name}  ({rid})\n    {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"    ! navigation issue: {e} (solve/locate manually, then continue)")

            ans = input("    Solve captcha + load details, then press Enter (or 's' to skip): ").strip().lower()
            if ans == "s":
                print("    skipped.")
                continue

            html = page.content()
            data = extract_detail(html, rera_id=rid, source_url=url)
            data["project_name"] = name
            data["promoter_name"] = row.get("promoter_name", "")
            data["captured_at"] = datetime.datetime.now().isoformat(timespec="seconds")

            (out_dir / f"{rid}.html").write_text(html, encoding="utf-8")
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            captured.append({"rera_id": rid, "project_name": name, "summary": _summary(data)})
            print(f"    saved ✓  {_summary(data)}\n")

        browser.close()

    snap = {
        "captured_at": datetime.date.today().isoformat(),
        "source": "maharerait.maharashtra.gov.in/public/project/view (human-in-the-loop)",
        "count": len(captured),
        "projects": captured,
    }
    (out_dir / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. Captured {len(captured)} project(s). Index: {out_dir / 'snapshot.json'}")


if __name__ == "__main__":
    main()
