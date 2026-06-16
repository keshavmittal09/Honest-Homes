"""Generic, structure-agnostic extractor for a MahaRERA project DETAIL page.

We have not hard-coded this portal's exact markup on purpose: the detail page is
captcha-gated, so until we capture a real one we don't know its precise structure.
This extractor therefore captures EVERYTHING it can find — every table, every
label/value pair, every heading, every document link, and the full visible text —
so the first human-in-the-loop capture yields complete data. Once we can see real
captured HTML we can tighten this into named fields (area, price, timeline, …).

Pure parsing, no network. Safe to re-run on saved HTML.
"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

_WS = re.compile(r"\s+")


def _clean(s: str) -> str:
    return _WS.sub(" ", (s or "").replace("\xa0", " ")).strip()


def _tables(tree: HTMLParser) -> list[dict]:
    """Every <table> as {caption, rows}. Two-column tables also exposed as kv."""
    out: list[dict] = []
    for t in tree.css("table"):
        rows: list[list[str]] = []
        for tr in t.css("tr"):
            cells = [_clean(td.text()) for td in tr.css("th,td")]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        cap_node = t.css_first("caption")
        table = {"caption": _clean(cap_node.text()) if cap_node else "", "rows": rows}
        # If it's a clean 2-column table, also give it as a dict.
        if rows and all(len(r) == 2 for r in rows):
            table["kv"] = {_clean(r[0]): _clean(r[1]) for r in rows if r[0]}
        out.append(table)
    return out


def _key_values(tree: HTMLParser) -> dict:
    """Best-effort label→value pairs from several common markup shapes."""
    kv: dict[str, str] = {}

    # <dl><dt>label</dt><dd>value</dd>
    for dl in tree.css("dl"):
        dts = dl.css("dt")
        dds = dl.css("dd")
        for dt, dd in zip(dts, dds):
            k = _clean(dt.text())
            if k:
                kv.setdefault(k, _clean(dd.text()))

    # Labelled blocks: an element with a "label/greyColor/control-label/text-muted"
    # class followed by its value sibling/parent text. Captures Bootstrap/Drupal forms.
    label_sel = (
        "[class*='label'], .greyColor, .control-label, .text-muted, "
        "label, .field-label, strong, b"
    )
    for node in tree.css(label_sel):
        k = _clean(node.text())
        if not k or len(k) > 60 or k in kv:
            continue
        val = ""
        nxt = node.next
        # skip whitespace text nodes
        while nxt is not None and not _clean(getattr(nxt, "text", lambda: "")()):
            nxt = nxt.next
        if nxt is not None:
            val = _clean(nxt.text())
        if val and val != k and len(val) < 200:
            kv.setdefault(k.rstrip(":"), val)

    return kv


def _doc_links(tree: HTMLParser) -> list[dict]:
    out = []
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "") or ""
        text = _clean(a.text())
        low = href.lower()
        if any(low.endswith(e) for e in (".pdf", ".xls", ".xlsx", ".doc", ".docx")) or "download" in low:
            out.append({"text": text, "href": href})
    return out


def extract_detail(html: str, *, rera_id: str = "", source_url: str = "") -> dict:
    """Return a dict with everything we could pull from the detail page HTML."""
    tree = HTMLParser(html)

    # Drop chrome/nav/script/style before reading the visible text.
    for sel in ("script", "style", "noscript", "header", "footer", "nav"):
        for n in tree.css(sel):
            n.decompose()

    headings = [_clean(h.text()) for h in tree.css("h1,h2,h3,h4") if _clean(h.text())]
    body = tree.css_first("body") or tree
    full_text = _clean(body.text())

    return {
        "rera_id": rera_id,
        "source_url": source_url,
        "headings": headings,
        "tables": _tables(tree),
        "key_values": _key_values(tree),
        "document_links": _doc_links(tree),
        "text_excerpt": full_text[:4000],
        "text_length": len(full_text),
    }
