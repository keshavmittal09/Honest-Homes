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
import hashlib
import json
import os
import re
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
RAW_ROOT = DATA_ROOT / "snapshots" / "detail"
PARSED_ROOT = DATA_ROOT / "snapshots" / "detail_parsed"


def _ro(api: dict, ep: str):
    v = api.get("endpoints", {}).get(ep, {})
    return v.get("responseObject") if isinstance(v, dict) else None


# Map a raw document filename -> (clean label, category, is_important).
# Order matters: first match wins.
_DOC_RULES = [
    (r"commencement|cc[ _\-]?compress|\bcc[ _\-]\d", "Commencement Certificate", "Approvals & certificates", True),
    (r"occupanc|\boc\b", "Occupancy Certificate", "Approvals & certificates", True),
    (r"completion", "Completion Certificate", "Approvals & certificates", True),
    (r"registration", "RERA Registration Certificate", "Approvals & certificates", True),
    (r"agreement.*(sale|sell)|(sale|sell).*agreement|allot", "Agreement for Sale", "Agreements & legal", True),
    (r"\biod\b|building.?aproov|building.?approv|building.?permit|sanction|approved.?plan|intimation of disapproval",
     "Building Approval (IOD)", "Approvals & certificates", True),
    (r"title|search report|legal report", "Title & Search Report", "Agreements & legal", True),
    (r"layout", "Layout Plan", "Plans", False),
    (r"floor.?plan|\bplan\b|drawing", "Building Plan", "Plans", False),
    (r"encumbr", "Encumbrance Certificate", "Agreements & legal", False),
    # MahaRERA's statutory forms. Form 1 = architect, 2 = engineer, 3 = CA,
    # 4 = architect's project-completion certificate, 5 = annual CA report,
    # B = promoter's declaration.
    (r"for[mn].?1\b|architec|arch.?cert", "Form 1 — Architect's Certificate", "Professional certificates", False),
    (r"for[mn].?2\b|engineer|\bengg\b", "Form 2 — Engineer's Certificate", "Professional certificates", False),
    (r"for[mn].?3\b|chartered|\bca\b", "Form 3 — CA Certificate", "Professional certificates", False),
    (r"for[mn].?4\b", "Form 4 — Completion Certificate (Architect)", "Professional certificates", False),
    (r"for[mn].?5\b", "Form 5 — Annual CA Report", "Professional certificates", False),
    (r"for[mn].?b\b", "Form B — Promoter's Declaration", "Agreements & legal", False),
    (r"pan ?card|\bpan\b", "PAN Card", "KYC & financial", False),
    (r"aadha", "Aadhaar", "KYC & financial", False),
    (r"\bgst", "GST Certificate", "KYC & financial", False),
    (r"7.?12|extract", "7/12 Extract", "Agreements & legal", False),
    (r"index.?(2|ii)\b", "Index II", "Agreements & legal", False),
    (r"deed", "Deed", "Agreements & legal", False),
    (r"\bnoc\b", "NOC", "Approvals & certificates", False),
    (r"receipt|payment", "Payment Receipt", "KYC & financial", False),
    (r"declarat|affidav", "Declaration / Affidavit", "Agreements & legal", False),
    (r"sold.?unsold|unsold", "Sold / Unsold Units List", "Other", False),
    (r"society", "Society Handover", "Agreements & legal", False),
    (r"brochure|advertis", "Brochure", "Other", False),
    (r"profileimage|photo", "Photograph", "Other", False),
    (r"apartment|association", "Apartment Association", "Other", False),
]
_DOC_COMPILED = [(re.compile(rx, re.I), lab, cat, imp) for rx, lab, cat, imp in _DOC_RULES]
DOC_CATEGORY_ORDER = ["Approvals & certificates", "Agreements & legal", "Plans",
                      "Professional certificates", "KYC & financial", "Other"]

# Captured filenames are underscore-joined and often carry a numeric de-duplication
# prefix ("1_OC.pdf", "3_Title_report.pdf"). Underscore is a WORD character to the
# regex engine, so "\bpan\b" never matched "1_PAN.pdf" and "\boc[ _-]" never matched
# "1_OC.pdf" — which is why most documents fell through to "Other". Normalise the
# name to spaced words first, so the rules above see real word boundaries.
_EXT = re.compile(r"\.[a-z0-9]+$", re.I)
_DEDUP_PREFIX = re.compile(r"^\d+[ _-]+")


def _match_text(filename: str) -> str:
    s = _EXT.sub("", filename or "")
    s = s.replace("_", " ").replace("-", " ")
    s = _DEDUP_PREFIX.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


_BARE_UUID = re.compile(r"^[0-9a-f]{8}[ ][0-9a-f]{4}[ ][0-9a-f]{4}[ ][0-9a-f]{4}[ ][0-9a-f]{12}$", re.I)


def label_document(filename: str) -> dict:
    text = _match_text(filename)
    for rx, label, cat, imp in _DOC_COMPILED:
        if rx.search(text):
            return {"file": filename, "label": label, "category": cat, "important": imp}
    # A filename that is just the storage UUID tells the reader nothing; say so
    # rather than printing the raw hex as if it were a title.
    if not text or _BARE_UUID.match(text):
        return {"file": filename, "label": "Unnamed document", "category": "Other", "important": False}
    base = text[:1].upper() + text[1:]
    return {"file": filename, "label": base[:54], "category": "Other", "important": False}


