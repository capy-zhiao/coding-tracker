"""Additive schema migration, run before the app starts.

SQLAlchemy's create_all() creates missing TABLES but never adds a column to a table that
already exists, so a running database silently lacks any column added later. This script
closes that gap for the only kind of change made so far — adding a nullable/defaulted
column — and takes a dated backup first, because the database holds practice history that
exists nowhere else (tracker.db is gitignored on purpose).

Idempotent: safe to run on every start.
Not a substitute for Alembic once columns start being renamed or dropped.
"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import settings


def _sqlite_path(url: str) -> Path | None:
    """The database file behind a sqlite:/// URL, or None for any other database.

    Relative paths resolve against the working directory, as SQLAlchemy does: start.sh
    runs this from backend/, so the default sqlite:///./tracker.db is backend/tracker.db.
    In Docker, DATABASE_URL=sqlite:////data/tracker.db points at the mounted volume.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix) or url.endswith(":memory:"):
        return None
    path = Path(url[len(prefix):])
    return path if path.is_absolute() else Path.cwd() / path


DB = _sqlite_path(settings.database_url)
BACKUP_DIR = DB.parent / ".backups" if DB else None
KEEP_BACKUPS = 7

# table -> [(column, SQL type + default)]
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "problems": [
        ("patterns", "TEXT DEFAULT '[]'"),
        ("in_top150", "BOOLEAN DEFAULT 0"),
        ("in_lc75", "BOOLEAN DEFAULT 0"),
    ],
    "attempts": [
        ("time_complexity", "VARCHAR(40) DEFAULT ''"),
        ("space_complexity", "VARCHAR(40) DEFAULT ''"),
        ("complexity_ok", "BOOLEAN"),
        ("blindwrite_score", "FLOAT"),
        ("complexity_ai", "TEXT"),
    ],
}


def backup() -> Path | None:
    """Keep the last KEEP_BACKUPS dated copies. Cheap insurance for a file with no remote."""
    if not DB.exists():
        return None
    BACKUP_DIR.mkdir(exist_ok=True)
    dest = BACKUP_DIR / f"tracker-{datetime.now():%Y-%m-%d-%H%M%S}.db"
    shutil.copy2(DB, dest)
    old = sorted(BACKUP_DIR.glob("tracker-*.db"))[:-KEEP_BACKUPS]
    for f in old:
        f.unlink()
    return dest


def main() -> None:
    if DB is None:
        print("DATABASE_URL is not a SQLite file — this script only migrates SQLite; skipping.")
        return
    if not DB.exists():
        print("No database yet — seed_db.py will create it with the current schema.")
        return

    saved = backup()
    if saved:
        print(f"Backup: .backups/{saved.name}")

    con = sqlite3.connect(DB)
    added = 0
    try:
        for table, cols in COLUMNS.items():
            existing = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            if not existing:
                continue                       # table not created yet; create_all handles it
            for name, decl in cols:
                if name in existing:
                    continue
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                print(f"  + {table}.{name}")
                added += 1
        con.commit()
    finally:
        con.close()

    print(f"Schema up to date ({added} column{'' if added == 1 else 's'} added)")


if __name__ == "__main__":
    main()
