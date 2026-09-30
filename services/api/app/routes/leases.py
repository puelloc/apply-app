"""Lease endpoints: the worker acquires, heartbeats, and releases a job's lease."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_session
from ..schemas.job import JobRead
from ..schemas.lease import LeaseAcquired, LeaseToken
from ..services import jobs as service

router = APIRouter(prefix="/leases", tags=["leases"])


@router.post("/acquire", response_model=LeaseAcquired)
def acquire(session: Session = Depends(get_session)) -> LeaseAcquired:
    result = service.acquire(session)
    if result is None:
        raise HTTPException(status_code=404, detail="no queued job")
    job, token, expires = result
    return LeaseAcquired(job=JobRead.model_validate(job), lease_token=token, expires_at=expires)


@router.post("/{job_id}/heartbeat")
def heartbeat(job_id: int, payload: LeaseToken, session: Session = Depends(get_session)) -> dict:
    expires = service.heartbeat(session, job_id, payload.lease_token)
    if expires is None:
        raise HTTPException(status_code=409, detail="lease not found or token mismatch")
    return {"expires_at": expires}


@router.post("/{job_id}/release")
def release(job_id: int, payload: LeaseToken, session: Session = Depends(get_session)) -> dict:
    if not service.release(session, job_id, payload.lease_token):
        raise HTTPException(status_code=409, detail="lease not found or token mismatch")
    return {"released": True}
