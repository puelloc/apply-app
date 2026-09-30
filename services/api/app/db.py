"""SQLAlchemy engine + sessions. SQLite in WAL mode (concurrent readers + one writer)."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def _enable_wal(engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Database:
    """Owns the engine and produces sessions. Pass a path (temp file in tests)."""

    def __init__(self, path: str) -> None:
        self.engine = create_engine(f"sqlite:///{path}", future=True)
        _enable_wal(self.engine)
        self._session_factory = sessionmaker(bind=self.engine, future=True)

    def session(self) -> Session:
        return self._session_factory()
