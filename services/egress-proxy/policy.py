"""Egress network policy for the browser's only route out.

This module is *pure* (DNS resolution is the only I/O, and it is injectable for tests) so the
security rules can be unit-tested without a network. Three rules, applied in order:

1. **Private-range denial** — a connection to any private, loopback, link-local, or reserved
   address is always refused. This is what keeps the browser off Ollama, the API, the DB, and the
   LAN.
2. **DNS-rebinding defense** — every resolved IP is checked (not just the first), and the caller
   must connect to a *returned* IP (never re-resolve the hostname).
3. **Domain allowlist** — when configured, only allowlisted hostnames are permitted.

Run the tests with:  python3 -m unittest test_policy -v
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable

# Address ranges that are never routable from inside the browser. (IPv4 and IPv6.)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),       # "this network"
    ipaddress.ip_network("10.0.0.0/8"),      # RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),   # carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),     # loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("172.16.0.0/12"),   # RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),    # reserved
    ipaddress.ip_network("192.0.2.0/24"),    # documentation (TEST-NET-1)
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),   # benchmarking
    ipaddress.ip_network("198.51.100.0/24"), # documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"),  # documentation (TEST-NET-3)
    ipaddress.ip_network("224.0.0.0/4"),     # multicast
    ipaddress.ip_network("240.0.0.0/4"),     # reserved
    ipaddress.ip_network("::/128"),          # unspecified
    ipaddress.ip_network("::1/128"),         # loopback
    ipaddress.ip_network("::ffff:0:0/96"),   # IPv4-mapped IPv6
    ipaddress.ip_network("100::/64"),        # discard
    ipaddress.ip_network("2001:db8::/32"),   # documentation
    ipaddress.ip_network("fc00::/7"),        # unique-local
    ipaddress.ip_network("fe80::/10"),       # link-local
    ipaddress.ip_network("ff00::/8"),        # multicast
]


def is_public(ip: str) -> bool:
    """Return True when `ip` is a public, globally routable address."""
    addr = ipaddress.ip_address(ip)
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped  # e.g. ::ffff:192.168.1.1 -> 192.168.1.1
    return all(addr not in network for network in BLOCKED_NETWORKS)


def resolve(host: str, port: int = 443) -> list[str]:
    """Resolve `host` to its unique IP strings (IPv4 + IPv6), sorted for determinism."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


class Allowlist:
    """Suffix-based domain allowlist. Empty means "allow every public host"."""

    def __init__(self, entries: list[str] | None = None) -> None:
        self._suffixes = {e.strip().lower().lstrip(".") for e in (entries or []) if e.strip()}

    def allows(self, host: str) -> bool:
        if not self._suffixes:
            return True
        candidate = host.lower().rstrip(".")
        if candidate in self._suffixes:
            return True
        return any(candidate.endswith("." + suffix) for suffix in self._suffixes)


# Resolver type: matches the signature of resolve().
Resolver = Callable[[str, int], list[str]]


def check(
    host: str,
    port: int,
    allowlist: Allowlist | None = None,
    resolver: Resolver = resolve,
) -> tuple[bool, str, list[str]]:
    """Decide whether a connection to `host:port` is allowed.

    Returns ``(allowed, reason, resolved_ips)``. The caller must connect to one of the returned IPs
    (never re-resolve the hostname) to avoid a DNS-rebinding race.
    """
    try:
        ips = resolver(host, port)
    except socket.gaierror as exc:
        return False, f"dns lookup failed: {exc}", []
    if not ips:
        return False, "dns returned no addresses", []

    for ip in ips:
        if not is_public(ip):
            return False, f"blocked {ip} (private/reserved)", ips

    if allowlist is not None and not allowlist.allows(host):
        return False, f"blocked {host} (not allowlisted)", ips

    return True, "", ips
