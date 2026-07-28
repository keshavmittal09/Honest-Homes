"""Group the captured document folders by area.

By default every project's documents sit flat under docs/<RERA_ID>/, which is
fine for the app but useless to browse — you cannot see what you hold for Thane
versus Raigarh without cross-referencing the index. This moves each project into

    docs/<District>/<Village or Taluka>/<RERA_ID>/

Nothing else has to change: DetailStore indexes document folders by scanning for
directories named like a RERA id, so it finds them wherever they end up.

    python -m collector.sort_docs_by_area --dry-run     # show the plan
    python -m collector.sort_docs_by_area               # do it
    python -m collector.sort_docs_by_area --flatten     # undo, back to flat
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from engine.detail import RAW_ROOT, PARSED_ROOT

_RID = re.compile(r"^P\d{11}$")


def _safe(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 ()&.-]", " ", (name or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s or "Unknown")[:60]


def _area_index() -> dict[str, tuple[str, str]]:
    """rera_id -> (district, village/taluka), from the index + parsed records."""
    area: dict[str, tuple[str, str]] = {}

    dirs = sorted(d for d in (RAW_ROOT.parent / "index").glob("*") if d.is_dir())
    if dirs:
        rows = dirs[-1] / "rows.jsonl"
        if rows.exists():
            with open(rows, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if r.get("rera_id"):
                        area[r["rera_id"]] = (_safe(r.get("district")), "")

    # The parsed record carries village/taluka from the HTML capture when present.
    parsed = sorted(d for d in PARSED_ROOT.glob("*") if d.is_dir())
    if parsed:
        rec = parsed[-1] / "records.json"
        if rec.exists():
            for rid, r in json.loads(rec.read_text(encoding="utf-8")).items():
                addr = r.get("address") or {}
                plot = r.get("plot") or {}
                d, v = area.get(rid, ("Unknown", ""))
                district = addr.get("district") or plot.get("district") or d
                # village/taluka is the browsable unit; locality is too granular
                # for a folder name (it is a plot number and sector).
                sub = addr.get("village") or addr.get("taluka") or plot.get("village") or plot.get("taluka") or v
                area[rid] = (_safe(district), _safe(sub) if sub else "")
    return area


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--flatten", action="store_true", help="move everything back to docs/<RID>/")
    args = ap.parse_args()

    area = _area_index()
    moves: list[tuple[Path, Path]] = []

    for docs_root in sorted(RAW_ROOT.glob("*/docs")):
        for p in sorted(docs_root.rglob("*")):
            if not (p.is_dir() and _RID.match(p.name)):
                continue
            if args.flatten:
                dest = docs_root / p.name
            else:
                district, village = area.get(p.name, ("Unknown", ""))
                dest = docs_root / district / village / p.name if village else docs_root / district / p.name
            if dest.resolve() != p.resolve():
                moves.append((p, dest))

    if not moves:
        print("Nothing to move — already organised.")
        return

    print(f"{len(moves)} project folder(s) to move\n")
    for src, dest in moves[:12]:
        print(f"  {src.relative_to(RAW_ROOT)}\n    -> {dest.relative_to(RAW_ROOT)}")
    if len(moves) > 12:
        print(f"  ... and {len(moves) - 12} more")

    if args.dry_run:
        print("\n--dry-run: nothing moved.")
        return

    done = 0
    for src, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():                      # merge rather than clobber
            for f in src.iterdir():
                target = dest / f.name
                if not target.exists():
                    shutil.move(str(f), str(target))
            if not any(src.iterdir()):
                src.rmdir()
        else:
            shutil.move(str(src), str(dest))
        done += 1

    # tidy up directories left empty by the move
    for docs_root in sorted(RAW_ROOT.glob("*/docs")):
        for p in sorted(docs_root.rglob("*"), key=lambda x: -len(x.parts)):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()

    print(f"\nMoved {done} project folder(s).")


if __name__ == "__main__":
    main()
