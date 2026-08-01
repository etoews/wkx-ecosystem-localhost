"""The /api/workspace/fetch SSE contract, driven over HTTP against a fake machine.

The highest-altitude fetch tests: a real app streaming real fetch results, only
the machine seam faked. They assert the wire format the browser's ``EventSource``
consumes, one event per repo, the ahead/behind counts, the unknown state for a
remote that cannot be reached, and the terminal ``done`` event that stops the
client reconnecting.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _data_events(body: str) -> list[dict[str, object]]:
    """Extract the JSON payload of every ``data:`` message from an SSE body."""
    events: list[dict[str, object]] = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


def _repo_events(client: TestClient) -> dict[str, dict[str, object]]:
    """Fetch the SSE stream and index each repo's event by its repo id."""
    body = client.get("/api/workspace/fetch").text
    return {str(event["repo"]): event for event in _data_events(body) if event}


def test_fetch_stream_is_served_as_an_event_stream(fetch_client: TestClient) -> None:
    response = fetch_client.get("/api/workspace/fetch")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


def test_fetch_stream_emits_one_event_per_repo_then_done(fetch_client: TestClient) -> None:
    body = fetch_client.get("/api/workspace/fetch").text

    # The two discovered repos, plus the terminal empty {} carried by done.
    payloads = _data_events(body)
    repo_events = [event for event in payloads if event]
    assert len(repo_events) == 2
    assert "event: done" in body


def test_fetch_stream_fills_ahead_behind_for_a_reachable_repo(fetch_client: TestClient) -> None:
    web = _repo_events(fetch_client)["~/dev/acme/web"]

    assert web["ahead"] == 3
    assert web["behind"] == 1
    assert web["unknown"] is False


def test_fetch_stream_marks_an_unreachable_repo_unknown(fetch_client: TestClient) -> None:
    api = _repo_events(fetch_client)["~/dev/acme/api"]

    assert api["unknown"] is True
    assert api["ahead"] is None
    assert api["behind"] is None


def test_fetch_stream_repo_ids_match_the_workspace_paths(fetch_client: TestClient) -> None:
    # The board keys rows by Repo.path, so every event's repo id must be a
    # home-relative path in that same shape.
    events = _repo_events(fetch_client)

    assert all(repo.startswith("~/") for repo in events)
