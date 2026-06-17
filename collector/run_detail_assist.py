"""Assistant-driven Tier-2 detail collector — with API capture + document download.

The MahaRERA detail page is an Angular app: all real data (and document URLs) come
from JSON API calls it makes after the captcha is solved. So we intercept those
responses (clean structured data), download every PDF/document the page loads, and
also click the "Click here to view" panels to surface lazy-loaded documents. The
human only ever solves captchas.

Driven by control files under data/snapshots/detail/.assist/:
  status.json  <- progress / what it's waiting for
  command      -> "capture" | "skip" | "stop"  (consumed by this script)

Per project, under data/snapshots/detail/<date>/:
  <RID>.html        rendered page
  <RID>.json        generic extraction (tables/fields/text)
  <RID>.api.json    every JSON API response the page made (the structured gold)
  docs/<RID>/...     downloaded documents (certificates, Form 3, etc.)
"""

from __future__ import annotations

import datetime
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from .parse_detail import extract_detail
from .run_detail import _load_index, _targets

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "data" / "snapshots" / "detail"
CTL = OUT_ROOT / ".assist"
HOST = "maharerait.maharashtra.gov.in"

POLL = 1.0
PER_PROJECT_MAX = 1800
OVERALL_MAX = 7200

_DOC_EXT = (".pdf", ".xls", ".xlsx", ".doc", ".docx", ".jpg", ".jpeg", ".png")
_DOC_URL_RE = re.compile(r'https?://[^\s"\'<>]+\.(?:pdf|xls|xlsx|doc|docx)', re.I)

# Per-project capture buckets (reset each project; read by the response handler).
STATE: dict = {"api": [], "docs": [], "seen": set(), "docs_dir": None}


