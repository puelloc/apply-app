"""Encrypted vault for account passwords.

The derived key lives only in memory and is never persisted — on restart the vault re-seals. On
disk there is only the salt, a passphrase-check ciphertext, and the encrypted secrets. Decryption
fails while sealed (or with a wrong passphrase).
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_ITERATIONS = 600_000
_CHECK = "vault-key-check"


class VaultSealedError(RuntimeError):
    pass


def _derive_key(passphrase: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(passphrase))


class Vault:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._fernet: Fernet | None = None

    # -- on-disk state (salt + check + secrets; nothing secret) -----------

    def _read(self) -> dict:
        if not self.path.exists():
            return {"salt": base64.b64encode(os.urandom(16)).decode(), "secrets": {}}
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())  # fsync before the atomic rename
        os.replace(tmp, self.path)

    # -- seal / unseal -----------------------------------------------------

    def unseal(self, passphrase: str) -> None:
        data = self._read()
        fernet = Fernet(_derive_key(passphrase.encode(), base64.b64decode(data["salt"])))
        if "check" in data:
            try:
                if fernet.decrypt(data["check"].encode()).decode() != _CHECK:
                    raise VaultSealedError("wrong passphrase")
            except InvalidToken as exc:
                raise VaultSealedError("wrong passphrase") from exc
        else:
            data["check"] = fernet.encrypt(_CHECK.encode()).decode()
            self._write(data)
        self._fernet = fernet

    def seal(self) -> None:
        self._fernet = None

    def is_unsealed(self) -> bool:
        return self._fernet is not None

    # -- secrets (require unsealed) ---------------------------------------

    def _require(self) -> Fernet:
        if self._fernet is None:
            raise VaultSealedError("vault is sealed")
        return self._fernet

    def put(self, key: str, plaintext: str) -> None:
        fernet = self._require()
        data = self._read()
        data["secrets"][key] = fernet.encrypt(plaintext.encode()).decode()
        self._write(data)

    def get(self, key: str) -> str:
        fernet = self._require()
        data = self._read()
        token = data["secrets"].get(key)
        if token is None:
            raise KeyError(key)
        return fernet.decrypt(token.encode()).decode()

    def keys(self) -> list[str]:
        return list(self._read()["secrets"].keys())
