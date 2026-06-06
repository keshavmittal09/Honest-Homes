"""Query projects from Supabase PostgreSQL database."""

from __future__ import annotations

import logging
import os
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger("honesthomes.store")

SUPABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:honesthomes_001@db.buhxytlquxsxziagooog.supabase.co:5432/postgres"


class ProjectStore:
    def __init__(self) -> None:
        self._conn: Optional[psycopg2.extensions.connection] = None
        self.snapshot_date = "2026-06-02"
        self.total_reported = 48263

    def _get_conn(self) -> psycopg2.extensions.connection:
        """Get or reuse database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(SUPABASE_URL, sslmode="prefer", connect_timeout=5)
        return self._conn

    def load_latest(self) -> int:
        """Connect to Supabase and count projects."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM projects")
                count = cur.fetchone()[0]
            log.info("loaded %d projects (snapshot %s)", count, self.snapshot_date)
            return count
        except Exception as e:
            log.error("failed to load from Supabase: %s", e)
            return 0

    def search(self, query: str = "", limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
        """Search projects. Returns (results, total_count)."""
        try:
            conn = self._get_conn()
            q = query.strip().lower() if query else ""

            if not q:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT COUNT(*) FROM projects")
                    total = cur.fetchone()[0]
                    cur.execute(
                        "SELECT * FROM projects ORDER BY project_name LIMIT %s OFFSET %s",
                        (limit, offset),
                    )
                    rows = [dict(r) for r in cur.fetchall()]
                return rows, total

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM projects
                    WHERE LOWER(project_name) LIKE %s
                       OR LOWER(promoter_name) LIKE %s
                       OR LOWER(district) LIKE %s
                       OR LOWER(rera_id) LIKE %s
                    """,
                    (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"),
                )
                total = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT * FROM projects
                    WHERE LOWER(project_name) LIKE %s
                       OR LOWER(promoter_name) LIKE %s
                       OR LOWER(district) LIKE %s
                       OR LOWER(rera_id) LIKE %s
                    ORDER BY project_name
                    LIMIT %s OFFSET %s
                    """,
                    (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", limit, offset),
                )
                rows = [dict(r) for r in cur.fetchall()]

            return rows, total
        except Exception as e:
            log.error("search failed: %s", e)
            return [], 0

    def get(self, rera_id: str) -> dict | None:
        """Fetch a single project by RERA ID."""
        try:
            conn = self._get_conn()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM projects WHERE rera_id = %s", (rera_id,))
                row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            log.error("get(%s) failed: %s", rera_id, e)
            return None

    def count(self) -> int:
        """Return total project count."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM projects")
                return cur.fetchone()[0]
        except Exception:
            return 0
