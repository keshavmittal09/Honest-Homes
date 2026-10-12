"""Karnataka RERA public registers — complaints, orders, penalties, lapsed list.

Unlike MahaRERA, K-RERA publishes its complaint and order registers as plain
public pages: no captcha, no token, one request per register for the whole
state. Four fetches, a few seconds, nothing to defeat.

    complaints   /viewAllComplaints      every complaint: id, project, promoter
    orders       /viewAllProjectOrders   three tables on one page:
                   complaint orders      who petitioned, relief sought, order date
                   project orders        registration / extension / revocation
                   penalty orders        violation, section, amount, by reg. no.
    lapsed       /viewDefaultProjects    "Default" (4) and "Lapsed" (3,000+) lists
    master       /viewAllProjects        every registration, to detect name clashes

The complaint and order lists carry NO registration number -- only the project
and promoter names as typed -- so they are joined to our projects on the
normalised (project, promoter) pair. Penalty orders and the lapsed list carry
the registration number and join exactly.

The state-wide complaint list is reduced to per-pair counts, and orders to the
pairs we hold, so the committed file stays small. Run after
`krera_region build`:

    python -m collector.krera_register
"""

from __future__ import annotations

import collections
import html
import json
import re
import time
from datetime import date
from pathlib import Path

from engine.karnataka import norm_name, pair_key

from .krera import KRera

BASE = "https://rera.karnataka.gov.in/"
ROOT = Path(__file__).resolve().parent.parent
REGION = ROOT / "data" / "regions" / "bangalore-north-east"
OUT = REGION / "krera-register.json"

_Q = r"'((?:[^'\\]|\\.)*)'"


def _page(k: KRera, path: str, attempts: int = 6) -> str:
    """Fetch one register, insisting on a complete document.

    The server sometimes answers 200 with a page cut off mid-table (a 10 MB
    page arriving as 3 MB, no closing tag) and nothing in the HTTP layer says
    so. Publishing that would drop two-thirds of the orders without any error,
    so a page is accepted only when it ends with </html>; otherwise retry.
    """
    for i in range(1, attempts + 1):
        try:
            text = k._get(BASE + path).decode("utf-8", "replace")
        except Exception as e:           # network hiccup: same treatment as truncation
            text = ""
            print("    %s attempt %d failed: %s" % (path, i, str(e)[:60]))
        if text.rstrip().lower().endswith("</html>"):
            return text
        if text:
            print("    %s attempt %d truncated (%.1f MB), retrying" % (path, i, len(text) / 1e6))
        time.sleep(3 * i)
    raise SystemExit("could not fetch a complete %s after %d attempts -- not writing a "
                     "partial register" % (path, attempts))


def _scripts_largest(raw: str) -> str:
    return max(re.findall(r"<script[^>]*>(.*?)</script>", raw, flags=re.S), key=len)


def _tables(raw: str) -> dict[int, list[list[str]]]:
    """Every <tr> in the page, grouped by its cell count.

    The orders page stacks three differently shaped tables in one document, so
    grouping by width is what keeps them apart. Header rows are kept; callers
    drop them by checking the first cell.
    """
    raw = re.sub(r"<script.*?</script>", "", raw, flags=re.S)
    out: dict[int, list[list[str]]] = collections.defaultdict(list)
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", raw, flags=re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, flags=re.S)]
        if cells:
            out[len(cells)].append(cells)
    return out


def _iso(d: str) -> str | None:
    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{4})", d or "")
    return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else None


def parse_complaints(raw: str) -> list[tuple[str, str, str]]:
    """[(id, project, promoter)] -- 'NOT FOUND' where K-RERA could not resolve one."""
    scr = _scripts_largest(raw)
    out = []
    for blk in scr.split("var localObj = {")[1:]:
        a = re.search(r"appNo\s*:\s*" + _Q, blk)
        p = re.search(r"applicationNameList3\s*\.push\(" + _Q + r"\)", blk)
        m = re.search(r"applicationNameList4\s*\.push\(" + _Q + r"\)", blk)
        if a and p and m:
            out.append((a.group(1), html.unescape(p.group(1)), html.unescape(m.group(1))))
    return out


def parse_master(raw: str) -> list[tuple[str, str, str, str]]:
    """[(ack no, registration no, project, promoter)] for every K-RERA project."""
    scr = _scripts_largest(raw)

    def pushes(name: str) -> list[str]:
        return [html.unescape(x) for x in re.findall(name + r"\s*\.push\(" + _Q + r"\)", scr)]

    cols = [pushes(n) for n in ("applicationNameList", "applicationNameList2",
                                "applicationNameList3", "applicationNameList4")]
    if len({len(c) for c in cols}) != 1:
        raise SystemExit("master list arrays differ in length %s -- page layout changed"
                         % [len(c) for c in cols])
    return list(zip(*cols))


