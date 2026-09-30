#!/usr/bin/env python3
"""Local test for the CDP relay's WebSocket tunnel: 101 handshake forwarding + bidirectional bytes."""
import os
import socket
import subprocess
import sys
import threading
import time

TARGET_PORT = 9331
RELAY_PORT = 9332


def echo_server() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", TARGET_PORT))
    srv.listen(5)

    def handle(conn: socket.socket) -> None:
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                data += conn.recv(4096)
            conn.sendall(
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: dummy==\r\n\r\n"
            )
            while True:
                d = conn.recv(65536)
                if not d:
                    break
                conn.sendall(d)
        except Exception:
            pass
        finally:
            conn.close()

    def accept_loop() -> None:
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()


def main() -> None:
    echo_server()
    env = {**os.environ,
           "CDP_RELAY_PORT": str(RELAY_PORT),
           "CDP_TARGET_PORT": str(TARGET_PORT),
           "CDP_EXTERNAL_HOST": f"localhost:{RELAY_PORT}"}
    relay = subprocess.Popen([sys.executable, "cdp_relay.py"], env=env,
                             cwd=os.path.dirname(os.path.abspath(__file__)))
    time.sleep(1)
    try:
        s = socket.create_connection(("127.0.0.1", RELAY_PORT), timeout=5)
        s.sendall(
            b"GET /devtools/browser/abc HTTP/1.1\r\n"
            b"Host: localhost:9332\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            b"Sec-WebSocket-Key: x\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        resp = s.recv(4096)
        assert b"101" in resp, resp
        s.sendall(b"hello-relay")
        s.settimeout(5)
        echo = s.recv(1024)
        assert echo == b"hello-relay", echo
        print("WS tunnel: PASS (101 + bidirectional echo)")
    except Exception as e:
        print("WS tunnel: FAIL", type(e).__name__, e)
        sys.exit(1)
    finally:
        relay.terminate()


if __name__ == "__main__":
    main()
