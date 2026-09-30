#!/usr/bin/env python3
"""CDP relay: expose Chromium's loopback CDP so the worker can reach it over the browser_net.

Chrome 136+ binds CDP to 127.0.0.1, rejects non-localhost `Host` headers (HTTP 500), and reports
`webSocketDebuggerUrl` as `ws://127.0.0.1:…`. This relay:
  1. rewrites the request `Host` to 127.0.0.1 (so Chrome answers),
  2. rewrites `127.0.0.1:9221` -> the external address in the response body (so the worker
     reconnects through the relay),
  3. tunnels the CDP WebSocket after the upgrade.
Handles Content-Length, chunked, and connection-close response bodies.
"""

import asyncio
import os
import re

LISTEN = ("0.0.0.0", int(os.environ.get("CDP_RELAY_PORT", "9222")))
TARGET = ("127.0.0.1", int(os.environ.get("CDP_TARGET_PORT", "9221")))
EXTERNAL = os.environ.get("CDP_EXTERNAL_HOST", "browser:9222")


async def _read_head(reader: asyncio.StreamReader) -> bytes:
    return await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)


def _rewrite_request(head: bytes) -> bytes:
    text = head.decode("latin-1").rstrip("\r\n")
    lines = text.split("\r\n")
    out = [lines[0]]
    for line in lines[1:]:
        low = line.lower()
        if low.startswith("host:"):
            out.append(f"Host: {TARGET[0]}:{TARGET[1]}")
        elif low.startswith("origin:"):
            out.append("Origin: http://localhost")
        else:
            out.append(line)
    return ("\r\n".join(out) + "\r\n\r\n").encode("latin-1")


def _rewrite_body(body: bytes) -> bytes:
    body = body.replace(f"ws://{TARGET[0]}:{TARGET[1]}".encode(), f"ws://{EXTERNAL}".encode())
    return body.replace(f"{TARGET[0]}:{TARGET[1]}".encode(), EXTERNAL.encode())


async def _read_body(up_reader: asyncio.StreamReader, head_text: str) -> bytes:
    """Read the response body, handling Content-Length, chunked, and connection-close."""
    m = re.search(r"(?i)content-length:\s*(\d+)", head_text)
    if m:
        try:
            return await up_reader.readexactly(int(m.group(1)))
        except asyncio.IncompleteReadError as e:
            return e.partial
    if re.search(r"(?i)transfer-encoding:\s*chunked", head_text):
        body = bytearray()
        while True:
            line = await up_reader.readline()
            size = int(line.strip().split(b";")[0], 16)
            if size == 0:
                await up_reader.readline()  # trailing CRLF after the last chunk
                break
            body += await up_reader.readexactly(size)
            await up_reader.readexactly(2)  # CRLF after chunk data
        return bytes(body)
    return await up_reader.read()


async def _tunnel(client_reader, client_writer, up_reader, up_writer) -> None:
    async def pipe(src, dst) -> None:
        try:
            while True:
                data = await src.read(65536)
                if not data:
                    break
                dst.write(data)
                await dst.drain()
        except Exception:
            pass
        finally:
            try:
                dst.close()
            except Exception:
                pass

    await asyncio.gather(pipe(client_reader, up_writer), pipe(up_reader, client_writer))


async def _forward_response(reader, writer, up_reader, up_writer) -> None:
    head = await _read_head(up_reader)
    text = head.decode("latin-1")
    status_line = text.split("\r\n", 1)[0]

    if " 101 " in status_line:
        # WebSocket upgrade: no body — forward the 101 head, then tunnel bytes.
        writer.write(head)
        await writer.drain()
        await _tunnel(reader, writer, up_reader, up_writer)
        return

    body = _rewrite_body(await _read_body(up_reader, text))
    kept = [ln for ln in text.split("\r\n") if not re.match(r"(?i)(content-length|transfer-encoding):", ln)]
    new_head = "\r\n".join(kept).rstrip("\r\n") + f"\r\nContent-Length: {len(body)}\r\n\r\n"
    writer.write(new_head.encode("latin-1") + body)
    await writer.drain()
    writer.close()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    up_reader = up_writer = None
    try:
        head = await _read_head(reader)
        up_reader, up_writer = await asyncio.open_connection(TARGET[0], TARGET[1])
        up_writer.write(_rewrite_request(head))
        await up_writer.drain()
        await _forward_response(reader, writer, up_reader, up_writer)
    except Exception as exc:
        print(f"cdp-relay error: {type(exc).__name__}: {exc}", flush=True)
    finally:
        try:
            writer.close()
        except Exception:
            pass
        if up_writer is not None:
            try:
                up_writer.close()
            except Exception:
                pass


async def main() -> None:
    server = await asyncio.start_server(handle, LISTEN[0], LISTEN[1])
    print(f"cdp-relay {LISTEN[0]}:{LISTEN[1]} -> {TARGET[0]}:{TARGET[1]} (external={EXTERNAL})")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
