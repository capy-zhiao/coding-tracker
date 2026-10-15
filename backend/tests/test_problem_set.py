"""The problem set (NeetCode 150 + Top Interview 150 + LeetCode 75) and how seed_db.py
builds it."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.neetcode150 import NEETCODE_150
from app.study_plans import (
    CHAPTER_OVERRIDES, GROUP_CHAPTER, LC_75, PLANS, PROBLEM_SET, TOP_150,
)

BACKEND = Path(__file__).resolve().parents[1]


def test_study_plans_are_complete_and_ordered():
    assert [len(p.numbers) for p in PLANS] == [150, 75]
    for plan in PLANS:
        assert sorted(plan.position.values()) == list(range(len(plan.numbers))), plan.name


def test_every_study_plan_problem_has_a_chapter():
    for plan in PLANS:
        for p in plan.problems:
            assert p["number"] in CHAPTER_OVERRIDES or p["group"] in GROUP_CHAPTER, p


def test_problem_set_is_the_union():
    assert PROBLEM_SET == NEETCODE_150 | TOP_150 | LC_75
    assert len(PROBLEM_SET) == 272


def run_seed(db: Path) -> str:
    """The same two steps as start.sh: create/upgrade the tables, then load the problems."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "LLM_PROVIDER": "none"}
    out = ""
    for script in ("migrate.py", "seed_db.py"):
        r = subprocess.run([sys.executable, script], cwd=BACKEND, env=env,
                           capture_output=True, text=True, check=True)
        out = r.stdout
    return out


def test_seed_builds_the_set_and_prunes_only_untouched_problems(tmp_path):
    db = tmp_path / "t.db"
    run_seed(db)
    con = sqlite3.connect(db)
    nums = {n for (n,) in con.execute("SELECT number FROM problems WHERE kind='problem'")}
    assert nums == PROBLEM_SET
    assert con.execute("SELECT COUNT(*) FROM problems WHERE kind='template'").fetchone()[0] == 15
    # flags and links for a Top-150-only problem
    top_only = con.execute(
        "SELECT in_neetcode150, in_top150, url FROM problems WHERE number=380").fetchone()
    assert top_only[:2] == (0, 1) and "leetcode.com/problems/insert-delete-getrandom-o1" in top_only[2]
    # in both lists -> LeetCode; NeetCode 150 only -> stays on neetcode.io
    url = dict(con.execute("SELECT number, url FROM problems WHERE number IN (1, 217)").fetchall())
    assert "leetcode.com/problems/two-sum/" in url[1]
    assert "neetcode.io" in url[217]
    links = con.execute("SELECT SUM(url LIKE '%leetcode.com%'), COUNT(*) FROM problems "
                        "WHERE kind='problem' AND (in_top150 OR in_lc75)").fetchone()
    assert links[0] == links[1] == len(TOP_150 | LC_75), "every study-plan problem links to LeetCode"
    lc75 = con.execute("SELECT in_lc75, url FROM problems WHERE number=1768").fetchone()
    assert lc75[0] == 1 and "envId=leetcode-75" in lc75[1]

    # Two problems outside the set: one practised, one never touched
    con.execute("INSERT INTO problems (number,title,difficulty,chapter_num,chapter,url,"
                "in_neetcode150,in_top150,in_lc75,kind,notes,code,patterns) VALUES "
                "(1406,'Stone Game III','Hard',13,'1-D DP','',0,0,0,'problem','','','[]'),"
                "(877,'Stone Game','Medium',14,'2-D DP','',0,0,0,'problem','','','[]')")
    pid = con.execute("SELECT id FROM problems WHERE number=1406").fetchone()[0]
    con.execute("INSERT INTO attempts (problem_id,created_at,grade,seconds,looked_at_solution,"
                "had_bugs,mistakes,code,note,mode,time_complexity,space_complexity) "
                "VALUES (?,'2026-09-01','good',60,0,0,'[]','','','practice','','')", (pid,))
    con.commit()

    out = run_seed(db)
    left = {n for (n,) in con.execute("SELECT number FROM problems WHERE kind='problem'")}
    assert 877 not in left, "untouched problem outside the set is removed"
    assert 1406 in left, "a problem with practice history is never deleted"
    assert "kept (has practice history): [1406]" in out
