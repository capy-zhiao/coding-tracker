"""Mock interview: random problem, timer, interviewer follow-ups.

Two kinds of follow-up:
  /followups   about the problem in general; generated once and cached per problem, with a
               generic offline fallback, so the flow works with no LLM configured
  /interview   about the code written in this session; the candidate answers each question
               in writing and the LLM grades the answer
"""
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..database import get_db
from ..deps import get_current_user, get_problem, states_for
from ..models import FollowUp, InterviewQA, Problem, User
from ..schemas import (
    AnswerGradeOut, AnswerIn, FollowUpOut, InterviewQuestionOut,
    InterviewStartIn, MockStartOut, ProblemDetail,
)

router = APIRouter(prefix="/mock", tags=["mock"])

DEFAULT_MINUTES = {"Easy": 20, "Medium": 35, "Hard": 45}

# Used when no LLM provider is configured, so the feature still works offline.
GENERIC_FOLLOWUPS = [
    ("What is the time and space complexity of your solution? Can it be improved?",
     "State where the current complexity comes from, then identify the bottleneck step."),
    ("What are the edge cases? Empty input, a single element, all elements identical?",
     "Name two or three concrete inputs and say what each should return."),
    ("If the input grew to a billion elements, would your approach still hold?",
     "Discuss memory limits, streaming, sharding, or an external-sort style approach."),
]


@router.post("/start", response_model=MockStartOut)
def start_mock(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    difficulty: str | None = Query(None, description="Restrict to a difficulty"),
    chapter: int | None = Query(None, description="Restrict to a chapter"),
    only_solved: bool = Query(False, description="Only draw problems you have solved before"),
):
    """Draw a random problem and start a mock interview."""
    stmt = select(Problem).where(Problem.kind == "problem")
    if difficulty:
        stmt = stmt.where(Problem.difficulty == difficulty)
    if chapter is not None:
        stmt = stmt.where(Problem.chapter_num == chapter)

    pool = list(db.scalars(stmt))
    states = states_for(db, user.id, "problem")
    if only_solved:
        pool = [p for p in pool if p.id in states and states[p.id].due]
    if not pool:
        raise HTTPException(404, "No problems match those filters")

    p = random.choice(pool)
    return MockStartOut(
        problem=ProblemDetail.of(p, states.get(p.id)),
        minutes=DEFAULT_MINUTES.get(p.difficulty, 35),
        followups_ready=bool(p.followups) or llm.is_enabled(),
    )


@router.get("/{number}/followups", response_model=list[FollowUpOut])
def get_followups(
    problem: Problem = Depends(get_problem),
    db: Session = Depends(get_db),
    regenerate: bool = Query(False),
):
    """Fetch follow-ups for a problem, generating and caching them on first request."""
    if problem.followups and not regenerate:
        return problem.followups

    if regenerate:
        for f in problem.followups:
            db.delete(f)
        db.flush()

    items = llm.generate_followups(
        problem.title, problem.number, problem.difficulty, problem.chapter
    )
    if not items:
        # No provider configured, or the call failed — fall back so the flow never breaks
        items = [llm.FollowUpItem(question=q, hint=h) for q, h in GENERIC_FOLLOWUPS]

    rows = [FollowUp(problem_id=problem.id, question=i.question, hint=i.hint) for i in items]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


@router.post("/{number}/interview", response_model=list[InterviewQuestionOut])
def start_code_interview(
    payload: InterviewStartIn,
    problem: Problem = Depends(get_problem),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate follow-up questions about the code written in this session.

    Key points are stored but not returned: they are revealed with the grade, so they
    cannot be read before answering.
    """
    if not llm.is_enabled():
        raise HTTPException(503, "AI interviews need LLM_PROVIDER and a key in backend/.env")
    if not payload.code.strip():
        raise HTTPException(400, "Write some code first — the questions are about your code")

    items = llm.interview_followups(
        problem.title, problem.number, problem.difficulty, payload.code,
        payload.time_complexity, payload.space_complexity,
    )
    if not items:
        raise HTTPException(502, "The AI call failed — the backend log has the reason")

    rows = [
        InterviewQA(user_id=user.id, problem_id=problem.id, code=payload.code,
                    question=i.question, key_points=i.hint)
        for i in items
    ]
    db.add_all(rows)
    db.commit()
    return [InterviewQuestionOut(id=r.id, question=r.question) for r in rows]


@router.post("/qa/{qa_id}/answer", response_model=AnswerGradeOut)
def answer_question(
    qa_id: int,
    payload: AnswerIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Grade a written answer. Answering again replaces the previous answer and grade."""
    if not llm.is_enabled():
        raise HTTPException(503, "AI grading needs LLM_PROVIDER and a key in backend/.env")
    qa = db.get(InterviewQA, qa_id)
    if qa is None or qa.user_id != user.id:      # someone else's looks like a missing one
        raise HTTPException(404, f"No interview question {qa_id}")
    if not payload.answer.strip():
        raise HTTPException(400, "The answer is empty")

    problem = qa.problem
    grade = llm.grade_answer(
        problem.title, problem.number, qa.code, qa.question, qa.key_points, payload.answer,
    )
    if grade is None:
        raise HTTPException(502, "The AI call failed — the backend log has the reason")

    qa.answer = payload.answer
    qa.grade = grade.model_dump()
    qa.answered_at = datetime.now(timezone.utc)
    db.commit()
    return AnswerGradeOut(
        id=qa.id, question=qa.question, answer=qa.answer, key_points=qa.key_points,
        score=grade.score, feedback=grade.feedback, missing=grade.missing,
        model_answer=grade.model_answer,
    )
