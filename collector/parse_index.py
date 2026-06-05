"""Parser for the MahaRERA project-index results page (captcha-free).

Selectors VERIFIED against live HTML captured 2026-06-01 (data/snapshots/.../raw_page_1.html).
The page is a Drupal site. Each project is a card:

    <div class="row shadow p-3 mb-5 bg-body rounded">
      <div class="col-xl-4">
        <p class="p-0"># P50500000005</p>
        <h4 class="title4"><strong>GREEN CITY 3</strong></h4>
        <p class="darkBlue bold">GREEN SPACE INFRA VENTURES</p>
        <ul class="listingList"><li><a href="...google.com/maps...">Nagpur (Rural)</a></li></ul>
      </div>
      <div class="col-xl-6">  <!-- labelled key/value pairs -->
        <div class="greyColor">State</div><p>MAHARASHTRA</p>
        <div class="greyColor">Pincode</div><p>441108</p>
        <div class="greyColor">District</div><p>Nagpur</p>
        <div class="greyColor">Last Modified</div><p>2017-05-20</p>
        <div class="greyColor">Extension Certificate</div><a>N/A</a>  <!-- delay signal! -->
      </div>
      <div class="col-xl-2"> ... <a href=".../project/view/1">View Details</a> ... </div>
    </div>

Data comes as <div class="greyColor">LABEL</div> followed by a <p> value, so we read
labels and pair each with its following value node. Everything degrades gracefully.
"""

from __future__ import annotations

import logging
import re

from selectolax.parser import HTMLParser, Node

from .models import ProjectIndexRow

log = logging.getLogger("honesthomes.parse_index")

# --- The single place to fix when real HTML differs ------------------------------
SELECTORS = {
    # The repeating project card. Verified class string. We match on the stable parts
    # ("shadow" + "rounded" bootstrap utility row) to survive minor class reordering.
    "row_candidates": [
        "div.row.shadow.rounded",
        "div[class*='shadow'][class*='rounded']",
    ],
    "id_and_name_block": ["div.col-xl-4"],
    "project_name": ["h4.title4", "h4"],
    "promoter_name": ["p.darkBlue", "p.bold"],
    "kv_label": ["div.greyColor"],
    "map_link": ["a[href*='google.com/maps']"],
    "detail_link": ["a[href*='project/view']"],
}

# "Showing Final <span>48228</span> Result" -> 48228. The count is wrapped in a
# <span>, so we strip tags between "Final" and "Result" before matching the digits.
_TOTAL_RE = re.compile(r"Showing\s+Final\s*<[^>]*>\s*([\d,]+)", re.IGNORECASE)
_TOTAL_RE_TEXT = re.compile(r"Showing\s+Final\s+([\d,]+)", re.IGNORECASE)
# "# P50500000005" -> P50500000005  (P=project, A=agent; ids are 'P' + digits)
_RERA_ID_RE = re.compile(r"\b(P\d{8,})\b")


def parse_total_count(html: str) -> int:
    """Pull the site-reported total ('Showing Final <span>N</span> Result'). 0 if absent.

    Tries the tag-wrapped form first (the live markup), then a plain-text fallback in
    case the span is ever removed.
    """
    m = _TOTAL_RE.search(html) or _TOTAL_RE_TEXT.search(html)
    if not m:
        return 0
    return int(m.group(1).replace(",", ""))


def _first(node: Node, selectors: list[str]) -> Node | None:
    for sel in selectors:
        found = node.css_first(sel)
        if found is not None:
            return found
    return None


def _text(node: Node | None) -> str:
    return node.text(strip=True) if node is not None else ""


def _find_rows(tree: HTMLParser) -> list[Node]:
    """Locate repeating project cards, trying candidate selectors until one hits."""
    for sel in SELECTORS["row_candidates"]:
        rows = tree.css(sel)
        if len(rows) > 1:  # a real list, not an incidental single match
            log.debug("matched %d rows via selector %r", len(rows), sel)
            return rows
    log.warning("no row selector matched — page structure likely changed")
    return []


def _read_kv(node: Node) -> dict[str, str]:
    """Read the card's labelled fields.

    Layout is ``<div class="greyColor">LABEL</div>`` followed by the value in the next
    sibling (a <p>, or an <a> for certificate fields). We walk each label and take the
    next element sibling's text as its value.
    """
    out: dict[str, str] = {}
    for label_node in node.css(SELECTORS["kv_label"][0]):
        label = label_node.text(strip=True).lower()
        value_node = label_node.next
        # skip whitespace/text nodes between the label and its value element
        while value_node is not None and value_node.tag in (None, "-text"):
            value_node = value_node.next
        if value_node is not None:
            out[label] = value_node.text(strip=True)
    return out


def _extract_row(node: Node, *, source_url: str, fetched_at: str) -> ProjectIndexRow | None:
    """Pull one project's index fields. Returns None if it has no usable RERA id."""
    # The id+name block is the first column; the id sits in a <p># Pxxxx</p>.
    head = _first(node, SELECTORS["id_and_name_block"]) or node
    m = _RERA_ID_RE.search(head.text(separator=" "))
    if not m:  # fall back to the whole card
        m = _RERA_ID_RE.search(node.text(separator=" "))
    if not m:
        return None  # without an id the row is useless for dedupe/diffing
    rera_id = m.group(1)

    name_node = _first(node, SELECTORS["project_name"])
    promoter_node = _first(node, SELECTORS["promoter_name"])
    detail_node = _first(node, SELECTORS["detail_link"])
    map_node = _first(node, SELECTORS["map_link"])
    kv = _read_kv(node)

    # The promoter <p> can collide with the id <p>; if promoter looks like the id, drop it.
    promoter = _text(promoter_node)
    if promoter.startswith("#") or _RERA_ID_RE.search(promoter):
        promoter = ""

    return ProjectIndexRow(
        rera_id=rera_id,
        project_name=_text(name_node),
        promoter_name=promoter,
        district=kv.get("district", ""),
        pincode=kv.get("pincode", ""),
        state=kv.get("state", "MAHARASHTRA"),
        last_modified=kv.get("last modified", ""),
        detail_url=detail_node.attributes.get("href", "") if detail_node else "",
        map_url=map_node.attributes.get("href", "") if map_node else "",
        source_url=source_url,
        fetched_at=fetched_at,
    )


def parse_index_page(
    html: str, *, source_url: str, fetched_at: str
) -> list[ProjectIndexRow]:
    """Parse one results page into rows. Never raises on bad structure — logs + skips."""
    tree = HTMLParser(html)
    rows: list[ProjectIndexRow] = []
    for node in _find_rows(tree):
        try:
            row = _extract_row(node, source_url=source_url, fetched_at=fetched_at)
        except Exception:  # one malformed card must not kill the whole page
            log.exception("failed to parse a project card; skipping it")
            continue
        if row is not None:
            rows.append(row)
    return rows
