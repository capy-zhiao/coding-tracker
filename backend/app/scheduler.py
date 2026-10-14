"""Builds the daily queue.

Every day you get three things:
  1. Due reviews  — what SRS says is due, ranked by priority(), capped at N
  2. New problems — NeetCode 150 in roadmap order, then Top Interview 150, then
                    LeetCode 75, each in its own order (Bit & Math wait), Hards last
  3. A template   — one of the 15 algorithm templates, also on an SRS schedule

Key design decision: **overflow defers**. Twenty problems may be due on a day you can only
finish four. Rather than dumping all twenty, the queue hands you the N that matter most and
rolls the rest forward.

Second decision: **the day is interleaved**. Ranking alone clusters: failures concentrate
in whichever chapter was hardest, so the top four can all be graph problems. Four of the
same kind in a row means you know the technique before reading the problem, which skips
the step an interview actually tests — recognising it. pick_diverse() caps each chapter
and each primary pattern per day, then backfills so no slot goes unused.
"""
from __future__ import annotations

import random
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .models import Problem, ReviewState
from .neetcode150 import NEETCODE_150_POSITION
from .study_plans import PLANS, first_plan
from .patterns import patterns_for
from .srs import priority


@dataclass
class QueueItem:
    problem: Problem
    reason: str                 # "due" | "new" | "template"
    priority_score: float = 0.0
    overdue_days: int = 0


@dataclass
class DailyQueue:
    reviews: list[QueueItem] = field(default_factory=list)
    new_problems: list[QueueItem] = field(default_factory=list)
    templates: list[QueueItem] = field(default_factory=list)
    total_due: int = 0          # how many are actually due (can exceed len(reviews))
    deferred: int = 0           # how many were pushed to a later day by the cap


def primary_pattern(problem) -> str | None:
    """The first pattern tag — the technique the problem is mainly testing."""
    tags = problem.patterns or patterns_for(problem.number, problem.chapter_num)
    return tags[0] if tags else None


def pick_diverse(
    items: list[QueueItem],
    cap: int,
    per_chapter: int,
    per_pattern: int,
) -> list[QueueItem]:
    """Take up to `cap` items in the given order, spreading across chapters and patterns.

    `items` must already be in preference order — by priority for reviews, by roadmap
    position for new problems — and the result keeps that order. An item is skipped when
    its chapter or its primary pattern already has its quota for the day; a limit of 0
    means unlimited. Skipped items then backfill any slot still empty, in that same order,
    so the rules only ever change which problems you get — never how many.

    Pure function (no database, no clock), so it is unit tested directly.
    """
    picked: list[tuple[int, QueueItem]] = []
    skipped: list[tuple[int, QueueItem]] = []
    by_chapter: Counter[int] = Counter()
    by_pattern: Counter[str] = Counter()

    for pos, item in enumerate(items):
        if len(picked) >= cap:
            break
        ch = item.problem.chapter_num
        pat = primary_pattern(item.problem)
        chapter_full = per_chapter > 0 and by_chapter[ch] >= per_chapter
        pattern_full = per_pattern > 0 and pat is not None and by_pattern[pat] >= per_pattern
        if chapter_full or pattern_full:
            skipped.append((pos, item))
            continue
        picked.append((pos, item))
        by_chapter[ch] += 1
        if pat is not None:
            by_pattern[pat] += 1

    # Everything skipped outranks everything not yet visited, so backfill from it first.
    for entry in skipped:
        if len(picked) >= cap:
            break
        picked.append(entry)

    picked.sort(key=lambda e: e[0])
    return [item for _, item in picked]


def roadmap_key(problem) -> tuple:
    """Chapter, then NeetCode's order within the chapter; other problems follow the 150
    in their chapter, by number."""
    pos = NEETCODE_150_POSITION.get(problem.number)
    return (problem.chapter_num, 0 if pos else 1, pos[1] if pos else problem.number)


def list_rank(problem, later_chapters: frozenset[int] = frozenset()) -> int:
    """Which list a new problem is drawn from: 0 = NeetCode 150, then 1, 2, ... for the
    study plans in PLANS order. NeetCode 150 problems in `later_chapters` wait with the
    first plan. A problem in several plans counts toward the first."""
    if problem.in_neetcode150:
        return 1 if problem.chapter_num in later_chapters else 0
    plan = first_plan(problem.number)
    return 1 + PLANS.index(plan) if plan else len(PLANS) + 1


def plan_key(problem, rank: int) -> tuple:
    """Order inside a study-plan tier: that plan's own sequence. Problems in the tier but
    not in the plan (deferred NeetCode chapters) follow, in roadmap order."""
    pos = PLANS[rank - 1].position.get(problem.number) if rank <= len(PLANS) else None
    return (0, pos, ()) if pos is not None else (1, 0, roadmap_key(problem))


