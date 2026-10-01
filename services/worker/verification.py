"""Extract the verification link from a verification email body."""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")

# Trailing punctuation that a URL regex can accidentally include.
_TRAILING = set(".,;:)!?]")


def find_verification_url(body: str) -> str | None:
    """Return the first http(s) URL in `body` (the verification link), or None."""
    match = _URL_RE.search(body)
    if not match:
        return None
    url = match.group(0)
    while url and url[-1] in _TRAILING:
        url = url[:-1]
    return url
