"""Parsers for the captcha-free MahaRERA reputation pages.

These pages carry the "bad news" signals that turn an N/A into a real verdict:
  • Promoter-wise complaints   -> /promoter-complaint-report   (table, paginated 10/pg)
  • Deregistered/revoked       -> /list_of_projects_deregistered (table)

All verified against live HTML captured 2026-06 (data/recon/*.html). Structure is a
plain <table><tbody><tr><td>… so we read columns positionally, defensively.
"""

from __future__ import annotations

import logging
import re

from selectolax.parser import HTMLParser

log = logging.getLogger("honesthomes.parse_reputation")

_PROMOTER_ID_RE = re.compile(r"promoter_id=(\d+)")
_INT_RE = re.compile(r"\d+")


def _rows(tree: HTMLParser) -> list:
    """Return the data <tr>s of the first real data table on the page."""
    for tbody in tree.css("tbody"):
        trs = tbody.css("tr")
        if len(trs) >= 1 and trs[0].css("td"):
            return trs
    return []


def parse_complaints_page(html: str) -> list[dict]:
    """Promoter-wise complaints: [{promoter, complaints, promoter_id}].

    Columns: [Sr] [Name of Promoter] [Number of Complaints] [View(link w/ promoter_id)].
    """
    tree = HTMLParser(html)
    out: list[dict] = []
    for tr in _rows(tree):
        tds = tr.css("td")
        if len(tds) < 3:
            continue
        name = tds[1].text(strip=True)
        if not name:
            continue
        m = _INT_RE.search(tds[2].text())
        complaints = int(m.group()) if m else 0
        link = tr.css_first("a[href*='promoter_id=']")
        pid = ""
        if link:
            mid = _PROMOTER_ID_RE.search(link.attributes.get("href", ""))
            pid = mid.group(1) if mid else ""
        out.append({"promoter": name, "complaints": complaints, "promoter_id": pid})
    return out


def parse_revoked_page(html: str) -> list[dict]:
    """Deregistered/revoked projects. Columns vary; we capture the RERA id + project
    name + promoter by scanning each row's cells for a P-id and the longest text cells.
    """
    tree = HTMLParser(html)
    out: list[dict] = []
    rera_re = re.compile(r"\b(P\d{8,})\b")
    for tr in _rows(tree):
        tds = [td.text(strip=True) for td in tr.css("td")]
        if not tds:
            continue
        blob = " ".join(tds)
        m = rera_re.search(blob)
        rera_id = m.group(1) if m else ""
        # project name = first longish non-numeric cell; promoter = next one
        texts = [t for t in tds if t and not t.isdigit() and not rera_re.fullmatch(t)]
        name = texts[0] if texts else ""
        promoter = texts[1] if len(texts) > 1 else ""
        if rera_id or name:
            out.append({"rera_id": rera_id, "project_name": name, "promoter": promoter, "revoked": True})
    return out


def parse_total_pages_hint(html: str) -> int:
    """Best-effort: highest page=N in the pager, else 0 (unknown)."""
    nums = [int(n) for n in re.findall(r"[?&]page=(\d+)", html)]
    return max(nums) + 1 if nums else 0
