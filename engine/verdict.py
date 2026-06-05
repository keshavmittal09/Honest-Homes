"""The honest verdict — transparent, rule-based, sourced.

DESIGN CONTRACT (do not violate):
  1. The score is DETERMINISTIC MATH from explicit signals. No AI decides the verdict.
  2. Every signal carries a human-readable reason AND its source label. The verdict can
     be defended line-by-line ("score is 6/10 because: registration valid +2, ...").
  3. We state facts, not accusations. A signal says "completion date revised twice
     (per MahaRERA, as of <date>)" — the BUYER concludes "risky". This is our liability
     shield and our integrity.

This v1 uses only the captcha-free signals we can collect today. Reputation signals
(complaints, orders, revocations) and Tier-2 delay signals plug in via the same
`Signal` shape later — the scoring loop does not need to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


# Verdict bands for the headline traffic-light.
BAND_GREEN = "green"     # looks clean on available records
BAND_AMBER = "amber"     # some caution flags / incomplete picture
BAND_RED = "red"         # serious flags on record
BAND_INCOMPLETE = "incomplete"  # not enough data to score honestly


@dataclass(slots=True)
class Signal:
    """One scored factor in the verdict.

    points:   contribution to the score (+ good, - bad), already weighted.
    reason:   plain-language fact, phrased as a fact not an accusation.
    source:   where it came from (e.g. 'MahaRERA project index').
    as_of:    the date the underlying data was captured.
    """

    key: str
    points: int
    reason: str
    source: str
    as_of: str
    kind: str = "neutral"  # 'positive' | 'caution' | 'negative' | 'neutral'

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "points": self.points,
            "reason": self.reason,
            "source": self.source,
            "as_of": self.as_of,
            "kind": self.kind,
        }


@dataclass(slots=True)
class Verdict:
    rera_id: str
    project_name: str
    promoter_name: str
    score: int                 # 0..10
    band: str
    headline: str
    signals: list[Signal] = field(default_factory=list)
    data_as_of: str = ""
    disclaimer: str = (
        "This summary is generated automatically from public MahaRERA records as of the "
        "date shown. It is informational only, not legal or financial advice, and may be "
        "incomplete or out of date. Always verify directly with MahaRERA before deciding."
    )

    def to_dict(self) -> dict:
        return {
            "rera_id": self.rera_id,
            "project_name": self.project_name,
            "promoter_name": self.promoter_name,
            "score": self.score,
            "band": self.band,
            "headline": self.headline,
            "signals": [s.to_dict() for s in self.signals],
            "data_as_of": self.data_as_of,
            "disclaimer": self.disclaimer,
        }


# Score starts here and signals move it. Clamped to [0, 10].
_BASE_SCORE = 6
_SRC_INDEX = "MahaRERA registered-projects list"


def _year_of(date_str: str) -> int | None:
    try:
        return int(date_str[:4])
    except (ValueError, TypeError):
        return None


_SRC_COMPLAINTS = "MahaRERA — promoter complaints register"
_SRC_REVOKED = "MahaRERA — deregistered/revoked list"


def build_verdict(project: dict, *, reputation=None, today: date | None = None) -> Verdict:
    """Build a verdict from one project index record, optionally enriched with the
    captcha-free reputation data (complaints + revoked status).

    Deterministic: same inputs -> same verdict. The score is transparent math from the
    signals below — never an opinion. When ``reputation`` is loaded we emit a REAL
    score; when it isn't, we honestly return an N/A (incomplete) verdict.
    """
    today = today or date.today()
    as_of = project.get("fetched_at", "")[:10] or today.isoformat()
    promoter = project.get("promoter_name", "")
    rera_id = project.get("rera_id", "")
    signals: list[Signal] = []

    # Baseline: registered.
    if rera_id:
        signals.append(Signal(
            key="rera_registered", points=2,
            reason=f"Project is RERA-registered (ID {rera_id}).",
            source=_SRC_INDEX, as_of=as_of, kind="positive",
        ))

    rep_loaded = reputation is not None and getattr(reputation, "loaded", False)
    rep_as_of = getattr(reputation, "captured_at", "") or as_of

    if rep_loaded:
        # --- Revoked status (the single biggest red flag) ----------------------
        if reputation.is_revoked(rera_id, promoter):
            signals.append(Signal(
                key="revoked", points=-8,
                reason="This project's MahaRERA registration has been REVOKED / deregistered.",
                source=_SRC_REVOKED, as_of=rep_as_of, kind="negative",
            ))
        revoked_siblings = reputation.revoked_count_for(promoter) or 0
        if revoked_siblings and not reputation.is_revoked(rera_id, promoter):
            signals.append(Signal(
                key="revoked_siblings", points=-2,
                reason=(f"This builder has {revoked_siblings} other project(s) with revoked "
                        "registrations on record."),
                source=_SRC_REVOKED, as_of=rep_as_of, kind="caution",
            ))

        # --- Complaints against the promoter -----------------------------------
        complaints = reputation.complaints_for(promoter)
        if complaints and complaints > 0:
            pts = -1 if complaints <= 2 else -3 if complaints <= 9 else -5
            kind = "caution" if complaints <= 2 else "negative"
            signals.append(Signal(
                key="complaints", points=pts,
                reason=(f"{complaints} consumer complaint(s) filed against this builder "
                        "with MahaRERA."),
                source=_SRC_COMPLAINTS, as_of=rep_as_of, kind=kind,
            ))
        else:
            signals.append(Signal(
                key="no_complaints", points=2,
                reason="No consumer complaints found against this builder in the MahaRERA register.",
                source=_SRC_COMPLAINTS, as_of=rep_as_of, kind="positive",
            ))

        # --- Honest coverage note (we have reputation, not yet delay history) ---
        signals.append(Signal(
            key="coverage", points=0,
            reason=("Based on registration, complaint and revocation records. Detailed "
                    "delay/extension history is not yet included."),
            source=_SRC_INDEX, as_of=rep_as_of, kind="neutral",
        ))

        score = max(0, min(10, _BASE_SCORE + sum(s.points for s in signals)))
        band, headline = _band_and_headline_scored(score, signals, project)
        return Verdict(rera_id=rera_id, project_name=project.get("project_name", ""),
                       promoter_name=promoter, score=score, band=band, headline=headline,
                       signals=signals, data_as_of=rep_as_of)

    # --- No reputation data loaded: honest N/A (incomplete) ---------------------
    signals.append(Signal(
        key="depth_pending", points=0,
        reason=("Detailed delay history, complaints and financials are not yet included in "
                "this summary. This is a preliminary check based on the public project list."),
        source=_SRC_INDEX, as_of=as_of, kind="neutral",
    ))
    return Verdict(rera_id=rera_id, project_name=project.get("project_name", ""),
                   promoter_name=promoter, score=None, band=BAND_INCOMPLETE,
                   headline=f"{project.get('project_name') or 'This project'} is RERA-registered; "
                            "full verdict pending reputation data.",
                   signals=signals, data_as_of=as_of)


def _band_and_headline_scored(score: int, signals: list[Signal], project: dict) -> tuple[str, str]:
    name = project.get("project_name") or "This project"
    builder = project.get("promoter_name") or "the builder"
    if any(s.key == "revoked" for s in signals):
        return BAND_RED, f"{name}'s MahaRERA registration has been revoked — treat with serious caution."
    comp = next((s for s in signals if s.key == "complaints"), None)
    if score >= 7:
        return BAND_GREEN, f"{name} looks clean on the public MahaRERA record — registered, no complaints found."
    if score >= 4:
        msg = f"{name} is registered"
        if comp:
            msg += f", but {builder} has complaints on record"
        return BAND_AMBER, msg + " — worth a closer look."
    return BAND_RED, f"{name} has serious flags on the MahaRERA record — look closely before proceeding."
