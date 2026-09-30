"""Worker entrypoint: unseal the vault, then poll the queue and process jobs.

The vault key lives only in this process's memory (re-seals on reboot). The passphrase is supplied
via VAULT_PASSPHRASE (or the CLI) at boot; it is never written to disk.
"""

from __future__ import annotations

import asyncio
import os

from vault import Vault  # COPY'd from services/api/app/vault.py
from pipeline import main as run_loop  # module-level import (pipeline resolves Chromium path pre-loop)


async def main() -> None:
    vault = Vault(os.environ.get("VAULT_PATH", "/data/vault/vault.json"))
    passphrase = os.environ.get("VAULT_PASSPHRASE")
    if passphrase:
        vault.unseal(passphrase)
        print("vault unsealed")
    else:
        print("vault sealed (set VAULT_PASSPHRASE to unseal)")

    await run_loop()


if __name__ == "__main__":
    asyncio.run(main())
