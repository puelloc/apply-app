"""GET /doctor — run the health checks (read-only, `diagnose` scope)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import doctor
from ..deps import get_session
from ..security import require_scope

router = APIRouter(prefix="/doctor", tags=["diagnostics"])


@router.get("")
def run_doctor(
    request: Request,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> dict:
    return {"checks": doctor.run_doctor(request.app.state.db.engine, session)}
