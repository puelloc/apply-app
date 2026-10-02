"""Pydantic request/response schemas for jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    company_name: str
    title: str
    listing_url: str
    application_url: str | None = None
    description: str | None = None
    ats: str | None = None
    external_id: str | None = None
    resume_version: str | None = None
    idempotency_key: str | None = None
    requires_account: bool = False
    requires_verification: bool = True


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    state: str
    company_name: str
    title: str
    listing_url: str
    application_url: str | None
    description: str | None
    ats: str | None
    external_id: str | None
    resume_version: str | None
    error_code: str | None
    requires_account: bool
    requires_verification: bool
    fill_summary: dict[str, Any] | None
    approved: bool
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobRead]
    next_cursor: int | None
    total: int


class JobAction(BaseModel):
    action: Literal["cancel", "skip", "retry", "requeue", "restage", "mark_submitted"]


class JobStateUpdate(BaseModel):
    state: Literal["awaiting_email", "account_created", "ready_for_review", "submitted", "failed", "needs_human"]
