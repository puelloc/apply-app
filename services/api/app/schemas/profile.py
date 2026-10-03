"""Profile schemas: single-user contact + resume (admin write, diagnose read)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_name: str
    last_name: str
    email: str
    phone: str
    resume: str


class ProfileUpdate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str
    resume: str = ""
