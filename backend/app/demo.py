"""The shared demo account: six weeks of believable practice, regenerated every day.

Someone looking at the deployed app can press "Try the demo" without a GitHub account and
land in a populated account: reviews due, a streak, a heatmap, weak patterns. It is shared
by every visitor, so it is wiped and rebuilt daily (see run_resets in main.py).

The history is simulated, not hand-written: each day picks the due reviews and a few new
problems in roadmap order and runs them through the same srs.review() the app uses, with
grades drawn from a fixed seed. Dates are relative to today, so every reset produces the
same six weeks shifted to the current date.

    python -m app.demo reset      rebuild it now
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .complexity import EXPECTED, check
from .models import Attempt, InterviewQA, Problem, ProblemNote, ReviewState, User
from .scheduler import roadmap_key
from .srs import SrsState, review

DAYS = 42                     # how far back the history starts
SEED = 42
GRADES = ["again", "hard", "good", "easy"]
GRADE_WEIGHTS = [0.12, 0.23, 0.5, 0.15]
MINUTES = {"Easy": (5, 15), "Medium": (12, 35), "Hard": (25, 55)}
REVIEWS_PER_DAY = 4
NEW_PER_DAY = (1, 3)
WRONG_ANSWER = "O(n^2)"       # what a wrong complexity answer looks like
EVENING_UTC = time(23, 0)     # practice sessions start around 7pm in North America


def demo_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.provider == "demo", User.provider_id == "demo"))
    if user is None:
        user = User(provider="demo", provider_id="demo", login="demo",
                    display_name="Demo account", is_demo=True)
        db.add(user)
        db.flush()
    return user


def reset_demo(db: Session, today: date) -> User:
    """Delete everything the demo account has and rebuild its history up to yesterday."""
    user = demo_user(db)
    for model in (Attempt, InterviewQA, ProblemNote, ReviewState):
        db.execute(delete(model).where(model.user_id == user.id))
    user.timezone = user.daily_review_cap = user.daily_new_cap = None   # undo visitors' edits

    rng = random.Random(SEED)
    roadmap = sorted(db.scalars(select(Problem).where(Problem.kind == "problem",
                                                      Problem.in_neetcode150)),
                     key=roadmap_key)
    templates = list(db.scalars(select(Problem).where(Problem.kind == "template")
                                .order_by(Problem.number)))
    by_id = {p.id: p for p in roadmap + templates}
    states: dict[int, SrsState] = {}
    last: dict[int, datetime] = {}
    totals: dict[int, int] = {}
    best: dict[int, int] = {}
    next_new = 0

    for back in range(DAYS, 0, -1):
        day = today - timedelta(days=back)
        if back > 9 and rng.random() < 0.15:
            continue                      # an occasional day off, but a live streak at the end
        due = sorted((pid for pid, s in states.items() if s.due and s.due <= day),
                     key=lambda pid: states[pid].due)
        problem_due = [pid for pid in due if by_id[pid].kind == "problem"][:REVIEWS_PER_DAY]
        fresh = []
        for _ in range(rng.randint(*NEW_PER_DAY)):
            if next_new < len(roadmap):
                fresh.append(roadmap[next_new].id)
                next_new += 1
        drill = []
        if templates and back % 3 == 0:   # a template drill every third day
            drill = [templates[(back // 3) % len(templates)].id]

        start = datetime.combine(day, EVENING_UTC)
        for i, pid in enumerate(problem_due + fresh + drill):
            p = by_id[pid]
            grade = rng.choices(GRADES, GRADE_WEIGHTS)[0]
            states[pid] = review(states.get(pid, SrsState()), grade, p.difficulty, day)
            seconds = rng.randint(*MINUTES.get(p.difficulty, (10, 30))) * 60
            when = start + timedelta(minutes=30 * i)
            last[pid] = when
            totals[pid] = totals.get(pid, 0) + 1
            best[pid] = min(best.get(pid, seconds), seconds)
            db.add(_attempt(user.id, p, grade, seconds, when, rng))

    for pid, s in states.items():
        db.add(ReviewState(
            user_id=user.id, problem_id=pid, interval_days=s.interval_days, ease=s.ease,
            reps=s.reps, lapses=s.lapses, due=s.due, last_attempt_at=last[pid],
            total_attempts=totals[pid], best_seconds=best[pid],
        ))
    user.demo_reset_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return user


def _attempt(user_id: int, p: Problem, grade: str, seconds: int, when: datetime,
             rng: random.Random) -> Attempt:
    if p.kind == "template":
        return Attempt(user_id=user_id, problem_id=p.id, created_at=when, grade=grade,
                       seconds=seconds, mode="drill",
                       blindwrite_score=round(rng.uniform(0.6, 1.0), 2))
    ref = EXPECTED.get(p.number)
    right = ref is not None and rng.random() < 0.8
    t_ans = ref[0][0] if right else WRONG_ANSWER
    s_ans = ref[1][0] if right else "O(n)"
    verdict = check(p.number, t_ans, s_ans)
    return Attempt(
        user_id=user_id, problem_id=p.id, created_at=when, grade=grade, seconds=seconds,
        looked_at_solution=grade == "again", had_bugs=grade in ("again", "hard"),
        mode="practice", time_complexity=t_ans, space_complexity=s_ans,
        complexity_ok=(verdict["time_ok"] and verdict["space_ok"]) if verdict else None,
    )


def needs_reset(user: User | None, now: datetime) -> bool:
    return (user is None or user.demo_reset_at is None
            or now - user.demo_reset_at >= timedelta(hours=24))


if __name__ == "__main__":
    if sys.argv[1:] != ["reset"]:
        sys.exit("usage: python -m app.demo reset")
    from .database import SessionLocal
    from .deps import today

    with SessionLocal() as session:
        u = reset_demo(session, today())
        n = session.query(Attempt).filter_by(user_id=u.id).count()
        print(f"Demo account rebuilt: {n} attempts over {DAYS} days")
