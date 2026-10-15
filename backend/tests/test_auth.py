"""Who the request belongs to. Local mode: no login, one automatically created user."""
from app.config import settings
from app.deps import today
from app.models import User


def test_local_mode_creates_one_user_on_first_request(client, db_session):
    first = client.get("/auth/me").json()
    second = client.get("/auth/me").json()
    assert first["id"] == second["id"]
    assert first["auth_mode"] == "local"
    assert first["provider"] == "local" and first["is_owner"]
    assert db_session.query(User).count() == 1


def test_local_mode_needs_no_credentials(client):
    for path in ("/review/today", "/stats", "/problems", "/templates"):
        assert client.get(path).status_code == 200, path


def test_the_users_own_timezone_and_caps_win_over_env(client, db_session):
    client.get("/auth/me")
    user = db_session.query(User).one()
    user.timezone = "Pacific/Kiritimati"      # UTC+14: a different date from most places
    user.daily_review_cap = 2
    db_session.commit()

    me = client.get("/auth/me").json()
    assert me["today"] == today("Pacific/Kiritimati").isoformat()
    q = client.get("/review/today").json()
    assert q["date"] == me["today"] and q["review_cap"] == 2
    # A value in the request still wins
    assert client.get("/review/today", params={"review_cap": 5}).json()["review_cap"] == 5


def test_other_modes_need_a_login(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "github")
    assert client.get("/review/today").status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/health").status_code == 200
