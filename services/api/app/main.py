"""FastAPI app skeleton — health endpoint only for now.

Jobs/queue/leases/step-events/auth land in later increments. The app exposes a `Database` on
`app.state.db` so routes can share one engine.
"""

from __future__ import annotations

from fastapi import FastAPI

from .config import get_settings
from .db import Database
from .routes import doctor, events, jobs, leases
from .security import load_token_hashes


def create_app(db_path: str | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="apply-app api", version="0.1.0")
    app.state.db = Database(db_path or settings.db_path)
    app.state.token_hashes = load_token_hashes()

    app.include_router(jobs.router)
    app.include_router(leases.router)
    app.include_router(doctor.router)
    app.include_router(events.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
