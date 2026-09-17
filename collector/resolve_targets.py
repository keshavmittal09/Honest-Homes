"""Resolve marketing project names -> exact MahaRERA RERA ids, from the live site.

The captcha-FREE public results page accepts a `project_name` filter:
    /projects-search-result?project_state=27&project_name=<name>
It returns matching rows carrying the RERA id (old P########### or new
PR#############), the project name, the promoter, and a /public/project/view/<id>
link. Crucially this hits the LIVE portal, so it finds the PR-series and the
post-June registrations our 2 June index snapshot cannot contain.

Given a list of {builder, project} targets, this searches each, then picks the
best candidate by how well the promoter and project name match -- so
"Krishna / Aura" resolves to the right phase rather than a namesake. Output is a
JSON list with rera_id + detail_url ready to hand to fetch_detail_api --ids.

    python -m collector.resolve_targets targets.json          # [{builder,project},...]
    python -m collector.resolve_targets --demo                # a few built-in names
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
BASE = "https://maharera.maharashtra.gov.in/projects-search-result"
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_ID = re.compile(r"(PR\d{13}|P\d{11})")
_STOP = {"the", "of", "and", "project", "tower", "phase", "group", "grp", "realty",
         "developer", "developers", "builder", "dev", "llp", "pvt", "ltd", "enterprises",
         "constructions", "construction", "associates", "corporation", "co", "and"}


def _toks(s: str) -> set[str]:
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()
            if w and w not in _STOP and len(w) > 2}


def _get(url: str) -> str:
    r = urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}),
        timeout=45, context=_CTX)
    raw = r.read()
    return (gzip.decompress(raw) if r.headers.get("Content-Encoding") == "gzip"
            else raw).decode("utf-8", "replace")


def _parse_results(html: str) -> list[dict]:
    """Extract (rera_id, project_name, promoter, city, view_id) rows.

    Each result renders, once tags are stripped, as a run of cells:
        <id> | <project name> | <promoter> | <city/taluka> | Find Route
    Anchoring on each unique id's position and reading the next cells is robust
    to both the old P########### layout and the new PR############# one, where
    the strict DOM selectors in parse_index break.
    """
    order = list(dict.fromkeys(_ID.findall(html)))   # unique ids, in page order
    rows = []
    for rid in order:
        pos = html.find(rid)
        chunk = html[pos:pos + 1500]                 # this project's own row
        # The view link MUST come from within this id's own row, not by pairing
        # across the page -- pooling view links by index mis-associates them
        # (that put Krishna Aura NX on the wrong internal id).
        vm = re.search(r"/public/project/view/(\d+)", chunk)
        seg = re.sub(r"<[^>]+>", "\x01", chunk)
        seg = re.sub(r"&nbsp;", " ", seg)
        cells = [c.strip() for c in seg.split("\x01") if c.strip()]
        name = cells[1] if len(cells) > 1 else ""
        promoter = cells[2] if len(cells) > 2 else ""
        city = cells[3] if len(cells) > 3 else ""
        rows.append({"rera_id": rid, "project_name": name[:90],
                     "promoter": promoter[:90], "city": city[:60],
                     "view_id": vm.group(1) if vm else None})
    return rows


def search(name: str) -> list[dict]:
    url = BASE + "?project_state=27&project_name=" + urllib.parse.quote(name)
    for attempt in range(3):
        try:
            return _parse_results(_get(url))
        except Exception:
            if attempt == 2:
                return []
            time.sleep(4 * (attempt + 1))
    return []


# The sheet's targets are all in Kharghar, which MahaRERA files under the
# Panvel taluka. Restricting candidates to Panvel kills the statewide namesakes
# ("Aura" -> Legacy Aura in Pune, "Sapphire" -> Daga Sapphire in Nagpur) a bare
# name search returns. Matched EXACTLY, not as a substring -- "uran" is inside
# "a-uran-gabad", so substring matching quietly let Aurangabad through.
KHARGHAR_AREA = {"panvel"}


def resolve_one(builder: str, project: str, area: set[str] | None = None) -> dict:
    """Best RERA match for one target, with a confidence label.

    `area` (lowercase city/taluka names) constrains candidates to the target's
    region so a same-word project elsewhere in the state cannot win.
    """
    # The sheet splits builder and project ("Krishna" / "Aura"), but MahaRERA
    # registers the full name ("Krishna Aura NX"). So search the combined name
    # first -- that is what surfaces the specific project among statewide
    # namesakes -- then the project alone, then the builder.
    b1 = (builder or "").split("&")[0].split("-")[0].strip()   # first builder if joint
    queries = []
    for q in ("%s %s" % (b1, project), project, "%s %s" % (builder, project), builder):
        q = q.strip()
        if q and q not in queries:
            queries.append(q)

    seen = {}
    for q in queries:
        for r in search(q):
            seen[r["rera_id"]] = r
        time.sleep(0.6)

    in_area = [r for r in seen.values()
               if not area or (r.get("city") or "").strip().lower() in area]

    bt, pt = _toks(builder), _toks(project)
    best, bscore = None, 0
    for r in in_area:
        pn, bn = _toks(r["project_name"]), _toks(r["promoter"])
        score = len(pt & pn) * 3 + len(bt & bn) * 3 + len(bt & pn) + len(pt & bn)
        if score > bscore:
            bscore, best = score, r
    if not best:
        # Nothing in-area matched. Say so honestly rather than fall back to a
        # statewide namesake, which is the exact error to avoid for a meeting list.
        return {"builder": builder, "project": project, "match": "none",
                "candidates": len(seen), "in_area": len(in_area)}

    pn, bn = _toks(best["project_name"]), _toks(best["promoter"])
    both = (pt & pn) and (bt & bn)
    conf = "strong" if both else ("project-only" if (pt & pn) else "builder-only")
    return {"builder": builder, "project": project, "match": conf,
            "rera_id": best["rera_id"],
            "detail_url": ("https://maharerait.maharashtra.gov.in/public/project/view/%s"
                           % best["view_id"]) if best["view_id"] else None,
            "rera_name": best["project_name"], "promoter": best["promoter"],
            "city": best.get("city"), "candidates": len(seen), "in_area": len(in_area)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="?", help="JSON list of {builder, project}")
    ap.add_argument("--out", default="data/_resolved_targets.json")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    if a.demo:
        targets = [{"builder": "Gami & Bhagwati", "project": "Krishna Aura NX"},
                   {"builder": "Chandak group", "project": "Noviya 11"},
                   {"builder": "Sai Developer & Priyanka", "project": "Codename Evolve"}]
    else:
        targets = json.loads(Path(a.targets).read_text(encoding="utf-8"))

    out = []
    for t in targets:
        r = resolve_one(t.get("builder", ""), t.get("project", ""), area=KHARGHAR_AREA)
        out.append(r)
        print("  [%-12s] %-16s %-22s -> %s %s" % (
            r["match"], (t.get("builder") or "")[:16], (t.get("project") or "")[:22],
            r.get("rera_id", "—"),
            ("(%s | %s)" % (r.get("rera_name", ""), r.get("city", "")))[:48] if r.get("rera_id") else ""))
        time.sleep(1.0)      # polite to the gov site

    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for k in ("strong", "project-only", "builder-only", "none"):
        print("%-14s %d" % (k, sum(1 for r in out if r["match"] == k)))
    print("-> %s" % a.out)


if __name__ == "__main__":
    main()
