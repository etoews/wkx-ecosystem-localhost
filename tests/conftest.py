"""Shared fixtures. Settings are constructed explicitly so tests never read a real .env."""

from __future__ import annotations

from pathlib import Path

import fixtures
import pytest
from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, scan_roots=[tmp_path])
    return TestClient(create_app(settings))


@pytest.fixture
def workspace_client() -> TestClient:
    """A client wired to a fake machine loaded with synthetic repos and home.

    Drives the real app and real Collectors over HTTP; the only substitution is
    the machine seam, so the JSON contract, redaction, and relativisation are all
    exercised exactly as production would produce them.
    """
    machine, home, roots = fixtures.build_workspace()
    settings = Settings(_env_file=None, scan_roots=roots)
    return TestClient(create_app(settings, machine=machine, home=home))


@pytest.fixture
def submodule_client() -> TestClient:
    """A client wired to a fake machine whose repos carry submodules.

    Drives the real app end to end over the fake seam: two submodules list their
    remote tags and one cannot reach its remote, so the pins, the latest-release
    ranking, the tags-behind counts, and the unknown state are all produced
    exactly as production would.
    """
    machine, home, roots = fixtures.build_submodule_workspace()
    settings = Settings(_env_file=None, scan_roots=roots)
    return TestClient(create_app(settings, machine=machine, home=home))


@pytest.fixture
def toolchains_client() -> TestClient:
    """A client wired to a fake machine loaded with synthetic toolchain facts.

    Drives the real app and Collector over HTTP: uv interpreters, the global and
    per-repo Python pins, the system python3, the global node/npm/tsc, the
    present-only package managers, and the per-repo declared-versus-installed
    TypeScript are all produced exactly as production would, only the machine seam
    faked.
    """
    machine, home, roots = fixtures.build_toolchains_workspace()
    settings = Settings(_env_file=None, scan_roots=roots)
    return TestClient(create_app(settings, machine=machine, home=home))


@pytest.fixture
def system_client() -> TestClient:
    """A client wired to a fake machine loaded with synthetic system-tool facts.

    Drives the real app and Collector over HTTP against a configured tool list:
    nine tools report a version in their own format, one is absent, and one is
    added purely through configuration with an overridden version command, so the
    present-or-missing contract and the config-driven probe are produced exactly as
    production would, only the machine seam faked.
    """
    machine, tools = fixtures.build_system_workspace()
    settings = Settings(_env_file=None, scan_roots=[fixtures.DEV], system_tools=tools)
    return TestClient(create_app(settings, machine=machine, home=fixtures.HOME))


@pytest.fixture
def claude_client() -> TestClient:
    """A client wired to a fake machine loaded with a synthetic Claude environment.

    Drives the real app and Collector over HTTP: user and plugin skills, plugins
    joined with their marketplace repos and enabled state, plugin and user and
    project MCP servers with their auth-needed state, and the narrow MCP-only read
    of the user config are all produced exactly as production would, only the
    machine seam faked.
    """
    machine, home = fixtures.build_claude_workspace()
    settings = Settings(_env_file=None, scan_roots=[fixtures.DEV])
    return TestClient(create_app(settings, machine=machine, home=home))


@pytest.fixture
def homebrew_client() -> TestClient:
    """A client wired to a fake machine whose Homebrew reports outdated packages.

    Drives the real app and Collector over HTTP: three outdated formulae (one at
    two installed versions) and two outdated casks are produced exactly as
    production would, only the machine seam faked.
    """
    machine = fixtures.build_homebrew_workspace()
    settings = Settings(_env_file=None, scan_roots=[fixtures.DEV])
    return TestClient(create_app(settings, machine=machine, home=fixtures.HOME))


@pytest.fixture
def homebrew_absent_client() -> TestClient:
    """A client wired to a fake machine with no Homebrew installed.

    Drives the real app and Collector over HTTP so the absent state is produced
    exactly as production would: present is False and both lists are empty, a plain
    fact rather than an error.
    """
    machine = fixtures.build_homebrew_absent()
    settings = Settings(_env_file=None, scan_roots=[fixtures.DEV])
    return TestClient(create_app(settings, machine=machine, home=fixtures.HOME))


@pytest.fixture
def docker_client() -> TestClient:
    """A client wired to a fake machine whose Docker daemon is reachable.

    Drives the real app and Collector over HTTP: 2 of 5 containers running, 12
    images, and 3.23 GB reclaimable across four resource types are produced exactly
    as production would, only the machine seam faked.
    """
    machine = fixtures.build_docker_workspace()
    settings = Settings(_env_file=None, scan_roots=[fixtures.DEV])
    return TestClient(create_app(settings, machine=machine, home=fixtures.HOME))


@pytest.fixture
def docker_down_client() -> TestClient:
    """A client wired to a fake machine whose Docker daemon cannot be reached.

    Drives the real app and Collector over HTTP so the down state is produced
    exactly as production would: daemon_reachable is False and the counts stay at
    their empty defaults, a plain fact rather than an error page.
    """
    machine = fixtures.build_docker_down()
    settings = Settings(_env_file=None, scan_roots=[fixtures.DEV])
    return TestClient(create_app(settings, machine=machine, home=fixtures.HOME))


@pytest.fixture
def flags_client() -> TestClient:
    """A client wired to a fake machine that lights up the whole at-rest Flag layer.

    Drives the real app and the real Collectors over HTTP: the workspace, system,
    Claude, Homebrew, and Docker per-item Flags and the cross-item drift and
    shadowing Flags are all derived from a multi-repo, multi-Origin fake exactly as
    production would, only the machine seam faked.
    """
    machine, home, roots, tools = fixtures.build_flags_workspace()
    settings = Settings(_env_file=None, scan_roots=roots, system_tools=tools)
    return TestClient(create_app(settings, machine=machine, home=home))


@pytest.fixture
def fetch_client() -> TestClient:
    """A client wired to a fake machine whose repos exercise the fetch stream.

    One repo fetches cleanly with ahead/behind counts, the other cannot reach its
    remote and lands unknown, so the SSE endpoint is driven end to end over the
    fake seam exactly as production would produce it.
    """
    machine, home, roots = fixtures.build_fetch_workspace()
    settings = Settings(_env_file=None, scan_roots=roots)
    return TestClient(create_app(settings, machine=machine, home=home))