def dedupe_files(doc_dir: Path, files: list[str]) -> list[str]:
    """Drop byte-identical copies of the same document.

    The same PDF is often filed under several DMS references, and the downloader
    keeps both by prefixing a counter ("Commencement_cert.pdf" and
    "1_Commencement_cert.pdf"). About a fifth of every capture is such duplicates,
    which is what turned the documents list into six identical rows. Keep one copy
    per content hash, preferring the filename without the counter prefix.
    """
    by_hash: dict[str, str] = {}
    for f in files:
        p = doc_dir / f
        try:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            by_hash.setdefault(f, f)   # unreadable: keep it, keyed by name
            continue
        kept = by_hash.get(digest)
        if kept is None or (_DEDUP_PREFIX.match(kept) and not _DEDUP_PREFIX.match(f)):
            by_hash[digest] = f
    return sorted(by_hash.values())


def label_documents(files: list[str]) -> list[dict]:
    """Label a project's documents, numbering repeats so they can be told apart.

    A project routinely files the same kind of document several times (one
    commencement certificate per building, a CA certificate per year). Rendering
    five identical "Commencement Certificate" rows gives the reader no way to pick
    one, so repeats get a 1-based suffix.
    """
    docs = [label_document(f) for f in files]
    counts: dict[str, int] = {}
    for d in docs:
        d["kind"] = d["label"]          # stable, un-numbered label for grouping/icons
        counts[d["kind"]] = counts.get(d["kind"], 0) + 1
    seen: dict[str, int] = {}
    for d in docs:
        kind = d["kind"]
        if counts[kind] > 1:
            seen[kind] = seen.get(kind, 0) + 1
            d["label"] = f"{kind} ({seen[kind]} of {counts[kind]})"
    return docs


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

    # --- Units / flats (apartment inventory with booked = sold counts) ---
    units = {"total": 0, "booked": 0, "mix": []}
    mb = _ro(api, "getMigratedBuildingDetails")
    if isinstance(mb, list):
        for r in mb:
            cnt = r.get("numberOfApartment") or 0
            bkd = r.get("numberOfBookedApartments") or 0
            units["total"] += cnt
            units["booked"] += bkd
            units["mix"].append({
                "building": r.get("buildingNameNumber"),
                "type": r.get("apartmentType"),
                "carpetArea": r.get("carpetArea"),
                "count": cnt,
                "booked": bkd,
            })
    if units["total"] == 0:  # non-migrated projects keep the header totals
        units["total"] = g.get("totalNumberOfUnits") or 0
        units["booked"] = g.get("totalNumberOfSoldUnits") or 0
    units["mix"] = [m for m in units["mix"] if m.get("count")]

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
        "unitsTotal": units["total"],
        "unitsSold": units["booked"],
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
        "units": units,
        "litigation": litigation,
        "complaints": complaints,
        "documents": label_documents(sorted(doc_files)),
        "document_count": len(doc_files),
    }


def build_parsed_snapshot() -> Path:
    """Read the latest raw capture dir, write a small parsed records.json. Returns its dir."""
    raw_dirs = sorted(d for d in RAW_ROOT.glob("*") if d.is_dir() and d.name != ".assist")
    if not raw_dirs:
        raise SystemExit("No raw detail capture found.")
    raw = raw_dirs[-1]

    # Any hosting URLs written by collector.upload_docs live only in the parsed file.
    # Carry them across a rebuild, keyed by (rera_id, filename), so re-parsing does
    # not silently un-publish every document.
    out_dir = PARSED_ROOT / raw.name
    prior: dict[tuple[str, str], str] = {}
    prior_file = out_dir / "records.json"
    if prior_file.exists():
        try:
            for rid, rec in json.loads(prior_file.read_text(encoding="utf-8")).items():
                for d in rec.get("documents", []):
                    if d.get("url") and d.get("file"):
                        prior[(rid, d["file"])] = d["url"]
        except (json.JSONDecodeError, AttributeError):
            pass

    records = {}
    for f in sorted(raw.glob("*.api.json")):
        api = json.loads(f.read_text(encoding="utf-8"))
        rid = api.get("rera_id")
        if not rid:
            continue
        ddir = raw / "docs" / rid
        files = sorted(os.listdir(ddir)) if ddir.is_dir() else []
        if files:
            files = dedupe_files(ddir, files)
        rec = parse_record(api, files)
        for d in rec["documents"]:
            url = prior.get((rid, d.get("file", "")))
            if url:
                d["url"] = url
        records[rid] = rec

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


class DetailStore:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.captured_at = ""
        self.docs_dir: Path | None = None   # local raw docs dir, if present
        self.loaded = False
        # Whether the external host recorded in records.json still answers. Probed
        # once at startup; until then we assume it does.
        self.external_ok = True

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

    def sample_external_url(self) -> str | None:
        """Any one document URL recorded at capture time, for the reachability probe."""
        for rec in self.records.values():
            for d in rec.get("documents", []):
                if d.get("url"):
                    return d["url"]
        return None

    def probe_external(self, timeout: float = 6.0) -> bool:
        """Check once whether externally hosted documents are still reachable.

        Storage buckets get deleted and their hostnames stop resolving. Rather than
        render links that 404 for every visitor, we probe a single URL at startup
        and, if it fails, stop offering external hrefs — the UI then says the
        document is on the MahaRERA record instead of pretending to serve it.
        """
        url = self.sample_external_url()
        if not url:
            self.external_ok = False
            return False
        try:
            import httpx
            r = httpx.head(url, timeout=timeout, follow_redirects=True)
            self.external_ok = r.status_code < 400
        except Exception:
            self.external_ok = False
        return self.external_ok

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
