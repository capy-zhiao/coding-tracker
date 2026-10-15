"""Move one user's practice history between databases or accounts, e.g. your local history
into your GitHub account on the deployed server.

    python -m app.tools export --login local > history.json
    python -m app.tools import --login capy-zhiao history.json

Problems are identified by LeetCode number, because row ids differ between databases.
Import replaces everything the target user has; they must have signed in once so their
account exists. Problems the target database doesn't have are skipped and counted.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Attempt, InterviewQA, Problem, ProblemNote, ReviewState, User

FORMAT_VERSION = 1
# Every personal table, by its name in the export file
TABLES = {"review_states": ReviewState, "attempts": Attempt, "notes": ProblemNote,
          "interview_qas": InterviewQA}
NOT_EXPORTED = {"id", "user_id", "problem_id"}      # local to one database
SETTINGS = ("timezone", "daily_review_cap", "daily_new_cap")


def export_user(db: Session, user: User) -> dict:
    numbers = {p.id: p.number for p in db.scalars(select(Problem))}
    out: dict = {
        "version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": {name: getattr(user, name) for name in SETTINGS},
    }
    for key, model in TABLES.items():
        rows = db.scalars(select(model).where(model.user_id == user.id))
        out[key] = [_row_out(r, numbers[r.problem_id]) for r in rows]
    return out


def import_user(db: Session, user: User, data: dict) -> dict[str, int]:
    if data.get("version") != FORMAT_VERSION:
        raise ValueError(f"unsupported export version {data.get('version')!r}")
    ids = {p.number: p.id for p in db.scalars(select(Problem))}
    for model in TABLES.values():
        db.execute(delete(model).where(model.user_id == user.id))
    for name in SETTINGS:
        setattr(user, name, data.get("settings", {}).get(name))

    counts = {"skipped": 0}
    for key, model in TABLES.items():
        counts[key] = 0
        for row in data.get(key, []):
            pid = ids.get(row.get("number"))
            if pid is None:
                counts["skipped"] += 1
                continue
            db.add(_row_in(model, row, user.id, pid))
            counts[key] += 1
    db.commit()
    return counts


def _row_out(obj, number: int) -> dict:
    row = {"number": number}
    for col in obj.__table__.columns:
        if col.name in NOT_EXPORTED:
            continue
        value = getattr(obj, col.name)
        row[col.name] = value.isoformat() if isinstance(value, (date, datetime)) else value
    return row


def _row_in(model, row: dict, user_id: int, problem_id: int):
    values = {}
    for col in model.__table__.columns:
        if col.name in NOT_EXPORTED or col.name not in row:
            continue
        value = row[col.name]
        if value is not None and isinstance(col.type, sa.DateTime):
            value = datetime.fromisoformat(value)
        elif value is not None and isinstance(col.type, sa.Date):
            value = date.fromisoformat(value)
        values[col.name] = value
    return model(user_id=user_id, problem_id=problem_id, **values)


def find_user(db: Session, login: str) -> User:
    users = db.scalars(select(User).where(User.login == login)).all()
    if not users:
        sys.exit(f"No user {login!r}. In github mode they have to sign in once first.")
    if len(users) > 1:
        sys.exit(f"More than one user is called {login!r}")
    return users[0]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.tools", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="write a user's history to stdout as JSON")
    exp.add_argument("--login", required=True)
    imp = sub.add_parser("import", help="replace a user's history with an export file")
    imp.add_argument("--login", required=True)
    imp.add_argument("file")
    args = parser.parse_args(argv)

    from .database import SessionLocal

    with SessionLocal() as db:
        user = find_user(db, args.login)
        if args.command == "export":
            json.dump(export_user(db, user), sys.stdout, indent=1, ensure_ascii=False)
            print()
        else:
            with open(args.file, encoding="utf-8") as f:
                counts = import_user(db, user, json.load(f))
            print(f"Imported into {user.login}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
