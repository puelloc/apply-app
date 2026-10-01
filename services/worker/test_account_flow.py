import unittest

import account_flow
from aliases import alias_for, token_for


class FakeApi:
    def __init__(self):
        self.accounts = {}

    def create_account(self, alias, site):
        self.accounts.setdefault(alias, "pending")

    def get_account(self, alias):
        return {"state": self.accounts[alias]} if alias in self.accounts else None

    def confirm_account(self, alias):
        self.accounts[alias] = "confirmed"


class FakeVault:
    def __init__(self):
        self.data = {}

    def put(self, key, value):
        self.data[key] = value


class TestAccountFlow(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.vault = FakeVault()

    def test_signup_stores_password_and_pending(self):
        info = account_flow.signup(self.api, self.vault, job_id=7, base_email="jobs@x.com", site="acme.com")
        self.assertEqual(info["alias"], alias_for("jobs@x.com", token_for(7)))
        self.assertEqual(self.vault.data[info["alias"]], info["password"])
        self.assertEqual(self.api.get_account(info["alias"])["state"], "pending")

    def test_verify_returns_url_when_it_arrives(self):
        calls = {"n": 0}

        def poll(alias):
            calls["n"] += 1
            return "https://acme.com/verify?t=1" if calls["n"] >= 3 else None

        url = account_flow.verify(poll, "jobs+job7@x.com", timeout_s=1.0, interval_s=0.0)
        self.assertEqual(url, "https://acme.com/verify?t=1")

    def test_verify_times_out(self):
        url = account_flow.verify(lambda alias: None, "a@x.com", timeout_s=0.1, interval_s=0.05)
        self.assertIsNone(url)

    def test_reconcile_decision(self):
        self.assertEqual(account_flow.reconcile(self.api, "new@x.com"), "signup")
        self.api.create_account("pending@x.com", "acme.com")
        self.assertEqual(account_flow.reconcile(self.api, "pending@x.com"), "login_or_reset")
        self.api.confirm_account("pending@x.com")
        self.assertEqual(account_flow.reconcile(self.api, "pending@x.com"), "login")


if __name__ == "__main__":
    unittest.main(verbosity=2)
