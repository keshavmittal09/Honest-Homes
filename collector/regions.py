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

import re

REGIONS: dict[str, dict] = {
    "kharghar-panvel": {
        "label": "Kharghar & Panvel",
        # Verified against captured Tier-2 addresses:
        #   410210 -> Kharghar
        #   410206 -> Panvel / Kamothe / Rohinjan / Navi Mumbai (M Corp.)
        #   410218 -> Khanda Colony, New Panvel
        #   410221 -> New Panvel / Shirdhon
        "pincodes": ["410210", "410206", "410218", "410221"],
        # The place names this region covers. Used to pull in projects filed
        # under a neighbouring pincode -- see pincodes_for(). Kept lowercase and
        # matched as substrings, so "kharghar" also catches "Kharghar Sector 20".
        "localities": ["kharghar", "panvel", "kamothe", "khanda colony",
                       "new panvel", "rohinjan", "shirdhon"],
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


def _localities(name: str) -> set[str]:
    return {v.lower() for v in region(name).get("localities", [])}


def stragglers(index: dict, detail: dict | None, name: str = DEFAULT_REGION) -> set[str]:
    """Projects in this region that its pincodes do not contain.

    A region is a place, not a postal code, and the two do not line up:
    "Regents Park Kharghar" is filed under 410208 (Taloja). Those projects have
    to be pulled in individually.

    Individually is the important word. An earlier version widened the region to
    every *pincode* where some captured project reported one of its localities,
    which dragged in 1,443 Kalyan-Dombivli projects on the strength of four
    filings that name a Kharghar address — a region defined by a place name has
    to stay that precise, or "Kharghar" quietly comes to mean half of MMR.
    """
    want = _localities(name)
    if not want:
        return set()
    out: set[str] = set()

    # The project's own filed address is the strongest evidence.
    for rid, rec in (detail or {}).items():
        a = rec.get("address") or {}
        for field in (a.get("village"), a.get("locality")):
            if str(field or "").strip().lower() in want:
                out.add(rid)
                break

    # Failing that, a locality in the project's own name. Matched on word
    # boundaries: "panvel" must not also catch a project called "Panvelkar".
    for rid, row in index.items():
        nm = (row.get("project_name") or "").lower()
        if any(re.search(r"\b%s\b" % re.escape(w), nm) for w in want):
            out.add(rid)
    return out


def targets(index: dict, name: str = DEFAULT_REGION,
            detail: dict | None = None) -> list[str]:
    """RERA ids in this region, in index order.

    `index` is the id -> row mapping the collector already builds, so this adds
    no new source of truth. Pass `detail` (the parsed snapshot) to also pick up
    projects filed under a neighbouring pincode.
    """
    want = set(region(name)["pincodes"])
    extra = stragglers(index, detail, name)
    return [rid for rid, row in index.items()
            if str(row.get("pincode") or "") in want or rid in extra]


def in_region(row: dict, name: str = DEFAULT_REGION) -> bool:
    return str(row.get("pincode") or "") in set(region(name)["pincodes"])
