"""Per-user data isolation: what one user does never shows up for another, through any
route, and nobody can act on another user's rows by guessing an id.

Two users share one database; `as_user` switches who the requests belong to by
overriding get_current_user, the single place a request's owner is decided.
"""
import pytest

from app.deps import get_current_user, local_user
from app.main import app
from app.models import InterviewQA, Problem, ReviewState, User

# Bob brings his own key (Anthropic: no base URL to look up), so his AI requests get past
# the AI check and reach the ownership check.
BOB_KEY = {"X-LLM-Provider": "anthropic", "X-LLM-Key": "sk-bob", "X-LLM-Model": "claude-test"}
ATTEMPT = {"grade": "good", "seconds": 600, "code": "def solve(): return 1",
           "time_complexity": "O(n)", "space_complexity": "O(1)"}


@pytest.fixture
def alice(db_session):
    return local_user(db_session)


@pytest.fixture
def bob(db_session):
    u = User(provider="github", provider_id="2", login="bob")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def as_user(client):
    def switch(user):
        app.dependency_overrides[get_current_user] = lambda: user
    yield switch
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def problems(db_session):
    db_session.add_all([
        Problem(number=1, title="Two Sum", difficulty="Easy", chapter_num=1,
                chapter="Arrays & Hashing", url="", kind="problem"),
        Problem(number=9001, title="Union-Find", difficulty="Hard", chapter_num=11,
                chapter="Graphs", url="", kind="template"),
    ])
    db_session.commit()


def test_an_attempt_shows_up_only_for_its_owner(client, as_user, alice, bob):
    as_user(alice)
    assert client.post("/review/1/attempt", json=ATTEMPT).status_code == 200
    assert len(client.get("/review/1/attempts").json()) == 1
    assert client.get("/stats").json()["attempts_total"] == 1
    assert [p["number"] for p in client.get("/problems", params={"status": "learning"}).json()] == [1]

    as_user(bob)
    assert client.get("/review/1/attempts").json() == []
    stats = client.get("/stats").json()
    assert stats["attempts_total"] == 0 and stats["started"] == 0 and stats["streak_days"] == 0
    assert client.get("/stats/heatmap").json() == []
    assert client.get("/stats/complexity").json()["answered"] == 0
    assert all(p["attempts"] == 0 for p in client.get("/stats/patterns").json())
    assert client.get("/problems/1").json()["state"] is None
    assert client.get("/problems", params={"status": "learning"}).json() == []
    assert [p["number"] for p in client.get("/problems", params={"status": "new"}).json()] == [1]
    assert all(day["count"] == 0 for day in client.get("/review/forecast").json())
    today = client.get("/review/today").json()
    assert today["reviews"] == [] and today["total_due"] == 0
    assert [i["problem"]["number"] for i in today["new_problems"]] == [1]


def test_each_user_has_their_own_review_state(client, as_user, alice, bob, db_session):
    as_user(alice)
    client.post("/review/1/attempt", json={**ATTEMPT, "grade": "easy"})
    as_user(bob)
    client.post("/review/1/attempt", json={**ATTEMPT, "grade": "again"})

    rows = {st.user_id: st for st in db_session.query(ReviewState).all()}
    assert set(rows) == {alice.id, bob.id}
    assert rows[alice.id].due > rows[bob.id].due          # easy pushes it further out
    assert client.get("/problems/1").json()["state"]["due"] == rows[bob.id].due.isoformat()


def test_template_drills_are_per_user(client, as_user, alice, bob):
    as_user(alice)
    client.post("/review/9001/attempt", json={**ATTEMPT, "mode": "drill"})
    assert client.get("/templates").json()[0]["state"] is not None
    as_user(bob)
    assert client.get("/templates").json()[0]["state"] is None


def test_someone_elses_attempt_answers_404(client, as_user, alice, bob):
    as_user(alice)
    attempt_id = client.post("/review/1/attempt", json=ATTEMPT).json()["attempt"]["id"]
    as_user(bob)
    r = client.post(f"/review/attempts/{attempt_id}/complexity-ai", headers=BOB_KEY)
    assert r.status_code == 404
    # Same answer as an id that doesn't exist, so ids can't be probed
    missing = client.post("/review/attempts/99999/complexity-ai", headers=BOB_KEY)
    assert missing.json()["detail"].startswith("No attempt")


def test_someone_elses_interview_question_answers_404(client, as_user, alice, bob, db_session):
    problem = db_session.query(Problem).filter_by(number=1).one()
    qa = InterviewQA(user_id=alice.id, problem_id=problem.id, code="x", question="Why?")
    db_session.add(qa)
    db_session.commit()
    as_user(bob)
    r = client.post(f"/mock/qa/{qa.id}/answer", json={"answer": "Because."}, headers=BOB_KEY)
    assert r.status_code == 404


def test_only_solved_mock_draws_from_your_own_history(client, as_user, alice, bob):
    as_user(alice)
    client.post("/review/1/attempt", json=ATTEMPT)
    assert client.post("/mock/start", params={"only_solved": True}).status_code == 200
    as_user(bob)
    assert client.post("/mock/start", params={"only_solved": True}).status_code == 404


def test_notes_and_saved_code_are_per_user(client, as_user, alice, bob):
    as_user(alice)
    client.patch("/problems/1", json={"notes": "hash map of complements"})
    client.post("/review/1/attempt", json={**ATTEMPT, "code": "alice's solution"})
    detail = client.get("/problems/1").json()
    assert (detail["notes"], detail["code"]) == ("hash map of complements", "alice's solution")

    as_user(bob)
    detail = client.get("/problems/1").json()
    assert (detail["notes"], detail["code"]) == ("", "")
    client.patch("/problems/1", json={"notes": "bob's take"})

    as_user(alice)
    assert client.get("/problems/1").json()["notes"] == "hash map of complements"
