# State — update this at the end of EVERY work session

> This is the compaction-recovery anchor. Keep it short and current.

**Milestone:** P1 — scaffold + candidate list (see `docs/CONSOLE-PLAN.md` §6)
**Status:** not started

## Done
- (nothing yet)

## Next step
1. Scaffold the Go backend + Svelte/shadcn-svelte app per `agents/stack.md`.
2. Add a console SQLite table `candidates` (id, title, company, url, score, bucket, status).
3. Seed it from a JSON fixture (before the matcher exists).
4. Render a plain table at `/`.

## Blockers / open questions
- Mock candidate source before the matcher exists → use a seed JSON fixture for now.

## Decisions made
- (record each decision in one line here so it survives compaction)

## Recent (last ~5 steps)
- (append one line per completed step)
