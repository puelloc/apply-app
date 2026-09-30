"""FastAPI app skeleton — health endpoint only for now.

Jobs/queue/leases/step-events/auth land in later increments. The app exposes a `Database` on
`app.state.db` so routes can share one engine.
"""

from __future__ import annotations

from fastapi import FastAPI

from .config import get_settings
from .db import Database


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="apply-app api", version="0.1.0")
    app.state.db = Database(settings.db_path)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
