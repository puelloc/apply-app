"""Pydantic schemas for accounts (metadata only — passwords live in the vault)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    alias: str
    site: str


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alias: str
    site: str
    state: str
    created_at: datetime
    updated_at: datetime
