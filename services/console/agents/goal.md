# Goal

## What the console is

A single-user web UI over the job-search pipeline:

1. **Candidate list** — jobs that fit my requirements, ranked.
2. **Job detail** — the listing + a tailored resume + a "prime application" action.
3. **Review inbox** — jobs already primed (apply-app `ready_for_review`), each with the field diff,
   a KasmVNC link, and approve/edit actions.
4. **Answers** — the answer bank + a "needs input" queue for unknown required questions.

**End goal:** open the UI → see 10–20 applications that fit and are ready to review & submit.

## What the console is NOT

- Not the automation — apply-app fills/parks; it does not rank or write prose.
- Not a second review UI — deep-link into apply-app's.
- Not a submitter — human-only submit.
- Not an LLM host — it calls Ollama; the model lives elsewhere.

## Service split

| Service | Owns |
| --- | --- |
| `job-app` | job listings (read-only intake) |
| `apply-app` | the application lifecycle, profile, adapters, error queue, review UI |
| `console` (this) | triage (new/shortlisted/dismissed), resume versions, the UI |
| `mcp` | the AI assistant's control plane |
| Ollama | the shared model |

Full design + rationale: `docs/ROADMAP.md`.
