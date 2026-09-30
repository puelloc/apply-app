"""Serve the mock ATS fixtures and record every POST (a submit/signup) for the S tests.

S1 (canary) needs to confirm the signup reached here; S2 (submit guard) needs to confirm ZERO
POSTs arrive. Both read `submissions.log`.

Usage:  python3 server.py [port]      # default 8000
"""

from __future__ import annotations

import http.server
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LOG_FILE = Path(__file__).resolve().parent / "submissions.log"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(FIXTURES), **kwargs)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", "replace")
        line = f"{self.command} {self.path} {body}\n"
        sys.stdout.write(line)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"recorded\n")

    def log_message(self, fmt, *args) -> None:
        sys.stdout.write("REQ %s\n" % (fmt % args))


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler) as server:
        sys.stdout.write(f"mock-ats serving {FIXTURES} on :{port}\n")
        server.serve_forever()


if __name__ == "__main__":
    main()
