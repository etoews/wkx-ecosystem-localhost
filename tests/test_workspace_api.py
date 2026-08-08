"""The /api/workspace JSON contract, driven over HTTP against a fake machine.

The highest-altitude tests: a real app with real Collectors, only the machine
seam faked. They assert external behaviour, the JSON contract, redaction,
relativisation, and the pending ahead/behind, exactly as production would emit it.
"""

from __future__ import annotations

import fixtures
from fastapi.testclient import TestClient


def _repos_by_name(client: TestClient) -> dict[str, dict[str, object]]:
    body = client.get("/api/workspace").json()
    return {repo["name"]: repo for repo in body["repos"]}


def test_workspace_lists_discovered_repos_in_stable_order(workspace_client: TestClient) -> None:
    body = workspace_client.get("/api/workspace").json()

    assert body["roots"] == ["~/dev"]
    assert [repo["path"] for repo in body["repos"]] == ["~/dev/acme/api", "~/dev/acme/web"]


def test_workspace_reports_branch_counts_and_stash(workspace_client: TestClient) -> None:
    web = _repos_by_name(workspace_client)["web"]

    assert web["branch"] == "feature/login"
    assert web["upstream"] == "origin/feature/login"
    assert (web["staged"], web["unstaged"], web["untracked"]) == (2, 2, 2)
    assert web["stashes"] == 3
    assert web["dirty"] is True


def test_workspace_reports_detached_head_with_short_sha(workspace_client: TestClient) -> None:
    api = _repos_by_name(workspace_client)["api"]

    assert api["branch"] is None
    assert api["detached_sha"] == "3333333"
    assert api["dirty"] is True


def test_workspace_renders_ahead_behind_as_pending(workspace_client: TestClient) -> None:
    repos = _repos_by_name(workspace_client)

    assert all(repo["ahead"] is None and repo["behind"] is None for repo in repos.values())


def test_workspace_paths_are_all_home_relative(workspace_client: TestClient) -> None:
    body = workspace_client.get("/api/workspace").json()

    assert all(root.startswith("~") for root in body["roots"])
    assert all(repo["path"].startswith("~") for repo in body["repos"])


def test_workspace_masks_email_and_keeps_raw_for_reveal(workspace_client: TestClient) -> None:
    web = _repos_by_name(workspace_client)["web"]
    emails = [entry for entry in web["config"] if entry["key"] == "user.email"]
    global_email = next(entry for entry in emails if entry["scope"] == "global")

    assert global_email["value"] == "a•••@example.com"
    assert global_email["raw"] == "ada.lovelace@example.com"


def test_workspace_strips_remote_credentials(workspace_client: TestClient) -> None:
    web = _repos_by_name(workspace_client)["web"]
    remote = next(entry for entry in web["config"] if entry["key"] == "remote.origin.url")

    assert remote["value"] == "https://github.com/ada/analytical-engine.git"
    assert remote["raw"] is None


def test_workspace_links_a_github_repo_and_leaves_a_non_github_repo_unlinked(
    workspace_client: TestClient,
) -> None:
    repos = _repos_by_name(workspace_client)

    # web's origin is a (tokened) GitHub remote, so it earns a link exposing only
    # owner and repo; api's origin is a non-GitHub host, so it earns none.
    assert repos["web"]["github"] == "https://github.com/ada/analytical-engine"
    assert repos["api"]["github"] is None


def test_workspace_github_link_carries_no_credential(workspace_client: TestClient) -> None:
    web = _repos_by_name(workspace_client)["web"]

    assert web["github"] is not None
    assert fixtures.SECRET_TOKEN not in web["github"]


def test_workspace_response_leaks_no_token_or_key_material(workspace_client: TestClient) -> None:
    raw_body = workspace_client.get("/api/workspace").text

    assert fixtures.SECRET_TOKEN not in raw_body
    assert "signingkey" not in raw_body


def test_workspace_response_leaks_no_absolute_home_path(workspace_client: TestClient) -> None:
    raw_body = workspace_client.get("/api/workspace").text

    assert "/home/dev" not in raw_body
