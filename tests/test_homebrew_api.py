"""The /api/homebrew JSON contract, driven over HTTP against a fake machine.

The highest-altitude homebrew tests: a real app with the real Collector, only the
machine seam faked. They assert the JSON contract for both the healthy state
(outdated formulae and casks with their counts) and Homebrew's absence.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_homebrew_reports_outdated_formulae_and_casks(homebrew_client: TestClient) -> None:
    body = homebrew_client.get("/api/homebrew").json()

    assert body["present"] is True
    assert [f["name"] for f in body["formulae"]] == ["wget", "ripgrep", "openssl@3"]
    assert [c["name"] for c in body["casks"]] == ["firefox", "docker"]


def test_homebrew_counts_read_off_the_list_lengths(homebrew_client: TestClient) -> None:
    body = homebrew_client.get("/api/homebrew").json()

    assert len(body["formulae"]) == 3
    assert len(body["casks"]) == 2


def test_homebrew_carries_installed_and_current_versions(homebrew_client: TestClient) -> None:
    body = homebrew_client.get("/api/homebrew").json()

    openssl = next(f for f in body["formulae"] if f["name"] == "openssl@3")
    assert openssl["installed"] == "3.3.1, 3.3.2"
    assert openssl["current"] == "3.4.0"


def test_homebrew_absent_renders_gracefully_as_a_fact(homebrew_absent_client: TestClient) -> None:
    response = homebrew_absent_client.get("/api/homebrew")

    assert response.status_code == 200
    body = response.json()
    assert body["present"] is False
    assert body["formulae"] == []
    assert body["casks"] == []
