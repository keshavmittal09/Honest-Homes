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
    # Complaint evidence comes FIRST. These are the papers behind the most damaging
    # facts on a project's page — the signed order, the hearing record, and the
    # recovery warrant. They were previously unmatched, so they fell to the bottom
    # of the download priority and were cut by the per-project cap.
    (r"\brecovery warrant|\bwarrant\b|\brw[ _\-]", "Recovery Warrant", "Complaint papers", True),
    (r"ro[zj]e?anama|roznama|\brfo\b", "Hearing Record (Roznama)", "Complaint papers", True),
    (r"interim order|final order|\border\b|\bcc\d{3}|order of ", "Complaint Order", "Complaint papers", True),
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
DOC_CATEGORY_ORDER = ["Complaint papers", "Approvals & certificates", "Agreements & legal", "Plans",
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


def _sanitised(name: str) -> str:
    """The on-disk filename the downloader would produce for this reference."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name or "")[:120]
    return safe if "." in safe else safe + ".pdf"


def merge_document_refs(on_disk: list[str], refs: list[dict]) -> list[tuple[str, bool]]:
    """(filename, downloaded) for every document the project references.

    A project can reference hundreds of documents while we only pull the ones a
    buyer checks. Listing just the downloaded ones would misrepresent the record
    as thinner than it is, so every reference is kept and flagged; the UI links
    only the ones actually present and points the rest at MahaRERA.
    """
    have = set(on_disk)
    out: list[tuple[str, bool]] = [(f, True) for f in sorted(on_disk)]
    seen = set(on_disk)
    for r in refs or []:
        fn = r.get("fileName")
        if not fn:
            continue
        safe = _sanitised(fn)
        if safe in have or safe in seen:
            continue
        # the downloader prefixes "<n>_" on collision, so check those too
        if any(d.endswith("_" + safe) for d in have):
            continue
        seen.add(safe)
        out.append((safe, False))
    return out


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


def _geo(api: dict) -> dict | None:
    """Latitude/longitude from the project's geo-tagging details.

    The index snapshot's map_url is empty for all but one of 44,279 projects
    ("...&query=,"), so Tier-2 is in practice the ONLY source of coordinates —
    and it carries them for every project captured so far.
    """
    found: list[tuple] = []

    def walk(x):
        if isinstance(x, dict):
            la, lo = x.get("latitude"), x.get("longitude")
            if la not in (None, "", 0) and lo not in (None, "", 0):
                try:
                    found.append((float(la), float(lo)))
                except (TypeError, ValueError):
                    pass
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(api.get("endpoints", {}))
    for lat, lng in found:
        # Maharashtra's bounding box — rejects 0,0 and transposed pairs.
        if 15.5 <= lat <= 22.5 and 72.0 <= lng <= 81.0:
            return {"lat": round(lat, 6), "lng": round(lng, 6)}
    return None


def _labelled_docs(on_disk: list[str], refs: list[dict]) -> tuple[list[dict], list[dict]]:
    """(documents we hold, summary of every kind on record).

    Listing all ~60,000 referenced documents individually produced a 13 MB
    snapshot in which 94% of rows were unopenable — a project with 481 references
    rendered 456 dead entries. Instead: the held documents in full (linkable), and
    a per-kind tally covering everything on record. The reader still learns the
    complete paper trail exists without wading through it.
    """
    held = label_documents(sorted(on_disk))
    for d in held:
        d["downloaded"] = True

    counts: dict[str, int] = {}
    for r in refs or []:
        fn = r.get("fileName")
        if fn:
            counts[label_document(_sanitised(fn))["label"]] = \
                counts.get(label_document(_sanitised(fn))["label"], 0) + 1
    have: dict[str, int] = {}
    for d in held:
        have[d["kind"]] = have.get(d["kind"], 0) + 1

    # Cap the tally: a project can reference a hundred distinct one-off filenames,
    # and the long tail was 40% of the whole snapshot while telling a reader
    # nothing. Keep the kinds that actually recur, plus a count of the remainder.
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    summary = [{"kind": k, "onRecord": n, "held": have.get(k, 0)} for k, n in ranked[:12]]
    rest = ranked[12:]
    if rest:
        summary.append({"kind": f"{len(rest)} other document type(s)",
                        "onRecord": sum(n for _, n in rest),
                        "held": sum(have.get(k, 0) for k, _ in rest)})
    return held, summary


_PARTY_NOISE = re.compile(r"\b(m/?s|mr|mrs|ms|shri|smt|and|ors?|others?|pvt|private|"
                          r"ltd|limited|llp|co|company|builders?|developers?|"
                          r"construction[s]?|realty|infra(structure)?|estates?|"
                          r"ventures?|enterprises?)\b", re.I)


def _party_key(name: str) -> set[str]:
    """Distinguishing word-set for a party name, for builder/buyer matching."""
    s = re.sub(r"^\s*\d+\)\s*", " ", name or "")        # "1) Foo 2) Bar"
    s = re.sub(r"\d+\)", " ", s)
    s = _PARTY_NOISE.sub(" ", s.lower())
    return {w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 2}


def _is_promoter(name: str, promoter: str) -> bool:
    """Is this party the project's own promoter (rather than a buyer)?"""
    a, b = _party_key(name), _party_key(promoter)
    if not a or not b:
        return False
    return len(a & b) >= min(2, len(b)) or (len(b) == 1 and b <= a)


# Markers that a party is a business rather than a person. Needed because the
# respondent is frequently a JOINT developer whose name differs from the
# registered promoter — matching the promoter alone left half of all complaints
# with an unknown direction.
_ORG_MARKERS = re.compile(
    r"\b(m/?s|builders?|developers?|construction|constructions|realty|infra|"
    r"infrastructure|estates?|ventures?|enterprises?|associates?|corporation|"
    r"company|pvt|private|ltd|limited|llp|group|projects?|promoters?|"
    r"buildcon|landmark|properties|property|homes|housing|realtors?)\b", re.I)


def _looks_like_org(name: str) -> bool:
    if not name:
        return False
    if _ORG_MARKERS.search(name):
        return True
    return bool(re.search(r"\d+\)", name))       # "1) X 2) Y" — a party list


def parse_address(api: dict) -> dict:
    """District / taluka / village / locality for the project's LAND.

    The API exposes these as plain names alongside the encrypted addressLine, and
    they are far more precise than the index's district alone — `locality` is the
    sector and neighbourhood, which is what a buyer actually recognises and what
    makes the document folders browsable by area.
    """
    best: dict = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get("districtName") or o.get("villageName"):
                cand = {
                    "district": (o.get("districtName") or "").strip() or None,
                    "taluka": (o.get("talukaName") or "").strip() or None,
                    "village": (o.get("villageName") or "").strip() or None,
                    "pincode": str(o.get("pinCode") or o.get("pincode") or "").strip() or None,
                    "locality": (o.get("locality") or "").strip() or None,
                }
                # prefer the richest record seen
                if sum(v is not None for v in cand.values()) > sum(v is not None for v in best.values()):
                    best.clear(); best.update(cand)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(api.get("endpoints", {}))
    return best


def parse_complaints(api: dict, promoter: str) -> list[dict]:
    """Every complaint on this project, assembled from all four MahaRERA sources.

    The portal splits one complaint across separate endpoints: the complaint
    itself (parties + status), the signed order, any non-compliance applications
    with their hearing roznamas, and any recovery warrant. Keyed by registration
    number so a buyer sees one row per dispute with its whole life-cycle, rather
    than four disconnected tables.

    Direction matters and is not given directly: MahaRERA names a complainant and
    a respondent, so we compare both against the project's promoter to say whether
    a buyer complained about the builder or the builder complained about a buyer.
    """
    eps = api.get("endpoints", {}) or {}

    def ro(k):
        v = eps.get(k)
        return v.get("responseObject") if isinstance(v, dict) else None

    base = ro("getComplaintByProjectId")
    base = base if isinstance(base, list) else []
    det = ro("getComplaintDetailsByProjectId") or {}
    det = det if isinstance(det, dict) else {}

    by_no: dict[str, dict] = {}

    def slot(no, cid=None):
        no = no or (f"complaint-{cid}" if cid else "unknown")
        return by_no.setdefault(no, {
            "complaintNo": no, "type": None, "filedOn": None, "status": None,
            "resolved": None, "complainant": None, "respondent": None,
            "direction": None, "order": None, "nonCompliance": [], "warrant": None,
        })

    for c in base:
        r = slot(c.get("complaintRegistrationNo"), c.get("complaintId"))
        r["type"] = c.get("complaintTypeName")
        r["filedOn"] = (c.get("complaintRegistrationDate") or "")[:10] or None
        r["status"] = (c.get("complaintStatus") or "").strip() or None
        r["complainant"] = (c.get("profileNameComplainant") or "").strip() or None
        r["respondent"] = (c.get("profileNameRespondent") or "").strip() or None

    for o in (det.get("complaintDetails") or []):
        r = slot(o.get("complaintRegistrationNo"), o.get("complaintId"))
        r["complainant"] = r["complainant"] or (o.get("complainantName") or "").strip() or None
        r["respondent"] = r["respondent"] or (o.get("respondentName") or "").strip() or None
        r["filedOn"] = r["filedOn"] or o.get("complaintFilingDate")
        if o.get("orderFileName") or o.get("orderDmsRefNo"):
            r["order"] = {"file": o.get("orderFileName"),
                          "ref": o.get("orderDmsRefNo"),
                          "approvedOn": (o.get("approvalDateTime") or "")[:10] or None}

    for m in (det.get("miscComplaintDetails") or []):
        r = slot(m.get("complaintRegistrationNo"), m.get("complaintId"))
        r["nonCompliance"].append({
            "appliedOn": (m.get("nonComplianceAppliedDate") or "")[:10] or None,
            "roznamaFile": m.get("roznamaFileName"),
            "roznamaRef": m.get("roznamaDmsRefNo"),
            "roznamaOn": (m.get("roznamaGenerationDate") or "")[:10] or None,
            "note": (m.get("roznamaContent") or "").strip() or None,
        })

    for w in (det.get("warrentDetails") or []):
        r = slot(w.get("complaintRegistrationNo"), w.get("complaintId"))
        r["warrant"] = {
            "file": w.get("warrantFileName"), "ref": w.get("warrantDmsRefNo"),
            "issuedOn": (w.get("dateOfIssueOfWarrant") or "")[:10] or None,
            "amount": w.get("totalAmountOfRecovery"),
            "issued": (w.get("isIssued") or "").strip() or None,
            "district": w.get("districtName"),
        }

    out = []
    for r in by_no.values():
        # A party is the "builder side" if it matches the registered promoter OR
        # simply reads as a business — joint developers are named as respondents
        # under their own name, not the promoter's.
        comp_biz = (_is_promoter(r["complainant"] or "", promoter)
                    or _looks_like_org(r["complainant"] or ""))
        resp_biz = (_is_promoter(r["respondent"] or "", promoter)
                    or _looks_like_org(r["respondent"] or ""))
        if resp_biz and not comp_biz:
            r["direction"] = "buyer_vs_builder"
        elif comp_biz and not resp_biz:
            r["direction"] = "builder_vs_buyer"
        elif comp_biz and resp_biz:
            r["direction"] = "business_vs_business"
        else:
            r["direction"] = "unknown"
        st = (r["status"] or "").lower()
        # An approved order closes the complaint; a warrant means the order was
        # NOT complied with, so it re-opens as unresolved regardless of status.
        r["resolved"] = (("order approved" in st or "closed" in st or "disposed" in st)
                         and not r["warrant"])
        r["nonCompliance"].sort(key=lambda x: x.get("appliedOn") or "")
        out.append(r)

    out.sort(key=lambda r: (r.get("filedOn") or ""), reverse=True)
    return out


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

    # --- Litigation / court cases declared for THIS project ---
    lit_ro = _ro(api, "getProjectLitigationDetails")
    litigation = None
    if isinstance(lit_ro, dict):
        cases = []
        for c in (lit_ro.get("projectLitigationDtlsResponse") or []):
            cases.append({
                "court": (c.get("courtName") or "").strip() or None,
                "caseNo": c.get("caseNumber") or c.get("caseNo"),
                "year": c.get("caseYear"),
                "status": (c.get("caseStatus") or "").strip() or None,
                "remark": (c.get("litigationRemark") or c.get("remark") or "").strip() or None,
            })
        present = lit_ro.get("isLitigationPresent")
        litigation = {
            "present": bool(present) or bool(cases),
            "declared": bool(lit_ro.get("isDeclared")),
            "cases": cases,
            "count": len(cases),
        }

    # --- Complaints filed against THIS project -------------------------------
    # Two endpoints carry different halves of the picture and BOTH have to be
    # read: getComplaintByProjectId is a list of the complaints themselves, while
    # getComplaintDetailsByProjectId is a *dict* holding the signed orders, the
    # non-compliance applications and the recovery warrants. The previous version
    # only counted a list, so whenever the first endpoint returned NO_RECORDS_FOUND
    # the dict fell through and the count became None — reporting "unknown" for
    # every project, including the ones with a genuinely clean record.
    comp_list = _ro(api, "getComplaintByProjectId")
    comp_list = comp_list if isinstance(comp_list, list) else []
    det_ro = _ro(api, "getComplaintDetailsByProjectId")
    det_ro = det_ro if isinstance(det_ro, dict) else {}

    def _rows(key):
        v = det_ro.get(key)
        return v if isinstance(v, list) else []

    orders = [{
        "complaintNo": o.get("complaintRegistrationNo"),
        "filedOn": o.get("complaintFilingDate"),
        "orderFile": o.get("orderFileName"),
        "orderRef": o.get("orderDmsRefNo"),
        "complainant": (o.get("complainantName") or "").strip() or None,
        "respondent": (o.get("respondentName") or "").strip() or None,
    } for o in _rows("complaintDetails")]

    noncompliance = [{
        "complaintNo": m.get("complaintRegistrationNo"),
        "appliedOn": m.get("nonComplianceAppliedDate"),
        "roznamaFile": m.get("roznamaFileName"),
        "roznamaOn": m.get("roznamaGenerationDate"),
    } for m in _rows("miscComplaintDetails")]

    warrants = [{
        "complaintNo": w.get("complaintRegistrationNo"),
        "amount": w.get("recoveryAmount") or w.get("amount"),
        "issuedOn": w.get("warrantIssueDate") or w.get("issueDate"),
        "status": (w.get("warrantStatus") or "").strip() or None,
    } for w in _rows("warrentDetails")]

    complaint_rows = [{
        "complaintNo": c.get("complaintRegistrationNo"),
        "type": c.get("complaintTypeName"),
        "filedOn": (c.get("complaintRegistrationDate") or "")[:10] or None,
        "status": (c.get("complaintStatus") or "").strip() or None,
        "complainant": (c.get("profileNameComplainant") or "").strip() or None,
        "respondent": (c.get("profileNameRespondent") or "").strip() or None,
    } for c in comp_list]

    # Complaint numbers seen anywhere, so a complaint that only appears in the
    # orders table still counts toward the total.
    seen_nos = {r["complaintNo"] for r in complaint_rows if r.get("complaintNo")}
    seen_nos |= {o["complaintNo"] for o in orders if o.get("complaintNo")}
    complaints = len(seen_nos) if (seen_nos or det_ro or comp_list) else None

    full = parse_complaints(api, api.get("promoter_name") or "")
    project_complaints = {
        "count": complaints if complaints is not None else (len(full) or None),
        "complaints": full,
        "unresolved": sum(1 for c in full if c.get("resolved") is False),
        "byBuyer": sum(1 for c in full if c["direction"] == "buyer_vs_builder"),
        "byBuilder": sum(1 for c in full if c["direction"] == "builder_vs_buyer"),
        "rows": complaint_rows,
        "orders": orders,
        "nonCompliance": noncompliance,
        "warrants": warrants,
    }

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

    _docs = _labelled_docs(doc_files, api.get("documents") or [])

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
        "geo": _geo(api),
        "address": parse_address(api),
        "litigation": litigation,
        "complaints": complaints,
        "projectComplaints": project_complaints,
        "documents": _docs[0],
        "documentSummary": _docs[1],
        "document_count": len(doc_files),
        "document_refs": len(api.get("documents") or []),
    }


