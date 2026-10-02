"""job fill_summary + approved

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-02 18:36:55.239178
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('fill_summary', sa.JSON(), nullable=True))
    op.add_column('jobs', sa.Column('approved', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('jobs', 'approved')
    op.drop_column('jobs', 'fill_summary')
