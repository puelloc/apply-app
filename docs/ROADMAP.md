# Roadmap: from "apply-app" to a full job-search platform (revision 2)

This extends `docs/PLAN.md` (the apply-app build plan, done) into the multi-service vision:
intake → match → rank → tailor resume → prime the application → review → approve/edit → submit. The
automation core (apply-app) already exists; this designs the intelligence + UI layer around it.

> **Revision 2 — after design review.** Key changes from rev 1: matcher/resume/UI are **collapsed into
> one "console" service**; apply-app stays the **sole owner of application state**; the build order is
> re-cut into **vertical slices** with the real field diff and a supervised real run first; self-healing
> is **declarative + human-gated (UI only)**; free-text answers and legal attestations get an explicit
> policy + an **answer bank**. Local Ollama (`qwen38-q3-64k`, no vision) is the only model.

---

## 1. Principles (carried from the plan, extended)

1. The agent **never** submits. Submission is a human action, and "submitted" is **verified** by a
   confirmation page/email, not an honor-system flag.
2. No endpoint/MCP tool returns a password; the vault never reaches the model. **Extend to listing
   content:** job listings, page, email, and log text are all untrusted data (prompt-injection).
3. Profile/resume are **admin-only**; per-job answer edits are the only thing reachable via MCP.
4. **apply-app never invents answers.** Protected/free-text fields are filled only from explicit
   profile values or left blank; unknown required questions become a `needs_input` item. Any drafted
   prose comes from the console and is marked "drafted" in the review diff.
5. Small, human-maintainable files; pure logic split from I/O; testable in the sandbox before Pi.
6. Pin deps, telemetry off, Ollama is the only model.

## 2. Service boundaries (collapsed)

| Service | Responsibility | Status |
| --- | --- | --- |
| `job-app` | Job-intake source (read-only JSON API) | exists |
| `apply-app` | **Sole owner of application state**: queue → fill → park → review → submit; profile, adapters, error queue, answer bank, review UI (diff + KasmVNC) | **built** |
| `console` (new) | One service = matcher + resume tailor + candidate-list UI. **Owns triage only** (new/shortlisted/dismissed), never application state | new |
| `mcp` | AI-assistant control plane over apply-app (ops tools). **Read-only** on the profile, answers, and suggested fixes | **built** |
| Ollama | The shared model | exists |

**Why collapse:** rev 1's `matcher`/`resume`/`ui` split created a two-store sync problem and a broker
for nothing. One `console` service with one SQLite DB removes that. Inside it, matching/resume logic
stays in separate modules (pure vs I/O), so it can be split later if it ever needs to.

**Build docs:** `docs/CONSOLE-PLAN.md` (design seed) + `services/console/AGENTS.md` (the build-time
agent guide, sized for the 64k local model + compaction recovery).

**Boundary rule:** apply-app is dumb automation + the application record. The console is intelligence
+ the candidate list. The only contract between them: **`POST /jobs` (§5) in → primed application out.**

## 3. Data model & ownership

| Entity | Owner | Notes |
| --- | --- | --- |
| **Profile** | apply-app | contact + resume (JSON-Resume-style structured data) + `requirements` + `experience` JSON. **Versioned** (`base_hash`) — editable, not immutable |
| **Candidate** | console | `{job_app_id, listing_hash, score, rationale, status}`. status: **new / shortlisted / dismissed** (triage only — never "applied") |
| **ResumeVersion** | console | `{job_app_id, base_hash, prompt_version, model}` → content-addressed artifact |
| **Job** (application) | apply-app | + `idempotency_key`, `source{system,id}`, `listing_hash`, `resume_artifact_hash`, `answers{field→{value, provenance: profile|drafted|human}}`, `outcome` |
| **Outcome** | apply-app | manual/derived: parked → submitted → interview / rejected / ghosted (the funnel + calibration data) |
| **AnswerBank** | apply-app | `{question_pattern → approved answer}`, human-confirmed once, reused across jobs |
| **SuggestedFix** | apply-app | a **declarative adapter change** (data diff: selectors, label→field maps, step lists), not code |

