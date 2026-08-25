"""Serving the neighbourhood directories the collector builds.

Two jobs, both shaped by size. A full `amenities.json` averages 110 KB and the
region will hold thousands of them, so nothing here loads eagerly: files are read
on demand, trimmed to what a page actually renders, and cached by id.

The trim is the important part. A project can have 200+ places within 5 km, and
sending all of them would be both slow and useless -- nobody reads the 38th
nearest ATM. Each category returns its nearest few, with the full count kept so
the page can say "and 34 more" honestly rather than implying that is all there is.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("hh.neighbourhood")

ROOT = Path(__file__).resolve().parent.parent
REGIONS = ROOT / "data" / "regions"

PLACES_PER_CATEGORY = 6      # what the UI shows before "show all"


def _dir_for(rera_id: str) -> Path | None:
    """The project's folder in whichever region holds it."""
    if not rera_id or not REGIONS.exists():
        return None
    for region in REGIONS.iterdir():
        if not region.is_dir() or region.name.startswith("_"):
            continue
        p = region / "projects" / rera_id
        if p.is_dir():
            return p
    return None


@lru_cache(maxsize=512)
def amenities(rera_id: str) -> dict | None:
    """Trimmed neighbourhood record, or None when we have not built one."""
    d = _dir_for(rera_id)
    if d is None:
        return None
    # `amenities-lite.json` is the shipped form: the same record with the long
    # tail of places already dropped. The full file holds up to 40 places per
    # category (~110 KB) which is right for analysis and far too heavy to carry
    # in the repo once every project in a region has one. Prefer lite, fall back
    # to the full file so a freshly built region works before it is trimmed.
    lite = d / "amenities" / "amenities-lite.json"
    f = lite if lite.exists() else d / "amenities" / "amenities.json"
    if not f.exists():
        return None
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        log.warning("amenities unreadable for %s: %s", rera_id, e)
        return None

    cats = []
    for key, c in (raw.get("categories") or {}).items():
        if not c.get("count"):
            continue                      # an empty category is noise on a page
        cats.append({
            "key": key,
            "label": c.get("label"),
            "count": c.get("count"),
            "grade": c.get("grade"),
            "gradeNote": c.get("gradeNote"),
            "nearestM": c.get("nearestM"),
            "nearestName": c.get("nearestName"),
            "places": (c.get("places") or [])[:PLACES_PER_CATEGORY],
            "more": max(0, (c.get("count") or 0) - PLACES_PER_CATEGORY),
        })
    # Best-served first: a page that opens on "Schools A, 6 nearby" reads better
    # than one that opens on whatever happened to be first alphabetically.
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
    cats.sort(key=lambda c: (order.get(c["grade"], 9), c.get("nearestM") or 9e9))

    return {
        "reraId": raw.get("reraId"),
        "overall": raw.get("overall"),
        "radiusM": raw.get("radiusM"),
        "location": raw.get("location"),
        "categories": cats,
        "totalPlaces": sum(c["count"] for c in cats),
        "notes": raw.get("notes"),
        "maps": {
            "street": bool((d / "amenities" / "map-street.jpg").exists()),
            "satellite": bool((d / "amenities" / "map-satellite.jpg").exists()),
        },
        "builtAt": raw.get("builtAt"),
    }


def map_image(rera_id: str, kind: str) -> Path | None:
    """Path to a stitched map image, or None. `kind` is street|satellite."""
    if kind not in ("street", "satellite"):
        return None
    d = _dir_for(rera_id)
    if d is None:
        return None
    f = d / "amenities" / ("map-%s.jpg" % kind)
    return f if f.exists() else None


def category_places(rera_id: str, key: str) -> list:
    """Every place in one category, for the "show all" expansion. Read straight
    from the file rather than the trimmed cache."""
    d = _dir_for(rera_id)
    if d is None:
        return []
    f = d / "amenities" / "amenities.json"
    if not f.exists():
        return []
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return ((raw.get("categories") or {}).get(key) or {}).get("places") or []
