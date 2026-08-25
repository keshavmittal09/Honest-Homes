"""Area search — finding projects by where they are, not what they are called.

Buyers do not search for "Balaji Symphony phase 3". They search for "Kharghar",
"Panvel", "Navi Mumbai", or a pincode. The index snapshot makes that awkward: its
`location` field is empty for all 44,279 rows and `status` is the constant
"registered", so the only positional fields are `district` and `pincode`.

Pincode alone is unhelpful to a human -- nobody browses by 410210. So the area
names come from the Tier-2 captures, where each project reports its village,
taluka and locality. Those are pooled per pincode to learn what people actually
call that postal area, and the mapping then covers every project in the index
sharing that pincode, including the ones never deep-collected.

The result: typing "kharghar" finds all 156 projects in 410210, not just the ones
whose own filing happens to spell it out.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict

log = logging.getLogger("hh.areas")

# Words that describe a place without identifying it. Kept out of area names so
# "Navi Mumbai (M Corp.)" and "Navi Mumbai" do not become two separate areas.
_NOISE = re.compile(r"\s*\((m\s*corp\.?|mc|ct|ov|np|cb|inc)\.?\)\s*$", re.I)
_MIN_FOR_AREA = 2          # a name reported by one project is not yet an area


def _clean(name: str) -> str:
    n = _NOISE.sub("", (name or "").strip())
    n = re.sub(r"\s+", " ", n)
    return n.title() if n.isupper() or n.islower() else n


class AreaIndex:
    """Area name -> the projects in it. Built once at startup, then read-only."""

    def __init__(self) -> None:
        self.loaded = False
        self._ids_by_area: dict[str, set[str]] = {}
        self._meta: dict[str, dict] = {}
        self._pin_names: dict[str, str] = {}     # pincode -> its common name

    def build(self, rows: list[dict], detail: dict | None = None) -> int:
        """`rows` are index rows; `detail` is the parsed Tier-2 snapshot."""
        detail = detail or {}
        ids_by_pin: dict[str, set[str]] = defaultdict(set)
        for r in rows:
            pin = str(r.get("pincode") or "").strip()
            if pin:
                ids_by_pin[pin].add(r["rera_id"])

        # What do the deep captures call each pincode?
        names_by_pin: dict[str, Counter] = defaultdict(Counter)
        for rid, rec in detail.items():
            a = rec.get("address") or {}
            pin = str(a.get("pincode") or "").strip()
            if not pin:
                continue
            for field in ("village", "locality", "taluka"):
                v = _clean(a.get(field) or "")
                if len(v) > 2:
                    names_by_pin[pin][v] += 1

        areas: dict[str, set[str]] = defaultdict(set)
        meta: dict[str, dict] = {}

        for pin, ids in ids_by_pin.items():
            counts = names_by_pin.get(pin) or Counter()
            best = counts.most_common(1)[0][0] if counts else None
            if best:
                self._pin_names[pin] = best
            # every name reported for this pincode maps to every project in it
            for name, n in counts.items():
                if n < _MIN_FOR_AREA and name != best:
                    continue
                key = name.lower()
                areas[key] |= ids
                m = meta.setdefault(key, {"name": name, "kind": "locality",
                                          "pincodes": set(), "count": 0})
                m["pincodes"].add(pin)
            # the pincode itself is always searchable
            key = pin
            areas[key] |= ids
            meta.setdefault(key, {"name": (best + " " + pin) if best else pin,
                                  "kind": "pincode", "pincodes": {pin}, "count": 0})

        # districts come from the index and cover everything
        for r in rows:
            d = _clean(r.get("district") or "")
            if not d:
                continue
            key = d.lower()
            areas[key].add(r["rera_id"])
            m = meta.setdefault(key, {"name": d, "kind": "district",
                                      "pincodes": set(), "count": 0})
            pin = str(r.get("pincode") or "").strip()
            if pin:
                m["pincodes"].add(pin)

        for key, ids in areas.items():
            meta[key]["count"] = len(ids)
            meta[key]["pincodes"] = sorted(meta[key]["pincodes"])

        self._ids_by_area = dict(areas)
        self._meta = meta
        self.loaded = True
        log.info("area index: %d searchable areas", len(areas))
        return len(areas)

    # -- lookups ----------------------------------------------------------

    def ids_for(self, query: str) -> set[str] | None:
        """Projects in the area a query names, or None when it names no area."""
        q = (query or "").strip().lower()
        if not q or not self.loaded:
            return None
        if q in self._ids_by_area:
            return self._ids_by_area[q]
        # a prefix is enough: "kharg" should find Kharghar while typing
        hits = [k for k in self._ids_by_area if k.startswith(q)]
        if not hits:
            hits = [k for k in self._ids_by_area if q in k]
        if not hits:
            return None
        out: set[str] = set()
        for k in hits[:6]:
            out |= self._ids_by_area[k]
        return out

    def suggest(self, query: str = "", limit: int = 8) -> list[dict]:
        """Areas matching a query, biggest first — for the search dropdown."""
        if not self.loaded:
            return []
        q = (query or "").strip().lower()
        keys = list(self._meta)
        if q:
            starts = [k for k in keys if k.startswith(q)]
            contains = [k for k in keys if q in k and k not in set(starts)]
            keys = starts + contains
        # A district is a coarser answer than a locality, so when both match a
        # query the locality is the more useful suggestion.
        rank = {"locality": 0, "pincode": 1, "district": 2}
        keys.sort(key=lambda k: (rank.get(self._meta[k]["kind"], 9),
                                 -self._meta[k]["count"]))
        return [dict(self._meta[k], key=k) for k in keys[:limit]]

    def name_for_pincode(self, pincode: str) -> str | None:
        return self._pin_names.get(str(pincode or "").strip())
