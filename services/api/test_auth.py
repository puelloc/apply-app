import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Base
from app.security import hash_token

JOB = {"company_name": "Acme", "title": "Engineer", "listing_url": "http://x"}


class TestAuth(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app(db_path=self.path)
        self.app.state.token_hashes = {
            "admin": hash_token("admin-token"),
            "ops": hash_token("ops-token"),
            "diagnose": hash_token("diag-token"),
        }
        Base.metadata.create_all(self.app.state.db.engine)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.state.db.engine.dispose()
        os.unlink(self.path)

    def test_no_token_401(self):
        self.assertEqual(self.client.get("/jobs").status_code, 401)

    def test_wrong_token_401(self):
        self.assertEqual(self.client.get("/jobs", headers={"Authorization": "Bearer nope"}).status_code, 401)

    def test_diagnose_read_ok_write_forbidden(self):
        h = {"Authorization": "Bearer diag-token"}
        self.assertEqual(self.client.get("/jobs", headers=h).status_code, 200)
        self.assertEqual(self.client.post("/jobs", json=JOB, headers=h).status_code, 403)

    def test_ops_write_ok(self):
        h = {"Authorization": "Bearer ops-token"}
        self.assertEqual(self.client.post("/jobs", json=JOB, headers=h).status_code, 201)

    def test_admin_can_read(self):
        h = {"Authorization": "Bearer admin-token"}
        self.assertEqual(self.client.get("/jobs", headers=h).status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
