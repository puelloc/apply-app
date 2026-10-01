"""Plus-address aliases: one per job, routing into the catch-all inbox.

Each job signs up with `local+<token>@domain` so the verification email is identifiable by its
`To:` header. The token is job-derived for traceability (a random suffix can be added later for
privacy).
"""

from __future__ import annotations


def alias_for(base_email: str, token: str) -> str:
    """Insert a `+token` into the local part: `jobs@x.com` -> `jobs+token@x.com`."""
    local, sep, domain = base_email.partition("@")
    if not sep:
        raise ValueError(f"not an email address: {base_email!r}")
    return f"{local}+{token}@{domain}"


def token_for(job_id: int) -> str:
    return f"job{job_id}"
