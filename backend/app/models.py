"""Database tables (SQLAlchemy 2.0 style).

  User        — who is practising; local mode has exactly one
  Problem     — static information for the problems and templates
  ReviewState — SRS state per problem (1:1); the persisted form of srs.SrsState
  Attempt     — one row per attempt (1:N); powers stats, code diffs and complexity accuracy
  FollowUp    — cached interviewer follow-up questions (1:N)
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .srs import DEFAULT_EASE, SrsState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Someone practising. Local mode has exactly one (provider "local"), created on the
    first request; cloud mode adds one per GitHub account, plus a shared demo account.

    The nullable settings override the matching .env values for this user only.
    """
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("provider", "provider_id", name="uq_users_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))             # local | github | demo
    provider_id: Mapped[str] = mapped_column(String(64))          # e.g. the GitHub user id
    login: Mapped[str] = mapped_column(String(100), index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    avatar_url: Mapped[str] = mapped_column(String(300), default="")
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    daily_review_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_new_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    demo_reset_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)  # LeetCode number
    title: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[str] = mapped_column(String(10))          # Easy / Medium / Hard
    chapter_num: Mapped[int] = mapped_column(Integer, index=True)
    chapter: Mapped[str] = mapped_column(String(60))
    url: Mapped[str] = mapped_column(String(300), default="")
    in_neetcode150: Mapped[bool] = mapped_column(Boolean, default=True)
    in_top150: Mapped[bool] = mapped_column(Boolean, default=False)   # LeetCode Top Interview 150
    in_lc75: Mapped[bool] = mapped_column(Boolean, default=False)     # LeetCode 75
    kind: Mapped[str] = mapped_column(String(20), default="problem")  # problem | template
    notes: Mapped[str] = mapped_column(Text, default="")         # migrated from markdown notes
    code: Mapped[str] = mapped_column(Text, default="")          # most recent accepted solution
    # Algorithm patterns (see patterns.py). Cuts across chapters: 239 sits in the Sliding
    # Window chapter but is really a monotonic deque.
    patterns: Mapped[list] = mapped_column(JSON, default=list)

    state: Mapped["ReviewState"] = relationship(
        back_populates="problem", uselist=False, cascade="all, delete-orphan"
    )
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan",
        order_by="Attempt.created_at.desc()",
    )
    followups: Mapped[list["FollowUp"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan"
    )
    interview_qas: Mapped[list["InterviewQA"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan"
    )


class ReviewState(Base):
    """SRS state. Fields mirror srs.SrsState one for one."""
    __tablename__ = "review_states"

    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), primary_key=True)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    ease: Mapped[float] = mapped_column(Float, default=DEFAULT_EASE)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    due: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    best_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    problem: Mapped[Problem] = relationship(back_populates="state")

    def to_srs(self) -> SrsState:
        """Bridge from the ORM row to the immutable value the pure functions operate on."""
        return SrsState(
            interval_days=self.interval_days, ease=self.ease,
            reps=self.reps, lapses=self.lapses, due=self.due,
        )

    def apply(self, s: SrsState) -> None:
        self.interval_days, self.ease = s.interval_days, s.ease
        self.reps, self.lapses, self.due = s.reps, s.lapses, s.due


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    grade: Mapped[str] = mapped_column(String(10))               # again/hard/good/easy
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    looked_at_solution: Mapped[bool] = mapped_column(Boolean, default=False)
    had_bugs: Mapped[bool] = mapped_column(Boolean, default=False)
    # Legacy: mistake tags are no longer collected. The column stays so existing databases
    # keep their shape (migrations here only ever add).
    mistakes: Mapped[list] = mapped_column(JSON, default=list)
    code: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")          # one line: why you got stuck
    mode: Mapped[str] = mapped_column(String(10), default="practice")  # practice | mock | drill
    # Self-reported complexity, required by the submit form. complexity_ok is None when we
    # have no reference answer for this problem, so "not graded" stays distinct from "wrong".
    time_complexity: Mapped[str] = mapped_column(String(40), default="")
    space_complexity: Mapped[str] = mapped_column(String(40), default="")
    complexity_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # The LLM's analysis of THIS code (see llm.analyze_complexity). When present it decides
    # complexity_ok, because it judges the solution actually written rather than comparing
    # against the textbook one.
    complexity_ai: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Template blind-writes only: fraction of checkpoints hit, 0..1
    blindwrite_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    problem: Mapped[Problem] = relationship(back_populates="attempts")


class FollowUp(Base):
    """Interviewer follow-up questions, generated once by the LLM and cached for mock mode."""
    __tablename__ = "followups"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    problem: Mapped[Problem] = relationship(back_populates="followups")


class InterviewQA(Base):
    """One code-specific interviewer question from a mock interview, with the candidate's
    answer and the LLM's grade. Unlike FollowUp these are not cached per problem: they are
    generated from the code the candidate wrote in that session."""
    __tablename__ = "interview_qas"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    code: Mapped[str] = mapped_column(Text, default="")          # snapshot the question refers to
    question: Mapped[str] = mapped_column(Text)
    key_points: Mapped[str] = mapped_column(Text, default="")    # withheld until answered
    answer: Mapped[str] = mapped_column(Text, default="")
    grade: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    problem: Mapped[Problem] = relationship(back_populates="interview_qas")
