"""Account flow: signup → verify → confirm/reconcile. Passwords stay in the vault.

`signup` creates a `pending` account (API) and stores the generated password in the vault (fsynced)
*before* the browser fills the form. `verify` polls for the verification link (the poll function is
injected so it's testable without IMAP). `reconcile` decides signup / login_or_reset / login.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable

from aliases import alias_for, token_for


def generate_password() -> str:
    return secrets.token_urlsafe(18)


def signup(api, vault, job_id: int, base_email: str, site: str) -> dict:
    """Begin signup: create the `pending` account + store the password in the vault."""
    alias = alias_for(base_email, token_for(job_id))
    password = generate_password()
    api.create_account(alias, site)  # pending (idempotent)
    vault.put(alias, password)       # encrypted + fsynced BEFORE the browser fills
    return {"alias": alias, "password": password}


def verify(poll_fn: Callable[[str], str | None], alias: str, timeout_s: float = 120.0, interval_s: float = 5.0) -> str | None:
    """Poll `poll_fn(alias)` until the verification URL arrives or the timeout elapses."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        url = poll_fn(alias)
        if url:
            return url
        time.sleep(interval_s)
    return None


def confirm(api, alias: str) -> None:
    api.confirm_account(alias)


def reconcile(api, alias: str) -> str:
    """Decide the reconcile action for an alias (the login/reset itself is the browser's job)."""
    account = api.get_account(alias)
    if account is None:
        return "signup"
    return "login_or_reset" if account.get("state") == "pending" else "login"
