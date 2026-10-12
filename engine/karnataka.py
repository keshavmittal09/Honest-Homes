"""The honest verdict for a Karnataka RERA (K-RERA) project.

Same contract as engine/verdict.py — deterministic, every signal sourced, facts
not accusations — and the same yardstick: this module reuses scoring.py's
weights, severity ladder, decay and confidence floor rather than inventing its
own. What differs is the evidence, which is what K-RERA actually publishes:

  * registration status, dates, extensions and filed documents  (the project page)
  * the complaint register, complaint orders and penalty orders (public lists)
  * K-RERA's own "lapsed projects" / "default projects" lists

Two categories can be assessed from that — Delivery (30) and Legal & regulatory
(25). Disclosure, Financial and Land are scored from document types and booking
figures that K-RERA labels differently or does not publish, so they are left
UNASSESSED rather than judged by MahaRERA's vocabulary (which would wrongly mark
every project as missing its Form 1/2/3). Assessed weight is therefore 55, the
confidence is below scoring.CONFIDENCE_FLOOR, and — by the framework's own
rule — only a band is published, never a number.

It never consults the MahaRERA reputation registers. Those are keyed by promoter
name, and a Bengaluru builder sharing a name with a Maharashtra one would
inherit someone else's complaints.
"""

from __future__ import annotations

import math
import re
from datetime import date

from engine.scoring import (CONFIDENCE_FLOOR, SEVERITY, UNPARSED_PENALTY, Category,
                            Finding, Score, _band, _decay, _years_since)
from engine.verdict import (BAND_AMBER, BAND_GREEN, BAND_INCOMPLETE, BAND_RED, Signal,
                            Verdict, _BAND_V2_TO_LEGACY)

SRC_KA = "Karnataka RERA — project registration"
SRC_KA_EXT = "Karnataka RERA — completion extensions"
SRC_KA_DOC = "Karnataka RERA — filed documents"
SRC_KA_CMP = "Karnataka RERA — complaint register"
SRC_KA_ORD = "Karnataka RERA — Authority orders"
SRC_KA_PEN = "Karnataka RERA — penalty orders"
SRC_KA_LAPSE = "Karnataka RERA — lapsed projects list"

KA_DISCLAIMER = (
    "This summary is generated automatically from public Karnataka RERA records as of the "
    "date shown. It is informational only, not legal or financial advice, and may be "
    "incomplete or out of date. Always verify directly with K-RERA before deciding."
)

# At or above this share of an assessed total the record shows nothing adverse.
_GREEN_AT = 0.85


def norm_name(x: str | None) -> str:
    """The key project and builder names are matched on.

    K-RERA's complaint and order lists carry no registration number, only free
    text names typed by clerks, so matching is on names. Normalisation is
    deliberately light — case, punctuation, "Pvt"/"Ltd" — because anything looser
    ("Pinnacle" is a project name used by several builders) would attribute one
    project's complaints to another, which is the worse error.
    """
    x = (x or "").lower().replace("&", " and ")
    x = re.sub(r"\bpvt\b\.?", "private", x)
    x = re.sub(r"\bltd\b\.?", "limited", x)
    return re.sub(r"[^a-z0-9]+", " ", x).strip()


def pair_key(project: str | None, promoter: str | None) -> str:
    return norm_name(project) + "|" + norm_name(promoter)


def latest_completion(rec: dict) -> str | None:
    sp = rec.get("specs") or {}
    revised = [e.get("revisedDate") for e in rec.get("extensions") or [] if e.get("revisedDate")]
    dates = [d for d in [sp.get("revisedCompletion"), *revised] if d]
    return max(dates) if dates else sp.get("originalCompletion")


def revision_count(rec: dict) -> int:
    """Extensions that actually moved the date.

    K-RERA records an extension even when the revised date equals the promised
    one (the certificate was filed, the date did not change), so counting rows
    alone would overstate the delay.
    """
    sp = rec.get("specs") or {}
    prev = sp.get("originalCompletion")
    n = 0
    for e in rec.get("extensions") or []:
        d = e.get("revisedDate")
        if d and (prev is None or d > prev):
            n += 1
            prev = d
    return n


