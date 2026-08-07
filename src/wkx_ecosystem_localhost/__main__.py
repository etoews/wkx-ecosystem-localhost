"""CLI entry point. Run with `uv run wkx-ecosystem-localhost`."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from wkx_ecosystem_localhost._logging import configure as configure_logging
from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import Settings

# Deliberately not configurable: the board is loopback-only as a security
# property. It inventories the machine, so nothing on the network may see it.
_HOST = "127.0.0.1"

# The package source, watched by --reload so a code change restarts the server.
_PACKAGE_DIR = Path(__file__).resolve().parent

# Import-string factory uvicorn's reloader re-imports on each change.
_RELOAD_TARGET = "wkx_ecosystem_localhost.app:create_app_from_env"

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
    settings = Settings()
    bind_port = port if port is not None else settings.port
    url = f"http://{_HOST}:{bind_port}/"
    if open_browser:
        # Give uvicorn a moment to bind before the browser asks.
        threading.Timer(0.7, webbrowser.open, args=(url,)).start()
    typer.echo(f"Serving the board at {url}")
    if reload:
        # The reloader re-imports the app in a subprocess on each change, so it
        # needs an import-string factory (not a built instance) and the source
        # tree to watch. Config is re-read on restart via the factory.
        uvicorn.run(
            _RELOAD_TARGET,
            factory=True,
            reload=True,
            reload_dirs=[str(_PACKAGE_DIR)],
            host=_HOST,
            port=bind_port,
            log_config=None,
        )
    else:
        uvicorn.run(create_app(settings), host=_HOST, port=bind_port, log_config=None)


def main() -> None:
    """Console-script entry point referenced from pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
