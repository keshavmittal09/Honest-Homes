"""Load reputation data from local JSONL snapshots."""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("honesthomes.reputation")

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

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
        self.captured_at = ""
        self.loaded = False
        self._complaints_by_promoter: dict[str, int] = {}
        self._revoked_ids: set[str] = set()
        self._revoked_by_promoter: dict[str, int] = {}
        self._projects_by_promoter: dict[str, int] = {}  # normalised -> #projects in index
        self.total_complaint_promoters = 0
        self.total_revoked = 0

    def load_latest(self) -> bool:
        """Load from JSONL snapshots in data/snapshots/reputation/."""
        try:
            # Only dated snapshot DIRECTORIES (e.g. 2026-06-04/), never the loose
            # files some repos also keep directly under reputation/. Sort by NAME so
            # the newest date wins — mtime is unreliable after a git clone (Render),
            # where every file shares the clone timestamp.
            snaps = sorted(
                d for d in glob.glob(str(DATA_ROOT / "snapshots" / "reputation" / "*"))
                if os.path.isdir(d)
            )
            if not snaps:
                log.info("no reputation snapshot found")
                return False

            d = Path(snaps[-1])
            self.captured_at = d.name
            log.info("loading reputation from %s", d)

            # Load complaints
            comp = d / "complaints.jsonl"
            if comp.exists():
                with open(comp, encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            r = json.loads(line)
                            key = normalise_name(r["promoter"])
                            if key:
                                self._complaints_by_promoter[key] = self._complaints_by_promoter.get(key, 0) + int(r["complaints"])
                        except (json.JSONDecodeError, KeyError):
                            continue
                self.total_complaint_promoters = len(self._complaints_by_promoter)
                log.info("loaded %d complaint-promoters", self.total_complaint_promoters)

            # Load revoked
            rev = d / "revoked.jsonl"
            if rev.exists():
                with open(rev, encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            r = json.loads(line)
                            if r.get("rera_id"):
                                self._revoked_ids.add(r["rera_id"])
                            key = normalise_name(r.get("promoter", ""))
                            if key:
                                self._revoked_by_promoter[key] = self._revoked_by_promoter.get(key, 0) + 1
                        except (json.JSONDecodeError, KeyError):
                            continue
                self.total_revoked = len(self._revoked_ids)
                log.info("loaded %d revoked projects", self.total_revoked)

            # Projects-per-builder, from the index snapshot. Needed to normalise
            # complaints (9 complaints on a 1-project builder != on an 80-project one).
            self._load_project_counts()

            self.loaded = True
            log.info("reputation loaded: %d complaint-promoters, %d revoked, %d builders w/ project counts (snapshot %s)",
                     self.total_complaint_promoters, self.total_revoked,
                     len(self._projects_by_promoter), self.captured_at)
            return True
        except Exception as e:
            log.error("load_latest failed: %s", e, exc_info=True)
            return False

    def _load_project_counts(self) -> None:
        """Count how many index projects each (normalised) builder has."""
        jsonls = sorted(
            d for d in glob.glob(str(DATA_ROOT / "snapshots" / "index" / "*"))
            if os.path.isdir(d)
        )
        if not jsonls:
            log.info("no index snapshot found for project counts")
            return
        rows_path = Path(jsonls[-1]) / "rows.jsonl"
        if not rows_path.exists():
            return
        with open(rows_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    key = normalise_name(r.get("promoter_name", ""))
                    if key:
                        self._projects_by_promoter[key] = self._projects_by_promoter.get(key, 0) + 1
                except (json.JSONDecodeError, KeyError):
                    continue

    def projects_for(self, promoter: str) -> int:
        """How many index projects this builder has (0 if unknown). Min 1 when known
        to avoid divide-by-zero in per-project ratios."""
        return self._projects_by_promoter.get(normalise_name(promoter), 0)

    def complaints_for(self, promoter: str) -> int | None:
        """Complaint count for a builder."""
        if not self.loaded:
            return None
        return self._complaints_by_promoter.get(normalise_name(promoter), 0)

    def is_revoked(self, rera_id: str, promoter: str = "") -> bool:
        return bool(rera_id) and rera_id in self._revoked_ids

    def revoked_count_for(self, promoter: str) -> int | None:
        if not self.loaded:
            return None
        return self._revoked_by_promoter.get(normalise_name(promoter), 0)