def has_occupancy(rec: dict) -> bool:
    for d in rec.get("documents") or []:
        text = ((d.get("label") or "") + " " + (d.get("kind") or "")).lower()
        if "occupancy certificate" in text or "completion certificate" in text:
            return True
    return False


def _months_past(iso: str | None, today: date) -> int | None:
    try:
        y, m, d = (int(x) for x in str(iso)[:10].split("-"))
        delta = (today - date(y, m, d)).days
    except (ValueError, TypeError):
        return None
    return int(delta / 30.4) if delta > 0 else None


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------

def _delivery(rec: dict, registered: bool, today: date, oc: bool) -> Category:
    """Delivery & timeline — 30. Same curves as scoring._delivery."""
    sp = rec.get("specs") or {}
    revs = revision_count(rec)
    latest = latest_completion(rec)
    earned, f = 30.0, []
    covered = registered and bool(sp.get("originalCompletion") or latest)

    if revs == 0:
        f.append(Finding("No completion-date extensions that moved the date", 0, "positive",
                         SRC_KA_EXT))
    else:
        pen = min(20.0, 6.0 + 4.5 * (revs - 1))     # a pattern costs more than one slip
        earned -= pen
        f.append(Finding(
            "Completion date revised %s" % _plural(revs, "time"), -pen,
            "negative" if revs > 1 else "caution", SRC_KA_EXT,
            question="The completion date has been revised %s. What is the current committed "
                     "handover date, and what is the remedy if it slips again?"
                     % _plural(revs, "time")))

    months = _months_past(latest, today) if registered else None
    if months is not None and months > 6 and not oc:
        pen = min(12.0, 2.2 * math.log2(1 + months / 6.0))
        earned -= pen
        f.append(Finding(
            "Committed completion date (%s) passed %d months ago, no occupancy certificate "
            "on file" % (latest, months), -pen, "negative", SRC_KA,
            question="The filing commits to %s, which was %d months ago. What is the present "
                     "status on site, has possession been offered, and can I see the "
                     "occupancy certificate?" % (latest, months)))
    elif oc and months is not None:
        f.append(Finding("Completion date has passed, but an occupancy / completion "
                         "certificate is on file", 0, "positive", SRC_KA_DOC))
    elif oc:
        f.append(Finding("Occupancy / completion certificate on the record", 0, "positive",
                         SRC_KA_DOC))

    return Category("delivery", "Delivery & timeline", 30, max(0.0, earned), covered, f,
                    note="" if covered else "Only registered projects are assessed for delivery")


