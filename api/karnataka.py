"""Karnataka RERA projects on the portal — the North & East Bengaluru region.

The K-RERA collector (collector/krera_region.py + krera_build.py) writes
data/regions/bangalore-north-east/records.json in the engine record shape. This
module turns those records into portal rows alongside the MahaRERA index, and
shapes them for the cards and the verdict screen.

Two things differ from MahaRERA and are handled here rather than leaking into
the shared code:

* **Ids.** A K-RERA registration number is "PRM/KA/RERA/1251/310/PR/150223/005721".
  The slashes cannot survive a URL path (Starlette decodes %2F before routing),
  so the portal id swaps them for dashes. The real number is kept as `reraId`
  and is what the page displays.
* **Evidence.** Every K-RERA project is verdicted by engine.karnataka, never by
  the MahaRERA reputation registers — see that module for why.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

from engine.karnataka import build_verdict_ka, latest_completion, norm_name, pair_key

log = logging.getLogger("honesthomes.karnataka")

REGION_DIR = Path(__file__).resolve().parent.parent / "data" / "regions" / "bangalore-north-east"
REGULATOR = "K-RERA"
STATE = "Karnataka"
PORTAL_URL = "https://rera.karnataka.gov.in/viewAllProjects"

_KIND = {"positive": "positive", "caution": "caution", "negative": "severe", "neutral": "neutral"}
_ICON = {
    "ka_registered": "shield-check",
    "ka_application": "file-warning",
    "ka_extensions": "calendar-clock",
    "ka_overdue": "calendar-clock",
    "ka_due": "calendar-check",
    "coverage": "info",
}


def portal_id(key: str) -> str:
    """URL-safe portal id for a records.json key.

    Keys are the registration number, the acknowledgement number for an
    application, or — when the page carried neither — the bare K-RERA tid.
    """
    if "/" in key:
        return key.replace("/", "-")
    return "KA-" + key


def is_ka(row: dict | None) -> bool:
    return bool(row) and row.get("state") == "KA"


class KarnatakaStore:
    def __init__(self) -> None:
        self.loaded = False
        self.as_of = ""
        self._recs: dict[str, dict] = {}      # portal id -> record
        self._reg: dict[str, str] = {}        # portal id -> displayed RERA number
        self._rows: list[dict] = []
        self._by_promoter: dict[str, list[str]] = {}
        self._key: dict[str, str] = {}        # portal id -> records.json key (the reg. no.)
        self._pair_n: dict[str, int] = {}     # (project|promoter) -> our records sharing it
        self.skipped = 0
        # K-RERA public registers (collector/krera_register.py). None until loaded:
        # a missing file must read as "not collected", never as "no complaints".
        self.register: dict | None = None
        self._orders_by_pair: dict[str, list[dict]] = {}
        self._promoter_stats: dict[str, dict] = {}
        self._lapsed: set[str] = set()
        self._default: set[str] = set()
        self._revoked: set[str] = set()
        self._unmatched = 0

    def load(self, region_dir: Path = REGION_DIR) -> int:
        p = region_dir / "records.json"
        if not p.exists():
            log.info("no Karnataka records at %s", p)
            return 0
        raw = json.loads(p.read_text(encoding="utf-8"))

        # The build stamps index.json; a file mtime would be the deploy's clone
        # time, which says nothing about when the record was read.
        self.as_of = ""
        idx = region_dir / "index.json"
        if idx.exists():
            try:
                self.as_of = (json.loads(idx.read_text(encoding="utf-8")).get("builtAt") or "")[:10]
            except ValueError:
                pass
        if not self.as_of:
            self.as_of = date.fromtimestamp(os.path.getmtime(p)).isoformat()

        for key, rec in raw.items():
            # A page with no project name is an abandoned or test application
            # ("kk" by "Krishna kanth" is typical) — nothing a buyer could search for.
            if not (rec.get("project_name") or "").strip():
                self.skipped += 1
                continue
            pid = portal_id(key)
            reg = rec.get("rera_id") or f"K-RERA application {key}"
            addr = rec.get("address") or {}
            geo = rec.get("geo") or {}
            sp = rec.get("specs") or {}
            self._recs[pid] = rec
            self._reg[pid] = reg
            self._key[pid] = key
            pk = pair_key(rec["project_name"], rec.get("promoter_name"))
            self._pair_n[pk] = self._pair_n.get(pk, 0) + 1
            self._rows.append({
                "rera_id": pid,
                "reg_no": reg,
                "state": "KA",
                "project_name": rec["project_name"].strip(),
                "promoter_name": (rec.get("promoter_name") or "").strip(),
                "district": addr.get("district") or "Bengaluru Urban",
                "pincode": str(addr.get("pincode") or ""),
                "location": addr.get("locality") or "",
                "status": "registered" if rec.get("registered") else "application",
                "last_modified": sp.get("registeredOn") or "",
                "detail_url": PORTAL_URL,
                "map_url": ("https://www.google.com/maps/search/?api=1&query=%s,%s"
                            % (geo["lat"], geo["lng"])) if geo.get("lat") else "",
                "fetched_at": self.as_of,
            })
            k = (rec.get("promoter_name") or "").strip().lower()
            if k:
                self._by_promoter.setdefault(k, []).append(pid)

        self.loaded = True
        log.info("Karnataka: %d projects loaded (%d unnamed applications skipped), as of %s",
                 len(self._rows), self.skipped, self.as_of)
        self._load_register(region_dir)
        return len(self._rows)

    def _load_register(self, region_dir: Path) -> None:
        p = region_dir / "krera-register.json"
        if not p.exists():
            log.info("no K-RERA register at %s -- complaints left unassessed", p)
            return
        try:
            reg = json.loads(p.read_text(encoding="utf-8"))
            for need in ("complaintPairs", "masterPairs", "orders", "penalties", "lapsed"):
                if need not in reg:
                    raise ValueError("missing %r" % need)
        except (ValueError, OSError) as e:
            # Fail closed: a damaged register must not turn into "no complaints".
            log.error("K-RERA register unreadable (%s) -- complaints left unassessed", e)
            return
        for o in reg["orders"]:
            self._orders_by_pair.setdefault(pair_key(o["project"], o["promoter"]), []).append(o)
        for pk, n in reg["complaintPairs"].items():
            prom = pk.split("|", 1)[1]
            st = self._promoter_stats.setdefault(prom, {"complaints": 0, "projects": 0})
            st["complaints"] += n
            st["projects"] += 1
        self._lapsed = set(reg["lapsed"])
        self._default = {d["regNo"] for d in reg.get("default", [])}
        self._revoked = set(reg.get("revoked", []))
        # Our pairs the master list does not contain cannot be matched to the
        # complaint register either (both come from the same system), so a
        # "no complaints" there would be unearned.
        self._unmatched = sum(1 for k in self._pair_n if k not in reg["masterPairs"])
        self.register = reg
        c = reg.get("counts", {})
        log.info("K-RERA register: %s complaints, %s orders (%s ours), %s penalties, "
                 "%s lapsed, %d of our name pairs not found in the master list (fetched %s)",
                 c.get("complaints"), c.get("orders"), c.get("ordersOurs"),
                 c.get("penaltiesOurs"), c.get("lapsed"), self._unmatched, reg.get("fetchedAt"))

    def evidence(self, row: dict) -> dict | None:
        """This project's slice of the K-RERA registers, or None if not collected.

        `matched` is False when the project's name pair is not in K-RERA's own
        master list: both lists come from the same system, so such a project
        cannot be found in the complaint register by name either, and "none
        found" would be an artefact of the join rather than a fact.
        """
        if self.register is None:
            return None
        pid = row["rera_id"]
        rec = self._recs.get(pid) or {}
        key = self._key.get(pid, "")
        pk = pair_key(rec.get("project_name"), rec.get("promoter_name"))
        in_master = self.register["masterPairs"].get(pk, 0)
        ours = self._pair_n.get(pk, 1)
        ev = {
            "matched": in_master > 0,
            # Registrations in K-RERA sharing this name+builder that are not ours:
            # the complaint could belong to one of those instead.
            "ambiguous": in_master > ours,
            "shared": ours,
            "complaints": self.register["complaintPairs"].get(pk, 0),
            "orders": self._orders_by_pair.get(pk, []),
            "penalties": self.register["penalties"].get(key, []),
            "lapsed": key in self._lapsed,
            "default": key in self._default,
            "revoked": key in self._revoked,
        }
        if not ev["matched"]:
            return None
        return ev

    def rows(self) -> list[dict]:
        return self._rows

    def get(self, pid: str) -> dict | None:
        return self._recs.get(pid)

    def ids(self) -> set[str]:
        return set(self._recs)

    def area_records(self) -> dict[str, dict]:
        """Records keyed by portal id, for the area index to learn locality names."""
        return self._recs

    def area_groups(self, min_count: int = 2) -> dict[str, set[str]]:
        """Place name -> project ids, from each project's OWN address block.

        Taluk, hobli and village as printed on the project's page. The pin code
        used to drive this and was the promoter's, so a search for "Whitefield"
        returned builders headquartered there rather than projects built there.
        """
        groups: dict[str, set[str]] = {}
        for pid, rec in self._recs.items():
            a = rec.get("address") or {}
            for name in (a.get("taluka"), a.get("hobli"), a.get("village")):
                n = (name or "").strip()
                if len(n) > 2:
                    groups.setdefault(n, set()).add(pid)
        return {n: ids for n, ids in groups.items() if len(ids) >= min_count}

    def bengaluru_ids(self) -> set[str]:
        """Projects whose own district is Bengaluru Urban or Rural.

        Not every project in the set is in Bengaluru: some builders based there
        build in Kolar, Mysore or Chitradurga, and a search for "Bangalore"
        must not return those.
        """
        ok = {"bengaluru urban", "bangalore urban", "bengaluru rural", "bangalore rural"}
        return {pid for pid, rec in self._recs.items()
                if ((rec.get("address") or {}).get("district") or "").strip().lower() in ok}

    def geo_points(self):
        for pid, rec in self._recs.items():
            g = rec.get("geo") or {}
            if g.get("lat") and g.get("lng"):
                yield pid, g, rec

    # -- shaping -------------------------------------------------------------

    def verdict(self, row: dict):
        rec = self._recs.get(row["rera_id"]) or {}
        return build_verdict_ka(rec, reg_no=row.get("reg_no") or row["rera_id"],
                                as_of=self.as_of, evidence=self.evidence(row))

    def card(self, row: dict) -> dict:
        rec = self._recs.get(row["rera_id"]) or {}
        addr = rec.get("address") or {}
        return {
            "band": self.verdict(row).band,
            "id": row["rera_id"],
            "reraId": row.get("reg_no"),
            "regulator": REGULATOR,
            "stateName": STATE,
            "score": None,
            "name": row.get("project_name") or "(unnamed project)",
            "builder": row.get("promoter_name") or "—",
            "builderId": row.get("promoter_name") or "unknown",
            "district": row.get("district") or "—",
            "area": addr.get("locality") or None,
            "locality": row.get("district") or "Karnataka",
            "pincode": row.get("pincode") or "",
            "status": "Registered" if row.get("status") == "registered" else "Application",
        }

    def full(self, row: dict) -> dict:
        rec = self._recs.get(row["rera_id"]) or {}
        ev = self.evidence(row)
        v = build_verdict_ka(rec, reg_no=row.get("reg_no") or row["rera_id"],
                             as_of=self.as_of, evidence=ev)
        sp = rec.get("specs") or {}
        promoter = row.get("promoter_name") or ""

        signals = []
        for s in v.signals:
            s = s.to_dict()
            detail = "" if s["reason"].rstrip(".").strip() == s["title"].rstrip(".").strip() else s["reason"]
            signals.append({
                "kind": _KIND.get(s["kind"], "neutral"), "impact": None,
                "icon": _ICON.get(s["key"], "file"), "fact": s["title"], "detail": detail,
                "source": s["source"], "asOf": s["as_of"],
            })

        # K-RERA stores each extension as just the new date. Chain them so the
        # page can show "promised -> revised" for every step, as it does for
        # MahaRERA -- keeping only the ones that moved the date, the same rule
        # revision_count applies, so the panel and the signal agree.
        exts, prev = [], sp.get("originalCompletion")
        for e in rec.get("extensions") or []:
            d = e.get("revisedDate")
            if d and (prev is None or d > prev):
                exts.append({"originalDate": prev, "revisedDate": d})
                prev = d

        timeline = []
        if sp.get("registeredOn"):
            timeline.append({"type": "registered", "label": "RERA registered", "date": sp["registeredOn"]})
        if sp.get("originalCompletion"):
            timeline.append({"type": "promised", "label": "Promised completion", "date": sp["originalCompletion"]})
        latest = latest_completion(rec) or ""
        if latest and sp.get("originalCompletion") and latest > sp["originalCompletion"]:
            timeline.append({"type": "revised", "label": "Revised completion", "date": latest})

        # The capture lists some files twice (same download token); one row each.
        docs, seen = [], set()
        for d in rec.get("documents") or []:
            url = d.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            label = (d.get("label") or d.get("kind") or "Document")
            if label.lower().endswith(".pdf"):
                label = label[:-4]
            docs.append({"label": label, "kind": label, "category": d.get("category") or "Other",
                         "href": url})

        revised = latest if latest and latest != sp.get("originalCompletion") else None

        # --- this project's complaints, shaped for the existing complaints panel
        pc = None
        if ev is not None and not ev["ambiguous"]:
            rows = []
            for o in sorted(ev["orders"], key=lambda x: x.get("orderDate") or "", reverse=True):
                pet = norm_name(o.get("petitioner"))
                prom = norm_name(promoter)
                # No order in K-RERA's published list has the promoter as petitioner;
                # still classify by name, so one that did would not be miscounted.
                by_builder = bool(prom and pet and (pet == prom or prom in pet or pet in prom))
                rows.append({
                    "complaintNo": o.get("complaintNo"),
                    "complainant": o.get("petitioner"), "respondent": o.get("respondent"),
                    "direction": "builder_vs_buyer" if by_builder else "buyer_vs_builder",
                    "filedOn": o.get("complaintDate"), "status": "Order passed by the Authority",
                    "resolved": True,
                    "order": {"approvedOn": o.get("orderDate"), "file": None},
                    "nonCompliance": [], "warrant": None, "relief": o.get("relief"),
                })
            n_total = max(ev["complaints"], len(rows))
            pc = {
                "count": n_total, "withOrder": len(rows), "rows": rows, "complaints": rows,
                "orders": [], "nonCompliance": [], "warrants": [],
                "byBuyer": sum(1 for r in rows if r["direction"] == "buyer_vs_builder"),
                "byBuilder": sum(1 for r in rows if r["direction"] == "builder_vs_buyer"),
                "penalties": ev["penalties"], "shared": ev["shared"],
                "lapsedListed": ev["lapsed"],
            }

        score = v.project_score
        suppressed = bool(score) and score.get("publishable") is False
        card = self.card(row)
        card.update({
            "statusNote": sp.get("status") or ("Registered" if rec.get("registered") else "Application"),
            "registered": sp.get("registeredOn") or "",
            "lastModified": sp.get("registeredOn") or "",
            "promisedCompletion": sp.get("originalCompletion") or "—",
            "revisedCompletion": revised,
            "actualCompletion": None,
            "extensions": len(exts),
            "complaints": pc["count"] if pc else None,
            "orders": pc["withOrder"] if pc else None,
            "projectComplaints": pc["count"] if pc else None,
            "courtCases": None,
            "headline": v.headline,
            "summary": (
                "The band is based on this project's Karnataka RERA registration and completion "
                "record, K-RERA's public complaint register, its Authority and penalty orders, "
                "and its list of projects past their completion date. Documents, quarterly "
                "reports and financials are not yet assessed, so we publish a band, not a "
                "number. Complaints are matched to the project by exact name and builder."
                if ev is not None else
                "The band is based on this project's Karnataka RERA registration and completion "
                "record only. We could not match it to K-RERA's complaint register, so "
                "complaints are unassessed — absence of complaints here is not evidence that "
                "there are none. Verify on the K-RERA portal before relying on this."
            ),
            "signals": signals,
            "timeline": timeline,
            "mapUrl": row.get("map_url", ""),
            "detailUrl": PORTAL_URL,
            "dataComplete": False,
            "dataAsOf": self.as_of,
            "disclaimer": v.disclaimer,
            "projectScore": score, "builderScore": None, "confidence": v.confidence,
            "bandV2": v.band_v2 or None, "scoreSuppressed": suppressed,
            "units": sp.get("unitsTotal"),
            "plot": None,
            "hasDetail": True,
            "detail": {
                "specs": {
                    "status": sp.get("status"),
                    "registeredOn": sp.get("registeredOn"),
                    "originalCompletion": sp.get("originalCompletion"),
                    "revisedCompletion": revised,
                    "unitsTotal": sp.get("unitsTotal"),
                },
                "extensions": exts,
                "buildings": [],
                "units": {"total": sp.get("unitsTotal")},
                "litigation": None,
                "documents": docs,
                "documentCount": len(docs),
                "documentsAvailable": bool(docs),
                "capturedAt": self.as_of,
                "projectComplaints": pc or {},
                "geo": rec.get("geo") or None,
                "address": rec.get("address"),
            },
        })
        return card

    def builder(self, row: dict) -> dict:
        """Builder panel: our Bengaluru projects for this promoter, plus the
        complaints K-RERA's register holds under the same builder name.

        Revocations stay unknown (None) rather than zero: K-RERA publishes no
        per-builder revocation list we have read, and a 0 would claim we had.
        """
        name = row.get("promoter_name") or "Unknown builder"
        mine = self._by_promoter.get(name.strip().lower(), [])
        by_id = {r["rera_id"]: r for r in self._rows}
        others = []
        for pid in mine:
            if pid == row["rera_id"]:
                continue
            orow = by_id.get(pid)
            rec = self._recs[pid]
            others.append({"id": pid, "name": rec.get("project_name"),
                           "district": (rec.get("address") or {}).get("locality") or "Bengaluru",
                           "band": self.verdict(orow).band if orow else "incomplete",
                           "status": "Registered" if rec.get("registered") else "Application"})
        n = len(mine)
        st = self._promoter_stats.get(norm_name(name)) if self.register is not None else None
        complaints = st["complaints"] if st else (0 if self.register is not None else None)
        if self.register is None:
            tail = ("K-RERA complaint records were not available, so complaints are shown as "
                    "unknown, not as zero.")
        elif complaints:
            tail = (f"K-RERA's complaint register holds {complaints} complaint(s) under this "
                    f"builder's name across {st['projects']} project name(s) state-wide, "
                    "matched by exact builder name. Revocations are not collected.")
        else:
            tail = ("No complaint on K-RERA's register carries this builder's exact name. "
                    "Revocations are not collected.")
        return {
            "name": name, "since": "—",
            "totalProjects": n or None,
            "projectsScope": "in our Bengaluru K-RERA set",
            "complaints": complaints, "revoked": None,
            "others": others[:8],
            "note": f"{n} project(s) by this builder in our Bengaluru K-RERA set. {tail}",
        }


KA = KarnatakaStore()
