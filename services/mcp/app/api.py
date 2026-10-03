"""Thin client for the apply-app API endpoints the MCP tools expose.

Never exposes vault, passwords, tokens, or anything resembling submit — the tools above it call only
the read/diagnose and write/ops job + review + doctor endpoints.
"""

from __future__ import annotations

import httpx


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, base_url: str, token: str):
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token}"}, timeout=15.0
        )

    def _raise(self, r: httpx.Response) -> None:
        if r.status_code >= 400:
            raise ApiError(f"{r.status_code}: {r.text[:200]}")

    def list_jobs(self, state: str | None = None) -> list[dict]:
        r = self._client.get(f"{self._base}/jobs", params={"state": state} if state else None)
        self._raise(r)
        return r.json()

    def get_job(self, job_id: int) -> dict:
        r = self._client.get(f"{self._base}/jobs/{job_id}")
        self._raise(r)
        return r.json()

    def create_job(self, data: dict) -> dict:
        r = self._client.post(f"{self._base}/jobs", json=data)
        self._raise(r)
        return r.json()

    def job_action(self, job_id: int, action: str) -> dict:
        r = self._client.post(f"{self._base}/jobs/{job_id}/actions", json={"action": action})
        self._raise(r)
        return r.json()

    def get_review(self, job_id: int) -> dict:
        r = self._client.get(f"{self._base}/jobs/{job_id}/review")
        self._raise(r)
        return r.json()

    def update_answers(self, job_id: int, answers: dict) -> dict:
        r = self._client.post(f"{self._base}/jobs/{job_id}/answers", json={"answers": answers})
        self._raise(r)
        return r.json()

    def get_review_link(self, job_id: int) -> dict:
        r = self._client.get(f"{self._base}/jobs/{job_id}/review-link")
        self._raise(r)
        return r.json()

    def doctor(self) -> dict:
        r = self._client.get(f"{self._base}/doctor")
        self._raise(r)
        return r.json()
