# Console UI — high-level plan

The console is the human front-end for the job-search pipeline. This document is the starting point
for its design; the build-time agent guide lives in `services/console/AGENTS.md`.

> Status: **design seed**. Design it with a stronger chat model (see §7), then record decisions in
> `services/console/agents/state.md`.

## 1. The end state

Open the UI and get **10–20 applications that fit my requirements, already primed and ready to review
and submit**. Concretely:

```
ranked candidates (jobs that fit)  →  shortlist  →  prime (apply-app fills + parks)
        →  inbox of ready_for_review jobs  →  review each (diff + resume + KasmVNC)  →  human submits
```

## 2. Screens

| Screen | Route | Shows | Actions |
| --- | --- | --- | --- |
| **Candidates** | `/` | ranked list of matching jobs (bucket + evidence) | shortlist, dismiss, open |
| **Candidate detail** | `/candidate/:id` | listing + tailored resume + match rationale | "prime application" (enqueue) |
| **Inbox** | `/inbox` | jobs in `ready_for_review` | open review, approve, edit answer, restage |
| **Review** | `/inbox/:id` | field diff (value/confidence/provenance) + job + resume | approve, edit, **open KasmVNC** |
| **Answers** | `/answers` | answer bank + "needs input" queue | save an approved answer |

Notes:
- The **Review** screen deep-links to apply-app's existing review + KasmVNC — do not rebuild it.
- "Approve" ≠ "Submits". Label clearly; the submit click happens in KasmVNC by the human.

## 3. Architecture

```
Svelte SPA (browser)
   │  same-origin, no secrets
   ▼
Go console service  ── SQLite (candidates, resume versions, answer-bank cache)
   ├── apply-app API   (holds the bearer token; enqueue, review, approve, KasmVNC link)
   └── Ollama          (matcher scoring, resume tailoring — later phases)
```

- One container: the Go service serves the API **and** the built Svelte assets (embedded).
- The Go service is the only thing holding the apply-app token.
- In dev, the Svelte dev server proxies `/api` to Go.

## 4. Data

**Console SQLite** (console-owned):
- `candidates(id, source_system, source_id, title, company, url, listing_hash, bucket, evidence, status)`
  — status: `new | shortlisted | dismissed`.
- `resume_versions(id, candidate_id, base_hash, prompt_version, model, artifact_hash)` — exists only
  once resume tailoring lands.
- `answer_bank(question_pattern, answer, approved_at)` — may live in apply-app; decide in design.

**apply-app** (not console-owned): the application lifecycle, outcome, profile, adapters.

## 5. API surface

See `services/console/agents/contracts.md` for the exact endpoints. Design rule: the console API is a
thin layer over apply-app plus the console's own triage data — no business logic that belongs in
apply-app.

## 6. Phases

| Phase | Deliverable | Depends on |
| --- | --- | --- |
| **P1** | Scaffold (Go + Svelte + shadcn) + a candidate list from a seed fixture | — |
| **P2** | Candidate detail + "prime application" → apply-app `POST /jobs` | apply-app (built) |
| **P3** | Inbox + review screen (field diff + KasmVNC link) + approve/edit/restage | apply-app (built) |
| **P4** | Matcher data (real candidates) + resume tailoring + answer bank | console matcher/resume work |

Phase **P1–P3 deliver the user's end goal** on top of the already-built apply-app; P4 adds the
intelligence. Design P1–P3 first — they are what makes the inbox real.

## 7. Using the stronger chat models (design workflow)

The user's chat models have **no file access** but can browse GitHub. Use them like this:

1. **Design a screen**: paste this file's §2 + §3 + the relevant `agents/contracts.md` rows. Ask for a
   component breakdown, states, and edge cases.
2. **Verify a version/API**: ask the chat to check the current release of `svelte`, `shadcn-svelte`,
   `tailwind`, and the Go router on GitHub. Record the pinned versions in `agents/stack.md`.
3. **Generate a component**: paste only the contract rows + conventions it needs (keep it small).
4. Bring the result back to the local model; it writes the code and updates `agents/state.md`.

Keep each pasted block self-contained, because the chat has no repo access.

## 8. Out of scope (do not build)

- A submit button that submits.
- A second field-diff/review UI (apply-app has one).
- Ranking/resume logic in the frontend (that is the console backend's job).
- Any secret, token, or password in the browser.
- Direct access to the apply-app DB or the vault.

## 9. Open design questions

1. Does the answer bank live in apply-app or the console? (Affects the API surface.)
2. How is a candidate's tailored resume displayed — rendered preview, or a link to the artifact?
3. Auth for the console: reuse NPM basic-auth + access list, or a VPN? (Roadmap §12 leans VPN.)
4. Where does the console run — same Pi compose (new service) or its own stack?
5. Polling vs SSE/WebSocket for the inbox (parked jobs change state asynchronously).
