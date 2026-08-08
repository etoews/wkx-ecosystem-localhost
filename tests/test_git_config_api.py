"""The /api/git-config JSON contract, driven over HTTP against a fake machine.

The highest-altitude git-config tests: a real app with the real Collector, only
the machine seam faked. They assert the JSON contract for the inventory (every key
shown, secrets masked), the shadowed conflict, the unshadowed multi-valued key, the
resolved include directives, and, above all, that the synthetic token never leaves
the parser.
"""

from __future__ import annotations

import fixtures
from fastapi.testclient import TestClient


def _entries(body: dict, key: str) -> list[dict]:
    return [entry for entry in body["entries"] if entry["key"] == key]


def test_git_config_reports_identity_and_shows_email(git_config_client: TestClient) -> None:
    body = git_config_client.get("/api/git-config").json()

    assert body["identity_present"] is True
    email = _entries(body, "user.email")
    assert len(email) == 1
    assert email[0]["value"] == "ada@example.com"
    assert email[0]["masked"] is False


def test_git_config_marks_the_shadowed_conflict(git_config_client: TestClient) -> None:
    body = git_config_client.get("/api/git-config").json()
    editors = _entries(body, "core.editor")
    assert [(e["value"], e["shadowed"]) for e in editors] == [
        ("vim", True),
        ("code --wait", False),
    ]


def test_git_config_never_shadows_a_multivalued_key(git_config_client: TestClient) -> None:
    body = git_config_client.get("/api/git-config").json()
    insteadof = _entries(body, "url.git@github.com:.insteadof")
    assert len(insteadof) == 2
    assert all(entry["shadowed"] is False for entry in insteadof)


def test_git_config_strips_an_embedded_credential(git_config_client: TestClient) -> None:
    body = git_config_client.get("/api/git-config").json()
    endpoint = _entries(body, "myservice.endpoint")
    assert len(endpoint) == 1
    # ADR 0001: the credential is stripped and the endpoint stays visible; the red
    # credentials Flag is what warns, not a whole-value mask.
    assert endpoint[0]["credentials"] is True
    assert endpoint[0]["masked"] is False
    assert endpoint[0]["value"] == "https://example.com/api"


def test_git_config_resolves_include_directives(git_config_client: TestClient) -> None:
    body = git_config_client.get("/api/git-config").json()
    by_path = {include["path"]: include for include in body["includes"]}

    assert by_path["~/.gitconfig-work"]["exists"] is True
    assert by_path["~/.gitconfig-work"]["condition"] is None
    assert by_path["~/.gitconfig-missing"]["exists"] is False
    assert by_path["~/.gitconfig-missing"]["condition"] == "gitdir:~/work/"


def test_git_config_never_leaks_the_synthetic_token(git_config_client: TestClient) -> None:
    response = git_config_client.get("/api/git-config")
    assert response.status_code == 200
    assert fixtures.SECRET_TOKEN not in response.text
