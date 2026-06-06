"""Load Honest Homes data from JSON snapshots into Supabase."""

import json
import sys
import os
from pathlib import Path

# Fix Windows encoding for console output
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import psycopg2
from psycopg2.extras import execute_batch

# Supabase connection details
SUPABASE_HOST = "db.buhxytlquxsxziagooog.supabase.co"
SUPABASE_DB = "postgres"
SUPABASE_USER = "postgres"
SUPABASE_PASSWORD = "honesthomes_001"
SUPABASE_PORT = 5432

DATA_DIR = Path(__file__).parent / "data" / "snapshots"


def load_projects(conn):
    """Load projects from rows.jsonl into projects table."""
    projects_file = DATA_DIR / "index" / "2026-06-02" / "rows.jsonl"

    if not projects_file.exists():
        print(f"❌ Projects file not found: {projects_file}")
        return 0

    print(f"Loading projects from {projects_file.name}...")

    rows = []
    with open(projects_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                rows.append((
                    row.get("rera_id"),
                    row.get("project_name"),
                    row.get("promoter_name"),
                    row.get("district"),
                    row.get("location", ""),
                    row.get("pincode"),
                    row.get("state", "MAHARASHTRA"),
                    row.get("status", "registered"),
                    row.get("last_modified"),
                    row.get("detail_url"),
                    row.get("map_url"),
                    row.get("source_url"),
                    row.get("fetched_at"),
                ))
            except json.JSONDecodeError:
                continue

    if not rows:
        print("❌ No projects loaded")
        return 0

    # Insert in batches
    with conn.cursor() as cur:
        execute_batch(
            cur,
            """
            INSERT INTO projects
            (rera_id, project_name, promoter_name, district, location, pincode, state, status, last_modified, detail_url, map_url, source_url, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (rera_id) DO NOTHING
            """,
            rows,
            page_size=1000,
        )
        conn.commit()

    print(f"✅ Loaded {len(rows)} projects")
    return len(rows)


def load_complaints(conn):
    """Load complaints from complaints.jsonl."""
    complaints_file = DATA_DIR / "reputation" / "2026-06-04" / "complaints.jsonl"

    if not complaints_file.exists():
        print(f"❌ Complaints file not found: {complaints_file}")
        return 0

    print(f"Loading complaints from {complaints_file.name}...")

    rows = []
    with open(complaints_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                rows.append((
                    row.get("promoter"),
                    row.get("complaints", 0),
                    row.get("promoter_id", ""),
                    row.get("source_url"),
                    row.get("fetched_at"),
                ))
            except json.JSONDecodeError:
                continue

    if not rows:
        print("❌ No complaints loaded")
        return 0

    with conn.cursor() as cur:
        execute_batch(
            cur,
            """
            INSERT INTO complaints
            (promoter, complaint_count, promoter_id, source_url, fetched_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (promoter) DO UPDATE
            SET complaint_count = EXCLUDED.complaint_count, fetched_at = EXCLUDED.fetched_at
            """,
            rows,
            page_size=1000,
        )
        conn.commit()

    print(f"✅ Loaded {len(rows)} complaint records")
    return len(rows)


def load_revoked(conn):
    """Load revoked projects from revoked.jsonl."""
    revoked_file = DATA_DIR / "reputation" / "2026-06-04" / "revoked.jsonl"

    if not revoked_file.exists():
        print(f"❌ Revoked file not found: {revoked_file}")
        return 0

    print(f"Loading revoked projects from {revoked_file.name}...")

    rows = []
    with open(revoked_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                rows.append((
                    row.get("rera_id"),
                    row.get("project_name"),
                    row.get("promoter"),
                    row.get("source_url"),
                    row.get("fetched_at"),
                ))
            except json.JSONDecodeError:
                continue

    if not rows:
        print("❌ No revoked projects loaded")
        return 0

    with conn.cursor() as cur:
        execute_batch(
            cur,
            """
            INSERT INTO revoked_projects
            (rera_id, project_name, promoter, source_url, fetched_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (rera_id) DO NOTHING
            """,
            rows,
            page_size=1000,
        )
        conn.commit()

    print(f"✅ Loaded {len(rows)} revoked projects")
    return len(rows)


def main():
    try:
        print("Connecting to Supabase...")
        conn = psycopg2.connect(
            host=SUPABASE_HOST,
            database=SUPABASE_DB,
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD,
            port=SUPABASE_PORT,
        )
        print("✅ Connected")

        n_projects = load_projects(conn)
        n_complaints = load_complaints(conn)
        n_revoked = load_revoked(conn)

        # Update metadata
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE metadata SET value = %s WHERE key = 'total_projects_loaded'",
                (str(n_projects),),
            )
            conn.commit()

        print(f"\n✅ Done! Loaded:")
        print(f"   {n_projects:,} projects")
        print(f"   {n_complaints:,} complaint records")
        print(f"   {n_revoked} revoked projects")

        conn.close()
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