def _legal(ev: dict | None, today: date) -> tuple[Category, bool]:
    """Legal & regulatory standing — 25. Same severity ladder and decay as scoring._legal."""
    f, earned = [], 25.0
    if ev is None:
        return Category("legal", "Legal & regulatory standing", 25, 0.0, False, [],
                        "K-RERA complaint and order registers not collected for this project"), False

    if ev.get("revoked"):
        f.append(Finding("Registration REVOKED on K-RERA's record", -25, "negative",
                         "Karnataka RERA — project orders",
                         question="The registration appears revoked. On what basis are units "
                                  "still being offered, and what is the position of buyers "
                                  "who have paid?"))
        return Category("legal", "Legal & regulatory standing", 25, 0.0, True, f), True

    if ev.get("ambiguous"):
        return Category(
            "legal", "Legal & regulatory standing", 25, 0.0, False, [],
            "This project's name and builder are shared with another K-RERA registration "
            "outside our area, so complaints cannot be attributed to this one with "
            "confidence"), False

    n_total = ev.get("complaints") or 0
    orders = ev.get("orders") or []
    n_orders = len(orders)
    n_total = max(n_total, n_orders)
    n_open = n_total - n_orders          # on the register, no order published
    penalties = ev.get("penalties") or []

    load_c = 0.0
    for o in orders:
        yrs = _years_since(o.get("orderDate"), today)
        load_c += _decay(SEVERITY["buyer_order"], yrs, True)
    load_c += SEVERITY["buyer_pending"] * n_open
    load_p = sum(_decay(SEVERITY["non_compliance"], _years_since(p.get("date"), today), False)
                 for p in penalties)

    # One sublinear deduction for the whole category, then split between the
    # findings in proportion to the load each contributed, so the impacts shown
    # add up to exactly what was taken off.
    pen = min(22.0, 5.5 * math.log2(1 + load_c + load_p)) if (load_c + load_p) else 0.0
    earned -= pen
    share_c = pen * load_c / (load_c + load_p) if (load_c + load_p) else 0.0
    share_p = pen - share_c

    if n_total:
        bits = ["%s on K-RERA's complaint register" % _plural(n_total, "complaint")]
        if n_orders:
            bits.append("%d with an Authority order published" % n_orders)
        f.append(Finding(
            ", ".join(bits), -share_c, "negative" if n_total > 1 else "caution", SRC_KA_CMP,
            question="Can you share K-RERA's orders on the complaints against this project, "
                     "and confirm what was done to comply with each?",
            benchmark="the median project on K-RERA's register has none"))
    else:
        f.append(Finding("No complaint on K-RERA's register under this project's name", 0,
                         "positive", SRC_KA_CMP))
    if penalties:
        amt = sum(int(p.get("amount") or 0) for p in penalties)
        what = ("not filing its annual report"
                if all("ANNUAL-REPORT" in (p.get("violation") or "") for p in penalties)
                else "a compliance violation")
        f.append(Finding(
            "K-RERA penalised the promoter for %s%s"
            % (what, " (₹%s)" % format(amt, ",") if amt else ""),
            -share_p, "negative", SRC_KA_PEN,
            question="K-RERA has penalised this promoter for a compliance default. Which "
                     "filings are outstanding, and are they now up to date?"))

    return Category("legal", "Legal & regulatory standing", 25,
                    max(0.0, min(25.0, earned)), True, f,
                    note="Complaints are matched to projects by exact name and builder"), False


def _unassessed(key: str, label: str, weight: int, why: str) -> Category:
    return Category(key, label, weight, 0.0, False, [], why)


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------

