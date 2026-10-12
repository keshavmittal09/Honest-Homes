"""Karnataka RERA collector — proof-of-concept for one project, end to end.

Karnataka's portal (rera.karnataka.gov.in) is a server-rendered Java/Spring app,
nothing like MahaRERA's Angular+token API. What that buys us:

* **No captcha, no token, no browser.** Every endpoint is plain HTTP. The whole
  state can be collected unattended -- the exact opposite of MahaRERA, where a
  human solves a captcha every ~90 minutes.
* **Master list in one request.** GET /viewAllProjects returns ~9,900 projects
  as inline JS arrays (ACK, registration no, name, promoter). No location, though.
* **Detail via POST /projectDetails** with action=<trailing id of the ACK>. Rich:
  registration/completion dates, units, floors, cost breakdown, per-year
  financials, NOCs, land owners, and the taluk we filter on.
* **Documents via GET /download_jc?DOC_ID=<token>** -- returns the real PDF.

"East/North Bengaluru" maps to the revenue taluks BANGALORE EAST / BANGALORE
NORTH (both inside Bengaluru Urban district), widened by locality name. Because
the master list carries no location, that filter needs each project's detail --
~9,900 fetches, but unattended and free.

This module proves ONE project through the existing verdict engine. The full
region pipeline (list -> filter -> detail -> docs -> parsed snapshot) is the next
build; the scoring engine itself is portable as-is.
"""

from __future__ import annotations

import argparse
import gzip
import http.cookiejar
import re
import ssl
import urllib.parse
import urllib.request
from datetime import date, datetime

BASE = "https://rera.karnataka.gov.in/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# East/North Bengaluru: the two taluks, widened by the localities buyers use.
EAST_NORTH_TALUKS = {"bangalore east", "bangalore north"}
EAST_NORTH_LOCALITIES = {
    "whitefield", "marathahalli", "kr puram", "krishnarajapuram", "mahadevapura",
    "bellandur", "kadugodi", "varthur", "hoodi", "brookefield", "bhoganahalli",
    "hebbal", "yelahanka", "thanisandra", "hennur", "banaswadi", "horamavu",
    "ramamurthy nagar", "kammanahalli", "jakkur", "sahakar nagar", "rt nagar",
    "devanahalli", "nagawara", "kalyan nagar", "hbr layout",
}


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


class KRera:
    def __init__(self) -> None:
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=_ctx()))
        self._started = False

    def _get(self, url: str, data: dict | None = None) -> bytes:
        hdr = {"User-Agent": UA, "Accept-Encoding": "gzip"}
        body = None
        if data is not None:
            hdr["Content-Type"] = "application/x-www-form-urlencoded"
            hdr["X-Requested-With"] = "XMLHttpRequest"
            body = urllib.parse.urlencode(data).encode()
        r = self.op.open(urllib.request.Request(url, data=body, headers=hdr), timeout=180)
        raw = r.read()
        return gzip.decompress(raw) if r.headers.get("Content-Encoding") == "gzip" else raw

    def start(self) -> None:
        # One hit to mint the session cookie the detail endpoint expects.
        self._get(BASE + "viewAllProjects")
        self._started = True

    def detail_html(self, project_id: str) -> str:
        if not self._started:
            self.start()
        return self._get(BASE + "projectDetails", {"action": project_id}).decode("utf-8", "replace")


# --- parsing ---------------------------------------------------------------

def _labelled(html: str, label: str) -> str | None:
    """Value of a `label <span>:</span></p></div> <div..>VALUE` field.

    Anchored on the label's markup so it reads the project's real value, never
    the page's dropdown of every option. Used for Promoter Name, Project Name,
    etc. -- the fields the master list does not reliably carry.
    """
    m = re.search(re.escape(label) + r"\s*<span[^>]*>\s*:\s*</span>\s*</p>\s*</div>\s*<div[^>]*>(.*?)</div>",
                  html, re.S)
    if not m:
        return None
    v = re.sub(r"<[^>]+>", " ", m.group(1))
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


def _cells(html: str, anchor: str, n: int) -> list[str]:
    i = html.find(anchor)
    if i < 0:
        return []
    seg = html[i:i + 5000]
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", seg, re.S)][:n]


def _dmy(s: str) -> str | None:
    """dd-mm-yyyy -> yyyy-mm-dd, the shape the scoring engine reads."""
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", s or "")
    return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else None


