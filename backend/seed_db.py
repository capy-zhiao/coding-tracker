"""Build the problem set (NeetCode 150 + LeetCode's Top Interview 150 and LeetCode 75)
and the 15 templates.

Problems come from data/seed.json (extracted from the NeetCode markdown notes, with notes
and solutions) and the study plans in data/ (see app/study_plans.py). Problems in none of
the lists are removed — but only if they have no practice history.

Usage:  python seed_db.py    incremental: add new problems, keep attempt history

Run migrate.py first: it creates and upgrades the tables, this only fills them.

This is the catalogue everyone shares. Personal starting data (problems already solved in
the notes start out due) is personal_seed.py, for the local user only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import delete, exists, select

from sqlalchemy import inspect

from app.database import SessionLocal, engine
from app.models import Attempt, InterviewQA, Problem, ReviewState
from app.neetcode150 import NEETCODE_150
from app.study_plans import (
    CHAPTER_NAMES, LC_75, PROBLEM_SET, TOP_150, chapter_for, plan_entry,
)
from app.patterns import patterns_for

SEED = Path(__file__).resolve().parent.parent / "data" / "seed.json"

# The 15 templates from the notes. They ride the same SRS machinery.
TEMPLATES = [
    (9001, "Union-Find", 11, "Graphs", "Hard"),
    (9002, "Grid DFS (three guards)", 11, "Graphs", "Medium"),
    (9003, "Multi-source BFS (level loop)", 11, "Graphs", "Medium"),
    (9004, "Topological sort (Kahn)", 11, "Graphs", "Medium"),
    (9005, "Backtracking skeleton", 10, "Backtracking", "Medium"),
    (9006, "Binary search (closed interval)", 5, "Binary Search", "Medium"),
    (9007, "Sliding window", 3, "Sliding Window", "Medium"),
    (9008, "Monotonic stack", 4, "Stack", "Medium"),
    (9009, "Linked list trio", 6, "Linked List", "Medium"),
    (9010, "Tree DFS and BFS", 7, "Trees", "Easy"),
    (9011, "Trie", 8, "Tries", "Medium"),
    (9012, "Heap (heapq)", 9, "Heap / Priority Queue", "Easy"),
    (9013, "Dijkstra / Prim / Bellman-Ford", 12, "Advanced Graphs", "Hard"),
    (9014, "DP three questions + memoization", 13, "1-D DP", "Medium"),
    (9015, "Interval merge + sweep line", 16, "Intervals", "Medium"),
]


def _has_history(db, problem_id: int) -> bool:
    """Whether any user has practised this problem: an attempt, a scheduled review, or a
    mock-interview question."""
    return bool(
        db.scalar(select(exists().where(Attempt.problem_id == problem_id)))
        or db.scalar(select(exists().where(ReviewState.problem_id == problem_id,
                                           ReviewState.due.is_not(None))))
        or db.scalar(select(exists().where(InterviewQA.problem_id == problem_id)))
    )


def main() -> None:
    if not inspect(engine).has_table("problems"):
        sys.exit("No tables yet - run `python migrate.py` first.")

    seed = {p["number"]: p for p in json.loads(SEED.read_text(encoding="utf-8"))["problems"]}
    db = SessionLocal()
    added = updated = removed = 0
    kept_with_history: list[int] = []

    def item_for(number: int) -> dict:
        """One problem's fields: from the notes if it's there, otherwise from its study
        plan. Anything in a LeetCode study plan links to LeetCode
        (via the first plan it appears in); only NeetCode-only problems keep neetcode.io."""
        entry = plan_entry(number)
        if number in seed:
            item = dict(seed[number])
            if entry:
                plan, q = entry
                item["url"] = plan.url(q["slug"])
            return item
        plan, q = entry
        ch = chapter_for(number, q["group"])
        return {"number": number, "title": q["title"], "difficulty": q["difficulty"],
                "chapter_num": ch, "chapter": CHAPTER_NAMES[ch], "url": plan.url(q["slug"])}

    try:
        existing = {p.number: p for p in db.scalars(select(Problem))}

        for number in sorted(PROBLEM_SET):
            item = item_for(number)
            p = existing.get(number)
            if p is None:
                p = Problem(
                    number=number, title=item["title"],
                    difficulty=item["difficulty"], chapter_num=item["chapter_num"],
                    chapter=item["chapter"], url=item["url"],
                    in_neetcode150=number in NEETCODE_150, in_top150=number in TOP_150,
                    in_lc75=number in LC_75,
                    kind="problem",
                    patterns=patterns_for(number, item["chapter_num"]),
                )
                db.add(p)
                db.flush()
                added += 1
            else:
                # Refresh static fields without touching attempt history
                p.title, p.difficulty = item["title"], item["difficulty"]
                p.url = item["url"] or p.url
                # Derived data — always refreshed, so editing patterns.py or the lists
                # takes effect on the next run
                p.patterns = patterns_for(number, p.chapter_num)
                p.in_neetcode150 = number in NEETCODE_150
                p.in_top150 = number in TOP_150
                p.in_lc75 = number in LC_75
                updated += 1

        # Problems no longer in any list. Anything anyone has practised stays.
        for number, p in existing.items():
            if p.kind != "problem" or number in PROBLEM_SET:
                continue
            if _has_history(db, p.id):
                kept_with_history.append(number)
                continue
            db.execute(delete(ReviewState).where(ReviewState.problem_id == p.id))
            db.delete(p)
            removed += 1

        t_added = 0
        for num, name, ch_num, ch, diff in TEMPLATES:
            if num in existing:
                continue
            t = Problem(
                number=num, title=name, difficulty=diff, chapter_num=ch_num,
                chapter=ch, url="", in_neetcode150=False, kind="template", patterns=[],
            )
            db.add(t)
            t_added += 1

        db.commit()
    finally:
        db.close()

    print("\nImport complete")
    print(f"  problems added: {added}   updated: {updated}   removed: {removed}")
    if kept_with_history:
        print(f"  not in either list but kept (has practice history): {kept_with_history}")
    print(f"  templates: {t_added}")
    print(f"  pattern tags refreshed on {added + updated} problems")


if __name__ == "__main__":
    main()
