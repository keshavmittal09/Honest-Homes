"""Map our real index data + verdict engine into the Claude-design HH_DATA shape.

The design (web/*.jsx) expects each project to carry: band, score, name, builder,
district, locality, pincode, status, headline, summary, signals[], timeline[],
builderId, and a dataComplete flag. Our v1 only has captcha-free INDEX data (no
complaints/orders/timeline yet — that needs the reputation collector). So for real
projects we honestly map to the design's **incomplete** band, which the design was
purpose-built to render ("we won't fake a score we can't defend").

This keeps the UI truthful: real projects show "index data only" until the reputation
collector lands, at which point this mapper grows to emit green/amber/red verdicts.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from engine.verdict import build_verdict
from engine.reputation import ReputationStore
from engine.detail import DetailStore

# Loaded once at import / startup. When a reputation snapshot exists, real projects get
# real green/amber/red scores; otherwise they honestly stay 'incomplete' (N/A).
REPUTATION = ReputationStore()
# Tier-2 detail (timeline, specs, documents) for the projects we've enriched.
DETAIL = DetailStore()


def load_reputation() -> bool:
    return REPUTATION.load_latest()


def load_detail() -> bool:
    return DETAIL.load_latest()

# Map our engine's signal kinds -> the design's kinds + icons.
_KIND = {"positive": "positive", "caution": "caution", "negative": "severe", "neutral": "neutral"}
_ICON = {
    "rera_registered": "shield-check",
    "revoked": "ban",
    "revoked_siblings": "ban",
    "complaints": "file-warning",
    "no_complaints": "shield-check",
    "project_complaints": "file-warning",
    "project_no_complaints": "shield-check",
    "recovery_warrant": "gavel",
    "project_litigation": "scale",
    "coverage": "info",
    "long_on_record": "calendar-clock",
    "recent_record": "calendar-check",
    "depth_pending": "hourglass",
}


def _detail_for(row: dict) -> dict | None:
    """The Tier-2 record for this project, if we hold one."""
    return DETAIL.get(row.get("rera_id", "")) if DETAIL.loaded else None


def _as_of(row: dict) -> str:
    raw = (row.get("fetched_at") or "")[:10]
    return raw or date.today().isoformat()


def _doc_with_href(rera_id: str, doc: dict) -> dict:
    """Attach the href the browser should actually open, resolved server-side.

    Preference order:
      1. our own /api/hh/doc route, when the captured file ships with this app —
         always reachable, no third party involved;
      2. an external URL recorded at capture time (e.g. object storage);
      3. nothing — `href` is None and the UI renders the row as unopenable rather
         than as a link that 404s.
    """
    out = dict(doc)
    fname = doc.get("file") or ""
    if fname and DETAIL.loaded and DETAIL.doc_path(rera_id, fname) is not None:
        out["href"] = f"/api/hh/doc/{quote(rera_id)}/{quote(fname)}"
    elif DETAIL.external_ok:
        out["href"] = doc.get("url") or None
    else:
        out["href"] = None
    return out


def _score_to_band(v) -> tuple[str, float | None]:
    """Map the engine verdict to the UI band/score. 'incomplete' -> N/A."""
    if v.score is None or v.band == "incomplete":
        return "incomplete", None
    return v.band, round(v.score, 1)


def project_to_card(row: dict) -> dict:
    """The lightweight shape used by landing/results cards."""
    v = build_verdict(row, reputation=REPUTATION, detail=_detail_for(row))
    band, score = _score_to_band(v)
    return {
        "id": row.get("rera_id", ""),
        "band": band,
        "score": score,
        "name": row.get("project_name") or "(unnamed project)",
        "builder": row.get("promoter_name") or "—",
        "builderId": (row.get("promoter_name") or "unknown"),
        "district": row.get("district") or "—",
        "locality": row.get("district") or "",
        "pincode": row.get("pincode") or "",
        "status": "Registered",
    }


def project_to_full(row: dict) -> dict:
    """The rich shape used by the Verdict screen."""
    v = build_verdict(row, reputation=REPUTATION, detail=_detail_for(row))
    band, score = _score_to_band(v)
    complete = score is not None
    as_of = v.data_as_of or _as_of(row)

    # rough numeric impact for display (UI shows +/- chips): derive from engine points.
    signals = []
    for s in v.signals:
        s = s.to_dict()
        fact = s["title"]
        # Don't print the same sentence twice: when the long form only restates the
        # title, the row shows just the title.
        detail = "" if s["reason"].rstrip(".").strip() == fact.rstrip(".").strip() else s["reason"]
        signals.append({
            "kind": _KIND.get(s["kind"], "neutral"),
            "impact": (s["points"] if complete and s["points"] != 0 else (0 if complete else None)),
            "icon": _ICON.get(s["key"], "file"),
            "fact": fact,
            "detail": detail,
            "source": s["source"],
            "asOf": s["as_of"],
        })

    last_mod = row.get("last_modified", "")
    timeline = [{"label": "On RERA record", "date": last_mod[:7] or "—", "type": "start"}]

    # pull complaint/revoked counts for the record-snapshot section
    complaints = REPUTATION.complaints_for(row.get("promoter_name", "")) if REPUTATION.loaded else None
    revoked = REPUTATION.is_revoked(row.get("rera_id", ""), row.get("promoter_name", "")) if REPUTATION.loaded else False

    card = project_to_card(row)
    card.update({
        "statusNote": "Revoked" if revoked else ("Registered" if complete else "Index data only"),
        "registered": last_mod,
        "lastModified": last_mod,
        "promisedCompletion": "—",
        "revisedCompletion": None,
        "actualCompletion": None,
        "extensions": None,
        "complaints": complaints,
        "orders": None,
        "headline": v.headline,
        "summary": (
            "This verdict is based on the official MahaRERA registration, complaint and "
            "revocation records. Detailed delay/extension history is not yet included — "
            "verify timelines on the MahaRERA portal before relying on this."
        ) if complete else (
            "Only preliminary index data is available for this project. We confirm it "
            "appears in the official MahaRERA project index. Verify complaints, orders "
            "and delay history directly on the MahaRERA portal before relying on this."
        ),
        "signals": signals,
        "timeline": timeline,
        "mapUrl": row.get("map_url", ""),
        "detailUrl": row.get("detail_url", ""),
        "dataComplete": complete,
        "dataAsOf": as_of,
    })

    # --- Merge Tier-2 detail (timeline, specs, documents) when we have it ---
    det = DETAIL.get(row.get("rera_id", "")) if DETAIL.loaded else None
    if det:
        sp = det.get("specs", {})
        exts = det.get("extensions", [])
        if det.get("timeline"):
            card["timeline"] = det["timeline"]
        card["promisedCompletion"] = sp.get("originalCompletion") or "—"
        card["revisedCompletion"] = sp.get("revisedCompletion")
        card["extensions"] = len(exts)
        card["units"] = sp.get("unitsTotal")
        card["statusNote"] = sp.get("status") or card["statusNote"]
        # Plot identity (CTS/survey number, land area, boundaries) only exists in the
        # HTML capture; it is what a DP-remarks lookup is keyed on.
        card["plot"] = det.get("plot")
        rid = row.get("rera_id", "")
        docs = [_doc_with_href(rid, o) for o in det.get("documents", [])]
        # An HTML-only capture has no specs, units or documents — flagging it as
        # "hasDetail" would render a Project snapshot of nothing but em-dashes.
        card["hasDetail"] = bool(sp) or bool(det.get("documents"))
        card["detail"] = {
            "specs": sp,
            "extensions": exts,
            "buildings": det.get("buildings", []),
            "units": det.get("units", {}),
            "litigation": det.get("litigation"),
            "documents": docs,
            "documentCount": det.get("document_count", 0),
            "documentsAvailable": any(o.get("href") for o in docs),
            "capturedAt": DETAIL.captured_at,
            "projectComplaints": det.get("projectComplaints") or {},
            "geo": det.get("geo"),
        }
        # Project-level counts override the builder-level placeholders, because
        # they answer the question the buyer actually asked.
        pc = det.get("projectComplaints") or {}
        card["projectComplaints"] = pc.get("count")
        card["orders"] = len(pc.get("orders") or []) if pc.get("count") is not None else None
        card["courtCases"] = (det.get("litigation") or {}).get("count")
    else:
        card["hasDetail"] = False

    return card


def builder_stub(row: dict) -> dict:
    """Builder track record from captcha-free reputation data.

    Only reports numbers we can actually source. We do NOT know how many projects a
    builder has delivered or delayed — the index has no completion field — so those
    are reported as unknown rather than inferred. (An earlier version showed the
    complaint count under a 'Delayed' heading, which stated something the record
    does not say.)
    """
    name = row.get("promoter_name") or "Unknown builder"
    if not REPUTATION.loaded:
        return {"name": name, "since": "—", "totalProjects": None,
                "complaints": None, "revoked": None, "others": [],
                "note": "Builder track record requires reputation data not yet ingested."}

    complaints = REPUTATION.complaints_for(name) or 0
    revoked = REPUTATION.revoked_count_for(name) or 0
    total = REPUTATION.projects_for(name) or 0

    scope = f"across its {total} project(s) in the MahaRERA index" if total else "on the MahaRERA record"
    caveat = ("Delivery and delay history is not part of the public index, so this is not a "
              "completion track record.")
    if complaints == 0 and revoked == 0:
        note = (f"No consumer complaints or revoked registrations found against this builder "
                f"{scope}. {caveat}")
    else:
        bits = []
        if complaints:
            bits.append(f"{complaints} consumer complaint(s)")
        if revoked:
            bits.append(f"{revoked} revoked registration(s)")
        note = (f"This builder has " + " and ".join(bits) + f" on record {scope}. {caveat}")
    return {
        "name": name,
        "since": "—",
        "totalProjects": total or None,
        "complaints": complaints,
        "revoked": revoked,
        "note": note,
        "others": [],
    }