def _write_status(**kw) -> None:
    CTL.mkdir(parents=True, exist_ok=True)
    kw["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    tmp = CTL / "status.tmp"
    tmp.write_text(json.dumps(kw, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CTL / "status.json")


def _read_command() -> str | None:
    f = CTL / "command"
    if not f.exists():
        return None
    try:
        cmd = f.read_text(encoding="utf-8").strip().lower()
        f.unlink()
    except Exception:
        return None
    return cmd or None


def _safe_name(url: str, ct: str) -> str:
    base = os.path.basename(unquote(urlparse(url).path)) or "file"
    if "." not in base:
        base += ".pdf" if "pdf" in ct else ".bin"
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120]


def _save_doc(data: bytes, url: str, ct: str) -> dict | None:
    d = STATE["docs_dir"]
    if not d or not data:
        return None
    d.mkdir(parents=True, exist_ok=True)
    name = _safe_name(url, ct)
    p, k = d / name, 1
    while p.exists():
        p, k = d / f"{k}_{name}", k + 1
    p.write_bytes(data)
    rec = {"url": url, "file": p.name, "bytes": len(data)}
    STATE["docs"].append(rec)
    return rec


def _on_response(resp) -> None:
    try:
        url = resp.url
        if HOST not in url or url in STATE["seen"]:
            return
        ct = ((resp.headers or {}).get("content-type", "") or "").lower()
        low = url.lower().split("?")[0]
        if "application/json" in ct:
            STATE["seen"].add(url)
            try:
                body = resp.json()
            except Exception:
                try:
                    body = resp.text()
                except Exception:
                    body = None
            STATE["api"].append({"url": url, "status": resp.status, "json": body})
        elif ("application/pdf" in ct or "octet-stream" in ct or "application/vnd" in ct
              or "msword" in ct or low.endswith(_DOC_EXT)):
            STATE["seen"].add(url)
            try:
                data = resp.body()
            except Exception:
                data = None
            if data:
                _save_doc(data, url, ct)
    except Exception:
        pass


def _trigger_lazy(page) -> None:
    """Click 'Click here to view' / 'Click to see list' panels to force lazy loads."""
    for ph in ("Click here to view", "Click to see list", "Click to view", "View Document"):
        try:
            loc = page.locator(f"text={ph}")
            n = min(loc.count(), 15)
        except Exception:
            n = 0
        for i in range(n):
            try:
                loc.nth(i).scroll_into_view_if_needed(timeout=2500)
                loc.nth(i).click(timeout=2500)
                page.wait_for_timeout(1600)   # let modal/api/pdf load (intercepted)
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
            except Exception:
                pass


def _download_doc_urls_from_json(ctx) -> None:
    """Scan captured API JSON for document URLs and fetch any not already saved."""
    urls = set()
    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            urls.update(_DOC_URL_RE.findall(o))
    for item in STATE["api"]:
        walk(item.get("json"))
    for u in urls:
        if u in STATE["seen"]:
            continue
        STATE["seen"].add(u)
        try:
            r = ctx.request.get(u, timeout=30000)
            if r.ok:
                _save_doc(r.body(), u, (r.headers or {}).get("content-type", ""))
        except Exception:
            pass


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _write_status(state="error", message="playwright not installed")
        raise SystemExit("playwright not installed")

    index = _load_index()
    targets = _targets("collector/targets.txt", index, 10)
    out_dir = OUT_ROOT / datetime.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    CTL.mkdir(parents=True, exist_ok=True)
    _read_command()

    captured: list[dict] = []
    started = time.time()
    _write_status(state="starting", total=len(targets), captured=0, message="launching Edge")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, channel="msedge")
        ctx = browser.new_context(viewport={"width": 1320, "height": 920}, accept_downloads=True)
        page = ctx.new_page()
        page.on("response", _on_response)

        for i, rid in enumerate(targets, 1):
            row = index.get(rid, {})
            url = row.get("detail_url") or ""
            name = row.get("project_name", "(unknown)")
            if (out_dir / f"{rid}.json").exists() or not url:
                continue

            # reset per-project buckets
            STATE["api"], STATE["docs"], STATE["seen"] = [], [], set()
            STATE["docs_dir"] = out_dir / "docs" / rid

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                _write_status(state="nav_warn", index=i, total=len(targets), rid=rid,
                              name=name, url=url, captured=len(captured), message=str(e))

            _write_status(state="awaiting", index=i, total=len(targets), rid=rid, name=name,
                          url=url, captured=len(captured),
                          message=f"Solve the captcha for {name} in Edge, then I'll capture (+docs).")

            t0, action = time.time(), None
            while action is None:
                if time.time() - started > OVERALL_MAX or time.time() - t0 > PER_PROJECT_MAX:
                    action = "skip"; break
                cmd = _read_command()
                if cmd in ("capture", "skip", "stop"):
                    action = cmd; break
                time.sleep(POLL)

            if action == "stop":
                _write_status(state="stopped", captured=len(captured), message="stopped by driver")
                break
            if action == "skip":
                captured.append({"rera_id": rid, "project_name": name, "summary": "skipped"})
                continue

            _write_status(state="capturing", index=i, total=len(targets), rid=rid, name=name,
                          captured=len(captured), message="expanding panels + downloading docs…")
            try:
                page.wait_for_timeout(800)          # let initial API calls settle
                _trigger_lazy(page)                 # click to surface lazy docs
                _download_doc_urls_from_json(ctx)   # fetch doc URLs found in API JSON
            except Exception:
                pass

            html = page.content()
            data = extract_detail(html, rera_id=rid, source_url=url)
            data["project_name"] = name
            data["promoter_name"] = row.get("promoter_name", "")
            data["captured_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            data["api_response_count"] = len(STATE["api"])
            data["documents"] = STATE["docs"]

            (out_dir / f"{rid}.html").write_text(html, encoding="utf-8")
            (out_dir / f"{rid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            (out_dir / f"{rid}.api.json").write_text(
                json.dumps(STATE["api"], ensure_ascii=False, indent=2), encoding="utf-8")

            summ = (f"tables={len(data['tables'])} fields={len(data['key_values'])} "
                    f"api={len(STATE['api'])} docs={len(STATE['docs'])} text={data['text_length']}")
            captured.append({"rera_id": rid, "project_name": name, "summary": summ})
            _write_status(state="saved", index=i, total=len(targets), rid=rid, name=name,
                          captured=len(captured), last=summ, message=f"saved {name}: {summ}")

        browser.close()

    snap = {
        "captured_at": datetime.date.today().isoformat(),
        "source": "maharerait.maharashtra.gov.in/public/project/view (assist + api + docs)",
        "count": len([c for c in captured if "tables=" in c.get("summary", "")]),
        "projects": captured,
    }
    (out_dir / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_status(state="done", total=len(targets), captured=len(captured),
                  message=f"finished — {snap['count']} captured", projects=captured)


if __name__ == "__main__":
    main()