def _kv(d: dict, *needles: str):
    """First key_values entry whose key starts with any of `needles`."""
    kv = d.get("key_values") or {}
    for n in needles:
        for k, v in kv.items():
            if k.lower().startswith(n.lower()):
                s = str(v).strip()
                if s and s != ":":
                    return s
    return None


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_html_record(d: dict) -> dict:
    """Parse a capture made by the HTML collector (run_detail.py).

    That page carries the plot's identity — CTS/survey number, land area,
    boundaries, the declared-litigation flag — which the API capture does NOT.
    It carries no complaints and no documents, so those stay unknown (None), not
    zero: we have genuinely not looked at the project's complaint page.
    """
    lat, lng = _num(_kv(d, "Latitude")), _num(_kv(d, "Longitude"))
    geo = None
    if lat and lng and 15.5 <= lat <= 22.5 and 72.0 <= lng <= 81.0:
        geo = {"lat": round(lat, 6), "lng": round(lng, 6)}
    return {
        "rera_id": d.get("rera_id"),
        "project_name": d.get("project_name"),
        "promoter_name": d.get("promoter_name"),
        "source": "html",
        "capturedAt": (d.get("captured_at") or "")[:10],
        "geo": geo,
        "plot": {
            "cts": _kv(d, "Final Plot bearing", "CTS Number", "Survey"),
            "landArea": _num(_kv(d, "Total Land Area")),
            "builtUpArea": _num(_kv(d, "Permissible Built-up")),
            "village": _kv(d, "Village"),
            "taluka": _kv(d, "Taluka"),
            "district": _kv(d, "District"),
            "pincode": _kv(d, "Pin Code"),
            "boundaries": {side: _kv(d, "Boundaries " + side)
                           for side in ("North", "South", "East", "West")},
        },
        "litigationDeclared": _kv(d, "Is there any litigation"),
        "specs": {}, "timeline": [], "extensions": [], "buildings": [],
        "units": {"total": 0, "booked": 0, "mix": []},
        "litigation": None,
        "complaints": None,
        "projectComplaints": {"count": None, "rows": [], "orders": [],
                              "nonCompliance": [], "warrants": []},
        "documents": [], "document_count": 0,
    }


