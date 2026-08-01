"""The /api/system JSON contract, driven over HTTP against a fake machine.

The highest-altitude system tests: a real app with the real Collector, only the
machine seam faked. They assert the JSON contract, the present-with-version and
missing states, the configured order, and that a tool added purely through
configuration reaches the response.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_system_reports_present_tools_with_their_versions(system_client: TestClient) -> None:
    tools = system_client.get("/api/system").json()["tools"]

    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["git"]["present"] is True
    assert by_name["git"]["version"] == "2.39.5"
    assert by_name["gh"]["version"] == "2.63.2"
    assert by_name["terraform"]["version"] == "1.10.2"
    assert by_name["code"]["version"] == "1.96.0"


def test_system_reports_an_absent_tool_as_missing(system_client: TestClient) -> None:
    tools = system_client.get("/api/system").json()["tools"]

    ty = next(tool for tool in tools if tool["name"] == "ty")
    assert ty["present"] is False
    assert ty["version"] is None


def test_system_includes_a_configuration_added_tool(system_client: TestClient) -> None:
    tools = system_client.get("/api/system").json()["tools"]

    widget = next(tool for tool in tools if tool["name"] == "widget")
    assert widget["present"] is True
    assert widget["version"] == "3.2.1"


def test_system_preserves_the_configured_order(system_client: TestClient) -> None:
    tools = system_client.get("/api/system").json()["tools"]

    names = [tool["name"] for tool in tools]
    assert names == [
        "git",
        "gh",
        "uv",
        "docker",
        "terraform",
        "aws",
        "code",
        "node",
        "ty",
        "widget",
    ]