**Single source of truth:** listings = job-app; triage = console; resume = console; application state +
outcome = apply-app. The console's list page deep-links into apply-app's existing review UI — **no
second review UI.**

## 4. End-to-end flow

```
job-app (GET /api/jobs)
   → console: dedup (application_url hash + company) → hard filters → LLM coarse-bucket score
   → console list: ranked candidates (deep-link to apply-app)
   → user picks one
   → console: tailor resume (constrained; §7) → ResumeVersion
   → user "apply" → apply-app POST /jobs {contract, §5}  (idempotent)
   → apply-app: worker fills (profile + resume + answer bank) → parks (submit guard) → ready_for_review
   → review UI: field diff (real values, §8) + artifacts + KasmVNC
   → approve / edit-answer / restage
   → human submits manually (agent/human lock, §8) → mark submitted → verify via confirmation page/email
   → outcome tracked (interview/rejected/ghosted)
```

## 5. The contract (write it down, version it)

`POST /jobs` (apply-app) — the *only* console→apply-app write:

```json
{
  "idempotency_key": "…",
  "source": {"system": "job-app", "id": "…"},
  "application_url": "…",
  "listing_hash": "…",
  "resume_artifact_hash": "…",
  "answers": {"field": {"value": "…", "provenance": "profile|drafted|human"}}
}
```
→ `{job_id}`. apply-app emits state-change events (or an outbox) for the console to join at read time.
`idempotency_key` is already on the Job (migration 0002); the rest is additive.

## 6. Key decisions (revised)

1. **One console service** (matcher+resume+UI), one SQLite DB, no broker.
2. **Triage vs lifecycle split.** Console = new/shortlisted/dismissed. apply-app = parked/submitted/
   interview/rejected/ghosted. "Applied" is derived by joining on `(source.system, source.id)`.
3. **Adapters are declarative data**, validated against a schema, with no ability to touch submit
   logic. A "fix" is a reviewable data diff, applied only after offline replay (§11).
4. **Fixes are approved in the UI only — never via MCP** (MCP is an LLM; an LLM must not approve an
   LLM-proposed patch). MCP reads fixes read-only.
5. **Agent/human handoff lock:** when a human takes over a parked tab, the worker detaches from that
   context and cannot re-attach — no agent/human race on one page.
6. **Scoring = hard filters first, LLM last.** Deterministic filters (location, remote, salary floor,
   seniority, keyword dealbreakers) cut the pool; the LLM then assigns coarse buckets (strong/maybe/no)
   + evidence lines, not an absolute 0–100 number. Log `prompt_version` + `model` on every score.
7. **Resume is structured + versioned.** JSON-Resume-style base, rendered via a template. Tailoring is
   constrained to select/reorder/lightly-rephrase the user's own bullets, with a deterministic check
   that no number/employer/title/date/tool in the output is absent from the base.
8. **One shared model, worker-priority budget.** The browser agent always wins; the console's match/
   tailor batch is pausable and yields while a fill is active.

## 7. The console (matcher + resume)

