# Roadmap: from "apply-app" to a full job-search platform

This extends `docs/PLAN.md` (the apply-app build plan, which is done) into the multi-service vision:
intake → match → rank → tailor resume → prime the application → review → approve/edit → submit. The
automation core (apply-app) already exists; this document designs the intelligence + UI layer around it.

> Status: **draft for review**. The apply-app core (steps 0–9) is built and live. Everything here is
> the *next* layer. Local Ollama (`qwen38-q3-64k`) is the only model; no external model calls.

---

## 1. Principles (carried from the plan)

1. The agent **never** submits. Submission is always a human action (manual click via KasmVNC, or a
   human "mark submitted").
2. No endpoint/MCP tool returns a password; the vault never reaches the model; page/email/log content
   is untrusted data.
3. Profile/resume are **admin-only**; per-job answer edits are the only thing reachable via MCP.
4. Small, human-maintainable files; pure logic separated from I/O; every new service is testable in
   the sandbox before Pi verification.
5. Pin dependencies, telemetry off. Ollama is the only model.

## 2. Service boundaries

| Service | Responsibility | Status |
| --- | --- | --- |
| `job-app` | Job-intake source (read-only JSON API) | exists (external) |
| `apply-app` | The automation: queue → fill → park → review. Owns the application lifecycle + profile + adapters + error queue | **built** |
| `matcher` (new) | Polls job-app, scores each job vs the profile with Ollama, stores candidates (ranked) | new |
| `resume` (new) | Tailors the base resume per job with Ollama, versions them | new |
| `ui` (new) | Ranked candidates → job detail + tailored resume + primed form → approve / edit / submit | new |
| `mcp` | The AI assistant's control plane over apply-app (ops tools) | **built** |
| Ollama | The shared model (matching, resume, agent fill, self-healing) | exists |

**Boundary rule:** apply-app stays *dumb automation* — it fills and parks, never ranks or writes
prose. Intelligence (matching, resume writing) lives in `matcher`/`resume`, which *feed* apply-app.
The only contract between them is: *a job listing in → a primed application out.*

## 3. Data model & ownership

| Entity | Owner | Notes |
| --- | --- | --- |
| **Profile** | apply-app | contact + resume (done) **+ `requirements` + `experience` JSON (new)** — the matcher's criteria |
| **Candidate** | matcher | `{job_app_id, listing snapshot, score, rationale, status}`. status: new → shortlisted → applied → rejected |
| **ResumeVersion** | resume | `{job_app_id, base_ref, tailored_text, created_at}` |
| **Job** (application) | apply-app | already exists; add `candidate_id` + `resume_version` (resume_version already exists) |
| **SuggestedFix** | apply-app | `{job_id, error_code, proposed_change, status}`. status: proposed → approved → applied/rejected |

**Single source of truth:** job listings = job-app; scores = matcher; resume versions = resume;
application state = apply-app. The UI is an aggregator (read-only across all four) plus the
approve/edit/submit actions on apply-app.

## 4. End-to-end flow

```
job-app (GET /api/jobs)
   → matcher: dedup → score each vs profile (Ollama) → Candidate{score, rationale}
   → ui: ranked list
   → user picks one
   → resume: tailor base resume → ResumeVersion
   → ui: "apply" → apply-app POST /jobs {listing, resume_version, candidate_id}
   → apply-app: worker fills (profile + tailored resume) → parks (submit guard) → ready_for_review
   → ui: review (field diff + artifacts + KasmVNC) → approve / edit-answer / restage
   → user submits manually (KasmVNC) → mark submitted
```

Failures anywhere → `Job.error_code` + reasoning (step events) → `needs_human` → self-healing loop (§8).

## 5. Key decisions (explicit, so the reviewer can attack them)

1. **Scores live in the matcher, not apply-app.** apply-app only knows "this job is queued." This
   keeps ranking/experimentation out of the automation core. Trade-off: two stores to query for the UI.
2. **The profile is the single matching-criteria source**, extended with `requirements`
   (title/remote/salary/location/seniority) and `experience` (skills/years/current role) as JSON in
   apply-app. The matcher reads it (diagnose scope) — no separate profile store.
3. **Resume versions are append-only** and keyed by `job_app_id`. A tailored resume is never the base
   resume; the base stays immutable. apply-app's `uploads` volume holds the rendered file.
