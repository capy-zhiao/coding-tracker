"""Give personal data an owner: review_states, attempts and interview_qas get user_id.

review_states changes its primary key from problem_id to (user_id, problem_id). SQLite
can't change a primary key in place, so the table is rebuilt explicitly: create the new
one, copy, drop the old one, rename. That runs the same way on Postgres.

Every existing row belongs to the local user, the only user a database from before this
change ever had. They are created here if the app hasn't created them yet.

The downgrade keeps only the local user's rows, since the old schema has room for one
person's data.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15
"""
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATE_COLUMNS = ("problem_id, interval_days, ease, reps, lapses, due, last_attempt_at,"
                 " total_attempts, best_seconds")
OWNED_TABLES = ("attempts", "interview_qas")


def _state_columns() -> list[sa.Column]:
    return [
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("ease", sa.Float(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column("due", sa.Date(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("total_attempts", sa.Integer(), nullable=False),
        sa.Column("best_seconds", sa.Integer(), nullable=True),
    ]


def _local_user_id(conn, create: bool) -> int | None:
    find = sa.text("SELECT id FROM users WHERE provider = 'local' AND provider_id = 'local'")
    uid = conn.execute(find).scalar()
    if uid is None and create:
        insert = sa.text(
            "INSERT INTO users (provider, provider_id, login, display_name, avatar_url,"
            " is_owner, is_demo, ai_enabled, created_at)"
            " VALUES ('local', 'local', 'local', 'Local user', '', :yes, :no, :yes, :now)"
        ).bindparams(       # typed, so each database gets its own boolean and timestamp form
            sa.bindparam("yes", type_=sa.Boolean()),
            sa.bindparam("no", type_=sa.Boolean()),
            sa.bindparam("now", type_=sa.DateTime()),
        )
        conn.execute(insert, {"yes": True, "no": False,
                              "now": datetime.now(timezone.utc).replace(tzinfo=None)})
        uid = conn.execute(find).scalar()
    return uid


def _has_rows(conn, table: str) -> bool:
    return conn.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None


def upgrade() -> None:
    conn = op.get_bind()
    has_data = any(_has_rows(conn, t) for t in ("review_states", *OWNED_TABLES))
    owner = _local_user_id(conn, create=has_data)

    # 1. review_states: rebuild with (user_id, problem_id) as the key
    op.create_table(
        "review_states_new",
        sa.Column("user_id", sa.Integer(), nullable=False),
        *_state_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"]),
        sa.PrimaryKeyConstraint("user_id", "problem_id"),
    )
    if owner is not None:
        op.execute(sa.text(
            f"INSERT INTO review_states_new (user_id, {STATE_COLUMNS})"
            f" SELECT :owner, {STATE_COLUMNS} FROM review_states"
        ).bindparams(owner=owner))
    op.drop_index("ix_review_states_due", table_name="review_states")
    op.drop_table("review_states")
    op.rename_table("review_states_new", "review_states")
    op.create_index("ix_review_states_user_due", "review_states", ["user_id", "due"])

    # 2. attempts, interview_qas: add user_id, fill it in, then make it required
    for table in OWNED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        if owner is not None:
            op.execute(sa.text(f"UPDATE {table} SET user_id = :owner").bindparams(owner=owner))
        with op.batch_alter_table(table) as batch:
            batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(f"fk_{table}_user_id_users", "users",
                                     ["user_id"], ["id"], ondelete="CASCADE")
            batch.create_index(f"ix_{table}_user_id", ["user_id"])


def downgrade() -> None:
    conn = op.get_bind()
    owner = _local_user_id(conn, create=False)

    for table in OWNED_TABLES:
        op.execute(sa.text(f"DELETE FROM {table} WHERE user_id <> :owner OR :owner IS NULL")
                   .bindparams(owner=owner))
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_user_id")
            batch.drop_constraint(f"fk_{table}_user_id_users", type_="foreignkey")
            batch.drop_column("user_id")

    op.create_table(
        "review_states_old",
        *_state_columns(),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"]),
        sa.PrimaryKeyConstraint("problem_id"),
    )
    if owner is not None:
        op.execute(sa.text(
            f"INSERT INTO review_states_old ({STATE_COLUMNS})"
            f" SELECT {STATE_COLUMNS} FROM review_states WHERE user_id = :owner"
        ).bindparams(owner=owner))
    op.drop_index("ix_review_states_user_due", table_name="review_states")
    op.drop_table("review_states")
    op.rename_table("review_states_old", "review_states")
    op.create_index("ix_review_states_due", "review_states", ["due"])
