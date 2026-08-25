"""Neighbourhood directory — what is actually around a project, and how far.

The things a buyer checks before paying: schools, hospitals, malls, markets,
stations, offices, parks, restaurants, banks, gyms. For every project in a region
this records each one within a radius, its real distance, and a grade.

Design notes that matter:

* **One fetch per region, not one per project.** Projects a kilometre apart share
  the same surroundings. The region's POIs are fetched once from Overpass into a
  cache; per-project distances are then computed offline. For Kharghar+Panvel
  that is ~10 API calls instead of ~2,700 against a free service.
* **Distance is straight-line and says so.** Road distance needs a routing
  engine; calling a 1.4 km crow-flies hop "1.4 km away" when the road is 3 km
  would be the kind of quiet inaccuracy this project exists to avoid.
* **Grades are computed from what OSM actually knows.** OpenStreetMap has no
  star ratings, so nothing here claims a school is *good*. The per-place grade
  reads establishment signals (brand, operator, website, capacity, emergency
  department); the per-category grade reads distance and count. Both are labelled
  as what they are. Published assessments that ARE quality judgements — NIRF
  rankings, Wikidata notability — come from `enrich_amenities.py` and are merged
  in here as their own fields, never blended into the OSM-derived grade.
* **Images are stitched map tiles**, street and satellite, cached by tile so
  neighbouring projects reuse them instead of re-downloading.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from collector.regions import DEFAULT_REGION, region

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "HonestHomes/1.0 (+https://honesthomes.onrender.com; propelloai.mmr@gmail.com)"

# The main instance throttles hard at peak. These are the public mirrors that run
# the same API and data; rotating across them turns a failed run into a slow one.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
TILE_STREET = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_SAT = ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery"
            "/MapServer/tile/{z}/{y}/{x}")

DEFAULT_RADIUS_M = 5000

# Each category is one Overpass filter set plus the distance, in metres, at which
# it stops being a selling point. The cutoffs are walk/drive realities, not round
# numbers: a school is a daily walk, a mall is a weekend drive.
CATEGORIES: dict[str, dict] = {
    "schools": {
        "label": "Schools",
        "filters": ['["amenity"~"^(school|kindergarten)$"]'],
        "near_m": 1500, "good_m": 3000,
    },
    "colleges": {
        "label": "Colleges & universities",
        "filters": ['["amenity"~"^(college|university)$"]'],
        "near_m": 3000, "good_m": 6000,
    },
    "hospitals": {
        "label": "Hospitals & clinics",
        "filters": ['["amenity"~"^(hospital|clinic|doctors)$"]'],
        "near_m": 2000, "good_m": 4000,
    },
    "pharmacies": {
        "label": "Pharmacies",
        "filters": ['["amenity"="pharmacy"]'],
        "near_m": 800, "good_m": 1500,
    },
    "malls": {
        "label": "Malls & department stores",
        "filters": ['["shop"~"^(mall|department_store)$"]', '["shop"="supermarket"]'],
        "near_m": 2500, "good_m": 5000,
    },
    "markets": {
        "label": "Markets & daily needs",
        "filters": ['["amenity"="marketplace"]',
                    '["shop"~"^(convenience|greengrocer|butcher|bakery|general)$"]'],
        "near_m": 800, "good_m": 1500,
    },
    "transport": {
        "label": "Stations & transport",
        "filters": ['["railway"~"^(station|halt)$"]', '["station"="subway"]',
                    '["amenity"="bus_station"]', '["highway"="bus_stop"]'],
        "near_m": 1200, "good_m": 3000,
    },
    "offices": {
        "label": "Offices & workplaces",
        # `office=*` is the tag for an actual business. `building=office` and
        # `landuse=commercial` were tried and dropped: over a 25x30 km box they
        # return enormous geometry, time the query out, and answer a question
        # nobody asked -- a buyer wants to know where the employers are, not
        # which structures are office-shaped.
        "filters": ['["office"]', '["amenity"="coworking_space"]'],
        "near_m": 3000, "good_m": 6000,
    },
    "parks": {
        "label": "Parks & open space",
        "filters": ['["leisure"~"^(park|garden|playground|nature_reserve)$"]'],
        "near_m": 1000, "good_m": 2500,
    },
    "dining": {
        "label": "Restaurants & cafes",
        "filters": ['["amenity"~"^(restaurant|cafe|fast_food|food_court)$"]'],
        "near_m": 1200, "good_m": 2500,
    },
    "banks": {
        "label": "Banks & ATMs",
        "filters": ['["amenity"~"^(bank|atm)$"]'],
        "near_m": 1000, "good_m": 2000,
    },
    "fitness": {
        "label": "Gyms & sports",
        "filters": ['["leisure"~"^(fitness_centre|sports_centre|swimming_pool|stadium)$"]',
                    '["amenity"="gym"]'],
        "near_m": 1500, "good_m": 3000,
    },
    "entertainment": {
        "label": "Cinemas & leisure",
        "filters": ['["amenity"~"^(cinema|theatre|community_centre)$"]'],
        "near_m": 2500, "good_m": 5000,
    },
    "worship": {
        "label": "Places of worship",
        "filters": ['["amenity"="place_of_worship"]'],
        "near_m": 1200, "good_m": 2500,
    },
}


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def haversine_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Great-circle metres. Equirectangular is fine at this scale but haversine
    costs nothing here and does not drift at the region's edges."""
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def walk_minutes(m: float) -> int:
    """At 4.8 km/h. Only quoted under ~2 km, where walking is plausible."""
    return max(1, round(m / 80.0))


