"""job idempotency key

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30 16:55:59.314985
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('idempotency_key', sa.String(length=128), nullable=True))
    # SQLite implements a UNIQUE constraint as a unique index, so use an index (ALTER ... ADD
    # CONSTRAINT is unsupported on SQLite).
    op.create_index('uq_jobs_idempotency_key', 'jobs', ['idempotency_key'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_jobs_idempotency_key', table_name='jobs')
    op.drop_column('jobs', 'idempotency_key')
    # ### end Alembic commands ###
