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
        # Ordered smallest-first on purpose. The collector works this list in
        # order, so a token spent here finishes whole areas rather than denting
        # several: Ulwe, Kalamboli, New Panvel, Khanda and Taloja together close
        # out in roughly the rounds it takes to make a visible dent in Panvel,
        # which alone is 2,417 projects. Kharghar (410210) is already complete
        # and stays listed so re-runs still recognise it as part of the region.
        "pincodes": ["410222",   # Ulwe / Dronagiri        28
                     "410218",   # Khanda Colony           72
                     "410221",   # New Panvel              76
                     "410209",   # Kalamboli               77
                     "410210",   # Kharghar               156  (done)
                     "410208",   # Taloja                 299
                     "410206"],  # Panvel                2417
        # The place names this region covers. Used to pull in projects filed
        # under a neighbouring pincode -- see pincodes_for(). Kept lowercase and
        # matched as substrings, so "kharghar" also catches "Kharghar Sector 20".
        "localities": ["kharghar", "panvel", "kamothe", "khanda colony",
                       "new panvel", "rohinjan", "shirdhon", "taloja",
                       "kalamboli", "ulwe", "dronagiri"],
        # south, west, north, east — the pincode footprint plus a ~6 km margin so
        # amenities just outside the postal boundary are still found.
        "bbox": (18.9000, 72.9400, 19.1300, 73.2200),
        "centre": (19.0330, 73.0297),          # Kharghar node, for sanity checks
    },

    "mumbai-priority": {
        "label": "Mumbai (priority localities)",
        # Priority pockets of Mumbai City + Suburban, full depth. Pincode->area
        # labels VERIFIED against India Post (api.postalpincode.in), not guessed
        # -- the check caught 400092 being Borivali WEST, not East. Ordered
        # smallest-first so whole localities complete early: a token finishes
        # Powai/Goregaon/Dadar before it dents Borivali. The locality name shown
        # to users still comes from each project's own MahaRERA address, so the
        # pincode set is only the filter, never the displayed label.
        "pincodes": ["400076",   # Powai                    44
                     "400063",   # Goregaon East           140
                     "400014",   # Dadar (part)            \
                     "400028",   # Dadar / Prabhadevi      191 together
                     "400050",   # Bandra West             \
                     "400051",   # Bandra East             \
                     "400052",   # Khar                    302 together
                     "400071",   # Chembur                 \
                     "400074",   # Chembur Extension       \
                     "400089",   # Chembur RS / Tilak Nagar 381 together
                     "400053",   # Andheri West            \
                     "400058",   # Andheri West            \
                     "400069",   # Andheri East            \
                     "400093",   # Chakala MIDC (Andheri E)413 together
                     "400064",   # Malad West              \
                     "400097",   # Malad East              437 together
                     "400092",   # Borivali West           \
                     "400066",   # Borivali East           \
                     "400091"],  # Borivali                557 together
        "localities": ["andheri", "bandra", "khar", "borivali", "malad",
                       "goregaon", "powai", "chembur", "dadar", "prabhadevi",
                       "tilak nagar", "chakala"],
        # Covers the western suburbs (Borivali/Malad down to Bandra) plus the
        # eastern pockets (Powai, Chembur) and Dadar, with a margin for amenities
        # just outside the postal boundary.
        "bbox": (18.9500, 72.7800, 19.2800, 72.9800),
        "centre": (19.1197, 72.9060),          # Powai, roughly central to the set
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
