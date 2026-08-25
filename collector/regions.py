"""Region definitions — which projects belong to a priority area, and the map
box its amenities are drawn from.

MahaRERA's index carries no locality: `location` is empty for all 44,279 rows and
`status` is the constant "registered". Pincode is the only field that reliably
places a project, so a region is defined by its pincodes and verified against the
villages reported in the Tier-2 captures we already hold.

The bounding box is deliberately larger than the pincodes: a buyer in Kharghar
cares about a hospital in Belapur, and clipping the POI fetch to the postal
boundary would hide everything just outside it.
"""

from __future__ import annotations

REGIONS: dict[str, dict] = {
    "kharghar-panvel": {
        "label": "Kharghar & Panvel",
        # Verified against captured Tier-2 addresses:
        #   410210 -> Kharghar
        #   410206 -> Panvel / Kamothe / Rohinjan / Navi Mumbai (M Corp.)
        #   410218 -> Khanda Colony, New Panvel
        #   410221 -> New Panvel / Shirdhon
        "pincodes": ["410210", "410206", "410218", "410221"],
        # south, west, north, east — the pincode footprint plus a ~6 km margin so
        # amenities just outside the postal boundary are still found.
        "bbox": (18.9000, 72.9400, 19.1300, 73.2200),
        "centre": (19.0330, 73.0297),          # Kharghar node, for sanity checks
    },
}

DEFAULT_REGION = "kharghar-panvel"


def region(name: str = DEFAULT_REGION) -> dict:
    try:
        return REGIONS[name]
    except KeyError:
        raise SystemExit(
            "unknown region %r — known: %s" % (name, ", ".join(sorted(REGIONS)))
        )


def targets(index: dict, name: str = DEFAULT_REGION) -> list[str]:
    """RERA ids in this region, in index order.

    `index` is the id -> row mapping the collector already builds, so this adds
    no new source of truth.
    """
    want = set(region(name)["pincodes"])
    return [rid for rid, row in index.items() if str(row.get("pincode") or "") in want]


def in_region(row: dict, name: str = DEFAULT_REGION) -> bool:
    return str(row.get("pincode") or "") in set(region(name)["pincodes"])
