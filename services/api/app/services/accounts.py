"""Two-phase account writes + the reconcile decision.

The password is written to the vault (encrypted + fsynced) BEFORE the account row is committed, so a
`pending` account always has its submitted string safely stored. The actual "login / password reset"
actions run in step 7; here we only decide which one.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account
from ..vault import Vault


def begin(session: Session, vault: Vault, alias: str, site: str, password: str) -> Account:
    account = Account(alias=alias, site=site, state="pending")
    session.add(account)
    session.flush()
    vault.put(alias, password)  # encrypted + fsynced before commit
    session.commit()
    return account


def confirm(session: Session, alias: str) -> Account:
    account = session.execute(select(Account).where(Account.alias == alias)).scalar_one_or_none()
    if account is None:
        raise KeyError(alias)
    account.state = "confirmed"
    session.commit()
    return account


def reconcile(session: Session, alias: str) -> str:
    """Decide the reconcile action for an alias (the action itself runs in step 7)."""
    account = session.execute(select(Account).where(Account.alias == alias)).scalar_one_or_none()
    if account is None:
        return "signup"
    return "login_or_reset" if account.state == "pending" else "login"