- **Matcher:** poll job-app → dedup → sanitize listing (it's untrusted) → hard filters → for the
  survivors, Ollama (JSON-schema `format`, `think:false`) → `{bucket: strong|maybe|no, evidence: []}`.
- **Resume:** base is structured (JSON Resume). Tailoring is a constrained rewrite (reorder/rephrase,
  no invention) + a deterministic fact-check + a base-diff shown in the UI. Rendered deterministically.
  Versions keyed `(job_app_id, base_hash, prompt_version, model)`, artifact content-addressed.

## 8. Review & submit (apply-app)

- **Real field diff first** (this is the safety-critical gate): read back actually-filled values +
  confidence + flags; provenance (profile/drafted/human) shown per field.
- **Parked jobs capped (3–5) + TTL.** "Park" = persist the field values; on review-open, re-fill
  (re-prime) rather than trusting a stale tab. A "re-prime" action exists.
- **Submit = human, verified.** The human clicks submit in KasmVNC under the agent/human lock; then
  apply-app detects the confirmation page/email and only then marks `submitted`. "Mark submitted"
  without evidence is a fallback, flagged.

## 9. Answers & attestations

- Free-text questions ("why us?") and legal attestations (work authorization, sponsorship, EEO) are
  **filled only from the profile or the answer bank — never invented.** Unknown required → `needs_input`.
- The **answer bank** (question pattern → human-approved answer) is the highest-leverage feature for
  real coverage — more than self-healing, because most real failures are posting-specific questions,
  not selector drift. Split the error taxonomy into **site-level** (adapter) vs **posting-level**
  (human answer) so the proposer is never asked to "fix" a question only the user can answer.

## 10. "As many sites as possible" (revised, honest)

Start with **Greenhouse, Lever, Ashby** (the most regular). Workday/iCIMS/Taleo are tenant-variant/
iframe/ancient — later. Where a board's public API exposes the form's question schema (Greenhouse's
does), pre-flight unknown required questions **without a browser**. Tiers: first-class adapters →
generic label agent → workflow replay. Drop the "~80%" claim until measured.

## 11. Self-healing (gated + declarative)

```
Job fails → error_code + reasoning (already) → proposer (Ollama) reads a *scrubbed* DOM snapshot + adapter
   → writes a declarative SuggestedFix (data diff, schema-validated, no submit-logic access)
   → human approves in the UI (MCP read-only)
   → offline replay: the fix must pass the failing snapshot AND prior successful ones
   → adapter patched (git, one commit per fix, easy rollback) → retry
```

Snapshots are scrubbed of PII before retention. Adapters are versioned in git. This is the
self-improving library, gated twice (human + replay).

## 12. Security & ops (things the review added)

- **Listing content is untrusted** — sanitize before render and before feeding prompts.
- **Access:** for a single user, a VPN (Tailscale/WireGuard) beats basic-auth/SSO. Keep the KasmVNC
  token gate regardless.
- **Hardware:** Ollama may be on another box — define behavior when it's down. Use SSD (not SD) for
  SQLite/Chromium/logs. Keep the Fernet key **separate** from backups; back up the DB (it holds PII).
- **ToS/bans:** rate-limit, avoid account sprawl, per-company dedup + cooldown.
- **Outcome tracking** (at minimum a manual field) gives the funnel + calibration labels from day one.
- **Idle cost:** the collapse to one console service (and later pruning mock/dev containers) reduces
  the 8-container burden.

## 13. Revised milestones (vertical slices — riskiest thing first)

| # | Milestone | Acceptance criteria |
| --- | --- | --- |
| **M4** | Real field diff | worker reads back actually-filled values + confidence/flags/provenance; review UI shows it (the safety-critical gate) |
| **M6a** | One real adapter + supervised run | Greenhouse adapter; one pasted real URL; fill + park; **verified via confirmation email** (not just the click) |
| **M1+M2** | Profile enrichment + matcher | `requirements`/`experience` on profile; console scores mock jobs with hard filters + coarse buckets + evidence; plain ranked table |
| **M5-min** | Candidate list page | ranked list deep-linking into apply-app's existing review UI (no second UI) |
| **Answer bank** | answer bank | question pattern → human-approved answer; fills free-text/attestation fields; `needs_input` for unknowns |
| **M3 (deferred/downgraded)** | resume tailoring | start with 2–3 hand-written base variants per role type; add LLM tailoring only if it demonstrably helps, with the no-invention check |
| **M7** | self-healing | a failed job → declarative SuggestedFix → human approve (UI) → offline replay passes → adapter patched → retry |

Order note: M4 and M6a prove the core on a real form *before* any intelligence/UI work, because the
risk is "can a local q3 no-vision agent reliably prime a real form" — not "can we rank jobs."

## 14. Open questions (remaining)

1. job-app's exact API shape + whether it exposes `application_url` and the form's question schema.
2. Where Ollama runs (same Pi or remote) and the down-behavior.
3. Resume layout: a deterministic template vs a real PDF renderer (ATS parsing of the uploaded file).
4. Greenhouse's public posting API — confirm it exposes the question schema for preflight.
5. VPN vs SSO decision for the human UI (defer; basic-auth works for now).
