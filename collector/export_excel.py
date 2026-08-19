"""Export everything collected into one Excel workbook for analysis.

The parsed snapshot is nested JSON, which is the right shape for the site and the
wrong shape for a spreadsheet. This flattens it into related sheets you can
pivot: one row per project, one row per complaint, one row per court case, one
row per document.

    python -m collector.export_excel
    python -m collector.export_excel --out "C:/somewhere/honest-homes.xlsx"
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from engine.detail import PARSED_ROOT
from engine.reputation import ReputationStore
from engine.verdict import build_verdict

ROOT = Path(__file__).resolve().parent.parent


def _index_rows() -> dict[str, dict]:
    dirs = sorted(d for d in (ROOT / "data" / "snapshots" / "index").glob("*") if d.is_dir())
    out: dict[str, dict] = {}
    if not dirs:
        return out
    p = dirs[-1] / "rows.jsonl"
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("rera_id"):
                out[r["rera_id"]] = r
    return out


def build(out_path: Path) -> dict[str, int]:
    parsed = sorted(d for d in PARSED_ROOT.glob("*") if d.is_dir())
    if not parsed:
        raise SystemExit("No parsed snapshot found — run build_parsed_snapshot first.")
    recs = json.loads((parsed[-1] / "records.json").read_text(encoding="utf-8"))
    index = _index_rows()

    rep = ReputationStore()
    rep.load_latest()

    projects, complaints, courts, docs = [], [], [], []

    for rid, r in recs.items():
        row = index.get(rid, {})
        addr = r.get("address") or {}
        plot = r.get("plot") or {}
        geo = r.get("geo") or {}
        specs = r.get("specs") or {}
        units = r.get("units") or {}
        pc = r.get("projectComplaints") or {}
        lit = r.get("litigation") or {}
        cs = pc.get("complaints") or []

        v = build_verdict(row, reputation=rep, detail=r) if row else None
        warrants = [c for c in cs if c.get("warrant")]

        projects.append({
            "RERA ID": rid,
            "Project": r.get("project_name") or row.get("project_name"),
            "Builder": r.get("promoter_name") or row.get("promoter_name"),
            "Score": None if not v or v.score is None else v.score,
            "Band": v.band if v else None,
            "Verdict": v.headline if v else None,
            "District": addr.get("district") or row.get("district"),
            "Taluka": addr.get("taluka"),
            "Village/Area": addr.get("village"),
            "Locality": addr.get("locality"),
            "Pincode": addr.get("pincode") or row.get("pincode"),
            "Latitude": geo.get("lat"),
            "Longitude": geo.get("lng"),
            "CTS / Survey no.": plot.get("cts"),
            "Plot area (sq.m)": plot.get("landArea"),
            "Status": specs.get("status"),
            "Current stage": specs.get("stage"),
            "Registered on": specs.get("registeredOn"),
            "Promised completion": specs.get("originalCompletion"),
            "Revised completion": specs.get("revisedCompletion"),
            "Extensions filed": len(r.get("extensions") or []),
            "Units total": units.get("total") or specs.get("unitsTotal"),
            "Units booked": units.get("booked") or specs.get("unitsSold"),
            "% booked": (round(100 * (units.get("booked") or 0) / units["total"], 1)
                         if units.get("total") else None),
            "Complaints (project)": pc.get("count"),
            "Complaints unresolved": pc.get("unresolved"),
            "Filed by buyers": pc.get("byBuyer"),
            "Filed by builder": pc.get("byBuilder"),
            "Recovery warrants": len(warrants),
            "Recovery sought (Rs)": sum((c["warrant"].get("amount") or 0) for c in warrants),
            "Court cases": lit.get("count") or 0,
            "Builder complaints (all projects)": rep.complaints_for(r.get("promoter_name") or "") if rep.loaded else None,
            "Builder revoked projects": rep.revoked_count_for(r.get("promoter_name") or "") if rep.loaded else None,
            "Documents held": r.get("document_count") or 0,
            "Documents on record": r.get("document_refs") or 0,
            "MahaRERA page": row.get("detail_url"),
        })

        for c in cs:
            w = c.get("warrant") or {}
            o = c.get("order") or {}
            complaints.append({
                "RERA ID": rid,
                "Project": r.get("project_name"),
                "Complaint no.": c.get("complaintNo"),
                "Type": c.get("type"),
                "Filed on": c.get("filedOn"),
                "Status": c.get("status"),
                "Resolved": c.get("resolved"),
                "Direction": {"buyer_vs_builder": "Buyer -> Builder",
                              "builder_vs_buyer": "Builder -> Buyer",
                              "business_vs_business": "Business <-> Business"}.get(
                                  c.get("direction"), "Unclear"),
                "Complainant": c.get("complainant"),
                "Respondent": c.get("respondent"),
                "Order passed on": o.get("approvedOn"),
                "Order document": o.get("file"),
                "Non-compliance filings": len(c.get("nonCompliance") or []),
                "Recovery warrant": "Yes" if w else "No",
                "Recovery amount (Rs)": w.get("amount"),
                "Warrant district": w.get("district"),
                "Warrant document": w.get("file"),
            })

        for cc in (lit.get("cases") or []):
            courts.append({
                "RERA ID": rid, "Project": r.get("project_name"),
                "Court": cc.get("court"), "Case no.": cc.get("caseNo"),
                "Year": cc.get("year"), "Status": cc.get("status"),
                "Remark": cc.get("remark"),
            })

        for dcm in (r.get("documents") or []):
            docs.append({
                "RERA ID": rid, "Project": r.get("project_name"),
                "Document": dcm.get("label"), "Category": dcm.get("category"),
                "Key document": dcm.get("important"), "File": dcm.get("file"),
                "Public URL": dcm.get("url"),
            })

    sheets = {
        "Projects": pd.DataFrame(projects).sort_values("Score", na_position="last"),
        "Complaints": pd.DataFrame(complaints),
        "Court cases": pd.DataFrame(courts),
        "Documents": pd.DataFrame(docs),
    }

    # A pivot-ready area summary, since "what does Thane look like" is the first
    # question anyone asks of this data.
    p = sheets["Projects"]
    if not p.empty:
        area = (p.groupby(["District", "Village/Area"], dropna=False)
                  .agg(Projects=("RERA ID", "count"),
                       Avg_score=("Score", "mean"),
                       Complaints=("Complaints (project)", "sum"),
                       Unresolved=("Complaints unresolved", "sum"),
                       Warrants=("Recovery warrants", "sum"),
                       Court_cases=("Court cases", "sum"))
                  .reset_index().sort_values("Projects", ascending=False))
        area["Avg_score"] = area["Avg_score"].round(2)
        sheets["By area"] = area

        bl = (p.groupby("Builder", dropna=False)
                .agg(Projects=("RERA ID", "count"),
                     Avg_score=("Score", "mean"),
                     Complaints=("Complaints (project)", "sum"),
                     Warrants=("Recovery warrants", "sum"),
                     Court_cases=("Court cases", "sum"))
                .reset_index().sort_values(["Complaints", "Projects"], ascending=False))
        bl["Avg_score"] = bl["Avg_score"].round(2)
        sheets["By builder"] = bl

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xl:
        for name, df in sheets.items():
            df.to_excel(xl, sheet_name=name[:31], index=False, freeze_panes=(1, 0))
            ws = xl.sheets[name[:31]]
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:                       # readable column widths
                letter = col[0].column_letter
                width = max((len(str(c.value)) for c in col[:200] if c.value is not None),
                            default=10)
                ws.column_dimensions[letter].width = min(max(width + 2, 10), 46)

    return {k: len(v) for k, v in sheets.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / f"HonestHomes-projects-{date.today()}.xlsx"))
    args = ap.parse_args()
    counts = build(Path(args.out))
    print(f"Written: {args.out}\n")
    for name, n in counts.items():
        print(f"  {name:14s} {n:6d} rows")


if __name__ == "__main__":
    main()
