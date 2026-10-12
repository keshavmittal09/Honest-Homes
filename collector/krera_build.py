"""Assemble the cached Bengaluru K-RERA projects into a sorted folder tree.

Reads the detail pages cached by `krera_region scan`, parses each into the
engine record shape, optionally downloads its documents, and lays them out
sorted by zone -> area, mirroring the Mumbai region layout:

    data/regions/bangalore-north-east/
      index.json                         roll-up, grouped by zone/area
      records.json                       engine-shape records (for scoring/portal)
      by-area/<Zone> Bengaluru/<Area>/<RERA-ID>/
        project.json
        documents/<named>.pdf

Where a project is comes from ITS OWN address block (taluk, village/hobli and,
when printed, pin code and coordinates) -- never from the promoter's, which the
page prints first under the same label names. An earlier build read the
promoter's pin code, so every area label here described the builder's office.

Identity comes from the page header (project name, acknowledgement and
registration numbers) and is cross-checked against K-RERA's own master list.
A cached page with no number at all is an abandoned draft and is left out.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .krera import KRera, parse_detail
from .krera_region import AREAS, ZONE_OF_TALUK, RAW, OUT, zone_of

SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe(s: str, limit: int = 120) -> str:
    out = SAFE.sub("", (s or "").replace("/", "-")).strip(" .")
    return out[:limit] or "x"


def _place(addr: dict) -> str | None:
    """A readable, unambiguous place name from the project's own address.

    "Kasaba" alone is the main hobli of many taluks, so the taluk is appended
    whenever the hobli or village does not already say it.
    """
    place = addr.get("hobli") or addr.get("village")
    taluk = addr.get("taluka")
    if place and taluk and place.lower() not in taluk.lower() and taluk.lower() not in place.lower():
        return "%s, %s" % (place, taluk)
    return place or taluk


def _master() -> tuple[dict, dict]:
    """K-RERA's own register of every project: {reg no: (name, promoter)} and
    {ack no: (name, promoter)}. Empty dicts if it cannot be fetched whole."""
    try:
        from .krera_register import _page, parse_master
        k = KRera()
        k.start()
        rows = parse_master(_page(k, "viewAllProjects"))
    except BaseException as e:           # SystemExit from an incomplete fetch included
        print("  master list unavailable (%s) -- names taken from the page headers" % e)
        return {}, {}
    by_reg = {r: (p, m) for a, r, p, m in rows if r}
    by_ack = {a: (p, m) for a, r, p, m in rows if a}
    return by_reg, by_ack


def _backup() -> None:
    """Keep the previous build before replacing it: it is reversible and cheap."""
    dest = OUT / "_superseded" / time.strftime("%Y-%m-%d-%H%M%S")
    moved = False
    for name in ("records.json", "index.json", "by-area"):
        src = OUT / name
        if src.exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest / name))
            moved = True
    if moved:
        print("previous build kept in %s" % dest.relative_to(OUT.parent.parent.parent))


def build(download_docs: bool = True, doc_delay: float = 0.5,
          only_pincodes: set | None = None) -> None:
    pages = sorted(RAW.glob("*.html"))
    if not pages:
        raise SystemExit("no cached detail pages in %s -- run `krera_region scan` first" % RAW)
    by_reg, by_ack = _master()
    print("cached pages: %d | master list: %d registered, %d total"
          % (len(pages), len(by_reg), len(by_ack)))

    k = KRera()
    k.start()
    records: dict[str, dict] = {}
    roll: list[dict] = []
    skipped = renamed = docs_done = 0
    prepared = []

    for hp in pages:
        html = hp.read_text(encoding="utf-8")
        rec = parse_detail(html, {})
        key = rec.get("rera_id")
        if not key:
            skipped += 1                  # abandoned draft: no ack, no registration no.
            continue
        m = by_reg.get(key) if rec["registered"] else by_ack.get(rec.get("ack_no"))
        if m:
            # The master list is K-RERA's register keyed by number, and the
            # complaint and order lists are built from the same names.
            if (m[0] or "").strip() and m[0].strip() != (rec.get("project_name") or ""):
                renamed += 1
            rec["project_name"] = (m[0] or "").strip() or rec.get("project_name")
            rec["promoter_name"] = (m[1] or "").strip() or rec.get("promoter_name")
        addr = rec["address"]
        pin = addr.get("pincode")
        if only_pincodes and pin not in only_pincodes:
            continue
        zone = zone_of(addr.get("taluka"), pin)
        # What the buyer sees as the area: a known target-pincode label only when
        # the PROJECT's own pin says so, otherwise its village / hobli / taluk.
        area = AREAS.get(pin) or _place(addr)
        addr["locality"] = area
        rec["_zone"], rec["_area"] = zone, area
        records[key] = rec
        prepared.append((hp.stem, key, rec, zone, area))

    _backup()                              # before any new folder exists
    for n, (tid, key, rec, zone, area) in enumerate(prepared, 1):
        folder = (OUT / "by-area" / ("%s Bengaluru" % (zone or "Other"))
                  / _safe(area or "Unlocated") / _safe(key))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "project.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

        if download_docs:
            ddir = folder / "documents"
            for d in rec.get("documents") or []:
                url = d.get("url")
                if not url:
                    continue
                try:
                    blob = k._get(url)
                except Exception:
                    continue
                if not blob or (blob[:4] != b"%PDF" and b"%PDF" not in blob[:1024]):
                    continue             # an HTML error page, not a document
                ddir.mkdir(parents=True, exist_ok=True)
                (ddir / ("%s.pdf" % _safe(d.get("kind") or "document"))).write_bytes(blob)
                docs_done += 1
                time.sleep(doc_delay)

        sp = rec.get("specs") or {}
        addr = rec["address"]
        roll.append({
            "reraId": key, "name": rec.get("project_name"),
            "promoter": rec.get("promoter_name"), "registered": rec["registered"],
            "zone": zone, "area": area, "pincode": addr.get("pincode"),
            "taluk": addr.get("taluka"), "village": addr.get("village"),
            "hobli": addr.get("hobli"),
            "lat": (rec.get("geo") or {}).get("lat"), "lng": (rec.get("geo") or {}).get("lng"),
            "registeredOn": sp.get("registeredOn"), "completion": sp.get("originalCompletion"),
            "unitsTotal": sp.get("unitsTotal"),
            "extensions": sum(1 for e in rec.get("extensions") or [] if e.get("moved")),
            "documents": rec.get("document_count"),
            "folder": str(folder.relative_to(OUT)),
        })
        if n % 100 == 0 or n == len(prepared):
            print("  [%d/%d] %s" % (n, len(prepared), key))

    _backup_and_write(records, roll, docs_done)
    print("\nbuilt %d projects (%d registered); %d cached pages had no number and were left out; "
          "%d names corrected from the master list; %d documents downloaded"
          % (len(roll), sum(1 for r in roll if r["registered"]), skipped, renamed, docs_done))
    print("-> %s" % OUT)


def _backup_and_write(records: dict, roll: list, docs_done: int) -> None:
    (OUT / "records.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    grouped: dict = {}
    for row in sorted(roll, key=lambda x: (x["zone"] or "~", x["area"] or "~", x["name"] or "")):
        grouped.setdefault(row["zone"] or "Other", {}).setdefault(
            row["area"] or "Unlocated", []).append(row)
    (OUT / "index.json").write_text(json.dumps({
        "region": "Bengaluru (K-RERA)",
        "source": "Karnataka RERA (rera.karnataka.gov.in)",
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "locationBasis": "project's own address block (taluk / village / hobli / pin when "
                         "printed); promoter address is never used",
        "projects": len(roll), "documents": docs_done,
        "byZone": grouped,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    build()