def build(delay: float = 1.0) -> dict:
    if not (REGION / "records.json").exists():
        raise SystemExit("no records.json -- run `krera_region build` first")
    recs = json.loads((REGION / "records.json").read_text(encoding="utf-8"))
    ours = {k: v for k, v in recs.items() if (v.get("project_name") or "").strip()}
    our_pairs = {pair_key(v["project_name"], v.get("promoter_name")) for v in ours.values()}
    our_regs = set(ours)

    k = KRera()
    k.start()
    raw = {}
    for name, path in (("complaints", "viewAllComplaints"),
                       ("orders", "viewAllProjectOrders"),
                       ("lapsed", "viewDefaultProjects"),
                       ("master", "viewAllProjects")):
        raw[name] = _page(k, path)
        print("  fetched %-10s %6.1f MB" % (name, len(raw[name]) / 1e6))
        time.sleep(delay)

    # --- complaints: state-wide pair counts ---------------------------------
    complaints = parse_complaints(raw["complaints"])
    pair_counts: collections.Counter = collections.Counter()
    unresolved = 0
    for _id, proj, prom in complaints:
        if proj == "NOT FOUND" or not proj.strip() or not prom.strip():
            unresolved += 1
            continue
        pair_counts[pair_key(proj, prom)] += 1

    # --- master list: how many registrations share each of our pairs --------
    master = parse_master(raw["master"])
    master_pairs = collections.Counter(pair_key(p, m) for _a, _r, p, m in master)
    master_ours = {k_: n for k_, n in master_pairs.items() if k_ in our_pairs}

    # --- orders page: three tables ------------------------------------------
    tables = _tables(raw["orders"])
    orders, penalties, revoked = [], collections.defaultdict(list), []
    for r in tables.get(13, []):
        if r[0].upper().startswith("S.NO"):
            continue
        if pair_key(r[6], r[7]) not in our_pairs:
            continue
        orders.append({
            "complaintNo": r[1], "complaintDate": _iso(r[2]), "orderDate": _iso(r[3]),
            "petitioner": r[4], "respondent": r[5], "project": r[6], "promoter": r[7],
            "district": r[8], "relief": r[9][:600], "disposedBy": r[10], "bench": r[12],
        })
    for r in tables.get(11, []):                 # penalty orders, by registration no.
        if r[0].upper().startswith("S.NO") or r[1] not in our_regs:
            continue
        penalties[r[1]].append({
            "violation": r[5], "section": r[6], "penaltySection": r[7],
            "date": _iso(r[8]), "amount": re.sub(r"[^\d]", "", r[10]) or "0",
        })
    for r in tables.get(8, []):                  # project orders: only revocations matter
        if r[0].upper().startswith("S.NO"):
            continue
        if "REVOKED" in r[4].upper():
            revoked.append(r[1])

    # --- lapsed / default lists: two tables of different width on one page ----
    # Default has 8 columns, Lapsed adds "TYPE OF PROJECT" for 9. Rows are told
    # apart by width, and each width is checked against its header so a layout
    # change fails loudly instead of silently returning an empty list.
    lt = _tables(raw["lapsed"])
    for width, last in ((8, "PROPOSED COMPLETION DATE"), (9, "PROPOSED COMPLETION DATE")):
        hdr = [r for r in lt.get(width, []) if r[0].upper().startswith("S.NO")]
        if not hdr or hdr[0][-1].upper() != last:
            raise SystemExit("lapsed-projects page: no %d-column table with header %r -- "
                             "layout changed" % (width, last))
    default = [{"regNo": r[1], "promoter": r[2], "project": r[3], "district": r[4],
                "proposed": _iso(r[7])}
               for r in lt[8] if not r[0].upper().startswith("S.NO")]
    lapsed = [{"regNo": r[1], "promoter": r[2], "project": r[3], "district": r[5],
               "proposed": _iso(r[8])}
              for r in lt[9] if not r[0].upper().startswith("S.NO")]

    out = {
        "source": "Karnataka RERA — public registers (rera.karnataka.gov.in)",
        "fetchedAt": date.today().isoformat(),
        "counts": {
            "complaints": len(complaints), "complaintsUnresolved": unresolved,
            "orders": sum(1 for r in tables.get(13, []) if not r[0].upper().startswith("S.NO")),
            "ordersOurs": len(orders), "penaltiesOurs": sum(len(v) for v in penalties.values()),
            "lapsed": len(lapsed), "default": len(default), "master": len(master),
        },
        "complaintPairs": dict(pair_counts),
        "masterPairs": master_ours,
        "orders": orders,
        "penalties": penalties,
        "lapsed": [x["regNo"] for x in lapsed],
        "default": default,
        "revoked": revoked,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("wrote %s (%.0f KB)" % (OUT, OUT.stat().st_size / 1024))
    print(json.dumps(out["counts"]))
    return out


if __name__ == "__main__":
    build()
