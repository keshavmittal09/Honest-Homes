"""Honest Homes scoring v2 — separate project and builder scores, plus confidence.

The rules that matter most, and why:

* **Direction decides everything.** A promoter pursuing a defaulting allottee is
  ordinary commercial recovery, not a consumer-protection signal. v1 charged its
  largest penalty for exactly that on 10 projects. Only buyer -> promoter
  complaints are scored adversely here; the reverse is credited, because a
  builder that enforces through the regulator is not one applying private
  pressure. The credit is capped so it cannot cancel genuine grievances.
* **Registration is not evidence.** Every project in the index is registered, so
  awarding +2 for it discriminated between nothing and merely inflated the base.
* **The two scores partition the evidence.** A project's own complaints are a
  subset of its builder's, so the builder signal is computed on the remainder --
  the same grievance is never charged twice.
* **Missing data is not clean data.** Anything we cannot see reduces confidence
  rather than quietly scoring well, and below a floor we publish a band only.
* **Nothing is asserted that the record does not say.** Every finding carries its
  source and, where it should prompt one, a question to put to the seller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

LDQ, RDQ = "“", "”"

# Bands are on the 0-100 project scale.
BANDS = [
    (80, "clear", "Clear", "Nothing adverse on the public record"),
    (60, "reasonable", "Reasonable", "Minor items, normal for the cohort"),
    (40, "watch", "Watch", "Specific issues worth asking about"),
    (20, "serious", "Serious flags", "Material adverse record"),
    (0, "severe", "Severe", "Revocation, suspension or sustained non-compliance"),
]

# Legal severity ladder, applied to buyer -> promoter complaints only.
# A complaint the promoter filed is credited instead, via PROMOTER_CREDIT.
SEVERITY = {
    "buyer_pending": 1.0,
    "buyer_order": 2.5,
    "non_compliance": 4.0,
    "warrant": 6.0,
    # Neither of the two below is reachable today, and both are kept deliberately:
    #   suspension  - MahaRERA does not publish s.7 suspensions in any feed we
    #                 collect, so nothing can set it. It is here so the ladder is
    #                 complete when that source lands.
    #   revocation  - handled as a hard cap in score_project, not as a decaying
    #                 event, because a revoked registration is a present-tense
    #                 fact about whether the project may legally be sold at all.
    "suspension": 8.0,
    "revocation": 10.0,
}

# Credit for a complaint the promoter itself filed. Enforcing a contract through
# the regulator is the lawful route, and carrying it to an order means it was
# seen through — so a resolved one earns double a pending one. `cap` keeps the
# credit from cancelling genuine consumer grievances in the same category.
PROMOTER_CREDIT = {"resolved": 1.0, "pending": 0.5, "cap": 5.0}

HALF_LIFE_YEARS = 3.0
CONFIDENCE_FLOOR = 0.60        # below this we publish a band, not a number

# Inputs MahaRERA publishes that we do not yet parse. Each costs confidence
# wherever it applies, so a gap can never read as a clean record.
UNPARSED_PENALTY = {"qpr": 0.10, "form3": 0.05}


@dataclass
class Finding:
    """One scored observation, always traceable to the record."""
    text: str
    impact: float = 0.0
    kind: str = "neutral"      # positive | caution | negative | neutral
    source: str = ""
    question: str = ""         # what the buyer should ask the seller
    benchmark: str = ""        # the counterfactual, e.g. cohort median


@dataclass
class Category:
    key: str
    label: str
    weight: int
    earned: float
    covered: bool              # did we have usable data for this category?
    findings: list = field(default_factory=list)
    note: str = ""

    @property
    def pct(self) -> float:
        return 0.0 if not self.weight else max(0.0, min(1.0, self.earned / self.weight))


@dataclass
class Score:
    total: float
    band: str
    band_label: str
    band_note: str
    confidence: float
    categories: list
    capped_by: str = ""

    @property
    def publishable(self) -> bool:
        """Below the floor the number would imply precision we do not have."""
        return self.confidence >= CONFIDENCE_FLOOR

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 1),
            "band": self.band,
            "bandLabel": self.band_label,
            "bandNote": self.band_note,
            "confidence": round(self.confidence, 2),
            "publishable": self.publishable,
            "cappedBy": self.capped_by or None,
            "categories": [{
                "key": c.key, "label": c.label, "weight": c.weight,
                "earned": round(c.earned, 1), "pct": round(c.pct, 3),
                "covered": c.covered, "note": c.note,
                "findings": [{
                    "text": f.text, "impact": round(f.impact, 1), "kind": f.kind,
                    "source": f.source, "question": f.question, "benchmark": f.benchmark,
                } for f in c.findings],
            } for c in self.categories],
        }


def _band(total: float, blocked: bool = False):
    """Map a score to a band.

    `blocked` enforces the top band's own wording. "Clear" claims nothing
    adverse is on the public record, so a project carrying a consumer
    complaint, a lapse or a revocation cannot be labelled Clear however old
    and well-decayed the event is -- the number may be high, but the sentence
    would be untrue. The score itself is never altered.
    """
    for cut, key, label, note in BANDS:
        if total >= cut:
            if blocked and key == "clear":
                continue
            return key, label, note
    b = BANDS[-1]
    return b[1], b[2], b[3]


def _year(d):
    try:
        return int(str(d)[:4])
    except (TypeError, ValueError):
        return None


def _years_since(d, today: date):
    y = _year(d)
    if y is None or not (1990 <= y <= today.year + 40):
        return None
    try:
        m = int(str(d)[5:7]) or 1
    except (TypeError, ValueError):
        m = 1
    return (today.year - y) + (today.month - m) / 12.0


def _decay(weight: float, years, cured: bool) -> float:
    """Old events say less than recent ones; cured ones fade twice as fast."""
    if years is None or years <= 0:
        return weight
    hl = HALF_LIFE_YEARS / 2 if cured else HALF_LIFE_YEARS
    return weight * (0.5 ** (years / hl))


def _has_doc(detail: dict, *needles: str) -> bool:
    """Match on category and label. `kind` is unreliable on its own — for an
    unlabelled file it is a slice of the GUID filename, which matches nothing
    useful — so all three fields are searched together."""
    want = tuple(n.lower() for n in needles)
    for d in detail.get("documents") or []:
        hay = " ".join(str(d.get(k) or "") for k in ("category", "label", "kind")).lower()
        if any(w in hay for w in want):
            return True
    return False


# --------------------------------------------------------------------------
# Project score
# --------------------------------------------------------------------------

def _delivery(detail: dict, today: date) -> Category:
    """Delivery & timeline — 30.

    MahaRERA never marks a project 'Completed' in this feed (672 Ongoing / 30
    New across the index), so completion cannot be read off the status field.
    Extensions, a lapsed registration and an overdue committed date are the
    signals that actually vary.
    """
    sp = detail.get("specs") or {}
    exts = detail.get("extensions") or []
    f, earned = [], 30.0
    covered = bool(sp)

    n = len(exts)
    if n == 0:
        f.append(Finding("No completion-date extensions filed", 0, "positive",
                         "MahaRERA — extension certificates",
                         benchmark="67% of projects on record have filed none"))
    else:
        pen = min(20.0, 6.0 + 4.5 * (n - 1))   # a pattern costs more than one slip
        earned -= pen
        plural = "" if n == 1 else "s"
        f.append(Finding(
            "Completion date revised %d time%s" % (n, plural),
            -pen, "negative" if n > 1 else "caution",
            "MahaRERA — extension certificates",
            question="The completion date has been revised %d time%s. What is the current "
                     "committed handover date, and what is the remedy if it slips again?"
                     % (n, plural),
            benchmark="67% of projects on record have filed none"))
        last = exts[-1] or {}
        if last.get("reason"):
            f.append(Finding(
                "Latest stated reason: %s%s%s" % (LDQ, str(last["reason"])[:130], RDQ),
                0, "neutral", "MahaRERA — extension certificate"))

    if sp.get("lapsed"):
        # A lapsed registration means the promoter may not legally market or sell
        # the project. It is the single most actionable thing a buyer can check.
        earned -= 20.0
        f.append(Finding(
            "Registration has LAPSED on the MahaRERA record", -20, "negative",
            "MahaRERA — project registration",
            question="Your MahaRERA registration shows as lapsed. Has it been renewed, "
                     "and can you show the current validity certificate?",
            benchmark="14% of projects on record are lapsed"))

    target = (sp.get("revisedCompletion") or sp.get("originalCompletion")
              or sp.get("proposedCompletion"))
    ys = _years_since(target, today)
    if ys is not None and ys > 0:
        months = int(ys * 12)
        if months > 6:
            pen = min(12.0, 2.2 * math.log2(1 + months / 6.0))
            earned -= pen
            f.append(Finding(
                "Committed completion date (%s) passed %d months ago" % (target, months),
                -pen, "negative", "MahaRERA — registration record",
                question="The filing commits to %s, which was %d months ago. What is the "
                         "present status on site, and has possession been offered?"
                         % (target, months)))

    if _has_doc(detail, "occupancy certificate", "completion certificate"):
        f.append(Finding("Occupancy / completion certificate on the public record",
                         0, "positive", "MahaRERA — uploaded documents"))

    return Category("delivery", "Delivery & timeline", 30, max(0.0, earned), covered, f)


def _legal(detail: dict, today: date, revoked: bool):
    """Legal & regulatory standing — 25. Direction-aware, severity-weighted, decayed."""
    pc = detail.get("projectComplaints") or {}
    cs = pc.get("complaints") or []
    lit = detail.get("litigation") or {}
    f, earned = [], 25.0
    covered = pc.get("count") is not None
    hard_cap = False

    if revoked:
        f.append(Finding(
            "MahaRERA registration REVOKED / deregistered", -25, "negative",
            "MahaRERA — deregistered projects list",
            question="The registration appears revoked. On what basis are units still "
                     "being offered, and what is the position of buyers who have paid?"))
        return Category("legal", "Legal & regulatory standing", 25, 0.0, covered, f), True

    buyer = [c for c in cs if c.get("direction") == "buyer_vs_builder"]
    promoter = [c for c in cs if c.get("direction") == "builder_vs_buyer"]
    unclear = [c for c in cs
               if c.get("direction") not in ("buyer_vs_builder", "builder_vs_buyer")]

    load, warrants, ncs = 0.0, 0, 0
    for c in buyer:
        yrs = _years_since(c.get("filedOn"), today)
        cured = bool(c.get("resolved"))
        if c.get("warrant"):
            load += _decay(SEVERITY["warrant"], yrs, False)
            warrants += 1
        elif c.get("nonCompliance"):    # a list; non-empty means an application exists
            load += _decay(SEVERITY["non_compliance"], yrs, False)
            ncs += 1
        elif c.get("order"):
            load += _decay(SEVERITY["buyer_order"], yrs, cured)
        else:
            load += _decay(SEVERITY["buyer_pending"], yrs, cured)

    if buyer:
        pen = min(22.0, 5.5 * math.log2(1 + load))  # sublinear: ten is not ten times one
        earned -= pen
        unres = sum(1 for c in buyer if c.get("resolved") is False)
        bits = ["%d consumer complaint%s against this project"
                % (len(buyer), "" if len(buyer) == 1 else "s")]
        if unres:
            bits.append("%d still unresolved" % unres)
        if warrants:
            bits.append("%d recovery warrant%s issued" % (warrants, "" if warrants == 1 else "s"))
        elif ncs:
            bits.append("%d non-compliance application%s" % (ncs, "" if ncs == 1 else "s"))
        f.append(Finding(
            ", ".join(bits), -pen, "negative" if (unres or warrants) else "caution",
            "MahaRERA — this project's complaint record",
            question="Can you share MahaRERA's orders on the complaints against this "
                     "project, and confirm what was done to comply with each?",
            benchmark="the median project on record has none"))
    elif covered:
        f.append(Finding("No consumer complaints filed against this project", 0, "positive",
                         "MahaRERA — this project's complaint record"))

    if promoter:
        # A promoter that pursues a defaulting allottee through MahaRERA is using
        # the statutory process rather than private pressure, and one that carried
        # it through to an order saw it finished. Credited — but capped, so a
        # builder cannot offset real consumer grievances by suing enough of its
        # own buyers, and never above the category weight.
        credit = min(PROMOTER_CREDIT["cap"], sum(
            PROMOTER_CREDIT["resolved"] if c.get("resolved") else PROMOTER_CREDIT["pending"]
            for c in promoter))
        earned += credit
        won = sum(1 for c in promoter if c.get("resolved"))
        f.append(Finding(
            "%d complaint%s filed BY the builder against buyers%s — recovery pursued "
            "through the regulator, not a grievance about this project"
            % (len(promoter), "" if len(promoter) == 1 else "s",
               (", %d resolved by order" % won) if won else ""),
            credit, "positive", "MahaRERA — this project's complaint record",
            question="These are the builder's own recovery actions against purchasers, "
                     "not grievances about the project. What payment terms triggered "
                     "them, and could the same terms apply to me?",
            benchmark="credited +%.1f resolved / +%.1f pending, capped at +%.0f"
                      % (PROMOTER_CREDIT["resolved"], PROMOTER_CREDIT["pending"],
                         PROMOTER_CREDIT["cap"])))

    if unclear:
        f.append(Finding(
            "%d complaint%s whose parties we could not classify — excluded from scoring"
            % (len(unclear), "" if len(unclear) == 1 else "s"),
            0, "neutral", "MahaRERA — this project's complaint record"))

    cases = lit.get("count") or 0
    if cases:
        # Penalised lightly and flagged: punishing a voluntary disclosure hard
        # would reward the promoters who declare least.
        pen = min(4.0, 1.0 + 0.5 * (cases - 1))
        earned -= pen
        rows = lit.get("cases") or []
        courts = sorted({str(c.get("court")).title() for c in rows if c.get("court")})
        first = (rows[0] or {}).get("caseNo") if rows else None
        f.append(Finding(
            "%d court case%s declared by the promoter%s"
            % (cases, "" if cases == 1 else "s",
               (" (%s)" % ", ".join(courts[:2])) if courts else ""),
            -pen, "caution", "MahaRERA — promoter's own declaration",
            question="Your filing declares %s — is it on this land or these units, "
                     "and has it been resolved?"
                     % ("case " + str(first) if first else "litigation"),
            benchmark="declared voluntarily; subject matter not yet classified"))

    return Category("legal", "Legal & regulatory standing", 25,
                    max(0.0, min(25.0, earned)), covered, f), hard_cap


def _disclosure(detail: dict) -> Category:
    """Disclosure & compliance hygiene — 20. QPR history is not collected yet."""
    f, earned = [], 20.0
    covered = bool(detail.get("document_count"))

    key_docs = [
        ("Commencement Certificate", ("commencement",)),
        ("Building approval / IOD", ("building approval", "iod", "building plan")),
        ("Title & Search Report", ("title",)),
        ("Agreement for Sale", ("agreement for sale", "draft agreement")),
    ]
    missing = [label for label, needles in key_docs if not _has_doc(detail, *needles)]
    if missing:
        pen = min(6.0, 1.5 * len(missing))
        earned -= pen
        f.append(Finding(
            "Not on the public record: " + ", ".join(missing), -pen, "caution",
            "MahaRERA — uploaded documents",
            question="These are not on your MahaRERA page: " + ", ".join(missing)
                     + ". Can you provide them?"))
    else:
        f.append(Finding("All key approval and title documents on record", 0, "positive",
                         "MahaRERA — uploaded documents"))

    forms = [n for n in ("Form 1", "Form 2", "Form 3") if _has_doc(detail, n.lower())]
    if len(forms) == 3:
        f.append(Finding("Full professional certificate set on record (Form 1, 2 and 3)",
                         0, "positive", "MahaRERA — uploaded documents"))
    elif forms:
        earned -= 2.0
        f.append(Finding(
            "Only %s on record of the three required certificates" % ", ".join(forms),
            -2, "caution", "MahaRERA — uploaded documents",
            question="Form 1 (architect), 2 (engineer) and 3 (CA) certify progress and "
                     "spending. Which are current, and can we see them?"))
    else:
        earned -= 4.0
        f.append(Finding("No architect, engineer or CA certificates on record", -4, "caution",
                         "MahaRERA — uploaded documents",
                         question="Form 1, 2 and 3 certificates are not on the record. "
                                  "Can you provide the current set?"))

    # QPR is the strongest hygiene signal and we do not hold it yet: name the gap
    # and let confidence carry it, rather than scoring the absence as clean.
    return Category("disclosure", "Disclosure & compliance hygiene", 20,
                    max(0.0, earned), covered, f,
                    note="Quarterly progress-report filing history not yet collected")


def _financial(detail: dict) -> Category:
    """Financial & construction viability — 15. Form 3 figures are not parsed yet."""
    units = detail.get("units") or {}
    sp = detail.get("specs") or {}
    total = units.get("total") or sp.get("unitsTotal") or 0
    booked = units.get("booked")
    if booked is None:
        booked = sp.get("unitsSold")
    f, earned = [], 15.0
    covered = bool(total)

    if total and booked is not None:
        pct = 100.0 * booked / total
        if pct >= 85:
            f.append(Finding("%d of %d units booked (%.0f%%)" % (booked, total, pct),
                             0, "positive", "MahaRERA — building and unit summary"))
        elif pct >= 40:
            f.append(Finding("%d of %d units booked (%.0f%%)" % (booked, total, pct),
                             0, "neutral", "MahaRERA — building and unit summary"))
        else:
            earned -= 3.0
            f.append(Finding(
                "Only %d of %d units booked (%.0f%%)" % (booked, total, pct),
                -3, "caution", "MahaRERA — building and unit summary",
                question="Bookings stand at %.0f%%. How is construction being funded at "
                         "this level of collection?" % pct))
    elif total:
        f.append(Finding("%d units registered; bookings not stated" % total, 0, "neutral",
                         "MahaRERA — building and unit summary"))

    return Category("financial", "Financial & construction viability", 15,
                    max(0.0, earned), covered, f,
                    note="Form 3 cost-incurred vs amount-collected not yet parsed")


def _land(detail: dict) -> Category:
    """Land & title clarity — 10."""
    f, earned = [], 10.0
    plot = detail.get("plot") or {}
    covered = bool(plot or detail.get("documents"))

    if _has_doc(detail, "title"):
        f.append(Finding("Title & Search Report on file", 0, "positive",
                         "MahaRERA — uploaded documents"))
    else:
        earned -= 4.0
        f.append(Finding(
            "No Title & Search Report on the public record", -4, "caution",
            "MahaRERA — uploaded documents",
            question="Is there a title and search report for this land, and can we see "
                     "it along with the advocate's opinion?"))

    if plot.get("cts"):
        f.append(Finding("Land identified as CTS / Survey %s" % plot["cts"], 0, "neutral",
                         "MahaRERA — land details"))

    return Category("land", "Land & title clarity", 10, max(0.0, earned), covered, f,
                    note="Declared litigation not yet classified by subject matter")


def score_project(detail: dict, *, revoked: bool = False, today=None) -> Score:
    """Score one project out of 100, with a confidence figure.

    Categories with no usable data are excluded from the denominator rather than
    counted as full marks, so an absent record can never inflate the result --
    it only lowers confidence.
    """
    today = today or date.today()
    legal, hard_cap = _legal(detail, today, revoked)
    cats = [_delivery(detail, today), legal, _disclosure(detail),
            _financial(detail), _land(detail)]

    scored_weight = sum(c.weight for c in cats if c.covered)
    total = 100.0 * sum(c.earned for c in cats if c.covered) / scored_weight if scored_weight else 0.0

    confidence = scored_weight / 100.0 - sum(UNPARSED_PENALTY.values())
    confidence = max(0.0, min(1.0, confidence))

    if hard_cap:
        total = min(total, 15.0)

    # Facts that contradict the top band's wording. Extensions and declared
    # litigation are deliberately not here: one extension is unremarkable, and
    # declared litigation is a voluntary disclosure we would rather encourage.
    sp = detail.get("specs") or {}
    cs = (detail.get("projectComplaints") or {}).get("complaints") or []
    blocked = (revoked or bool(sp.get("lapsed"))
               or any(c.get("direction") == "buyer_vs_builder" for c in cs))

    band, label, note = _band(total, blocked)
    return Score(total, band, label, note, confidence, cats,
                 capped_by="revocation" if hard_cap else "")


# --------------------------------------------------------------------------
# Builder score
# --------------------------------------------------------------------------

def score_builder(promoter: str, *, portfolio: list, reputation=None,
                  exclude_complaints: int = 0, today=None) -> Score:
    """Score a builder out of 100.

    Evidence is partitioned with the project score: `exclude_complaints` is the
    count already charged against the project being viewed, so the same
    grievance is never counted twice across the two numbers.
    """
    today = today or date.today()
    portfolio = portfolio or []
    n_projects = len(portfolio)
    rep_ok = reputation is not None and getattr(reputation, "loaded", True)

    def _rep(method, default=0):
        fn = getattr(reputation, method, None) if rep_ok else None
        try:
            return fn(promoter) if fn else default
        except Exception:
            return default

    # --- delivery track record (35)
    f1, e1 = [], 35.0
    cov1 = bool(portfolio)
    if portfolio:
        lapsed = sum(1 for r in portfolio if (r.get("specs") or {}).get("lapsed"))
        exts = [len(r.get("extensions") or []) for r in portfolio]
        avg_ext = sum(exts) / len(exts)
        if lapsed:
            pen = min(14.0, 14.0 * lapsed / max(1, n_projects))
            e1 -= pen
            f1.append(Finding(
                "%d of %d project%s carry a lapsed registration"
                % (lapsed, n_projects, "" if n_projects == 1 else "s"),
                -pen, "negative", "MahaRERA — project registrations",
                benchmark="14% of all projects on record are lapsed"))
        if avg_ext > 0.6:
            pen = min(10.0, 6.0 * avg_ext)
            e1 -= pen
            f1.append(Finding(
                "Averages %.1f completion-date extensions per project" % avg_ext,
                -pen, "caution", "MahaRERA — extension certificates",
                benchmark="0.6 across all builders on record"))
        elif avg_ext == 0:
            f1.append(Finding("No completion-date extensions anywhere in the portfolio",
                              0, "positive", "MahaRERA — extension certificates"))
    cat1 = Category("track", "Delivery track record", 35, max(0.0, e1), cov1, f1,
                    note="Completion inferred from extensions and lapse — MahaRERA "
                         "publishes no delivered flag")

    # --- complaint intensity (25), normalised per 1,000 sold units per year
    f2, e2 = [], 25.0
    cov2 = rep_ok
    if cov2:
        total_c = _rep("complaints_for") or 0
        # The promoter-complaints register is a raw head-count with no direction,
        # so it also contains complaints the builder filed against its own
        # defaulting buyers. Those are not consumer grievances — _legal credits
        # them — so deduct every one we can see in the portfolio we hold.
        # Projects we have no detail for stay unknown, which is what coverage
        # is for; this corrects what we can see rather than guessing the rest.
        promoter_filed = sum(
            1 for r in portfolio
            for c in ((r.get("projectComplaints") or {}).get("complaints") or [])
            if c.get("direction") == "builder_vs_buyer")
        others = max(0, total_c - max(0, exclude_complaints) - promoter_filed)
        if promoter_filed:
            f2.append(Finding(
                "%d complaint%s in the register were filed BY this builder against "
                "buyers — deducted, not charged against it"
                % (promoter_filed, "" if promoter_filed == 1 else "s"),
                0, "neutral", "MahaRERA — promoter complaints register"))
        sold = sum((r.get("units") or {}).get("booked") or 0 for r in portfolio)
        ages = [_years_since((r.get("specs") or {}).get("registeredOn"), today)
                for r in portfolio]
        ages = [a for a in ages if a and a > 0]
        age = (sum(ages) / len(ages)) if ages else None
        if others and sold and age:
            rate = others / (sold / 1000.0) / age
            pen = min(18.0, 4.0 * math.log2(1 + rate))
            e2 -= pen
            f2.append(Finding(
                "%d further complaint%s across this builder's other projects "
                "(%.1f per 1,000 sold units per year)"
                % (others, "" if others == 1 else "s", rate),
                -pen, "caution", "MahaRERA — promoter complaints register",
                benchmark="rate-normalised, so a large portfolio is not punished for size"))
        elif others:
            pen = min(12.0, 2.0 * math.log2(1 + others))
            e2 -= pen
            f2.append(Finding(
                "%d further complaint%s across this builder's other projects"
                % (others, "" if others == 1 else "s"),
                -pen, "caution", "MahaRERA — promoter complaints register"))
        else:
            f2.append(Finding("No other complaints against this builder on record",
                              0, "positive", "MahaRERA — promoter complaints register"))
    cat2 = Category("intensity", "Complaint intensity", 25, max(0.0, e2), cov2, f2)

    # --- regulatory penalties (20)
    f3, e3 = [], 20.0
    cov3 = rep_ok
    if cov3:
        rev = _rep("revoked_count_for") or 0
        if rev:
            pen = min(20.0, 8.0 + 4.0 * (rev - 1))
            e3 -= pen
            f3.append(Finding(
                "%d project registration%s revoked by MahaRERA"
                % (rev, "" if rev == 1 else "s"),
                -pen, "negative", "MahaRERA — deregistered projects list",
                question="MahaRERA has revoked registrations on other projects by this "
                         "promoter. What happened there, and what changed since?"))
        else:
            f3.append(Finding("No revoked registrations on record", 0, "positive",
                              "MahaRERA — deregistered projects list"))
    cat3 = Category("penalties", "Regulatory penalties", 20, max(0.0, e3), cov3, f3)

    # --- scale & continuity (10)
    f4, e4 = [], 10.0
    cov4 = bool(portfolio)
    if portfolio:
        years = [_year((r.get("specs") or {}).get("registeredOn")) for r in portfolio]
        years = [y for y in years if y]
        first = min(years) if years else None
        if first:
            age = today.year - first
            if age >= 8:
                f4.append(Finding(
                    "Registering projects with MahaRERA since %d (%d on record)"
                    % (first, n_projects), 0, "positive",
                    "MahaRERA — registration records"))
            elif age <= 2:
                e4 -= 3.0
                f4.append(Finding(
                    "First registration only %d year%s ago (%d)"
                    % (age, "" if age == 1 else "s", first),
                    -3, "caution", "MahaRERA — registration records",
                    benchmark="a short record is not a bad one, but there is less to check"))
    cat4 = Category("continuity", "Scale & continuity", 10, max(0.0, e4), cov4, f4)

    # --- portfolio transparency (10)
    f5, e5 = [], 10.0
    cov5 = bool(portfolio)
    if portfolio:
        with_title = sum(1 for r in portfolio if _has_doc(r, "title"))
        share = with_title / len(portfolio)
        if share < 0.5:
            pen = 10.0 * (0.5 - share)
            e5 -= pen
            f5.append(Finding(
                "Title report on record for only %d of %d projects"
                % (with_title, len(portfolio)),
                -pen, "caution", "MahaRERA — uploaded documents"))
        else:
            f5.append(Finding(
                "Title report on record for %d of %d projects" % (with_title, len(portfolio)),
                0, "positive", "MahaRERA — uploaded documents"))
    cat5 = Category("transparency", "Portfolio transparency", 10, max(0.0, e5), cov5, f5,
                    note="QPR filing consistency not yet collected")

    cats = [cat1, cat2, cat3, cat4, cat5]
    scored = sum(c.weight for c in cats if c.covered)
    total = 100.0 * sum(c.earned for c in cats if c.covered) / scored if scored else 0.0
    confidence = max(0.0, min(1.0, scored / 100.0 - UNPARSED_PENALTY["qpr"]))
    band, label, note = _band(total)
    return Score(total, band, label, note, confidence, cats)
