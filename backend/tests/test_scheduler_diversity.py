"""Interleaving in the daily review queue.

Pure-function tests use lightweight stand-ins for Problem, since pick_diverse only reads
chapter_num, number and patterns.
"""
from datetime import timedelta
from types import SimpleNamespace

from app.deps import today as study_today
from app.models import Problem, ReviewState
from app.scheduler import QueueItem, pick_diverse


def item(number, chapter, pattern, score):
    p = SimpleNamespace(number=number, chapter_num=chapter, patterns=[pattern])
    return QueueItem(problem=p, reason="due", priority_score=score)


def numbers(items):
    return [i.problem.number for i in items]


# The real queue from 2026-09-23: five graph problems outrank everything else.
GRAPH_HEAVY = [
    item(261, 11, "union-find",       11.9),
    item(200, 11, "grid-dfs",          8.9),
    item(417, 11, "grid-dfs",          8.9),
    item(130, 11, "grid-dfs",          8.9),
    item(207, 11, "topological-sort",  8.9),
    item(128, 1,  "hashmap",           6.9),
    item(424, 3,  "sliding-window",    6.7),
    item(853, 4,  "monotonic-stack",   6.6),
]


def test_one_chapter_cannot_take_every_slot():
    got = pick_diverse(GRAPH_HEAVY, cap=4, per_chapter=2, per_pattern=2)
    assert numbers(got) == [261, 200, 128, 424]


def test_pattern_limit_alone_does_not_stop_a_chapter_monopoly():
    """Why both limits exist: 207 is topological sort, so a pattern-only rule still
    fills all four slots with graph problems."""
    got = pick_diverse(GRAPH_HEAVY, cap=4, per_chapter=0, per_pattern=2)
    assert numbers(got) == [261, 200, 417, 207]
    assert all(i.problem.chapter_num == 11 for i in got)


def test_pattern_limit_applies_across_chapters():
    items = [
        item(27, 1, "two-pointers", 9.0),
        item(75, 1, "two-pointers", 8.0),     # chapter 1 now full
        item(125, 2, "two-pointers", 7.0),    # different chapter, same pattern -> skipped
        item(33, 5, "binary-search", 6.0),
    ]
    got = pick_diverse(items, cap=3, per_chapter=2, per_pattern=2)
    assert numbers(got) == [27, 75, 33]


def test_backfills_when_everything_due_is_one_chapter():
    """The limits change which problems you get, never how many."""
    only_graphs = GRAPH_HEAVY[:5]
    got = pick_diverse(only_graphs, cap=4, per_chapter=2, per_pattern=2)
    assert len(got) == 4
    assert numbers(got) == [261, 200, 417, 130]


def test_backfill_takes_the_highest_priority_skipped_items():
    items = [
        item(1, 11, "a", 10.0),
        item(2, 11, "b", 9.0),
        item(3, 11, "c", 8.0),     # skipped, higher priority
        item(4, 11, "d", 7.0),     # skipped, lower priority
    ]
    got = pick_diverse(items, cap=3, per_chapter=2, per_pattern=0)
    assert numbers(got) == [1, 2, 3]


def test_result_is_in_priority_order():
    got = pick_diverse(GRAPH_HEAVY, cap=4, per_chapter=1, per_pattern=0)
    scores = [i.priority_score for i in got]
    assert scores == sorted(scores, reverse=True)


def test_zero_disables_both_limits():
    got = pick_diverse(GRAPH_HEAVY, cap=4, per_chapter=0, per_pattern=0)
    assert numbers(got) == numbers(GRAPH_HEAVY[:4])


def test_fewer_items_than_the_cap():
    got = pick_diverse(GRAPH_HEAVY[:2], cap=4, per_chapter=1, per_pattern=1)
    assert numbers(got) == [261, 200]


def test_today_endpoint_interleaves_chapters(client, db_session):
    """End to end: three failing graph problems and one array problem, cap 3."""
    d = study_today()
    rows = [
        (261, 11, 3), (200, 11, 2), (417, 11, 2),   # graphs, many failures
        (128, 1, 1),                                # arrays, one failure
    ]
    for number, chapter, lapses in rows:
        p = Problem(number=number, title=f"P{number}", difficulty="Medium",
                    chapter_num=chapter, chapter=f"Ch{chapter}", url="", kind="problem")
        db_session.add(p)
        db_session.flush()
        db_session.add(ReviewState(problem_id=p.id, interval_days=1, reps=1,
                                   lapses=lapses, due=d - timedelta(days=1)))
    db_session.commit()

    q = client.get("/review/today", params={"review_cap": 3}).json()
    assert [i["problem"]["number"] for i in q["reviews"]] == [261, 200, 128]
    assert q["deferred"] == 1