4. **The UI's "submit" opens KasmVNC**, it does *not* submit. Rule 1 is absolute; the human does the
   final click watching the live browser. (Option to revisit: a single, explicit, non-agent "submit
   now" button that a human confirms — but never implicit.)
5. **Self-healing is human-gated.** Ollama *proposes* adapter fixes into a `SuggestedFix` queue; a
   human approves via UI/MCP; only then is the adapter updated + the job retried. No auto-apply.
6. **One model, shared, with explicit budget.** Matching/resume/fill all hit Ollama. The matcher
   batches + caches; a "budget" cap prevents a 200-job match from starving the worker's browser agent.

## 6. The matcher (design sketch)

- Polls job-app, dedupes by a stable id, snapshots the listing (title/company/description/location).
- Builds a scoring prompt: profile.requirements + experience vs the listing → JSON
  `{score: 0..100, rationale: str, must_have_hits: [], dealbreakers: []}`.
- Stores `Candidate`. Caches scores (don't re-score on every poll). A "sync" re-scores only new/updated.
- Exposes a read API for the UI: `GET /candidates?sort=score` + `POST /candidates/{id}/shortlist`.

## 7. The resume tailor

- Input: base resume (from apply-app profile) + the job listing + the matcher's rationale.
- Output: a tailored resume (rewrite highlights to match the listing; do **not** invent facts).
- Stored as `ResumeVersion`. Renders to a file in apply-app's uploads volume; the job references it by
  version. `resume_version` on Job already exists for this.

## 8. The self-healing loop

```
Job fails (selector_missing, postcondition_failed, …)
   → apply-app already records error_code + step events (reasoning)
   → a "proposer" (Ollama) looks at the failure + the page snapshot + the adapter
   → writes SuggestedFix {proposed_change, confidence}
   → human reviews (UI/MCP: "3 jobs failed, 2 proposed fixes")
   → approve → adapter patched (small file) → job retried
   → reject → recorded as rejected (so it isn't re-proposed)
```

This is the "self-improving adapter library" — driven by real failures, gated by a human.

## 9. "As many sites as possible"

Three tiers, already designed in the plan:
1. **First-class adapters** (Greenhouse, Lever, Ashby, Workday, iCIMS, Taleo, SmartRecruiters,
   Pinpoint) — human-maintained field selectors per ATS. Covers the ~80% long tail's head.
2. **Generic agent** — label-based fill for anything else.
3. **Workflow replay** — record a successful fill per site, truncate before submit, replay it.
Plus the submit guard + park-for-review everywhere. The self-healing loop grows tier 1 from real
failures. Realistic ceiling: top ~8 platforms well, long tail best-effort.

## 10. Security invariants (unchanged, extended)

- Never submit (agent). No password via endpoint/MCP. Vault never reaches the model.
- Profile/resume are admin-only; MCP can never read or write them.
- The matcher/resume run with **read-only** access to the profile + no token/password access.
- The UI is human-only, behind basic-auth/SSO + access list; KasmVNC keeps its token gate.
- All services reachable only via the docker bridge (`172.17.0.1`) or the internal backend network;
  nothing new is exposed on the LAN.

## 11. Phased milestones (acceptance criteria)

| # | Milestone | Acceptance criteria |
| --- | --- | --- |
| M1 | Profile enrichment | `requirements` + `experience` JSON on the profile, admin-only; worker still fills contact/resume |
| M2 | Matcher | matcher scores ≥1 mock job from a mock job-app feed; candidates ranked + rationale stored; unit-tested scoring parser |
| M3 | Resume tailor | tailors a base resume for a mock job; version stored; "no invented facts" check; unit-tested |
| M4 | Real field diff | worker reads back the actually-filled values + confidence/flags (replaces canned summary) |
| M5 | Listing/review UI | ranked list → detail → primed form + tailored resume → approve/edit/restage; submit opens KasmVNC |
| M6 | Adapters + real test | 2–3 adapters (Greenhouse/Lever/…); one supervised real application, never submitting |
| M7 | Self-healing loop | a failed job produces a SuggestedFix; approve patches the adapter; retry succeeds |

Each milestone: sandbox tests pass first, then Pi-verified, then recorded in PLAN.md's verification log.

## 12. Open questions / risks (to resolve in review)

1. job-app's exact API shape + whether it has `application_url` (the plan assumed it does).
2. Matcher freshness: a job applied/skipped in apply-app vs still "new" in the matcher — sync policy.
3. Model contention: matching 100 jobs vs a live fill — need a shared queue/budget on Ollama.
4. Score calibration: how do we know the scores are good without a labeled set? (start with
   user-curated shortlist feedback.)
5. Resume "no invented facts" enforcement — is a prompt rule enough, or do we need a diff/check step?
6. Where the UI lives (new service vs a static front-end served by one of the existing hosts).
