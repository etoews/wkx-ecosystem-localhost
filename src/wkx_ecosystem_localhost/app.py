"""FastAPI application factory serving the board shell and the JSON API."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from wkx_ecosystem_localhost.config import Settings

logger = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings) -> FastAPI:
    """Build the application.

    Collectors added in later milestones read their configuration from
    app.state.settings; the factory takes Settings explicitly so tests can
    construct apps without touching the environment.
    """
    app = FastAPI(title="WKX Ecosystem localhost")
    app.state.settings = settings

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        """Liveness probe for the board's own JS and for smoke tests."""
        return {"ok": True}

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    logger.debug("app created with %d scan root(s)", len(settings.scan_roots))
    return app
