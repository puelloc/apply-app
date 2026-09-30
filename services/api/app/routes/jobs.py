"""Job endpoints: create (single + bulk), list (cursor + filters), get, and manual state actions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_session
from ..models import Job
from ..schemas.job import JobAction, JobCreate, JobListResponse, JobRead, JobStateUpdate
from ..security import require_scope
from ..services import jobs as service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _create_job(session: Session, payload: JobCreate) -> Job:
    if payload.idempotency_key:
        existing = session.execute(
            select(Job).where(Job.idempotency_key == payload.idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    job = Job(**payload.model_dump())
    session.add(job)
    session.flush()
    return job


@router.post("", response_model=JobRead, status_code=201)
def create_job(
    payload: JobCreate,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> Job:
    job = _create_job(session, payload)
    session.commit()
    session.refresh(job)
    return job


@router.post("/bulk", status_code=201)
def bulk_create(
    payload: list[JobCreate],
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> dict:
    jobs = [_create_job(session, item) for item in payload]
    session.commit()
    return {"total": len(jobs), "jobs": [JobRead.model_validate(j) for j in jobs]}


@router.get("", response_model=JobListResponse)
def list_jobs(
    state: str | None = None,
    ats: str | None = None,
    company: str | None = None,
    cursor: int | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> JobListResponse:
    limit = min(max(limit, 1), 200)
    filters = []
    if state:
        filters.append(Job.state == state)
    if ats:
        filters.append(Job.ats == ats)
    if company:
        filters.append(Job.company_name.ilike(f"%{company}%"))

    total = session.execute(select(func.count()).select_from(Job).where(*filters)).scalar_one()

    stmt = select(Job).where(*filters).order_by(Job.id)
    if cursor is not None:
        stmt = stmt.where(Job.id > cursor)
    rows = session.execute(stmt.limit(limit + 1)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    return JobListResponse(
        jobs=[JobRead.model_validate(j) for j in rows],
        next_cursor=rows[-1].id if has_more else None,
        total=total,
    )


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: int,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    return job


@router.post("/{job_id}/actions", response_model=JobRead)
def job_action(
    job_id: int,
    payload: JobAction,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        service.transition(job, payload.action)
    except service.InvalidTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(job)
    return job


@router.post("/{job_id}/state", response_model=JobRead)
def set_job_state(
    job_id: int,
    payload: JobStateUpdate,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> Job:
    """Worker-driven pipeline transition (e.g. running -> ready_for_review)."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        service.set_state(job, payload.state)
    except service.InvalidTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(job)
    return job
