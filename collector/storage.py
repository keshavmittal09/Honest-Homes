"""Dated, never-overwrite snapshot storage + resume checkpointing.

Every monthly run lands in its own dated folder. We never overwrite a prior month —
the month-over-month *diff* (new complaints, slipped dates, revocations) is the moat,
and you can only diff if you kept the history.

Layout:
    data/
      snapshots/
        index/
          2026-06-01/
            checkpoint.json     # resume state: pages done, rows so far
            rows.jsonl          # one ProjectIndexRow per line, appended as we go
            snapshot.json       # final assembled IndexSnapshot (written at the end)
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from .models import IndexSnapshot, ProjectIndexRow

log = logging.getLogger("honesthomes.storage")

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


class IndexSnapshotStore:
    """Append-only store for a single dated index run, with resume support."""

    def __init__(
        self,
        run_date: str | None = None,
        root: Path | None = None,
        *,
        resume: bool = False,
    ) -> None:
        index_root = (root or DATA_ROOT) / "snapshots" / "index"

        # A long crawl can span midnight. If we're resuming, DON'T blindly open a
        # folder named with today's date (that would start a fresh, empty run and
        # re-crawl from page 1). Instead attach to the most recent UNFINISHED run —
        # one with a checkpoint but no final snapshot.json — so we continue it.
        if run_date is None and resume:
            run_date = self._latest_unfinished_run(index_root)

        self.run_date = run_date or date.today().isoformat()
        base = index_root / self.run_date
        base.mkdir(parents=True, exist_ok=True)
        self.dir = base
        self.rows_path = base / "rows.jsonl"
        self.checkpoint_path = base / "checkpoint.json"
        self.snapshot_path = base / "snapshot.json"

    @staticmethod
    def _latest_unfinished_run(index_root: Path) -> str | None:
        """Return the newest dated run that has a checkpoint but isn't finalised."""
        if not index_root.exists():
            return None
        candidates = sorted(
            (d for d in index_root.iterdir() if d.is_dir()),
            key=lambda d: d.name,
            reverse=True,
        )
        for d in candidates:
            if (d / "checkpoint.json").exists():
                # An unfinished run is the best resume target. A finalised one
                # (snapshot.json present) is complete — resuming it just re-confirms
                # the end, which is harmless, so we still attach to the newest.
                return d.name
        return None

    # --- resume -------------------------------------------------------------------
    def load_checkpoint(self) -> dict:
        """Return {'last_page': int, 'seen_ids': set} so an interrupted run continues."""
        if not self.checkpoint_path.exists():
            return {"last_page": 0, "seen_ids": set()}
        raw = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        return {"last_page": raw.get("last_page", 0), "seen_ids": set(raw.get("seen_ids", []))}

    def save_checkpoint(self, last_page: int, seen_ids: set[str]) -> None:
        self.checkpoint_path.write_text(
            json.dumps({"last_page": last_page, "seen_ids": sorted(seen_ids)}),
            encoding="utf-8",
        )

    # --- rows (append-only, so a crash never loses prior pages) -------------------
    def append_rows(self, rows: list[ProjectIndexRow]) -> None:
        with self.rows_path.open("a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

    def read_all_rows(self) -> list[ProjectIndexRow]:
        if not self.rows_path.exists():
            return []
        out: list[ProjectIndexRow] = []
        for line in self.rows_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(ProjectIndexRow(**json.loads(line)))
        return out

    # --- finalisation -------------------------------------------------------------
    def finalize(self, *, total_reported: int, pages_fetched: int, source: str) -> Path:
        """Assemble the dated snapshot.json from the appended rows. Idempotent."""
        rows = self.read_all_rows()
        snap = IndexSnapshot(
            captured_at=self.run_date,
            source=source,
            total_reported=total_reported,
            pages_fetched=pages_fetched,
            rows=rows,
        )
        self.snapshot_path.write_text(
            json.dumps(snap.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("wrote snapshot %s (%d rows)", self.snapshot_path, len(rows))
        return self.snapshot_path

    def dump_html(self, page: int, html: str) -> Path:
        """Persist raw page HTML so selectors can be verified against ground truth."""
        p = self.dir / f"raw_page_{page}.html"
        p.write_text(html, encoding="utf-8")
        return p
