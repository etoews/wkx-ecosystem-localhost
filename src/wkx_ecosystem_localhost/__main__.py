"""CLI entry point. Run with `uv run wkx-ecosystem-localhost`."""

from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path
from socket import socket
from typing import Annotated

import typer
import uvicorn
from uvicorn.supervisors import ChangeReload

from wkx_ecosystem_localhost._logging import configure as configure_logging
from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import (
    Settings,
    check_configuration,
    check_environment,
    resolve_config_file,
)
from wkx_ecosystem_localhost.view import resolve_view_file

# Deliberately not configurable: the board is loopback-only as a security
# property. It inventories the machine, so nothing on the network may see it.
_HOST = "127.0.0.1"

# The package source, the only tree --reload watches for code changes. Watching
# just this directory is what keeps a test edit, a standards/ file, or any other
# file outside the package from bouncing the always-on instance: uvicorn collapses
# a watched child into a watched ancestor and matches include globs right-anchored,
# so adding the config file's parent (the repo root) would silently pull the whole
# repo — tests, standards/, .venv — into the watch. The config file is watched on
# its own by _ConfigWatch instead (see _ConfigAwareReload).
_PACKAGE_DIR = Path(__file__).resolve().parent

# Import-string factory uvicorn's reloader re-imports on each change.
_RELOAD_TARGET = "wkx_ecosystem_localhost.app:create_app_from_env"


def _file_mtime(path: Path | None) -> float | None:
    """The file's modification time, or None if it is absent or unreadable.

    A missing configuration file is normal (the board runs on its defaults), so a
    stat failure is a state, not an error: the caller compares this value across
    polls and a None -> float transition (the file being created) reads as a change.
    """
    if path is None:
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


class _ConfigWatch:
    """Polls one configuration file's mtime and reports each change exactly once.

    uvicorn's own reloader watches whole directory trees for ``*.py`` files, which
    cannot pick up a single TOML that lives outside the watched package source
    without also watching every other file beside it. This watches just the one
    file: each :meth:`changed` call after the file is written (or created, or
    removed) returns its path once, then None until it changes again.
    """

    def __init__(self, config_file: Path | None) -> None:
        # Resolve to an absolute path so the stat and the reload log line stay
        # stable regardless of the working directory.
        self._config_file = config_file.resolve() if config_file is not None else None
        self._mtime = _file_mtime(self._config_file)

    def changed(self) -> Path | None:
        """Return the configuration file's path if it changed since the last call."""
        if self._config_file is None:
            return None
        current = _file_mtime(self._config_file)
        if current != self._mtime:
            self._mtime = current
            return self._config_file
        return None


class _ConfigAwareReload(ChangeReload):  # ty: ignore[unsupported-base]
    """uvicorn's reloader, extended to also restart on a configuration-file change.

    The base reloader (WatchFiles if installed, else StatReload) watches the package
    source for code changes. This layers a poll of the single configuration file on
    top, so a TOML save restarts the always-on instance exactly as a code edit does,
    without widening the directory watch to the repo root. The configuration is
    re-read by the factory on the restart.
    """

    def __init__(
        self,
        config: uvicorn.Config,
        target: object,
        sockets: list[socket],
        *,
        config_file: Path | None,
    ) -> None:
        super().__init__(config, target, sockets)
        self._config_watch = _ConfigWatch(config_file)

    def should_restart(self) -> list[Path] | None:
        """Restart on a package-source change (via the base) or a configuration change."""
        changed = super().should_restart()
        if changed:
            return changed
        config_changed = self._config_watch.changed()
        return [config_changed] if config_changed is not None else None


def _run_reloader(config: uvicorn.Config, config_file: Path | None) -> None:
    """Bind the socket and run the configuration-aware reloader.

    Mirrors the reload path of ``uvicorn.run`` (bind a socket, run the reloader over
    a server target), but substitutes :class:`_ConfigAwareReload` so a configuration
    save is watched alongside the package source. Kept as a seam the CLI tests stub,
    so they exercise the wiring without binding a real socket.
    """
    server = uvicorn.Server(config)
    sock = config.bind_socket()
    _ConfigAwareReload(config, target=server.run, sockets=[sock], config_file=config_file).run()


app = typer.Typer(
    help="Read-only localhost board that inventories this dev machine's ecosystem.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root() -> None:
    """Configure logging before any subcommand runs."""
    configure_logging()


@app.command()
def serve(
    port: Annotated[
        int | None,
        typer.Option(help="Port to bind on 127.0.0.1. Defaults to the configured port."),
    ] = None,
    open_browser: Annotated[
        bool,
        typer.Option("--open-browser", help="Open the board in the default browser."),
    ] = False,
    reload: Annotated[
        bool,
        typer.Option(
            "--reload",
            help="Restart on code changes. Development only; not for the always-on service.",
        ),
    ] = False,
) -> None:
    """Serve the board on loopback."""
    check_environment()
    config_file = resolve_config_file(os.environ)
    check_configuration(config_file)
    settings = Settings()
    view_file = resolve_view_file(os.environ)
    bind_port = port if port is not None else settings.port
    url = f"http://{_HOST}:{bind_port}/"
    if open_browser:
        # Give uvicorn a moment to bind before the browser asks.
        threading.Timer(0.7, webbrowser.open, args=(url,)).start()
    typer.echo(f"Serving the board at {url}")
    if reload:
        # The reloader re-imports the app in a subprocess on each change, so it
        # needs an import-string factory (not a built instance). Only the package
        # source is watched for code changes; the configuration file is watched
        # separately by _ConfigAwareReload, so a TOML save restarts the instance
        # without dragging the whole repo (tests, standards/, .venv) into the watch.
        # Config is re-read on the restart via the factory.
        config = uvicorn.Config(
            _RELOAD_TARGET,
            factory=True,
            reload=True,
            reload_dirs=[str(_PACKAGE_DIR)],
            host=_HOST,
            port=bind_port,
            log_config=None,
        )
        _run_reloader(config, config_file)
    else:
        uvicorn.run(
            create_app(
                settings,
                config_file=config_file,
                view_file=view_file,
                bound_port=bind_port,
            ),
            host=_HOST,
            port=bind_port,
            log_config=None,
        )


def main() -> None:
    """Console-script entry point referenced from pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
