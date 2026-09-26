"""The serve CLI wiring: default binds a built app; --reload uses uvicorn's reloader.

uvicorn.run is stubbed so these exercise how serve calls it, never a real socket.
"""

from __future__ import annotations

import contextlib
import logging
import os
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
def restore_environ() -> Iterator[None]:
    """Restore the process environment around each test.

    ``serve`` exports the bound port into ``os.environ`` for the reloader worker, a
    direct mutation monkeypatch cannot undo. Snapshot and restore so that export
    never leaks the bound port into another module's fixtures.
    """
    saved = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


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


ReloaderCall = tuple[uvicorn.Config, Path | None]


@pytest.fixture
def reloader_calls(monkeypatch: pytest.MonkeyPatch) -> list[ReloaderCall]:
    """Capture the reloader wiring instead of binding a socket and running it.

    The --reload path builds a uvicorn.Config and hands it, with the config file, to
    _run_reloader. Stubbing that seam exercises the wiring — which trees are watched,
    which file is polled — without a real socket or a running reloader.
    """
    calls: list[ReloaderCall] = []
    monkeypatch.setattr(
        cli, "_run_reloader", lambda config, config_file: calls.append((config, config_file))
    )
    return calls


def test_serve_default_binds_a_built_app(uvicorn_calls: list[Call]) -> None:
    result = runner.invoke(cli.app, ["serve"])

    assert result.exit_code == 0
    (args, kwargs) = uvicorn_calls[0]
    assert isinstance(args[0], FastAPI)  # a built app, not an import string
    assert not kwargs.get("reload", False)  # the production path never reloads


def test_serve_default_bounds_the_graceful_shutdown(uvicorn_calls: list[Call]) -> None:
    result = runner.invoke(cli.app, ["serve"])

    assert result.exit_code == 0
    (_args, kwargs) = uvicorn_calls[0]
    # An open SSE stream never closes on its own, so an unbounded wait would hang
    # the shutdown for as long as a board tab stays open.
    assert kwargs["timeout_graceful_shutdown"] == cli._GRACEFUL_SHUTDOWN_S


def test_serve_reload_bounds_the_graceful_shutdown(reloader_calls: list[ReloaderCall]) -> None:
    result = runner.invoke(cli.app, ["serve", "--reload"])

    assert result.exit_code == 0
    (config, _config_file) = reloader_calls[0]
    # Each reload shuts the old worker down; an open SSE stream must not wedge it.
    assert config.timeout_graceful_shutdown == cli._GRACEFUL_SHUTDOWN_S


def test_serve_reload_uses_the_factory_import_string(reloader_calls: list[ReloaderCall]) -> None:
    result = runner.invoke(cli.app, ["serve", "--reload"])

    assert result.exit_code == 0
    (config, _config_file) = reloader_calls[0]
    assert config.app == "wkx_ecosystem_localhost.app:create_app_from_env"
    assert config.factory is True
    assert config.reload is True


def test_serve_reload_watches_only_the_package_source(reloader_calls: list[ReloaderCall]) -> None:
    result = runner.invoke(cli.app, ["serve", "--reload"])

    assert result.exit_code == 0
    (config, _config_file) = reloader_calls[0]
    # Only the package source is watched for code changes. Anything else — a test, a
    # standards/ file, a top-level .py, .venv — sits outside it and cannot bounce the
    # server. uvicorn resolves reload_dirs to absolute directories.
    watched = [str(path) for path in config.reload_dirs]
    assert watched == [str(cli._PACKAGE_DIR)]
    # The repo root (the config file's own directory) is deliberately not watched:
    # watching it would drag every .py in the repo into the reload.
    assert str(Path.cwd()) not in watched


