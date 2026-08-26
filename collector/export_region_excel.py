"""Export one region to a workbook the team can actually work in.

Not a data dump. Each sheet answers a question someone will ask:

  Projects      one row per project — the whole record, flattened
  Complaints    one row per complaint, with direction and outcome
  Court cases   declared litigation
  Documents     what exists on the public record, by kind
  Amenities     one row per project — grade per category, distances
  Nearby places one row per place — every school, hospital, station we found
  Builders      rolled up by promoter
  Data quality  what is missing and why, so nobody mistakes a gap for a finding

The last sheet is the point. A spreadsheet invites people to sort by a column and
draw a conclusion, and the fastest way to a wrong conclusion here is to read an
empty cell as a zero. Every blank in this workbook has a reason, and the reason
is written down.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _latest_snapshot() -> dict:
    p = sorted(glob.glob(str(DATA / "snapshots" / "detail_parsed" / "*" / "records.json")))
    if not p:
        raise SystemExit("no parsed snapshot found")
    return json.loads(Path(p[-1]).read_text(encoding="utf-8"))


def _index() -> dict:
    out = {}
    f = DATA / "snapshots" / "index" / "2026-06-02" / "rows.jsonl"
    for line in f.open(encoding="utf-8"):
        r = json.loads(line)
        out[r["rera_id"]] = r
    return out


def _amenities(rid: str, region: str) -> dict | None:
    p = DATA / "regions" / region / "projects" / rid / "amenities" / "amenities-lite.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _pct(a, b):
    return round(100.0 * a / b, 1) if (a and b) else None


def build(region: str, out_path: Path) -> None:
    try:
        import xlsxwriter
    except ImportError:
        raise SystemExit("pip install xlsxwriter")

    from collector.regions import region as region_cfg, targets

    det = _latest_snapshot()
    idx = _index()
    ids = targets(idx, region, det)
    rows = [(r, idx[r], det.get(r)) for r in ids if r in idx]
    captured = [(r, i, d) for r, i, d in rows if d]

    wb = xlsxwriter.Workbook(str(out_path), {"constant_memory": False})
    F = {
        "h": wb.add_format({"bold": True, "bg_color": "#1B4E80", "font_color": "white",
                            "border": 1, "align": "left", "valign": "vcenter", "text_wrap": True}),
        "t": wb.add_format({"bold": True, "font_size": 15, "font_color": "#1B4E80"}),
        "n": wb.add_format({"font_size": 10, "font_color": "#666666", "text_wrap": True, "valign": "top"}),
        "d": wb.add_format({"num_format": "yyyy-mm-dd"}),
        "i": wb.add_format({"num_format": "#,##0"}),
        "red": wb.add_format({"font_color": "#B03A34", "bold": True}),
        "amber": wb.add_format({"font_color": "#A9711A", "bold": True}),
        "green": wb.add_format({"font_color": "#1C8456", "bold": True}),
        "wrap": wb.add_format({"text_wrap": True, "valign": "top"}),
    }

    def sheet(name, headers, widths):
        ws = wb.add_worksheet(name)
        ws.freeze_panes(1, 0)
        for c, (hd, w) in enumerate(zip(headers, widths)):
            ws.write(0, c, hd, F["h"])
            ws.set_column(c, c, w)
        ws.autofilter(0, 0, 0, len(headers) - 1)
        return ws

    # ---------------- Projects -------------------------------------------
    hdr = ["RERA ID", "Project", "Promoter", "Pincode", "Village", "Taluka", "District",
           "Type", "Status", "Registered", "Promised completion", "Revised completion",
           "Lapsed", "Extensions", "Units total", "Units booked", "% booked",
           "Complaints", "By buyer", "By builder", "Unresolved", "Warrants",
           "Court cases", "Documents", "Latitude", "Longitude", "Coords usable",
           "Amenity grade", "Amenity score", "MahaRERA page"]
    ws = sheet("Projects", hdr, [15, 40, 34, 9, 18, 14, 14, 14, 11, 12, 18, 18, 9, 11,
                                 11, 12, 10, 11, 10, 11, 11, 10, 11, 11, 11, 11, 13, 13, 13, 44])
    r = 1
    for rid, ix, d in rows:
        sp = (d or {}).get("specs") or {}
        pc = (d or {}).get("projectComplaints") or {}
        ad = (d or {}).get("address") or {}
        un = (d or {}).get("units") or {}
        geo = (d or {}).get("geo") or {}
        am = _amenities(rid, region) if d else None
        ov = (am or {}).get("overall") or {}
        tot, bk = un.get("total") or sp.get("unitsTotal"), un.get("booked") or sp.get("unitsSold")
        vals = [rid, ix.get("project_name"), ix.get("promoter_name"), ix.get("pincode"),
                ad.get("village"), ad.get("taluka"), ad.get("district") or ix.get("district"),
                sp.get("type"), sp.get("status"), sp.get("registeredOn"),
                sp.get("originalCompletion"), sp.get("revisedCompletion"),
                "YES" if sp.get("lapsed") else ("no" if d else None),
                len((d or {}).get("extensions") or []) if d else None,
                tot, bk, _pct(bk, tot),
                pc.get("count"), pc.get("byBuyer"), pc.get("byBuilder"),
                pc.get("unresolved"), len(pc.get("warrants") or []) if d else None,
                ((d or {}).get("litigation") or {}).get("count"),
                len((d or {}).get("documents") or []) if d else None,
                geo.get("lat"), geo.get("lng"),
                ("yes" if ov.get("known") is not False else "NO — outside region")
                if am else (None if not d else "not assessed"),
                ov.get("grade"), ov.get("score"), ix.get("detail_url")]
        for c, v in enumerate(vals):
            fmt = None
            if c == 12 and v == "YES":
                fmt = F["red"]
            elif c == 27 and v:
                fmt = F["green"] if v in ("A", "B") else F["amber"] if v == "C" else F["red"]
            ws.write(r, c, v, fmt) if fmt else ws.write(r, c, v)
        r += 1

    # ---------------- Complaints -----------------------------------------
    ws = sheet("Complaints", ["RERA ID", "Project", "Promoter", "Complaint no", "Type",
                              "Filed on", "Status", "Resolved", "Direction",
                              "Counts against builder?", "Complainant", "Respondent",
                              "Order date", "Non-compliance", "Recovery warrant"],
               [15, 34, 30, 22, 12, 12, 20, 10, 20, 22, 34, 34, 12, 15, 15])
    DIRN = {"buyer_vs_builder": ("Buyer → Builder", "YES"),
            "builder_vs_buyer": ("Builder → Buyer", "no — builder is the complainant"),
            "business_vs_business": ("Business ↔ Business", "no"),
            None: ("unclear", "excluded"), "unknown": ("unclear", "excluded")}
    r = 1
    for rid, ix, d in captured:
        for c_ in ((d.get("projectComplaints") or {}).get("complaints") or []):
            lbl, counts = DIRN.get(c_.get("direction"), ("unclear", "excluded"))
            w = c_.get("warrant") or {}
            vals = [rid, ix.get("project_name"), ix.get("promoter_name"),
                    c_.get("complaintNo"), c_.get("type"), c_.get("filedOn"),
                    c_.get("status"), "yes" if c_.get("resolved") else "NO",
                    lbl, counts, c_.get("complainant"), c_.get("respondent"),
                    (c_.get("order") or {}).get("approvedOn"),
                    len(c_.get("nonCompliance") or []) or None,
                    "YES" if w else None]
            for cc, v in enumerate(vals):
                f = F["red"] if (cc == 7 and v == "NO") or (cc == 14 and v == "YES") else None
                ws.write(r, cc, v, f) if f else ws.write(r, cc, v)
            r += 1

    # ---------------- Court cases ----------------------------------------
    ws = sheet("Court cases", ["RERA ID", "Project", "Promoter", "Case no", "Court",
                               "Filed on", "Parties", "Note"],
               [15, 34, 30, 22, 26, 12, 40, 46])
    r = 1
    for rid, ix, d in captured:
        for c_ in ((d.get("litigation") or {}).get("cases") or []):
            ws.write_row(r, 0, [rid, ix.get("project_name"), ix.get("promoter_name"),
                                c_.get("caseNo"), c_.get("court"), c_.get("filedOn"),
                                c_.get("parties"), c_.get("note")])
            r += 1

    # ---------------- Documents ------------------------------------------
    ws = sheet("Documents", ["RERA ID", "Project", "Category", "Kind", "File",
                             "Important", "Hosted copy"],
               [15, 34, 26, 34, 46, 11, 11])
    r = 1
    for rid, ix, d in captured:
        for doc in (d.get("documents") or []):
            ws.write_row(r, 0, [rid, ix.get("project_name"), doc.get("category"),
                                doc.get("kind") or doc.get("label"), doc.get("file"),
                                "yes" if doc.get("important") else "",
                                "yes" if doc.get("url") else "no — see MahaRERA"])
            r += 1

    # ---------------- Amenities (per project) ----------------------------
    cats = ["schools", "colleges", "hospitals", "pharmacies", "malls", "markets",
            "transport", "offices", "parks", "dining", "banks", "fitness",
            "entertainment", "worship"]
    hdr = ["RERA ID", "Project", "Overall grade", "Overall score", "Places within 5km"]
    for c_ in cats:
        hdr += ["%s grade" % c_.title(), "%s count" % c_.title(), "%s nearest (m)" % c_.title()]
    ws = sheet("Amenities", hdr, [15, 34, 13, 13, 16] + [11, 11, 14] * len(cats))
    r = 1
    for rid, ix, d in captured:
        am = _amenities(rid, region)
        if not am:
            continue
        ov = am.get("overall") or {}
        ac = am.get("categories") or {}
        row = [rid, ix.get("project_name"), ov.get("grade"), ov.get("score"),
               sum((c_.get("count") or 0) for c_ in ac.values())]
        for key in cats:
            c_ = ac.get(key) or {}
            row += [c_.get("grade"), c_.get("count"), c_.get("nearestM")]
        for cc, v in enumerate(row):
            f = None
            if cc == 2 and v:
                f = F["green"] if v in ("A", "B") else F["amber"] if v == "C" else F["red"]
            ws.write(r, cc, v, f) if f else ws.write(r, cc, v)
        r += 1

    # ---------------- Nearby places --------------------------------------
    ws = sheet("Nearby places", ["RERA ID", "Project", "Category", "Place", "Kind",
                                 "Operator", "Distance (m)", "Walk (min)",
                                 "NIRF rank", "Notable", "Map link"],
               [15, 30, 20, 38, 18, 26, 12, 11, 11, 10, 52])
    r = 1
    for rid, ix, d in captured:
        am = _amenities(rid, region)
        if not am:
            continue
        for key, c_ in (am.get("categories") or {}).items():
            for p in (c_.get("places") or []):
                lat, lon = p.get("lat"), p.get("lon")
                link = ("https://www.google.com/maps/search/?api=1&query=%s,%s" % (lat, lon)) if lat else None
                ws.write_row(r, 0, [rid, ix.get("project_name"), c_.get("label"),
                                    p.get("name"), p.get("kind"), p.get("operator"),
                                    p.get("distanceM"), p.get("walkMinutes"),
                                    (p.get("nirf") or {}).get("rank"),
                                    "yes" if p.get("notable") else "", link])
                r += 1

    # ---------------- Builders -------------------------------------------
    by: dict[str, dict] = {}
    for rid, ix, d in rows:
        k = (ix.get("promoter_name") or "?").strip()
        b = by.setdefault(k, {"n": 0, "cap": 0, "units": 0, "sold": 0, "cx": 0,
                              "buyer": 0, "unres": 0, "lapsed": 0, "ext": 0, "docs": 0})
        b["n"] += 1
        if d:
            sp = d.get("specs") or {}
            pc = d.get("projectComplaints") or {}
            b["cap"] += 1
            b["units"] += (d.get("units") or {}).get("total") or 0
            b["sold"] += (d.get("units") or {}).get("booked") or 0
            b["cx"] += pc.get("count") or 0
            b["buyer"] += pc.get("byBuyer") or 0
            b["unres"] += pc.get("unresolved") or 0
            b["lapsed"] += 1 if sp.get("lapsed") else 0
            b["ext"] += len(d.get("extensions") or [])
            b["docs"] += len(d.get("documents") or [])
    ws = sheet("Builders", ["Promoter", "Projects in region", "Captured", "Units",
                            "Booked", "% booked", "Complaints", "By buyer",
                            "Unresolved", "Lapsed registrations", "Extensions", "Documents"],
               [40, 17, 11, 11, 11, 10, 12, 11, 12, 19, 12, 12])
    r = 1
    for k, b in sorted(by.items(), key=lambda kv: (-kv[1]["buyer"], -kv[1]["n"])):
        vals = [k, b["n"], b["cap"], b["units"] or None, b["sold"] or None,
                _pct(b["sold"], b["units"]), b["cx"] or None, b["buyer"] or None,
                b["unres"] or None, b["lapsed"] or None, b["ext"] or None, b["docs"] or None]
        for cc, v in enumerate(vals):
            f = F["red"] if cc in (8, 9) and v else None
            ws.write(r, cc, v, f) if f else ws.write(r, cc, v)
        r += 1

    # ---------------- Data quality ---------------------------------------
    ws = wb.add_worksheet("Data quality")
    ws.set_column(0, 0, 46)
    ws.set_column(1, 1, 14)
    ws.set_column(2, 2, 88)
    ws.write(0, 0, "Read this before drawing conclusions", F["t"])
    ws.write(1, 0,
             "A blank cell in this workbook almost never means zero. It usually means "
             "MahaRERA has not published that field, or we have not collected the project "
             "yet. Sorting by a column with blanks in it will mislead you.", F["n"])
    ws.set_row(1, 46)

    n_all, n_cap = len(rows), len(captured)
    am_known = am_unknown = 0
    for rid, ix, d in captured:
        am = _amenities(rid, region)
        if not am:
            continue
        if (am.get("overall") or {}).get("known") is False:
            am_unknown += 1
        else:
            am_known += 1
    no_geo = sum(1 for _, _, d in captured if not (d.get("geo") or {}).get("lat"))

    facts = [
        ("Projects in region", n_all,
         "Pincodes %s, plus projects whose filed address or name places them here."
         % ", ".join(region_cfg(region)["pincodes"])),
        ("Full records collected", n_cap,
         "Each is a sweep of all 42 MahaRERA endpoints. The rest have index data only "
         "(name, promoter, pincode) — every detail column is blank for them."),
        ("Still to collect", n_all - n_cap,
         "Collection is captcha-gated: one captcha yields ~90 minutes and ~50 projects."),
        ("Neighbourhood assessed", am_known,
         "Places within 5 km, graded A-E per category."),
        ("Location not confirmed", am_unknown,
         "MahaRERA's coordinates for these fall outside the region — one Kharghar tower "
         "is tagged 450 km away. They are NOT graded. An empty amenity row here means "
         "'we cannot place the building', never 'nothing is nearby'."),
        ("Captured but no coordinates", no_geo,
         "MahaRERA published no geo-tagging, so no neighbourhood directory exists."),
    ]
    ws.write_row(3, 0, ["Measure", "Count", "What it means"], F["h"])
    for i, (k, v, note) in enumerate(facts):
        ws.write(4 + i, 0, k)
        ws.write(4 + i, 1, v)
        ws.write(4 + i, 2, note, F["wrap"])

    row0 = 5 + len(facts)
    ws.write(row0, 0, "Known limitations", F["t"])
    for i, t in enumerate([
        "Complaint DIRECTION is parsed from party names. A complaint the builder filed "
        "against a defaulting buyer is not a consumer grievance — see the 'Counts against "
        "builder?' column before totalling anything.",
        "Distances are straight-line. Road distance is longer, sometimes much longer.",
        "'NIRF rank' is a published government ranking and applies only to colleges. "
        "OpenStreetMap has no star ratings, so no amenity here carries one.",
        "Document rows list what exists on the MahaRERA record. 'Hosted copy = no' means "
        "the file is on the portal but not mirrored by us.",
        "Quarterly progress reports and Form 3 financials are not collected yet.",
    ]):
        ws.write(row0 + 1 + i, 0, "• " + t, F["wrap"])
        ws.merge_range(row0 + 1 + i, 0, row0 + 1 + i, 2, "• " + t, F["wrap"])

    ws.write(row0 + 7, 0, "Generated", F["h"])
    ws.write(row0 + 7, 1, date.today().isoformat())
    ws.write(row0 + 8, 0, "Source", F["h"])
    ws.merge_range(row0 + 8, 1, row0 + 8, 2,
                   "MahaRERA public records; OpenStreetMap (ODbL); Wikidata (CC0); "
                   "NIRF, Ministry of Education", F["wrap"])

    wb.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="kharghar-panvel")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT / ("HonestHomes-%s-%s.xlsx" % (a.region, date.today().isoformat()))
    build(a.region, out)
    print("wrote %s  (%.1f MB)" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
