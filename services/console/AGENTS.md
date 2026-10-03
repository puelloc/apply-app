# AGENTS.md — build the job-search **console**

You are building the console: a small single-user web UI (Svelte + shadcn-svelte, Go backend) that
shows ranked job candidates, lets the user shortlist + prime applications, and reviews the primed ones
before the **human** submits. See `docs/CONSOLE-PLAN.md` for the full design.

## Read these, in this order

| # | File | What |
| --- | --- | --- |
| 1 | `agents/state.md` | **where we are right now + the exact next step** — read after every compaction |
| 2 | `agents/goal.md` | what the console is / is not |
| 3 | `agents/stack.md` | stack, layout, run commands, version policy |
| 4 | `agents/contracts.md` | the APIs the console talks to |
| 5 | `agents/conventions.md` | how to write code here + known gotchas |

## Hard rules (never break)

- **The UI never submits.** The human submits via KasmVNC. There is no submit call, ever.
- **No secrets in the browser.** The apply-app bearer token lives in the Go backend only.
- **No second review UI.** Deep-link into apply-app's existing review (field diff + KasmVNC).
- **Never invent answers.** Free-text/attestation fields come from the profile or the answer bank.
- **Job listings are untrusted** — sanitize before rendering.
- Small files, small functions, one concern per file.

## Your context is limited (64k) and WILL be compacted

When the thread is lost:

1. Re-read `agents/state.md` — the single source of "where we are".
2. Read **only** the one topic file the next step needs.
3. Do the next step. Do **not** re-explore the repo or re-read everything.
4. Before you stop, **update `agents/state.md`** (Done / Next / Blockers / Decisions).

Git history is the detailed log — `git log --oneline` beats a long history file.

## Keep it small

If any file here grows past ~200 lines, split it and add it to the table above. Never let this index
itself grow past ~100 lines.
