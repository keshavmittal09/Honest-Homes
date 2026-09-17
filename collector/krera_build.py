"""Assemble the matched North/East Bengaluru projects into a sorted folder tree.

Reads the target-pincode matches cached by `krera_region scan`, parses each into
the engine record shape, downloads its documents, and lays them out sorted by
zone -> area -> pincode, mirroring the Mumbai region layout the user asked for:

    data/regions/bangalore-north-east/
      index.json                         roll-up, grouped by zone/area/pincode
      records.json                       engine-shape records (for scoring/portal)
      by-area/<Zone>/<Area> (<PIN>)/<RERA-ID>/
        project.json
        documents/<named>.pdf

Location is taken from the precise labelled fields (PIN Code / Taluk / lat-lng),
not the hardcoded placeholders in krera.parse_detail -- so every project carries
its real pincode and coordinates.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .krera import KRera, parse_detail
from .krera_region import AREAS, ZONE, RAW, LOC_INDEX, OUT, location_of, _field, _latlng

SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe(s: str, limit: int = 120) -> str:
    out = SAFE.sub("", (s or "").replace("/", "-")).strip(" .")
    return out[:limit] or "x"


def _matched_rows() -> list[dict]:
    rows = []
    if not LOC_INDEX.exists():
        raise SystemExit("no location-index.jsonl — run `krera_region scan` first")
    for line in LOC_INDEX.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if (r.get("pincode") or "") in AREAS:
            rows.append(r)
    return rows


def build(download_docs: bool = True, doc_delay: float = 0.5, only_pincodes: set | None = None) -> None:
    rows = _matched_rows()
    if only_pincodes:
        rows = [r for r in rows if (r.get('pincode') or '') in only_pincodes]
    print("matched target-pincode projects: %d" % len(rows))
    k = KRera()
    k.start()

    records: dict[str, dict] = {}
    roll: list[dict] = []
    docs_done = missing_html = 0

    for n, r in enumerate(rows, 1):
        tid = r["tid"]
        hp = RAW / ("%s.html" % tid)
        if not hp.exists():
            missing_html += 1
            continue
        html = hp.read_text(encoding="utf-8")

        # names/promoter from the master-list row would be ideal, but the scan
        # kept only location; the detail page carries them too, so pull from there.
        name = _field(html, "Project Name") or None
        promoter = None
        rec = parse_detail(html, {"name": name, "promoter": promoter, "reg": r.get("rera_id")})

        pin = r["pincode"]
        lat, lng = _latlng(html)
        # Overwrite the placeholder location with the real, precise values.
        rec["address"] = {
            "district": r.get("district") or "Bengaluru Urban",
            "taluka": r.get("taluk"), "village": None,
            "pincode": pin, "locality": AREAS.get(pin),
        }
        rec["geo"] = {"lat": lat, "lng": lng} if lat and lng else {}
        rec["_zone"] = ZONE.get(pin)
        rec["_area"] = AREAS.get(pin)
        rid = rec.get("rera_id") or r.get("rera_id") or tid
        records[rid] = rec

        # folder: by-area/<Zone> Bengaluru/<Area> (<PIN>)/<RERA-ID>/
        folder = (OUT / "by-area" / ("%s Bengaluru" % ZONE.get(pin))
                  / ("%s (%s)" % (AREAS.get(pin), pin)) / _safe(rid))
        (folder).mkdir(parents=True, exist_ok=True)
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
                if not blob or blob[:4] not in (b"%PDF",) and b"%PDF" not in blob[:1024]:
                    # not a PDF (often an HTML error) — skip rather than save junk
                    continue
                ddir.mkdir(parents=True, exist_ok=True)
                (ddir / ("%s.pdf" % _safe(d.get("kind") or "document"))).write_bytes(blob)
                docs_done += 1
                time.sleep(doc_delay)

        roll.append({
            "reraId": rid, "name": rec.get("project_name"),
            "promoter": rec.get("promoter_name"),
            "zone": ZONE.get(pin), "area": AREAS.get(pin), "pincode": pin,
            "taluk": r.get("taluk"), "lat": lat, "lng": lng,
            "registeredOn": (rec.get("specs") or {}).get("registeredOn"),
            "completion": (rec.get("specs") or {}).get("originalCompletion"),
            "unitsTotal": (rec.get("specs") or {}).get("unitsTotal"),
            "extensions": len(rec.get("extensions") or []),
            "documents": rec.get("document_count"),
            "folder": str(folder.relative_to(OUT)),
        })
        if n % 25 == 0 or n == len(rows):
            print("  [%d/%d] %s docs=%d" % (n, len(rows), rid, docs_done))

    (OUT / "records.json").write_text(
        json.dumps(records, ensure_ascii=False), encoding="utf-8")

    # index.json grouped by zone -> area -> pincode
    grouped: dict = {}
    for row in sorted(roll, key=lambda x: (x["zone"] or "", x["area"] or "", x["name"] or "")):
        grouped.setdefault(row["zone"], {}).setdefault(
            "%s (%s)" % (row["area"], row["pincode"]), []).append(row)
    (OUT / "index.json").write_text(json.dumps({
        "region": "North & East Bengaluru",
        "source": "Karnataka RERA (rera.karnataka.gov.in)",
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "projects": len(roll), "documents": docs_done,
        "byZone": grouped,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\nbuilt %d projects, %d documents (missing cached html: %d)"
          % (len(roll), docs_done, missing_html))
    print("-> %s" % OUT)


if __name__ == "__main__":
    build()
