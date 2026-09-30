"""A minimal forward proxy (HTTP + HTTPS CONNECT) that enforces the egress policy.

The browser is configured to use this as its only proxy. Every request is checked by `policy.check`
before any bytes reach the target; domains are logged for the audit trail.

Design notes (kept deliberately small):
- CONNECT is a dumb byte tunnel once the policy check passes.
- HTTP is handled by parsing the absolute-form request line and forwarding in origin-form.
- The upstream connection always uses a *verified* IP (from `policy.check`), never a re-resolution,
  which closes the DNS-rebinding race.
"""

from __future__ import annotations

import asyncio
import logging

import policy

log = logging.getLogger("egress-proxy")

RELAY_CHUNK = 65536


class EgressProxy:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 3128,
        allowlist: policy.Allowlist | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.allowlist = allowlist

    async def run(self) -> None:
        server = await asyncio.start_server(self._handle_client, self.host, self.port)
        log.info("egress proxy listening on %s:%d", self.host, self.port)
        async with server:
            await server.serve_forever()

    # -- client handling ----------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            method, target, version = self._parse_request_line(line)
            if method is None:
                await self._reject(writer, "400 Bad Request", "malformed request line")
                return
            if method == "CONNECT":
                await self._handle_connect(reader, writer, target)
            else:
                await self._handle_http(reader, writer, method, target)
        except Exception:  # noqa: BLE001 — a client error must not kill the server
            log.exception("client error")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _parse_request_line(line: bytes) -> tuple[str | None, str, str]:
        parts = line.decode("latin-1").rstrip("\r\n").split(" ")
        if len(parts) != 3:
            return None, "", ""
        return parts[0].upper(), parts[1], parts[2]

    # -- CONNECT (HTTPS tunneling) -----------------------------------------

    async def _handle_connect(self, reader, writer, target: str) -> None:
        host, port = self._split_host_port(target, default_port=443)
        if host is None:
            await self._reject(writer, "400 Bad Request", "bad CONNECT target")
            return

        allowed, reason, ips = policy.check(host, port, self.allowlist)
        if not allowed:
            log.warning("deny CONNECT %s:%d — %s", host, port, reason)
            await self._reject(writer, "403 Forbidden", reason)
            return

        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(ips[0], port)
        except OSError as exc:
            log.warning("CONNECT %s:%d upstream failed: %s", host, port, exc)
            await self._reject(writer, "502 Bad Gateway", str(exc))
            return

        log.info("allow CONNECT %s:%d -> %s", host, port, ips[0])
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await self._relay(reader, writer, upstream_reader, upstream_writer)

    # -- HTTP (forward proxy) ----------------------------------------------

    async def _handle_http(self, reader, writer, method: str, target: str) -> None:
        if not target.startswith("http://"):
            await self._reject(writer, "400 Bad Request", "only absolute http:// URLs are proxied")
            return

        rest = target[len("http://"):]
        hostport, _, path = rest.partition("/")
        path = "/" + path if path else "/"
        host, port = self._split_host_port(hostport, default_port=80)
        if host is None:
            await self._reject(writer, "400 Bad Request", "missing host")
            return

        allowed, reason, ips = policy.check(host, port, self.allowlist)
        if not allowed:
            log.warning("deny %s http://%s — %s", method, host, reason)
            await self._reject(writer, "403 Forbidden", reason)
            return

        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(ips[0], port)
        except OSError as exc:
            log.warning("HTTP %s:%d upstream failed: %s", host, port, exc)
            await self._reject(writer, "502 Bad Gateway", str(exc))
            return

        log.info("allow %s http://%s%s", method, host, path)
        upstream_writer.write(f"{method} {path} HTTP/1.1\r\n".encode("latin-1"))
        await self._forward_headers(reader, upstream_writer, host, port)
        await upstream_writer.drain()
        await self._relay(reader, writer, upstream_reader, upstream_writer)

    async def _forward_headers(self, reader, upstream_writer, host: str, port: int) -> None:
        """Copy client headers until the blank line, ensuring a Host header is present."""
        saw_host = False
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            if line.lower().startswith(b"host:"):
                saw_host = True
            if line.lower().startswith(b"proxy-connection:"):
                continue  # hop-by-hop; drop it
            upstream_writer.write(line)
        if not saw_host:
            upstream_writer.write(f"Host: {host}:{port}\r\n".encode("latin-1"))
        upstream_writer.write(b"\r\n")

    # -- shared helpers -----------------------------------------------------

    @staticmethod
    def _split_host_port(hostport: str, default_port: int) -> tuple[str | None, int]:
        """Split 'host' or 'host:port'; return (None, _) when unparsable."""
        if ":" in hostport and not hostport.startswith("["):
            host, _, port_s = hostport.rpartition(":")
            if not host or not port_s.isdigit():
                return None, default_port
            return host, int(port_s)
        return hostport, default_port

    async def _relay(self, a_reader, a_writer, b_reader, b_writer) -> None:
        async def pipe(src, dst):
            try:
                while True:
                    data = await src.read(RELAY_CHUNK)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except (ConnectionError, OSError, asyncio.IncompleteReadError):
                pass
            finally:
                try:
                    dst.close()
                except Exception:  # noqa: BLE001
                    pass

        await asyncio.gather(pipe(a_reader, b_writer), pipe(b_reader, a_writer))

    @staticmethod
    async def _reject(writer, status: str, message: str) -> None:
        body = message.encode("utf-8")
        writer.write(
            f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n\r\n".encode("latin-1") + body
        )
        await writer.drain()
