"""Request/response shapes (Pydantic v2).

Deliberately separate from the ORM models so internal schema changes don't leak into the API.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .srs import Difficulty, Grade


class MeOut(BaseModel):
    """The signed-in user, plus what the frontend needs to know about this deployment."""
    id: int
    login: str
    display_name: str
    avatar_url: str
    provider: str
    is_owner: bool
    is_demo: bool
    ai_enabled: bool
    timezone: str | None
    daily_review_cap: int
    daily_new_cap: int
    auth_mode: str
    today: date         # the user's study day; the browser's own date can differ


class StateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    interval_days: int
    ease: float
    reps: int
    lapses: int
    due: date | None
    total_attempts: int
    best_seconds: int | None


class ProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: int
    title: str
    difficulty: str
    chapter_num: int
    chapter: str
    url: str
    in_neetcode150: bool
    in_top150: bool = False
    in_lc75: bool = False
    kind: str
    patterns: list[str] = []
    state: StateOut | None = None


class ProblemDetail(ProblemOut):
    notes: str = ""
    code: str = ""


class QueueItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    problem: ProblemOut
    reason: str
    priority_score: float = 0.0
    overdue_days: int = 0


class DailyQueueOut(BaseModel):
    date: date
    reviews: list[QueueItemOut]
    new_problems: list[QueueItemOut]
    templates: list[QueueItemOut]
    total_due: int
    deferred: int
    review_cap: int              # reviews per day, for "N days to clear the backlog"


class AttemptIn(BaseModel):
    """Payload for recording one attempt."""
    grade: Grade
    seconds: int = Field(0, ge=0)
    looked_at_solution: bool = False
    had_bugs: bool = False
    code: str = ""
    note: str = ""
    mode: str = "practice"
    # Required by the UI, not by the schema — an older client that omits them still works.
    time_complexity: str = ""
    space_complexity: str = ""
    blindwrite_score: float | None = None   # template drills only


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    problem_id: int
    created_at: datetime
    grade: str
    seconds: int
    note: str
    mode: str
    code: str = ""
    time_complexity: str = ""
    space_complexity: str = ""
    complexity_ok: bool | None = None
    complexity_ai: dict | None = None


class ComplexityCheck(BaseModel):
    """Verdict on the self-reported complexity. graded=False means we have no reference."""
    graded: bool
    time_ok: bool = False
    space_ok: bool = False
    expected_time: str = ""
    expected_space: str = ""
    accepted_time: list[str] = []
    accepted_space: list[str] = []


class AttemptResult(BaseModel):
    """Returned after submitting: the new SRS state plus when this problem comes back."""
    attempt: AttemptOut
    state: StateOut
    next_due_in_days: int
    complexity: ComplexityCheck | None = None


class GradeSuggestion(BaseModel):
    grade: Grade
    reason: str


class ChapterStat(BaseModel):
    chapter_num: int
    chapter: str
    total: int
    started: int
    mastered: int          # interval >= 21 days counts as mastered


class StatsOut(BaseModel):
    total_problems: int
    started: int
    mastered: int
    due_today: int
    attempts_total: int
    attempts_7d: int
    streak_days: int
    avg_seconds: int
    by_chapter: list[ChapterStat]


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    question: str
    hint: str


class MockStartOut(BaseModel):
    problem: ProblemDetail
    minutes: int
    followups_ready: bool


# --- template blind-write ---

class BlindWriteIn(BaseModel):
    code: str


class CheckItem(BaseModel):
    id: str
    label: str
    why: str
    passed: bool


class BlindWriteOut(BaseModel):
    """Result of grading a blind-written template against the reference."""
    number: int
    name: str
    passed: bool
    similarity: float
    checks: list[CheckItem]
    missing: list[str]
    diff: list[str]
    verdict: str
    suggested_grade: Grade
    reference: str = ""          # withheld until the first attempt has been graded


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    number: int
    title: str
    chapter: str
    check_count: int = 0
    state: StateOut | None = None


# --- pattern proficiency ---

class PatternStat(BaseModel):
    id: str
    label: str
    description: str
    total: int
    started: int
    mastered: int
    attempts: int
    avg_seconds: int
    again_rate: float            # share of attempts graded "again"
    weakness: float              # 0..1, higher = needs work. Drives the sort order.
    template_number: int | None = None


class ComplexityStat(BaseModel):
    answered: int
    graded: int
    time_correct: int
    space_correct: int
    both_correct: int
    accuracy: float
    worst: list[dict]            # problems most often answered wrong


# --- code-aware mock interview ---

class InterviewStartIn(BaseModel):
    code: str
    time_complexity: str = ""
    space_complexity: str = ""


class InterviewQuestionOut(BaseModel):
    """A question as shown before answering — key points deliberately left out."""
    id: int
    question: str


class AnswerIn(BaseModel):
    answer: str


class AnswerGradeOut(BaseModel):
    id: int
    question: str
    answer: str
    key_points: str
    score: int                 # 1 weak · 2 partial · 3 good · 4 strong
    feedback: str
    missing: list[str]
    model_answer: str
