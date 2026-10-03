"""Profile endpoint: single-user contact + resume (admin write, diagnose read)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_session
from ..models import Profile
from ..schemas.profile import ProfileRead, ProfileUpdate
from ..security import require_scope

router = APIRouter(tags=["profile"])

_PROFILE_ID = 1


@router.get("/profile", response_model=ProfileRead)
def get_profile(
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> Profile:
    profile = session.get(Profile, _PROFILE_ID)
    if profile is None:
        raise HTTPException(status_code=404, detail="not_found")
    return profile


@router.put("/profile", response_model=ProfileRead)
def put_profile(
    payload: ProfileUpdate,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("admin")),
) -> Profile:
    profile = session.get(Profile, _PROFILE_ID)
    if profile is None:
        profile = Profile(id=_PROFILE_ID, **payload.model_dump())
        session.add(profile)
    else:
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)
    session.commit()
    session.refresh(profile)
    return profile
