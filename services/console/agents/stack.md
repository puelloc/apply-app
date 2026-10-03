# Stack

- **Frontend:** Svelte 5 + shadcn-svelte + Tailwind, TypeScript.
- **Backend:** Go (net/http or chi), SQLite for the console's own data.
- **Model:** Ollama `qwen38-q3-64k:latest` at `https://ai.siggy-lab.org` (text-only, 64k ctx).
- **Packaging:** one container — the built Svelte assets embedded in the Go binary via `embed`.

## Version policy

Pin every version when you scaffold, and record it here. Versions are **not** guesses — the user's
chat model can check GitHub for the current releases. If unsure, write `TODO(version)` and ask.

```
svelte:            TODO(version)
shadcn-svelte:     TODO(version)
tailwind:          TODO(version)
go:                TODO(version)
chi (or stdlib):   TODO(version)
```

## Layout (target)

```
services/console/
  AGENTS.md            # you are here (the index)
  agents/              # the small topic files
  go.mod
  cmd/console/main.go  # entrypoint; serves the API + embedded assets
  internal/
    api/               # HTTP handlers for the console's own API
    store/             # SQLite (candidates, resume versions)
    applyapp/          # client for the apply-app API (holds the token)
    matcher/           # (later) scoring
  web/                 # Svelte app
    src/routes/        # pages
    src/lib/components/ # UI pieces
  web/build/           # Svelte build output, embedded by Go
```

## Commands

```bash
# backend
go run ./cmd/console            # dev server (API only)
go test ./...                   # tests

# frontend
cd web && npm install
npm run dev                     # dev server (proxies /api to the Go backend)
npm run build                   # emits web/build/ for embedding
```

## Rules of thumb

- Keep the Go backend thin: it holds the token + talks to apply-app; the Svelte app never sees the token.
- Pure logic (scoring parse, formatting) goes in its own package, no I/O — so it unit-tests fast.
- One concern per file; split before a file reaches ~200 lines.
