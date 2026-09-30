"""Job queue business logic: the state machine and lease acquire/heartbeat/release."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job, Lease
from ..models.base import utcnow

LEASE_TTL = timedelta(minutes=5)

# action -> (allowed source states, target state)
TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "cancel": (frozenset({"queued", "running", "awaiting_email", "account_created", "ready_for_review", "needs_human", "restaging"}), "cancelled"),
    "skip": (frozenset({"ready_for_review", "needs_human"}), "skipped"),
    "retry": (frozenset({"failed"}), "queued"),
    "requeue": (frozenset({"failed", "cancelled", "skipped", "stale"}), "queued"),
    "restage": (frozenset({"ready_for_review", "stale"}), "restaging"),
    "mark_submitted": (frozenset({"ready_for_review"}), "submitted"),
}


class InvalidTransition(ValueError):
    pass


def transition(job: Job, action: str) -> None:
    """Apply a manual state transition, raising InvalidTransition when it's not allowed."""
    try:
        allowed, target = TRANSITIONS[action]
    except KeyError as exc:
        raise InvalidTransition(f"unknown action {action!r}") from exc
    if job.state not in allowed:
        raise InvalidTransition(f"cannot {action} from state {job.state!r}")
    job.state = target


def _lease_by_job(session: Session, job_id: int) -> Lease | None:
    return session.execute(select(Lease).where(Lease.job_id == job_id)).scalar_one_or_none()


def acquire(session: Session) -> tuple[Job, str, datetime] | None:
    """Lease the oldest queued job; returns (job, token, expires_at) or None when the queue is empty."""
    job = session.execute(select(Job).where(Job.state == "queued").order_by(Job.id).limit(1)).scalar_one_or_none()
    if job is None:
        return None
    token = secrets.token_urlsafe(16)
    expires = utcnow() + LEASE_TTL
    job.state = "running"
    session.add(Lease(job_id=job.id, lease_token=token, expires_at=expires))
    session.commit()
    return job, token, expires


def heartbeat(session: Session, job_id: int, token: str) -> datetime | None:
    """Refresh a lease if the token matches; returns the new expiry or None."""
    lease = _lease_by_job(session, job_id)
    if lease is None or lease.lease_token != token:
        return None
    lease.expires_at = utcnow() + LEASE_TTL
    lease.heartbeat_at = utcnow()
    session.commit()
    return lease.expires_at


def release(session: Session, job_id: int, token: str) -> bool:
    """Drop a lease if the token matches."""
    lease = _lease_by_job(session, job_id)
    if lease is None or lease.lease_token != token:
        return False
    session.delete(lease)
    session.commit()
    return True
