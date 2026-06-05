"""Load + index the captcha-free reputation snapshot for use by the verdict engine.

Joins reputation data to a project by:
  • promoter name  -> complaints (normalised match)
  • rera_id / promoter -> revoked status
And computes per-builder track records (how many of a builder's projects are revoked).

Builder-name matching is deliberately conservative: we normalise (lowercase, strip
punctuation/whitespace/legal suffixes) and match exactly on the normalised key. This
avoids false "this builder has complaints" claims — on a trust product, a false negative
(missing a match) is far safer than a false positive (smearing a clean builder).
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("honesthomes.reputation")

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

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
        self.captured_at = ""
        self.loaded = False
        self._complaints_by_promoter: dict[str, int] = {}   # normalised -> count
        self._revoked_ids: set[str] = set()                 # rera_ids that are revoked
        self._revoked_by_promoter: dict[str, int] = {}      # normalised -> #revoked projects
        self.total_complaint_promoters = 0
        self.total_revoked = 0

    def load_latest(self) -> bool:
        snaps = sorted(
            glob.glob(str(DATA_ROOT / "snapshots" / "reputation" / "*")),
            key=os.path.getmtime,
        )
        if not snaps:
            log.info("no reputation snapshot found — verdicts stay index-only")
            return False
        d = Path(snaps[-1])
        self.captured_at = d.name

        comp = d / "complaints.jsonl"
        if comp.exists():
            for line in comp.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                key = normalise_name(r["promoter"])
                if key:
                    self._complaints_by_promoter[key] = self._complaints_by_promoter.get(key, 0) + int(r["complaints"])
            self.total_complaint_promoters = len(self._complaints_by_promoter)

        rev = d / "revoked.jsonl"
        if rev.exists():
            for line in rev.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("rera_id"):
                    self._revoked_ids.add(r["rera_id"])
                key = normalise_name(r.get("promoter", ""))
                if key:
                    self._revoked_by_promoter[key] = self._revoked_by_promoter.get(key, 0) + 1
            self.total_revoked = len(self._revoked_ids)

        self.loaded = True
        log.info("reputation loaded: %d complaint-promoters, %d revoked (snapshot %s)",
                 self.total_complaint_promoters, self.total_revoked, self.captured_at)
        return True

    # --- lookups used by the verdict engine ---
    def complaints_for(self, promoter: str) -> int | None:
        """Complaint count for a builder. 0 means 'checked, none found'. None = not loaded."""
        if not self.loaded:
            return None
        return self._complaints_by_promoter.get(normalise_name(promoter), 0)

    def is_revoked(self, rera_id: str, promoter: str = "") -> bool:
        return bool(rera_id) and rera_id in self._revoked_ids

    def revoked_count_for(self, promoter: str) -> int | None:
        if not self.loaded:
            return None
        return self._revoked_by_promoter.get(normalise_name(promoter), 0)
