"""The serve CLI wiring: default binds a built app; --reload uses uvicorn's reloader.

uvicorn.run is stubbed so these exercise how serve calls it, never a real socket.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from typer.testing import CliRunner

from wkx_ecosystem_localhost import __main__ as cli
from wkx_ecosystem_localhost.app import create_app_from_env
from wkx_ecosystem_localhost.exceptions import ConfigError

runner = CliRunner()

Call = tuple[tuple[Any, ...], dict[str, Any]]


@pytest.fixture(autouse=True)
def preserve_root_logging() -> Iterator[None]:
    """Restore root logging around each test.

    Invoking the CLI callback and the reload factory both call configure(), which
    clears and replaces the root logger's handlers. Snapshot and restore so this
    module never leaks logging state into the rest of the suite.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        yield
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


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


def test_serve_reload_watches_the_config_file(uvicorn_calls: list[Call]) -> None:
    result = runner.invoke(cli.app, ["serve", "--reload"])

    assert result.exit_code == 0
    (_args, kwargs) = uvicorn_calls[0]
    # The default config file joins the watch: its directory is watched and its
    # name is an include glob, so a configuration edit restarts the instance.
    watched = [str(path) for path in kwargs["reload_dirs"]]
    includes = kwargs["reload_includes"]
    assert "wkx-ecosystem-localhost.toml" in includes
    assert "*.py" in includes  # the package source still triggers a reload too
    config_dir = str(Path("wkx-ecosystem-localhost.toml").resolve().parent)
    assert any(path == config_dir for path in watched)


def test_serve_rejects_an_unknown_env_variable(
    uvicorn_calls: list[Call], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_PROT", "9001")

    result = runner.invoke(cli.app, ["serve"])

    # The startup scan fails fast before uvicorn is ever asked to bind.
    assert result.exit_code != 0
    assert uvicorn_calls == []
    assert "WKX_ECO_LOCAL_PROT" in str(result.exception)


def test_reload_factory_builds_the_real_app() -> None:
    assert isinstance(create_app_from_env(), FastAPI)


def test_reload_factory_rejects_an_unknown_env_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_PROT", "9001")

    with pytest.raises(ConfigError):
        create_app_from_env()


def test_reload_factory_formats_worker_logs(capsys: pytest.CaptureFixture[str]) -> None:
    # The reload worker imports the factory but never runs the CLI callback, so the
    # factory must configure logging itself. Otherwise the worker's warnings fall
    # through to logging.lastResort: bare, on stderr, WARNING and above only.
    logging.getLogger().handlers.clear()  # a fresh, unconfigured worker

    create_app_from_env()
    logging.getLogger("wkx_ecosystem_localhost.machine").warning("probe program not found: tsc")

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "wkx_ecosystem_localhost.machine" in out
    assert "probe program not found: tsc" in out
