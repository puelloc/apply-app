"""The Job model — the queue's central entity, plus the queue-state vocabulary."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

# Plan's state machine:  queued → running → awaiting_email → account_created →
#                        ready_for_review → submitted
QUEUE_STATES = frozenset(
    {"queued", "running", "awaiting_email", "account_created", "ready_for_review", "submitted"}
)
SIDE_STATES = frozenset(
    {"needs_human", "stale", "restaging", "skipped", "cancelled", "failed", "submitted_unconfirmed"}
)
ALL_STATES = QUEUE_STATES | SIDE_STATES


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    company_name: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    listing_url: Mapped[str] = mapped_column(Text)
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ats: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    # True = the site requires an account (signup/login -> verify -> apply). False (default) = quick
    # apply, no account. Set explicitly at intake, or derived from the ATS default.
    requires_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    # True (default) = the signup needs email verification (IMAP). False = signup then apply directly
    # (no verification email). Only meaningful when requires_account is true.
    requires_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    # Frozen answers: the field diff saved on the first run (value/source/confidence/flags). Re-staging
    # replays these and never regenerates them.
    fill_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # True once the user has reviewed and picked this job (approve NEVER submits).
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
