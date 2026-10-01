"""IMAP polling for a job's verification email.

`extract_verification_url_from_message` is pure (testable with a fake email message); `poll` is the
I/O wrapper (imaplib, stdlib). The worker polls the catch-all inbox for an email `To:` the job's
plus-address alias and returns its verification link.
"""

from __future__ import annotations

import email
import imaplib
from email.header import decode_header
from email.utils import getaddresses

from verification import find_verification_url


def _decode(value: str | None) -> str:
    parts = decode_header(value or "")
    out: list[str] = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", "replace"))
        else:
            out.append(text)
    return "".join(out)


def _to_addresses(message) -> set[str]:
    addrs: set[str] = set()
    for header in ("To", "Delivered-To", "Cc"):
        for name, addr in getaddresses([_decode(h) for h in message.get_all(header, [])]):
            if addr:
                addrs.add(addr.lower())
    return addrs


def _body_text(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode("utf-8", "replace")
        return ""
    return message.get_payload(decode=True).decode("utf-8", "replace")


def extract_verification_url_from_message(message, alias: str) -> str | None:
    if alias.lower() not in _to_addresses(message):
        return None
    return find_verification_url(_body_text(message))


def poll(host: str, user: str, password: str, alias: str, folder: str = "INBOX", timeout: int = 15) -> str | None:
    """Return the verification URL for `alias`, or None if no matching email has arrived yet."""
    conn = imaplib.IMAP4_SSL(host, timeout=timeout)
    try:
        conn.login(user, password)
        conn.select(folder)
        status, data = conn.search(None, "TO", f'"{alias}"')
        ids = data[0].split() if data and data[0] else []
        for i in reversed(ids):  # newest first
            status, msgdata = conn.fetch(i, "(RFC822)")
            raw = msgdata[0][1]
            url = extract_verification_url_from_message(email.message_from_bytes(raw), alias)
            if url:
                return url
        return None
    finally:
        try:
            conn.logout()
        except Exception:
            pass
