"""Backfill promoter, land-owner and previous-project data from cached K-RERA HTML.

The K-RERA detail page is tabbed:

    Promoter Details (#home) | Project Details (#menu1) |
    Uploaded Documents (#menu2) | Enquired Documents (#menu4) |
    Complaints (#menu-complaints) | Quarterly Updates (#quarter)

Only `#home` and `#menu1` are rendered server-side; the rest load over AJAX.
The original parse read `#menu1` only, so `promoter_name` came back set on just
14.7% of records and the promoter's identity -- type, PAN, registered address,
company registration number -- was missing entirely, even though `#home` was
sitting in the HTML we had already cached. This reads that pane, so nothing is
re-fetched and promoter coverage goes to ~96%.

Field labels inside the pane are wrapped as

    <p class="text-right">LABEL <span class="space_LR">:</span></p>
    </div><div class="col-..."><p>VALUE</p></div>

and the promoter's own name is labelled just "Name", which also appears in the
Authorized Signatory block below it. So the promoter block is cut at
"Authorized Signatory" before any label is read -- otherwise a firm's projects
would be attributed to whoever happened to sign for them.

    python -m collector.krera_promoter --region bangalore-north-east
    python -m collector.krera_promoter --region bangalore-north-east --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def _field(segment: str, label: str) -> str | None:
    """Value of one labelled field, requiring the label to be the whole of its
    `text-right` paragraph.

    Anchoring on the enclosing <p> is what separates "Name" from "Project Name"
    and "PAN Number"; a bare substring search would match the tail of a longer
    label and silently return the wrong field's value.

    The class is matched loosely because the page mixes `class="text-right"` and
    `class="text-right "` -- the signatory block uses the trailing-space form, so
    a tight match silently skipped that whole section.
    """
    m = re.search(
        r'<p[^>]*class="[^"]*text-right[^"]*"[^>]*>\s*' + re.escape(label) +
        r'\s*<span[^>]*>\s*:\s*</span>\s*</p>\s*</div>\s*<div[^>]*>(.*?)</div>',
        segment, re.S)
    if not m:
        return None
    v = re.sub(r"<[^>]+>", " ", m.group(1))
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def _pane(html: str, pane_id: str, next_ids: tuple[str, ...]) -> str:
    """The markup of one tab pane, cut at whichever following pane starts first."""
    m = re.search(r'<div[^>]*id=["\']%s["\']' % re.escape(pane_id), html)
    if not m:
        return ""
    start = m.start()
    end = len(html)
    for nid in next_ids:
        mm = re.search(r'<div[^>]*id=["\']%s["\']' % re.escape(nid), html[start:])
        if mm:
            end = min(end, start + mm.start())
    return html[start:end]


def parse_promoter_pane(html: str) -> dict:
    """Promoter identity and authorised signatory from the #home pane."""
    home = _pane(html, "home", ("menu1", "menu2", "menu4", "menu-complaints", "quarter"))
    if not home:
        return {}

    # The promoter's own block ends where the signatory's begins.
    cut = re.search(r"Authorized\s+Signatory", home, re.I)
    promo = home[:cut.start()] if cut else home

    out: dict = {}
    name = _field(promo, "Name")
    ptype = _field(promo, "Promoter Type")
    pan = _field(promo, "PAN Number")
    creg = _field(promo, "Company Registration No.")
    if name:
        out["promoter_name"] = name
    promoter = {
        "type": ptype,
        "pan": pan,
        "companyRegNo": creg,
        "address": _field(promo, "Address"),
        "district": _field(promo, "District"),
        "state": _field(promo, "State/UT"),
        "pincode": _field(promo, "PIN Code"),
    }
    if any(promoter.values()):
        out["promoter"] = {k: v for k, v in promoter.items() if v}

    if cut:
        sig = home[cut.start():]
        sname = _field(sig, "Name")
        if sname:
            out["signatory"] = {"name": sname, "address": _field(sig, "Address")}

    # "Project Land Owner Details" and "Previous Project Details (Last 5 years
    # only)" are headings only in the server-rendered HTML -- across 200 cached
    # files they carried land-owner rows twice and previous-project rows never.
    # Their tables come over AJAX like the complaints and quarterly-update tabs,
    # so they are deliberately not parsed here: an extractor aimed at an empty
    # section reads whatever table follows it, which is the registration table,
    # and would file that as a promoter's track record.
    return out


