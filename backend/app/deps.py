"""Shared dependencies and small helpers."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Problem, ReviewState, User


def get_current_user(db: Session = Depends(get_db)) -> User:
    """Who is making this request. Every router depends on it.

    Local mode has no login: the one local user is created on the first request and every
    request is theirs.
    """
    if settings.auth_mode == "local":
        return _local_user(db)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")


def _local_user(db: Session) -> User:
    query = select(User).where(User.provider == "local", User.provider_id == "local")
    user = db.scalar(query)
    if user is not None:
        return user
    user = User(provider="local", provider_id="local", login="local",
                display_name="Local user", is_owner=True, ai_enabled=True)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:            # two first requests raced; the other one created it
        db.rollback()
        return db.scalar(query)
    return user


def require_owner(user: User = Depends(get_current_user)) -> User:
    if not user.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can do this")
    return user


def get_problem(number: int, db: Session = Depends(get_db)) -> Problem:
    p = db.scalar(select(Problem).where(Problem.number == number))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No problem numbered {number}")
    return p


def ensure_state(db: Session, problem: Problem) -> ReviewState:
    """Lazily create the SRS row the first time a problem is attempted."""
    if problem.state is None:
        st = ReviewState(problem_id=problem.id)
        db.add(st)
        db.flush()
        problem.state = st
    return problem.state


def _zone(tz: str | None = None) -> ZoneInfo | None:
    """The study-day zone: the given one (a user's), else TIMEZONE, else None meaning the
    machine's local zone."""
    name = tz or settings.timezone
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:                      # unknown zone name: fall back rather than crash
        return None


def today(tz: str | None = None) -> date:
    """The current study day.

    Deliberately NOT the UTC date. Timestamps are stored in UTC, but a day boundary at
    00:00 UTC is 20:00 the previous evening in EDT, so an evening session would land on
    the next day: tomorrow's queue would appear at 8pm and the streak would break.
    """
    return datetime.now(_zone(tz)).date()


def local_date(dt: datetime, tz: str | None = None) -> date:
    """Which study day a stored timestamp belongs to.

    created_at is written as UTC but stored naive (the column has no timezone), so it has
    to be re-stamped as UTC before converting — otherwise astimezone() would read it as
    local time and shift it a second time.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_zone(tz)).date()


def user_today(user: User) -> date:
    return today(user.timezone)


def effective_caps(
    user: User, review_cap: int | None = None, new_cap: int | None = None,
) -> tuple[int, int]:
    """Daily limits: an explicit request value, else the user's own, else .env."""
    def pick(explicit, own, default):
        if explicit is not None:
            return explicit
        return own if own is not None else default
    return (pick(review_cap, user.daily_review_cap, settings.daily_review_cap),
            pick(new_cap, user.daily_new_cap, settings.daily_new_cap))
