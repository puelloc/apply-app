"""`doctor`: named health checks, each returning (ok, detail).

Checks that depend on services built later are listed as deferred comments and wired in steps 4-7:
  vault (4), browser CDP + egress proxy + host memory/disk/throttle (5), IMAP (7).
"""

from __future__ import annotations

import os
import urllib.request
from datetime import datetime, timezone

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Lease


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check_db_migrations(engine) -> tuple[bool, str]:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head = script.get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current == head, f"current={current} head={head}"


def check_stuck_leases(session: Session) -> tuple[bool, str]:
    expired = session.execute(
        select(func.count()).select_from(Lease).where(Lease.expires_at < _utcnow())
    ).scalar_one()
    return expired == 0, f"{expired} expired lease(s)"


def check_ollama(base_url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=5) as resp:
            return resp.status == 200, f"http {resp.status}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def run_doctor(engine, session: Session) -> list[dict[str, object]]:
    base_url = os.environ.get("OLLAMA_BASE_URL", "https://ai.siggy-lab.org")
    checks = [
        ("db_migrations", check_db_migrations(engine)),
        ("stuck_leases", check_stuck_leases(session)),
        ("ollama_reachable", check_ollama(base_url)),
    ]
    return [{"name": name, "ok": ok, "detail": detail} for name, (ok, detail) in checks]