def _tid_map(region_dir: Path) -> dict[str, str]:
    """rera_id -> cache key, from the location index.

    A registered project's record key is its PRM registration number while the
    cached file is named for the ACK's trailing digits, so the two only join
    through this index. An application-only record is keyed by its ACK already,
    which the caller falls back to.
    """
    out: dict[str, str] = {}
    p = region_dir / "location-index.jsonl"
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("rera_id") and r.get("tid"):
                out[r["rera_id"]] = r["tid"]
    return out


def run(region: str, dry_run: bool = False) -> None:
    region_dir = DATA / "regions" / region
    rec_path = region_dir / "records.json"
    records = json.loads(rec_path.read_text(encoding="utf-8"))
    tids = _tid_map(region_dir)
    cache_dir = region_dir / "_detail_html"

    stats = {"records": len(records), "no_cache": 0, "no_pane": 0,
             "promoter_name": 0, "promoter_block": 0, "pan": 0,
             "signatory": 0, "updated": 0}
    before = sum(1 for r in records.values() if (r.get("promoter_name") or "").strip())

    for rid, rec in records.items():
        # A registered project joins its cached file only through the location
        # index, because the record is keyed by its PRM registration number and
        # the file is named for the ACK. Those two numbers are unrelated: the
        # project registered .../190525/002577 is cached as 005072.html, while
        # 002577.html is a different project altogether. So the trailing digits
        # of a PRM key must never be used as a cache key -- doing so reads a
        # stranger's promoter and files it against this project. Fall back only
        # when the record key already *is* a bare ACK id, which is how the
        # application-stage records are keyed.
        tid = tids.get(rid)
        if not tid and re.fullmatch(r"\d{4,8}", rid.strip()):
            tid = rid.strip()
        f = cache_dir / ("%s.html" % tid) if tid else None
        if not (f and f.exists()):
            stats["no_cache"] += 1
            continue
        html = f.read_text(encoding="utf-8", errors="ignore")
        got = parse_promoter_pane(html)
        if not got:
            stats["no_pane"] += 1
            continue

        changed = False
        # Only fill a blank promoter_name; never overwrite one already parsed
        # from the project tab, which is the registrant of record.
        if got.get("promoter_name") and not (rec.get("promoter_name") or "").strip():
            rec["promoter_name"] = got["promoter_name"]
            stats["promoter_name"] += 1
            changed = True
        for key in ("promoter", "signatory"):
            if key in got and not rec.get(key):
                rec[key] = got[key]
                changed = True
        if got.get("promoter"):
            stats["promoter_block"] += 1
            if got["promoter"].get("pan"):
                stats["pan"] += 1
        if got.get("signatory"):
            stats["signatory"] += 1
        if changed:
            stats["updated"] += 1

    after = sum(1 for r in records.values() if (r.get("promoter_name") or "").strip())
    n = len(records)
    print("region            : %s" % region)
    print("records           : %d" % n)
    print("no cached html    : %d" % stats["no_cache"])
    print("pane not found    : %d" % stats["no_pane"])
    print("---")
    print("promoter_name     : %d -> %d  (%.1f%% -> %.1f%%)"
          % (before, after, 100.0 * before / n, 100.0 * after / n))
    print("promoter block    : %d (%.1f%%)" % (stats["promoter_block"], 100.0 * stats["promoter_block"] / n))
    print("  with PAN        : %d (%.1f%%)" % (stats["pan"], 100.0 * stats["pan"] / n))
    print("signatory         : %d (%.1f%%)" % (stats["signatory"], 100.0 * stats["signatory"] / n))
    print("records updated   : %d" % stats["updated"])

    if dry_run:
        print("\n(dry run -- records.json not written)")
        return
    rec_path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nwrote %s" % rec_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="bangalore-north-east")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    run(a.region, a.dry_run)
