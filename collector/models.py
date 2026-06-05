"""Data shapes for collected records. Plain dataclasses, no ORM — snapshots are JSON."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class ProjectIndexRow:
    """One row from the captcha-free project index list.

    These are the *index* fields only (Tier 1). Deep per-project detail (Tier 2) is
    NOT collected here — it is fetched on-demand, one human lookup at a time.

    ``source_url`` and ``fetched_at`` are mandatory: every record we store must be
    traceable to where and when it came from. That sourcing is a product requirement,
    not a nicety — the verdict cites it.
    """

    rera_id: str
    project_name: str
    promoter_name: str
    district: str = ""
    location: str = ""
    pincode: str = ""
    state: str = "MAHARASHTRA"
    status: str = "registered"  # "registered" | "revoked"
    last_modified: str = ""
    # Link back to the captcha-gated detail page — stored, not auto-fetched.
    detail_url: str = ""
    map_url: str = ""
    # Provenance — required on every record.
    source_url: str = ""
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class IndexSnapshot:
    """A full monthly capture of the index, with run metadata for auditing/diffing."""

    captured_at: str
    source: str
    total_reported: int = 0  # the "Showing Final N Result" the site claimed
    pages_fetched: int = 0
    rows: list[ProjectIndexRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "captured_at": self.captured_at,
            "source": self.source,
            "total_reported": self.total_reported,
            "pages_fetched": self.pages_fetched,
            "row_count": len(self.rows),
            "rows": [r.to_dict() for r in self.rows],
        }
