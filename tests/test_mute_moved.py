"""Mute moved from the configuration into the View (ADR 0004).

``mute`` in the configuration file, or the ``WKX_ECO_LOCAL_MUTE`` environment
variable, now stops the board at startup with a message that names the View file,
rather than being read as configuration. ``/api/config`` no longer carries the
Mutes; ``/api/view`` does. Every file here is written to a tmp path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import Settings, check_configuration, check_environment
from wkx_ecosystem_localhost.exceptions import ConfigError

HOME = Path("/home/someone")


def test_mute_in_the_configuration_file_stops_the_board(tmp_path: Path) -> None:
    config_file = tmp_path / "wkx-ecosystem-localhost.toml"
    config_file.write_text('mute = [ { category = "brew-outdated" } ]\n')

    with pytest.raises(ConfigError) as excinfo:
        check_configuration(config_file)

    # The message names the View file, so the operator knows where Mute went.
    assert "wkx-ecosystem-localhost.view.toml" in str(excinfo.value)


def test_a_configuration_without_mute_starts(tmp_path: Path) -> None:
    config_file = tmp_path / "wkx-ecosystem-localhost.toml"
    config_file.write_text("port = 9100\n")

    check_configuration(config_file)  # does not raise


def test_no_configuration_file_starts() -> None:
    check_configuration(None)  # does not raise


def test_mute_environment_variable_stops_the_board() -> None:
    with pytest.raises(ConfigError) as excinfo:
        check_environment({"WKX_ECO_LOCAL_MUTE": '[{"category": "brew-outdated"}]'})

    assert "wkx-ecosystem-localhost.view.toml" in str(excinfo.value)


def test_config_api_no_longer_carries_mute(tmp_path: Path) -> None:
    view_file = tmp_path / "wkx-ecosystem-localhost.view.toml"
    settings = Settings(_env_file=None, _config_file=None, scan_roots=[tmp_path])
    client = TestClient(create_app(settings, home=HOME, view_file=view_file))

    body = client.get("/api/config").json()

    assert "mute" not in body
