"""job requires_account

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30 20:55:07.157386
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('requires_account', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('jobs', 'requires_account')
