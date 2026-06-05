"""Runner: monthly captcha-free crawl of the MahaRERA project index.

This walks the public, captcha-free results list page by page, parses each page into
index rows, and writes a dated snapshot. It is deliberately polite (see PoliteClient)
and resumable (see IndexSnapshotStore) so a long monthly run survives interruption.

It does NOT touch any captcha-gated detail page.

Usage:
    python -m collector.run_index --max-pages 2 --dump-html   # smoke test
    python -m collector.run_index                             # full monthly run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from .client import PoliteClient
from .parse_index import parse_index_page, parse_total_count
from .storage import IndexSnapshotStore

log = logging.getLogger("honesthomes.run_index")

SEARCH_PATH = "/projects-search-result"
MAHARASHTRA_STATE = 27  # observed value of project_state for Maharashtra
PAGE_SIZE_ASSUMED = 10  # the site shows ~10/page; only used to estimate page count


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _page_params(page: int) -> dict:
    return {"project_state": MAHARASHTRA_STATE, "project_district": 0, "page": page}


def run(max_pages: int | None, dump_html: bool, resume: bool,
        min_delay: float, max_delay: float) -> int:
    store = IndexSnapshotStore(resume=resume)
    if resume:
        log.info("resuming into snapshot folder %s", store.run_date)
    ckpt = store.load_checkpoint() if resume else {"last_page": 0, "seen_ids": set()}
    seen: set[str] = ckpt["seen_ids"]
    start_page = ckpt["last_page"] + 1

    total_reported = 0
    pages_done = ckpt["last_page"]
    empty_streak = 0  # consecutive pages yielding no new rows => we've reached the end

    log.info("starting index crawl at page %d (resume=%s, delay=%.0f-%.0fs)",
             start_page, resume, min_delay, max_delay)

    with PoliteClient(min_delay=min_delay, max_delay=max_delay) as client:
        page = start_page
        while True:
            if max_pages is not None and (page - start_page) >= max_pages:
                log.info("hit --max-pages limit (%d)", max_pages)
                break

            url = SEARCH_PATH
            # On a sustained failure (the client already retried 4x internally), the
            # gov site is likely rate-limiting or briefly down. Rather than ending the
            # whole run, cool down for progressively longer and try the page again.
            # Only give up on a page after several long cooldowns.
            resp = None
            for cooldown in (60, 180, 300, 600):
                try:
                    resp = client.get(url, params=_page_params(page))
                    break
                except Exception:
                    log.warning(
                        "page %d failed; cooling down %ds before retry (progress saved)",
                        page, cooldown,
                    )
                    time.sleep(cooldown)
            if resp is None:
                log.error("page %d still failing after long cooldowns; stopping cleanly "
                          "(re-run later to resume from here)", page)
                break

            html = resp.text
            if dump_html:
                p = store.dump_html(page, html)
                log.info("dumped raw HTML -> %s", p)

            if total_reported == 0:
                total_reported = parse_total_count(html)
                if total_reported:
                    est = -(-total_reported // PAGE_SIZE_ASSUMED)  # ceil
                    log.info("site reports %d projects (~%d pages)", total_reported, est)

            rows = parse_index_page(
                html, source_url=str(resp.url), fetched_at=_now()
            )
            new_rows = [r for r in rows if r.rera_id not in seen]
            for r in new_rows:
                seen.add(r.rera_id)

            store.append_rows(new_rows)
            pages_done = page
            store.save_checkpoint(pages_done, seen)
            log.info("page %d: %d rows (%d new), %d total", page, len(rows), len(new_rows), len(seen))

            # An empty page is ambiguous: it can mean "end of results" OR a transient
            # blip where the site briefly served an unparseable/blocked page (we saw
            # 200 OK with no cards mid-crawl). Distinguish by position: only believe
            # "end" when we're near the EXPECTED last page (from the reported total).
            # Otherwise treat empties as blips — skip and keep going, giving up only
            # after a long run of them.
            expected_last = -(-total_reported // PAGE_SIZE_ASSUMED) if total_reported else None
            near_expected_end = expected_last is not None and page >= expected_last - 2

            if not rows:  # nothing parsed at all from this page
                empty_streak += 1
                if near_expected_end and empty_streak >= 2:
                    log.info("two empty pages near expected end (~%s); done", expected_last)
                    break
                if empty_streak >= 8:
                    log.warning(
                        "%d consecutive empty pages at page %d (expected end ~%s) — likely "
                        "blocked, not end. Stopping; re-run to resume from here.",
                        empty_streak, page, expected_last,
                    )
                    break
                log.info("empty page %d (streak %d) — treating as transient blip, continuing",
                         page, empty_streak)
            else:
                empty_streak = 0

            page += 1

    snap_path = store.finalize(
        total_reported=total_reported,
        pages_fetched=pages_done,
        source="maharera.maharashtra.gov.in/projects-search-result",
    )
    print(f"\nDone. {len(seen)} unique projects -> {snap_path}")
    if total_reported and len(seen) < total_reported and max_pages is None:
        log.warning(
            "collected %d of %d reported — investigate before trusting this snapshot",
            len(seen), total_reported,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MahaRERA captcha-free index collector")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="stop after N pages (smoke testing). Omit for full run.")
    ap.add_argument("--dump-html", action="store_true",
                    help="save raw page HTML to verify selectors against ground truth.")
    ap.add_argument("--no-resume", action="store_true",
                    help="ignore any existing checkpoint and start from page 1.")
    ap.add_argument("--min-delay", type=float, default=4.0,
                    help="min seconds between requests (raise to avoid rate-limits).")
    ap.add_argument("--max-delay", type=float, default=8.0,
                    help="max seconds between requests.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return run(max_pages=args.max_pages, dump_html=args.dump_html,
               resume=not args.no_resume,
               min_delay=args.min_delay, max_delay=args.max_delay)


if __name__ == "__main__":
    raise SystemExit(main())
