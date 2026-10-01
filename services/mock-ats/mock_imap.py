#!/usr/bin/env python3
"""Minimal mock IMAP server: serves ONE canned verification email to a given alias.

Used by the step-7 spike to test the account-verification flow without real IMAP credentials
(rule 7). Implements just the imaplib commands the worker's `imap.poll` uses: CAPABILITY, LOGIN,
SELECT, SEARCH, FETCH, LOGOUT.
"""

import os
import socketserver
from email.message import EmailMessage

PORT = int(os.environ.get("MOCK_IMAP_PORT", "9143"))
ALIAS = os.environ.get("MOCK_IMAP_ALIAS", "jobs+job1@example.invalid")
VERIFY_URL = os.environ.get("MOCK_VERIFY_URL", "http://mock-ats:8000/verify?token=canary1")


def canned_email() -> bytes:
    msg = EmailMessage()
    msg["To"] = ALIAS
    msg["From"] = "no-reply@acme.invalid"
    msg["Subject"] = "Verify your email"
    msg.set_content(f"Thanks for signing up. Click to verify: {VERIFY_URL}")
    return msg.as_bytes()


class Handler(socketserver.StreamRequestHandler):
    def _send(self, data: bytes) -> None:
        self.wfile.write(data)
        self.wfile.flush()

    def handle(self) -> None:
        self._send(b"* OK mock-imap ready\r\n")
        while True:
            line = self.rfile.readline()
            if not line:
                break
            parts = line.decode("utf-8", "replace").strip().split(" ", 2)
            if len(parts) < 2:
                continue
            tag, cmd = parts[0], parts[1].upper()
            if cmd == "CAPABILITY":
                self._send(b"* CAPABILITY IMAP4rev1\r\n")
                self._send(f"{tag} OK CAPABILITY completed\r\n".encode())
            elif cmd == "LOGIN":
                self._send(f"{tag} OK LOGIN completed\r\n".encode())
            elif cmd == "SELECT":
                self._send(b"* 1 EXISTS\r\n")
                self._send(f"{tag} OK [READ-WRITE] SELECT completed\r\n".encode())
            elif cmd == "SEARCH":
                self._send(b"* SEARCH 1\r\n")
                self._send(f"{tag} OK SEARCH completed\r\n".encode())
            elif cmd == "FETCH":
                body = canned_email()
                self._send(f"* 1 FETCH (RFC822 {{{len(body)}}}\r\n".encode())
                self._send(body)
                self._send(b")\r\n")
                self._send(f"{tag} OK FETCH completed\r\n".encode())
            elif cmd == "LOGOUT":
                self._send(b"* BYE logging out\r\n")
                self._send(f"{tag} OK LOGOUT completed\r\n".encode())
                break
            else:
                self._send(f"{tag} OK\r\n".encode())


def main() -> None:
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as server:
        print(f"mock-imap serving on :{PORT} (alias={ALIAS} url={VERIFY_URL})")
        server.serve_forever()


if __name__ == "__main__":
    main()
