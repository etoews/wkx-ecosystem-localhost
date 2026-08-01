"""CLI entry point. Run with `uv run wkx-ecosystem-localhost`."""

from __future__ import annotations

import threading
import webbrowser
from typing import Annotated

import typer
import uvicorn

from wkx_ecosystem_localhost._logging import configure as configure_logging
from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import Settings

# Deliberately not configurable: the board is loopback-only as a security
# property. It inventories the machine, so nothing on the network may see it.
_HOST = "127.0.0.1"

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
) -> None:
    """Serve the board on loopback."""
    settings = Settings()
    bind_port = port if port is not None else settings.port
    url = f"http://{_HOST}:{bind_port}/"
    if open_browser:
        # Give uvicorn a moment to bind before the browser asks.
        threading.Timer(0.7, webbrowser.open, args=(url,)).start()
    typer.echo(f"Serving the board at {url}")
    uvicorn.run(create_app(settings), host=_HOST, port=bind_port, log_config=None)


def main() -> None:
    """Console-script entry point referenced from pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
