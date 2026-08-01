"""Settings behaviour: computed defaults, env overrides, and typo rejection."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from wkx_ecosystem_localhost.config import Settings


def test_defaults_are_computed_not_literal() -> None:
    settings = Settings(_env_file=None)

    assert settings.scan_roots == [Path.home() / "dev"]
    assert settings.scan_depth == 8
    assert settings.port == 8787


def test_env_overrides_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_PORT", "9001")

    settings = Settings(_env_file=None)

    assert settings.port == 9001


def test_env_overrides_scan_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_SCAN_ROOTS", '["/somewhere/else"]')

    settings = Settings(_env_file=None)

    assert settings.scan_roots == [Path("/somewhere/else")]


def test_default_system_tools_is_the_generic_list() -> None:
    settings = Settings(_env_file=None)

    names = [tool.name for tool in settings.system_tools]
    assert names == [
        "git",
        "gh",
        "uv",
        "ruff",
        "ty",
        "pre-commit",
        "docker",
        "terraform",
        "aws",
        "code",
        "node",
    ]
    # Each tool defaults to the --version probe every generic tool understands.
    assert all(tool.version_args == ("--version",) for tool in settings.system_tools)


def test_env_extends_system_tools_without_code_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "WKX_ECO_SYSTEM_TOOLS",
        '[{"name": "kubectl"}, {"name": "just", "version_args": ["--version"]}]',
    )

    settings = Settings(_env_file=None)

    assert [tool.name for tool in settings.system_tools] == ["kubectl", "just"]
    assert settings.system_tools[0].argv() == ("kubectl", "--version")


def test_unknown_setting_is_rejected() -> None:
    # extra="forbid" guards explicit construction. Note: pydantic-settings'
    # env source reads declared fields only, so a misspelt WKX_ECO_* variable
    # is silently ignored rather than rejected.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, prot=9001)
