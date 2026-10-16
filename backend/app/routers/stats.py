"""Stats dashboard: progress, streaks, pattern proficiency and complexity accuracy."""
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import credit, llm
from ..complexity import EXPECTED, check as check_complexity
from ..database import get_db
from ..deps import get_current_user, local_date, require_owner, states_for, user_today
from ..models import Attempt, Problem, User
from ..patterns import PATTERN_TEMPLATE, PATTERNS, describe, label, patterns_for
from ..schemas import ChapterStat, ComplexityStat, PatternStat, StatsOut

router = APIRouter(prefix="/stats", tags=["stats"])

MASTERED_INTERVAL = 21   # an interval of 21+ days counts as "mastered"


def _streak(db: Session, user: User) -> int:
    """Consecutive days with at least one attempt, counting back from today.

    Grouping happens in Python rather than with SQL's date(), because created_at is stored
    in UTC: an evening session east of UTC would otherwise be filed under the next day and
    silently break the streak.
    """
    days = {
        local_date(a.created_at, user.timezone).isoformat()
        for a in db.scalars(select(Attempt).where(Attempt.user_id == user.id))
    }
    if not days:
        return 0
    cur = user_today(user)
    if cur.isoformat() not in days:
        cur = cur - timedelta(days=1)      # nothing today yet, so start from yesterday
        if cur.isoformat() not in days:
            return 0
    n = 0
    while cur.isoformat() in days:
        n += 1
        cur -= timedelta(days=1)
    return n


@router.get("", response_model=StatsOut)
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = user_today(user)
    problems = list(db.scalars(select(Problem).where(Problem.kind == "problem")))
    st = states_for(db, user.id, "problem").get

    started = sum(1 for p in problems if st(p.id) and st(p.id).due)
    mastered = sum(1 for p in problems if st(p.id) and st(p.id).interval_days >= MASTERED_INTERVAL)
    due_today = sum(1 for p in problems if st(p.id) and st(p.id).due and st(p.id).due <= d)

    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == user.id)))
    week_ago = d - timedelta(days=7)
    attempts_7d = sum(1 for a in attempts if local_date(a.created_at, user.timezone) >= week_ago)
    timed = [a.seconds for a in attempts if a.seconds > 0]

    by_chapter: list[ChapterStat] = []
    for ch in sorted({p.chapter_num for p in problems}):
        g = [p for p in problems if p.chapter_num == ch]
        by_chapter.append(ChapterStat(
            chapter_num=ch, chapter=g[0].chapter, total=len(g),
            started=sum(1 for p in g if st(p.id) and st(p.id).due),
            mastered=sum(1 for p in g if st(p.id) and st(p.id).interval_days >= MASTERED_INTERVAL),
        ))

    return StatsOut(
        total_problems=len(problems), started=started, mastered=mastered,
        due_today=due_today, attempts_total=len(attempts), attempts_7d=attempts_7d,
        streak_days=_streak(db, user),
        avg_seconds=int(sum(timed) / len(timed)) if timed else 0,
        by_chapter=by_chapter,
    )


@router.get("/heatmap")
def heatmap(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    days: int = Query(90, ge=1, le=371),
):
    """Attempts per day for the last N days — a GitHub-style contribution grid."""
    start = user_today(user) - timedelta(days=days)
    counter: Counter[str] = Counter()
    for a in db.scalars(select(Attempt).where(Attempt.user_id == user.id)):
        day = local_date(a.created_at, user.timezone)
        if day >= start:
            counter[day.isoformat()] += 1
    return [{"date": k, "count": v} for k, v in sorted(counter.items())]


# Weighting for the weakness score. Coverage dominates (you cannot be good at a pattern you
# have not practiced), then how often attempts collapse, then historic failures.
W_COVERAGE, W_AGAIN, W_LAPSE = 0.45, 0.35, 0.20


