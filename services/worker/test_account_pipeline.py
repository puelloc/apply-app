import os
import unittest

import account_pipeline
from aliases import alias_for, token_for


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


class FakeVault:
    def __init__(self):
        self.data = {}

    def put(self, key, value):
        self.data[key] = value


class _Result:
    def is_successful(self):
        return True


class TestRunAccountFlow(unittest.IsolatedAsyncioTestCase):
    async def test_full_flow(self):
        os.environ["BASE_EMAIL"] = "jobs@x.com"
        api = FakeApi()
        vault = FakeVault()
        job = {"id": 1, "ats": "workday", "application_url": "http://x"}
        calls = []

        async def run_agent(task, adapter):
            calls.append(("run_agent", task, adapter))
            return _Result()

        async def fill_and_park():
            calls.append(("fill_and_park",))
            api.set_state(1, "ready_for_review")

        await account_pipeline.run_account_flow(api, vault, job, None, run_agent, fill_and_park, poll_fn=lambda a: "https://verify")

        alias = alias_for("jobs@x.com", token_for(1))
        self.assertEqual(api.accounts[alias], "confirmed")
        self.assertEqual(api.states, ["awaiting_email", "account_created", "ready_for_review"])
        self.assertEqual([c[0] for c in calls], ["run_agent", "run_agent", "fill_and_park"])

    async def test_verify_timeout_marks_failed(self):
        os.environ["BASE_EMAIL"] = "jobs@x.com"
        os.environ["IMAP_TIMEOUT"] = "0.1"
        api = FakeApi()
        vault = FakeVault()
        job = {"id": 1, "ats": "workday", "application_url": "http://x"}

        async def run_agent(task, adapter):
            return _Result()

        async def fill_and_park():
            raise AssertionError("fill_and_park should not be called")

        await account_pipeline.run_account_flow(api, vault, job, None, run_agent, fill_and_park, poll_fn=lambda a: None)

        self.assertEqual(api.states, ["awaiting_email", "failed"])

    async def test_no_verification_skips_imap(self):
        os.environ["BASE_EMAIL"] = "jobs@x.com"
        api = FakeApi()
        vault = FakeVault()
        job = {"id": 1, "ats": "taleo", "application_url": "http://x", "requires_verification": False}
        calls = []

        async def run_agent(task, adapter):
            calls.append(("run_agent",))
            return _Result()

        async def fill_and_park():
            calls.append(("fill_and_park",))
            api.set_state(1, "ready_for_review")

        await account_pipeline.run_account_flow(api, vault, job, None, run_agent, fill_and_park, poll_fn=lambda a: None)

        alias = alias_for("jobs@x.com", token_for(1))
        self.assertEqual(api.accounts[alias], "confirmed")
        self.assertEqual(api.states, ["account_created", "ready_for_review"])
        self.assertEqual([c[0] for c in calls], ["run_agent", "fill_and_park"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
