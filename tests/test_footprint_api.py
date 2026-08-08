"""The /api/footprint JSON contract, driven over HTTP against a fake machine.

The highest-altitude footprint tests: a real app with the real Collector behind
its cache, only the machine seam faked. They assert the JSON contract, repo rows
biggest-first, the humanised per-repo and total sizes, the empty repo excluded,
and the embedded Docker disk figures.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_footprint_ranks_repos_biggest_first_and_excludes_the_empty_one(
    footprint_client: TestClient,
) -> None:
    body = footprint_client.get("/api/footprint").json()

    assert [repo["name"] for repo in body["repos"]] == ["web", "cli", "api"]


def test_footprint_reports_each_repos_humanised_sizes(footprint_client: TestClient) -> None:
    body = footprint_client.get("/api/footprint").json()
    web, cli, api = body["repos"]

    assert web["path"] == "~/dev/acme/web"
    assert web["venv"] == "92.27 MB"
    assert web["node_modules"] == "524.29 MB"
    assert web["total"] == "616.55 MB"
    assert web["total_bytes"] == 616_554_496

    assert cli["venv"] is None
    assert cli["node_modules"] == "256 MB"
    assert cli["total"] == "256 MB"

    assert api["venv"] == "46.08 MB"
    assert api["node_modules"] is None
    assert api["total"] == "46.08 MB"


def test_footprint_reports_the_workspace_total(footprint_client: TestClient) -> None:
    body = footprint_client.get("/api/footprint").json()

    assert body["repos_total"] == "918.63 MB"


def test_footprint_embeds_the_docker_disk_figures(footprint_client: TestClient) -> None:
    body = footprint_client.get("/api/footprint").json()

    assert body["docker_reachable"] is True
    assert body["docker_total"] == "4.62 GB"
    assert body["docker_reclaimable"] == "3.23 GB"