@router.get("/patterns", response_model=list[PatternStat])
def pattern_proficiency(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Proficiency grouped by algorithm pattern rather than by roadmap chapter.

    An interviewer asks "is this a sliding window or a monotonic stack", never "which
    chapter is this". Sorted weakest first, so the top of the list is the revision list.
    """
    problems = list(db.scalars(select(Problem).where(Problem.kind == "problem")))
    st = states_for(db, user.id, "problem").get
    by_id = {p.id: p for p in problems}

    # attempts grouped by problem, so each attempt is counted once per pattern
    attempts_by_problem: dict[int, list[Attempt]] = {}
    for a in db.scalars(select(Attempt).where(Attempt.user_id == user.id)):
        attempts_by_problem.setdefault(a.problem_id, []).append(a)

    buckets: dict[str, list[Problem]] = {pid: [] for pid in PATTERNS}
    for p in problems:
        for tag in (p.patterns or patterns_for(p.number, p.chapter_num)):
            buckets.setdefault(tag, []).append(p)

    out: list[PatternStat] = []
    for pid, group in buckets.items():
        if not group:
            continue
        total = len(group)
        started = sum(1 for p in group if st(p.id) and st(p.id).due)
        mastered = sum(
            1 for p in group
            if st(p.id) and st(p.id).interval_days >= MASTERED_INTERVAL
        )
        lapses = sum(st(p.id).lapses for p in group if st(p.id))

        atts = [a for p in group for a in attempts_by_problem.get(p.id, [])]
        timed = [a.seconds for a in atts if a.seconds > 0]
        again = sum(1 for a in atts if a.grade == "again")
        again_rate = again / len(atts) if atts else 0.0

        coverage_gap = 1.0 - (mastered / total)
        lapse_ratio = min(1.0, lapses / started) if started else 0.0
        weakness = (
            W_COVERAGE * coverage_gap + W_AGAIN * again_rate + W_LAPSE * lapse_ratio
        )

        out.append(PatternStat(
            id=pid, label=label(pid), description=describe(pid),
            total=total, started=started, mastered=mastered,
            attempts=len(atts),
            avg_seconds=int(sum(timed) / len(timed)) if timed else 0,
            again_rate=round(again_rate, 3),
            weakness=round(weakness, 3),
            template_number=PATTERN_TEMPLATE.get(pid),
        ))

    out.sort(key=lambda s: (-s.weakness, s.label))
    return out


@router.get("/complexity", response_model=ComplexityStat)
def complexity_accuracy(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """How often the self-reported big-O was right.

    An attempt counts when the AI has judged it or the problem has a reference answer;
    the rest are recorded but not graded, so the number never pretends to more certainty
    than it has. Where both exist, the AI verdict wins: it judged the code actually written.
    """
    numbers = {p.id: p.number for p in db.scalars(select(Problem))}
    answered = graded = t_ok = s_ok = both = 0
    wrong: Counter[int] = Counter()
    seen: Counter[int] = Counter()

    for a in db.scalars(select(Attempt).where(Attempt.user_id == user.id)):
        if not (a.time_complexity or a.space_complexity):
            continue
        answered += 1
        num = numbers.get(a.problem_id)
        if num is None:
            continue
        if a.complexity_ai:
            # The AI judged the code actually written — prefer it over the lookup table.
            verdict = {"time_ok": bool(a.complexity_ai.get("time_correct")),
                       "space_ok": bool(a.complexity_ai.get("space_correct"))}
        elif num in EXPECTED:
            verdict = check_complexity(num, a.time_complexity, a.space_complexity)
        else:
            continue
        graded += 1
        seen[num] += 1
        t_ok += verdict["time_ok"]
        s_ok += verdict["space_ok"]
        if verdict["time_ok"] and verdict["space_ok"]:
            both += 1
        else:
            wrong[num] += 1

    titles = {p.number: p.title for p in db.scalars(select(Problem))}
    worst = [
        {"number": n, "title": titles.get(n, ""), "wrong": c, "attempts": seen[n]}
        for n, c in wrong.most_common(8)
    ]
    return ComplexityStat(
        answered=answered, graded=graded,
        time_correct=t_ok, space_correct=s_ok, both_correct=both,
        accuracy=round(both / graded, 3) if graded else 0.0,
        worst=worst,
    )


@router.get("/credit", dependencies=[Depends(require_owner)])
def api_credit(refresh: bool = False):
    """Remaining credit on the server's LLM account (cached for a minute). The owner's
    account, so only the owner sees it."""
    if not llm.is_enabled():
        raise HTTPException(503, "AI features are off")
    result = credit.fetch_credit(force=refresh)
    if result is None:
        raise HTTPException(502, "The provider did not report a balance")
    return result
