"""The shared demo account, and moving a user's history between accounts."""
from datetime import timedelta

import pytest

from app import demo, tools
from app.auth.session import SESSION_COOKIE
from app.config import settings
from app.deps import get_current_user, local_user, today
from app.main import app
from app.models import Attempt, Problem, ReviewState, User
from app.neetcode150 import NEETCODE_150


@pytest.fixture
def catalogue(db_session):
    """A slice of the NeetCode 150 plus two templates: enough for a realistic history."""
    numbers = sorted(NEETCODE_150)[:40]
    db_session.add_all([
        Problem(number=n, title=f"P{n}", difficulty=("Easy", "Medium", "Hard")[n % 3],
                chapter_num=1 + n % 5, chapter="Ch", url="", kind="problem",
                in_neetcode150=True)
        for n in numbers
    ] + [
        Problem(number=n, title=f"T{n}", difficulty="Medium", chapter_num=11,
                chapter="Graphs", url="", kind="template")
        for n in (9001, 9002)
    ])
    db_session.commit()


def counts(db, user):
    return (db.query(Attempt).filter_by(user_id=user.id).count(),
            db.query(ReviewState).filter_by(user_id=user.id).count())


def test_reset_builds_a_history_up_to_yesterday(db_session, catalogue):
    d = today()
    user = demo.reset_demo(db_session, d)
    attempts = db_session.query(Attempt).filter_by(user_id=user.id).all()
    assert user.is_demo and len(attempts) > 40
    assert all(a.created_at.date() < d + timedelta(days=1) for a in attempts)
    assert any(a.mode == "drill" for a in attempts)
    # Something is due today, so the demo opens on a working queue
    assert any(st.due and st.due <= d for st in db_session.query(ReviewState).filter_by(user_id=user.id))


def test_reset_is_repeatable_and_leaves_other_users_alone(db_session, catalogue):
    owner = local_user(db_session)
    db_session.add(Attempt(user_id=owner.id, problem_id=db_session.query(Problem).first().id,
                           grade="good"))
    db_session.commit()

    first = counts(db_session, demo.reset_demo(db_session, today()))
    user = demo.reset_demo(db_session, today())
    assert counts(db_session, user) == first
    assert db_session.query(Attempt).filter_by(user_id=owner.id).count() == 1


def test_a_day_old_demo_needs_a_reset(db_session, catalogue):
    user = demo.reset_demo(db_session, today())
    assert not demo.needs_reset(user, user.demo_reset_at + timedelta(hours=23))
    assert demo.needs_reset(user, user.demo_reset_at + timedelta(hours=24))
    assert demo.needs_reset(None, user.demo_reset_at)


@pytest.fixture
def github_demo(monkeypatch):
    for name, value in {"auth_mode": "github", "public_base_url": "http://testserver",
                        "session_secret": "s" * 40, "github_client_id": "id",
                        "github_client_secret": "secret", "demo_enabled": True}.items():
        monkeypatch.setattr(settings, name, value)


def test_try_the_demo_signs_you_in(github_demo, client, catalogue):
    r = client.post("/auth/demo")
    assert r.status_code == 200 and r.json()["is_demo"]
    assert SESSION_COOKIE in r.headers["set-cookie"]
    me = client.get("/auth/me").json()
    assert me["login"] == "demo" and not me["is_owner"] and not me["ai_enabled"]
    assert client.get("/stats").json()["attempts_total"] > 0


def test_the_demo_is_off_unless_enabled(github_demo, client, monkeypatch):
    monkeypatch.setattr(settings, "demo_enabled", False)
    assert client.post("/auth/demo").status_code == 404


def test_the_demo_is_off_in_local_mode(client):
    assert client.post("/auth/demo").status_code == 404


def test_export_and_import_move_a_history_to_another_account(db_session, catalogue, client):
    source = demo.reset_demo(db_session, today())
    source.timezone = "Asia/Tokyo"
    target = User(provider="github", provider_id="5", login="capy-zhiao")
    db_session.add(target)
    db_session.commit()

    data = tools.export_user(db_session, source)
    result = tools.import_user(db_session, target, data)

    assert result["skipped"] == 0
    assert counts(db_session, target) == counts(db_session, source)
    assert target.timezone == "Asia/Tokyo"
    stats = {}
    for user in (source, target):
        app.dependency_overrides[get_current_user] = lambda user=user: user
        stats[user.login] = client.get("/stats").json()
    app.dependency_overrides.pop(get_current_user, None)
    assert stats["demo"] == stats["capy-zhiao"]


def test_import_replaces_the_targets_history_and_skips_unknown_problems(db_session, catalogue):
    target = local_user(db_session)
    demo_user = demo.reset_demo(db_session, today())
    data = tools.export_user(db_session, demo_user)
    data["attempts"].append({**data["attempts"][0], "number": 99999})

    tools.import_user(db_session, target, data)
    again = tools.import_user(db_session, target, data)       # replaces, doesn't append

    assert again["skipped"] == 1
    assert counts(db_session, target) == counts(db_session, demo_user)
