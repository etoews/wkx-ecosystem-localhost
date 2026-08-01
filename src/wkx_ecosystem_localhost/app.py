"""FastAPI application factory serving the board shell and the JSON API."""

import logging
from collections.abc import Iterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from wkx_ecosystem_localhost import sse
from wkx_ecosystem_localhost.collectors.fetch import stream_fetches
from wkx_ecosystem_localhost.collectors.submodules import (
    collect_submodules,
    stream_submodule_probes,
)
from wkx_ecosystem_localhost.collectors.toolchains import collect_toolchains
from wkx_ecosystem_localhost.collectors.workspace import collect_workspace, discover_repos
from wkx_ecosystem_localhost.config import Settings
from wkx_ecosystem_localhost.machine import Machine, RealMachine
from wkx_ecosystem_localhost.models import (
    SubmoduleSection,
    ToolchainsSection,
    WorkspaceSection,
)

logger = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"


def create_app(
    settings: Settings, *, machine: Machine | None = None, home: Path | None = None
) -> FastAPI:
    """Build the application.

    Collectors read their configuration from ``settings`` and reach the host only
    through ``machine`` (the seam), so tests inject a fake and a synthetic ``home``
    to drive the real app end to end without touching a real machine. Production
    defaults to the ``RealMachine`` and the actual home directory.

    Args:
        settings: Typed configuration, built once at the entry point.
        machine: The machine seam. Defaults to ``RealMachine``.
        home: Home directory used to relativise displayed paths. Defaults to the
            real home.
    """
    app = FastAPI(title="WKX Ecosystem localhost")
    app.state.settings = settings
    app.state.machine = machine if machine is not None else RealMachine()
    app.state.home = home if home is not None else Path.home()

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        """Liveness probe for the board's own JS and for smoke tests."""
        return {"ok": True}

    @app.get("/api/workspace")
    def workspace() -> WorkspaceSection:
        """Discovered repos with status and redacted config for the workspace Section."""
        return collect_workspace(
            app.state.machine,
            settings.scan_roots,
            home=app.state.home,
            max_depth=settings.scan_depth,
        )

    @app.get("/api/workspace/fetch")
    def workspace_fetch() -> StreamingResponse:
        """Stream each repo's ahead/behind as its background fetch lands (SSE).

        The board opens this with a native ``EventSource`` on load. Each repo is
        fetched on a bounded pool and its counts are pushed the moment they are
        ready, so the one slow truth fills in progressively without blocking the
        rest of the board. This is the only write the app performs, and it
        touches remote-tracking refs only.
        """
        repo_paths = discover_repos(
            app.state.machine, settings.scan_roots, max_depth=settings.scan_depth
        )

        def events() -> Iterator[str]:
            for event in stream_fetches(
                app.state.machine,
                repo_paths,
                home=app.state.home,
                max_workers=settings.fetch_workers,
                timeout=settings.fetch_timeout,
            ):
                yield sse.pack(event)
            yield sse.done()

        return StreamingResponse(
            events(),
            media_type=sse.EVENT_STREAM,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/submodules")
    def submodules() -> SubmoduleSection:
        """Each discovered repo's submodules with pins resolved for the submodules Section.

        ``latest`` and ``behind`` arrive over the SSE probe below; this returns the
        pins straight away so the page renders without waiting on any network.
        """
        repo_paths = discover_repos(
            app.state.machine, settings.scan_roots, max_depth=settings.scan_depth
        )
        return collect_submodules(app.state.machine, repo_paths, home=app.state.home)

    @app.get("/api/submodules/probe")
    def submodules_probe() -> StreamingResponse:
        """Stream each submodule's latest release and tags-behind as its listing lands (SSE).

        The board opens this with a native ``EventSource`` after the pins render.
        Each submodule's remote tags are listed on a bounded pool and its numbers
        are pushed the moment they are ready, so the network truth fills in
        progressively without blocking the board. No submodule objects are fetched.
        """
        repo_paths = discover_repos(
            app.state.machine, settings.scan_roots, max_depth=settings.scan_depth
        )

        def events() -> Iterator[str]:
            for event in stream_submodule_probes(
                app.state.machine,
                repo_paths,
                home=app.state.home,
                max_workers=settings.fetch_workers,
                ls_remote_timeout=settings.fetch_timeout,
            ):
                yield sse.pack(event)
            yield sse.done()

        return StreamingResponse(
            events(),
            media_type=sse.EVENT_STREAM,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/toolchains")
    def toolchains() -> ToolchainsSection:
        """The Python and Node/TypeScript toolchain facts for the toolchains Section.

        Reuses the same repo discovery as the workspace so the per-repo Python
        pins and per-repo TypeScript line up with the repos already on the board.
        """
        repo_paths = discover_repos(
            app.state.machine, settings.scan_roots, max_depth=settings.scan_depth
        )
        return collect_toolchains(app.state.machine, repo_paths, home=app.state.home)

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    logger.debug("app created with %d scan root(s)", len(settings.scan_roots))
    return app
