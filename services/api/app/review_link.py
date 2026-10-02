"""Short-lived review-link tokens (signed with a server secret; no storage needed).

The review UI / KasmVNC verifies the token (step 9 NPM auth_request). A token embeds `job_id.expiry`
and an HMAC signature; it expires on its own.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from pathlib import Path

_DEFAULT_SECRET = b"dev-review-link-secret"


def _secret() -> bytes:
    env = os.environ.get("REVIEW_LINK_SECRET")
    if env:
        return env.encode()
    path = Path("/run/secrets/review_link_secret")
    if path.is_file():
        return path.read_text().strip().encode()
    return _DEFAULT_SECRET


def generate_token(job_id: int, ttl_s: int = 3600) -> tuple[str, int]:
    """Return (token, expiry_epoch)."""
    expiry = int(time.time()) + ttl_s
    msg = f"{job_id}.{expiry}".encode()
    sig = hmac.new(_secret(), msg, hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(f"{job_id}.{expiry}.{sig}".encode()).decode()
    return token, expiry


def verify_token(token: str) -> int | None:
    """Return the job_id if the token is valid and unexpired, else None."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        job_id, expiry, sig = raw.split(".")
        expected = hmac.new(_secret(), f"{job_id}.{expiry}".encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        if int(expiry) < time.time():
            return None
        return int(job_id)
    except Exception:
        return None
