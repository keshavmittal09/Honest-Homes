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

    def add_from_detail(self, detail_records: dict) -> int:
        """Adopt detail records that are not in the index as synthetic rows.

        The index is a dated snapshot (currently 2 June); a project registered
        after it -- notably the new PR-series ids -- is captured in the detail
        set but has no index row, so the portal cannot surface it (it looks
        projects up by index). This builds a minimal row from the detail record
        itself so those projects are searchable and servable. The verdict still
        merges the full detail, so scoring is unaffected. Refreshing the index
        makes this a no-op; until then it is what puts post-snapshot
        registrations on the site.
        """
        added = 0
        for rid, rec in (detail_records or {}).items():
            if rid in self._by_id:
                continue
            addr = rec.get("address") or {}
            geo = rec.get("geo") or {}
            sp = rec.get("specs") or {}
            row = {
                "rera_id": rid,
                "project_name": rec.get("project_name") or "",
                "promoter_name": rec.get("promoter_name") or "",
                "district": addr.get("district") or "",
                "pincode": str(addr.get("pincode") or ""),
                "location": addr.get("locality") or "",
                "status": "registered" if rec.get("registered", True) else "application",
                "last_modified": sp.get("registeredOn") or rec.get("capturedAt", "")[:10],
                # No stored detail_url for these; the UI falls back to the generic
                # MahaRERA portal link, which is correct rather than a wrong guess.
                "detail_url": rec.get("detail_url") or "",
                "map_url": ("https://www.google.com/maps/search/?api=1&query=%s,%s"
                            % (geo["lat"], geo["lng"])) if geo.get("lat") else "",
                "source_url": "",
                "_synthetic": True,
            }
            self._rows.append(row)
            self._by_id[rid] = row
            added += 1
        return added

    def rows(self) -> list[dict]:
        """Every loaded row. Read-only by convention — the area index needs the
        whole set to know which projects sit in which pincode."""
        return self._rows

    def get(self, rera_id: str) -> dict | None:
        return self._by_id.get(rera_id)

    def count(self) -> int:
        return len(self._rows)
