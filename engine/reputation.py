"""Query reputation data from Supabase REST API."""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("honesthomes.reputation")

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://buhxytlquxsxziagooog.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ1aHh5dGxxdXhzeHppYWdvb29nIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA3MzE0NzYsImV4cCI6MjA5NjMwNzQ3Nn0.z-Tlbk9A843IPWrVtqEHRVKweOSwx-ndjBEfdc5ojAw"

COMPLAINTS_API = f"{SUPABASE_URL}/rest/v1/complaints"
REVOKED_API = f"{SUPABASE_URL}/rest/v1/revoked_projects"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Content-Type": "application/json",
}


class ReputationStore:
    def __init__(self) -> None:
        self.captured_at = "2026-06-04"
        self.loaded = False
        self._client = httpx.Client(timeout=10.0)
        self.total_complaint_promoters = 0
        self.total_revoked = 0

    def load_latest(self) -> bool:
        """Load reputation counts from Supabase REST API."""
        try:
            # Count complaints
            resp = self._client.get(
                f"{COMPLAINTS_API}?select=count()",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.total_complaint_promoters = data[0]["count"] if data else 0

            # Count revoked
            resp = self._client.get(
                f"{REVOKED_API}?select=count()",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.total_revoked = data[0]["count"] if data else 0

            self.loaded = True
            log.info("reputation loaded: %d complaint-promoters, %d revoked (snapshot %s)",
                     self.total_complaint_promoters, self.total_revoked, self.captured_at)
            return True
        except Exception as e:
            log.error("failed to load reputation: %s", e)
            return False

    def complaints_for(self, promoter: str) -> int | None:
        """Get complaint count for a builder."""
        if not self.loaded:
            return None
        try:
            # Case-insensitive search via REST API
            resp = self._client.get(
                f"{COMPLAINTS_API}?promoter=ilike.{promoter}&select=complaint_count",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                rows = resp.json()
                return rows[0]["complaint_count"] if rows else 0
            return None
        except Exception as e:
            log.error("complaints_for(%s) failed: %s", promoter, e)
            return None

    def is_revoked(self, rera_id: str, promoter: str = "") -> bool:
        """Check if a project is revoked."""
        if not self.loaded or not rera_id:
            return False
        try:
            resp = self._client.get(
                f"{REVOKED_API}?rera_id=eq.{rera_id}&select=rera_id",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                rows = resp.json()
                return len(rows) > 0
            return False
        except Exception:
            return False

    def revoked_count_for(self, promoter: str) -> int | None:
        """Get count of revoked projects for a builder."""
        if not self.loaded:
            return None
        try:
            resp = self._client.get(
                f"{REVOKED_API}?promoter=ilike.{promoter}&select=count()",
                headers=HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data[0]["count"] if data else 0
            return None
        except Exception as e:
            log.error("revoked_count_for(%s) failed: %s", promoter, e)
            return None
