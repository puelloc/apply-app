"""Step-event endpoints: the worker writes agent reasoning here; diagnostics reads it back."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_session
from ..models import Job, StepEvent
from ..schemas.event import StepEventCreate, StepEventRead
from ..security import require_scope

router = APIRouter(tags=["events"])


@router.post("/jobs/{job_id}/step-events", status_code=201)
def create_step_event(
    job_id: int,
    payload: StepEventCreate,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> dict:
    if session.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="not_found")
    event = StepEvent(job_id=job_id, **payload.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    return {"id": event.id}


@router.get("/jobs/{job_id}/step-events", response_model=list[StepEventRead])
def list_step_events(
    job_id: int,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> list[StepEvent]:
    return session.execute(
        select(StepEvent).where(StepEvent.job_id == job_id).order_by(StepEvent.id)
    ).scalars().all()
