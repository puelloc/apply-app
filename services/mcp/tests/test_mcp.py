import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.server import build_server


class FakeClient:
    def __init__(self):
        self.calls = []

    def list_jobs(self, state=None):
        self.calls.append(("list_jobs", state))
        return []

    def get_job(self, job_id):
        self.calls.append(("get_job", job_id))
        return {"id": job_id}

    def create_job(self, data):
        self.calls.append(("create_job", data))
        return {"id": 1}

    def job_action(self, job_id, action):
        self.calls.append(("job_action", job_id, action))
        return {"state": action}

    def get_review(self, job_id):
        self.calls.append(("get_review", job_id))
        return {"job": {"id": job_id}}

    def update_answers(self, job_id, answers):
        self.calls.append(("update_answers", job_id, answers))
        return {"id": job_id}

    def get_review_link(self, job_id):
        self.calls.append(("get_review_link", job_id))
        return {"url": "https://x"}

    def doctor(self):
        self.calls.append(("doctor",))
        return {"status": "ok"}


class TestMCP(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = FakeClient()
        self.server = build_server(self.client)

    async def test_tool_names_exact(self):
        names = sorted(t.name for t in await self.server.list_tools())
        expected = sorted(
            ["list_jobs", "get_job", "enqueue", "cancel", "skip", "retry", "requeue",
             "restage", "get_diff", "get_review_link", "update_answer", "system_status"]
        )
        self.assertEqual(names, expected)

    async def test_no_forbidden_tools(self):
        names = [t.name for t in await self.server.list_tools()]
        for f in ["mark_submitted", "submit", "vault", "seal", "unseal", "password", "token", "shell"]:
            self.assertFalse(any(f in n for n in names), f"forbidden tool present: {f}")

    async def test_update_answer_calls_api(self):
        await self.server.call_tool("update_answer", {"job_id": 7, "field": "email", "value": "x@y.com"})
        self.assertEqual(self.client.calls, [("update_answers", 7, {"email": "x@y.com"})])

    async def test_enqueue_builds_payload(self):
        await self.server.call_tool(
            "enqueue",
            {"company_name": "Acme", "title": "Eng", "listing_url": "http://x", "requires_account": True},
        )
        self.assertEqual(self.client.calls[0][0], "create_job")
        data = self.client.calls[0][1]
        self.assertEqual(data["company_name"], "Acme")
        self.assertTrue(data["requires_account"])

    async def test_system_status(self):
        await self.server.call_tool("system_status", {})
        self.assertEqual(self.client.calls, [("doctor",)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
