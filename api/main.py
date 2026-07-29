"""Honest Homes API + static frontend.

Endpoints:
  GET /api/health           -> status + dataset size
  GET /api/search?q=...     -> matching projects (index fields)
  GET /api/project/{id}     -> one project + its honest verdict
The frontend (web/) is served as static files at /.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
from pathlib import Path

import httpx

# Load a local .env for development convenience. In production (Render) the
# environment variables come from the dashboard, so a missing .env or missing
# python-dotenv is perfectly fine.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from engine.verdict import build_verdict
from .store import ProjectStore
from .shape import project_to_card, project_to_full, builder_stub, load_reputation, load_detail, REPUTATION, DETAIL

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("honesthomes.api")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Honest Homes API", version="0.1.0")
store = ProjectStore()


@app.on_event("startup")
def _load() -> None:
    import sys
    log.info("Python version: %s", sys.version)
    # Supabase is NOT a data source. Project/reputation/detail data all come from
    # the JSONL + JSON snapshots committed in data/. Supabase is only ever used to
    # store submitted leads, and only when SUPABASE_KEY is set.
    log.info("lead storage: supabase %s", "configured" if os.getenv("SUPABASE_KEY") else "NOT configured")

    try:
        n = store.load_latest()
        if n == 0:
            log.error("CRITICAL: No projects loaded from the committed snapshot")
        else:
            log.info("loaded %d projects from the committed data/ snapshot", n)
    except Exception as e:
        log.error("FAILED to load projects: %s", e, exc_info=True)

    try:
        if load_reputation():
            log.info("reputation loaded: %d complaint-promoters, %d revoked",
                     REPUTATION.total_complaint_promoters, REPUTATION.total_revoked)
        else:
            log.info("no reputation data loaded")
    except Exception as e:
        log.error("FAILED to load reputation: %s", e, exc_info=True)

    try:
        if load_detail():
            log.info("tier-2 detail loaded: %d projects (snapshot %s, docs_available=%s)",
                     len(DETAIL.records), DETAIL.captured_at, DETAIL.docs_available)
            # Only probe the external document host when we are NOT shipping the
            # files ourselves — if they're local, external reachability is moot.
            if not DETAIL.docs_available:
                sample = DETAIL.sample_external_url()
                if DETAIL.probe_external():
                    log.info("external document host reachable")
                else:
                    log.warning(
                        "external document host UNREACHABLE (%s) — document links will be "
                        "shown as unavailable. Ship the files with the app "
                        "(data/snapshots/detail/<date>/docs/) or re-upload to a live host.",
                        sample or "no URL recorded")
        else:
            log.info("no tier-2 detail data loaded")
    except Exception as e:
        log.error("FAILED to load detail: %s", e, exc_info=True)


@app.get("/api/health")
def health() -> dict:
    """Status + enough config diagnostics to tell, from outside, whether the
    deployment is actually wired up. Reports only booleans and hostnames — never
    a key. Without this there is no way to distinguish "leads are being stored"
    from "leads are being silently dropped", because /api/lead answers the
    visitor optimistically either way.
    """
    key = os.getenv("SUPABASE_KEY", "")
    return {
        "status": "ok",
        "projects_loaded": store.count(),
        "snapshot_date": store.snapshot_date,
        "total_in_rera": store.total_reported,
        "detail_projects": len(DETAIL.records) if DETAIL.loaded else 0,
        "lead_storage": "supabase" if key else "EPHEMERAL FILE — submissions are lost on restart",
        "supabase_host": (os.getenv("SUPABASE_URL", "") or "").replace("https://", "").rstrip("/") or None,
        "documents": "local" if DETAIL.docs_available else ("external" if DETAIL.external_ok else "unavailable"),
    }


LEADS_FILE = Path(__file__).resolve().parent.parent / "data" / "leads.jsonl"

# Best-effort in-memory rate limit (per client IP). Single Render instance, so a
# plain dict is fine; it just blunts casual spam/abuse of the public endpoint.
_RATE: dict[str, list[float]] = {}
_RATE_MAX = 12          # submissions
_RATE_WINDOW = 600      # per 10 minutes


def _rate_ok(ip: str) -> bool:
    import time
    now = time.time()
    hits = [t for t in _RATE.get(ip, []) if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_MAX:
        _RATE[ip] = hits
        return False
    hits.append(now)
    _RATE[ip] = hits
    return True


def _mask(phone: str) -> str:
    p = "".join(ch for ch in phone if ch.isdigit())
    return ("*" * max(0, len(p) - 4) + p[-4:]) if p else ""


async def _supabase_insert(rec: dict) -> bool:
    """Insert a submission into Supabase (durable). No-op unless SUPABASE_KEY is set.
    Uses the service key server-side only; the table has RLS on with no public
    policies, so submissions are never readable by the anon/public API."""
    url = os.getenv("SUPABASE_URL", "https://buhxytlquxsxziagooog.supabase.co").rstrip("/")
    key = os.getenv("SUPABASE_KEY", "")
    if not key:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{url}/rest/v1/submissions",
                headers={"apikey": key, "Authorization": f"Bearer {key}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                json={"type": rec["type"], "name": rec["name"], "phone": rec["phone"],
                      "project": rec["project"], "project_id": rec["project_id"], "message": rec["message"]},
            )
        if r.status_code in (200, 201, 204):
            return True
        log.error("supabase insert HTTP %s: %s", r.status_code, r.text[:200])
        return False
    except Exception as e:
        log.error("supabase insert failed: %s", e)
        return False


@app.post("/api/lead")
async def lead(payload: dict, request: Request) -> dict:
    """Capture a visitor submission — unlock lead, project request, or inquiry.

    Stored to data/leads.jsonl AND logged (phone masked). NOTE: on Render's free
    tier the filesystem is ephemeral, so for durable storage set
    HH_CONTACT_FORM_ENDPOINT (frontend posts there) or wire a database.
    """
    ip = (request.client.host if request.client else "?")
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="too many requests, please try again later")

    kind = str(payload.get("type", "lead"))[:24].strip() or "lead"
    rec = {
        "type": kind,
        "name": str(payload.get("name", ""))[:120].strip(),
        "phone": str(payload.get("phone", ""))[:40].strip(),
        "project": str(payload.get("project", ""))[:200].strip(),
        "project_id": str(payload.get("projectId", ""))[:40].strip(),
        "message": str(payload.get("message", ""))[:2000].strip(),
        "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    if not rec["name"] or not rec["phone"]:
        raise HTTPException(status_code=400, detail="name and phone are required")

    stored = await _supabase_insert(rec)          # durable store (when configured)
    try:                                          # local backup / dev visibility
        LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LEADS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # never fail the user's submission on a storage hiccup
        log.error("lead write failed: %s", e)
    if not stored:
        # Loud, because the fallback file is on an ephemeral disk: on Render this
        # submission is gone at the next restart. Silent success here is how leads
        # disappear without anyone noticing.
        log.error("LEAD NOT DURABLY STORED — SUPABASE_KEY missing or insert failed. "
                  "Submission kept only in the ephemeral %s", LEADS_FILE.name)
    log.info("SUBMIT[%s] %s | %s | %s (durable=%s)", kind, rec["name"], _mask(rec["phone"]), rec["project"], stored)
    # `stored` tells an operator whether this actually landed somewhere permanent.
    # The visitor still sees success either way — their submission is not their problem.
    return {"ok": True, "stored": stored}


@app.get("/api/config")
def config() -> dict:
    """PUBLIC, browser-safe config only. Never put secret keys here — this is
    fetched by the frontend and visible to anyone. Values come from env vars
    (.env locally, Render dashboard in prod) so they can change without a code
    edit. Falls back to sensible defaults when unset.
    """
    return {
        "contact": {
            "email": os.getenv("HH_CONTACT_EMAIL", "29925keshav@gmail.com"),
            "formEndpoint": os.getenv("HH_CONTACT_FORM_ENDPOINT", ""),
            "whatsapp": os.getenv("HH_CONTACT_WHATSAPP", ""),
        }
    }


@app.get("/api/search")
def search(q: str = "", offset: int = 0, limit: int = 30) -> dict:
    # store.search returns (rows, total); unpacking it matters — treating the tuple
    # as the result list made `count` always 2 and `results` a [rows, total] pair.
    limit = max(1, min(limit, 60))
    results, total = store.search(q, limit=limit, offset=offset)
    return {
        "query": q,
        "count": len(results),
        "total": total,
        "offset": offset,
        "limit": limit,
        "results": results,
        "snapshot_date": store.snapshot_date,
    }


@app.get("/api/project/{rera_id}")
def project(rera_id: str) -> dict:
    row = store.get(rera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found in current snapshot")
    verdict = build_verdict(row, reputation=REPUTATION)
    return {"project": row, "verdict": verdict.to_dict()}


# --- design-shaped endpoints (feed the Claude-design HH_DATA front-end) ------------
@app.get("/api/hh/featured")
def hh_featured() -> dict:
    """A non-empty set of cards for the landing grid (so the portal is never blank)."""
    rows, _total = store.search("", limit=8)
    return {
        "as_of": store.snapshot_date,
        "indexed": store.total_reported,
        "loaded": store.count(),
        "cards": [project_to_card(r) for r in rows],
    }


@app.get("/api/hh/search")
def hh_search(q: str = "", offset: int = 0, limit: int = 30) -> dict:
    """Paginated search/browse. Returns this page of cards plus the total match count
    so the UI can show 'X of Y' and a working 'Load more'."""
    limit = max(1, min(limit, 60))  # guard
    rows, total = store.search(q, limit=limit, offset=offset)
    return {
        "query": q,
        "offset": offset,
        "limit": limit,
        "total": total,
        "loaded": store.count(),
        "cards": [project_to_card(r) for r in rows],
    }


@app.get("/api/hh/nearby")
def hh_nearby(lat: float, lng: float, km: float = 10.0, limit: int = 24) -> dict:
    """Projects closest to a point, nearest first.

    Only projects we hold Tier-2 detail for can appear: the index snapshot has no
    usable coordinates (its map_url is empty for all but one of 44,279 rows), so
    coordinates exist solely for the deep-collected set. The response says how
    many that is, because "nothing near you" must not be mistaken for "nothing
    exists near you".
    """
    import math

    if not DETAIL.loaded:
        return {"cards": [], "searched": 0, "radiusKm": km}

    km = max(0.5, min(km, 100.0))
    limit = max(1, min(limit, 60))
    hits = []
    for rid, rec in DETAIL.records.items():
        g = rec.get("geo") or {}
        if not (g.get("lat") and g.get("lng")):
            continue
        # equirectangular approximation — accurate well inside a city, and far
        # cheaper than haversine across every record on each request
        dlat = math.radians(g["lat"] - lat)
        dlng = math.radians(g["lng"] - lng) * math.cos(math.radians((g["lat"] + lat) / 2))
        d = 6371.0 * math.sqrt(dlat * dlat + dlng * dlng)
        if d <= km:
            hits.append((d, rid))

    hits.sort()
    cards = []
    for d, rid in hits[:limit]:
        row = store.get(rid)
        if row is None:
            continue
        card = project_to_card(row)
        card["distanceKm"] = round(d, 2)
        rec = DETAIL.records.get(rid) or {}
        addr = rec.get("address") or {}
        card["area"] = addr.get("village") or addr.get("taluka") or card.get("district")
        cards.append(card)

    return {
        "cards": cards,
        "radiusKm": km,
        "searched": sum(1 for r in DETAIL.records.values() if (r.get("geo") or {}).get("lat")),
        "found": len(hits),
    }


@app.get("/api/hh/project/{rera_id}")
def hh_project(rera_id: str) -> dict:
    row = store.get(rera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    full = project_to_full(row)
    return {"project": full, "builder": builder_stub(row), "as_of": store.snapshot_date}


@app.get("/api/hh/doc/{rera_id}/{filename}")
def hh_doc(rera_id: str, filename: str) -> FileResponse:
    """Serve a captured Tier-2 document file. Opens INLINE in the browser (PDF
    viewer / image) so users can read it; they can download from there."""
    p = DETAIL.doc_path(rera_id, filename) if DETAIL.loaded else None
    if p is None:
        raise HTTPException(status_code=404, detail="document not available")
    return FileResponse(p, content_disposition_type="inline")


# --- static frontend ---------------------------------------------------------------
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


_OG_ESCAPE = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})


def _page(title: str = "", description: str = "", url: str = "") -> HTMLResponse:
    """index.html with per-page social/SEO tags injected.

    A hash route (#/verdict/x) is never sent to the server, so every share on
    WhatsApp and every crawl by Google saw the same generic homepage. Real paths
    let each verdict carry its own title, description and preview card — which
    matters for a product whose growth is people sharing a verdict.
    """
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    if not title:
        return HTMLResponse(html)

    t = title.translate(_OG_ESCAPE)
    d = description.translate(_OG_ESCAPE)
    tags = (
        f"<title>{t}</title>\n"
        f'<meta name="description" content="{d}" />\n'
        f'<meta property="og:type" content="article" />\n'
        f'<meta property="og:title" content="{t}" />\n'
        f'<meta property="og:description" content="{d}" />\n'
        f'<meta property="og:url" content="{url}" />\n'
        f'<meta name="twitter:card" content="summary" />\n'
        f'<meta name="twitter:title" content="{t}" />\n'
        f'<meta name="twitter:description" content="{d}" />\n'
    )
    html = re.sub(r"<title>.*?</title>", "", html, count=1, flags=re.S)
    return HTMLResponse(html.replace("</head>", tags + "</head>", 1))


@app.get("/")
def index() -> HTMLResponse:
    return _page()


@app.get("/verdict/{rera_id}")
def page_verdict(rera_id: str, request: Request) -> HTMLResponse:
    row = store.get(rera_id)
    if row is None:
        return _page()
    v = build_verdict(row, reputation=REPUTATION, detail=DETAIL.get(rera_id))
    name = row.get("project_name") or rera_id
    builder = row.get("promoter_name") or "the builder"
    score = "" if v.score is None else f"{v.score}/10 — "
    return _page(
        title=f"{name} — MahaRERA verdict | Honest Homes",
        description=f"{score}{v.headline} Sourced from the official MahaRERA record for {name} by {builder}.",
        url=str(request.url),
    )


@app.get("/search/{q}")
def page_search(q: str, request: Request) -> HTMLResponse:
    return _page(title=f'"{q}" — MahaRERA project search | Honest Homes',
                 description=f'Trust verdicts for MahaRERA-registered projects matching "{q}".',
                 url=str(request.url))


@app.get("/search")
@app.get("/report/{rera_id}")
def page_plain(rera_id: str = "") -> HTMLResponse:
    return _page()
