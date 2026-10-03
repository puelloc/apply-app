"""Single-user profile (one row): the contact + resume the worker fills into applications."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)  # always 1 (single-user)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resume: Mapped[str] = mapped_column(Text, nullable=False, default="")
