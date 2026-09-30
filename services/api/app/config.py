"""Configuration from environment variables (no external settings library)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str
    debug: bool


def get_settings() -> Settings:
    """Read settings from the environment (at call time, for testability)."""
    return Settings(
        db_path=os.environ.get("DB_PATH", "/data/jobs.db"),
        debug=os.environ.get("DEBUG", "false").lower() == "true",
    )
