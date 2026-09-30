import os
import tempfile
import unittest

from app.db import Database
from app.models import Base
from app.services import accounts
from app.vault import Vault, VaultSealedError


class TestVault(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)
        self.vault = Vault(self.path)

    def test_put_get_roundtrip(self):
        self.vault.unseal("correct horse battery staple")
        self.vault.put("a1", "hunter2")
        self.assertEqual(self.vault.get("a1"), "hunter2")

    def test_sealed_raises(self):
        self.vault.unseal("pw")
        self.vault.put("a1", "secret")
        self.vault.seal()
        with self.assertRaises(VaultSealedError):
            self.vault.get("a1")

    def test_reunseal_with_same_passphrase(self):
        self.vault.unseal("pw")
        self.vault.put("a1", "secret")
        self.vault.seal()
        self.vault.unseal("pw")
        self.assertEqual(self.vault.get("a1"), "secret")

    def test_wrong_passphrase_rejected(self):
        self.vault.unseal("right")
        self.vault.put("a1", "secret")
        self.vault.seal()
        with self.assertRaises(VaultSealedError):
            self.vault.unseal("wrong")

    def test_keys_does_not_leak_values(self):
        self.vault.unseal("pw")
        self.vault.put("a1", "secret")
        self.assertEqual(self.vault.keys(), ["a1"])


class TestAccounts(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        fd, self.vault_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.vault_path)
        self.db = Database(self.db_path)
        Base.metadata.create_all(self.db.engine)
        self.vault = Vault(self.vault_path)
        self.vault.unseal("pw")

    def tearDown(self) -> None:
        self.db.engine.dispose()
        os.unlink(self.db_path)
        os.unlink(self.vault_path)

    def test_two_phase_and_reconcile(self):
        with self.db.session() as s:
            accounts.begin(s, self.vault, "c1@example.invalid", "acme.com", "pw1")
        self.assertEqual(self.vault.get("c1@example.invalid"), "pw1")

        with self.db.session() as s:
            self.assertEqual(accounts.reconcile(s, "c1@example.invalid"), "login_or_reset")
            accounts.confirm(s, "c1@example.invalid")
        with self.db.session() as s:
            self.assertEqual(accounts.reconcile(s, "c1@example.invalid"), "login")

        with self.db.session() as s:
            self.assertEqual(accounts.reconcile(s, "new@example.invalid"), "signup")


if __name__ == "__main__":
    unittest.main(verbosity=2)
