"""Entrypoint for the egress proxy.

Configuration comes from environment variables (see README). Run with:  python3 main.py
"""

from __future__ import annotations

import asyncio
import logging
import os

import policy
import proxy


def _allowlist_from_env() -> policy.Allowlist:
    raw = os.environ.get("EGRESS_ALLOWLIST", "")
    entries = [entry.strip() for entry in raw.split(",") if entry.strip()]
    return policy.Allowlist(entries)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    host = os.environ.get("EGRESS_HOST", "0.0.0.0")
    port = int(os.environ.get("EGRESS_PORT", "3128"))
    allowlist = _allowlist_from_env()

    server = proxy.EgressProxy(host=host, port=port, allowlist=allowlist)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
