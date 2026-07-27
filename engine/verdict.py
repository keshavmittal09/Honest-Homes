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
    title:    short headline for the signal row (a few words, no trailing period).
    reason:   plain-language fact, phrased as a fact not an accusation.
    source:   where it came from (e.g. 'MahaRERA project index').
    as_of:    the date the underlying data was captured.

    The UI shows `title` above `reason`. Deriving the title by chopping `reason`
    (as the front end used to) breaks on decimals and mid-word — hence an explicit
    field owned here, where the wording is written.
    """

    key: str
    points: int
    reason: str
    source: str
    as_of: str
    kind: str = "neutral"  # 'positive' | 'caution' | 'negative' | 'neutral'
    title: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "points": self.points,
            "title": self.title or self.reason.rstrip("."),
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
_SRC_PROJECT = "MahaRERA — this project's own complaint record"


def _project_signals(detail: dict, as_of: str) -> list[Signal]:
    """Signals from the project's OWN MahaRERA record (Tier-2 detail).

    A complaint against this project is far more relevant to a buyer than one
    against the builder's other projects, so these are scored separately and more
    heavily. Only emitted when we actually hold Tier-2 detail for the project —
    silence here means "not collected", never "clean", and the coverage signal
    says so explicitly.
    """
    out: list[Signal] = []
    pc = (detail or {}).get("projectComplaints") or {}
    n = pc.get("count")
    if n is None:
        return out

    warrants = len(pc.get("warrants") or [])
    orders = len(pc.get("orders") or [])
    noncomp = len(pc.get("nonCompliance") or [])

    if n == 0:
        out.append(Signal(
            key="project_no_complaints", points=1,
            title="No complaints against this project",
            reason=("No consumer complaints are recorded against this specific project on its "
                    "own MahaRERA page."),
            source=_SRC_PROJECT, as_of=as_of, kind="positive",
        ))
    else:
        pts = -2 if n == 1 else -3 if n <= 3 else -5
        bits = [f"{n} consumer complaint(s) filed against this project"]
        if orders:
            bits.append(f"{orders} order(s) issued")
        if noncomp:
            bits.append(f"{noncomp} non-compliance application(s)")
        out.append(Signal(
            key="project_complaints", points=pts,
            title=f"{n} complaint(s) against this project",
            reason=", ".join(bits) + " on the project's own MahaRERA record.",
            source=_SRC_PROJECT, as_of=as_of,
            kind="negative" if n > 1 else "caution",
        ))

    # A recovery warrant means an order went unpaid and MahaRERA moved to recover.
    if warrants:
        out.append(Signal(
            key="recovery_warrant", points=-3,
            title=f"{warrants} recovery warrant(s) issued",
            reason=("MahaRERA has issued recovery warrant(s) against this project, which follow "
                    "an order that was not complied with."),
            source=_SRC_PROJECT, as_of=as_of, kind="negative",
        ))

    lit = (detail or {}).get("litigation") or {}
    cases = lit.get("count") or 0
    if cases:
        courts = sorted({c.get("court") for c in (lit.get("cases") or []) if c.get("court")})
        where = f" ({', '.join(courts[:2]).title()})" if courts else ""
        out.append(Signal(
            key="project_litigation", points=-1,
            title=f"{cases} court case(s) declared on this project",
            reason=(f"The promoter has declared {cases} pending legal case(s) for this project"
                    f"{where} in its MahaRERA filing."),
            source=_SRC_PROJECT, as_of=as_of, kind="caution",
        ))
    return out


def build_verdict(project: dict, *, reputation=None, detail: dict | None = None,
                  today: date | None = None) -> Verdict:
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
            title="Registered with MahaRERA",
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
                title="Registration revoked",
                reason="This project's MahaRERA registration has been REVOKED / deregistered.",
                source=_SRC_REVOKED, as_of=rep_as_of, kind="negative",
            ))
        revoked_siblings = reputation.revoked_count_for(promoter) or 0
        if revoked_siblings and not reputation.is_revoked(rera_id, promoter):
            signals.append(Signal(
                key="revoked_siblings", points=-2,
                title=f"{revoked_siblings} other project(s) by this builder revoked",
                reason=(f"This builder has {revoked_siblings} other project(s) with revoked "
                        "registrations on record."),
                source=_SRC_REVOKED, as_of=rep_as_of, kind="caution",
            ))

        # --- Complaints against the promoter -----------------------------------
        # Normalise by the builder's project count: 9 complaints on a 1-project
        # builder is alarming; the same on an 80-project builder is ordinary. We
        # penalise on complaints-PER-PROJECT, with no upper cap so egregious
        # records keep scoring worse.
        # When we hold this project's OWN complaint record, the builder-wide count
        # becomes secondary evidence — the two overlap, and counting both at full
        # weight drove genuinely bad projects straight to the 0.0 floor, which
        # destroys the scale's ability to distinguish "bad" from "worst".
        has_project_record = (detail or {}).get("projectComplaints", {}).get("count") is not None

        complaints = reputation.complaints_for(promoter)
        if complaints and complaints > 0:
            n_proj = max(1, reputation.projects_for(promoter))
            ratio = complaints / n_proj
            # Per-project ratio -> penalty. Tunable thresholds; uncapped tail.
            if ratio < 0.25:
                pts, kind = -1, "caution"
            elif ratio < 0.75:
                pts, kind = -3, "negative"
            elif ratio < 1.5:
                pts, kind = -5, "negative"
            else:
                pts, kind = -7, "negative"  # >=1.5 complaints per project: severe
            proj_note = (f" across {n_proj} project(s) on record" if n_proj > 1
                         else " on its sole project on record")
            scaled = ""
            if has_project_record:
                # Halve, but never to zero: a complaint that exists must always cost
                # something, otherwise the score says "clean" while the band says
                # "caution" and the two contradict each other.
                pts = min(-1, -(-pts // 2))
                scaled = (" Counted at half weight here because this project's own complaint "
                          "record was checked directly and is scored separately.")
            signals.append(Signal(
                key="complaints", points=pts,
                title=(f"{complaints} consumer complaint(s) against this builder"),
                reason=(f"{complaints} consumer complaint(s) filed against this builder "
                        f"with MahaRERA{proj_note} "
                        f"(~{ratio:.1f} per project).{scaled}"),
                source=_SRC_COMPLAINTS, as_of=rep_as_of, kind=kind,
            ))
        else:
            # Absence of complaints is NOT proof of a clean builder — our complaint
            # register covers only a minority of promoters. Treat as neutral (0),
            # never a positive bonus, and say "on record" not "clean".
            signals.append(Signal(
                key="no_complaints", points=0,
                title="No complaints found on record",
                reason="No consumer complaints found on record against this builder in the MahaRERA register.",
                source=_SRC_COMPLAINTS, as_of=rep_as_of, kind="neutral",
            ))

        # --- Signals from the project's own record, when we hold Tier-2 detail ---
        signals.extend(_project_signals(detail, rep_as_of))

        # --- Honest coverage note. It MUST say whether the project's own record was
        # checked: without Tier-2 detail we cannot see project-level complaints, and
        # a quiet verdict would otherwise read as "clean" rather than "not checked".
        has_project_record = bool((detail or {}).get("projectComplaints", {}).get("count") is not None)
        signals.append(Signal(
            key="coverage", points=0,
            title="What this verdict covers",
            reason=(
                "Based on registration, complaint and revocation records, plus this project's "
                "own MahaRERA complaint and litigation record. Detailed delay/extension history "
                "is not yet included."
                if has_project_record else
                "Based on the builder's registration, complaint and revocation records. This "
                "project's own complaint and litigation page has NOT been checked yet, so "
                "project-specific complaints may exist that are not reflected here."
            ),
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
        title="Deeper records not yet ingested",
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

    # Revoked is always the top red flag, regardless of score.
    if any(s.key == "revoked" for s in signals):
        return BAND_RED, f"{name}'s MahaRERA registration has been revoked — treat with serious caution."

    comp = next((s for s in signals if s.key == "complaints"), None)
    revoked_sib = any(s.key == "revoked_siblings" for s in signals)
    proj = next((s for s in signals if s.key == "project_complaints"), None)
    warrant = any(s.key == "recovery_warrant" for s in signals)
    litig = next((s for s in signals if s.key == "project_litigation"), None)

    # A complaint against THIS project outranks anything about the builder — it is
    # the most directly relevant fact a buyer of this flat can be told.
    if warrant:
        return BAND_RED, (f"{name} has a MahaRERA recovery warrant against it — an order was "
                          "not complied with. Treat with serious caution.")
    if proj is not None and proj.points <= -4:
        return BAND_RED, (f"{name} has multiple consumer complaints on its own MahaRERA record "
                          "— look very closely before proceeding.")

    # GREEN is a positive claim, so it requires the ABSENCE of any negative signal
    # — not merely a high score from the registered baseline. A builder with
    # complaints or revoked siblings can never be green, even if the math is high.
    if score >= 7 and comp is None and not revoked_sib and proj is None and litig is None:
        return BAND_GREEN, (f"{name} is RERA-registered with no complaints or revocations "
                            "on the public MahaRERA record — but this is a baseline check, "
                            "not a full clearance.")

    # RED for serious complaint load or low score.
    if comp is not None and comp.points <= -5:
        return BAND_RED, (f"{builder} has a heavy complaint record on MahaRERA relative to its "
                          f"project count — look very closely before proceeding with {name}.")
    if score < 4:
        return BAND_RED, f"{name} has serious flags on the MahaRERA record — look closely before proceeding."

    # Everything else is AMBER (caution / incomplete picture).
    msg = f"{name} is registered"
    if proj is not None:
        msg += " but has complaints on its own record"
    elif litig is not None:
        msg += " but has a declared court case"
    elif comp is not None:
        msg += f", but {builder} has complaints on record"
    elif revoked_sib:
        msg += f", but {builder} has other revoked projects on record"
    return BAND_AMBER, msg + " — worth a closer look."
