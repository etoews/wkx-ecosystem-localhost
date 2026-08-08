"""The /api/editor JSON contract, driven over HTTP against a fake machine.

The highest-altitude editor tests: a real app with the real Collector, only the
machine seam faked. They assert the JSON contract for both the installed state
(version and the extensions with their ids and versions) and the absent CLI,
which must render as a fact with a 200, never an error page.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_editor_reports_installed_with_version(editor_client: TestClient) -> None:
    body = editor_client.get("/api/editor").json()

    assert body["installed"] is True
    assert body["version"] == "1.96.0"


def test_editor_reports_the_installed_extensions(editor_client: TestClient) -> None:
    body = editor_client.get("/api/editor").json()

    assert len(body["extensions"]) == 4
    assert [(e["id"], e["version"]) for e in body["extensions"]] == [
        ("ms-python.python", "2024.22.0"),
        ("esbenp.prettier-vscode", "11.0.0"),
        ("dbaeumer.vscode-eslint", "3.0.10"),
        ("charliermarsh.ruff", "2025.22.0"),
    ]


def test_editor_absent_renders_gracefully_as_a_fact(editor_absent_client: TestClient) -> None:
    response = editor_absent_client.get("/api/editor")

    assert response.status_code == 200
    body = response.json()
    assert body["installed"] is False
    assert body["version"] is None
    assert body["extensions"] == []
