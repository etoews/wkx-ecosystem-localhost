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
def fetch_client() -> TestClient:
    """A client wired to a fake machine whose repos exercise the fetch stream.

    One repo fetches cleanly with ahead/behind counts, the other cannot reach its
    remote and lands unknown, so the SSE endpoint is driven end to end over the
    fake seam exactly as production would produce it.
    """
    machine, home, roots = fixtures.build_fetch_workspace()
    settings = Settings(_env_file=None, scan_roots=roots)
    return TestClient(create_app(settings, machine=machine, home=home))