def new_problem_tiers(
    problems,
    hard_last: bool = True,
    nc150_first: bool = True,
    later_chapters: frozenset[int] = frozenset(),
) -> list[list]:
    """Unstarted problems grouped into tiers, each exhausted before the next:

        Easy/Medium:  NeetCode 150 (roadmap order) -> Top Interview 150 -> LeetCode 75
        Hard:         the same three lists again

    The study plans follow their own order on LeetCode. hard_last=False merges the Hard
    tiers into the others; nc150_first=False puts everything in plain roadmap order.
    NeetCode 150 problems in `later_chapters` wait with Top Interview 150 (a study-plan
    choice, not a data change — they stay NeetCode 150). Empty tiers are dropped.
    """
    buckets: dict[tuple[bool, int], list] = {}
    for p in problems:
        held_back = hard_last and p.difficulty == "Hard"
        rank = list_rank(p, later_chapters) if nc150_first else 0
        buckets.setdefault((held_back, rank), []).append(p)

    tiers = []
    for (held_back, rank) in sorted(buckets):
        group = buckets[(held_back, rank)]
        if rank == 0:
            group.sort(key=roadmap_key)
        else:
            group.sort(key=lambda p, r=rank: plan_key(p, r))
        tiers.append(group)
    return tiers


def pick_tiered(
    tiers: list[list[QueueItem]], cap: int, per_chapter: int, per_pattern: int,
) -> list[QueueItem]:
    """Fill `cap` slots tier by tier. A tier is exhausted — backfill included — before the
    next one is touched, so spreading across chapters never pulls in a lower tier early."""
    picked: list[QueueItem] = []
    for tier in tiers:
        if len(picked) >= cap:
            break
        picked += pick_diverse(tier, cap - len(picked), per_chapter, per_pattern)
    return picked


def _load(db: Session, kind: str) -> list[Problem]:
    stmt = (
        select(Problem)
        .options(selectinload(Problem.state))
        .where(Problem.kind == kind)
    )
    return list(db.scalars(stmt))


def build_today(
    db: Session,
    today: date | None = None,
    review_cap: int | None = None,
    new_cap: int | None = None,
    shuffle: int | None = None,
    skip: Collection[int] = (),
) -> DailyQueue:
    """Today's queue.

    Reviews are ranked by priority, unless `shuffle` (a seed) is given: then they're picked
    at random — "Next batch" on the home screen. `skip` holds ids of the batch being
    replaced; they go to the back so the new batch is different whenever enough is due.
    """
    today = today or date.today()
    review_cap = review_cap if review_cap is not None else settings.daily_review_cap
    new_cap = new_cap if new_cap is not None else settings.daily_new_cap

    problems = _load(db, "problem")
    queue = DailyQueue()

    # --- 1. Due reviews, ranked, capped ---
    due_items: list[QueueItem] = []
    for p in problems:
        st = p.state
        if st is None or st.due is None or st.due > today:
            continue
        s = st.to_srs()
        due_items.append(QueueItem(
            problem=p,
            reason="due",
            priority_score=priority(s, today, p.difficulty, p.chapter_num),
            overdue_days=(today - st.due).days,
        ))
    due_items.sort(key=lambda i: i.priority_score, reverse=True)
    queue.total_due = len(due_items)
    if shuffle is not None:
        # Each problem gets its own random key, so the same seed gives the same batch, and
        # finishing one of them doesn't reshuffle the rest
        due_items.sort(key=lambda i: random.Random(f"{shuffle}:{i.problem.id}").random())
    skip = set(skip)
    due_items.sort(key=lambda i: i.problem.id in skip)   # stable: keeps the order above
    queue.reviews = pick_diverse(
        due_items, review_cap,
        settings.daily_per_chapter_cap, settings.daily_per_pattern_cap,
    )
    queue.deferred = len(due_items) - len(queue.reviews)

    # --- 2. New problems: NeetCode 150, then Top Interview 150, then LeetCode 75 ---
    fresh = [p for p in problems if p.state is None or p.state.due is None]
    tiers = new_problem_tiers(
        fresh, settings.new_hard_last, settings.new_neetcode150_first,
        settings.new_later_chapter_set,
    )
    queue.new_problems = pick_tiered(
        [[QueueItem(problem=p, reason="new") for p in tier] for tier in tiers], new_cap,
        settings.daily_new_per_chapter_cap, settings.daily_new_per_pattern_cap,
    )

    # --- 3. One template: the due one, otherwise whichever has gone longest untouched ---
    templates = _load(db, "template")
    t_due = [t for t in templates if t.state and t.state.due and t.state.due <= today]
    if t_due:
        t_due.sort(key=lambda t: (t.state.due, -t.state.lapses))
        pick = t_due[0]
    elif templates:
        pick = min(templates, key=lambda t: (
            t.state.last_attempt_at if t.state and t.state.last_attempt_at else 0,
        ))
    else:
        pick = None
    if pick is not None:
        queue.templates = [QueueItem(problem=pick, reason="template")]

    return queue


def forecast(db: Session, today: date | None = None, days: int = 14) -> list[dict]:
    """Review load for the next N days, so the UI can warn you before a pile-up.

    Problems only: template drills have their own one-a-day slot and never compete for
    the review cap, so counting them here would overstate the load the Review section
    actually hands you.
    """
    today = today or date.today()
    counts = {today + timedelta(days=i): 0 for i in range(days)}
    overdue = 0
    stmt = (
        select(ReviewState)
        .join(Problem, Problem.id == ReviewState.problem_id)
        .where(ReviewState.due.is_not(None), Problem.kind == "problem")
    )
    for st in db.scalars(stmt):
        if st.due < today:
            overdue += 1
        elif st.due in counts:
            counts[st.due] += 1
    out = [{"date": today.isoformat(), "count": counts[today] + overdue, "overdue": overdue}]
    out += [{"date": d.isoformat(), "count": c, "overdue": 0}
            for d, c in sorted(counts.items()) if d != today]
    return out
