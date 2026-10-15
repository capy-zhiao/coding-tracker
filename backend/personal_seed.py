"""Your own starting point in local mode, from the NeetCode notes.

Problems marked solved in data/seed.json start out "due today", with the failure counts
from the old review plan, so the first daily queue picks up where the manual study plan
left off; every template starts due too. That history is one person's, so it only goes
to the local user: cloud accounts start from nothing.

Never changes a row that already exists, so start.sh runs it on every start: a problem
newly marked solved in the notes joins the reviews, and nothing practised is touched.

Usage:  python personal_seed.py      (after migrate.py and seed_db.py)
"""
from __future__ import annotations

import json
import sys

from sqlalchemy import inspect, select

from app.config import settings
from app.database import SessionLocal, engine
from app.deps import local_user, states_for, today
from app.models import Problem, ReviewState
from app.srs import DEFAULT_EASE
from seed_db import SEED

# Historic failure counts, migrated from the manual review plan. Without these every solved
# problem would share the same priority; with them the first queue surfaces the problems
# that were actually difficult.
KNOWN_LAPSES = {
    994: 3,   # Rotting Oranges: wrong counter, flag hack, -1 condition — three rewrites
    695: 3,   # Max Area of Island: type, pass-by-value, visited lookup, missing return
    261: 3,   # Graph Valid Tree: template copied wrong, flag overwrite, missing edge check
    130: 2,   # Surrounded Regions: digit zero vs letter O, missing guard on 'T'
    200: 2,   # Number of Islands: counter inside dfs, missing guard
    417: 2,   # Pacific Atlantic: both oceans shared one visited set
    207: 2,   # Course Schedule: adjacency direction reversed
    33:  1,   # Search in Rotated Sorted Array: only worked after heavy print debugging
    153: 1,
    424: 1,
    743: 1,   # Dijkstra: forgot to accumulate t1+t2, effectively wrote Prim
    853: 1,   # Car Fleet: "else if" instead of elif, missing return
    128: 1,   # Longest Consecutive Sequence: returned length instead of the max
}


def main() -> None:
    if settings.auth_mode != "local":
        print("Not in local mode - no personal seed.")
        return
    if not inspect(engine).has_table("problems"):
        sys.exit("No tables yet - run `python migrate.py` and `python seed_db.py` first.")

    notes = json.loads(SEED.read_text(encoding="utf-8"))["problems"]
    solved = {p["number"] for p in notes if p.get("solved")}
    db = SessionLocal()
    added = templates = 0
    try:
        user = local_user(db)
        d = today(user.timezone)
        states = states_for(db, user.id)
        for p in db.scalars(select(Problem)):
            if p.id in states:
                continue
            if p.kind == "problem" and p.number in solved:
                lapses = KNOWN_LAPSES.get(p.number, 0)
                db.add(ReviewState(
                    user_id=user.id, problem_id=p.id, interval_days=1,
                    # Problems that caused trouble get a lower ease, so gaps grow slower
                    ease=max(1.3, DEFAULT_EASE - 0.2 * lapses),
                    reps=1, lapses=lapses, due=d, total_attempts=0,
                ))
                added += 1
            elif p.kind == "template":
                db.add(ReviewState(user_id=user.id, problem_id=p.id, interval_days=0, due=d))
                templates += 1
        db.commit()
    finally:
        db.close()
    print(f"Personal seed: {added} solved problems and {templates} templates start due today")


if __name__ == "__main__":
    main()
