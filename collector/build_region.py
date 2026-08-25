"""Assemble one region into a per-project folder tree.

The dated capture directories are organised for the scraper's convenience: every
run writes its own `data/snapshots/detail/<date>/`, so a single project's files
can be spread across several dates, and its documents sit in an area-sorted tree
some distance from its JSON. That is right for collection and wrong for reading.

This materialises the readable view — one folder per project holding everything
we know about it:

    data/regions/<region>/
      index.json                     roll-up: every project, grades, counts
      amenities/pois.json            the region's POI cache
      projects/<RERA-ID>/
        project.json                 full parsed record (specs, units, land, ...)
        documents/                   project documents, named by what they are
        complaints/<COMPLAINT-NO>/
          complaint.json             parties, direction, dates, outcome
          documents/                 order, roznama, warrant PDFs
        amenities/
          amenities.json             everything within the radius, graded
          map-street.jpg
          map-satellite.jpg

Documents are hard-linked where the filesystem allows it, so the readable tree
costs no extra disk. It falls back to copying across volumes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from pathlib import Path

from collector.regions import DEFAULT_REGION, region

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe(name: str, limit: int = 120) -> str:
    """A filename that survives Windows, Linux and a zip download."""
    out = SAFE.sub("", (name or "").replace("/", "-")).strip(" .")
    return (out[:limit] or "file")


def _link(src: Path, dst: Path) -> str:
    """Hard-link, else copy. Returns what happened, for the manifest."""
    if dst.exists():
        return "present"
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
        return "linked"
    except OSError:
        try:
            shutil.copy2(src, dst)
            return "copied"
        except OSError:
            return "failed"


def _doc_dirs() -> dict[str, list[Path]]:
    """rera_id -> every directory holding its documents, across capture dates."""
    idx: dict[str, list[Path]] = {}
    root = DATA / "snapshots" / "detail"
    if not root.exists():
        return idx
    for d in root.rglob("P[0-9]*"):
        if d.is_dir() and re.fullmatch(r"P\d{11}", d.name):
            idx.setdefault(d.name, []).append(d)
    return idx


def _find(dirs: list[Path], filename: str) -> Path | None:
    if not filename:
        return None
    for d in dirs:
        p = d / filename
        if p.exists():
            return p
        hit = next((q for q in d.rglob(filename) if q.is_file()), None)
        if hit:
            return hit
    return None


def build(region_name: str, limit: int = 0, with_docs: bool = True) -> None:
    reg = region(region_name)
    out_root = DATA / "regions" / region_name
    proj_root = out_root / "projects"
    proj_root.mkdir(parents=True, exist_ok=True)

    parsed = sorted((DATA / "snapshots" / "detail_parsed").glob("*/records.json"))
    if not parsed:
        raise SystemExit("no parsed snapshot found — run the parser first")
    records = json.loads(parsed[-1].read_text(encoding="utf-8"))

    index = {}
    for line in (DATA / "snapshots" / "index" / "2026-06-02" / "rows.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        index[r["rera_id"]] = r

    want = set(reg["pincodes"])
    ids = [rid for rid, row in index.items() if str(row.get("pincode") or "") in want]
    have = [rid for rid in ids if rid in records]
    if limit:
        have = have[:limit]

    print("%s: %d projects in region, %d captured so far" % (reg["label"], len(ids), len(have)))
    docs_by_id = _doc_dirs() if with_docs else {}

    roll = []
    stats = {"docs": 0, "complaint_docs": 0, "linked": 0, "copied": 0, "missing": 0}

    for n, rid in enumerate(have, 1):
        rec = records[rid]
        pdir = proj_root / rid
        pdir.mkdir(parents=True, exist_ok=True)

        (pdir / "project.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

        dirs = docs_by_id.get(rid, [])

        # --- project documents, named by what they are rather than by GUID -----
        if with_docs:
            for d in rec.get("documents") or []:
                src = _find(dirs, d.get("file") or "")
                if not src:
                    stats["missing"] += 1
                    continue
                label = _safe(d.get("kind") or d.get("label") or src.stem)
                dst = pdir / "documents" / ("%s%s" % (label, src.suffix or ".pdf"))
                i = 2
                while dst.exists() and dst.stat().st_size != src.stat().st_size:
                    dst = dst.with_name("%s (%d)%s" % (label, i, src.suffix or ".pdf"))
                    i += 1
                r = _link(src, dst)
                stats["docs"] += 1
                stats[r] = stats.get(r, 0) + 1

        # --- complaints, one folder each, with their papers -------------------
        pc = rec.get("projectComplaints") or {}
        for c in pc.get("complaints") or []:
            cno = _safe(c.get("complaintNo") or "complaint")
            cdir = pdir / "complaints" / cno
            cdir.mkdir(parents=True, exist_ok=True)
            (cdir / "complaint.json").write_text(
                json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
            if not with_docs:
                continue
            papers = []
            order = c.get("order") or {}
            if order.get("file"):
                papers.append(("Order", order["file"]))
            for nc in c.get("nonCompliance") or []:
                if nc.get("roznamaFile"):
                    papers.append(("Hearing record (Roznama)", nc["roznamaFile"]))
            w = c.get("warrant") or {}
            if isinstance(w, dict) and w.get("file"):
                papers.append(("Recovery warrant", w["file"]))
            for label, fn in papers:
                src = _find(dirs, fn)
                if not src:
                    stats["missing"] += 1
                    continue
                dst = cdir / "documents" / ("%s%s" % (_safe(label), src.suffix or ".pdf"))
                i = 2
                while dst.exists() and dst.stat().st_size != src.stat().st_size:
                    dst = dst.with_name("%s (%d)%s" % (_safe(label), i, src.suffix or ".pdf"))
                    i += 1
                r = _link(src, dst)
                stats["complaint_docs"] += 1
                stats[r] = stats.get(r, 0) + 1

        # --- roll-up row ------------------------------------------------------
        am_path = pdir / "amenities" / "amenities.json"
        am = json.loads(am_path.read_text(encoding="utf-8")) if am_path.exists() else None
        sp = rec.get("specs") or {}
        roll.append({
            "reraId": rid,
            "name": rec.get("project_name") or index[rid].get("project_name"),
            "promoter": rec.get("promoter_name") or index[rid].get("promoter_name"),
            "pincode": index[rid].get("pincode"),
            "village": (rec.get("address") or {}).get("village"),
            "status": sp.get("status"),
            "lapsed": sp.get("lapsed"),
            "registeredOn": sp.get("registeredOn"),
            "unitsTotal": sp.get("unitsTotal"),
            "unitsSold": sp.get("unitsSold"),
            "documents": len(rec.get("documents") or []),
            "complaints": pc.get("count"),
            "complaintsByBuyer": pc.get("byBuyer"),
            "complaintsByBuilder": pc.get("byBuilder"),
            "amenityGrade": (am or {}).get("overall", {}).get("grade"),
            "amenityScore": (am or {}).get("overall", {}).get("score"),
            "folder": "projects/%s" % rid,
        })
        if n % 25 == 0 or n == len(have):
            print("  [%d/%d] %s" % (n, len(have), rid))

    (out_root / "index.json").write_text(json.dumps({
        "region": reg["label"],
        "pincodes": reg["pincodes"],
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "projectsInRegion": len(ids),
        "projectsCaptured": len(have),
        "projects": sorted(roll, key=lambda r: (r["name"] or "").lower()),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\nprojects written : %d" % len(have))
    print("project docs     : %d" % stats["docs"])
    print("complaint docs   : %d" % stats["complaint_docs"])
    print("linked/copied    : %d / %d" % (stats.get("linked", 0), stats.get("copied", 0)))
    print("files not found  : %d" % stats["missing"])
    print("-> %s" % out_root)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default=DEFAULT_REGION)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-docs", action="store_true",
                    help="write JSON only; skip linking document files")
    a = ap.parse_args()
    build(a.region, a.limit, not a.no_docs)


if __name__ == "__main__":
    main()
