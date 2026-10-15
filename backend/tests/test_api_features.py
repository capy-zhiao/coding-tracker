"""End-to-end tests for the template drill, complexity check and pattern view."""
import pytest

from app.deps import today as study_today
from app.models import Problem, ReviewState
from app.templates_ref import BY_NUMBER


@pytest.fixture
def sample_templates(db_session, user):
    rows = [
        Problem(number=9001, title="Union-Find", difficulty="Hard", chapter_num=11,
                chapter="Graphs", url="", kind="template", patterns=[]),
        Problem(number=9006, title="Binary search (closed interval)", difficulty="Medium",
                chapter_num=5, chapter="Binary Search", url="", kind="template", patterns=[]),
    ]
    db_session.add_all(rows)
    db_session.flush()
    for r in rows:
        db_session.add(ReviewState(user_id=user.id, problem_id=r.id, interval_days=0,
                                   due=study_today()))
    db_session.commit()
    return rows


# --- template drill ---

def test_list_templates(client, sample_templates):
    r = client.get("/templates")
    assert r.status_code == 200
    body = r.json()
    assert [t["number"] for t in body] == [9001, 9006]
    assert body[0]["check_count"] == len(BY_NUMBER[9001].checks)
    assert body[0]["state"]["due"] == study_today().isoformat()


def test_check_accepts_a_correct_blindwrite(client):
    r = client.post("/templates/9006/check", json={"code": BY_NUMBER[9006].reference})
    assert r.status_code == 200
    body = r.json()
    assert body["passed"] is True
    assert body["missing"] == []
    assert body["suggested_grade"] == "easy"


def test_check_rejects_a_broken_blindwrite_with_reasons(client):
    r = client.post("/templates/9006/check", json={"code": """
left, right = 0, len(nums) - 1
while left <= right:
    mid = (left + right) // 2
    if nums[mid] == target: return mid
    elif nums[mid] < target: left = mid
    else: right = mid
return -1
"""})
    body = r.json()
    assert body["passed"] is False
    assert body["suggested_grade"] == "again"
    failed = [c for c in body["checks"] if not c["passed"]]
    assert len(failed) == 2
    assert all(c["why"] for c in failed), "a failing check must explain itself"
    assert body["diff"]


def test_check_on_an_unknown_template_is_404(client):
    assert client.post("/templates/1234/check", json={"code": "x"}).status_code == 404


def test_reference_endpoint_exposes_the_answer(client):
    r = client.get("/templates/9001/reference")
    assert r.status_code == 200
    assert "while parent[x] != x" in r.json()["reference"]


def test_drill_attempt_flows_through_the_normal_srs(client, sample_templates):
    """Templates are Problems, so they reuse the whole review pipeline."""
    r = client.post("/review/9001/attempt", json={
        "grade": "good", "seconds": 180, "mode": "drill", "blindwrite_score": 1.0,
        "code": BY_NUMBER[9001].reference,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next_due_in_days"] > 0
    assert body["attempt"]["mode"] == "drill"
    assert body["state"]["reps"] == 1


# --- complexity self-check ---

def test_complexity_choices_are_served(client):
    r = client.get("/review/complexity-choices")
    assert r.status_code == 200
    assert "O(n log n)" in r.json()


def test_correct_complexity_is_graded_ok(client, sample_problems):
    r = client.post("/review/200/attempt", json={
        "grade": "good", "seconds": 600,
        "time_complexity": "O(m*n)", "space_complexity": "O(m * n)",
    })
    c = r.json()["complexity"]
    assert c["graded"] and c["time_ok"] and c["space_ok"]
    assert r.json()["attempt"]["complexity_ok"] is True


def test_wrong_complexity_is_recorded_with_the_reference(client, sample_problems):
    r = client.post("/review/200/attempt", json={
        "grade": "good", "seconds": 600,
        "time_complexity": "O(n)", "space_complexity": "O(1)",
    })
    c = r.json()["complexity"]
    assert c["graded"] and not c["time_ok"]
    assert c["expected_time"] == "O(m * n)"
    assert r.json()["attempt"]["complexity_ok"] is False


def test_ungraded_problem_records_but_does_not_judge(client, db_session):
    """No reference answer must read as "not graded", never as "wrong"."""
    p = Problem(number=999999, title="Made Up", difficulty="Medium", chapter_num=1,
                chapter="Arrays & Hashing", url="", kind="problem", patterns=["hashmap"])
    db_session.add(p)
    db_session.commit()

    r = client.post("/review/999999/attempt", json={
        "grade": "good", "seconds": 60,
        "time_complexity": "O(n)", "space_complexity": "O(n)",
    })
    assert r.json()["complexity"]["graded"] is False
    assert r.json()["attempt"]["complexity_ok"] is None
    assert r.json()["attempt"]["time_complexity"] == "O(n)"


def test_complexity_accuracy_stats(client, sample_problems):
    client.post("/review/200/attempt", json={
        "grade": "good", "time_complexity": "O(m*n)", "space_complexity": "O(m*n)"})
    client.post("/review/1/attempt", json={
        "grade": "good", "time_complexity": "O(n^2)", "space_complexity": "O(n)"})

    s = client.get("/stats/complexity").json()
    assert s["answered"] == 2
    assert s["graded"] == 2
    assert s["both_correct"] == 1
    assert s["accuracy"] == 0.5
    assert s["worst"][0]["number"] == 1        # Two Sum answered wrong


# --- pattern view ---

def test_pattern_stats_group_across_chapters(client, sample_problems):
    r = client.get("/stats/patterns")
    assert r.status_code == 200
    by_id = {p["id"]: p for p in r.json()}

    # 994 and 200 are both chapter 11, but different techniques
    assert by_id["multi-source-bfs"]["total"] == 1
    assert by_id["grid-dfs"]["total"] == 1
    assert by_id["hashmap"]["total"] == 1       # Two Sum

    assert by_id["grid-dfs"]["template_number"] == 9002


def test_pattern_stats_sorted_weakest_first(client, sample_problems):
    rows = client.get("/stats/patterns").json()
    weaknesses = [r["weakness"] for r in rows]
    assert weaknesses == sorted(weaknesses, reverse=True)


def test_failed_attempts_raise_a_patterns_weakness(client, sample_problems):
    before = {p["id"]: p for p in client.get("/stats/patterns").json()}
    client.post("/review/200/attempt", json={"grade": "again", "looked_at_solution": True})
    after = {p["id"]: p for p in client.get("/stats/patterns").json()}

    assert after["grid-dfs"]["again_rate"] == 1.0
    assert after["grid-dfs"]["weakness"] > before["grid-dfs"]["weakness"]


def test_problem_payload_carries_its_patterns(client, db_session):
    p = Problem(number=239, title="Sliding Window Maximum", difficulty="Hard",
                chapter_num=3, chapter="Sliding Window", url="", kind="problem",
                patterns=["monotonic-stack", "sliding-window"])
    db_session.add(p)
    db_session.commit()
    body = client.get("/problems/239").json()
    assert body["patterns"] == ["monotonic-stack", "sliding-window"]
