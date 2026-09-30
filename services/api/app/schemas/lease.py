"""Pydantic request/response schemas for leases."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .job import JobRead


class LeaseAcquired(BaseModel):
    job: JobRead
    lease_token: str
    expires_at: datetime


class LeaseToken(BaseModel):
    lease_token: str
