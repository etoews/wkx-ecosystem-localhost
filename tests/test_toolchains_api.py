"""The /api/toolchains JSON contract, driven over HTTP against a fake machine.

The highest-altitude toolchains tests: a real app with the real Collector, only
the machine seam faked. They assert the JSON contract, the relativised paths, the
present-only package managers, the per-repo TypeScript drift, and that absent
tools serialise as absent facts rather than failing the response.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_toolchains_reports_uv_interpreters_installed_and_current(
    toolchains_client: TestClient,
) -> None:
    python = toolchains_client.get("/api/toolchains").json()["python"]

    rows = [(i["version"], i["source"], i["current"]) for i in python["interpreters"]]
    assert rows == [
        ("3.14.7", "homebrew", "3.14.7"),
        ("3.14.4", "uv", "3.14.7"),
        ("3.13.13", "uv", "3.14.7"),
        ("3.9.6", "macos", "3.14.7"),
    ]
    repos = {r["repo"]: (r["version"], r["current"]) for r in python["repos"]}
    assert repos == {"~/dev/acme/web": ("3.14.4", "3.14.7"), "~/dev/acme/api": ("3.12.1", "3.14.7")}
    # The per-repo and global pins are no longer part of the Section.
    assert "repo_pins" not in python
    assert "global_pin" not in python


def test_toolchains_reports_the_system_interpreter(toolchains_client: TestClient) -> None:
    python = toolchains_client.get("/api/toolchains").json()["python"]

    assert python["system"]["present"] is True
    assert python["system"]["version"] == "3.14.5"


def test_toolchains_reports_node_npm_and_absent_tsc(toolchains_client: TestClient) -> None:
    node = toolchains_client.get("/api/toolchains").json()["node"]

    assert node["node"]["version"] == "24.15.0"
    assert node["npm"]["version"] == "11.12.1"
    assert node["tsc"]["present"] is False
    assert node["tsc"]["version"] is None


def test_toolchains_lists_only_present_package_managers(toolchains_client: TestClient) -> None:
    node = toolchains_client.get("/api/toolchains").json()["node"]

    names = [tool["name"] for tool in node["package_managers"]]
    assert names == ["pnpm"]


def test_toolchains_shows_per_repo_declared_versus_installed_typescript(
    toolchains_client: TestClient,
) -> None:
    node = toolchains_client.get("/api/toolchains").json()["node"]

    by_repo = {repo["repo"]: repo for repo in node["repos"]}
    assert by_repo["~/dev/acme/web"]["declared"] == "^5.4.0"
    assert by_repo["~/dev/acme/web"]["installed"] == "5.3.3"
    assert by_repo["~/dev/acme/api"]["declared"] == "~5.2.0"
    assert by_repo["~/dev/acme/api"]["installed"] is None
    assert "~/dev/acme/cli" not in by_repo


def test_toolchains_paths_are_all_home_relative(toolchains_client: TestClient) -> None:
    body = toolchains_client.get("/api/toolchains").json()

    for interpreter in body["python"]["interpreters"]:
        # uv-managed interpreters live under home; Homebrew's and the OS's do not.
        if interpreter["source"] == "uv":
            assert interpreter["path"].startswith("~")
    for repo in body["python"]["repos"]:
        assert repo["repo"].startswith("~")
        assert repo["path"].startswith("~")
    for repo in body["node"]["repos"]:
        assert repo["repo"].startswith("~")


def test_toolchains_response_leaks_no_absolute_home_path(toolchains_client: TestClient) -> None:
    raw_body = toolchains_client.get("/api/toolchains").text

    assert "/home/.local" not in raw_body
    assert "/home/dev" not in raw_body