def _merge(api_rec: dict, html_rec: dict) -> dict:
    """API record wins (it is far richer); HTML fills in what only it knows."""
    out = dict(api_rec)
    out["source"] = "api+html"
    out["plot"] = html_rec.get("plot")
    out["litigationDeclared"] = html_rec.get("litigationDeclared")
    if not out.get("geo"):
        out["geo"] = html_rec.get("geo")
    return out


def build_parsed_snapshot(out_name: str | None = None) -> Path:
    """Merge EVERY raw capture dir into one parsed records.json. Returns its dir.

    This deliberately reads all capture dates and both capture formats rather than
    only the newest directory. Taking just the newest meant a fresh collector run
    silently replaced the live dataset — a run that captured 9 new projects would
    have dropped the 10 already published, and an HTML-only run would have emitted
    an empty file (it globbed *.api.json, which those captures do not produce).

    Per project the richest capture wins: the API record carries complaints,
    orders, litigation and documents; the HTML record contributes the plot's
    CTS/survey number, land area and boundaries, which the API does not expose.
    """
    raw_dirs = sorted(d for d in RAW_ROOT.glob("*") if d.is_dir() and d.name != ".assist")
    if not raw_dirs:
        raise SystemExit("No raw detail capture found.")

    # Hosting URLs written by collector.upload_docs live only in the parsed file.
    # Carry them across a rebuild, keyed by (rera_id, filename), so re-parsing does
    # not silently un-publish every document.
    prior: dict[tuple[str, str], str] = {}
    for pf in PARSED_ROOT.glob("*/records.json"):
        try:
            for rid, rec in json.loads(pf.read_text(encoding="utf-8")).items():
                for d in rec.get("documents", []):
                    if d.get("url") and d.get("file"):
                        prior[(rid, d["file"])] = d["url"]
        except (json.JSONDecodeError, AttributeError):
            continue

    api_recs: dict[str, dict] = {}
    html_recs: dict[str, dict] = {}

    for raw in raw_dirs:                      # oldest -> newest, newest wins
        # Document folders may be grouped by area (docs/<District>/<Village>/<RID>),
        # so locate them by scanning rather than assuming the flat docs/<RID>/ path.
        doc_dirs = {d.name: d for d in (raw / "docs").rglob("*")
                    if d.is_dir() and re.fullmatch(r"P\d{11}", d.name)}                    if (raw / "docs").is_dir() else {}
        for f in sorted(raw.glob("*.api.json")):
            try:
                api = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            # run_detail_assist writes a LIST of intercepted browser responses (it
            # carries the auth token, not a project record); only the dict form
            # written by fetch_detail_api is a parseable capture.
            if not isinstance(api, dict):
                continue
            rid = api.get("rera_id")
            if not rid:
                continue
            ddir = doc_dirs.get(rid)
            files = sorted(os.listdir(ddir)) if ddir and ddir.is_dir() else []
            if files:
                files = dedupe_files(ddir, files)
            rec = parse_record(api, files)
            rec["source"] = "api"
            rec["capturedAt"] = raw.name
            for d in rec["documents"]:
                url = prior.get((rid, d.get("file", "")))
                if url:
                    d["url"] = url
            api_recs[rid] = rec

        for f in sorted(raw.glob("*.json")):
            if f.name.endswith(".api.json") or f.name in ("snapshot.json", "api_snapshot.json"):
                continue
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if d.get("rera_id") and "key_values" in d:
                html_recs[d["rera_id"]] = parse_html_record(d)

    records: dict[str, dict] = {}
    for rid in sorted(set(api_recs) | set(html_recs)):
        a, h = api_recs.get(rid), html_recs.get(rid)
        records[rid] = _merge(a, h) if (a and h) else (a or h)

    out_dir = PARSED_ROOT / (out_name or raw_dirs[-1].name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


class DetailStore:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.captured_at = ""
        # Every capture date's docs/ directory. Documents accumulate across runs, so
        # a single directory would hide everything collected on other dates.
        self.docs_dirs: list[Path] = []
        self._doc_index: dict[str, list[Path]] = {}
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
        # Newest first, so a re-captured document resolves to the latest copy.
        self.docs_dirs = [p for p in
                          sorted((RAW_ROOT.glob("*/docs")), key=lambda x: x.parent.name, reverse=True)
                          if p.is_dir()]
        self._index_docs()
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
        return bool(self._doc_index or self.docs_dirs)

    def _index_docs(self) -> None:
        """Map rera_id -> EVERY directory holding its documents.

        Built by scanning rather than assuming docs/<RID>/, so the folders can be
        reorganised (e.g. grouped by district) without breaking document serving.
        A project can appear in several capture dates with different files in
        each — a backfill adds to one date, a re-capture to another — so all of
        its directories are kept, newest first.
        """
        idx: dict[str, list[Path]] = {}
        for root in self.docs_dirs:                    # already newest-first
            for p in root.rglob("*"):
                if p.is_dir() and re.fullmatch(r"P\d{11}", p.name):
                    idx.setdefault(p.name, []).append(p)
        self._doc_index = idx

    def doc_path(self, rera_id: str, filename: str) -> Path | None:
        """Locate a document for a project, whatever the folder layout."""
        for base in self._doc_index.get(rera_id, ()):
            p = (base / filename).resolve()
            # guard against path traversal
            if base.resolve() in p.parents and p.is_file():
                return p
        return None
