"""Bring your own key: anyone but the owner uses AI on their own API key, which arrives
with each request and must never be stored, cached or logged; the server's key is the
owner's alone. Provider construction is stubbed, so no test calls a real API."""
import logging
import socket

import pytest
from sqlalchemy import inspect, text

from app import deps, llm
from app.deps import get_current_user, local_user
from app.main import app
from app.models import Problem, User

KEY = "sk-user-secret-0123456789"
OWN_KEY = {"X-LLM-Provider": "openai", "X-LLM-Key": KEY, "X-LLM-Model": "deepseek-chat",
           "X-LLM-Base-URL": "https://api.deepseek.com"}
VERDICT = llm.ComplexityVerdict(
    actual_time="O(n)", actual_space="O(1)", time_correct=True, space_correct=True,
    why_wrong="", optimal_time="O(n)", optimal_space="O(1)",
    time_optimal=True, space_optimal=True, optimal_how="", optimized_code="",
)


class StubProvider(llm._Provider):
    name = "stub"

    def __init__(self, cfg):
        self.cfg = cfg

    def model_for(self, task="default"):
        return self.cfg.model

    def complete(self, prompt, schema, task="default"):
        return VERDICT if schema is llm.ComplexityVerdict else None


@pytest.fixture
def built(monkeypatch):
    """Record every provider built from a request, and resolve DNS to a public address."""
    configs = []

    def build(cfg):
        configs.append(cfg)
        return StubProvider(cfg)

    monkeypatch.setattr(llm, "build_provider", build)
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda host, *a, **k: [(None, None, None, "", ("104.18.6.92", 443))])
    deps._ai_calls.clear()
    return configs


@pytest.fixture
def stranger(client, db_session):
    """A signed-in GitHub user who isn't the owner."""
    user = User(provider="github", provider_id="9", login="stranger")
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def attempt_id(client, db_session):
    db_session.add(Problem(number=1, title="Two Sum", difficulty="Easy", chapter_num=1,
                           chapter="Arrays & Hashing", url="", kind="problem"))
    db_session.commit()
    body = {"grade": "good", "seconds": 60, "code": "def two_sum(): return []",
            "time_complexity": "O(n)", "space_complexity": "O(1)"}
    return client.post("/review/1/attempt", json=body).json()["attempt"]["id"]


def test_without_a_key_a_stranger_is_asked_for_one(attempt_id, stranger, client):
    client.post("/review/1/attempt", json={"grade": "good", "code": "x = 1"})
    own = client.get("/review/1/attempts").json()[0]["id"]
    r = client.post(f"/review/attempts/{own}/complexity-ai")
    assert r.status_code == 403 and "API key" in r.json()["detail"]


def test_the_owner_without_a_server_key_is_told_to_configure_one(attempt_id, client):
    r = client.post(f"/review/attempts/{attempt_id}/complexity-ai")
    assert r.status_code == 503 and "LLM_PROVIDER" in r.json()["detail"]


def test_a_request_with_a_key_runs_on_that_key(attempt_id, built, client):
    r = client.post(f"/review/attempts/{attempt_id}/complexity-ai", headers=OWN_KEY)
    assert r.status_code == 200
    assert r.json()["complexity_ai"]["model"] == "deepseek-chat"
    (cfg,) = built
    assert (cfg.api_key, cfg.model, cfg.base_url) == (KEY, "deepseek-chat", "https://api.deepseek.com")
    assert cfg.thinking is None        # no DeepSeek-only parameters for someone else's endpoint
    assert llm._cached is None         # a user's provider is never kept around


def test_the_key_is_never_stored_or_logged(attempt_id, built, client, db_session, caplog):
    caplog.set_level(logging.DEBUG)
    client.post(f"/review/attempts/{attempt_id}/complexity-ai", headers=OWN_KEY)

    assert KEY not in caplog.text
    assert KEY not in repr(built[0])
    conn = db_session.connection()
    for table in inspect(conn).get_table_names():
        for row in conn.execute(text(f"SELECT * FROM {table}")):
            assert KEY not in " ".join(str(v) for v in row), f"key found in {table}"


@pytest.mark.parametrize("url, message", [
    ("http://api.deepseek.com", "https://"),
    ("https://internal.example", "public address"),
])
def test_base_urls_that_could_reach_private_hosts_are_refused(attempt_id, built, client,
                                                              monkeypatch, url, message):
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda host, *a, **k: [(None, None, None, "", ("10.0.0.5", 443))])
    r = client.post(f"/review/attempts/{attempt_id}/complexity-ai",
                    headers={**OWN_KEY, "X-LLM-Base-URL": url})
    assert r.status_code == 400 and message in r.json()["detail"]
    assert built == []


def test_the_metadata_address_is_refused():
    with pytest.raises(llm.BadKeyConfig):
        llm.check_base_url("https://169.254.169.254/latest")


def test_a_model_is_required(attempt_id, built, client):
    r = client.post(f"/review/attempts/{attempt_id}/complexity-ai",
                    headers={**OWN_KEY, "X-LLM-Model": ""})
    assert r.status_code == 400 and "model" in r.json()["detail"]


def test_ai_requests_on_a_users_key_are_rate_limited(attempt_id, built, client, monkeypatch):
    monkeypatch.setattr(deps, "AI_MAX_PER_WINDOW", 2)
    codes = [client.post(f"/review/attempts/{attempt_id}/complexity-ai", headers=OWN_KEY).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]


def test_only_the_owner_sees_the_server_credit(stranger, client):
    assert client.get("/stats/credit").status_code == 403


def test_without_ai_followups_are_generic_and_not_cached(stranger, client, db_session):
    db_session.add(Problem(number=7, title="Reverse Integer", difficulty="Medium",
                           chapter_num=18, chapter="Math & Geometry", url="", kind="problem"))
    db_session.commit()
    first = client.get("/mock/7/followups").json()
    assert len(first) == 3 and all(f["id"] == 0 for f in first)
    assert db_session.execute(text("SELECT count(*) FROM followups")).scalar() == 0
    assert client.get("/mock/7/followups", params={"regenerate": True}).status_code == 403


def test_the_local_user_is_the_owner_and_uses_the_server_key(db_session):
    assert local_user(db_session).is_owner
