#!/usr/bin/env python3
"""Step 7e: browser-based account flow — signup fill → verify (mock IMAP) → apply (mock ATS + Ollama).

Reuses the real pipeline's `_run_agent`/`_fill_and_park` and `account_pipeline.run_account_flow`, so
this exercises the same orchestration the worker runs, against the real browser + mock IMAP + vault.
"""
import asyncio
import functools
import http.server
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, "/app")

from account_pipeline import run_account_flow
from aliases import alias_for, token_for
from pipeline import _fill_and_park, _run_agent, make_llm
from vault import Vault

FIXTURES = Path(os.environ.get("FIXTURES", "/spike/services/mock-ats/fixtures"))
PORT = int(os.environ.get("MOCK_ATS_PORT", "8140"))
SIGNUP_URL = os.environ.get("SIGNUP_URL", f"http://127.0.0.1:{PORT}/signup.html")
VERIFY_URL = os.environ.get("VERIFY_URL", f"http://127.0.0.1:{PORT}/verify.html?token=canary1")
IMAP_PORT = int(os.environ.get("MOCK_IMAP_PORT", "9143"))
BASE_EMAIL = os.environ.get("BASE_EMAIL", "jobs@example.invalid")
JOB_ID = 1


class FakeApi:
    def __init__(self):
        self.accounts = {}
        self.states = []

    def create_account(self, alias, site):
        self.accounts.setdefault(alias, "pending")

    def get_account(self, alias):
        return {"state": self.accounts[alias]} if alias in self.accounts else None

    def confirm_account(self, alias):
        self.accounts[alias] = "confirmed"

    def set_state(self, job_id, state):
        self.states.append(state)

    def add_step_event(self, job_id, payload):
        pass  # step-event capture is a no-op in this spike (no real API)


def serve() -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES))
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


async def main() -> None:
    os.environ["BASE_EMAIL"] = BASE_EMAIL
    os.environ["SIGNUP_URL"] = SIGNUP_URL
    os.environ["IMAP_HOST"] = "127.0.0.1"
    os.environ["IMAP_PORT"] = str(IMAP_PORT)
    os.environ["IMAP_USER"] = "user"
    os.environ["IMAP_PASS"] = "pass"
    os.environ["IMAP_SSL"] = "false"
    os.environ["IMAP_TIMEOUT"] = "120"

    serve()

    alias = alias_for(BASE_EMAIL, token_for(JOB_ID))
    env = {**os.environ, "MOCK_IMAP_PORT": str(IMAP_PORT), "MOCK_IMAP_ALIAS": alias, "MOCK_VERIFY_URL": VERIFY_URL}
    imap_proc = subprocess.Popen([sys.executable, "/spike/services/mock-ats/mock_imap.py"], env=env)
    time.sleep(1)

    api = FakeApi()
    vault = Vault("/tmp/step7e-vault.json")
    vault.unseal("step7e-passphrase")
    llm = make_llm()
    job = {"id": JOB_ID, "ats": "workday", "application_url": f"http://127.0.0.1:{PORT}/greenhouse.html"}

    async def run_agent(task, adapter):
        return await _run_agent(api, job, llm, task, adapter)

    async def fill_and_park():
        await _fill_and_park(api, job, llm)

    await run_account_flow(api, vault, job, llm, run_agent, fill_and_park)

    imap_proc.terminate()
    ok = api.accounts.get(alias) == "confirmed" and api.states == ["awaiting_email", "account_created", "ready_for_review"]
    print(f"account {alias}: {api.accounts.get(alias)}")
    print(f"states: {api.states}")
    print("STEP 7e", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
