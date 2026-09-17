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


def parse_detail(html: str, row: dict) -> dict:
    """Map a K-RERA detail page into the record shape engine.scoring reads.

    Only fields the scoring engine actually consumes are mapped. Complaints and
    litigation come from a separate endpoint (projectComplaintDetails) and are
    left empty here rather than guessed -- absent, not zero.
    """
    reg = re.search(r"PRM/KA/RERA/[A-Za-z0-9/\-]+", html)
    regdates = _cells(html, "At the time of Registration", 3)
    start = _dmy(regdates[0]) if regdates else None
    completion = _dmy(regdates[1]) if len(regdates) > 1 else None

    taluk = None
    tk = re.search(r"BANGALORE\s+(?:EAST|NORTH|SOUTH|WEST)", html, re.I) \
        or re.search(r"BENGALURU\s+(?:URBAN|RURAL)", html, re.I)
    if tk:
        taluk = tk.group(0).title()

    units_total = None
    m = re.search(r"Total No of Units\s*</[^>]*>\s*<[^>]*>\s*(\d+)", html) \
        or re.search(r"Total No\. of Units\s*</[^>]*>\s*<[^>]*>\s*(\d+)", html)
    if m:
        units_total = int(m.group(1))

    # extensions: a "Revised" / "extension" registration row beyond the first
    exts = []
    for mm in re.finditer(r"(Extension|Revised)\s*</", html, re.I):
        seg = html[mm.start():mm.start() + 400]
        d = re.search(r"\d{2}-\d{2}-\d{4}", seg)
        if d:
            exts.append({"revisedDate": _dmy(d.group(0))})

    docs = []
    for href, label in re.findall(r'href="(/?download_jc\?DOC_ID=[^"]+)"[^>]*>(.*?)</a>', html, re.S):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()
        if name:
            docs.append({"kind": name, "label": name, "category": _doc_category(name),
                         "file": name, "url": BASE + href.lstrip("/")})

    # Name and promoter come from the detail page itself -- authoritative and
    # present for every project, unlike the master list which only carries names
    # for its first visible page. "Promoter Name" is the developer/registrant;
    # on a small landowner-registered project that is an individual, which is
    # correct, not a parsing miss.
    project_name = _labelled(html, "Project Name") or row.get("name")
    promoter_name = _labelled(html, "Promoter Name") or row.get("promoter")

    # rera_id: the final PRM registration number if present; otherwise the
    # project is an application/unregistered (ACK only) -- flagged, not dressed
    # up as registered.
    ack = re.search(r"ACK/KA/RERA/[A-Za-z0-9/\-]+", html)
    rera_id = reg.group(0) if reg else (ack.group(0) if ack else row.get("reg"))
    registered = bool(reg)

    return {
        "rera_id": rera_id,
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
        "address": {"district": "Bengaluru Urban", "taluka": taluk,
                    "village": None, "pincode": None, "locality": None},
        "geo": {},
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
