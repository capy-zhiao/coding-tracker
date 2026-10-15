"""Baseline: the schema as it stood before Alembic.

Databases created before Alembic already have exactly these tables (checked against a
real one), so migrate.py marks them as being at this revision instead of running it;
only a brand-new database actually runs this upgrade.

Revision ID: 0001
Revises: 
Create Date: 2026-10-15 17:53:45.527264
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('problems',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('difficulty', sa.String(length=10), nullable=False),
    sa.Column('chapter_num', sa.Integer(), nullable=False),
    sa.Column('chapter', sa.String(length=60), nullable=False),
    sa.Column('url', sa.String(length=300), nullable=False),
    sa.Column('in_neetcode150', sa.Boolean(), nullable=False),
    sa.Column('in_top150', sa.Boolean(), nullable=False),
    sa.Column('in_lc75', sa.Boolean(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('patterns', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('problems', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_problems_chapter_num'), ['chapter_num'], unique=False)
        batch_op.create_index(batch_op.f('ix_problems_number'), ['number'], unique=True)

    op.create_table('attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('grade', sa.String(length=10), nullable=False),
    sa.Column('seconds', sa.Integer(), nullable=False),
    sa.Column('looked_at_solution', sa.Boolean(), nullable=False),
    sa.Column('had_bugs', sa.Boolean(), nullable=False),
    sa.Column('mistakes', sa.JSON(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('mode', sa.String(length=10), nullable=False),
    sa.Column('time_complexity', sa.String(length=40), nullable=False),
    sa.Column('space_complexity', sa.String(length=40), nullable=False),
    sa.Column('complexity_ok', sa.Boolean(), nullable=True),
    sa.Column('complexity_ai', sa.JSON(), nullable=True),
    sa.Column('blindwrite_score', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attempts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_attempts_problem_id'), ['problem_id'], unique=False)

    op.create_table('followups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('hint', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('followups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_followups_problem_id'), ['problem_id'], unique=False)

    op.create_table('interview_qas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('key_points', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('grade', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('answered_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('interview_qas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_interview_qas_problem_id'), ['problem_id'], unique=False)

    op.create_table('review_states',
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('interval_days', sa.Integer(), nullable=False),
    sa.Column('ease', sa.Float(), nullable=False),
    sa.Column('reps', sa.Integer(), nullable=False),
    sa.Column('lapses', sa.Integer(), nullable=False),
    sa.Column('due', sa.Date(), nullable=True),
    sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
    sa.Column('total_attempts', sa.Integer(), nullable=False),
    sa.Column('best_seconds', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['problem_id'], ['problems.id'], ),
    sa.PrimaryKeyConstraint('problem_id')
    )
    with op.batch_alter_table('review_states', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_review_states_due'), ['due'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('review_states', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_review_states_due'))

    op.drop_table('review_states')
    with op.batch_alter_table('interview_qas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_interview_qas_problem_id'))

    op.drop_table('interview_qas')
    with op.batch_alter_table('followups', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_followups_problem_id'))

    op.drop_table('followups')
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attempts_problem_id'))
        batch_op.drop_index(batch_op.f('ix_attempts_created_at'))

    op.drop_table('attempts')
    with op.batch_alter_table('problems', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_problems_number'))
        batch_op.drop_index(batch_op.f('ix_problems_chapter_num'))

    op.drop_table('problems')
