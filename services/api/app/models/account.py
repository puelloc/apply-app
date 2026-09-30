"""The Account model — metadata only; the password lives in the vault (step 4), never here."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(255), unique=True)   # the catch-all email alias
    site: Mapped[str] = mapped_column(String(255))                # the ATS domain
    state: Mapped[str] = mapped_column(String(16), default="pending")  # pending / confirmed
