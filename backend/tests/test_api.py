"""End-to-end API tests."""
from datetime import timedelta

from app.deps import today as study_today


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_today_queue_orders_by_priority(client, sample_problems):
    """Long overdue plus repeated failures should outrank a problem merely due today."""
    r = client.get("/review/today")
    assert r.status_code == 200
    q = r.json()

    numbers = [i["problem"]["number"] for i in q["reviews"]]
    assert numbers[0] == 994, f"994 should lead the queue, got {numbers}"
    assert q["total_due"] == 2
    assert q["reviews"][0]["overdue_days"] == 5

    # Never-attempted problems land in the "new" bucket
    assert [i["problem"]["number"] for i in q["new_problems"]] == [1]


def test_daily_cap_defers_overflow(client, sample_problems):
    r = client.get("/review/today", params={"review_cap": 1})
    q = r.json()
    assert len(q["reviews"]) == 1
    assert q["total_due"] == 2
    assert q["deferred"] == 1, "overflow is deferred, not dropped"


def test_submit_attempt_updates_srs(client, sample_problems):
    r = client.post("/review/1/attempt", json={
        "grade": "good", "seconds": 600,
        "code": "class Solution: pass", "note": "hash map of complements",
    })
    assert r.status_code == 200, r.text
    body = r.json()

    # First "good" is 4 days; Two Sum is Easy so x1.15 -> 5 days
    assert body["next_due_in_days"] == 5
    assert body["state"]["reps"] == 1
    assert body["state"]["total_attempts"] == 1
    assert body["state"]["best_seconds"] == 600
    assert body["state"]["due"] == (study_today() + timedelta(days=5)).isoformat()

    # It should drop out of today's review queue
    nums = [i["problem"]["number"] for i in client.get("/review/today").json()["reviews"]]
    assert 1 not in nums


def test_again_grade_resets_and_counts_lapse(client, sample_problems):
    r = client.post("/review/200/attempt", json={
        "grade": "again", "seconds": 1800, "looked_at_solution": True,
    })
    body = r.json()
    assert body["next_due_in_days"] == 1
    assert body["state"]["lapses"] == 1
    assert body["state"]["reps"] == 0


def test_grade_suggestion_from_timer(client):
    r = client.get("/review/suggest-grade",
                   params={"seconds": 200, "difficulty": "Medium"})
    assert r.json()["grade"] == "easy"

    r = client.get("/review/suggest-grade",
                   params={"seconds": 1500, "difficulty": "Medium"})
    assert r.json()["grade"] == "hard"


def test_overview_stats(client, sample_problems):
    client.post("/review/1/attempt", json={"grade": "good", "seconds": 300})
    s = client.get("/stats").json()
    assert s["total_problems"] == 3
    assert s["attempts_total"] == 1
    assert s["streak_days"] == 1
    assert s["avg_seconds"] == 300
    assert any(c["chapter_num"] == 11 for c in s["by_chapter"])


def test_attempt_history_for_diff(client, sample_problems):
    client.post("/review/1/attempt", json={"grade": "again", "code": "v1"})
    client.post("/review/1/attempt", json={"grade": "good", "code": "v2"})
    hist = client.get("/review/1/attempts").json()
    assert len(hist) == 2
    assert hist[0]["code"] == "v2"               # newest first, ready to diff


def test_problem_filters(client, sample_problems):
    assert len(client.get("/problems", params={"chapter": 11}).json()) == 2
    assert len(client.get("/problems", params={"difficulty": "Easy"}).json()) == 1
    assert len(client.get("/problems", params={"status": "new"}).json()) == 1
    assert client.get("/problems", params={"q": "island"}).json()[0]["number"] == 200


def test_followups_fall_back_without_a_provider(client, sample_problems):
    """With LLM_PROVIDER unset the endpoint must still return generic follow-ups."""
    r = client.get("/mock/1/followups")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 3
    assert all(i["question"] for i in items)


def test_mock_start(client, sample_problems):
    r = client.post("/mock/start", params={"difficulty": "Medium"})
    assert r.status_code == 200
    body = r.json()
    assert body["problem"]["difficulty"] == "Medium"
    assert body["minutes"] == 35


def test_forecast_counts_problems_but_not_template_drills(client, sample_problems, db_session,
                                                           user):
    """Drills have their own slot; counting them would overstate the review load."""
    from app.models import Problem, ReviewState
    from app.deps import today as study_today
    t = Problem(number=9001, title="Union-Find", difficulty="Hard", chapter_num=11,
                chapter="Graphs", url="", kind="template")
    db_session.add(t)
    db_session.flush()
    db_session.add(ReviewState(user_id=user.id, problem_id=t.id, interval_days=0,
                               due=study_today() - timedelta(days=3)))
    db_session.commit()

    today_row = client.get("/review/forecast").json()[0]
    assert today_row["overdue"] == 1        # 994 only; 200 is due today, not overdue
    assert today_row["count"] == 2          # 994 overdue + 200 due today; drill excluded


def test_queue_reports_the_review_cap(client, sample_problems):
    assert client.get("/review/today", params={"review_cap": 3}).json()["review_cap"] == 3


def test_problem_list_follows_neetcode_order_within_a_chapter(client, db_session):
    from app.models import Problem
    for n in (5, 70, 746, 198, 1137):     # 1137 is a 250 addition
        db_session.add(Problem(number=n, title=f"P{n}", difficulty="Medium", chapter_num=13,
                               chapter="1-D DP", url="", kind="problem"))
    db_session.commit()
    got = [p["number"] for p in client.get("/problems", params={"chapter": 13}).json()]
    assert got == [70, 746, 198, 5, 1137]
