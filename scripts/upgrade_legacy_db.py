"""Upgrade an existing (old) SQLite jobs.db to the new schema, keeping your data.

Old schema:  job(id, company, role, status)
New schema:  job + location, url, notes, deadline, created_at, updated_at
             and a new status_history table (one starting row per old job).

Usage (from the project root):
    python scripts/upgrade_legacy_db.py                      # uses instance/jobs.db
    python scripts/upgrade_legacy_db.py path/to/jobs.db

A backup copy (jobs.db.bak) is made first. Safe to run more than once.
SQLite only. For PostgreSQL use a migration tool (Flask-Migrate / Alembic).
"""
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

NEW_COLUMNS = {
    "location": "VARCHAR(100)",
    "url": "VARCHAR(500)",
    "notes": "TEXT",
    "deadline": "DATE",
    "created_at": "DATETIME",
    "updated_at": "DATETIME",
}

HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER NOT NULL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES job (id) ON DELETE CASCADE,
    from_status VARCHAR(50),
    to_status VARCHAR(50) NOT NULL,
    changed_at DATETIME NOT NULL
)
"""


def main(db_path):
    db_path = Path(db_path)
    if not db_path.exists():
        sys.exit(f"Database not found: {db_path}")

    backup = db_path.with_name(db_path.name + ".bak")
    shutil.copy2(db_path, backup)
    print(f"Backup saved: {backup}")

    now = datetime.now(timezone.utc).isoformat(sep=" ")
    con = sqlite3.connect(db_path)
    try:
        existing = {row[1] for row in con.execute("PRAGMA table_info(job)")}
        if not existing:
            sys.exit("No 'job' table found. Start the app once to create a fresh database.")

        for column, sql_type in NEW_COLUMNS.items():
            if column not in existing:
                con.execute(f"ALTER TABLE job ADD COLUMN {column} {sql_type}")
                print(f"Added column job.{column}")

        con.execute("UPDATE job SET created_at = ? WHERE created_at IS NULL", (now,))
        con.execute("UPDATE job SET updated_at = ? WHERE updated_at IS NULL", (now,))

        con.execute(HISTORY_TABLE)
        con.execute("CREATE INDEX IF NOT EXISTS ix_status_history_job_id ON status_history (job_id)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_job_company ON job (company)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_job_status ON job (status)")

        added = con.execute(
            """
            INSERT INTO status_history (job_id, from_status, to_status, changed_at)
            SELECT id, NULL, status, created_at FROM job
            WHERE id NOT IN (SELECT job_id FROM status_history)
            """
        ).rowcount
        con.commit()
        print(f"Created {added} starting history row(s). Upgrade complete.")
    finally:
        con.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "instance/jobs.db")
