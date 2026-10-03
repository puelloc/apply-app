# Conventions & gotchas

## Code

- Small files, small functions, one concern per file. Split before ~200 lines.
- Pure logic separate from I/O (so it unit-tests without a server or DB).
- Go: table-driven tests; `internal/` for non-public packages.
- Svelte: pages in `web/src/routes/`, reusable pieces in `web/src/lib/components/`.
- Never put the apply-app token (or any secret) in the frontend.

## UI

- **Job listings are untrusted input** — render as text, sanitize any HTML. Never `{@html}` raw
  listing content.
- Error codes from apply-app are meaningful (`selector_missing`, `email_timeout`, …) — show them.
- "Approve" is not "submit". Label them differently; never imply the UI submits.

## Gotchas learned on this project

- The model is **text-only** (`use_vision=False`) — no screenshots; design for DOM/code, not images.
- The browser agent **cannot submit** (page-level submit guard). Don't add anything that fights it.
- Ports bind to the docker bridge `172.17.0.1`, not the LAN — if you add a service, follow suit.
- Nginx/NPM cannot resolve `host.docker.internal` at runtime; use literal IPs.
- Ollama is shared: long match/tailor batches must not starve the worker's browser agent.

## Working with the user's chat models

The user has stronger chat models with **no file access** (but they can browse GitHub). Workflow:
the user copy-pastes a section (plus the relevant file) to the chat, gets an answer, pastes it back.
So keep sections in these docs self-contained enough to copy in isolation.
