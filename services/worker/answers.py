"""The answers the worker fills into the form (pure — no browser-use import).

Frozen answers (from the first run's `fill_summary`) are replayed on re-staging and never regenerated;
per-job `answer_overrides` (edit-and-rerun) are merged on top. A first fill uses CANARY values.
"""

from __future__ import annotations

_CANARY = {
    "first_name": "CANARY-First",
    "last_name": "CANARY-Last",
    "email": "canary@example.invalid",
    "phone": "555-0001",
}


def _frozen_answers(fill_summary: dict | None) -> dict:
    if not fill_summary:
        return {}
    return {f["name"]: f["value"] for f in fill_summary.get("fields", [])}


def answers(job: dict) -> dict:
    """The answers to fill: frozen (replay) + overrides, else CANARY (first fill)."""
    base = _frozen_answers(job.get("fill_summary")) if job.get("fill_summary") else dict(_CANARY)
    base.update(job.get("answer_overrides") or {})
    return base


def build_task(job: dict) -> str:
    # TODO(step 8): derive from the profile/answers + adapter fields; for now frozen+overrides/CANARY.
    url = job.get("application_url") or job.get("listing_url")
    a = answers(job)
    return (
        f"Open the application form at {url}. Fill first name {a['first_name']}, last name {a['last_name']}, "
        f"email {a['email']}, phone {a['phone']}. Then STOP. Do NOT click the Submit button."
    )


def build_fill_summary(job: dict) -> dict:
    # TODO(step 8): extract the actual filled values from the parked page; for now the answers used.
    a = answers(job)
    overrides = job.get("answer_overrides") or {}
    frozen = bool(job.get("fill_summary"))
    return {
        "fields": [
            {"name": name, "value": value, "source": "override" if name in overrides else ("frozen" if frozen else "canary")}
            for name, value in a.items()
        ]
    }
