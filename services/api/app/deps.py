"""FastAPI dependency: a request-scoped SQLAlchemy session."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.db.session()
    try:
        yield session
    finally:
        session.close()
