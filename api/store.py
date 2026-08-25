"""Load projects from local JSONL snapshot (fallback if REST API unavailable)."""

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
        """Load from JSONL snapshot (works on Render, no network calls needed)."""
        try:
            # Find the latest rows.jsonl
            jsonls = sorted(
                glob.glob(str(DATA_ROOT / "snapshots" / "index" / "*" / "rows.jsonl")),
                key=os.path.getmtime,
                reverse=True,
            )
            if not jsonls:
                log.error("no rows.jsonl found in data/snapshots/")
                return 0

            p = Path(jsonls[0])
            self.snapshot_date = p.parent.name
            log.info("loading from %s", p)

            rows: list[dict] = []
            with open(p, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                        rows.append(row)
                    except json.JSONDecodeError as e:
                        if i < 10 or i % 1000 == 0:
                            log.warning("line %d: %s", i, e)
                        continue

            self._rows = rows
            self._by_id = {r["rera_id"]: r for r in rows if r.get("rera_id")}

            # Get total_reported from snapshot.json if available
            snap_file = p.parent / "snapshot.json"
            if snap_file.exists():
                try:
                    snap = json.loads(snap_file.read_text(encoding="utf-8"))
                    self.total_reported = snap.get("total_reported", 0)
                except Exception:
                    self.total_reported = 0

            log.info("loaded %d projects (snapshot %s)", len(rows), self.snapshot_date)
            return len(rows)
        except Exception as e:
            log.error("load_latest failed: %s", e, exc_info=True)
            return 0

    def search(self, query: str = "", limit: int = 30, offset: int = 0,
               areas=None) -> tuple[list[dict], int]:
        """Search in-memory. Returns (page_of_rows, total_matches).

        `areas` is an optional AreaIndex. When the query names a place rather
        than a project -- "kharghar", "panvel", "410210" -- every project in that
        area matches, including the ones whose own name says nothing about where
        they are. Without it, searching a locality found only projects that
        happened to have the locality in their title.
        """
        q = query.strip().lower()
        if not q:
            total = len(self._rows)
            return self._rows[offset:offset + limit], total

        area_ids = areas.ids_for(q) if areas is not None else None

        scored: list[tuple[int, dict]] = []
        for r in self._rows:
            name = (r.get("project_name") or "").lower()
            promoter = (r.get("promoter_name") or "").lower()
            rid = (r.get("rera_id") or "").lower()
            district = (r.get("district") or "").lower()
            pincode = str(r.get("pincode") or "")

            if name.startswith(q):
                scored.append((0, r))
            elif q in name:
                scored.append((1, r))
            elif pincode == q:
                scored.append((2, r))
            elif q in promoter:
                scored.append((3, r))
            # An area match ranks below a name match but above a bare district
            # one: someone typing "kharghar" wants Kharghar projects, not every
            # project in Raigad.
            elif area_ids is not None and r.get("rera_id") in area_ids:
                scored.append((4, r))
            elif q in district:
                scored.append((5, r))
            elif q in rid:
                scored.append((6, r))

        scored.sort(key=lambda t: t[0])
        total = len(scored)
        return [r for _, r in scored[offset:offset + limit]], total

    def rows(self) -> list[dict]:
        """Every loaded row. Read-only by convention — the area index needs the
        whole set to know which projects sit in which pincode."""
        return self._rows

    def get(self, rera_id: str) -> dict | None:
        return self._by_id.get(rera_id)

    def count(self) -> int:
        return len(self._rows)
