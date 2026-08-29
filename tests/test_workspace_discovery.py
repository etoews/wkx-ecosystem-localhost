"""Repo discovery: stop at the first .git, skip the noise, obey the depth cap."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeMachine
from fixtures import DEV, HOME

from wkx_ecosystem_localhost.collectors.workspace import discover_repos


def _workspace() -> FakeMachine:
    """A synthetic tree with repos nested behind every trap discovery must avoid."""
    dirs = {
        DEV,
        DEV / "acme",
        DEV / "acme" / "web",
        DEV / "acme" / "api",
        DEV / "personal",
        DEV / "personal" / "blog",
        # Inside a repo: must never be descended into.
        DEV / "personal" / "blog" / "node_modules",
        DEV / "personal" / "blog" / "vendor",
        DEV / "personal" / "blog" / "vendor" / "nested-lib",
        # Traps directly under a scanned root.
        DEV / ".hidden",
        DEV / ".hidden" / "secret",
        DEV / "node_modules",
        DEV / "node_modules" / "pkg",
        DEV / "venv",
        DEV / "venv" / "lib",
    }
    repos = {
        DEV / "acme" / "web",
        DEV / "acme" / "api",
        DEV / "personal" / "blog",
        DEV / "personal" / "blog" / "vendor" / "nested-lib",
        DEV / ".hidden" / "secret",
        DEV / "node_modules" / "pkg",
        DEV / "venv" / "lib",
    }
    # A plain file under a scanned root: descent must skip it, not try to enter it.
    nondirs = {DEV / "README.md"}
    return FakeMachine(dirs=dirs, repos=repos, nondirs=nondirs)


def test_discover_finds_repos_and_stops_at_the_first_git() -> None:
    found = discover_repos(_workspace(), [DEV], home=HOME, max_depth=8)

    assert found == [DEV / "acme" / "api", DEV / "acme" / "web", DEV / "personal" / "blog"]
    assert DEV / "personal" / "blog" / "vendor" / "nested-lib" not in found


def test_discover_skips_hidden_and_dependency_directories() -> None:
    found = discover_repos(_workspace(), [DEV], home=HOME, max_depth=8)

    assert DEV / ".hidden" / "secret" not in found
    assert DEV / "node_modules" / "pkg" not in found
    assert DEV / "venv" / "lib" not in found


@pytest.mark.parametrize(
    ("max_depth", "expected_found"),
    [
        (2, False),  # repo sits at depth 3, below the cap: not descended into
        (3, True),  # cap reaches depth 3: discovered
    ],
)
def test_discover_respects_the_depth_cap(max_depth: int, expected_found: bool) -> None:
    root = Path("/home/deep")
    repo = root / "a" / "b" / "c"
    machine = FakeMachine(dirs={root, root / "a", root / "a" / "b", repo}, repos={repo})

    found = discover_repos(machine, [root], home=HOME, max_depth=max_depth)

    assert (repo in found) is expected_found


def test_discover_does_not_double_count_overlapping_roots() -> None:
    machine = _workspace()

    found = discover_repos(machine, [DEV, DEV / "acme"], home=HOME, max_depth=8)

    # ~/dev/acme is inside ~/dev; its repos are found once, not twice.
    assert found == [DEV / "acme" / "api", DEV / "acme" / "web", DEV / "personal" / "blog"]


def test_discover_tolerates_a_missing_root() -> None:
    found = discover_repos(FakeMachine(), [Path("/home/does-not-exist")], home=HOME, max_depth=8)

    assert found == []


# ---------- Exclude globs ----------

_API = DEV / "acme" / "api"
_WEB = DEV / "acme" / "web"
_BLOG = DEV / "personal" / "blog"
_ALL_REPOS = [_API, _WEB, _BLOG]


@pytest.mark.parametrize(
    ("excludes", "expected"),
    [
        # A leading ~/ that exactly matches a repo's displayed path: that repo is
        # pruned before its .git is read, so it is not reported.
        (["~/dev/personal/blog"], [_API, _WEB]),
        # A leading ~/ that matches an intermediate directory: the whole subtree is
        # pruned, so neither repo below ~/dev/acme is descended into or reported.
        (["~/dev/acme"], [_BLOG]),
        # ** matches at any depth, pruning the matched directory and its subtree.
        (["**/acme"], [_BLOG]),
        # No glob matches any visited directory: every repo is still discovered.
        (["~/dev/nowhere", "**/absent"], _ALL_REPOS),
    ],
)
def test_discover_prunes_excluded_directories(excludes: list[str], expected: list[Path]) -> None:
    found = discover_repos(_workspace(), [DEV], home=HOME, max_depth=8, excludes=excludes)

    assert found == expected


def test_discover_without_excludes_reports_every_repo() -> None:
    # The default empty excludes changes nothing: the baseline discovery stands.
    found = discover_repos(_workspace(), [DEV], home=HOME, max_depth=8, excludes=[])

    assert found == _ALL_REPOS
