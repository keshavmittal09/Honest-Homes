"""Write the shipped form of each neighbourhood record.

`amenities.json` keeps up to 40 places per category so the data is there for
analysis later. That is ~110 KB per project — fine on disk, wrong in a git repo:
one region alone would add ~300 MB once every project has one, for places no page
ever shows.

This writes `amenities-lite.json` next to it, holding only what the UI renders:
the grades, the counts, and the nearest few places per category. The API prefers
the lite file and falls back to the full one, so running this is an optimisation
rather than a required build step.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGIONS = ROOT / "data" / "regions"

# Matches PLACES_PER_CATEGORY in api/neighbourhood.py. Kept a little higher so a
# UI change to show one or two more does not require re-running the whole trim.
KEEP = 8

# The fields the page actually reads. Everything else in a place record (osm id,
# raw tags, opening hours) is for analysis, not display.
PLACE_FIELDS = ("name", "distanceM", "distanceKm", "walkMinutes", "kind",
                "operator", "prominence", "prominenceLabel", "notable",
                "nirf", "wikidata", "mapUrl")


def trim_one(raw: dict) -> dict:
    cats = {}
    for key, c in (raw.get("categories") or {}).items():
        if not c.get("count"):
            continue
        places = []
        for p in (c.get("places") or [])[:KEEP]:
            places.append({k: p[k] for k in PLACE_FIELDS if p.get(k) is not None})
        cats[key] = {
            "label": c.get("label"), "count": c.get("count"),
            "grade": c.get("grade"), "gradeNote": c.get("gradeNote"),
            "nearestM": c.get("nearestM"), "nearestName": c.get("nearestName"),
            "places": places,
        }
    return {
        "reraId": raw.get("reraId"), "projectName": raw.get("projectName"),
        "overall": raw.get("overall"), "radiusM": raw.get("radiusM"),
        "location": raw.get("location"), "notes": raw.get("notes"),
        "builtAt": raw.get("builtAt"), "categories": cats,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="kharghar-panvel")
    a = ap.parse_args()

    root = REGIONS / a.region / "projects"
    if not root.exists():
        raise SystemExit("no such region: %s" % a.region)

    n = 0
    before = after = 0
    for f in root.glob("*/amenities/amenities.json"):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        out = f.with_name("amenities-lite.json")
        out.write_text(json.dumps(trim_one(raw), ensure_ascii=False,
                                  separators=(",", ":")), encoding="utf-8")
        before += f.stat().st_size
        after += out.stat().st_size
        n += 1

    print("trimmed %d records" % n)
    print("  full : %6.1f MB" % (before / 1e6))
    print("  lite : %6.1f MB  (%.0f%% smaller)"
          % (after / 1e6, 100 * (1 - after / before) if before else 0))


if __name__ == "__main__":
    main()
