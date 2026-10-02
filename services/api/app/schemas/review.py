"""Pydantic schemas for the review flow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .job import JobRead


class FillSummaryWrite(BaseModel):
    fill_summary: dict[str, Any]


class AnswersUpdate(BaseModel):
    answers: dict[str, Any]


class ReviewResponse(BaseModel):
    job: JobRead
    ready_to_approve: bool
