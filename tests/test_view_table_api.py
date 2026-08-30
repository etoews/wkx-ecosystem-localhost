"""The M13 table overrides driven over PATCH /api/view.

The three controls (Filter, Hidden columns, sort) are written through the same
one-preference-per-call write route M12 opened, on a tmp View file, guarded to the
board's own Host. Validation is against the table catalogue: an unknown table,
column, or Section is a 422, exactly as an unknown panel already is.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import Settings

HOME = Path("/home/someone")
HOST = "127.0.0.1:8787"


def _client(tmp_path: Path) -> TestClient:
    view_file = tmp_path / "wkx-ecosystem-localhost.view.toml"
    settings = Settings(_env_file=None, _config_file=None, scan_roots=[tmp_path])
    return TestClient(create_app(settings, home=HOME, view_file=view_file))


def _patch(client: TestClient, body: dict) -> object:
    return client.patch("/api/view", json=body, headers={"host": HOST})


# ---------- the round trip ----------


def test_patch_sets_a_filter(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = _patch(client, {"field": "filter", "section": "workspace", "text": "acme"})

    assert response.status_code == 200
    assert client.get("/api/view").json()["filter"] == {"workspace": "acme"}


def test_patch_hides_a_column(tmp_path: Path) -> None:
    client = _client(tmp_path)

    _patch(client, {"field": "columns_hidden", "table": "workspace", "column": "stash", "on": True})

    assert client.get("/api/view").json()["columns_hidden"] == {"workspace": ["stash"]}


def test_patch_sorts_a_table(tmp_path: Path) -> None:
    client = _client(tmp_path)

    _patch(
        client,
        {"field": "sort", "table": "workspace", "column": "behind", "direction": "descending"},
    )

    assert client.get("/api/view").json()["sort"] == {
        "workspace": {"column": "behind", "direction": "descending"}
    }


def test_clearing_a_sort_leaves_no_line(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _patch(
        client,
        {"field": "sort", "table": "workspace", "column": "behind", "direction": "ascending"},
    )

    _patch(client, {"field": "sort", "table": "workspace", "column": "behind", "direction": None})

    assert client.get("/api/view").json()["sort"] == {}


# ---------- catalogue validation (view-unknown-key surface) ----------


def test_an_unknown_filter_section_is_rejected(tmp_path: Path) -> None:
    response = _patch(_client(tmp_path), {"field": "filter", "section": "nope", "text": "x"})

    assert response.status_code == 422


def test_an_unknown_columns_hidden_table_is_rejected(tmp_path: Path) -> None:
    response = _patch(
        _client(tmp_path),
        {"field": "columns_hidden", "table": "nope", "column": "stash", "on": True},
    )

    assert response.status_code == 422


def test_an_unknown_columns_hidden_column_is_rejected(tmp_path: Path) -> None:
    response = _patch(
        _client(tmp_path),
        {"field": "columns_hidden", "table": "workspace", "column": "nope", "on": True},
    )

    assert response.status_code == 422


def test_an_unknown_sort_column_is_rejected(tmp_path: Path) -> None:
    response = _patch(
        _client(tmp_path),
        {"field": "sort", "table": "workspace", "column": "nope", "direction": "ascending"},
    )

    assert response.status_code == 422


def test_the_write_guard_still_covers_the_new_fields(tmp_path: Path) -> None:
    # A foreign Host is refused before the body is even validated, so the new
    # write kinds inherit the M12 loopback guard.
    client = _client(tmp_path)

    response = client.patch(
        "/api/view",
        json={"field": "filter", "section": "workspace", "text": "acme"},
        headers={"host": "evil.example"},
    )

    assert response.status_code == 403
