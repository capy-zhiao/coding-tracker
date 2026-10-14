"""Daily queue and attempt submission — the entry point into the SRS engine."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from .. import llm
from ..complexity import COMPLEXITY_CHOICES, EXPECTED, check as check_complexity
from ..database import get_db
from ..deps import ensure_state, get_problem, today as get_today
from ..models import Attempt, Problem
from ..schemas import (
    AttemptIn, AttemptOut, AttemptResult, ComplexityCheck, DailyQueueOut,
    GradeSuggestion, StateOut,
)
from ..scheduler import build_today, forecast
from ..srs import review as srs_review, suggest_grade

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/today", response_model=DailyQueueOut)
def today_queue(
    db: Session = Depends(get_db),
    review_cap: int | None = Query(None, ge=0, le=50),
    new_cap: int | None = Query(None, ge=0, le=50),
    shuffle: int | None = Query(None, description="seed: pick reviews at random instead of by priority"),
    skip: list[int] = Query([], description="problem ids to put last in the review pick"),
):
    """What to work on today — this powers the home screen."""
    d = get_today()
    q = build_today(db, d, review_cap, new_cap, shuffle, skip)
    return DailyQueueOut(
        date=d,
        reviews=q.reviews, new_problems=q.new_problems, templates=q.templates,
        total_due=q.total_due, deferred=q.deferred,
        review_cap=review_cap if review_cap is not None else settings.daily_review_cap,
    )


@router.get("/forecast")
def review_forecast(db: Session = Depends(get_db), days: int = Query(14, ge=1, le=60)):
    """Upcoming review load, rendered as a bar chart in the UI."""
    return forecast(db, get_today(), days)


@router.get("/suggest-grade", response_model=GradeSuggestion)
def grade_suggestion(
    seconds: int = Query(..., ge=0),
    looked_at_solution: bool = False,
    had_bugs: bool = False,
    difficulty: str = "Medium",
):
    """Called when the timer stops; the UI pre-selects the returned grade."""
    g = suggest_grade(seconds, looked_at_solution, had_bugs, difficulty)  # type: ignore[arg-type]
    mins = seconds / 60
    reason = {
        "again": "Looked at the solution — back tomorrow",
        "hard": f"Took {mins:.0f} min or hit bugs — interval grows only slightly",
        "good": f"Solved smoothly in {mins:.0f} min",
        "easy": f"Nailed it in {mins:.0f} min — interval stretches a lot",
    }[g]
    return GradeSuggestion(grade=g, reason=reason)


@router.post("/{number}/attempt", response_model=AttemptResult)
def submit_attempt(
    payload: AttemptIn,
    problem: Problem = Depends(get_problem),
    db: Session = Depends(get_db),
):
    """Record an attempt and let SRS compute the next review date."""
    d = get_today()
    st = ensure_state(db, problem)

    # 1. Store this attempt
    attempt = Attempt(
        problem_id=problem.id,
        grade=payload.grade,
        seconds=payload.seconds,
        looked_at_solution=payload.looked_at_solution,
        had_bugs=payload.had_bugs,
        code=payload.code,
        note=payload.note,
        mode=payload.mode,
        time_complexity=payload.time_complexity.strip(),
        space_complexity=payload.space_complexity.strip(),
        blindwrite_score=payload.blindwrite_score,
    )

    # 1b. Grade the self-reported complexity. verdict is None when we have no reference,
    # which keeps "not graded" distinct from "answered wrong" in the stats.
    verdict = check_complexity(
        problem.number, payload.time_complexity, payload.space_complexity
    )
    if verdict is not None:
        attempt.complexity_ok = verdict["time_ok"] and verdict["space_ok"]
    db.add(attempt)

    # 2. Run the SRS step (pure function, easy to test)
    new_state = srs_review(st.to_srs(), payload.grade, problem.difficulty, d)  # type: ignore[arg-type]
    st.apply(new_state)
    st.total_attempts += 1
    st.last_attempt_at = datetime.now(timezone.utc)
    if payload.seconds > 0 and (st.best_seconds is None or payload.seconds < st.best_seconds):
        st.best_seconds = payload.seconds

    # 3. Keep the latest solution on the problem so the next pass can diff against it
    if payload.code.strip():
        problem.code = payload.code

    db.commit()
    db.refresh(attempt)
    db.refresh(st)
    return AttemptResult(
        attempt=AttemptOut.model_validate(attempt),
        state=StateOut.model_validate(st),
        next_due_in_days=new_state.interval_days,
        complexity=(
            ComplexityCheck(graded=True, **verdict) if verdict
            else ComplexityCheck(graded=False)
        ),
    )


@router.get("/complexity-choices")
def complexity_choices():
    """Fills the complexity dropdowns. Free text is accepted too — it is recorded, not graded."""
    return COMPLEXITY_CHOICES


@router.get("/{number}/attempts", response_model=list[AttemptOut])
def attempt_history(problem: Problem = Depends(get_problem)):
    """History for this problem — lets you diff this attempt against the previous one."""
    return problem.attempts


@router.post("/attempts/{attempt_id}/complexity-ai", response_model=AttemptOut)
def ai_complexity(attempt_id: int, db: Session = Depends(get_db)):
    """Have the LLM judge the stated complexity against the code actually submitted.

    Separate from submitting, because a thinking-mode reply can take tens of seconds and
    must not hold up recording the attempt. The verdict is stored on the attempt and, since
    it judges the real code rather than the textbook solution, decides complexity_ok.
    """
    if not llm.is_enabled():
        raise HTTPException(503, "AI features are off — set LLM_PROVIDER and a key in backend/.env")
    attempt = db.get(Attempt, attempt_id)
    if attempt is None:
        raise HTTPException(404, f"No attempt {attempt_id}")
    if not attempt.code.strip():
        raise HTTPException(400, "This attempt has no code to analyse")

    problem = attempt.problem
    verdict = llm.analyze_complexity(
        problem.title, problem.number, attempt.code,
        attempt.time_complexity, attempt.space_complexity,
        EXPECTED.get(problem.number),
    )
    if verdict is None:
        raise HTTPException(502, "The AI call failed — the backend log has the reason")

    already_optimal = verdict.time_optimal and verdict.space_optimal
    code, diff = ("", []) if already_optimal else llm.optimized_patch(attempt.code, verdict.optimized_code)
    attempt.complexity_ai = {
        **verdict.model_dump(),
        "optimized_code": code,          # validated, or "" when not worth showing
        "optimized_diff": diff,          # unified diff against the submitted code
        "model": llm.model_name("complexity"),
    }
    attempt.complexity_ok = verdict.time_correct and verdict.space_correct
    db.commit()
    db.refresh(attempt)
    return attempt
