# Contracts

Two APIs matter: the **console's own** API (what Svelte calls) and **apply-app's** API (what the Go
backend calls). All apply-app calls carry the bearer token — held by Go, never the browser.

## apply-app API (Go → apply-app)

Base: `http://172.17.0.1:8000` (docker bridge) or `API_URL` env. Auth: `Authorization: Bearer <token>`.

| Method | Path | Use |
| --- | --- | --- |
| POST | `/jobs` | enqueue a primed application (idempotent; see body below) |
| GET | `/jobs?state=ready_for_review` | the review inbox |
| GET | `/jobs/{id}/review` | the field diff + `ready_to_approve` |
| POST | `/jobs/{id}/approve` | mark picked (never submits) |
| POST | `/jobs/{id}/answers` | `{"answers": {"field": "value"}}` — per-job edit |
| POST | `/jobs/{id}/actions` | `{"action": "restage"}` — re-fill |
| GET | `/jobs/{id}/review-link` | short-lived KasmVNC link |
| GET | `/profile` | contact + resume + requirements |
| GET | `/doctor` | system status |

`POST /jobs` body (the contract — the only console→apply-app write):

```json
{
  "idempotency_key": "console:<candidate-id>",
  "company_name": "…", "title": "…",
  "listing_url": "…", "application_url": "…",
  "source": {"system": "job-app", "id": "…"},
  "listing_hash": "…",
  "resume_artifact_hash": "…"
}
```

## Console API (Svelte → Go)

Base: `/api`. Same-origin; no token in the browser.

| Method | Path | Use |
| --- | --- | --- |
| GET | `/api/candidates` | ranked candidates (triage list) |
| POST | `/api/candidates/{id}/shortlist` | mark shortlisted |
| POST | `/api/candidates/{id}/dismiss` | dismiss |
| POST | `/api/candidates/{id}/apply` | tailor (later) + enqueue in apply-app |
| GET | `/api/inbox` | proxy of apply-app `ready_for_review` |
| GET | `/api/jobs/{id}/review` | proxy: field diff |
| POST | `/api/jobs/{id}/approve` | proxy: approve (never submits) |
| POST | `/api/jobs/{id}/answers` | proxy: edit an answer |
| POST | `/api/jobs/{id}/restage` | proxy: re-fill |
| GET | `/api/jobs/{id}/review-link` | proxy: KasmVNC link |
| GET | `/api/status` | proxy of `/doctor` |

## Rules

- Proxies must pass the apply-app error codes through unchanged (the UI shows them).
- Nothing in the console API submits. There is no submit endpoint.
- Keep this file in sync when an apply-app route changes.