# --------------------------------------------------------------------------
# Overpass
# --------------------------------------------------------------------------

def _overpass(query: str, rounds: int = 3) -> dict | None:
    """Ask each mirror in turn, then wait and go round again.

    Returns None when every mirror has refused -- the caller records the category
    as unfetched and carries on. Raising here would throw away the categories
    that already succeeded, which is exactly what happened on the first run.
    """
    for rnd in range(rounds):
        for url in OVERPASS_ENDPOINTS:
            try:
                req = urllib.request.Request(url, data=query.encode("utf-8"),
                                             headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.loads(r.read().decode("utf-8", "replace"))
            except Exception as e:
                code = getattr(e, "code", "")
                host = url.split("/")[2]
                print("    %s %s %s" % (host, code, str(e)[:44]), flush=True)
                time.sleep(4)
        wait = 30 * (rnd + 1)
        if rnd < rounds - 1:
            print("    all mirrors busy — waiting %ds" % wait, flush=True)
            time.sleep(wait)
    return None


def fetch_region_pois(reg: dict, out: Path, refresh: bool = False) -> dict:
    """Every POI in the region box, one category at a time.

    Split by category rather than one giant query: a single request for fourteen
    filter sets over a 25x30 km box reliably times out, and a partial failure
    would otherwise lose the whole fetch.
    """
    out.parent.mkdir(parents=True, exist_ok=True)

    # Resume rather than restart. Each category is written as it lands, so a run
    # that dies at category 8 of 14 keeps the first seven and picks up at the
    # eighth. The first version wrote only at the end and lost everything.
    done_cats: dict[str, list] = {}
    if out.exists():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            if not refresh:
                done_cats = prev.get("categories", {}) or {}
        except ValueError:
            pass
    if done_cats and all(k in done_cats for k in CATEGORIES) and not refresh:
        print("POI cache complete: %d places (use --refresh-pois to re-fetch)"
              % sum(len(v) for v in done_cats.values()))
        return {"categories": done_cats}
    if done_cats:
        print("Resuming POI fetch — %d of %d categories already cached"
              % (len(done_cats), len(CATEGORIES)), flush=True)

    s, w, n, e = reg["bbox"]
    bbox = "%f,%f,%f,%f" % (s, w, n, e)
    result: dict[str, list] = dict(done_cats)
    failed: list[str] = []

    def _save():
        out.write_text(json.dumps({
            "region": reg["label"], "bbox": reg["bbox"],
            "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "OpenStreetMap via Overpass API (ODbL)",
            "incomplete": failed or None,
            "categories": result,
        }, ensure_ascii=False), encoding="utf-8")

    for key, cfg in CATEGORIES.items():
        if key in result:
            continue
        parts = []
        for f in cfg["filters"]:
            # Nodes and ways only. Relations are multipolygon wrappers that add
            # little at POI level and cost a great deal to assemble over a box
            # this size -- including them was what stalled the first run.
            for kind in ("node", "way"):
                parts.append("%s%s(%s);" % (kind, f, bbox))
        q = "[out:json][timeout:120];(%s);out center tags;" % "".join(parts)
        print("  %-14s fetching..." % key, flush=True)
        data = _overpass(q)
        if data is None:
            # Recorded, not guessed at. A missing category shows up in the output
            # as `incomplete` rather than silently reading as "nothing nearby".
            failed.append(key)
            print("  %-14s UNAVAILABLE — every mirror refused; re-run to retry"
                  % key, flush=True)
            continue
        places = []
        for el in data.get("elements", []):
            tags = el.get("tags") or {}
            name = tags.get("name") or tags.get("brand") or tags.get("operator")
            if not name:
                continue                      # unnamed nodes are noise in a directory
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            places.append({
                "osm": "%s/%s" % (el.get("type"), el.get("id")),
                "name": name, "lat": lat, "lon": lon, "tags": tags,
            })
        # One name can appear as both a node and a building way.
        seen, uniq = set(), []
        for p in sorted(places, key=lambda p: -len(p["tags"])):
            k = (p["name"].strip().lower(), round(p["lat"], 4), round(p["lon"], 4))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(p)
        result[key] = uniq
        _save()                                # survive a crash in the next category
        print("  %-14s %5d places" % (key, len(uniq)), flush=True)
        time.sleep(3)                          # courtesy gap on a shared service

    _save()
    total = sum(len(v) for v in result.values())
    print("POIs cached: %d places across %d categories -> %s"
          % (total, len(result), out))
    if failed:
        print("UNFETCHED (re-run to fill): %s" % ", ".join(failed))
    return {"categories": result}


# --------------------------------------------------------------------------
# grading
# --------------------------------------------------------------------------

def place_prominence(tags: dict) -> tuple[int, str]:
    """How well-established a place looks *in the OSM record*.

    This is not a quality rating and must never be presented as one. It counts
    the signals a mapper adds for a real, findable business: a brand, an
    operator, a website, a phone, opening hours, a capacity, an A&E department.
    A famous hospital with a thin OSM entry will score low, and that is an honest
    statement about the data rather than a claim about the hospital.
    """
    score = 0
    for k in ("brand", "operator", "website", "contact:website", "phone",
              "contact:phone", "opening_hours", "wikidata", "wikipedia"):
        if tags.get(k):
            score += 1
    if tags.get("emergency") == "yes":
        score += 2
    for k in ("capacity", "beds", "rooms"):
        if tags.get(k):
            score += 1
    if tags.get("isced:level") or tags.get("school:type"):
        score += 1
    if score >= 5:
        return score, "Well documented"
    if score >= 3:
        return score, "Established listing"
    if score >= 1:
        return score, "Basic listing"
    return score, "Name only"


def category_grade(nearest_m: float | None, count: int, cfg: dict) -> tuple[str, str]:
    """A -> E for one category at one project, from distance and choice.

    Both inputs are facts. The grade is a summary of them, not an opinion about
    the places themselves.
    """
    if nearest_m is None or not count:
        return "E", "Nothing on the map within range"
    near, good = cfg["near_m"], cfg["good_m"]
    if nearest_m <= near and count >= 5:
        return "A", "Several within easy reach"
    if nearest_m <= near:
        return "B", "Close by, limited choice"
    if nearest_m <= good and count >= 5:
        return "B", "Good choice, a short drive"
    if nearest_m <= good:
        return "C", "Reachable, limited choice"
    if count >= 3:
        return "D", "Some options, all far"
    return "D", "Very limited"


GRADE_POINTS = {"A": 4, "B": 3, "C": 2, "D": 1, "E": 0}
# Daily-need categories weigh more than nice-to-haves: a buyer notices a missing
# chemist every week and a missing cinema twice a year.
CATEGORY_WEIGHT = {
    "schools": 3, "hospitals": 3, "markets": 3, "transport": 3,
    "pharmacies": 2, "malls": 2, "parks": 2, "dining": 2, "banks": 2,
    "offices": 2, "colleges": 1, "fitness": 1, "entertainment": 1, "worship": 1,
}


def overall_grade(cats: dict) -> dict:
    # Not one place in any of fourteen categories within 5 km is not a finding
    # about the neighbourhood -- no inhabited part of MMR looks like that. It
    # means the point we searched from is wrong, and the honest output is "we do
    # not know" rather than "E, poorly served". Publishing the latter told buyers
    # a Kharghar tower had nothing around it because MahaRERA had geo-tagged it
    # 450 km away.
    found = sum(c.get("count") or 0 for c in cats.values())
    if not found:
        return {"score": None, "grade": None, "label": "Location not confirmed",
                "known": False,
                "basis": "No usable coordinates for this project, so its "
                         "surroundings have not been assessed"}

    got = wt = 0
    for key, c in cats.items():
        w = CATEGORY_WEIGHT.get(key, 1)
        got += GRADE_POINTS.get(c["grade"], 0) * w
        wt += 4 * w
    pct = round(100.0 * got / wt, 1) if wt else 0.0
    letter = ("A" if pct >= 80 else "B" if pct >= 65 else
              "C" if pct >= 50 else "D" if pct >= 35 else "E")
    words = {"A": "Very well served", "B": "Well served", "C": "Adequate",
             "D": "Thin", "E": "Poorly served"}
    return {"score": pct, "grade": letter, "label": words[letter], "known": True,
            "basis": "Weighted across %d categories; daily needs count most" % len(cats)}


# --------------------------------------------------------------------------
# map tiles
# --------------------------------------------------------------------------

def _deg2tile(lat: float, lon: float, z: int) -> tuple[float, float]:
    la = math.radians(lat)
    n = 2.0 ** z
    return ((lon + 180.0) / 360.0 * n,
            (1.0 - math.asinh(math.tan(la)) / math.pi) / 2.0 * n)


def _tile(url: str, z: int, x: int, y: int, cache: Path) -> bytes | None:
    """Tiles are cached on disk: neighbouring projects share most of them, and
    the tile servers' usage policies expect exactly that."""
    f = cache / str(z) / str(x) / ("%d.png" % y)
    if f.exists():
        return f.read_bytes()
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url.format(z=z, x=x, y=y), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            b = r.read()
        f.write_bytes(b)
        time.sleep(0.12)
        return b
    except Exception:
        return None


def map_image(lat: float, lon: float, out: Path, cache: Path, *,
              satellite: bool = False, z: int = 15, size: int = 3) -> bool:
    """A size x size tile mosaic centred on the project, with a marker.

    Written with Pillow, which the project already depends on for share cards.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    tx, ty = _deg2tile(lat, lon, z)
    cx, cy = int(tx), int(ty)
    half = size // 2
    canvas = Image.new("RGB", (256 * size, 256 * size), (232, 230, 226))
    got = 0
    for dx in range(-half, half + 1):
        for dy in range(-half, half + 1):
            raw = _tile(TILE_SAT if satellite else TILE_STREET, z, cx + dx, cy + dy,
                        cache / ("sat" if satellite else "street"))
            if not raw:
                continue
            try:
                from io import BytesIO
                t = Image.open(BytesIO(raw)).convert("RGB")
            except Exception:
                continue
            canvas.paste(t, (256 * (dx + half), 256 * (dy + half)))
            got += 1
    if not got:
        return False
    # marker at the project's true offset inside its own tile
    px = int(256 * (half + (tx - cx)))
    py = int(256 * (half + (ty - cy)))
    d = ImageDraw.Draw(canvas)
    d.ellipse([px - 13, py - 13, px + 13, py + 13], fill=(220, 60, 50), outline=(255, 255, 255), width=4)
    d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 255, 255))
    d.rectangle([0, canvas.height - 20, canvas.width, canvas.height],
                fill=(255, 255, 255))
    d.text((7, canvas.height - 15),
           "(c) Esri, Maxar" if satellite else "(c) OpenStreetMap contributors",
           fill=(70, 70, 70))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="JPEG", quality=82, optimize=True)
    return True


# --------------------------------------------------------------------------
# geocoding
# --------------------------------------------------------------------------

def geocode(name: str, pincode: str, cache: dict) -> tuple[float, float] | None:
    """Fall back for projects with no Tier-2 capture yet.

    Nominatim asks for at most one request a second and a real user agent; both
    are honoured. Results are cached so a re-run costs nothing.
    """
    key = "%s|%s" % (name.strip().lower(), pincode)
    if key in cache:
        v = cache[key]
        return (v[0], v[1]) if v else None
    q = ", ".join(x for x in (name, pincode, "Maharashtra, India") if x)
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1, "countrycodes": "in"})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            js = json.loads(r.read().decode("utf-8", "replace"))
        time.sleep(1.1)
        if js:
            lat, lon = float(js[0]["lat"]), float(js[0]["lon"])
            cache[key] = [lat, lon]
            return lat, lon
    except Exception:
        pass
    cache[key] = None
    return None


# --------------------------------------------------------------------------
# per-project directory
# --------------------------------------------------------------------------

def build_for_project(rid: str, row: dict, lat: float, lon: float, pois: dict,
                      radius: int, quality: dict | None = None) -> dict:
    quality = quality or {}
    cats: dict[str, dict] = {}
    for key, cfg in CATEGORIES.items():
        found = []
        for p in pois["categories"].get(key, []):
            d = haversine_m(lat, lon, p["lat"], p["lon"])
            if d > radius:
                continue
            score, label = place_prominence(p["tags"])
            t = p["tags"]
            q = quality.get(p["osm"]) or {}
            found.append({
                "name": p["name"],
                # Published assessments, where one exists. These are facts from a
                # named authority, unlike `prominence` which describes our data.
                "nirf": q.get("nirf"),
                "wikidata": q.get("wikidata"),
                "notable": bool(q.get("wikidata") or q.get("nirf")),
                "distanceM": round(d),
                "distanceKm": round(d / 1000.0, 2),
                "walkMinutes": walk_minutes(d) if d <= 2000 else None,
                "prominence": score, "prominenceLabel": label,
                "kind": (t.get("amenity") or t.get("shop") or t.get("leisure")
                         or t.get("railway") or t.get("office") or t.get("landuse") or ""),
                "operator": t.get("operator") or t.get("brand") or None,
                "website": t.get("website") or t.get("contact:website") or None,
                "phone": t.get("phone") or t.get("contact:phone") or None,
                "openingHours": t.get("opening_hours") or None,
                "lat": p["lat"], "lon": p["lon"], "osm": p["osm"],
                "mapUrl": "https://www.openstreetmap.org/?mlat=%s&mlon=%s#map=18/%s/%s"
                          % (p["lat"], p["lon"], p["lat"], p["lon"]),
            })
        found.sort(key=lambda x: (x["distanceM"], -x["prominence"]))
        nearest = found[0]["distanceM"] if found else None
        grade, note = category_grade(nearest, len(found), cfg)
        cats[key] = {
            "label": cfg["label"], "count": len(found),
            "nearestM": nearest,
            "nearestName": found[0]["name"] if found else None,
            "grade": grade, "gradeNote": note,
            "places": found[:40],       # the long tail is noise in a directory
        }
    return {
        "reraId": rid,
        "projectName": row.get("project_name"),
        "promoter": row.get("promoter_name"),
        "pincode": row.get("pincode"),
        "district": row.get("district"),
        "location": {"lat": lat, "lon": lon, "source": row.get("_geo_source")},
        "radiusM": radius,
        "overall": overall_grade(cats),
        "categories": cats,
        "notes": {
            "distance": "Straight-line distance. Road distance will be longer.",
            "quality": ("OpenStreetMap has no user ratings. 'Prominence' counts how "
                        "completely a place is recorded (brand, operator, contact, "
                        "hours, emergency dept) and is not a judgement of quality. "
                        "Where a place carries a 'nirf' block that IS a published "
                        "government ranking; 'wikidata' means a notable institution "
                        "with its own encyclopaedic record."),
            "source": ("OpenStreetMap contributors (ODbL); Wikidata (CC0); "
                       "NIRF, Ministry of Education. Maps (c) OSM / Esri."),
        },
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default=DEFAULT_REGION)
    ap.add_argument("--radius", type=int, default=DEFAULT_RADIUS_M)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh-pois", action="store_true")
    ap.add_argument("--no-images", action="store_true",
                    help="skip map tiles (much faster for a first pass)")
    ap.add_argument("--geocode", action="store_true",
                    help="geocode projects with no Tier-2 coordinates (slow: 1 req/sec)")
    args = ap.parse_args()

    reg = region(args.region)
    root = DATA / "regions" / args.region
    pois = fetch_region_pois(reg, root / "amenities" / "pois.json", args.refresh_pois)

    index = {}
    idx = DATA / "snapshots" / "index" / "2026-06-02" / "rows.jsonl"
    for line in idx.open(encoding="utf-8"):
        r = json.loads(line)
        index[r["rera_id"]] = r

    detail = {}
    parsed = sorted((DATA / "snapshots" / "detail_parsed").glob("*/records.json"))
    if parsed:
        detail = json.loads(parsed[-1].read_text(encoding="utf-8"))

    want = set(reg["pincodes"])
    targets = [(rid, r) for rid, r in index.items() if str(r.get("pincode") or "") in want]
    if args.limit:
        targets = targets[:args.limit]
    print("\n%s: %d projects in scope" % (reg["label"], len(targets)))

    gc_path = root / "amenities" / "geocode-cache.json"
    gcache = json.loads(gc_path.read_text(encoding="utf-8")) if gc_path.exists() else {}

    # Published quality signals, if enrich_amenities has been run. Absent is fine
    # -- the directory is still useful without them, just less informative.
    q_path = root / "amenities" / "quality.json"
    quality = {}
    if q_path.exists():
        quality = json.loads(q_path.read_text(encoding="utf-8")).get("places", {})
        print("quality signals: %d places carry a published assessment" % len(quality))
    else:
        print("quality signals: none yet (run collector.enrich_amenities)")

    built = skipped = off_region = cleared = 0
    for i, (rid, row) in enumerate(targets, 1):
        lat = lon = None
        det = detail.get(rid) or {}
        geo = det.get("geo") or {}
        if geo.get("lat") and geo.get("lng"):
            # MahaRERA's geo-tagging is not always the project's location. Some
            # filings carry a placeholder shared by many projects, and at least
            # one Kharghar project is tagged 400 km away near Nagpur. Both pass a
            # Maharashtra-wide check, so validate against the region the project's
            # pincode actually places it in -- a directory built on a wrong point
            # would describe someone else's neighbourhood with total confidence.
            s, w, n_, e = reg["bbox"]
            if s <= geo["lat"] <= n_ and w <= geo["lng"] <= e:
                lat, lon, row["_geo_source"] = geo["lat"], geo["lng"], "MahaRERA Tier-2"
            else:
                off_region += 1
                if args.geocode:
                    hit = geocode(row.get("project_name") or "", row.get("pincode") or "", gcache)
                    if hit:
                        lat, lon = hit
                        row["_geo_source"] = "Nominatim (MahaRERA coordinate was out of region)"
        elif args.geocode:
            hit = geocode(row.get("project_name") or "", row.get("pincode") or "", gcache)
            if hit:
                lat, lon = hit
                row["_geo_source"] = "Nominatim (approximate)"
        if lat is None:
            skipped += 1
            # A skip must not leave an older record standing. These projects
            # previously had coordinates we now reject, and the stale file said
            # "E — Poorly served": a confident, wrong statement about someone's
            # neighbourhood, left behind by a rebuild that simply passed over
            # them. Overwrite with the honest answer instead of walking away.
            pdir = root / "projects" / rid / "amenities"
            if (pdir / "amenities.json").exists() or (pdir / "amenities-lite.json").exists():
                unknown = {
                    "reraId": rid,
                    "projectName": row.get("project_name"),
                    "location": {"lat": None, "lon": None, "source": None},
                    "radiusM": args.radius,
                    "overall": {"score": None, "grade": None, "known": False,
                                "label": "Location not confirmed",
                                "basis": "MahaRERA has not published usable "
                                         "coordinates for this project"},
                    "categories": {},
                    "notes": {"location": "The filed coordinates are missing or "
                                          "fall outside this region, so the "
                                          "surroundings have not been assessed."},
                    "builtAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                for fn in ("amenities.json", "amenities-lite.json"):
                    (pdir / fn).write_text(json.dumps(unknown, ensure_ascii=False),
                                           encoding="utf-8")
                # Map images drawn from a rejected point are wrong pictures.
                for img in pdir.glob("map-*.jpg"):
                    img.unlink(missing_ok=True)
                cleared += 1
            continue

        pdir = root / "projects" / rid
        rec = build_for_project(rid, row, lat, lon, pois, args.radius, quality)
        (pdir / "amenities").mkdir(parents=True, exist_ok=True)
        (pdir / "amenities" / "amenities.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

        if not args.no_images:
            cache = DATA / "regions" / "_tilecache"
            map_image(lat, lon, pdir / "amenities" / "map-street.jpg", cache, satellite=False)
            map_image(lat, lon, pdir / "amenities" / "map-satellite.jpg", cache, satellite=True)

        built += 1
        if i % 25 == 0 or i == len(targets):
            print("  [%d/%d] built=%d skipped(no coords)=%d  last=%s %s"
                  % (i, len(targets), built, skipped, rid, rec["overall"]["grade"]))
        if built % 40 == 0:
            gc_path.write_text(json.dumps(gcache), encoding="utf-8")

    gc_path.parent.mkdir(parents=True, exist_ok=True)
    gc_path.write_text(json.dumps(gcache), encoding="utf-8")
    print("\nbuilt %d directories, %d skipped for want of coordinates" % (built, skipped))
    print("-> %s" % (root / "projects"))


if __name__ == "__main__":
    main()
