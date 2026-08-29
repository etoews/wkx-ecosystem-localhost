"""The /api/config route: a read-only effective-configuration view over HTTP.

Drives the real app end to end. Clients are built explicitly with a synthetic
home and, where a file is exercised, a TOML written to a tmp path, so the suite
never reads a real configuration file.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import Settings

HOME = Path("/home/someone")


def _client(*, config_file: Path | None, **settings_kwargs: object) -> TestClient:
    settings = Settings(_env_file=None, _config_file=config_file, **settings_kwargs)
    return TestClient(create_app(settings, home=HOME, config_file=config_file))


def test_config_reports_defaults_when_no_file() -> None:
    client = _client(config_file=None)

    body = client.get("/api/config").json()

    assert body["file"] is None
    assert body["found"] is False
    by_key = {item["key"]: item for item in body["values"]}
    assert by_key["port"]["value"] == "8787"
    assert all(item["source"] == "default" for item in body["values"])
    assert body["system_tools"]["source"] == "default"


def test_config_reports_file_values_and_their_source(tmp_path: Path) -> None:
    path = tmp_path / "wkx-ecosystem-localhost.toml"
    path.write_text("port = 9100\n")
    client = _client(config_file=path)

    body = client.get("/api/config").json()

    assert body["found"] is True
    by_key = {item["key"]: item for item in body["values"]}
    assert by_key["port"]["source"] == "file"
    assert by_key["port"]["value"] == "9100"
    # A key the file leaves alone still reads as a default.
    assert by_key["scan_depth"]["source"] == "default"


def test_config_relativises_scan_roots() -> None:
    client = _client(config_file=None, scan_roots=[HOME / "dev", HOME / "work"])

    body = client.get("/api/config").json()

    by_key = {item["key"]: item for item in body["values"]}
    assert by_key["scan_roots"]["value"] == "~/dev, ~/work"


def test_config_lists_system_tools_as_a_table() -> None:
    client = _client(config_file=None)

    body = client.get("/api/config").json()

    names = [tool["name"] for tool in body["system_tools"]["tools"]]
    assert "git" in names
    assert "docker" in names


def test_config_reports_empty_excludes_by_default() -> None:
    client = _client(config_file=None)

    body = client.get("/api/config").json()

    assert body["exclude"]["source"] == "default"
    assert body["exclude"]["globs"] == []


def test_config_reports_excludes_from_the_file(tmp_path: Path) -> None:
    path = tmp_path / "wkx-ecosystem-localhost.toml"
    path.write_text('exclude = ["~/dev/experiments", "**/vendor"]\n')
    client = _client(config_file=path)

    body = client.get("/api/config").json()

    assert body["exclude"]["source"] == "file"
    assert body["exclude"]["globs"] == ["~/dev/experiments", "**/vendor"]


def test_config_relativises_the_file_path(tmp_path: Path) -> None:
    path = HOME / "wkx-ecosystem-localhost.toml"
    # No real file at HOME; the route still reports the ~-relative path it would read.
    settings = Settings(_env_file=None, _config_file=None)
    client = TestClient(create_app(settings, home=HOME, config_file=path))

    body = client.get("/api/config").json()

    assert body["file"] == "~/wkx-ecosystem-localhost.toml"
    assert body["found"] is False


def test_config_has_no_write_path() -> None:
    client = _client(config_file=None)

    # The board reports its configuration; it never writes it.
    assert client.post("/api/config").status_code == 405
    assert client.put("/api/config").status_code == 405
