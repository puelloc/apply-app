"""Account endpoints (metadata only). The worker orchestrates signup/verify/reconcile and keeps the
password in the vault — the API never sees it."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_session
from ..models import Account
from ..schemas.account import AccountCreate, AccountRead
from ..security import require_scope

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountRead, status_code=201)
def create_account(
    payload: AccountCreate,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> Account:
    existing = session.execute(select(Account).where(Account.alias == payload.alias)).scalar_one_or_none()
    if existing is not None:
        return existing  # idempotent
    account = Account(alias=payload.alias, site=payload.site, state="pending")
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.get("", response_model=list[AccountRead])
def list_accounts(
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> list[Account]:
    return session.execute(select(Account).order_by(Account.id)).scalars().all()


@router.get("/{alias}", response_model=AccountRead)
def get_account(
    alias: str,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("diagnose")),
) -> Account:
    account = session.execute(select(Account).where(Account.alias == alias)).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="not_found")
    return account


@router.post("/{alias}/confirm", response_model=AccountRead)
def confirm_account(
    alias: str,
    session: Session = Depends(get_session),
    _scope: str = Depends(require_scope("ops")),
) -> Account:
    account = session.execute(select(Account).where(Account.alias == alias)).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="not_found")
    account.state = "confirmed"
    session.commit()
    session.refresh(account)
    return account
