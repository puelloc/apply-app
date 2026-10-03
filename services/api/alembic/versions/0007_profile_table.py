"""profile table

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02 21:18:29.840992
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('profile',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(length=128), nullable=False),
        sa.Column('last_name', sa.String(length=128), nullable=False),
        sa.Column('email', sa.String(length=256), nullable=False),
        sa.Column('phone', sa.String(length=64), nullable=False),
        sa.Column('resume', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_profile'))
    )
    # Seed the single-user profile with CANARY placeholders (rule 7: never real data).
    op.execute(
        "INSERT INTO profile (id, first_name, last_name, email, phone, resume) VALUES "
        "(1, 'CANARY-First', 'CANARY-Last', 'canary@example.invalid', '555-0001', "
        "'CANARY resume — replace with a real resume.')"
    )


def downgrade() -> None:
    op.drop_table('profile')
