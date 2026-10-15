"""Move notes and the latest solution off the shared problems table into problem_notes,
one row per (user, problem).

Existing notes and code are the local user's: they came from that person's NeetCode notes
and submissions. A template's notes column only ever held the fixed "Blind-write practice"
label, so for templates just the code (the last blind-write) is copied.

The downgrade puts the local user's notes and code back on problems.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15
"""
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _local_user_id(conn, create: bool) -> int | None:
    find = sa.text("SELECT id FROM users WHERE provider = 'local' AND provider_id = 'local'")
    uid = conn.execute(find).scalar()
    if uid is None and create:
        insert = sa.text(
            "INSERT INTO users (provider, provider_id, login, display_name, avatar_url,"
            " is_owner, is_demo, ai_enabled, created_at)"
            " VALUES ('local', 'local', 'local', 'Local user', '', :yes, :no, :yes, :now)"
        ).bindparams(
            sa.bindparam("yes", type_=sa.Boolean()),
            sa.bindparam("no", type_=sa.Boolean()),
            sa.bindparam("now", type_=sa.DateTime()),
        )
        conn.execute(insert, {"yes": True, "no": False, "now": _now()})
        uid = conn.execute(find).scalar()
    return uid


def upgrade() -> None:
    conn = op.get_bind()
    op.create_table(
        "problem_notes",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"]),
        sa.PrimaryKeyConstraint("user_id", "problem_id"),
    )

    personal = "(kind = 'problem' AND notes <> '') OR code <> ''"
    if conn.execute(sa.text(f"SELECT 1 FROM problems WHERE {personal} LIMIT 1")).first():
        owner = _local_user_id(conn, create=True)
        copy = sa.text(
            "INSERT INTO problem_notes (user_id, problem_id, notes, code, updated_at)"
            " SELECT :owner, id, CASE WHEN kind = 'template' THEN '' ELSE notes END, code, :now"
            f" FROM problems WHERE {personal}"
        ).bindparams(sa.bindparam("now", type_=sa.DateTime()))
        conn.execute(copy, {"owner": owner, "now": _now()})

    with op.batch_alter_table("problems") as batch:
        batch.drop_column("notes")
        batch.drop_column("code")


def downgrade() -> None:
    conn = op.get_bind()
    with op.batch_alter_table("problems") as batch:
        batch.add_column(sa.Column("notes", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("code", sa.Text(), nullable=False, server_default=""))

    owner = _local_user_id(conn, create=False)
    if owner is not None:
        for col in ("notes", "code"):
            conn.execute(sa.text(
                f"UPDATE problems SET {col} = COALESCE((SELECT n.{col} FROM problem_notes n"
                f" WHERE n.problem_id = problems.id AND n.user_id = :owner), '')"
            ), {"owner": owner})
    op.drop_table("problem_notes")
