"""The background-fetch Collector: refresh remote-tracking refs, report ahead/behind.

The one write the whole board ever performs, and it touches remote-tracking refs
only: no working tree, branch, or history is modified. Each fetch is
non-interactive (terminal prompts are disabled at the Machine seam), bounded by a
wall-clock timeout, and neither recurses submodules nor runs housekeeping. The
fetches run on a small bounded pool and each result is streamed the moment it
lands, so the board's one slow truth fills in progressively.

ahead/behind is computed from local refs after the fetch. A repo that cannot
reach its remote (say it needs credentials) fails quietly to a labelled unknown
state rather than hanging the stream.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import FetchEvent
from wkx_ecosystem_localhost.redaction import relativise

logger = logging.getLogger(__name__)

# The fixed fetch argv. Remote-tracking refs only:
#   -c gc.auto=0             never trigger housekeeping as a side effect
#   --no-recurse-submodules  never descend into submodules (that is M2b's job)
#   --no-tags                do not import tags, keeping this to tracking refs
#   --quiet                  no progress noise on stderr
# GIT_TERMINAL_PROMPT=0 is set at the Machine seam, so a repo needing credentials
# fails immediately instead of blocking on a prompt.
FETCH_ARGV = (
    "git",
    "-c",
    "gc.auto=0",
    "fetch",
    "--no-recurse-submodules",
    "--no-tags",
    "--quiet",
)

# After the fetch, count how far HEAD sits from its upstream using local refs
# only. Output is "<behind>\t<ahead>": the left side is commits in the upstream
# not in HEAD (behind), the right side is commits in HEAD not in the upstream
# (ahead). The command exits non-zero when the branch has no upstream.
AHEAD_BEHIND_ARGV = ("git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD")

# Per-fetch wall-clock ceiling. A network fetch is slower than a local probe, so
# this is more generous than the workspace probes, but still bounded so an
# unreachable remote degrades one row instead of hanging the stream.
FETCH_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class FetchOutcome:
    """The parsed result of fetching one repo and measuring its divergence.

    ``unknown`` is True when the fetch itself could not complete (an unreachable
    or credential-gated remote, or a timeout): the row is left in a labelled
    unknown state. When the fetch succeeds but the repo has no upstream, the
    fetch is known-good yet ``ahead`` and ``behind`` are None, because there is
    simply nothing to compare against.
    """

    ahead: int | None
    behind: int | None
    unknown: bool


def parse_ahead_behind(text: str) -> tuple[int, int] | None:
    """Parse ``git rev-list --left-right --count @{upstream}...HEAD``.

    Args:
        text: The command's stdout, a single ``<behind>\\t<ahead>`` line.

    Returns:
        ``(ahead, behind)`` counts, or None when the output is not the expected
        two-integer line (for example an empty string from a repo with no
        upstream).
    """
    fields = text.split()
    if len(fields) != 2:
        return None
    try:
        behind, ahead = int(fields[0]), int(fields[1])
    except ValueError:
        return None
    return ahead, behind


def fetch_repo(
    machine: Machine, repo_path: Path, *, timeout: float = FETCH_TIMEOUT_S
) -> FetchOutcome:
    """Fetch one repo's remote-tracking refs and measure ahead/behind.

    Runs the non-interactive fetch through the seam, then counts divergence from
    the upstream using local refs only. A fetch that exits non-zero (credentials,
    no network, a timeout) yields an unknown outcome rather than raising, so a
    single unreachable remote costs one row's freshness, never the stream.

    Args:
        machine: The seam both commands run through.
        repo_path: The repo's root directory.
        timeout: Per-fetch wall-clock ceiling in seconds.

    Returns:
        The repo's ahead/behind counts, or an unknown outcome when the fetch
        could not complete.
    """
    fetch_result = machine.run(FETCH_ARGV, cwd=repo_path, timeout=timeout)
    if not fetch_result.ok:
        logger.info("background fetch could not complete for %s", repo_path.name)
        return FetchOutcome(ahead=None, behind=None, unknown=True)

    ab_result = machine.run(AHEAD_BEHIND_ARGV, cwd=repo_path, timeout=timeout)
    if not ab_result.ok:
        # The fetch worked; the branch simply has no upstream to compare against.
        return FetchOutcome(ahead=None, behind=None, unknown=False)

    counts = parse_ahead_behind(ab_result.stdout)
    if counts is None:
        return FetchOutcome(ahead=None, behind=None, unknown=False)
    ahead, behind = counts
    return FetchOutcome(ahead=ahead, behind=behind, unknown=False)


def stream_fetches(
    machine: Machine,
    repo_paths: Sequence[Path],
    *,
    home: Path,
    max_workers: int,
    timeout: float = FETCH_TIMEOUT_S,
) -> Iterator[FetchEvent]:
    """Fetch every repo on a bounded pool, yielding each result as it lands.

    The fetches run concurrently on at most ``max_workers`` threads and results
    are yielded in completion order, not submission order, so a fast repo's
    counts reach the board while a slow one is still in flight. Each repo's
    identifier is its home-relative path, matching the workspace Section so the
    board can fill the right row.

    Args:
        machine: The seam every fetch runs through.
        repo_paths: The repos to fetch, as discovered for the workspace Section.
        home: Home directory, for relativising each repo's path.
        max_workers: Ceiling on concurrent fetches.
        timeout: Per-fetch wall-clock ceiling in seconds.

    Yields:
        One ``FetchEvent`` per repo, in the order the fetches complete.
    """
    if not repo_paths:
        return
    workers = max(1, min(max_workers, len(repo_paths)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_repo, machine, path, timeout=timeout): path for path in repo_paths
        }
        for future in as_completed(futures):
            path = futures[future]
            outcome = future.result()
            yield FetchEvent(
                repo=relativise(path, home),
                ahead=outcome.ahead,
                behind=outcome.behind,
                unknown=outcome.unknown,
            )
