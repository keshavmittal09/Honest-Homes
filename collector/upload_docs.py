"""Upload captured Tier-2 documents to Supabase Storage (public bucket) and write
each document's public URL back into the parsed records, so the live public site
can open documents (not just localhost).

Needs SUPABASE_URL + SUPABASE_KEY (service_role) in the environment (.env). Free
Supabase Storage is 1 GB — our captures (~121 MB) fit comfortably.

Run:  python -m collector.upload_docs
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import urllib.parse
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from engine.detail import PARSED_ROOT, RAW_ROOT

BUCKET = "project-docs"


def _latest(root: Path) -> Path | None:
    dirs = sorted(d for d in root.glob("*") if d.is_dir() and d.name != ".assist")
    return dirs[-1] if dirs else None


def main() -> None:
    import argparse
    from engine.detail import DetailStore

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--projects", default="",
                    help="JSON file or comma-separated RERA ids to upload (default: all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        sys.exit("SUPABASE_URL / SUPABASE_KEY not set. Put them in .env, then re-run.")

    parsed_dir = _latest(PARSED_ROOT)
    if not parsed_dir:
        sys.exit("No parsed records found.")
    records_path = parsed_dir / "records.json"
    records = json.loads(records_path.read_text(encoding="utf-8"))

    # Documents are grouped by area now, so resolve each project's folder through
    # the same index the app uses rather than assuming docs/<RID>/.
    store = DetailStore()
    store.load_latest()

    wanted: set[str] | None = None
    if args.projects:
        p = Path(args.projects)
        if p.exists():
            wanted = set(json.loads(p.read_text(encoding="utf-8")))
        else:
            wanted = {x.strip() for x in args.projects.split(",") if x.strip()}

    todo = [(rid, rec) for rid, rec in records.items()
            if (wanted is None or rid in wanted) and rec.get("documents")]
    n_docs = sum(len(r.get("documents", [])) for _, r in todo)
    print(f"{len(todo)} project(s), {n_docs} document(s) to upload")
    if args.dry_run:
        return

    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=120, headers=headers) as c:
        # Create the public bucket (ignore "already exists").
        b = c.post(f"{url}/storage/v1/bucket", json={"id": BUCKET, "name": BUCKET, "public": True})
        if b.status_code not in (200, 201) and "exist" not in b.text.lower():
            print("bucket create:", b.status_code, b.text[:160])

        total = up_ok = 0
        for rid, rec in todo:
            n = 0
            for doc in rec.get("documents", []):
                f = doc.get("file")
                if not f:
                    continue
                local = store.doc_path(rid, f)
                if local is None:
                    continue
                total += 1
                enc_key = urllib.parse.quote(f"{rid}/{f}")
                mime = mimetypes.guess_type(f)[0] or "application/octet-stream"
                r = c.post(
                    f"{url}/storage/v1/object/{BUCKET}/{enc_key}",
                    content=local.read_bytes(),
                    headers={**headers, "Content-Type": mime, "x-upsert": "true"},
                )
                if r.status_code in (200, 201):
                    doc["url"] = f"{url}/storage/v1/object/public/{BUCKET}/{enc_key}"
                    up_ok += 1
                    n += 1
                else:
                    print("  FAIL", rid, f[:40], r.status_code, r.text[:100])
            print(f"  {rid}: {n}/{len(rec.get('documents', []))} uploaded")

    records_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone. {up_ok}/{total} documents uploaded. URLs written to {records_path}")


if __name__ == "__main__":
    main()