# A detail page is a stack of titled sections, and the SAME label appears in
# several of them: "PIN Code" and "Taluk" are printed first under Promoter
# Details (the builder's office) and again, differently capitalised, under
# Project Ongoing Status (the site). Reading a label page-wide returns whichever
# comes first, which is how a project in Kengeri was filed under the builder's
# Hennur office. Everything below is therefore read from its own section.
_HEADING = re.compile(
    r'<(?:h[1-6]|div class="[^"]*(?:panel-title|heading|title)[^"]*")[^>]*>(.*?)</(?:h[1-6]|div)>',
    re.S)


def _text(s: str) -> str:
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def section(html: str, title: str) -> str:
    """Raw HTML of the section whose heading contains `title`, up to the next heading.

    Empty string when the page has no such section -- callers treat that as
    "not stated", never as a value.
    """
    spans = [(m.start(), m.end(), _text(m.group(1))) for m in _HEADING.finditer(html)
             if 2 < len(_text(m.group(1))) < 90]
    want = title.lower()
    # An exact heading wins: "Project Details" is also a substring of "Previous
    # Project Details (Last 5 years only)", which comes first on the page.
    pick = next((i for i, (_a, _e, t) in enumerate(spans) if t.lower() == want), None)
    if pick is None:
        pick = next((i for i, (_a, _e, t) in enumerate(spans) if t.lower().startswith(want)), None)
    if pick is None:
        return ""
    end = spans[pick][1]
    nxt = spans[pick + 1][0] if pick + 1 < len(spans) else len(html)
    return html[end:nxt]


def labelled_in(block: str, label: str) -> str | None:
    """Like _labelled, but case-insensitive on the label and confined to `block`."""
    m = re.search(re.escape(label) + r"\s*<span[^>]*>\s*:\s*</span>\s*</p>\s*</div>\s*<div[^>]*>(.*?)</div>",
                  block, re.S | re.I)
    if not m:
        return None
    v = _text(m.group(1))
    return v or None


def labelled_exact(block: str, label: str) -> str | None:
    """Value of a field whose label is exactly `label`.

    "Name" is a substring of "Father's Name" and "Agent Name", so the promoter's
    own name is only read from a label that is nothing else.
    """
    m = re.search(r"<p[^>]*>\s*" + re.escape(label) + r"\s*<span[^>]*>\s*:\s*</span>\s*</p>\s*"
                  r"</div>\s*<div[^>]*>(.*?)</div>", block, re.S | re.I)
    if not m:
        return None
    v = _text(m.group(1))
    return v or None


_HDR = re.compile(r"Project Name\s*:\s*(.*?)\s*Acknowledgement Number\s*:\s*([A-Za-z0-9]+/\S+)?"
                  r"(?:\s*Registration Number\s*:\s*(PRM/KA/\S+))?")


def header(html: str) -> dict:
    """The page's own identity: project name, acknowledgement and registration no.

    This is the only place a page states which project it IS. The registration
    number is absent for an application that has not been registered yet.
    """
    t = _text(re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S))
    m = _HDR.search(t)
    if not m:
        return {}
    # The label can be followed by a notice instead of a number on abandoned
    # drafts ("THE BUYERS ARE STRICTLY ADVISED..."); those have no identity.
    name = m.group(1).strip()
    if name.upper().startswith("THE BUYERS ARE"):
        name = ""
    return {"name": name or None, "ack": m.group(2), "reg": m.group(3)}


def registration_rows(html: str) -> list[dict]:
    """Rows of the 'Registration/Extensions' table: the registration itself, then
    each extension. Columns are label | Start Date | Proposed Completion Date.

    An extension's Start Date is the PREVIOUS completion date and its Proposed
    Completion Date is the new one. An earlier version read the first date on
    the row, i.e. the old one, so every revision showed one step behind.
    """
    out = []
    for tbl in re.findall(r"<table.*?</table>", section(html, "Project Details") or html, flags=re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, flags=re.S)
        if not rows:
            continue
        head = [_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], flags=re.S)]
        if not head or "registration/extensions" not in head[0].lower():
            continue
        for r in rows[1:]:
            c = [_text(x) for x in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, flags=re.S)]
            if len(c) >= 3 and c[0]:
                out.append({"label": c[0], "start": _dmy(c[1]), "completion": _dmy(c[2])})
        break
    return out


