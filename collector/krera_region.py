"""Karnataka RERA region collector — North & East Bengaluru, end to end.

Captcha-free, token-free, unattended. Unlike MahaRERA this needs no human and no
Claude at all -- plain HTTP against rera.karnataka.gov.in.

Two phases, deliberately separate so the expensive network pass is done once:

  scan   Fetch every project's detail (~9,957), read its precise labelled
         location (District / Taluk / PIN Code / lat-lng), and append a compact
         row to location-index.jsonl. Projects whose PIN is in the target set
         also get their raw detail HTML cached. Resumable: an appNo already in
         the index is skipped, so a killed run picks up where it stopped.

  build  From the cached target HTML: parse the full record, download documents,
         and lay out data/regions/bangalore-north-east/<area>/<PIN>/<RERA-ID>/
         sorted by area and pincode, plus an index.json roll-up.

Why fetch all 9,957: the master list carries no location, so the only way to
find the target pincodes is to look at each project's detail. It is free and
unattended, so the cost is time and politeness, not money or captchas.

    python -m collector.krera_region scan            # the long unattended pass
    python -m collector.krera_region scan --limit 50 # smoke test
    python -m collector.krera_region build           # assemble matched projects
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from .krera import KRera, parse_detail

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "regions" / "bangalore-north-east"
RAW = OUT / "_detail_html"          # cached detail HTML for target matches
LOC_INDEX = OUT / "location-index.jsonl"

# The user's target pincodes -> area label. PIN Code is the precise filter
# (matches the buyer's own list); the label is only for foldering and display.
AREAS: dict[str, str] = {
    # --- North Bengaluru ---
    "560024": "Hebbal", "560077": "Thanisandra",
    "560045": "HBR Layout - Nagawara", "560032": "Nagawara - Hennur Road",
    "560043": "Hennur", "560064": "Yelahanka New Town - Jakkur",
    "560063": "Yelahanka", "560065": "Yelahanka", "560092": "Yelahanka",
    "560106": "Yelahanka", "562149": "Bagalur", "562110": "Devanahalli",
    # --- East Bengaluru ---
    "560066": "Whitefield", "560067": "Kundalahalli - Old Madras Road",
    "560037": "Marathahalli", "560103": "Panathur - Kadubeesanahalli - Bellandur",
    "560087": "Varthur", "560035": "Off Sarjapur Road",
    "560049": "Budigere Cross", "560036": "KR Puram", "562114": "Hoskote",
}
ZONE = {p: ("North" if p in {
    "560024", "560077", "560045", "560032", "560043", "560064", "560063",
    "560065", "560092", "560106", "562149", "562110"} else "East") for p in AREAS}


def _field(html: str, label: str) -> str | None:
    """Value of a labelled field: `label <span>:</span></p></div> <div..>VALUE`.

    Anchored on the label's own markup so it never picks up the page's dropdown
    of every Karnataka pincode -- a naive scrape did exactly that.
    """
    m = re.search(re.escape(label) + r"\s*<span[^>]*>\s*:\s*</span>\s*</p>\s*</div>\s*<div[^>]*>(.*?)</div>",
                  html, re.S)
    if not m:
        return None
    v = re.sub(r"<[^>]+>", " ", m.group(1))
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def _latlng(html: str) -> tuple[float | None, float | None]:
    def one(label):
        m = re.search(label + r"\s*<span[^>]*>\s*:\s*</span>\s*</p>\s*</div>\s*<div[^>]*>\s*<p>\s*([-\d.]+)",
                      html)
        try:
            return float(m.group(1)) if m else None
        except ValueError:
            return None
    return one("Latitude"), one("Longitude")


def location_of(html: str) -> dict:
    """Just the location fields — the cheap read used to decide a match."""
    lat, lng = _latlng(html)
    reg = re.search(r"PRM/KA/RERA/[A-Za-z0-9/\-]+", html)
    return {
        "district": _field(html, "District"),
        "taluk": _field(html, "Taluk"),
        "pincode": (_field(html, "PIN Code") or "").strip() or None,
        "lat": lat, "lng": lng,
        "rera_id": reg.group(0) if reg else None,
    }


def _load_done() -> set[str]:
    done = set()
    if LOC_INDEX.exists():
        for line in LOC_INDEX.open(encoding="utf-8"):
            try:
                done.add(json.loads(line)["appNo"])
            except (ValueError, KeyError):
                continue
    return done


def scan(limit: int = 0, delay: float = 0.4) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    k = KRera()
    k.start()
    raw = k._get("https://rera.karnataka.gov.in/viewAllProjects").decode("utf-8", "replace")
    appnos = re.findall(r"appNo\s*:\s*'([^']+)'", raw)
    print("master list: %d projects" % len(appnos))

    done = _load_done()
    todo = [a for a in appnos if a not in done]
    if limit:
        todo = todo[:limit]
    print("already scanned: %d | to scan: %d" % (len(done), len(todo)))

    matched = strikes = 0
    with LOC_INDEX.open("a", encoding="utf-8") as idx:
        for i, ap in enumerate(todo, 1):
            tid = ap.rsplit("/", 1)[-1]
            try:
                html = k.detail_html(tid)
                strikes = 0
            except Exception as e:
                strikes += 1
                print("  [%d/%d] %s ERR %s" % (i, len(todo), tid, getattr(e, "code", str(e)[:30])))
                if strikes >= 5:
                    print("  5 consecutive failures — the site may be rate-limiting; pausing 60s")
                    time.sleep(60)
                    strikes = 0
                continue

            loc = location_of(html)
            pin = loc.get("pincode")
            hit = pin in AREAS
            row = {"appNo": ap, "tid": tid, **loc,
                   "area": AREAS.get(pin), "zone": ZONE.get(pin)}
            idx.write(json.dumps(row, ensure_ascii=False) + "\n")
            idx.flush()
            if hit:
                (RAW / ("%s.html" % tid)).write_text(html, encoding="utf-8")
                matched += 1
            if i % 50 == 0 or hit:
                print("  [%d/%d] %s pin=%s %s%s"
                      % (i, len(todo), tid, pin, loc.get("taluk") or "",
                         "  <-- MATCH %s" % AREAS.get(pin) if hit else ""))
            time.sleep(delay)

    print("\nscan complete. matched target pincodes: %d (raw HTML cached in %s)" % (matched, RAW))
    print("run:  python -m collector.krera_region build")


def pick(pincodes: list[str], delay: float = 0.4) -> None:
    """Collect specific pincodes from the already-scanned location index.

    Once the full scan has run, every project's pincode is known, so a one-off
    pincode request need not re-scan all 9,957 -- it filters the index, fetches
    only the matching projects' detail (if not already cached), and builds them.
    This is what the operator console calls for an ad-hoc Karnataka pincode run.
    """
    want = {p.strip() for p in pincodes if p.strip()}
    if not LOC_INDEX.exists():
        print("no location index yet — run a full `scan` first (needed once).")
        return
    rows = []
    for line in LOC_INDEX.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if (r.get("pincode") or "") in want:
            rows.append(r)
    print("index holds %d projects in %s" % (len(rows), sorted(want)))
    if not rows:
        print("none found — either not scanned yet, or no projects in those pincodes.")
        return
    RAW.mkdir(parents=True, exist_ok=True)
    k = KRera(); k.start()
    fetched = 0
    for i, r in enumerate(rows, 1):
        hp = RAW / ("%s.html" % r["tid"])
        if hp.exists():
            continue
        try:
            hp.write_text(k.detail_html(r["tid"]), encoding="utf-8")
            fetched += 1
        except Exception as e:
            print("  %s ERR %s" % (r["tid"], getattr(e, "code", str(e)[:30])))
        time.sleep(delay)
    print("cached %d newly-fetched details; building..." % fetched)
    from .krera_build import build
    build(only_pincodes=want)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("--limit", type=int, default=0)
    s.add_argument("--delay", type=float, default=0.4)
    s.add_argument("--pincodes", default="", help="only cache/build these pincodes")
    p = sub.add_parser("pick"); p.add_argument("--pincodes", required=True)
    p.add_argument("--delay", type=float, default=0.4)
    sub.add_parser("build")
    a = ap.parse_args()
    if a.cmd == "scan":
        # --pincodes on scan is an ad-hoc shortcut: if the index already covers
        # the site, just pick; otherwise fall through to a normal full scan.
        if a.pincodes and LOC_INDEX.exists():
            pick([x for x in a.pincodes.split(",")], a.delay)
        else:
            scan(a.limit, a.delay)
    elif a.cmd == "pick":
        pick([x for x in a.pincodes.split(",")], a.delay)
    elif a.cmd == "build":
        from .krera_build import build
        build()
