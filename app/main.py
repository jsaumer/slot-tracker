"""FastAPI application factory and router registration."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import bonuses, dashboard, export, games, hunts, sessions

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(title="slot-tracker", docs_url="/docs", redoc_url=None)

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe. Returns 200 with no database dependency —
        the Swarm healthcheck calls this with stdlib urllib (CLAUDE.md
        constraint 3)."""
        return {"status": "ok"}

    app.include_router(bonuses.router)
    app.include_router(dashboard.router)
    app.include_router(games.router)
    app.include_router(hunts.router)
    app.include_router(sessions.router)
    app.include_router(export.router)

    return app


app = create_app()
