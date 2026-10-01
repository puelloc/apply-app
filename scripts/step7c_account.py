#!/usr/bin/env python3
"""Step 7c: account-flow chain — signup (vault) → verify (mock IMAP) → confirm.

Runs the worker's real account_flow/aliases/imap/vault modules against the mock IMAP server, so the
full account chain is exercised with zero real credentials. The browser fill of the signup form is
deferred to the full pipeline (the fill pattern is already verified in step 6c); this proves the
account + verification + confirm chain.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, "/app")  # worker modules live in /app

from account_flow import confirm, signup, verify
from aliases import alias_for, token_for
from imap import poll
from vault import Vault

BASE_EMAIL = os.environ.get("BASE_EMAIL", "jobs@example.invalid")
JOB_ID = int(os.environ.get("JOB_ID", "1"))
IMAP_HOST = os.environ.get("MOCK_IMAP_HOST", "127.0.0.1")
IMAP_PORT = int(os.environ.get("MOCK_IMAP_PORT", "9143"))


class FakeApi:
    def __init__(self):
        self.accounts = {}

    def create_account(self, alias, site):
        self.accounts.setdefault(alias, "pending")

    def get_account(self, alias):
        return {"state": self.accounts[alias]} if alias in self.accounts else None

    def confirm_account(self, alias):
        self.accounts[alias] = "confirmed"


def main() -> None:
    alias = alias_for(BASE_EMAIL, token_for(JOB_ID))
    verify_url = f"http://mock-ats:8000/verify?token=canary{JOB_ID}"

    env = {**os.environ, "MOCK_IMAP_PORT": str(IMAP_PORT), "MOCK_IMAP_ALIAS": alias, "MOCK_VERIFY_URL": verify_url}
    imap_proc = subprocess.Popen([sys.executable, "/spike/services/mock-ats/mock_imap.py"], env=env)
    time.sleep(1)

    api = FakeApi()
    vault = Vault("/tmp/step7c-vault.json")
    vault.unseal("step7c-passphrase")

    info = signup(api, vault, JOB_ID, BASE_EMAIL, "acme.com")
    assert vault.get(info["alias"]) == info["password"], "vault round-trip failed"
    print(f"signup: alias={info['alias']} password-in-vault=OK")

    url = verify(lambda a: poll(IMAP_HOST, "user", "pass", a, timeout=5), info["alias"], timeout_s=30, interval_s=2)
    print(f"verify: url={url}")

    if url:
        confirm(api, info["alias"])
    state = api.get_account(info["alias"])["state"]
    print(f"confirm: state={state}")

    imap_proc.terminate()
    ok = url == verify_url and state == "confirmed"
    print("STEP 7c", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
