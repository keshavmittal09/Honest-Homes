"""Query projects from Supabase REST API (works over HTTPS, no port restrictions)."""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("honesthomes.store")

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://buhxytlquxsxziagooog.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ1aHh5dGxxdXhzeHppYWdvb29nIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA3MzE0NzYsImV4cCI6MjA5NjMwNzQ3Nn0.z-Tlbk9A843IPWrVtqEHRVKweOSwx-ndjBEfdc5ojAw"

PROJECTS_API = f"{SUPABASE_URL}/rest/v1/projects"

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
            # Use Prefer header to get count from response instead of aggregate
            resp = self._client.get(
                f"{PROJECTS_API}?select=rera_id&limit=1",
                headers={**HEADERS, "Prefer": "count=exact"},
            )
            if resp.status_code == 200:
                # Count is in Content-Range header
                count_header = resp.headers.get("content-range", "0/0").split("/")
                count = int(count_header[-1]) if len(count_header) > 1 else 0
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
                # Browse all with pagination
                resp = self._client.get(
                    f"{PROJECTS_API}?order=project_name.asc&limit={limit}&offset={offset}",
                    headers=HEADERS,
                )
                if resp.status_code != 200:
                    log.error("browse failed: %d %s", resp.status_code, resp.text)
                    return [], 0

                rows = resp.json()

                # Get total count
                resp_count = self._client.get(
                    f"{PROJECTS_API}?select=count()",
                    headers=HEADERS,
                )
                total = 0
                if resp_count.status_code == 200:
                    data = resp_count.json()
                    total = data[0]["count"] if data else 0

                return rows, total

            # Search by name, promoter, district, or rera_id
            # Build filter: or(project_name.ilike.X, promoter_name.ilike.X, ...)
            search_term = f"%{q}%"
            filters = [
                f"project_name.ilike.{search_term}",
                f"promoter_name.ilike.{search_term}",
                f"district.ilike.{search_term}",
                f"rera_id.ilike.{search_term}",
            ]
            filter_expr = "or(" + ",".join(filters) + ")"

            resp = self._client.get(
                f"{PROJECTS_API}?{filter_expr}&order=project_name.asc&limit={limit}&offset={offset}",
                headers=HEADERS,
            )

            if resp.status_code != 200:
                log.error("search failed: %d %s", resp.status_code, resp.text)
                return [], 0

            rows = resp.json()

            # Get total matching count
            resp_count = self._client.get(
                f"{PROJECTS_API}?{filter_expr}&select=count()",
                headers=HEADERS,
            )
            total = 0
            if resp_count.status_code == 200:
                data = resp_count.json()
                total = data[0]["count"] if data else 0

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
                f"{PROJECTS_API}?select=rera_id&limit=1",
                headers={**HEADERS, "Prefer": "count=exact"},
            )
            if resp.status_code == 200:
                count_header = resp.headers.get("content-range", "0/0").split("/")
                return int(count_header[-1]) if len(count_header) > 1 else 0
            return 0
        except Exception:
            return 0
