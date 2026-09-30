import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Base
from app.security import hash_token

JOB = {"company_name": "Acme", "title": "Engineer", "listing_url": "http://x"}


class TestStepEvents(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app(db_path=self.path)
        self.app.state.token_hashes = {"admin": hash_token("admin"), "ops": hash_token("ops"), "diagnose": hash_token("diag")}
        Base.metadata.create_all(self.app.state.db.engine)
        self.client = TestClient(self.app, headers={"Authorization": "Bearer ops"})

    def tearDown(self) -> None:
        self.app.state.db.engine.dispose()
        os.unlink(self.path)

    def test_write_and_read_events(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        payload = {
            "run_id": "r1", "step": "agent-1", "adapter": "greenhouse",
            "action": "input_text", "postcondition": "pass",
            "model_meta": {"eval": "e", "memory": "m", "next_goal": "n"},
        }
        r = self.client.post(f"/jobs/{jid}/step-events", json=payload)
        self.assertEqual(r.status_code, 201)

        events = self.client.get(f"/jobs/{jid}/step-events", headers={"Authorization": "Bearer diag"}).json()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["adapter"], "greenhouse")
        self.assertEqual(events[0]["model_meta"]["next_goal"], "n")

    def test_event_for_missing_job_404(self):
        self.assertEqual(self.client.post("/jobs/999/step-events", json={"run_id": "r", "step": "s", "action": "a"}).status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
