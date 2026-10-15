"""Bring the database schema up to date. start.sh and the Docker entrypoint run this before
the app starts.

Schema changes are Alembic migrations (alembic/versions/). This script adds the two things
a personal SQLite database needs around them:

- a dated backup first, because tracker.db is gitignored and holds practice history that
  exists nowhere else;
- adopting databases created before Alembic: they get the columns that used to be added
  by hand here, then are marked as being at the baseline revision instead of running it,
  since their tables already exist.

Idempotent: safe to run on every start. On Postgres there's no file to copy, so it only
runs the migrations; back that up with pg_dump.
"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.config import settings

BACKEND = Path(__file__).resolve().parent
BASELINE = "0001"
KEEP_BACKUPS = 7

# Columns that were added by hand before Alembic. A database older than any of them gets
# them here, so it matches the baseline before it is marked as being at it.
# table -> [(column, SQL type + default)]
PRE_ALEMBIC_COLUMNS: dict[str, list[tuple[str, str]]] = {
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


def sqlite_path(url: str) -> Path | None:
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


def backup(db: Path) -> Path | None:
    """Keep the last KEEP_BACKUPS dated copies. Cheap insurance for a file with no remote."""
    if not db.exists():
        return None
    backup_dir = db.parent / ".backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"tracker-{datetime.now():%Y-%m-%d-%H%M%S}.db"
    shutil.copy2(db, dest)
    for old in sorted(backup_dir.glob("tracker-*.db"))[:-KEEP_BACKUPS]:
        old.unlink()
    return dest


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))   # ini-file escaping
    cfg.attributes["configure_logger"] = False                     # keep our own output
    return cfg


def current_revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def _table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _add_pre_alembic_columns(db: Path) -> list[str]:
    con = sqlite3.connect(db)
    added = []
    try:
        for table, cols in PRE_ALEMBIC_COLUMNS.items():
            existing = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if existing and name not in existing:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                    added.append(f"{table}.{name}")
        con.commit()
    finally:
        con.close()
    return added


def migrate(url: str) -> None:
    db = sqlite_path(url)
    if db is not None and db.exists():
        saved = backup(db)
        if saved:
            print(f"Backup: {saved.parent.name}/{saved.name}")

    cfg = alembic_config(url)
    tables = _table_names(url)
    if tables and "alembic_version" not in tables:
        if db is not None:
            for col in _add_pre_alembic_columns(db):
                print(f"  + {col}")
        command.stamp(cfg, BASELINE)
        print(f"Existing database adopted at revision {BASELINE}")

    before = current_revision(url)
    command.upgrade(cfg, "head")
    after = current_revision(url)
    if before == after:
        print(f"Schema up to date (revision {after})")
    else:
        print(f"Schema migrated: {before or 'empty'} -> {after}")


def main() -> None:
    migrate(settings.database_url)


if __name__ == "__main__":
    main()
