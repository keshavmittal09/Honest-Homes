"""Quality signals for amenities, from free authoritative sources.

OpenStreetMap tells us a school exists and where it is. It does not tell us
whether it is any good. Star ratings would need Google Places and a paid key, and
for the categories that matter most they are the weaker evidence anyway: "NAAC
A+" or "NIRF rank 34" is a published government assessment, while "4.3 stars from
60 reviews" is a mood.

Two sources, both free and neither needing a key:

* **Wikidata** — notability and structured facts. A hospital or college with a
  Wikidata item is a real institution someone thought worth recording, and the
  item often carries inception date, capacity and official website. Matched on
  the `wikidata` tag OSM already carries, then by name within a short distance.
* **NIRF** — the Ministry of Education's national rankings (overall, university,
  engineering, medical, management, pharmacy). This is a genuine, published
  quality assessment for colleges, refreshed yearly.

What is deliberately absent: NABH hospital accreditation. Its list is rendered
client-side, so collecting it needs a browser session rather than a fetch. It is
worth adding later -- accreditation is exactly the kind of hard signal this
module is for -- but it is not pretended to exist here.

Output is a region-level cache keyed by OSM id, merged into per-project
directories by fetch_amenities.py. Enriching once per place rather than once per
project is what keeps this cheap: a Kharghar school is shared by every project
near it.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from collector.regions import DEFAULT_REGION, region

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "HonestHomes/1.0 (+https://honesthomes.onrender.com; propelloai.mmr@gmail.com)"

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
NIRF_YEAR = 2024
NIRF_LISTS = {
    "Overall": "OverallRanking.html",
    "University": "UniversityRanking.html",
    "Engineering": "EngineeringRanking.html",
    "Medical": "MedicalRanking.html",
    "Management": "ManagementRanking.html",
    "Pharmacy": "PharmacyRanking.html",
    "College": "CollegeRanking.html",
}


def _get(url: str, data: bytes | None = None, tries: int = 3) -> bytes | None:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                print("    fetch failed: %s %s" % (url[:60], str(e)[:60]))
                return None
            time.sleep(8 * (i + 1))
    return None


# --------------------------------------------------------------------------
# Wikidata
# --------------------------------------------------------------------------

def wikidata_nearby(centre: tuple[float, float], radius_km: float = 18.0) -> dict:
    """Every Wikidata item with coordinates near the region, keyed by Q-id.

    One SPARQL call covers the whole region. `wikibase:around` is an index-backed
    service call, so this stays fast even at an 18 km radius.
    """
    lat, lon = centre
    q = """
