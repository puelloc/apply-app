"""Scoped bearer-token auth.

Tokens are hash-stored (sha256); the API only ever holds the hash, never the plaintext. Scopes are
ordered: diagnose (read-only) < ops < admin. Token hashes come from env (`TOKEN_HASH_<SCOPE>`) or
Docker secrets (`/run/secrets/api_<scope>_token_hash`).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from fastapi import Header, HTTPException, Request

SCOPES = ("admin", "ops", "diagnose")
_SCOPE_LEVEL = {"diagnose": 1, "ops": 2, "admin": 3}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def has_scope(granted: str, required: str) -> bool:
    return _SCOPE_LEVEL.get(granted, 0) >= _SCOPE_LEVEL[required]


def load_token_hashes() -> dict[str, str]:
    """Return {scope: sha256-hex} from env vars, falling back to Docker secret files."""
    hashes: dict[str, str] = {}
    for scope in SCOPES:
        value = os.environ.get(f"TOKEN_HASH_{scope.upper()}")
        if not value:
            path = Path(f"/run/secrets/api_{scope}_token_hash")
            if path.is_file():
                value = path.read_text().strip()
        if value:
            hashes[scope] = value
    return hashes


def require_scope(required: str):
    """FastAPI dependency: authenticate the bearer token and require at least `required` scope."""

    def dependency(request: Request, authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="unauthorized")
        digest = hash_token(authorization[7:].strip())
        granted = next(
            (scope for scope, stored in request.app.state.token_hashes.items()
             if hmac.compare_digest(digest, stored)),
            None,
        )
        if granted is None:
            raise HTTPException(status_code=401, detail="unauthorized")
        if not has_scope(granted, required):
            raise HTTPException(status_code=403, detail="insufficient_scope")
        return granted

    return dependency
