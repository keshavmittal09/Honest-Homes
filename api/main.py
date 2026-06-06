"""Honest Homes API + static frontend.

Endpoints:
  GET /api/health           -> status + dataset size
  GET /api/search?q=...     -> matching projects (index fields)
  GET /api/project/{id}     -> one project + its honest verdict
The frontend (web/) is served as static files at /.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine.verdict import build_verdict
from .store import ProjectStore
from .shape import project_to_card, project_to_full, builder_stub, load_reputation, REPUTATION

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("honesthomes.api")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Honest Homes API", version="0.1.0")
store = ProjectStore()


@app.on_event("startup")
def _load() -> None:
    import sys
    log.info("Python version: %s", sys.version)
    log.info("SUPABASE_URL: %s", os.getenv("SUPABASE_URL", "(using default)"))
    log.info("SUPABASE_KEY: %s", "***" if os.getenv("SUPABASE_KEY") else "(using default)")

    try:
        n = store.load_latest()
        if n == 0:
            log.error("CRITICAL: No projects loaded from REST API")
        else:
            log.info("Successfully loaded %d projects from Supabase REST API", n)
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


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "projects_loaded": store.count(),
        "snapshot_date": store.snapshot_date,
        "total_in_rera": store.total_reported,
    }


@app.get("/api/search")
def search(q: str = "") -> dict:
    results = store.search(q)
    return {
        "query": q,
        "count": len(results),
        "results": results,
        "snapshot_date": store.snapshot_date,
    }


@app.get("/api/project/{rera_id}")
def project(rera_id: str) -> dict:
    row = store.get(rera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found in current snapshot")
    verdict = build_verdict(row)
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


@app.get("/api/hh/project/{rera_id}")
def hh_project(rera_id: str) -> dict:
    row = store.get(rera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    full = project_to_full(row)
    return {"project": full, "builder": builder_stub(row), "as_of": store.snapshot_date}


# --- static frontend ---------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
