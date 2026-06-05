"""In-memory store loaded from the newest index snapshot.

For the demo we load the latest dated snapshot into memory and search it directly.
This is deliberately simple — a real DB (SQLite/Postgres) slots in behind this same
interface later without changing the API or frontend.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("honesthomes.store")

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


class ProjectStore:
    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self.snapshot_date = ""
        self.total_reported = 0

    def load_latest(self) -> int:
        """Load the most recent index snapshot. Prefers snapshot.json, falls back to
        the append-only rows.jsonl (useful while a collection run is still finishing)."""
        snaps = sorted(
            glob.glob(str(DATA_ROOT / "snapshots" / "index" / "*" / "snapshot.json")),
            key=os.path.getmtime,
        )
        rows: list[dict] = []
        if snaps:
            data = json.loads(Path(snaps[-1]).read_text(encoding="utf-8"))
            rows = data.get("rows", [])
            self.snapshot_date = data.get("captured_at", "")
            self.total_reported = data.get("total_reported", 0)
        else:
            # fall back to newest rows.jsonl
            jsonls = sorted(
                glob.glob(str(DATA_ROOT / "snapshots" / "index" / "*" / "rows.jsonl")),
                key=os.path.getmtime,
            )
            if jsonls:
                p = Path(jsonls[-1])
                rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
                self.snapshot_date = p.parent.name

        self._rows = rows
        self._by_id = {r["rera_id"]: r for r in rows if r.get("rera_id")}
        log.info("loaded %d projects (snapshot %s)", len(rows), self.snapshot_date)
        return len(rows)

    def search(self, query: str, limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
        """Case-insensitive substring match. Returns (page_of_rows, total_matches).

        Ranked: name-start first, then name contains, then promoter, district, id.
        Empty query = browse all (the full index), paginated.
        """
        q = query.strip().lower()
        if not q:
            total = len(self._rows)
            return self._rows[offset:offset + limit], total

        scored: list[tuple[int, dict]] = []
        for r in self._rows:
            name = (r.get("project_name") or "").lower()
            promoter = (r.get("promoter_name") or "").lower()
            rid = (r.get("rera_id") or "").lower()
            district = (r.get("district") or "").lower()
            if name.startswith(q):
                scored.append((0, r))
            elif q in name:
                scored.append((1, r))
            elif q in promoter:
                scored.append((2, r))
            elif q in district:
                scored.append((3, r))
            elif q in rid:
                scored.append((4, r))
        scored.sort(key=lambda t: t[0])
        total = len(scored)
        return [r for _, r in scored[offset:offset + limit]], total

    def get(self, rera_id: str) -> dict | None:
        return self._by_id.get(rera_id)

    def count(self) -> int:
        return len(self._rows)
