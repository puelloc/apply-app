"""Thin httpx client for the API, authenticated with the worker's ops token."""

from __future__ import annotations

import httpx


class ApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def _post(self, path: str, json: dict | None = None) -> httpx.Response:
        return httpx.post(self._url(path), json=json, headers=self._headers, timeout=15)

    def acquire(self) -> dict | None:
        r = self._post("/leases/acquire")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def release(self, job_id: int, lease_token: str) -> None:
        self._post(f"/leases/{job_id}/release", {"lease_token": lease_token}).raise_for_status()

    def add_step_event(self, job_id: int, payload: dict) -> None:
        self._post(f"/jobs/{job_id}/step-events", payload).raise_for_status()

    def transition(self, job_id: int, action: str) -> None:
        self._post(f"/jobs/{job_id}/actions", {"action": action}).raise_for_status()