SELECT ?item ?itemLabel ?typeLabel ?coord ?website ?inception WHERE {
  SERVICE wikibase:around {
    ?item wdt:P625 ?coord .
    bd:serviceParam wikibase:center "Point(%f %f)"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "%f" .
  }
  OPTIONAL { ?item wdt:P31 ?type }
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P571 ?inception }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,hi,mr" }
}
""" % (lon, lat, radius_km)
    url = WIKIDATA_SPARQL + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    raw = _get(url)
    if not raw:
        return {}
    try:
        js = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return {}
    out: dict[str, dict] = {}
    for b in js.get("results", {}).get("bindings", []):
        qid = b.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        if not qid:
            continue
        label = b.get("itemLabel", {}).get("value")
        if not label or label == qid:
            continue
        rec = out.setdefault(qid, {
            "qid": qid, "label": label, "types": [],
            "website": b.get("website", {}).get("value"),
            "inception": (b.get("inception", {}).get("value") or "")[:4] or None,
            "url": "https://www.wikidata.org/wiki/" + qid,
        })
        t = b.get("typeLabel", {}).get("value")
        if t and t not in rec["types"]:
            rec["types"].append(t)
    return out


# --------------------------------------------------------------------------
# NIRF
# --------------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_NAME = re.compile(r"^(.*?)(?:More Details|Close)", re.S)


def nirf_maharashtra(year: int = NIRF_YEAR) -> list[dict]:
    """Ranked Maharashtra institutions across every NIRF list.

    The tables are flat <td> runs rather than tidy rows, so cells are read in
    order and stitched: institute id, name blob, ..., city, state, score, rank.
    Rows that do not parse cleanly are dropped rather than guessed at.
    """
    found: list[dict] = []
    for category, page in NIRF_LISTS.items():
        raw = _get("https://www.nirfindia.org/Rankings/%d/%s" % (year, page))
        if not raw:
            continue
        html = raw.decode("utf-8", "replace")
        cells = [_TAG.sub("", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", html, re.S)]
        cells = [c for c in cells if c]
        for i, c in enumerate(cells):
            if c != "Maharashtra":
                continue
            # walk back to the institute id (IR-...), which starts the row
            start = None
            for j in range(i - 1, max(-1, i - 12), -1):
                if cells[j].startswith("IR-"):
                    start = j
                    break
            if start is None:
                continue
            blob = cells[start + 1] if start + 1 < len(cells) else ""
            m = _NAME.match(blob)
            name = (m.group(1) if m else blob).strip(" |")
            name = re.sub(r"\s+", " ", name)
            if not name:
                continue
            city = cells[i - 1] if i >= 1 else None
            score = rank = None
            if i + 1 < len(cells):
                try:
                    score = float(cells[i + 1])
                except ValueError:
                    pass
            if i + 2 < len(cells):
                m2 = re.match(r"^(\d+)", cells[i + 2])
                if m2:
                    rank = int(m2.group(1))
            found.append({
                "name": name, "city": city, "category": category,
                "rank": rank, "score": score, "year": year,
                "source": "NIRF %d, Ministry of Education" % year,
            })
        print("  NIRF %-12s %3d Maharashtra entries" % (category, sum(
            1 for f in found if f["category"] == category)), flush=True)
        time.sleep(1.5)
    return found


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------

# Deliberately short. An earlier version also stripped "school", "college",
# "high" and "institute" as noise -- which made "St. Xavier's High School" and
# "St. Xavier`s College" both collapse to {xavier} and match at 1.00, attaching
# a national college ranking to a local high school. The words that distinguish
# one kind of institution from another are the opposite of noise.
_STOP = {"the", "of", "and", "at", "for", "trust", "society",
         "shri", "sri", "smt", "dr", "navi", "mumbai", "new"}


def _norm(name: str) -> set[str]:
    words = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).split()
    return {w for w in words if w not in _STOP and len(w) > 2}


def _similar(a: str, b: str) -> float:
    """Jaccard over meaningful words. Deliberately blunt: institution names vary
    so much in punctuation and honorifics that anything stricter misses real
    matches, and anything looser starts pairing every 'City Hospital'."""
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


def enrich(region_name: str, refresh: bool = False) -> dict:
    reg = region(region_name)
    root = DATA / "regions" / region_name / "amenities"
    pois_path = root / "pois.json"
    if not pois_path.exists():
        raise SystemExit("no POI cache yet — run collector.fetch_amenities first")
    pois = json.loads(pois_path.read_text(encoding="utf-8"))

    out_path = root / "quality.json"
    if out_path.exists() and not refresh:
        print("quality cache exists (use --refresh to rebuild)")
        return json.loads(out_path.read_text(encoding="utf-8"))

    print("Wikidata: items near %s..." % reg["label"], flush=True)
    wd = wikidata_nearby(reg["centre"])
    print("  %d Wikidata items with coordinates" % len(wd), flush=True)

    print("NIRF: ranked Maharashtra institutions...", flush=True)
    nirf = nirf_maharashtra()
    print("  %d ranked entries total" % len(nirf), flush=True)

    quality: dict[str, dict] = {}
    wd_by_name = {v["label"].lower(): v for v in wd.values()}
    matched_wd = matched_nirf = 0

    for cat, places in pois.get("categories", {}).items():
        for p in places:
            tags = p.get("tags") or {}
            rec: dict = {}

            # -- Wikidata: prefer the id OSM already carries; it is exact.
            qid = tags.get("wikidata")
            item = wd.get(qid) if qid else None
            if item is None:
                cand = wd_by_name.get(p["name"].lower())
                if cand:
                    item = cand
            if item:
                rec["wikidata"] = {
                    "qid": item["qid"], "label": item["label"],
                    "types": item["types"][:4], "website": item.get("website"),
                    "since": item.get("inception"), "url": item["url"],
                    "match": "osm-tag" if qid else "name",
                }
                matched_wd += 1

            # -- NIRF ranks higher education only. A school is never eligible,
            # however similar its name is to a ranked college -- trusts commonly
            # run both under one name, and the ranking belongs to exactly one.
            amenity = (tags.get("amenity") or "").lower()
            if cat == "colleges" and amenity in ("college", "university"):
                best, best_s = None, 0.0
                for n in nirf:
                    s = _similar(p["name"], n["name"])
                    if s > best_s:
                        best, best_s = n, s
                # Two shared meaningful words minimum: a single shared token is
                # how "City Hospital" ends up matching "City College".
                shared = len(_norm(p["name"]) & _norm(best["name"])) if best else 0
                if best and best_s >= 0.55 and shared >= 2:
                    rec["nirf"] = dict(best, matchConfidence=round(best_s, 2))
                    matched_nirf += 1

            if rec:
                rec["name"] = p["name"]
                quality[p["osm"]] = rec

    payload = {
        "region": reg["label"],
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sources": [
            "Wikidata (CC0) — notability and structured facts",
            "NIRF %d, Ministry of Education — official national rankings" % NIRF_YEAR,
        ],
        "notAvailable": [
            "NABH hospital accreditation — list is rendered client-side and needs "
            "a browser session, not yet collected",
            "Google Places star ratings and photos — needs a paid API key",
        ],
        "matched": {"wikidata": matched_wd, "nirf": matched_nirf},
        "places": quality,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nmatched: %d Wikidata, %d NIRF -> %s" % (matched_wd, matched_nirf, out_path))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default=DEFAULT_REGION)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    enrich(a.region, a.refresh)


if __name__ == "__main__":
    main()
