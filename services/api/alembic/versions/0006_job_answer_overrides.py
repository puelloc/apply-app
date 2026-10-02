"""job answer_overrides

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02 18:43:34.661142
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('answer_overrides', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'answer_overrides')
