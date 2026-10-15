"""Which template drill today's queue offers."""
from datetime import datetime, timedelta

from app.deps import today
from app.models import Problem, ReviewState
from app.scheduler import build_today


def template(number):
    return Problem(number=number, title=f"T{number}", difficulty="Medium", chapter_num=11,
                   chapter="Graphs", url="", kind="template")


def test_with_none_due_the_never_practised_template_comes_first(db_session, user):
    """Some templates practised and some not used to crash the queue: the sort key mixed
    a datetime with a 0 placeholder, and comparing those raises TypeError."""
    done, fresh = template(9001), template(9002)
    db_session.add_all([done, fresh])
    db_session.flush()
    d = today()
    db_session.add(ReviewState(user_id=user.id, problem_id=done.id, interval_days=5,
                               due=d + timedelta(days=5),
                               last_attempt_at=datetime(2026, 10, 1, 20, 0)))
    db_session.commit()

    q = build_today(db_session, user.id, d)

    assert [i.problem.number for i in q.templates] == [9002]


def test_with_none_due_the_longest_untouched_comes_first(db_session, user):
    older, newer = template(9001), template(9002)
    db_session.add_all([older, newer])
    db_session.flush()
    d = today()
    for t, when in ((older, datetime(2026, 9, 1)), (newer, datetime(2026, 10, 1))):
        db_session.add(ReviewState(user_id=user.id, problem_id=t.id, interval_days=5,
                                   due=d + timedelta(days=5), last_attempt_at=when))
    db_session.commit()

    assert [i.problem.number for i in build_today(db_session, user.id, d).templates] == [9001]