def test_next_batch_is_random_and_stable(client, db_session):
    """'Next batch' sends a seed and the batch on screen. The pick is random, avoids that
    batch while enough is due, and stays put as its problems get done."""
    d = study_today()
    states = {}
    for number in range(1, 13):
        p = Problem(number=number, title=f"P{number}", difficulty="Medium",
                    chapter_num=number, chapter=f"Ch{number}", url="", kind="problem")
        db_session.add(p)
        db_session.flush()
        states[number] = ReviewState(problem_id=p.id, interval_days=1, reps=1,
                                     lapses=13 - number, due=d - timedelta(days=1))
        db_session.add(states[number])
    db_session.commit()

    def pick(**params):
        q = client.get("/review/today", params={"review_cap": 4, **params}).json()
        return q, [i["problem"]["number"] for i in q["reviews"]]

    first, by_priority = pick()
    assert by_priority == [1, 2, 3, 4]
    on_screen = [i["problem"]["id"] for i in first["reviews"]]

    batches = {tuple(pick(shuffle=seed, skip=on_screen)[1]) for seed in range(20)}
    assert len(batches) > 1                                     # random
    assert all(not set(b) & {1, 2, 3, 4} for b in batches)     # avoids the batch on screen
    q, batch = pick(shuffle=7, skip=on_screen)
    assert q["total_due"] == 12 and q["deferred"] == 8          # nothing is dropped

    # Finishing one keeps the other three where they were
    states[batch[0]].due = d + timedelta(days=3)
    db_session.commit()
    assert pick(shuffle=7, skip=on_screen)[1][:3] == batch[1:]

    # With fewer due than skipped, skipped ones still fill the batch
    assert len(pick(shuffle=7, skip=list(range(1, 100)))[1]) == 4


# --- new problems ---

from app.neetcode150 import NEETCODE_150, NEETCODE_150_BY_CHAPTER
from app.scheduler import new_problem_tiers, pick_tiered
from app.study_plans import LC_75_PLAN, TOP_150_PLAN


def fresh(number, chapter, difficulty="Medium", pattern="x", nc150=True):
    return SimpleNamespace(number=number, chapter_num=chapter, difficulty=difficulty,
                           patterns=[pattern], in_neetcode150=nc150)


def as_items(tiers):
    return [[QueueItem(problem=p, reason="new") for p in t] for t in tiers]


def test_keeps_input_order_rather_than_resorting_by_score():
    """New problems all score 0; the roadmap order must survive the pick."""
    items = [QueueItem(problem=fresh(n, ch, pattern=f"p{n}"), reason="new")
             for n, ch in [(75, 1), (122, 1), (18, 2), (209, 3)]]
    got = pick_diverse(items, cap=3, per_chapter=1, per_pattern=0)
    assert numbers(got) == [75, 18, 209]


def test_tiers_are_150_then_additions_then_hards():
    ps = [
        fresh(88, 2, "Easy", nc150=False),       # addition
        fresh(42, 2, "Hard"),                    # 150 Hard
        fresh(746, 13, "Easy"),                  # 150
        fresh(4, 5, "Hard", nc150=False),        # addition Hard (not really, but a test)
        fresh(198, 13),                          # 150
    ]
    tiers = new_problem_tiers(ps)
    assert [[p.number for p in t] for t in tiers] == [[746, 198], [88], [42], [4]]


def test_150_tier_follows_neetcode_order_not_problem_number():
    """1-D DP is 70, 746, 198, 213, 5 ... — by number 5 would jump the queue."""
    ps = [fresh(n, 13) for n in (5, 213, 198, 746)]
    assert [p.number for p in new_problem_tiers(ps)[0]] == [746, 198, 213, 5]


def test_top150_problems_follow_the_study_plan_order():
    """Second tier = LeetCode's own sequence for the plan, not problem number."""
    nums = (380, 88, 274, 80, 58)                    # all Top 150, none NeetCode 150
    ps = [fresh(n, 1, nc150=False) for n in nums]
    order = [p.number for p in new_problem_tiers(ps)[0]]
    assert order == sorted(nums, key=TOP_150_PLAN.position.__getitem__)
    assert order[0] == 88, "Merge Sorted Array opens the study plan"


def test_leetcode_75_comes_after_top_150_in_its_own_order():
    """1768 and 1071 are LeetCode 75 only; 88 is Top 150."""
    ps = [fresh(n, 1, "Easy", nc150=False) for n in (1071, 1768, 88)]
    tiers = [[p.number for p in t] for t in new_problem_tiers(ps)]
    assert tiers == [[88], sorted([1071, 1768], key=LC_75_PLAN.position.__getitem__)]
    assert tiers[1][0] == 1768, "Merge Strings Alternately opens LeetCode 75"


def test_later_chapter_problems_outside_the_plan_come_after_it():
    """338 Counting Bits is NeetCode 150 (Bit, a later chapter) but not in Top 150."""
    ps = [fresh(338, 17, "Easy"), fresh(88, 1, "Easy", nc150=False)]
    tiers = new_problem_tiers(ps, later_chapters=frozenset({17, 18}))
    assert [p.number for p in tiers[0]] == [88, 338]