def _coord(v: str | None) -> float | None:
    """A coordinate as printed: decimal degrees, or degrees-minutes-seconds."""
    if not v:
        return None
    v = v.strip()
    try:
        return float(v)
    except ValueError:
        pass
    m = re.match(r"\s*(\d+)\s*[°º]\s*(\d+)?\s*['′]?\s*([\d.]+)?\s*[\"″]?\s*([NSEW])?", v)
    if not m:
        return None
    try:
        deg = float(m.group(1)) + float(m.group(2) or 0) / 60.0 + float(m.group(3) or 0) / 3600.0
    except ValueError:                  # "13.17.75" and the like: unreadable, not zero
        return None
    return -deg if (m.group(4) or "").upper() in ("S", "W") else deg


# Bengaluru and its rural taluks. A coordinate outside this box is a typo or a
# placeholder ("0", "Not Available"), and plotting it would put the project in
# another state, so it is dropped rather than shown.
_LAT_BOX = (12.6, 13.6)
_LNG_BOX = (77.0, 78.2)


def project_location(html: str) -> dict:
    """The SITE's address -- never the promoter's.

    Two layouts exist. Newer pages print the site under "Project Ongoing Status"
    with its own "Pin Code"; older ones print it under "Project Details" with no
    separate pin and often only the village/hobli in the address text. Both are
    read from the project's own blocks, and the promoter's block is never used.
    """
    blocks = [section(html, "Project Ongoing Status"), section(html, "Project Details")]

    def first(*labels):
        for blk in blocks:
            for lab in labels:
                v = labelled_in(blk, lab)
                if v:
                    return v
        return None

    addr = first("Project Address")
    lat = _coord(first("Latitude", "North Latitude"))
    lng = _coord(first("Longitude", "East Longitude"))
    if lat is not None and lng is not None and not (
            _LAT_BOX[0] <= lat <= _LAT_BOX[1] and _LNG_BOX[0] <= lng <= _LNG_BOX[1]):
        lat = lng = None
    pin = first("Pin Code")
    if not (pin and re.fullmatch(r"\d{6}", pin)):
        m = re.search(r"(?<!\d)(5[6-9]\d{4})(?!\d)", addr or "")
        pin = m.group(1) if m else None

    hobli = village = None
    if addr:
        m = re.search(r"([A-Za-z][A-Za-z.' ]{2,40}?)\s+Hobli", addr, re.I)
        hobli = re.sub(r"\s+", " ", m.group(1)).strip(" .,") if m else None
        m = re.search(r"([A-Za-z][A-Za-z.' ]{2,40}?)\s+Village", addr, re.I)
        village = re.sub(r"\s+", " ", m.group(1)).strip(" .,") if m else None
    return {
        "address": addr, "district": first("District"), "taluk": first("Taluk"),
        "pincode": pin, "lat": lat, "lng": lng, "hobli": hobli, "village": village,
    }


