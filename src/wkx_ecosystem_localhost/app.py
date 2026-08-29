"""FastAPI application factory serving the board shell and the JSON API."""

import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TypeVar

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from wkx_ecosystem_localhost import sse
from wkx_ecosystem_localhost._logging import configure as configure_logging
from wkx_ecosystem_localhost.cache import TtlCache
from wkx_ecosystem_localhost.collectors.claude import collect_claude
from wkx_ecosystem_localhost.collectors.docker import collect_docker
from wkx_ecosystem_localhost.collectors.editor import collect_editor
from wkx_ecosystem_localhost.collectors.fetch import stream_fetches
from wkx_ecosystem_localhost.collectors.flags import collect_flags
from wkx_ecosystem_localhost.collectors.footprint import collect_footprint
from wkx_ecosystem_localhost.collectors.git_config import collect_git_config
from wkx_ecosystem_localhost.collectors.homebrew import collect_homebrew
from wkx_ecosystem_localhost.collectors.submodules import (
    CURL_TIMEOUT_S,
    collect_submodules,
    stream_submodule_probes,
)
from wkx_ecosystem_localhost.collectors.system import collect_system_tools
from wkx_ecosystem_localhost.collectors.toolchains import collect_toolchains
from wkx_ecosystem_localhost.collectors.workspace import DiscoveryCache, collect_workspace
from wkx_ecosystem_localhost.config import (
    ConfigView,
    Settings,
    check_environment,
    describe,
    resolve_config_file,
)
from wkx_ecosystem_localhost.machine import Machine, RealMachine
from wkx_ecosystem_localhost.models import (
    ClaudeSection,
    DockerSection,
    EditorSection,
    FlagsSection,
    FootprintSection,
    GitConfigSection,
    HomebrewSection,
    Section,
    SubmoduleSection,
    SystemToolsSection,
    ToolchainsSection,
    WorkspaceSection,
)

logger = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"

_Route = TypeVar("_Route", bound=Callable[..., object])


