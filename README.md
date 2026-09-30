# apply-app

Local job-application automation: a queue of job applications that runs in the background, fills the
forms, and parks each job on its final page — **never** clicking submit. You review and approve later.

The plan is the source of truth: **[docs/PLAN.md](docs/PLAN.md)**. All decisions, discoveries, and
verification evidence live there.

For a fresh-session handoff (rules, hosts, versions, gotchas, current state): **[CONTEXT.md](CONTEXT.md)**.

## Layout

| Path | Purpose |
| --- | --- |
| `docs/PLAN.md` | The plan (verbatim) + Decision log, Verification log, Open questions, Changelog |
| `compose.yaml` | Docker Compose skeleton: `dev` / `test` (mock ATS) / `prod` profiles, four networks, volumes, secrets |
| `scripts/spikes/` | Step-0 spike commands (P1–P5, O1–O6, W1–W3), one copy-paste script per machine |
| `tests/` | Verification tests (N, S, E, R, L suites) as they are built |

## Job source

`apply-app` reads jobs from the existing **jobs-app** project's read-only JSON API (`GET /api/jobs`,
`GET /api/jobs/{id}` with `application_url`), not from a duplicated database. See the Decision log in
`docs/PLAN.md`.

## Safety invariants (non-negotiable)

- The agent never submits an application.
- No endpoint or MCP tool ever returns a password.
- The vault never reaches the model.
- Page, email, and log content is untrusted data.
