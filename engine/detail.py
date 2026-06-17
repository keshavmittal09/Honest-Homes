"""Parse the captured MahaRERA Tier-2 API data into clean, display-ready records.

Input: the raw per-project captures under data/snapshots/detail/<date>/<RID>.api.json
(produced by collector.fetch_detail_api) plus the downloaded files in docs/<RID>/.

Output (via build_parsed_snapshot): a SMALL, committable JSON at
data/snapshots/detail_parsed/<date>/records.json — structured fields + document
filenames only (no PDF bytes), so the web service can show rich detail on the
live site without shipping 125 MB of documents.

DetailStore loads that parsed snapshot for the API and also detects whether the
actual document files are present locally (so download links only show when real).
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
RAW_ROOT = DATA_ROOT / "snapshots" / "detail"
PARSED_ROOT = DATA_ROOT / "snapshots" / "detail_parsed"


def _ro(api: dict, ep: str):
    v = api.get("endpoints", {}).get(ep, {})
    return v.get("responseObject") if isinstance(v, dict) else None


def _first(api: dict, ep: str) -> dict:
    ro = _ro(api, ep)
    if isinstance(ro, list) and ro:
        return ro[0]
    return ro if isinstance(ro, dict) else {}


def parse_record(api: dict, doc_files: list[str]) -> dict:
    g = _ro(api, "getProjectGeneralDetailsByProjectId") or {}
    if not isinstance(g, dict):
        g = {}

    # --- Extensions (promised -> revised, with the builder's stated reason) ---
    extensions = []
    ext_ro = _ro(api, "getProjectPreviousExtensionDetails")
    if isinstance(ext_ro, list):
        for e in ext_ro:
            extensions.append({
                "appNo": e.get("projectExtensionApplicationNo"),
                "originalDate": e.get("projectOriginalCompletionDate"),
                "revisedDate": e.get("projectProposeRevisedCompletionDate"),
                "reason": (e.get("projectDelayReason") or "").strip() or None,
            })
    extensions = [e for e in extensions if e.get("revisedDate") or e.get("reason")]

    original = g.get("originalProjectProposeCompletionDate")
    proposed = g.get("projectProposeComplitionDate")
    revised = None
    if extensions:
        revised = extensions[-1].get("revisedDate") or proposed
    elif proposed and original and proposed != original:
        revised = proposed

    # --- Timeline items for the Timeline component ---
    timeline = []
    if g.get("reraRegistrationDate"):
        timeline.append({"type": "registered", "label": "RERA registered", "date": g["reraRegistrationDate"]})
    if original:
        timeline.append({"type": "promised", "label": "Promised completion", "date": original})
    for e in extensions:
        if e.get("revisedDate"):
            timeline.append({"type": "revised", "label": "Revised completion", "date": e["revisedDate"]})
    if proposed and proposed not in [original] + [e.get("revisedDate") for e in extensions]:
        timeline.append({"type": "revised", "label": "Current target", "date": proposed})

    # --- Buildings / units ---
    buildings = []
    bu = _ro(api, "getBuildingWingUnitSummary")
    if isinstance(bu, list):
        for b in bu:
            buildings.append({
                "name": b.get("buildingNameNumber") or b.get("advertisedBuildingNameNumber"),
                "wing": None if (b.get("buildingWingsNameNumber") in (None, "NA")) else b.get("buildingWingsNameNumber"),
                "floorsProposed": b.get("noOfBuildingWingFloorProposed"),
                "floorsSanctioned": b.get("noOfBuildingWingFloorSanctioned"),
                "residential": b.get("residentialUnitCount"),
                "nonResidential": b.get("nonResidentialUnitCount"),
                "total": b.get("totalUnitCount"),
            })

    # --- Litigation ---
    lit_ro = _ro(api, "getProjectLitigationDetails")
    litigation = None
    if isinstance(lit_ro, dict):
        lp = lit_ro.get("isLitigationPresent")
        if lp not in (None, ""):
            litigation = {"present": bool(lp), "declared": bool(lit_ro.get("isDeclared"))}

    # --- Complaints (from the project's own detail, if any) ---
    comp = _ro(api, "getComplaintByProjectId") or _ro(api, "getComplaintDetailsByProjectId")
    complaints = len(comp) if isinstance(comp, list) else None

    specs = {
        "type": g.get("projectTypeName"),
        "status": g.get("projectStatusName"),
        "stage": g.get("projectCurrentStatus"),
        "registeredOn": g.get("reraRegistrationDate"),
        "originalCompletion": original,
        "proposedCompletion": proposed,
        "revisedCompletion": revised,
        "unitsTotal": g.get("totalNumberOfUnits"),
        "unitsSold": g.get("totalNumberOfSoldUnits"),
        "feesPayable": g.get("projectFeesPayableAmount"),
        "lapsed": bool(g.get("isProjectLapsed")),
    }

    return {
        "rera_id": api.get("rera_id"),
        "project_id": api.get("project_id"),
        "project_name": api.get("project_name") or g.get("projectName"),
        "promoter_name": api.get("promoter_name"),
        "specs": specs,
        "timeline": timeline,
        "extensions": extensions,
        "buildings": buildings,
        "litigation": litigation,
        "complaints": complaints,
        "documents": sorted(doc_files),
        "document_count": len(doc_files),
    }


def build_parsed_snapshot() -> Path:
    """Read the latest raw capture dir, write a small parsed records.json. Returns its dir."""
    raw_dirs = sorted(d for d in RAW_ROOT.glob("*") if d.is_dir() and d.name != ".assist")
    if not raw_dirs:
        raise SystemExit("No raw detail capture found.")
    raw = raw_dirs[-1]
    records = {}
    for f in sorted(raw.glob("*.api.json")):
        api = json.loads(f.read_text(encoding="utf-8"))
        rid = api.get("rera_id")
        if not rid:
            continue
        ddir = raw / "docs" / rid
        files = sorted(os.listdir(ddir)) if ddir.is_dir() else []
        records[rid] = parse_record(api, files)
    out_dir = PARSED_ROOT / raw.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


class DetailStore:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.captured_at = ""
        self.docs_dir: Path | None = None   # local raw docs dir, if present
        self.loaded = False

    def load_latest(self) -> bool:
        dirs = sorted(d for d in PARSED_ROOT.glob("*") if d.is_dir())
        if not dirs:
            return False
        d = dirs[-1]
        rec = d / "records.json"
        if not rec.exists():
            return False
        self.records = json.loads(rec.read_text(encoding="utf-8"))
        self.captured_at = d.name
        # Are the actual document files present locally? (not on the deploy)
        raw_docs = RAW_ROOT / d.name / "docs"
        self.docs_dir = raw_docs if raw_docs.is_dir() else None
        self.loaded = True
        return True

    def get(self, rera_id: str) -> dict | None:
        return self.records.get(rera_id)

    @property
    def docs_available(self) -> bool:
        return self.docs_dir is not None

    def doc_path(self, rera_id: str, filename: str) -> Path | None:
        if not self.docs_dir:
            return None
        p = (self.docs_dir / rera_id / filename).resolve()
        # guard against path traversal
        base = (self.docs_dir / rera_id).resolve()
        if base in p.parents and p.is_file():
            return p
        return None
