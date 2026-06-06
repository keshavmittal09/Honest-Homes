"""Query reputation data (complaints, revocations) from Supabase.

Joins reputation data to a project by:
  • promoter name  -> complaints (normalised match)
  • rera_id / promoter -> revoked status

Builder-name matching is deliberately conservative: we normalise (lowercase, strip
punctuation/whitespace/legal suffixes) and match exactly on the normalised key. This
avoids false "this builder has complaints" claims — on a trust product, a false negative
(missing a match) is far safer than a false positive (smearing a clean builder).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger("honesthomes.reputation")

SUPABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:honesthomes_001@db.buhxytlquxsxziagooog.supabase.co:5432/postgres"

# Legal-form suffixes stripped during normalisation so "Lodha Developers Ltd" and
# "Lodha Developers Limited" match.
_SUFFIXES = re.compile(
    r"\b(private|pvt|limited|ltd|llp|developers?|builders?|constructions?|"
    r"realty|infra(structure)?|estates?|enterprises?|ventures?|co|company|and|&)\b",
    re.IGNORECASE,
)
_NONWORD = re.compile(r"[^a-z0-9]+")


def normalise_name(name: str) -> str:
    s = (name or "").lower()
    s = _SUFFIXES.sub(" ", s)
    s = _NONWORD.sub(" ", s)
    return " ".join(s.split())


class ReputationStore:
    def __init__(self) -> None:
        self.captured_at = "2026-06-04"
        self.loaded = False
        self._conn: Optional[psycopg2.extensions.connection] = None
        self.total_complaint_promoters = 0
        self.total_revoked = 0

    def _get_conn(self) -> psycopg2.extensions.connection:
        """Get or reuse database connection."""
        if self._conn is None or self._conn.closed:
            try:
                self._conn = psycopg2.connect(SUPABASE_URL, sslmode="require", connect_timeout=5)
            except Exception as e:
                log.warning("SSL connection failed: %s, trying without SSL", e)
                try:
                    self._conn = psycopg2.connect(SUPABASE_URL, connect_timeout=5)
                except Exception as e2:
                    log.error("Database connection failed: %s", e2)
                    raise
        return self._conn

    def load_latest(self) -> bool:
        """Connect to Supabase and load reputation counts."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM complaints")
                self.total_complaint_promoters = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM revoked_projects")
                self.total_revoked = cur.fetchone()[0]
            self.loaded = True
            log.info("reputation loaded: %d complaint-promoters, %d revoked (snapshot %s)",
                     self.total_complaint_promoters, self.total_revoked, self.captured_at)
            return True
        except Exception as e:
            log.error("failed to load reputation: %s", e)
            return False

    def complaints_for(self, promoter: str) -> int | None:
        """Get complaint count for a builder from Supabase."""
        if not self.loaded:
            return None
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT complaint_count FROM complaints WHERE LOWER(promoter) = LOWER(%s)",
                    (promoter,),
                )
                row = cur.fetchone()
            return row[0] if row else 0
        except Exception as e:
            log.error("complaints_for(%s) failed: %s", promoter, e)
            return None

    def is_revoked(self, rera_id: str, promoter: str = "") -> bool:
        """Check if a project is revoked."""
        if not self.loaded or not rera_id:
            return False
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM revoked_projects WHERE rera_id = %s", (rera_id,))
            return bool(cur.fetchone())
        except Exception:
            return False

    def revoked_count_for(self, promoter: str) -> int | None:
        """Get count of revoked projects for a builder."""
        if not self.loaded:
            return None
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM revoked_projects WHERE LOWER(promoter) = LOWER(%s)",
                    (promoter,),
                )
                return cur.fetchone()[0]
        except Exception as e:
            log.error("revoked_count_for(%s) failed: %s", promoter, e)
            return None