def build_verdict_ka(rec: dict, *, reg_no: str, as_of: str, evidence: dict | None = None,
                     today: date | None = None) -> Verdict:
    """`evidence` is the project's slice of the K-RERA registers (see api.karnataka);
    None means they were not collected, and the legal category is left unassessed."""
    today = today or date.today()
    sp = rec.get("specs") or {}
    name = rec.get("project_name") or "This project"
    registered = bool(rec.get("registered")) and (sp.get("status") or "").lower() == "registered"
    ev = evidence
    oc = has_occupancy(rec)
    revs = revision_count(rec)
    latest = latest_completion(rec)
    lapsed_listed = bool(ev and ev.get("lapsed"))
    defaulted = bool(ev and ev.get("default"))
    signals: list[Signal] = []

    # ---- signals (the plain-language list under "Why this verdict") -------
    if registered:
        on = f" on {sp['registeredOn']}" if sp.get("registeredOn") else ""
        signals.append(Signal(
            key="ka_registered", points=0, title="Registered with Karnataka RERA",
            reason=(f"Registered{on} (No. {reg_no}). Registration is a legal requirement to "
                    "sell, not a quality signal, so it earns no points."),
            source=SRC_KA, as_of=as_of, kind="neutral"))
    else:
        signals.append(Signal(
            key="ka_application", points=0, title="Application only — not yet registered",
            reason=("K-RERA lists this as an application, not a registered project. A project "
                    "may not be advertised or sold before it is registered — ask the seller "
                    "for the registration certificate."),
            source=SRC_KA, as_of=as_of, kind="caution"))

    if revs:
        signals.append(Signal(
            key="ka_extensions", points=0,
            title=f"Completion date revised {_plural(revs, 'time')}",
            reason=(f"Promised completion was {sp.get('originalCompletion')}; the latest date "
                    f"on the K-RERA record is {latest}."),
            source=SRC_KA_EXT, as_of=as_of, kind="negative" if revs > 1 else "caution"))
    if oc:
        signals.append(Signal(
            key="ka_occupancy", points=0,
            title="Occupancy / completion certificate on the record",
            reason="An occupancy or completion certificate is among the documents filed.",
            source=SRC_KA_DOC, as_of=as_of, kind="positive"))

    months = _months_past(latest, today) if registered else None
    if registered and latest:
        if months is None:
            signals.append(Signal(
                key="ka_due", points=0, title=f"Completion due {latest}",
                reason=f"The latest completion date on the K-RERA record is {latest}.",
                source=SRC_KA, as_of=as_of, kind="neutral"))
        elif oc:
            signals.append(Signal(
                key="ka_overdue", points=0,
                title="Completion date has passed — certificate on file",
                reason=(f"The latest completion date on record ({latest}) has passed, but an "
                        "occupancy or completion certificate is on file, so this is not "
                        "treated as a delay."),
                source=SRC_KA, as_of=as_of, kind="neutral"))
        elif months > 6:
            signals.append(Signal(
                key="ka_overdue", points=0,
                title=f"Completion date passed {months} months ago",
                reason=(f"The latest completion date on record ({latest}) was {months} months "
                        "ago and no occupancy or completion certificate is on file. The record "
                        "does not say whether the project was delivered — ask the seller for "
                        "the occupancy certificate."),
                source=SRC_KA, as_of=as_of, kind="caution"))
        else:
            signals.append(Signal(
                key="ka_overdue", points=0, title="Completion date has just passed",
                reason=(f"The latest completion date on record ({latest}) passed within the "
                        "last six months. Short overruns are common; ask for the current "
                        "handover date."),
                source=SRC_KA, as_of=as_of, kind="neutral"))

    if lapsed_listed:
        signals.append(Signal(
            key="ka_lapsed_list", points=0,
            title="On K-RERA's list of projects past their completion date",
            reason=("K-RERA's own \"Lapsed Projects\" list includes this project, with the "
                    "notice that its proposed completion date has expired and buyers should "
                    "take an informed decision."),
            source=SRC_KA_LAPSE, as_of=as_of, kind="caution"))
    if defaulted:
        signals.append(Signal(
            key="ka_default_list", points=0,
            title="On K-RERA's Default Projects list",
            reason="K-RERA's public \"Default Projects\" list includes this project.",
            source=SRC_KA_LAPSE, as_of=as_of, kind="negative"))

    if registered and not (rec.get("documents") or []):
        signals.append(Signal(
            key="ka_no_docs", points=0, title="No documents on the K-RERA record",
            reason=("No documents are filed against this registered project on the K-RERA "
                    "page, so none of its approvals or financials can be checked from here."),
            source=SRC_KA_DOC, as_of=as_of, kind="caution"))

    legal, hard_cap = _legal(ev, today)
    if ev is not None and legal.covered and not hard_cap:
        n_total = max(ev.get("complaints") or 0, len(ev.get("orders") or []))
        if n_total:
            n_ord = len(ev.get("orders") or [])
            signals.append(Signal(
                key="ka_complaints", points=0,
                title=f"{_plural(n_total, 'complaint')} filed against this project",
                reason=(f"{_plural(n_total, 'complaint')} on K-RERA's public complaint register "
                        f"carry this project's name and builder; {n_ord} "
                        f"{'has' if n_ord == 1 else 'have'} an Authority order published. "
                        "K-RERA's published orders show no complaint filed by a promoter "
                        "against a buyer, so these are counted as complaints against the "
                        "project."),
                source=SRC_KA_CMP, as_of=as_of, kind="negative" if n_total > 1 else "caution"))
        else:
            signals.append(Signal(
                key="ka_no_complaints", points=0,
                title="No complaint on K-RERA's register under this project's name",
                reason=("No entry on K-RERA's public complaint register carries this project's "
                        "name and builder. Matching is by exact name, so a complaint filed "
                        "under a different spelling would not appear here."),
                source=SRC_KA_CMP, as_of=as_of, kind="positive"))
        for p in ev.get("penalties") or []:
            signals.append(Signal(
                key="ka_penalty", points=0,
                title="Penalised by K-RERA for a compliance default",
                reason=(f"K-RERA ordered a penalty of ₹{int(p.get('amount') or 0):,} on "
                        f"{p.get('date')} under {p.get('penaltySection') or 'the Act'} for "
                        f"{(p.get('violation') or 'a violation').replace('-', ' ').title()}."),
                source=SRC_KA_PEN, as_of=as_of, kind="negative"))
    elif ev is not None and ev.get("ambiguous"):
        signals.append(Signal(
            key="ka_ambiguous", points=0, title="Complaints could not be attributed",
            reason=("This project's name and builder are shared with another K-RERA "
                    "registration outside our area, so complaints on the register cannot be "
                    "attributed to this one with confidence."),
            source=SRC_KA_CMP, as_of=as_of, kind="caution"))

    # ---- score ------------------------------------------------------------
    delivery = _delivery(rec, registered, today, oc)
    cats = [
        delivery, legal,
        _unassessed("disclosure", "Disclosure & compliance hygiene", 20,
                    "K-RERA files are not classified into the Form 1/2/3 and approval "
                    "categories this framework scores, and quarterly reports are not collected"),
        _unassessed("financial", "Financial & construction viability", 15,
                    "K-RERA does not publish booked-unit figures"),
        _unassessed("land", "Land & title clarity", 10,
                    "Title documents on K-RERA are not classified yet"),
    ]
    scored_weight = sum(c.weight for c in cats if c.covered)
    if scored_weight:
        total = 100.0 * sum(c.earned for c in cats if c.covered) / scored_weight
    else:
        total = 0.0
    confidence = max(0.0, min(1.0, scored_weight / 100.0 - sum(UNPARSED_PENALTY.values())))
    if hard_cap:
        total = min(total, 15.0)
    n_buyer = max(ev.get("complaints") or 0, len(ev.get("orders") or [])) if ev else 0
    # "Looks clean" is a positive claim, so it needs the absence of every adverse
    # finding -- a revision or a passed deadline included -- not merely a high
    # total. The number itself is never altered by this.
    adverse = any(fd.impact < 0 for c in cats if c.covered for fd in c.findings)
    blocked = bool(hard_cap or lapsed_listed or defaulted or n_buyer or adverse
                   or (ev and ev.get("penalties")))
    band2, label2, note2 = _band(total, blocked)
    score = Score(total, band2 if scored_weight else "unrated", label2, note2, confidence, cats,
                  capped_by="revocation" if hard_cap else "")
    if not scored_weight:
        score = Score(0.0, "unrated", "Not yet assessed",
                      "Nothing project-specific could be assessed", 0.0, cats)

    # ---- band and headline ------------------------------------------------
    if not scored_weight:
        band = BAND_INCOMPLETE
    else:
        band = _BAND_V2_TO_LEGACY.get(score.band, BAND_AMBER)
    if not registered and band == BAND_GREEN:
        band = BAND_AMBER                  # an application cannot be "looks clean"
    if defaulted and band == BAND_GREEN:
        band = BAND_AMBER
    if band == BAND_GREEN and not legal.covered:
        # "Looks clean" is a claim about the complaint record too. Where that
        # could not be checked, the dates alone cannot carry it: leave the band
        # unassigned rather than reassure on half the evidence.
        band = BAND_INCOMPLETE

    worst = None
    for c in cats:
        if not c.covered:
            continue
        for fd in c.findings:
            if fd.impact < 0 and (worst is None or fd.impact < worst.impact):
                worst = fd

    def _fact(fd: Finding) -> str:
        """The finding as a sentence with a subject and a verb."""
        t = fd.text
        if t.startswith("Completion date revised"):
            return "its completion date has been revised %s" % t.split("revised ", 1)[1]
        if t.startswith("Committed completion date"):
            return ("its committed completion date (%s) passed %d months ago with no "
                    "occupancy certificate on file" % (latest, months or 0))
        if "complaint" in t:
            n_ord = len(ev.get("orders") or []) if ev else 0
            return "%s %s on K-RERA's complaint register%s" % (
                n_buyer, "complaint is" if n_buyer == 1 else "complaints are",
                " (%d with an Authority order published)" % n_ord if n_ord else "")
        if t.startswith("K-RERA penalised"):
            return "K-RERA has penalised its promoter for a compliance default"
        return t[0].lower() + t[1:]

    if hard_cap:
        headline = (f"{name}'s Karnataka RERA registration has been revoked — treat with "
                    "serious caution.")
    elif not registered:
        extra = (" " + _fact(worst)[0].upper() + _fact(worst)[1:] + "."
                 if worst is not None and legal.covered and n_buyer else "")
        headline = (f"{name} is only an application on Karnataka RERA, not a registered "
                    f"project — confirm registration before paying anything.{extra}")
    elif band == BAND_GREEN:
        headline = (f"Nothing adverse on {name}'s Karnataka RERA registration, completion or "
                    "complaint record — but this is a baseline check from dates and K-RERA's "
                    "public registers, not a clearance.")
    elif band == BAND_INCOMPLETE:
        headline = (f"{name}'s Karnataka RERA registration and dates show nothing adverse, but "
                    "we could not match it to K-RERA's complaint register, so it is not "
                    "rated — check complaints on the K-RERA portal.")
    elif worst is not None:
        more = ""
        n_other = sum(1 for c in cats if c.covered for fd in c.findings
                      if fd.impact < 0 and fd is not worst)
        if n_other:
            more = " (and %d other finding%s below)" % (n_other, "" if n_other == 1 else "s")
        headline = (f"On {name}'s Karnataka RERA record, {_fact(worst)}{more}. Worth a closer "
                    "look — this is a band from dates and K-RERA's public registers, not a "
                    "clearance.")
    elif lapsed_listed or defaulted:
        headline = (f"K-RERA lists {name} among projects past their completion date. Worth a "
                    "closer look — this is a band from public registers, not a clearance.")
    else:
        headline = (f"{name} is on the Karnataka RERA record with items worth a closer "
                    "look — this is a band from public registers, not a clearance.")
    if ev is None and band not in (BAND_INCOMPLETE,):
        headline += " Complaint records were not available for this check."

    signals.append(Signal(
        key="coverage", points=0, title="What this verdict covers",
        reason=("Based on this project's Karnataka RERA registration and completion record"
                + (", plus K-RERA's public complaint register, complaint orders, penalty "
                   "orders and lapsed-projects list" if ev is not None else "")
                + ". Documents, quarterly reports and financials are not yet assessed, so no "
                  "numeric score is given — only a band."
                + (" Complaints are matched to the project by exact name and builder, so one "
                   "filed under a different spelling would not appear." if ev is not None
                   else " K-RERA complaint records were not available, so absence of "
                        "complaints here is not evidence that there are none.")),
        source=SRC_KA, as_of=as_of, kind="neutral"))

    publishable = score.publishable
    return Verdict(
        rera_id=reg_no, project_name=rec.get("project_name") or "",
        promoter_name=rec.get("promoter_name") or "",
        score=round(score.total / 10.0, 1) if (publishable and scored_weight) else None,
        band=band, headline=headline, signals=signals, data_as_of=as_of,
        project_score=score.to_dict() if scored_weight else None, builder_score=None,
        confidence=round(confidence, 2) if scored_weight else None,
        band_v2=score.band if scored_weight else "", disclaimer=KA_DISCLAIMER)
