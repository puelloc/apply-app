"""Review endpoints: field diff, approve, the worker writing the fill summary, and the review link."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_session
from ..models import Job
from ..review_link import generate_token
from ..schemas.job import JobRead
from ..schemas.review import FillSummaryWrite, ReviewResponse
from ..security import require_scope

router = APIRouter(tags=["review"])


@router.get("/jobs/{job_id}/review", response_model=ReviewResponse)
def review(
    job_id: int,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> ReviewResponse:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    return ReviewResponse(job=job, ready_to_approve=job.state == "ready_for_review" and not job.approved)


@router.post("/jobs/{job_id}/fill-summary", response_model=JobRead)
def write_fill_summary(
    job_id: int,
    payload: FillSummaryWrite,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    job.fill_summary = payload.fill_summary
    session.commit()
    session.refresh(job)
    return job


@router.post("/jobs/{job_id}/approve", response_model=JobRead)
def approve(
    job_id: int,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.state != "ready_for_review":
        raise HTTPException(status_code=400, detail=f"cannot approve from state {job.state!r}")
    job.approved = True
    session.commit()
    session.refresh(job)
    return job


@router.get("/jobs/{job_id}/review-link")
def review_link(
    job_id: int,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> dict:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.state != "ready_for_review":
        raise HTTPException(status_code=400, detail=f"no review link for state {job.state!r}")
    token, expiry = generate_token(job_id)
    return {"url": f"https://jobs-review.siggy-lab.org/?token={token}", "expires_at": expiry}
