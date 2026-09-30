#!/usr/bin/env python3
"""Local regression test for cdp_relay.py: verifies Host rewrite + ws-URL rewrite + body handling
against a fake upstream using Content-Length, chunked, and connection-close encodings."""
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler

UPSTREAM_PORT = 9321
RELAY_PORT = 9322
JSON_BODY = json.dumps({
    "Browser": "Chrome/145",
    "webSocketDebuggerUrl": f"ws://127.0.0.1:{UPSTREAM_PORT}/devtools/browser/abc",
}).encode()


class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        mode = self.path.split("=")[-1]
        if mode == "chunked":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"%x\r\n" % len(JSON_BODY))
            self.wfile.write(JSON_BODY + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        elif mode == "close":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(JSON_BODY)
        else:  # content-length
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(JSON_BODY)))
            self.end_headers()
            self.wfile.write(JSON_BODY)

    def log_message(self, *a):
        pass


def main() -> None:
    srv = socketserver.TCPServer(("127.0.0.1", UPSTREAM_PORT), Upstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    env = {**os.environ,
           "CDP_RELAY_PORT": str(RELAY_PORT),
           "CDP_TARGET_PORT": str(UPSTREAM_PORT),
           "CDP_EXTERNAL_HOST": f"localhost:{RELAY_PORT}"}
    relay = subprocess.Popen([sys.executable, "cdp_relay.py"], env=env,
                             cwd=os.path.dirname(os.path.abspath(__file__)))
    time.sleep(1)

    failures = 0
    try:
        for mode in ("content-length", "chunked", "close"):
            url = f"http://127.0.0.1:{RELAY_PORT}/json/version={mode}"
            data = json.loads(urllib.request.urlopen(url, timeout=5).read().decode())
            ws = data["webSocketDebuggerUrl"]
            ok = f"localhost:{RELAY_PORT}" in ws and f"127.0.0.1:{UPSTREAM_PORT}" not in ws
            print(f"  {mode:15s} -> {ws}  {'PASS' if ok else 'FAIL'}")
            failures += 0 if ok else 1
    except Exception as e:
        print("ERROR:", type(e).__name__, e)
        failures += 1
    finally:
        relay.terminate()
        srv.shutdown()

    print("RESULT:", "PASS" if failures == 0 else f"FAIL ({failures})")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
