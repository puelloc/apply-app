"""Account-path orchestration: signup → verify (IMAP) → confirm → apply.

Pure/testable: the browser steps (`run_agent`, `fill_and_park`) and the IMAP poll are injected, so
the sequence can be tested without browser-use or a real mailbox. `pipeline.py` supplies the real
browser steps.
"""

from __future__ import annotations

import os

from account_flow import confirm, signup, verify


def imap_poll_fn():
    """Build the IMAP poll from env (real IMAP is SSL 993; the mock is plaintext)."""
    from imap import poll

    host = os.environ.get("IMAP_HOST", "127.0.0.1")
    port = int(os.environ.get("IMAP_PORT", "993"))
    user = os.environ.get("IMAP_USER", "")
    password = os.environ.get("IMAP_PASS", "")
    ssl = os.environ.get("IMAP_SSL", "true").lower() == "true"
    return lambda alias: poll(host, user, password, alias, port=port, ssl=ssl)


def _signup_task(signup_url: str, alias: str, password: str) -> str:
    return (
        f"Open the signup form at {signup_url}. Fill name CANARY, email {alias}, password {password}. "
        "Then STOP. Do NOT click submit."
    )


def _verify_task(url: str) -> str:
    return f"Open {url}. Confirm the verification succeeded, then STOP."


async def run_account_flow(api, vault, job, llm, run_agent, fill_and_park, poll_fn=None) -> None:
    """Signup → verify → confirm → apply. `run_agent(task, adapter)` and `fill_and_park()` are async."""
    base_email = os.environ.get("BASE_EMAIL")
    if not base_email:
        raise RuntimeError("BASE_EMAIL required for account-required jobs")
    adapter = job.get("ats") or "unknown"

    # 1. signup: pending account + password fsynced to the vault.
    info = signup(api, vault, job["id"], base_email, adapter)

    # 2. fill the signup form.
    signup_url = os.environ.get("SIGNUP_URL") or (job.get("application_url") or job.get("listing_url"))
    await run_agent(_signup_task(signup_url, info["alias"], info["password"]), adapter)

    # 3. verify (only when the site requires email verification).
    if job.get("requires_verification", True):
        api.set_state(job["id"], "awaiting_email")
        if poll_fn is None:
            poll_fn = imap_poll_fn()
        url = verify(poll_fn, info["alias"], timeout_s=float(os.environ.get("IMAP_TIMEOUT", "300")))
        if not url:
            api.set_state(job["id"], "failed")
            return
        await run_agent(_verify_task(url), adapter)

    # confirmed either way: after the verify click, or right after signup when no verification.
    confirm(api, info["alias"])

    # 4. account is ready; fill the application form -> park.
    api.set_state(job["id"], "account_created")
    await fill_and_park()
