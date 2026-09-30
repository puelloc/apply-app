import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Job, Lease
from app.security import hash_token

SERVICE_DIR = Path(__file__).resolve().parent


class TestDoctor(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        # Apply real migrations so the db_migrations check sees current == head.
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(SERVICE_DIR),
            env={**os.environ, "DB_PATH": self.path},
            check=True,
            capture_output=True,
        )
        self.app = create_app(db_path=self.path)
        self.app.state.token_hashes = {"diagnose": hash_token("diag")}
        self.client = TestClient(self.app, headers={"Authorization": "Bearer diag"})

    def tearDown(self) -> None:
        self.app.state.db.engine.dispose()
        os.unlink(self.path)

    def test_doctor_returns_three_checks(self):
        r = self.client.get("/doctor")
        self.assertEqual(r.status_code, 200)
        checks = {c["name"]: c for c in r.json()["checks"]}
        self.assertIn("db_migrations", checks)
        self.assertIn("stuck_leases", checks)
        self.assertIn("ollama_reachable", checks)
        self.assertTrue(checks["db_migrations"]["ok"])

    def test_stuck_lease_detected(self):
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        with self.app.state.db.session() as s:
            job = Job(company_name="Acme", title="T", listing_url="http://x")
            s.add(job)
            s.flush()
            s.add(Lease(job_id=job.id, lease_token="t", expires_at=past))
            s.commit()
        checks = {c["name"]: c for c in self.client.get("/doctor").json()["checks"]}
        self.assertFalse(checks["stuck_leases"]["ok"])
        self.assertIn("1 expired", checks["stuck_leases"]["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
