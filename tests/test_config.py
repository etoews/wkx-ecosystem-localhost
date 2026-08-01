"""Settings behaviour: computed defaults, env overrides, and typo rejection."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from wkx_ecosystem_localhost.config import Settings


def test_defaults_are_computed_not_literal() -> None:
    settings = Settings(_env_file=None)

    assert settings.scan_roots == [Path.home() / "dev"]
    assert settings.port == 8787


def test_env_overrides_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_PORT", "9001")

    settings = Settings(_env_file=None)

    assert settings.port == 9001


def test_env_overrides_scan_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_SCAN_ROOTS", '["/somewhere/else"]')

    settings = Settings(_env_file=None)

    assert settings.scan_roots == [Path("/somewhere/else")]


def test_unknown_setting_is_rejected() -> None:
    # extra="forbid" guards explicit construction. Note: pydantic-settings'
    # env source reads declared fields only, so a misspelt WKX_ECO_* variable
    # is silently ignored rather than rejected.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, prot=9001)
