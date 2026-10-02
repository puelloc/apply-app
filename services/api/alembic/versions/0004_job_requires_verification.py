"""job requires_verification

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02 18:25:15.398378
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('requires_verification', sa.Boolean(), server_default='1', nullable=False))


def downgrade() -> None:
    op.drop_column('jobs', 'requires_verification')
