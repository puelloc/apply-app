import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Base
from app.security import hash_token


class TestAccountsApi(unittest.TestCase):
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

    def test_create_idempotent_and_confirm(self):
        r = self.client.post("/accounts", json={"alias": "jobs+1@x.com", "site": "acme.com"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["state"], "pending")
        # idempotent
        r2 = self.client.post("/accounts", json={"alias": "jobs+1@x.com", "site": "acme.com"})
        self.assertEqual(r.json()["id"], r2.json()["id"])

        r3 = self.client.post("/accounts/jobs+1@x.com/confirm")
        self.assertEqual(r3.json()["state"], "confirmed")

    def test_get_missing_404(self):
        self.assertEqual(self.client.get("/accounts/nope@x.com").status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
