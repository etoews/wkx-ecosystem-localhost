"""The shared repo-discovery cache: hit, miss, expiry, keying, and one walk per load.

The unit tests drive a ``DiscoveryCache`` over a synthetic ``FakeMachine`` tree
with a fake clock, the way ``test_cache.py`` drives the underlying ``TtlCache``:
a within-TTL read is served without re-walking, an expired or re-keyed read walks
again. A ``_CountingMachine`` records every ``list_dir`` so a walk is observable.
The two HTTP tests then prove one board load walks the scan roots once across every
route and the Flag layer, and that a fresh ``create_app`` starts cold. No captured
machine data: every tree is hand-built here or from the synthetic fixtures.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import fixtures
import pytest
from fakes import FakeMachine
from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.collectors.workspace import DiscoveryCache
from wkx_ecosystem_localhost.config import Settings
from wkx_ecosystem_localhost.machine import CommandResult, DirEntry

_HOME = Path("/home")
_ROOT = _HOME / "dev"
_API = _ROOT / "acme" / "api"
_WEB = _ROOT / "acme" / "web"
_CLI = _ROOT / "acme" / "cli"


def _fake_clock() -> tuple[list[float], Callable[[], float]]:
    now = [0.0]
    return now, lambda: now[0]


def _tree() -> FakeMachine:
    """Two repos under ~/dev/acme, the smallest tree that shows a walk."""
    return FakeMachine(
        dirs={_ROOT, _ROOT / "acme", _API, _WEB},
        repos={_API, _WEB},
    )


@dataclass
class _CountingMachine:
    """A ``Machine`` that records every ``list_dir`` so a discovery walk is visible.

    Delegates every primitive to an inner ``FakeMachine`` and appends the listed
    path, so a test counts how many directories a call walked and, with
    ``_under_roots``, isolates discovery walks from a Collector's own listing.
    """

    inner: FakeMachine
    list_dir_paths: list[Path] = field(default_factory=list)

    @property
    def list_dir_calls(self) -> int:
        return len(self.list_dir_paths)

    def run(self, argv: Sequence[str], *, cwd: Path | None = None, timeout: float) -> CommandResult:
        return self.inner.run(argv, cwd=cwd, timeout=timeout)

    def read_file(self, path: Path, max_bytes: int | None = None) -> str | None:
        return self.inner.read_file(path, max_bytes)

    def list_dir(self, path: Path) -> list[DirEntry]:
        self.list_dir_paths.append(path)
        return self.inner.list_dir(path)


def _under_roots(machine: _CountingMachine, roots: Sequence[Path]) -> int:
    """How many recorded listings fell under a scan root, i.e. were discovery."""
    return sum(
        1
        for path in machine.list_dir_paths
        if any(path == root or path.is_relative_to(root) for root in roots)
    )


def test_a_cold_cache_walks_the_roots() -> None:
    machine = _CountingMachine(_tree())
    cache = DiscoveryCache(60.0)

    found = cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)

    assert found == [_API, _WEB]
    assert machine.list_dir_calls > 0


def test_within_ttl_a_second_discover_is_served_without_re_walking() -> None:
    now, clock = _fake_clock()
    machine = _CountingMachine(_tree())
    cache = DiscoveryCache(60.0, clock)

    now[0] = 100.0
    first = cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)
    walks = machine.list_dir_calls
    now[0] = 150.0  # 50s later, still within the 60s TTL

    second = cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)

    assert second == first
    assert machine.list_dir_calls == walks


def test_a_hit_within_ttl_does_not_see_a_newly_added_repo() -> None:
    now, clock = _fake_clock()
    inner = _tree()
    machine = _CountingMachine(inner)
    cache = DiscoveryCache(60.0, clock)

    now[0] = 100.0
    first = cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)
    inner.dirs.add(_CLI)
    inner.repos.add(_CLI)
    now[0] = 150.0  # within the TTL: the cached walk still stands

    second = cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)

    assert _CLI not in first
    assert second == first


def test_after_ttl_discover_re_walks() -> None:
    now, clock = _fake_clock()
    machine = _CountingMachine(_tree())
    cache = DiscoveryCache(60.0, clock)

    now[0] = 100.0
    cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)
    walks = machine.list_dir_calls
    now[0] = 170.0  # 70s later, past the 60s TTL

    cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)

    assert machine.list_dir_calls > walks


def test_expiry_boundary_at_exactly_ttl_re_walks() -> None:
    now, clock = _fake_clock()
    machine = _CountingMachine(_tree())
    cache = DiscoveryCache(60.0, clock)

    now[0] = 100.0
    cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)
    walks = machine.list_dir_calls
    now[0] = 160.0  # exactly the TTL later: the boundary is a miss

    cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)

    assert machine.list_dir_calls > walks


def test_a_re_walk_after_expiry_reflects_the_current_tree() -> None:
    now, clock = _fake_clock()
    inner = _tree()
    machine = _CountingMachine(inner)
    cache = DiscoveryCache(60.0, clock)

    now[0] = 100.0
    first = cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)
    inner.dirs.add(_CLI)
    inner.repos.add(_CLI)
    now[0] = 170.0  # past the TTL: the next read walks again

    second = cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)

    assert _CLI not in first
    assert _CLI in second


@pytest.mark.parametrize(
    ("roots", "max_depth", "excludes"),
    [
        ((_ROOT / "acme",), 8, ()),  # a different root set
        ((_ROOT,), 1, ()),  # a different depth cap
        ((_ROOT,), 8, ("**/api",)),  # a different Exclude glob
    ],
)
def test_a_changed_input_is_a_miss_within_ttl(
    roots: tuple[Path, ...], max_depth: int, excludes: tuple[str, ...]
) -> None:
    now, clock = _fake_clock()
    machine = _CountingMachine(_tree())
    cache = DiscoveryCache(60.0, clock)

    now[0] = 100.0
    cache.discover(machine, [_ROOT], home=_HOME, max_depth=8)
    walks = machine.list_dir_calls
    now[0] = 110.0  # well within the TTL, so only the changed key forces a re-walk

    cache.discover(machine, roots, home=_HOME, max_depth=max_depth, excludes=excludes)

    assert machine.list_dir_calls > walks


def test_one_board_load_walks_the_scan_roots_once() -> None:
    inner, home, roots, tools = fixtures.build_flags_workspace()
    machine = _CountingMachine(inner)
    settings = Settings(_env_file=None, _config_file=None, scan_roots=roots, system_tools=tools)
    client = TestClient(create_app(settings, machine=machine, home=home))

    client.get("/api/workspace")
    after_workspace = _under_roots(machine, roots)
    assert after_workspace > 0

    for route in ("/api/submodules", "/api/toolchains", "/api/footprint", "/api/flags"):
        client.get(route)

    # Every later route and the Flag layer reuse the first walk, so no scan root is
    # listed again within the TTL: one board load, one walk.
    assert _under_roots(machine, roots) == after_workspace


def test_a_fresh_app_starts_with_a_cold_cache() -> None:
    inner, home, roots = fixtures.build_workspace()
    machine = _CountingMachine(inner)
    settings = Settings(_env_file=None, _config_file=None, scan_roots=roots)

    first = TestClient(create_app(settings, machine=machine, home=home))
    first.get("/api/workspace")
    after_first_app = _under_roots(machine, roots)
    assert after_first_app > 0

    second = TestClient(create_app(settings, machine=machine, home=home))
    second.get("/api/workspace")

    # The second app builds its own DiscoveryCache, so it walks cold rather than
    # serving the first app's warm result.
    assert _under_roots(machine, roots) > after_first_app
