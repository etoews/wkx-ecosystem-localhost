"""The /api/docker JSON contract, driven over HTTP against a fake machine.

The highest-altitude docker tests: a real app with the real Collector, only the
machine seam faked. They assert the JSON contract for both the healthy state
(daemon reachable with counts and reclaimable disk) and the down daemon, which
must render as a fact with a 200, never an error page.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_docker_reports_daemon_reachable_with_counts(docker_client: TestClient) -> None:
    body = docker_client.get("/api/docker").json()

    assert body["daemon_reachable"] is True
    assert body["containers_running"] == 2
    assert body["containers_total"] == 5
    assert body["images"] == 12


def test_docker_reports_the_reclaimable_disk_total(docker_client: TestClient) -> None:
    body = docker_client.get("/api/docker").json()

    assert body["reclaimable"] == "3.23 GB"


def test_docker_reports_the_total_disk(docker_client: TestClient) -> None:
    body = docker_client.get("/api/docker").json()

    assert body["total_disk"] == "4.62 GB"


def test_docker_daemon_down_renders_gracefully_as_a_fact(docker_down_client: TestClient) -> None:
    response = docker_down_client.get("/api/docker")

    assert response.status_code == 200
    body = response.json()
    assert body["daemon_reachable"] is False
    assert body["containers_running"] == 0
    assert body["containers_total"] == 0
    assert body["images"] == 0
    assert body["reclaimable"] is None
    assert body["total_disk"] is None
