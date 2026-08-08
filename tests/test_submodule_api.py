"""The submodule API and SSE contract, driven over HTTP against a fake machine.

The highest-altitude submodule tests: a real app serving real pins and streaming
real remote-tag results, only the machine seam faked. They assert the pins land
straight away on ``/api/submodules`` and that ``/api/submodules/probe`` streams
one event per submodule in the browser's ``EventSource`` wire format, with the
latest release, the tags-behind count, the unknown state, and the terminal
``done`` event.
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


def _probe_events(client: TestClient) -> dict[str, dict[str, object]]:
    """Fetch the probe stream and index each submodule's event by its path."""
    body = client.get("/api/submodules/probe").text
    return {str(event["submodule"]): event for event in _data_events(body) if event}


def test_submodules_endpoint_returns_pins_without_the_remote_truth(
    submodule_client: TestClient,
) -> None:
    body = submodule_client.get("/api/submodules").json()

    by_path = {sub["path"]: sub for sub in body["submodules"]}
    widgets = by_path["~/dev/acme/app/libs/widgets"]
    assert widgets["pinned"] == "1.2.0"
    assert widgets["repo"] == "~/dev/acme/app"
    # The network truth is deferred to the SSE probe.
    assert widgets["latest"] is None
    assert widgets["behind"] is None
    # The GitHub release rides the same probe, so it is pending here too.
    assert widgets["github_release"] is None


def test_submodules_link_a_github_remote_and_leave_a_non_github_one_unlinked(
    submodule_client: TestClient,
) -> None:
    body = submodule_client.get("/api/submodules").json()
    by_path = {sub["path"]: sub for sub in body["submodules"]}

    # widgets' remote is on GitHub, so it earns a link exposing only owner and
    # repo; kit and the unreachable submodule are non-GitHub, so they earn none.
    assert by_path["~/dev/acme/app/libs/widgets"]["github"] == "https://github.com/acme/widgets"
    assert by_path["~/dev/acme/app/tools/kit"]["github"] is None
    assert by_path["~/dev/acme/api/vendor/remote-gone"]["github"] is None


def test_probe_stream_is_served_as_an_event_stream(submodule_client: TestClient) -> None:
    response = submodule_client.get("/api/submodules/probe")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


def test_probe_stream_emits_one_event_per_submodule_then_done(
    submodule_client: TestClient,
) -> None:
    body = submodule_client.get("/api/submodules/probe").text

    # Three submodules across the two repos, plus the terminal empty {} from done.
    repo_events = [event for event in _data_events(body) if event]
    assert len(repo_events) == 3
    assert "event: done" in body


def test_probe_stream_fills_latest_and_behind_for_a_drifted_submodule(
    submodule_client: TestClient,
) -> None:
    widgets = _probe_events(submodule_client)["~/dev/acme/app/libs/widgets"]

    assert widgets["latest"] == "2.0.0"
    assert widgets["behind"] == 2
    assert widgets["unknown"] is False


def test_probe_stream_augments_with_the_github_release_when_it_differs(
    submodule_client: TestClient,
) -> None:
    widgets = _probe_events(submodule_client)["~/dev/acme/app/libs/widgets"]

    # GitHub blesses 1.3.0 as latest while the highest tag is 2.0.0, so the release
    # is streamed alongside; the tag-based latest and behind are unchanged.
    assert widgets["github_release"] == "1.3.0"
    assert widgets["latest"] == "2.0.0"
    assert widgets["behind"] == 2


def test_probe_stream_leaves_a_non_github_submodule_release_free(
    submodule_client: TestClient,
) -> None:
    events = _probe_events(submodule_client)

    # kit is a non-GitHub remote and remote-gone is unreachable, so neither gets a
    # release lookup: both fall back to the tag-based facts alone.
    assert events["~/dev/acme/app/tools/kit"]["github_release"] is None
    assert events["~/dev/acme/api/vendor/remote-gone"]["github_release"] is None


def test_probe_stream_reports_zero_behind_when_pinned_on_the_latest(
    submodule_client: TestClient,
) -> None:
    kit = _probe_events(submodule_client)["~/dev/acme/app/tools/kit"]

    assert kit["latest"] == "v3.1.0"
    assert kit["behind"] == 0


def test_probe_stream_marks_an_unreachable_submodule_unknown(
    submodule_client: TestClient,
) -> None:
    gone = _probe_events(submodule_client)["~/dev/acme/api/vendor/remote-gone"]

    assert gone["unknown"] is True
    assert gone["latest"] is None
    assert gone["behind"] is None


def test_probe_stream_ids_match_the_submodule_paths(submodule_client: TestClient) -> None:
    # The board keys rows by Submodule.path, so every event's id must be a
    # home-relative path in that same shape.
    events = _probe_events(submodule_client)

    assert all(path.startswith("~/") for path in events)
