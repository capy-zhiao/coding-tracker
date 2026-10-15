"""migrate.py and the Alembic migrations, against real SQLite files.

A new database and one created before Alembic must both end at the latest revision with
their data intact, and the models must never drift from what the migrations build.
"""
import sqlite3

from alembic import command
from alembic.script import ScriptDirectory

import migrate


def make_url(tmp_path):
    return f"sqlite:///{tmp_path / 'tracker.db'}"


def head(url):
    return ScriptDirectory.from_config(migrate.alembic_config(url)).get_current_head()


def pre_alembic_database(tmp_path):
    """A database as create_all() used to leave it: the baseline tables, no alembic_version."""
    url = make_url(tmp_path)
    command.upgrade(migrate.alembic_config(url), migrate.BASELINE)
    con = sqlite3.connect(tmp_path / "tracker.db")
    con.execute("DROP TABLE alembic_version")
    con.execute(
        "INSERT INTO problems (id, number, title, difficulty, chapter_num, chapter, url,"
        " in_neetcode150, in_top150, in_lc75, kind, notes, code, patterns)"
        " VALUES (1, 1, 'Two Sum', 'Easy', 1, 'Arrays & Hashing', '', 1, 1, 0, 'problem',"
        " 'my notes', 'def twoSum(): ...', '[]')"
    )
    con.execute(
        "INSERT INTO review_states (problem_id, interval_days, ease, reps, lapses, due,"
        " total_attempts) VALUES (1, 3, 2.5, 2, 1, '2026-10-01', 2)"
    )
    con.execute(
        "INSERT INTO attempts (problem_id, created_at, grade, seconds, looked_at_solution,"
        " had_bugs, mistakes, code, note, mode, time_complexity, space_complexity)"
        " VALUES (1, '2026-09-28 20:00:00', 'good', 600, 0, 0, '[]', '', '', 'practice',"
        " 'O(n)', 'O(n)')"
    )
    con.commit()
    con.close()
    return url


def test_new_database_is_built_by_the_migrations(tmp_path):
    url = make_url(tmp_path)
    migrate.migrate(url)
    assert migrate.current_revision(url) == head(url)
    # Raises if app/models.py and the migrations disagree about any table or column.
    command.check(migrate.alembic_config(url))


def test_existing_database_is_adopted_and_keeps_its_data(tmp_path, capsys):
    url = pre_alembic_database(tmp_path)

    migrate.migrate(url)

    assert migrate.current_revision(url) == head(url)
    assert "adopted at revision 0001" in capsys.readouterr().out
    con = sqlite3.connect(tmp_path / "tracker.db")
    assert con.execute("SELECT count(*) FROM attempts").fetchone() == (1,)
    assert con.execute("SELECT count(*) FROM review_states").fetchone() == (1,)
    con.close()
    # The untouched original is kept next to it
    assert len(list((tmp_path / ".backups").glob("tracker-*.db"))) == 1


def test_database_older_than_the_baseline_gets_the_missing_columns(tmp_path):
    url = pre_alembic_database(tmp_path)
    con = sqlite3.connect(tmp_path / "tracker.db")
    con.execute("ALTER TABLE problems DROP COLUMN in_lc75")
    con.execute("ALTER TABLE attempts DROP COLUMN complexity_ai")
    con.commit()
    con.close()

    migrate.migrate(url)

    con = sqlite3.connect(tmp_path / "tracker.db")
    assert "in_lc75" in {r[1] for r in con.execute("PRAGMA table_info(problems)")}
    assert "complexity_ai" in {r[1] for r in con.execute("PRAGMA table_info(attempts)")}
    con.close()
    assert migrate.current_revision(url) == head(url)


def test_running_twice_changes_nothing(tmp_path, capsys):
    url = make_url(tmp_path)
    migrate.migrate(url)
    capsys.readouterr()
    migrate.migrate(url)
    assert "Schema up to date" in capsys.readouterr().out


def test_existing_rows_are_given_to_the_local_user(tmp_path):
    url = pre_alembic_database(tmp_path)     # one review state and one attempt, no users

    migrate.migrate(url)

    con = sqlite3.connect(tmp_path / "tracker.db")
    users = con.execute("SELECT id, provider, provider_id, is_owner FROM users").fetchall()
    assert len(users) == 1
    uid, provider, provider_id, is_owner = users[0]
    assert (provider, provider_id, is_owner) == ("local", "local", 1)
    assert con.execute("SELECT user_id FROM review_states").fetchall() == [(uid,)]
    assert con.execute("SELECT user_id FROM attempts").fetchall() == [(uid,)]
    con.close()


def test_ownership_can_be_rolled_back_without_losing_the_local_users_rows(tmp_path):
    url = pre_alembic_database(tmp_path)
    migrate.migrate(url)
    cfg = migrate.alembic_config(url)

    command.downgrade(cfg, "0002")

    con = sqlite3.connect(tmp_path / "tracker.db")
    assert con.execute("SELECT count(*) FROM review_states").fetchone() == (1,)
    assert con.execute("SELECT count(*) FROM attempts").fetchone() == (1,)
    assert "user_id" not in {r[1] for r in con.execute("PRAGMA table_info(attempts)")}
    con.close()
    command.upgrade(cfg, "head")                 # and forward again
    assert migrate.current_revision(url) == head(url)
