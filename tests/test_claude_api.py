"""HTTP-level tests for the claude Section over the fake Machine.

Drive the real app through the FastAPI ``TestClient`` so the JSON contract,
relativisation, the narrow user-config read, and the no-secret guarantee are all
exercised exactly as production would serialise them.
"""

from __future__ import annotations

import fixtures
from fastapi.testclient import TestClient


def test_claude_endpoint_returns_the_section_shape(claude_client: TestClient) -> None:
    response = claude_client.get("/api/claude")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"skills", "plugins", "mcp_servers"}


def test_claude_skills_carry_origin_and_enabled(claude_client: TestClient) -> None:
    skills = {s["name"]: s for s in claude_client.get("/api/claude").json()["skills"]}

    assert skills["tidy-repo"]["origin"] == "user"
    assert skills["tidy-repo"]["enabled"] is True
    assert skills["layout"]["origin"] == "tidy@studio-official"
    assert skills["wireframe"]["enabled"] is False


def test_claude_plugins_show_repo_version_and_disabled(claude_client: TestClient) -> None:
    plugins = {p["name"]: p for p in claude_client.get("/api/claude").json()["plugins"]}

    assert plugins["tidy"]["repo"] == "acme/studio-official"
    assert plugins["tidy"]["version"] == "2.3.0"
    assert plugins["tidy"]["install_path"].startswith("~/")
    # A disabled plugin is present and badged, never filtered out.
    assert plugins["sketch"]["enabled"] is False
    assert plugins["gizmo"]["repo"] is None


def test_claude_mcp_servers_show_origin_and_auth(claude_client: TestClient) -> None:
    servers = {s["name"]: s for s in claude_client.get("/api/claude").json()["mcp_servers"]}

    assert servers["cloud-mcp"]["origin"] == "cloudkit@studio-official"
    assert servers["cloud-mcp"]["needs_auth"] is True
    assert servers["vault-mcp"]["origin"] == "user"
    assert servers["vault-mcp"]["needs_auth"] is True
    assert servers["repo-mcp"]["origin"] == "project"


def test_claude_reads_only_the_mcp_subset_of_the_user_config(claude_client: TestClient) -> None:
    # The proof: the whole serialised Section contains the MCP server names but
    # none of the account, machine, telemetry, or credential fields, so the narrow
    # read never touched them.
    raw = claude_client.get("/api/claude").text

    assert "notes-mcp" in raw and "vault-mcp" in raw and "repo-mcp" in raw
    assert "should-never-appear" not in raw
    assert "should-not-leak" not in raw
    assert fixtures.CLAUDE_SECRET not in raw
