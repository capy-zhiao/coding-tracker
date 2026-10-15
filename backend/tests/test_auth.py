"""Who a request belongs to. Local mode: no login, one automatically created user.
github mode: GitHub OAuth and a signed session cookie (GitHub's two calls are stubbed)."""
import pytest

from app.auth import github
from app.auth.session import SESSION_COOKIE, STATE_COOKIE
from app.config import settings
from app.deps import today
from app.main import check_auth_settings
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


# --- github mode ---------------------------------------------------------------------

PROFILE = {"id": 4242, "login": "capy-zhiao", "name": "Zhiao", "avatar_url": "https://a/x.png"}


@pytest.fixture
def github_mode(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "github")
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    monkeypatch.setattr(settings, "session_secret", "s" * 40)
    monkeypatch.setattr(settings, "github_client_id", "client-id")
    monkeypatch.setattr(settings, "github_client_secret", "client-secret")
    monkeypatch.setattr(settings, "owner_github_login", "")
    monkeypatch.setattr(github, "exchange_code", lambda code: f"token-for-{code}")
    monkeypatch.setattr(github, "fetch_user", lambda token: dict(PROFILE))


def sign_in(client, profile=None, monkeypatch=None):
    """Walk the real flow: /login sets the state cookie, GitHub sends the browser back to
    /callback with that state and a code."""
    if profile is not None:
        monkeypatch.setattr(github, "fetch_user", lambda token: dict(profile))
    client.get("/auth/login/github", follow_redirects=False)
    state = client.cookies.get(STATE_COOKIE)
    return client.get("/auth/callback/github", params={"code": "c0de", "state": state},
                      follow_redirects=False)


def test_github_mode_needs_a_session_for_everything_but_health(github_mode, client):
    assert client.get("/review/today").status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/health").json()["auth_mode"] == "github"


def test_login_redirects_to_github_with_a_state(github_mode, client):
    r = client.get("/auth/login/github", follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=client-id" in location
    assert "redirect_uri=http%3A%2F%2Ftestserver%2Fapi%2Fauth%2Fcallback%2Fgithub" in location
    state = client.cookies.get(STATE_COOKIE)
    assert state and f"state={state}" in location


def test_signing_in_creates_the_user_and_a_session(github_mode, client, db_session):
    r = sign_in(client)
    assert r.status_code == 302 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"]
    assert SESSION_COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    me = client.get("/auth/me").json()
    assert (me["login"], me["display_name"], me["provider"]) == ("capy-zhiao", "Zhiao", "github")
    assert not me["is_owner"]
    assert client.get("/review/today").status_code == 200


def test_signing_in_again_reuses_the_account_even_after_a_rename(github_mode, client,
                                                                 db_session, monkeypatch):
    sign_in(client)
    sign_in(client, {**PROFILE, "login": "renamed"}, monkeypatch)
    users = db_session.query(User).filter_by(provider="github").all()
    assert len(users) == 1 and users[0].login == "renamed"


def test_the_owner_is_recognised_by_login(github_mode, client, monkeypatch):
    monkeypatch.setattr(settings, "owner_github_login", "Capy-Zhiao")
    sign_in(client)
    me = client.get("/auth/me").json()
    assert me["is_owner"] and me["ai_enabled"]


def test_a_callback_with_the_wrong_state_is_refused(github_mode, client):
    client.get("/auth/login/github", follow_redirects=False)
    r = client.get("/auth/callback/github", params={"code": "c0de", "state": "forged"},
                   follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/?signin=failed"
    assert client.get("/auth/me").status_code == 401


def test_a_github_failure_goes_back_to_sign_in_with_a_message(github_mode, client, monkeypatch):
    def broken(code):
        raise github.GitHubError("token exchange failed (401)")
    monkeypatch.setattr(github, "exchange_code", broken)
    r = sign_in(client)
    assert r.headers["location"] == "/?signin=failed"
    assert client.get("/auth/me").status_code == 401


def test_cancelling_on_github_just_goes_home(github_mode, client):
    r = client.get("/auth/callback/github", params={"error": "access_denied"},
                   follow_redirects=False)
    assert r.status_code == 302 and client.get("/auth/me").status_code == 401


def test_a_tampered_session_cookie_is_ignored(github_mode, client):
    sign_in(client)
    value = client.cookies.get(SESSION_COOKIE)
    client.cookies.set(SESSION_COOKIE, value[:-2] + ("A" if value[-2] != "A" else "B") + value[-1])
    assert client.get("/auth/me").status_code == 401


def test_logging_out_ends_the_session(github_mode, client):
    sign_in(client)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_cross_site_writes_are_refused(github_mode, client):
    sign_in(client)
    attempt = {"grade": "good", "seconds": 60}
    evil = client.post("/review/1/attempt", json=attempt, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    # Same origin passes the guard (and then 404s: there is no problem 1 in this database)
    same = client.post("/review/1/attempt", json=attempt, headers={"Origin": "http://testserver"})
    assert same.status_code == 404


def test_cookies_are_secure_on_https(github_mode, client, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://leetcode.example.dev")
    r = client.get("/auth/login/github", follow_redirects=False)
    assert "secure" in r.headers["set-cookie"].lower()


def test_github_mode_refuses_to_start_with_a_weak_secret(github_mode, monkeypatch):
    check_auth_settings()                                # the fixture's settings are fine
    monkeypatch.setattr(settings, "session_secret", "short")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        check_auth_settings()
    monkeypatch.setattr(settings, "auth_mode", "magic")
    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        check_auth_settings()
