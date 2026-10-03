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

    def test_requires_account_default_and_set(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        self.assertFalse(self.client.get(f"/jobs/{jid}").json()["requires_account"])
        jid2 = self.client.post("/jobs", json={**JOB, "requires_account": True}).json()["id"]
        self.assertTrue(self.client.get(f"/jobs/{jid2}").json()["requires_account"])

    def test_review_fill_summary_and_approve(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        self._set_state(jid, "ready_for_review")
        summary = {"fields": [{"name": "email", "value": "x@y.com", "source": "canary"}]}
        self.assertEqual(self.client.post(f"/jobs/{jid}/fill-summary", json={"fill_summary": summary}).json()["fill_summary"], summary)
        rv = self.client.get(f"/jobs/{jid}/review").json()
        self.assertTrue(rv["ready_to_approve"])
        self.assertEqual(rv["job"]["fill_summary"], summary)
        self.assertTrue(self.client.post(f"/jobs/{jid}/approve").json()["approved"])
        self.assertFalse(self.client.get(f"/jobs/{jid}/review").json()["ready_to_approve"])

    def test_answer_overrides_and_restage(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        self.client.post(f"/jobs/{jid}/answers", json={"answers": {"email": "new@x.com"}})
        self.assertEqual(self.client.get(f"/jobs/{jid}").json()["answer_overrides"], {"email": "new@x.com"})
        # merge a second override
        self.client.post(f"/jobs/{jid}/answers", json={"answers": {"phone": "555-9999"}})
        self.assertEqual(self.client.get(f"/jobs/{jid}").json()["answer_overrides"], {"email": "new@x.com", "phone": "555-9999"})
        # restage -> restaging, then the worker (lease acquire) picks it up
        self._set_state(jid, "ready_for_review")
        self.assertEqual(self.client.post(f"/jobs/{jid}/actions", json={"action": "restage"}).json()["state"], "restaging")
        lease = self.client.post("/leases/acquire")
        self.assertEqual(lease.status_code, 200)
        self.assertEqual(lease.json()["job"]["id"], jid)

    def test_auth_review_token(self):
        jid = self.client.post("/jobs", json=JOB).json()["id"]
        self._set_state(jid, "ready_for_review")
        link = self.client.get(f"/jobs/{jid}/review-link").json()
        token = link["url"].split("token=")[1]
        self.assertEqual(self.client.get("/auth/review", params={"token": token}).status_code, 200)
        self.assertEqual(self.client.get("/auth/review", params={"token": "bad"}).status_code, 401)
        # a valid token for a non-ready job is rejected
        jid2 = self.client.post("/jobs", json={**JOB, "title": "Other"}).json()["id"]
        self._set_state(jid2, "ready_for_review")
        tok2 = self.client.get(f"/jobs/{jid2}/review-link").json()["url"].split("token=")[1]
        self._set_state(jid2, "cancelled")
        self.assertEqual(self.client.get("/auth/review", params={"token": tok2}).status_code, 401)

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