class _NoCacheStaticFiles(StaticFiles):
    """Static files that always revalidate, so the board never runs stale assets.

    The board is a live dashboard, often served with ``--reload``. A browser that
    heuristically caches ``app.js`` or ``styles.css`` (neither carries an explicit
    freshness lifetime) would keep running old code after a change, so a newly
    shipped panel would sit forever on its placeholder. ``no-cache`` forces a
    conditional request on every load: an unchanged asset still 304s cheaply on its
    ETag, a changed one is re-fetched.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(
    settings: Settings,
    *,
    machine: Machine | None = None,
    home: Path | None = None,
    config_file: Path | None = None,
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
        config_file: The TOML the settings were read from, reported by
            ``/api/config``. Defaults to None (no file), so the suite never reads a
            real file; the entry point passes the resolved path in production.
    """
    app = FastAPI(title="WKX Ecosystem localhost")
    app.state.settings = settings
    app.state.machine = machine if machine is not None else RealMachine()
    app.state.home = home if home is not None else Path.home()
    app.state.config_file = config_file
    # The footprint probe walks whole trees with ``du``, so its Section is computed
    # synchronously behind a short-lived cache rather than on every request.
    app.state.footprint_cache = TtlCache[FootprintSection](settings.footprint_cache_ttl)
    # Repo discovery is shared behind its own cache so one board load walks the scan
    # roots once, no matter how many routes and the Flag layer ask for the repos.
    app.state.discovery_cache = DiscoveryCache(settings.discovery_cache_ttl)

    # The Sections switched off in configuration. An Off Section's route is never
    # registered below, so ``/api/<section>`` 404s and its Collector never runs.
    off = set(settings.sections_off)

    def _section_route(section: Section, path: str) -> Callable[[_Route], _Route]:
        """Register a GET route only when its Section is on.

        An Off Section's route is never wired to the router, so ``/api/<section>``
        returns 404 and its Collector never runs. The handler is still defined (a
        harmless closure); it is simply not attached, so the Section leaves every
        surface at once. ``/api/config`` and ``/api/flags`` are deliberately not
        gated: config is the board's own self-description that the client boots
        from, and flags is the cross-cutting layer, not a Section.
        """

        def register(func: _Route) -> _Route:
            if section not in off:
                app.get(path)(func)
            return func

        return register

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        """Liveness probe for the board's own JS and for smoke tests."""
        return {"ok": True}

    @_section_route(Section.WORKSPACE, "/api/workspace")
    def workspace() -> WorkspaceSection:
        """Discovered repos with status and redacted config for the workspace Section."""
        return collect_workspace(
            app.state.machine,
            settings.scan_roots,
            home=app.state.home,
            max_depth=settings.scan_depth,
            excludes=settings.exclude,
            discovery=app.state.discovery_cache,
        )

    @_section_route(Section.WORKSPACE, "/api/workspace/fetch")
    def workspace_fetch() -> StreamingResponse:
        """Stream each repo's ahead/behind as its background fetch lands (SSE).

        The board opens this with a native ``EventSource`` on load. Each repo is
        fetched on a bounded pool and its counts are pushed the moment they are
        ready, so the one slow truth fills in progressively without blocking the
        rest of the board. This is the only write the app performs, and it
        touches remote-tracking refs only.
        """
        repo_paths = app.state.discovery_cache.discover(
            app.state.machine,
            settings.scan_roots,
            home=app.state.home,
            max_depth=settings.scan_depth,
            excludes=settings.exclude,
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

    @_section_route(Section.WORKSPACE, "/api/submodules")
    def submodules() -> SubmoduleSection:
        """Each discovered repo's submodules with pins resolved for the submodules Section.

        ``latest`` and ``behind`` arrive over the SSE probe below; this returns the
        pins straight away so the page renders without waiting on any network.
        """
        repo_paths = app.state.discovery_cache.discover(
            app.state.machine,
            settings.scan_roots,
            home=app.state.home,
            max_depth=settings.scan_depth,
            excludes=settings.exclude,
        )
        return collect_submodules(app.state.machine, repo_paths, home=app.state.home)

    @_section_route(Section.WORKSPACE, "/api/submodules/probe")
    def submodules_probe() -> StreamingResponse:
        """Stream each submodule's latest release and tags-behind as its listing lands (SSE).

        The board opens this with a native ``EventSource`` after the pins render.
        Each submodule's remote tags are listed on a bounded pool and its numbers
        are pushed the moment they are ready, so the network truth fills in
        progressively without blocking the board. No submodule objects are fetched.
        """
        repo_paths = app.state.discovery_cache.discover(
            app.state.machine,
            settings.scan_roots,
            home=app.state.home,
            max_depth=settings.scan_depth,
            excludes=settings.exclude,
        )

        def events() -> Iterator[str]:
            for event in stream_submodule_probes(
                app.state.machine,
                repo_paths,
                home=app.state.home,
                max_workers=settings.fetch_workers,
                ls_remote_timeout=settings.fetch_timeout,
                # The release lookup is a best-effort augment, so bound it to its
                # own ceiling rather than the full fetch budget: it must not double
                # a GitHub submodule's worst-case probe tail behind the ls-remote.
                curl_timeout=min(settings.fetch_timeout, CURL_TIMEOUT_S),
            ):
                yield sse.pack(event)
            yield sse.done()

        return StreamingResponse(
            events(),
            media_type=sse.EVENT_STREAM,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @_section_route(Section.TOOLCHAINS, "/api/toolchains")
    def toolchains() -> ToolchainsSection:
        """The Python and Node/TypeScript toolchain facts for the toolchains Section.

        Reuses the same repo discovery as the workspace so the per-repo Python
        pins and per-repo TypeScript line up with the repos already on the board.
        """
        repo_paths = app.state.discovery_cache.discover(
            app.state.machine,
            settings.scan_roots,
            home=app.state.home,
            max_depth=settings.scan_depth,
            excludes=settings.exclude,
        )
        return collect_toolchains(app.state.machine, repo_paths, home=app.state.home)

    @_section_route(Section.SYSTEM, "/api/system")
    def system() -> SystemToolsSection:
        """Each configured developer CLI as present-with-version or missing.

        The tools probed come straight from ``settings``, so a machine extends the
        Section by naming more tools in its configuration, not by changing code.
        """
        return collect_system_tools(app.state.machine, settings.system_tools)

    @_section_route(Section.CLAUDE, "/api/claude")
    def claude() -> ClaudeSection:
        """Skills, plugins, and MCP servers with their Origins for the claude Section.

        The Claude user config is read narrowly (only the MCP server subset), and no
        MCP server carries its command, URL, headers, or environment, so account,
        machine, telemetry, and credential fields never reach the board.
        """
        return collect_claude(app.state.machine, home=app.state.home)

    @_section_route(Section.GIT_CONFIG, "/api/git-config")
    def git_config() -> GitConfigSection:
        """The whole global gitconfig chain, every key shown with targeted redaction.

        Unlike the M1 per-repo view this is deny-nothing: every key is inventoried,
        with the secret-bearing families masked and URL credentials stripped (ADR
        0001). Include directives are lifted out and existence-checked, and the
        conflict, broken-include, credential, and no-identity anomalies are left for
        the Flag layer to badge.
        """
        return collect_git_config(app.state.machine, home=app.state.home)

    @_section_route(Section.HOMEBREW, "/api/homebrew")
    def homebrew() -> HomebrewSection:
        """Outdated formulae and casks, or Homebrew's absence, for the homebrew Section.

        The whole thing is one ``brew outdated`` probe: a machine without ``brew``
        reports absent as a plain fact rather than erroring the board.
        """
        return collect_homebrew(app.state.machine)

    @_section_route(Section.DOCKER, "/api/docker")
    def docker() -> DockerSection:
        """Daemon reachability, container and image counts, and reclaimable disk.

        A daemon that cannot be reached (down, or the CLI absent) renders as a fact
        on the board, never an error page; the counts stay at their empty defaults.
        """
        return collect_docker(app.state.machine)

    @_section_route(Section.EDITOR, "/api/editor")
    def editor() -> EditorSection:
        """VS Code's presence, CLI version, and installed extensions.

        A ``code`` CLI that cannot be run (absent, or not on the path) renders as a
        fact on the board, never an error page; the version and extensions stay at
        their empty defaults.
        """
        return collect_editor(app.state.machine)

    @_section_route(Section.FOOTPRINT, "/api/footprint")
    def footprint() -> FootprintSection:
        """Per-repo ``.venv``/``node_modules`` disk usage plus the Docker disk.

        The design calls for this synchronous probe to sit behind a cache: ``du``
        walks whole directory trees, so a fresh cached Section is returned straight
        away and the probe only re-runs once the TTL lapses. Repos are discovered
        with the same walk as the rest of the board so the rows line up.
        """
        cached = app.state.footprint_cache.get()
        if cached is not None:
            return cached
        repo_paths = app.state.discovery_cache.discover(
            app.state.machine,
            settings.scan_roots,
            home=app.state.home,
            max_depth=settings.scan_depth,
            excludes=settings.exclude,
        )
        section = collect_footprint(app.state.machine, repo_paths, home=app.state.home)
        app.state.footprint_cache.set(section)
        return section

    @app.get("/api/flags")
    def flags() -> FlagsSection:
        """Data-evident anomalies derived from the Sections, badged inline on the board.

        The cross-cutting Flag layer, not a panel: it runs the Collectors whose
        facts a Flag can be derived from and returns the open Flags, each naming the
        Section and row it badges. Flags that need a background fetch to be known
        (behind remote, submodule tags behind) are not here; the board raises those
        as its SSE events land.
        """
        return collect_flags(
            app.state.machine,
            settings,
            home=app.state.home,
            discovery=app.state.discovery_cache,
        )

    @app.get("/api/config")
    def config() -> ConfigView:
        """The effective configuration, each value tagged with where it came from.

        A read-only view for the config Section: every scalar setting and the
        system-tools probe list, paths relativised to ``~``, each tagged
        ``default``, ``file``, or ``env``, plus the file path and whether it was
        found. The board reports its configuration; it never writes it.
        """
        return describe(
            settings,
            home=app.state.home,
            config_file=app.state.config_file,
            environ=os.environ,
        )

    app.mount("/static", _NoCacheStaticFiles(directory=_STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    logger.debug("app created with %d scan root(s)", len(settings.scan_roots))
    return app


def create_app_from_env() -> FastAPI:
    """Zero-argument application factory for uvicorn's reloader.

    ``serve --reload`` runs uvicorn's autoreloader, which re-imports its target in a
    fresh subprocess on every code change, so it needs an import-string factory it
    can call with no arguments rather than a pre-built instance. Settings are read
    afresh here, so a reload also picks up configuration changes. Production
    (non-reload) serving keeps passing a built app to ``uvicorn.run`` directly.

    Logging is configured here because the reloader runs the app in a worker
    subprocess that imports this factory and never runs the CLI callback. Without
    it the worker's root logger has no handler and its records fall through to
    ``logging.lastResort`` (bare, on stderr, WARNING and above only).

    The environment is scanned here too, so a reload that picks up a misspelt
    ``WKX_ECO_LOCAL_*`` variable fails fast in the worker rather than serving on.
    """
    configure_logging()
    check_environment()
    config_file = resolve_config_file(os.environ)
    return create_app(Settings(), config_file=config_file)
