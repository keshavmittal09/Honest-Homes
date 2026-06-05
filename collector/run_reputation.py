"""Runner: collect the captcha-free MahaRERA reputation signals.

Two sources, both public list pages (no captcha):
  • Promoter-wise complaints  (~5,027 promoters, paginated 10/page)
  • Deregistered/revoked list  (single page, ~450 projects)

Writes a dated snapshot under data/snapshots/reputation/<date>/ with:
  • complaints.jsonl   — {promoter, complaints, promoter_id}
  • revoked.jsonl      — {rera_id, project_name, promoter}
  • snapshot.json      — assembled summary

Polite + resumable like the index collector. NO captcha-gated pages are touched.

Usage:
  python -m collector.run_reputation                 # full run
  python -m collector.run_reputation --max-pages 3   # smoke test
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .client import PoliteClient
from .parse_reputation import parse_complaints_page, parse_revoked_page

log = logging.getLogger("honesthomes.run_reputation")

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
COMPLAINTS_PATH = "/promoter-complaint-report"
REVOKED_PATH = "/list_of_projects_deregistered"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_dir(run_date: str | None) -> Path:
    d = DATA_ROOT / "snapshots" / "reputation" / (run_date or date.today().isoformat())
    d.mkdir(parents=True, exist_ok=True)
    return d


def collect_revoked(client: PoliteClient, store: Path) -> int:
    log.info("collecting revoked/deregistered projects")
    resp = client.get(REVOKED_PATH)
    rows = parse_revoked_page(resp.text)
    with (store / "revoked.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            r["source_url"] = str(resp.url)
            r["fetched_at"] = _now()
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    log.info("revoked: %d projects", len(rows))
    return len(rows)


def collect_complaints(client: PoliteClient, store: Path, max_pages: int | None) -> int:
    log.info("collecting promoter-wise complaints")
    out_path = store / "complaints.jsonl"
    seen: set[str] = set()
    fh = out_path.open("w", encoding="utf-8")
    page = 1
    empty_streak = 0
    try:
        while True:
            if max_pages is not None and page > max_pages:
                break
            try:
                resp = client.get(COMPLAINTS_PATH, params={"page": page})
            except Exception:
                # cool down and retry once on a sustained failure, then stop cleanly
                log.warning("complaints page %d failed; cooling 60s", page)
                time.sleep(60)
                try:
                    resp = client.get(COMPLAINTS_PATH, params={"page": page})
                except Exception:
                    log.error("complaints page %d still failing; stopping", page)
                    break
            rows = parse_complaints_page(resp.text)
            new = [r for r in rows if r["promoter"] and r["promoter"].lower() not in seen]
            for r in new:
                seen.add(r["promoter"].lower())
                r["source_url"] = str(resp.url)
                r["fetched_at"] = _now()
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            log.info("complaints page %d: %d rows (%d new), %d total", page, len(rows), len(new), len(seen))
            if not rows:
                empty_streak += 1
                if empty_streak >= 2:
                    log.info("two empty complaint pages; done")
                    break
            else:
                empty_streak = 0
            page += 1
    finally:
        fh.close()
    log.info("complaints: %d promoters", len(seen))
    return len(seen)


def run(max_pages: int | None) -> int:
    store = _store_dir(None)
    log.info("reputation run -> %s", store)
    with PoliteClient(min_delay=8, max_delay=15) as client:
        n_revoked = collect_revoked(client, store)
        n_complaints = collect_complaints(client, store, max_pages)

    summary = {
        "captured_at": store.name,
        "source": "maharera.maharashtra.gov.in",
        "complaints_promoters": n_complaints,
        "revoked_projects": n_revoked,
    }
    (store / "snapshot.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nDone. complaints={n_complaints} promoters, revoked={n_revoked} projects -> {store}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MahaRERA captcha-free reputation collector")
    ap.add_argument("--max-pages", type=int, default=None, help="limit complaint pages (smoke test)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return run(max_pages=args.max_pages)


if __name__ == "__main__":
    raise SystemExit(main())
