"""The /api/view read and write routes, driven over HTTP.

Every client is built with a View file on a tmp path, never a real file, and the
write guard is exercised header by header. The board's first write route
(ADR 0004): loopback-only, one preference per call, atomic, and refused when the
file on disk does not parse.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx2
import pytest
from clients import loopback_client
from fastapi.testclient import TestClient
from support import make_settings

from wkx_ecosystem_localhost.app import create_app

# A permission bit does not stop root, so the unreadable-file tests skip there.
_skip_as_root = pytest.mark.skipif(
    getattr(os, "geteuid", lambda: 1)() == 0, reason="a permission bit does not stop root"
)

HOME = Path("/home/someone")
# The board binds 127.0.0.1 on the default port, so a same-origin write carries
# this Host; the guard's allow-list is built from the bound port.
HOST = "127.0.0.1:8787"
ORIGIN = "http://127.0.0.1:8787"


def _client(tmp_path: Path) -> TestClient:
    view_file = tmp_path / "wkx-ecosystem-localhost.view.toml"
    settings = make_settings(scan_roots=[tmp_path])
    return loopback_client(create_app(settings, home=HOME, view_file=view_file))


def _patch(client: TestClient, body: dict[str, Any], **headers: str) -> httpx2.Response:
    merged = {"host": HOST, **headers}
    return client.patch("/api/view", json=body, headers=merged)


# ---------- reading ----------


def test_get_view_is_empty_for_a_fresh_board(tmp_path: Path) -> None:
    body = _client(tmp_path).get("/api/view").json()

    assert body["theme"] is None
    assert body["sections_hidden"] == []
    assert body["found"] is False


def test_get_view_reports_the_file_line(tmp_path: Path) -> None:
    # The config Section reads file, found, and writable for its View-file line
    # (loaded / absent / not writable).
    body = _client(tmp_path).get("/api/view").json()

    assert body["file"].endswith("wkx-ecosystem-localhost.view.toml")
    assert body["found"] is False
    assert body["writable"] is True


def test_get_view_surfaces_an_unknown_key(tmp_path: Path) -> None:
    view_file = tmp_path / "wkx-ecosystem-localhost.view.toml"
    view_file.write_text('sections_hidden = ["docker", "nope"]\n')
    settings = make_settings(scan_roots=[tmp_path])
    client = loopback_client(create_app(settings, home=HOME, view_file=view_file))

    body = client.get("/api/view").json()

    assert body["sections_hidden"] == ["docker"]
    assert any("nope" in key for key in body["unknown_keys"])


# ---------- the round trip ----------


def test_patch_writes_and_get_reflects_it(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = _patch(client, {"field": "theme", "value": "dark"})

    assert response.status_code == 200
    assert response.json()["theme"] == "dark"
    assert client.get("/api/view").json()["theme"] == "dark"


def test_patch_hides_a_section(tmp_path: Path) -> None:
    client = _client(tmp_path)

    _patch(client, {"field": "sections_hidden", "panel": "docker", "on": True})

    assert client.get("/api/view").json()["sections_hidden"] == ["docker"]


# ---------- the write guard ----------


def test_write_with_no_origin_is_accepted(tmp_path: Path) -> None:
    # A non-browser client (curl) sends no Origin; the write is accepted.
    response = _patch(_client(tmp_path), {"field": "theme", "value": "dark"})

    assert response.status_code == 200


def test_write_with_a_same_origin_origin_is_accepted(tmp_path: Path) -> None:
    response = _patch(_client(tmp_path), {"field": "theme", "value": "dark"}, origin=ORIGIN)

    assert response.status_code == 200


def test_write_with_a_foreign_origin_is_refused(tmp_path: Path) -> None:
    response = _patch(
        _client(tmp_path), {"field": "theme", "value": "dark"}, origin="http://evil.example"
    )

    assert response.status_code == 403


def test_write_with_a_foreign_host_is_refused(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.patch(
        "/api/view", json={"field": "theme", "value": "dark"}, headers={"host": "evil.example"}
    )

    assert response.status_code == 403


def test_write_with_a_non_json_content_type_is_refused(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.patch(
        "/api/view",
        content="field=theme",
        headers={"host": HOST, "content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 403


def test_a_refused_write_leaves_no_file(tmp_path: Path) -> None:
    client = _client(tmp_path)

    _patch(client, {"field": "theme", "value": "dark"}, origin="http://evil.example")

    assert not (tmp_path / "wkx-ecosystem-localhost.view.toml").exists()


# ---------- validation and parse-failure ----------


def test_an_unknown_panel_is_rejected(tmp_path: Path) -> None:
    response = _patch(_client(tmp_path), {"field": "sections_hidden", "panel": "nope", "on": True})

    assert response.status_code == 422


def test_a_corrupt_file_refuses_the_write(tmp_path: Path) -> None:
    view_file = tmp_path / "wkx-ecosystem-localhost.view.toml"
    view_file.write_text("this = is = not valid toml\n")
    settings = make_settings(scan_roots=[tmp_path])
    client = loopback_client(create_app(settings, home=HOME, view_file=view_file))

    response = _patch(client, {"field": "theme", "value": "dark"})

    assert response.status_code == 409
    # The board never regenerates the file from memory.
    assert view_file.read_text() == "this = is = not valid toml\n"


def test_view_has_a_write_route_but_config_does_not(tmp_path: Path) -> None:
    client = _client(tmp_path)

    # /api/view accepts PATCH; /api/config never does.
    assert client.patch("/api/config").status_code == 405


def test_an_oversized_patch_body_is_refused(tmp_path: Path) -> None:
    # The file is re-parsed on every request and write, so an oversized body is
    # refused up front rather than read, parsed, and (for a Filter) stored.
    client = _client(tmp_path)
    huge = {"field": "filter", "section": "workspace", "text": "x" * (64 * 1024 + 1)}

    response = _patch(client, huge)

    assert response.status_code == 413


# ---------- an unreadable View file must not take the shell down (finding 5) ----------


def _unreadable_client(tmp_path: Path) -> tuple[TestClient, Path]:
    view_file = tmp_path / "wkx-ecosystem-localhost.view.toml"
    view_file.write_text('theme = "dark"\n')
    view_file.chmod(0o000)
    settings = make_settings(scan_roots=[tmp_path])
    return loopback_client(create_app(settings, home=HOME, view_file=view_file)), view_file


@_skip_as_root
def test_the_shell_still_serves_over_an_unreadable_view_file(tmp_path: Path) -> None:
    client, view_file = _unreadable_client(tmp_path)
    try:
        response = client.get("/")

        assert response.status_code == 200
        assert "WKX" in response.text
        # The saved theme cannot be read, so the shell serves unthemed rather than 500.
        assert 'data-theme="dark"' not in response.text
    finally:
        view_file.chmod(0o644)


@_skip_as_root
def test_get_view_reports_an_unreadable_file(tmp_path: Path) -> None:
    client, view_file = _unreadable_client(tmp_path)
    try:
        body = client.get("/api/view").json()

        assert body["found"] is True
        assert body["readable"] is False
        assert body["writable"] is False
        assert body["theme"] is None
    finally:
        view_file.chmod(0o644)


@_skip_as_root
def test_a_patch_onto_an_unreadable_file_is_not_saved(tmp_path: Path) -> None:
    client, view_file = _unreadable_client(tmp_path)
    try:
        response = _patch(client, {"field": "theme", "value": "light"})

        assert response.status_code == 500
    finally:
        view_file.chmod(0o644)