def test_150_is_exhausted_before_any_addition_even_in_one_chapter():
    """Chapter spreading must not pull an addition in while 150 problems remain."""
    ps = [fresh(n, 13) for n in (746, 198, 213)] + \
         [fresh(n, ch, nc150=False) for n, ch in ((88, 2), (219, 3))]
    got = pick_tiered(as_items(new_problem_tiers(ps)), cap=3, per_chapter=1, per_pattern=0)
    assert numbers(got) == [746, 198, 213]


def test_additions_fill_the_slots_the_150_cannot():
    ps = [fresh(746, 13)] + [fresh(n, ch, nc150=False) for n, ch in ((88, 2), (219, 3))]
    got = pick_tiered(as_items(new_problem_tiers(ps)), cap=3, per_chapter=1, per_pattern=0)
    assert numbers(got)[0] == 746
    assert sorted(numbers(got)[1:]) == [88, 219]


def test_switches_restore_plain_roadmap_order():
    ps = [fresh(88, 2, "Easy", nc150=False), fresh(42, 2, "Hard"), fresh(746, 13, "Easy")]
    tiers = new_problem_tiers(ps, hard_last=False, nc150_first=False)
    assert [[p.number for p in t] for t in tiers] == [[42, 88, 746]]


def test_official_150_list_is_complete_and_in_the_seed():
    import json
    from pathlib import Path
    seed = json.loads((Path(__file__).resolve().parents[2] / "data" / "seed.json").read_text())
    by_number = {p["number"]: p for p in seed["problems"]}
    assert len(NEETCODE_150) == 150
    assert sum(len(v) for v in NEETCODE_150_BY_CHAPTER.values()) == 150, "no duplicates"
    assert NEETCODE_150 <= set(by_number)
    assert {n for n, p in by_number.items() if p["in_neetcode150"]} == NEETCODE_150
    for chapter, nums in NEETCODE_150_BY_CHAPTER.items():
        assert all(by_number[n]["chapter_num"] == chapter for n in nums), chapter


def test_today_new_problems_follow_order_and_skip_hards(client, db_session):
    """No chapter spreading for new problems by default: strict tier order."""
    for number, chapter, diff in [
        (41, 1, "Hard"), (75, 1, "Medium"), (122, 1, "Medium"),
        (18, 2, "Medium"), (26, 2, "Easy"),
        (209, 3, "Medium"),
    ]:
        db_session.add(Problem(number=number, title=f"P{number}", difficulty=diff,
                               chapter_num=chapter, chapter=f"Ch{chapter}", url="",
                               kind="problem"))
    db_session.commit()

    q = client.get("/review/today", params={"new_cap": 3}).json()
    assert [i["problem"]["number"] for i in q["new_problems"]] == [75, 122, 18]


def test_later_chapters_wait_with_the_additions():
    """Bit & Math are NeetCode 150 but were left out of the study plan."""
    ps = [fresh(136, 17, "Easy"), fresh(48, 18), fresh(746, 13, "Easy"),
          fresh(88, 2, "Easy", nc150=False)]
    tiers = new_problem_tiers(ps, later_chapters=frozenset({17, 18}))
    assert [p.number for p in tiers[0]] == [746]
    assert sorted(p.number for p in tiers[1]) == [48, 88, 136]


def test_later_chapters_empty_keeps_them_in_the_150():
    ps = [fresh(136, 17, "Easy"), fresh(746, 13, "Easy")]
    tiers = new_problem_tiers(ps, later_chapters=frozenset())
    assert [p.number for p in tiers[0]] == [746, 136]


def test_later_chapters_setting_parses_csv():
    from app.config import Settings
    assert Settings(new_later_chapters="17, 18").new_later_chapter_set == {17, 18}
    assert Settings(new_later_chapters="").new_later_chapter_set == frozenset()


def test_new_problems_keep_strict_order_without_caps():
    """A pattern cap would skip 213 (third dp-1d) and pull 5 forward."""
    ps = [fresh(n, 13, pattern=pat) for n, pat in
          ((746, "dp-1d"), (198, "dp-1d"), (213, "dp-1d"), (5, "dp-string"))]
    got = pick_tiered(as_items(new_problem_tiers(ps)), cap=3, per_chapter=0, per_pattern=0)
    assert numbers(got) == [746, 198, 213]


def test_new_backfills_when_only_one_chapter_is_left(client, db_session):
    for number in (169, 229, 238):
        db_session.add(Problem(number=number, title=f"P{number}", difficulty="Medium",
                               chapter_num=1, chapter="Ch1", url="", kind="problem"))
    db_session.commit()

    q = client.get("/review/today", params={"new_cap": 3}).json()
    assert len(q["new_problems"]) == 3