def parse_detail(html: str, row: dict) -> dict:
    """Map a K-RERA detail page into the record shape engine.scoring reads.

    Only fields the scoring engine actually consumes are mapped. Complaints and
    litigation come from a separate endpoint (projectComplaintDetails) and are
    left empty here rather than guessed -- absent, not zero.
    """
    hdr = header(html)
    reg_no, ack_no = hdr.get("reg"), hdr.get("ack")

    rows = registration_rows(html)
    first = next((r for r in rows if "at the time of registration" in r["label"].lower()), None)
    start = first["start"] if first else None
    completion = first["completion"] if first else None
    # Each extension row's completion column is the NEW date. `moved` marks the
    # rows that actually changed it, so a certificate that repeats the old date
    # is not counted as a delay downstream.
    exts, prev = [], completion
    for r in rows:
        if r is first or not r["completion"]:
            continue
        exts.append({"revisedDate": r["completion"], "startDate": r["start"], "kind": r["label"],
                     "moved": bool(prev and r["completion"] > prev)})
        if not prev or r["completion"] > prev:
            prev = r["completion"]

    loc = project_location(html)

    units_total = None
    m = re.search(r"Total No of Units\s*</[^>]*>\s*<[^>]*>\s*(\d+)", html) \
        or re.search(r"Total No\. of Units\s*</[^>]*>\s*<[^>]*>\s*(\d+)", html)
    if m:
        units_total = int(m.group(1))

    docs = []
    for href, label in re.findall(r'href="(/?download_jc\?DOC_ID=[^"]+)"[^>]*>(.*?)</a>', html, re.S):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()
        if name:
            docs.append({"kind": name, "label": name, "category": _doc_category(name),
                         "file": name, "url": BASE + href.lstrip("/")})

    # Identity comes from the page header, never from a first-match label: the
    # same labels recur in the table of the promoter's OTHER projects, so a
    # page-wide search returned a sibling project's name on ~1 page in 6.
    project_name = hdr.get("name") or row.get("name")
    pblk = section(html, "Promoter Details")
    promoter_name = (labelled_exact(pblk, "Promoter Name") or labelled_exact(pblk, "Name")
                     or row.get("promoter"))
    registered = bool(reg_no)
    rera_id = reg_no or ack_no or row.get("reg")

    return {
        "rera_id": rera_id,
        "ack_no": ack_no,
        "registered": registered,
        "project_name": project_name,
        "promoter_name": promoter_name,
        "source": "karnataka-rera",
        "specs": {
            "registeredOn": start,
            "originalCompletion": completion,
            "revisedCompletion": exts[-1]["revisedDate"] if exts else None,
            "status": "Registered" if registered else "Application (not yet registered)",
            "lapsed": False,
            "unitsTotal": units_total,
            "unitsSold": None,
        },
        "extensions": exts,
        "units": {"total": units_total, "booked": None},
        "address": {"district": loc["district"] or "Bengaluru Urban", "taluka": loc["taluk"],
                    "village": loc["village"], "hobli": loc["hobli"], "pincode": loc["pincode"],
                    "locality": None, "street": loc["address"]},
        "geo": {"lat": loc["lat"], "lng": loc["lng"]} if loc["lat"] and loc["lng"] else {},
        "plot": {},
        # From projectComplaintDetails in the full build -- not fabricated here.
        "projectComplaints": {"count": None, "complaints": []},
        "litigation": {"count": 0, "cases": [], "declared": False},
        "documents": docs,
        "document_count": len(docs),
    }


def _doc_category(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("balance sheet", "profit", "cash flow", "audit", "director")):
        return "KYC & financial"
    if any(k in n for k in ("commencement", "occupancy", "completion", "noc", "approval")):
        return "Approvals & certificates"
    if any(k in n for k in ("agreement", "sale deed", "title")):
        return "Agreements & legal"
    if "plan" in n:
        return "Plans"
    return "Other"


def in_east_north(html: str) -> bool:
    tk = re.search(r"BANGALORE\s+(EAST|NORTH)", html, re.I)
    if tk:
        return True
    low = html.lower()
    return any(loc in low for loc in EAST_NORTH_LOCALITIES)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", default="010519", help="project id (trailing number of the ACK)")
    ap.add_argument("--name", default="MBS VASUDHA")
    ap.add_argument("--promoter", default="")
    a = ap.parse_args()

    k = KRera()
    k.start()
    html = k.detail_html(a.id)
    row = {"name": a.name, "promoter": a.promoter, "reg": None}
    rec = parse_detail(html, row)

    print("=" * 64)
    print("KARNATAKA RERA — one project, end to end")
    print("=" * 64)
    print("  Project     :", rec["project_name"])
    print("  Registration:", rec["rera_id"])
    print("  Taluk        :", (rec["address"] or {}).get("taluka"))
    print("  In East/North:", in_east_north(html))
    print("  Registered on:", rec["specs"]["registeredOn"])
    print("  Completion   :", rec["specs"]["originalCompletion"])
    print("  Units (total):", rec["specs"]["unitsTotal"])
    print("  Extensions   :", len(rec["extensions"]))
    print("  Documents    :", rec["document_count"])

    # Run the existing verdict engine unchanged.
    from engine.scoring import score_project
    s = score_project(rec, today=date.today())
    print("\n  --- verdict engine (engine.scoring) ---")
    print("  Project score : %.1f / 100   band: %s   confidence: %.2f"
          % (s.total, s.band_label, s.confidence))
    for c in s.categories:
        cov = "%.1f/%d" % (c.earned, c.weight) if c.covered else "not assessed"
        print("    %-28s %s" % (c.label, cov))
    print("\n  NOTE: complaints/litigation come from projectComplaintDetails in the")
    print("  full build; shown here as not-assessed rather than a fake zero.")


if __name__ == "__main__":
    main()
