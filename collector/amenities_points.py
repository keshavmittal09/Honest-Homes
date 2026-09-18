"""Build neighbourhood directories for a specific list of projects by their own
coordinates -- for projects scattered outside any single region box.

The region builder (fetch_amenities) fetches one POI cache for a bounding box,
which is right for a dense area like Kharghar. A handful of projects spread
across Airoli, Panvel, Kharghar and Thane (e.g. one builder's portfolio) do not
share a box, so this fetches POIs around each project's point instead -- one
Overpass query per project -- and reuses the exact grading, map and trim logic
so the output is identical in shape to the region builder's.

Output lands under data/regions/<region>/projects/<RERA-ID>/amenities/, which is
where the neighbourhood API already scans, so these projects light up on the
site with no further wiring.

    python -m collector.amenities_points --region gami-group --ids P51700079334,P51700013200
"""

from __future__ import annotations

import argparse
import glob
import json
import time
from pathlib import Path

from .fetch_amenities import (
    CATEGORIES, _overpass, build_for_project, map_image, DATA,
)
from .trim_amenities import trim_one

REGIONS = DATA / "regions"


def _pois_around(lat: float, lon: float, radius_m: int) -> dict:
    """Every POI within radius of a point, one Overpass query per category.

    Same category filters as the region builder; `around:` centres on the point
    so a scattered project gets its own true surroundings.
    """
    cats: dict[str, list] = {}
    for key, cfg in CATEGORIES.items():
        parts = []
        for f in cfg["filters"]:
            for kind in ("node", "way"):
                parts.append("%s%s(around:%d,%f,%f);" % (kind, f, radius_m, lat, lon))
        q = "[out:json][timeout:120];(%s);out center tags;" % "".join(parts)
        data = _overpass(q)
        places = []
        if data:
            seen = set()
            for el in data.get("elements", []):
                tags = el.get("tags") or {}
                name = tags.get("name") or tags.get("brand") or tags.get("operator")
                if not name:
                    continue
                plat = el.get("lat") or (el.get("center") or {}).get("lat")
                plon = el.get("lon") or (el.get("center") or {}).get("lon")
                if plat is None or plon is None:
                    continue
                k = (name.strip().lower(), round(plat, 4), round(plon, 4))
                if k in seen:
                    continue
                seen.add(k)
                places.append({"osm": "%s/%s" % (el.get("type"), el.get("id")),
                               "name": name, "lat": plat, "lon": plon, "tags": tags})
        cats[key] = places
        print("    %-14s %5d" % (key, len(places)), flush=True)
        time.sleep(2)
    return {"categories": cats}


def build(region: str, rera_ids: list[str], radius_m: int = 5000) -> None:
    snap = sorted(glob.glob(str(DATA / "snapshots" / "detail_parsed" / "*" / "records.json")))
    if not snap:
        raise SystemExit("no parsed snapshot")
    records = json.loads(Path(snap[-1]).read_text(encoding="utf-8"))

    proj_root = REGIONS / region / "projects"
    proj_root.mkdir(parents=True, exist_ok=True)
    tilecache = REGIONS / "_tilecache"
    built = skipped = 0

    for rid in rera_ids:
        rec = records.get(rid)
        geo = (rec or {}).get("geo") or {}
        lat, lon = geo.get("lat"), geo.get("lng")
        if not (rec and lat and lon):
            print("  %s -> no coordinates, skipped" % rid)
            skipped += 1
            continue
        print("  %s @ %.4f,%.4f" % (rid, lat, lon), flush=True)
        pois = _pois_around(lat, lon, radius_m)
        row = {"project_name": rec.get("project_name"),
               "promoter_name": rec.get("promoter_name"),
               "pincode": (rec.get("address") or {}).get("pincode"),
               "district": (rec.get("address") or {}).get("district"),
               "_geo_source": "MahaRERA Tier-2"}
        full = build_for_project(rid, row, lat, lon, pois, radius_m, {})

        adir = proj_root / rid / "amenities"
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "amenities.json").write_text(
            json.dumps(full, ensure_ascii=False, indent=1), encoding="utf-8")
        (adir / "amenities-lite.json").write_text(
            json.dumps(trim_one(full), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        map_image(lat, lon, adir / "map-street.jpg", tilecache, satellite=False)
        map_image(lat, lon, adir / "map-satellite.jpg", tilecache, satellite=True)
        built += 1
        print("     overall: %s" % (full.get("overall") or {}).get("grade"), flush=True)

    print("\nbuilt amenities for %d project(s), skipped %d -> %s" % (built, skipped, proj_root))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", required=True, help="region folder name, e.g. gami-group")
    ap.add_argument("--ids", required=True, help="comma-separated RERA ids")
    ap.add_argument("--radius", type=int, default=5000)
    a = ap.parse_args()
    build(a.region, [x.strip() for x in a.ids.split(",") if x.strip()], a.radius)
