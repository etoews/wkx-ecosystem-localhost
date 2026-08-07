"""The serve CLI wiring: default binds a built app; --reload uses uvicorn's reloader.

uvicorn.run is stubbed so these exercise how serve calls it, never a real socket.
"""

from __future__ import annotations

from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from typer.testing import CliRunner

from wkx_ecosystem_localhost import __main__ as cli

runner = CliRunner()

Call = tuple[tuple[Any, ...], dict[str, Any]]


@pytest.fixture
def uvicorn_calls(monkeypatch: pytest.MonkeyPatch) -> list[Call]:
    """Capture uvicorn.run arguments instead of binding a socket."""
    calls: list[Call] = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    return calls


def test_serve_default_binds_a_built_app(uvicorn_calls: list[Call]) -> None:
    result = runner.invoke(cli.app, ["serve"])

    assert result.exit_code == 0
    (args, kwargs) = uvicorn_calls[0]
    assert isinstance(args[0], FastAPI)  # a built app, not an import string
    assert not kwargs.get("reload", False)  # the production path never reloads


def test_serve_reload_uses_the_factory_import_string(uvicorn_calls: list[Call]) -> None:
    result = runner.invoke(cli.app, ["serve", "--reload"])

    assert result.exit_code == 0
    (args, kwargs) = uvicorn_calls[0]
    assert args[0] == "wkx_ecosystem_localhost.app:create_app_from_env"
    assert kwargs["factory"] is True
    assert kwargs["reload"] is True


def test_serve_reload_watches_the_package_source(uvicorn_calls: list[Call]) -> None:
    result = runner.invoke(cli.app, ["serve", "--reload"])

    assert result.exit_code == 0
    (_args, kwargs) = uvicorn_calls[0]
    watched = [str(path) for path in kwargs["reload_dirs"]]
    assert any(path.endswith("wkx_ecosystem_localhost") for path in watched)


def test_reload_factory_builds_the_real_app() -> None:
    from wkx_ecosystem_localhost.app import create_app_from_env

    assert isinstance(create_app_from_env(), FastAPI)
