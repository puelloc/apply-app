# egress-proxy

The browser's **only route out**. A minimal forward proxy (HTTP + HTTPS CONNECT) that refuses
private/reserved destinations, defends against DNS rebinding, and enforces a domain allowlist.

## Files

| File | Purpose |
| --- | --- |
| `policy.py` | Pure policy: `is_public`, `resolve`, `Allowlist`, `check` (unit-testable, no I/O) |
| `proxy.py` | The asyncio proxy server (`EgressProxy`) — HTTP + CONNECT handlers, byte relay |
| `main.py` | Entrypoint: reads env config, starts the server |
| `test_policy.py` | Unit tests for the policy (stdlib `unittest`) |
| `Dockerfile` | `python:3.12-slim`, non-root, port 3128 |

## Security rules (in `policy.check`, applied in order)

1. **Private-range denial** — a connection to any private/loopback/link-local/reserved IP is refused.
   This is what keeps the browser off Ollama, the API, the DB, and the LAN.
2. **DNS-rebinding defense** — *every* resolved IP is checked; the caller connects to a *returned*
   IP and never re-resolves the hostname.
3. **Domain allowlist** — when `EGRESS_ALLOWLIST` is set, only those domains (and subdomains) are
   allowed.

## Configuration (env)

| Var | Default | Meaning |
| --- | --- | --- |
| `EGRESS_HOST` | `0.0.0.0` | Bind address |
| `EGRESS_PORT` | `3128` | Listen port |
| `EGRESS_ALLOWLIST` | *(empty = allow all public)* | Comma-separated domain suffixes, e.g. `greenhouse.io,lever.co,ashbyhq.com` |

## Test

```bash
python3 -m unittest test_policy -v
```

## Run

```bash
python3 main.py
```

Point a browser at it with `--proxy-server=http://<proxy>:3128` (the browser service does this in
compose). In the compose stack it sits on `browser_net` (internal) + `egress` (its only route out).
