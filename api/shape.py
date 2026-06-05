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

from engine.verdict import build_verdict
from engine.reputation import ReputationStore

# Loaded once at import / startup. When a reputation snapshot exists, real projects get
# real green/amber/red scores; otherwise they honestly stay 'incomplete' (N/A).
REPUTATION = ReputationStore()


def load_reputation() -> bool:
    return REPUTATION.load_latest()

# Map our engine's signal kinds -> the design's kinds + icons.
_KIND = {"positive": "positive", "caution": "caution", "negative": "severe", "neutral": "neutral"}
_ICON = {
    "rera_registered": "shield-check",
    "revoked": "ban",
    "long_on_record": "calendar-clock",
    "recent_record": "calendar-check",
    "depth_pending": "hourglass",
}


def _as_of(row: dict) -> str:
    raw = (row.get("fetched_at") or "")[:10]
    return raw or date.today().isoformat()


def _score_to_band(v) -> tuple[str, float | None]:
    """Map the engine verdict to the UI band/score. 'incomplete' -> N/A."""
    if v.score is None or v.band == "incomplete":
        return "incomplete", None
    return v.band, round(v.score, 1)


def project_to_card(row: dict) -> dict:
    """The lightweight shape used by landing/results cards."""
    v = build_verdict(row, reputation=REPUTATION)
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
    v = build_verdict(row, reputation=REPUTATION)
    band, score = _score_to_band(v)
    complete = score is not None
    as_of = v.data_as_of or _as_of(row)

    # rough numeric impact for display (UI shows +/- chips): derive from engine points.
    signals = []
    for s in v.signals:
        s = s.to_dict()
        signals.append({
            "kind": _KIND.get(s["kind"], "neutral"),
            "impact": (s["points"] if complete and s["points"] != 0 else (0 if complete else None)),
            "icon": _ICON.get(s["key"], "file"),
            "fact": s["reason"].split(".")[0][:120],
            "detail": s["reason"],
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
    return card


def builder_stub(row: dict) -> dict:
    """Builder track record from captcha-free reputation data."""
    name = row.get("promoter_name") or "Unknown builder"
    if not REPUTATION.loaded:
        return {"name": name, "since": "—", "totalProjects": "—", "delivered": "—",
                "delayed": None, "revoked": 0, "others": [],
                "note": "Builder track record requires reputation data not yet ingested."}
    complaints = REPUTATION.complaints_for(name) or 0
    revoked = REPUTATION.revoked_count_for(name) or 0
    if complaints == 0 and revoked == 0:
        note = "No complaints or revoked registrations found against this builder on the MahaRERA record."
    else:
        bits = []
        if complaints: bits.append(f"{complaints} complaint(s)")
        if revoked: bits.append(f"{revoked} revoked registration(s)")
        note = "On the MahaRERA record, this builder has " + " and ".join(bits) + "."
    return {
        "name": name, "since": "—", "totalProjects": "—",
        "delivered": "—",
        "delayed": complaints if complaints else 0,
        "revoked": revoked,
        "note": note,
        "others": [],
    }
