import os
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import create_app
from app.models import Base, Job
from app.security import hash_token

JOB = {"company_name": "Acme", "title": "Engineer", "listing_url": "http://x", "application_url": "http://y"}


class TestJobsApi(unittest.TestCase):
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

    def _set_state(self, job_id: int, state: str) -> None:
        with self.app.state.db.session() as s:
            s.execute(update(Job).where(Job.id == job_id).values(state=state))
            s.commit()

    def test_create_and_get(self):
        r = self.client.post("/jobs", json=JOB)
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["state"], "queued")
        self.assertEqual(self.client.get(f"/jobs/{body['id']}").json()["company_name"], "Acme")

    def test_create_idempotent(self):
        r1 = self.client.post("/jobs", json={**JOB, "idempotency_key": "k1"})
        r2 = self.client.post("/jobs", json={**JOB, "idempotency_key": "k1"})
        self.assertEqual(r1.json()["id"], r2.json()["id"])

    def test_list_filters_and_pagination(self):
        for i in range(3):
            self.client.post("/jobs", json={**JOB, "title": f"E{i}", "ats": "greenhouse" if i < 2 else "lever"})
        r = self.client.get("/jobs", params={"ats": "greenhouse", "limit": 1})
        body = r.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["jobs"]), 1)
        self.assertIsNotNone(body["next_cursor"])

    def test_transition_cancel_and_invalid(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        self.assertEqual(self.client.post(f"/jobs/{jid}/actions", json={"action": "cancel"}).json()["state"], "cancelled")
        self.assertEqual(self.client.post(f"/jobs/{jid}/actions", json={"action": "cancel"}).status_code, 400)

    def test_retry_from_failed(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        self._set_state(jid, "failed")
        self.assertEqual(self.client.post(f"/jobs/{jid}/actions", json={"action": "retry"}).json()["state"], "queued")

    def test_pipeline_state_transition(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        # queued -> ready_for_review is not a valid direct pipeline transition
        self.assertEqual(self.client.post(f"/jobs/{jid}/state", json={"state": "ready_for_review"}).status_code, 400)
        self._set_state(jid, "running")
        self.assertEqual(self.client.post(f"/jobs/{jid}/state", json={"state": "ready_for_review"}).json()["state"], "ready_for_review")

    def test_bulk_create(self):
        r = self.client.post("/jobs/bulk", json=[JOB, {**JOB, "title": "Other"}])
        self.assertEqual(r.json()["total"], 2)


class TestLeaseApi(unittest.TestCase):
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

    def test_acquire_heartbeat_release(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        r = self.client.post("/leases/acquire")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["job"]["id"], jid)
        token = r.json()["lease_token"]

        # queue is now empty
        self.assertEqual(self.client.post("/leases/acquire").status_code, 404)

        # heartbeat: wrong token -> 409, right token -> 200
        self.assertEqual(self.client.post(f"/leases/{jid}/heartbeat", json={"lease_token": "bad"}).status_code, 409)
        self.assertEqual(self.client.post(f"/leases/{jid}/heartbeat", json={"lease_token": token}).status_code, 200)

        # release
        self.assertEqual(self.client.post(f"/leases/{jid}/release", json={"lease_token": token}).json()["released"], True)
        self.assertEqual(self.client.post(f"/leases/{jid}/release", json={"lease_token": token}).status_code, 409)


if __name__ == "__main__":
    unittest.main(verbosity=2)
