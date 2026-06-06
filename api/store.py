"""Query projects from Supabase via REST API (more reliable than direct PostgreSQL)."""

from __future__ import annotations

import logging
import os
import httpx

log = logging.getLogger("honesthomes.store")

# Supabase REST API endpoint
SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://buhxytlquxsxziagooog.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ1aHh5dGxxdXhzeFppYWdvb29nIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MTc0NzE2NTEsImV4cCI6MTczMzAyMzY1MX0.MsaXkGhCl7gzCz5p4kU_EaZrZ4-dRvH6-4Z1W8L7u-0"

PROJECTS_API = f"{SUPABASE_URL}/rest/v1/projects"
COMPLAINTS_API = f"{SUPABASE_URL}/rest/v1/complaints"
REVOKED_API = f"{SUPABASE_URL}/rest/v1/revoked_projects"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Content-Type": "application/json",
}


class ProjectStore:
    def __init__(self) -> None:
        self.snapshot_date = "2026-06-02"
        self.total_reported = 48263
        self._client = httpx.Client(timeout=10.0)

    def load_latest(self) -> int:
        """Count projects via REST API."""
        try:
            resp = self._client.get(
                f"{PROJECTS_API}?select=count()",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                count = resp.json()[0]["count"]
                log.info("loaded %d projects (snapshot %s)", count, self.snapshot_date)
                return count
            else:
                log.error("API error %d: %s", resp.status_code, resp.text)
                return 0
        except Exception as e:
            log.error("failed to load from Supabase: %s", e)
            return 0

    def search(self, query: str = "", limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
        """Search projects via REST API."""
        try:
            q = query.strip().lower() if query else ""

            if not q:
                # Browse all
                resp = self._client.get(
                    f"{PROJECTS_API}?select=*&order=project_name.asc&limit={limit}&offset={offset}",
                    headers=HEADERS,
                )
                if resp.status_code != 200:
                    return [], 0

                rows = resp.json()

                # Get total count
                resp_count = self._client.get(
                    f"{PROJECTS_API}?select=count()",
                    headers=HEADERS,
                )
                total = resp_count.json()[0]["count"] if resp_count.status_code == 200 else 0
                return rows, total

            # Search by name, promoter, or district
            # Supabase full-text search is complex, so we do simple wildcard matching
            search_term = f"%{q}%"
            filter_str = f"or(project_name.ilike.{search_term},promoter_name.ilike.{search_term},district.ilike.{search_term},rera_id.ilike.{search_term})"

            resp = self._client.get(
                f"{PROJECTS_API}?{filter_str}&order=project_name.asc&limit={limit}&offset={offset}",
                headers=HEADERS,
            )

            if resp.status_code != 200:
                return [], 0

            rows = resp.json()

            # Get total matching count
            resp_count = self._client.get(
                f"{PROJECTS_API}?{filter_str}&select=count()",
                headers=HEADERS,
            )
            total = resp_count.json()[0]["count"] if resp_count.status_code == 200 else 0

            return rows, total
        except Exception as e:
            log.error("search failed: %s", e)
            return [], 0

    def get(self, rera_id: str) -> dict | None:
        """Fetch a single project by RERA ID."""
        try:
            resp = self._client.get(
                f"{PROJECTS_API}?rera_id=eq.{rera_id}",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                rows = resp.json()
                return rows[0] if rows else None
            return None
        except Exception as e:
            log.error("get(%s) failed: %s", rera_id, e)
            return None

    def count(self) -> int:
        """Return total project count."""
        try:
            resp = self._client.get(
                f"{PROJECTS_API}?select=count()",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                return resp.json()[0]["count"]
            return 0
        except Exception:
            return 0
