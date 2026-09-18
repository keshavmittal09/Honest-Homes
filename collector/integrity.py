"""Collection-integrity checks: refuse to let a bad run pass for a good one.

Two failures got into production data and neither announced itself:

  1. The index parser recognised only the legacy `P`+11-digit id scheme, so every
     card in the `PR`/`PM`/`PP`/`PC` series introduced from 2025 parsed as an
     empty row. Whole pages read as blank, the crawl's empty-page guard stopped
     it early, and the snapshot came back 5,092 short of the portal's own
     reported total. That shortfall was *written into snapshot.json* -- the file
     recorded `total_reported: 49371` beside `row_count: 44279` -- and nothing
     ever compared the two.

  2. A detail run on 9 September wrote 1,051 records that held a specs stub and
     nothing else: no address, no units, no documents, no dates. They counted as
     collected for nine days and overstated deep coverage by 89%.

Both are cheap to detect and were only expensive because nothing looked. This
module is the thing that looks. It is deliberately advisory-by-default for the
index (a short snapshot is still worth keeping and resuming from) but it marks
the snapshot so that no downstream reader can mistake a partial crawl for a
complete one.

    python -m collector.integrity                 # audit everything on disk
    python -m collector.integrity --strict        # non-zero exit if anything fails
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# A crawl that lands within this fraction of the portal's own count is treated as
# complete; the portal's total drifts by a handful of rows during a long run, so
# demanding an exact match would cry wolf on every successful crawl.
INDEX_TOLERANCE = 0.005          # 0.5%
# A detail record without an address never came back from a real capture.
DETAIL_MIN_FIELD = "address"


def check_index(rows: list[dict], total_reported: int) -> dict:
    """Compare what a crawl stored against what the portal said existed."""
    stored = len({r.get("rera_id") for r in rows if r.get("rera_id")})
    out = {"stored": stored, "total_reported": total_reported,
           "missing": None, "missing_pct": None, "complete": None, "problems": []}
    if not total_reported:
        out["problems"].append("portal total not captured -- completeness unknowable")
        return out
    missing = total_reported - stored
    out["missing"] = missing
    out["missing_pct"] = round(100.0 * missing / total_reported, 2)
    out["complete"] = missing <= total_reported * INDEX_TOLERANCE
    if not out["complete"]:
        out["problems"].append(
            "snapshot holds %d of %d reported projects -- %d missing (%.2f%%)"
            % (stored, total_reported, missing, out["missing_pct"]))

    # An id-scheme regression shows up as a suspiciously pure scheme mix: the
    # portal has served two-letter series since 2025, so a snapshot containing
    # none of them is parsing them away rather than genuinely lacking them.
    schemes: dict[str, int] = {}
    for r in rows:
        rid = (r.get("rera_id") or "").strip()
        if not rid:
            continue
        pre = "".join(c for c in rid[:2] if c.isalpha())
        schemes[pre] = schemes.get(pre, 0) + 1
    out["id_schemes"] = dict(sorted(schemes.items(), key=lambda kv: -kv[1]))
    two_letter = sum(v for k, v in schemes.items() if len(k) == 2)
    if stored > 1000 and two_letter == 0:
        out["problems"].append(
            "no two-letter id scheme (PR/PM/PP/PC) present in %d rows -- the id "
            "pattern is almost certainly dropping post-2025 registrations" % stored)
    return out


def check_detail(records: dict) -> dict:
    """Separate real captures from stubs a failed run left behind."""
    total = len(records)
    stubs, by_date = [], {}
    for rid, rec in records.items():
        addr = rec.get(DETAIL_MIN_FIELD) or {}
        if not (addr.get("pincode") or "").strip():
            stubs.append(rid)
            d = (rec.get("capturedAt") or "?")[:10]
            by_date[d] = by_date.get(d, 0) + 1
    out = {"total": total, "complete": total - len(stubs), "stubs": len(stubs),
           "stub_pct": round(100.0 * len(stubs) / total, 1) if total else 0,
           "stubs_by_capture_date": dict(sorted(by_date.items(), key=lambda kv: -kv[1])),
           "problems": []}
    if stubs:
        out["problems"].append(
            "%d of %d records carry no address -- these are failed captures, not "
            "coverage" % (len(stubs), total))
        # A single date dominating the stubs is a failed run, not scattered noise,
        # and names the run to re-queue.
        for d, n in list(out["stubs_by_capture_date"].items())[:1]:
            if n > 50:
                out["problems"].append(
                    "%d of them were captured on %s -- one failed run, re-collect "
                    "that batch" % (n, d))
    return out


def _print(title: str, res: dict) -> None:
    print("\n%s" % title)
    print("-" * len(title))
    for k, v in res.items():
        if k == "problems":
            continue
        print("  %-24s %s" % (k, v))
    if res.get("problems"):
        for p in res["problems"]:
            print("  FAIL  %s" % p)
    else:
        print("  OK    no problems found")


def audit() -> bool:
    """Audit every snapshot on disk. Returns True when everything passes."""
    ok = True

    for d in sorted(glob.glob(str(DATA / "snapshots" / "index" / "*"))):
        snap = Path(d) / "snapshot.json"
        rowsf = Path(d) / "rows.jsonl"
        if not snap.exists():
            if rowsf.exists():
                print("\nindex %s\n%s\n  SKIP  crawl in progress (no snapshot.json)"
                      % (os.path.basename(d), "-" * (6 + len(os.path.basename(d)))))
            continue
        meta = json.loads(snap.read_text(encoding="utf-8"))
        rows = meta.get("rows") or []
        if not rows and rowsf.exists():
            rows = [json.loads(l) for l in open(rowsf, encoding="utf-8") if l.strip()]
        res = check_index(rows, meta.get("total_reported") or 0)
        _print("index %s" % os.path.basename(d), res)
        ok = ok and not res["problems"]

    parsed = sorted(glob.glob(str(DATA / "snapshots" / "detail_parsed" / "*" / "records.json")))
    if parsed:
        recs = json.loads(Path(parsed[-1]).read_text(encoding="utf-8"))
        res = check_detail(recs)
        _print("detail_parsed %s" % Path(parsed[-1]).parent.name, res)
        ok = ok and not res["problems"]

    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any check fails (for CI or a cron guard)")
    a = ap.parse_args()
    passed = audit()
    print()
    if passed:
        print("ALL CHECKS PASSED")
    else:
        print("CHECKS FAILED -- see FAIL lines above")
    raise SystemExit(0 if passed or not a.strict else 1)
