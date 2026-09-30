"""Pydantic schemas for step events (the diagnostics spine)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StepEventCreate(BaseModel):
    run_id: str
    step: str
    adapter: str | None = None
    action: str
    postcondition: str | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    model_meta: dict[str, Any] | None = None


class StepEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    run_id: str
    step: str
    adapter: str | None
    action: str
    postcondition: str | None
    duration_ms: int | None
    error_code: str | None
    model_meta: dict[str, Any] | None
    created_at: datetime