def test_serve_reload_hands_the_config_file_to_the_reloader(
    reloader_calls: list[ReloaderCall], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "wkx-ecosystem-localhost.toml"
    monkeypatch.setenv("WKX_ECO_LOCAL_CONFIG_FILE", str(config))

    result = runner.invoke(cli.app, ["serve", "--reload"])

    assert result.exit_code == 0
    (_config, config_file) = reloader_calls[0]
    # serve resolves the config file from the environment and hands it to the
    # reloader, which polls it (not reload_dirs) so a TOML save restarts the instance
    # without widening the directory watch.
    assert config_file == config


def test_serve_reload_binds_the_requested_port(reloader_calls: list[ReloaderCall]) -> None:
    result = runner.invoke(cli.app, ["serve", "--reload", "--port", "9123"])

    assert result.exit_code == 0
    (config, _config_file) = reloader_calls[0]
    assert config.port == 9123


def test_serve_reload_exports_the_bound_port_for_the_worker_guard(
    reloader_calls: list[ReloaderCall], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The reloader worker re-imports create_app_from_env with no arguments, so its
    # only channel to --port is the environment. serve exports the bound port there,
    # so the worker binds it AND builds the write guard's Host allow-list for it;
    # otherwise every browser request to a non-default --port is refused (the
    # always-on install renders exactly `serve --reload --port N`). delenv here so
    # monkeypatch removes whatever serve set, keeping the export out of later tests.
    port_env = f"{cli.ENV_PREFIX}PORT"
    monkeypatch.delenv(port_env, raising=False)

    result = runner.invoke(cli.app, ["serve", "--reload", "--port", "9123"])

    assert result.exit_code == 0
    assert os.environ[port_env] == "9123"
    # The factory the worker imports now builds its guard for the bound port.
    guard_app = create_app_from_env()
    assert "127.0.0.1:9123" in guard_app.state.allowed_hosts


def _serve_output(result: object) -> str:
    """The CLI's combined stdout and stderr, however this Click version splits them."""
    out = getattr(result, "output", "") or ""
    with contextlib.suppress(ValueError):
        out += getattr(result, "stderr", "") or ""
    return out


def test_serve_rejects_an_unknown_env_variable(
    uvicorn_calls: list[Call], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_PROT", "9001")

    result = runner.invoke(cli.app, ["serve"])

    # The startup scan fails fast before uvicorn is ever asked to bind, with a clean
    # message and exit 1 rather than a traceback.
    assert result.exit_code == 1
    assert uvicorn_calls == []
    assert "WKX_ECO_LOCAL_PROT" in _serve_output(result)
    assert "Traceback" not in _serve_output(result)


def test_serve_reports_a_toml_syntax_error_without_a_traceback(
    uvicorn_calls: list[Call], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad = tmp_path / "wkx-ecosystem-localhost.toml"
    bad.write_text("port = = 1\n")
    monkeypatch.setenv("WKX_ECO_LOCAL_CONFIG_FILE", str(bad))

    result = runner.invoke(cli.app, ["serve"])

    assert result.exit_code == 1
    assert uvicorn_calls == []
    output = _serve_output(result)
    assert str(bad) in output
    assert "does not parse" in output
    assert "Traceback" not in output


def test_serve_reports_an_invalid_value_naming_the_key(
    uvicorn_calls: list[Call], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad = tmp_path / "wkx-ecosystem-localhost.toml"
    bad.write_text('port = "not a number"\n')
    monkeypatch.setenv("WKX_ECO_LOCAL_CONFIG_FILE", str(bad))

    result = runner.invoke(cli.app, ["serve"])

    assert result.exit_code == 1
    assert uvicorn_calls == []
    output = _serve_output(result)
    assert "port" in output
    assert "Traceback" not in output


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


# _ConfigWatch is the runtime half of the fix: the reloader polls it every cycle so a
# TOML save restarts the always-on instance. These exercise that matching against a
# real file on disk, not the reloader's arguments, which is where the M10 gap hid.


def _bump_mtime(path: Path) -> None:
    """Move a file's mtime a second ahead, so a change shows whatever the clock resolution."""
    stamp = path.stat().st_mtime + 1
    os.utime(path, (stamp, stamp))


def test_config_watch_reports_no_change_when_the_file_is_untouched(tmp_path: Path) -> None:
    config_file = tmp_path / "wkx-ecosystem-localhost.toml"
    config_file.write_text("# config\n")
    watch = cli._ConfigWatch(config_file)

    assert watch.changed() is None


def test_config_watch_reports_a_save_once(tmp_path: Path) -> None:
    config_file = tmp_path / "wkx-ecosystem-localhost.toml"
    config_file.write_text("port = 8787\n")
    watch = cli._ConfigWatch(config_file)

    config_file.write_text("port = 8788\n")
    _bump_mtime(config_file)

    assert watch.changed() == config_file.resolve()
    assert watch.changed() is None  # the change is consumed; no spurious re-reload


def test_config_watch_reports_the_file_being_created(tmp_path: Path) -> None:
    config_file = tmp_path / "wkx-ecosystem-localhost.toml"
    watch = cli._ConfigWatch(config_file)  # constructed before the file exists

    config_file.write_text("# now it exists\n")

    assert watch.changed() == config_file.resolve()


def test_config_watch_reports_the_file_being_removed(tmp_path: Path) -> None:
    config_file = tmp_path / "wkx-ecosystem-localhost.toml"
    config_file.write_text("# config\n")
    watch = cli._ConfigWatch(config_file)

    config_file.unlink()

    assert watch.changed() == config_file.resolve()


def test_config_watch_never_reports_when_the_file_source_is_off() -> None:
    watch = cli._ConfigWatch(None)  # the suite and any --config-less run opt out

    assert watch.changed() is None
