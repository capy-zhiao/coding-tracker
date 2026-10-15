"""Test fixtures: each test gets its own empty database.

In-memory SQLite by default. CI also runs the suite on Postgres by setting
TEST_DATABASE_URL to a throwaway database, which is emptied before and after each test.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.deps import today as study_today
from app.main import app
from app.models import Problem, ReviewState


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Settings are read from backend/.env, so once a real key lives there every test run
    would call the paid API. Force AI off; tests that need it install a stub provider."""
    from app import llm
    from app.config import settings
    monkeypatch.setattr(settings, "llm_provider", "none")
    monkeypatch.setattr(llm, "_cached", None)


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def db_session():
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(bind=engine)      # in case an earlier run died midway
    else:
        engine = create_engine(
            "sqlite://",                       # in-memory
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,              # share one database across connections
        )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        if TEST_DATABASE_URL:
            Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user(db_session):
    """The local user, whom every request belongs to in local mode."""
    from app.deps import local_user
    return local_user(db_session)


@pytest.fixture
def sample_problems(db_session, user):
    """Three problems: one never attempted, two solved and due for review."""
    from datetime import timedelta
    # The app's own notion of today, never date.today(): the two differ for part of every
    # evening east of UTC, which used to make these tests fail after 20:00 EDT.
    today = study_today()
    rows = [
        Problem(number=1, title="Two Sum", difficulty="Easy", chapter_num=1,
                chapter="Arrays & Hashing", url="", kind="problem"),
        Problem(number=994, title="Rotting Oranges", difficulty="Medium", chapter_num=11,
                chapter="Graphs", url="", kind="problem"),
        Problem(number=200, title="Number of Islands", difficulty="Medium", chapter_num=11,
                chapter="Graphs", url="", kind="problem"),
    ]
    db_session.add_all(rows)
    db_session.flush()
    # 994 is five days overdue and has failed three times -> highest priority
    db_session.add(ReviewState(user_id=user.id, problem_id=rows[1].id, interval_days=2, reps=1,
                               lapses=3, due=today - timedelta(days=5)))
    db_session.add(ReviewState(user_id=user.id, problem_id=rows[2].id, interval_days=4, reps=2,
                               lapses=0, due=today))
    db_session.commit()
    return rows
