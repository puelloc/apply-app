import os
import tempfile
import unittest

from app.db import Database
from app.models import ALL_STATES, Account, Base, Job, Lease, StepEvent


class TestModels(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.path)
        Base.metadata.create_all(self.db.engine)

    def tearDown(self) -> None:
        self.db.engine.dispose()
        os.unlink(self.path)

    def test_job_defaults_and_roundtrip(self) -> None:
        with self.db.session() as s:
            job = Job(company_name="Acme", title="Engineer", listing_url="http://x", application_url="http://y")
            s.add(job)
            s.commit()
            job_id = job.id
        with self.db.session() as s:
            job = s.get(Job, job_id)
            self.assertEqual(job.state, "queued")
            self.assertEqual(job.company_name, "Acme")
            self.assertIsNotNone(job.created_at)

    def test_step_event_links_to_job(self) -> None:
        with self.db.session() as s:
            job = Job(company_name="Acme", title="Engineer", listing_url="http://x")
            s.add(job)
            s.flush()
            s.add(StepEvent(job_id=job.id, run_id="r1", step="fill", action="input", postcondition="pass"))
            s.commit()
        with self.db.session() as s:
            self.assertEqual(s.query(StepEvent).count(), 1)
            self.assertEqual(s.query(StepEvent).one().job_id, s.query(Job).one().id)

    def test_lease_and_account(self) -> None:
        from datetime import datetime, timedelta, timezone

        with self.db.session() as s:
            job = Job(company_name="Acme", title="Engineer", listing_url="http://x")
            s.add(job)
            s.flush()
            s.add(Lease(job_id=job.id, lease_token="t1", expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
            s.add(Account(alias="c1@example.invalid", site="acme.com"))
            s.commit()
        with self.db.session() as s:
            self.assertEqual(s.query(Lease).count(), 1)
            self.assertEqual(s.query(Account).one().state, "pending")

    def test_state_vocabulary(self) -> None:
        for state in ("queued", "running", "ready_for_review", "submitted", "failed", "stale", "submitted_unconfirmed"):
            self.assertIn(state, ALL_STATES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
