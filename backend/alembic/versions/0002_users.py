"""Users table.

No rows are inserted here: local mode creates its one user on the first request, and
the migration that gives existing data an owner (0003) creates it when there is data.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15 17:57:21.381654
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('provider_id', sa.String(length=64), nullable=False),
    sa.Column('login', sa.String(length=100), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('avatar_url', sa.String(length=300), nullable=False),
    sa.Column('is_owner', sa.Boolean(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('ai_enabled', sa.Boolean(), nullable=False),
    sa.Column('ai_daily_limit', sa.Integer(), nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=True),
    sa.Column('daily_review_cap', sa.Integer(), nullable=True),
    sa.Column('daily_new_cap', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.Column('demo_reset_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'provider_id', name='uq_users_provider')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_login'), ['login'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_login'))

    op.drop_table('users')
