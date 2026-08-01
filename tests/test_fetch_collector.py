"""The background-fetch Collector: per-repo outcomes and the streaming pool.

Every read goes through the fake seam. These pin the three per-repo outcomes
(fetched with counts, fetched but no upstream, fetch failed to an unknown state)
and the streaming behaviour that a fast repo's result lands before a slow one's.
"""

from __future__ import annotations

from pathlib import Path

from fakes import FakeMachine

from wkx_ecosystem_localhost.collectors.fetch import (
    AHEAD_BEHIND_ARGV,
    FETCH_ARGV,
    fetch_repo,
    stream_fetches,
)
from wkx_ecosystem_localhost.machine import CommandResult

HOME = Path("/home")
FAST = HOME / "dev" / "fast"
SLOW = HOME / "dev" / "slow"
REPO = HOME / "dev" / "repo"


def _ok(stdout: str) -> CommandResult:
    return CommandResult(0, stdout, "")


def test_fetch_repo_reports_ahead_behind_after_a_clean_fetch() -> None:
    machine = FakeMachine(
        commands={
            (REPO, FETCH_ARGV): _ok(""),
            (REPO, AHEAD_BEHIND_ARGV): _ok("1\t3\n"),
        }
    )

    outcome = fetch_repo(machine, REPO)

    assert (outcome.ahead, outcome.behind) == (3, 1)
    assert outcome.unknown is False


def test_fetch_repo_with_no_upstream_is_known_but_uncounted() -> None:
    # The fetch succeeds; the ahead/behind command exits non-zero (no upstream).
    machine = FakeMachine(commands={(REPO, FETCH_ARGV): _ok("")})

    outcome = fetch_repo(machine, REPO)

    assert outcome.ahead is None
    assert outcome.behind is None
    assert outcome.unknown is False


def test_fetch_repo_falls_to_unknown_when_the_fetch_fails() -> None:
    # No fetch command registered: the fake returns 127, standing in for a
    # remote that needs credentials or cannot be reached.
    outcome = fetch_repo(FakeMachine(), REPO)

    assert outcome.ahead is None
    assert outcome.behind is None
    assert outcome.unknown is True


def test_stream_fetches_yields_one_event_per_repo() -> None:
    machine = FakeMachine(
        commands={
            (FAST, FETCH_ARGV): _ok(""),
            (FAST, AHEAD_BEHIND_ARGV): _ok("0\t2\n"),
            (SLOW, FETCH_ARGV): _ok(""),
            (SLOW, AHEAD_BEHIND_ARGV): _ok("0\t0\n"),
        }
    )

    events = list(stream_fetches(machine, [FAST, SLOW], home=HOME, max_workers=4))

    by_repo = {event.repo: event for event in events}
    assert set(by_repo) == {"~/dev/fast", "~/dev/slow"}
    assert (by_repo["~/dev/fast"].ahead, by_repo["~/dev/fast"].behind) == (2, 0)


def test_stream_fetches_yields_the_fast_repo_before_the_slow_one() -> None:
    # The slow repo's fetch sleeps, so on a pool of two the fast repo must land
    # first: results stream in completion order, not submission order.
    machine = FakeMachine(
        commands={
            (FAST, FETCH_ARGV): _ok(""),
            (FAST, AHEAD_BEHIND_ARGV): _ok("0\t1\n"),
            (SLOW, FETCH_ARGV): _ok(""),
            (SLOW, AHEAD_BEHIND_ARGV): _ok("0\t1\n"),
        },
        delays={(SLOW, FETCH_ARGV): 0.2},
    )

    events = list(stream_fetches(machine, [SLOW, FAST], home=HOME, max_workers=2))

    assert [event.repo for event in events] == ["~/dev/fast", "~/dev/slow"]


def test_stream_fetches_over_no_repos_yields_nothing() -> None:
    assert list(stream_fetches(FakeMachine(), [], home=HOME, max_workers=4)) == []
