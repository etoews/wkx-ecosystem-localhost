"""Shared fixtures. Settings are constructed explicitly so tests never read a real .env."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, scan_roots=[tmp_path])
    return TestClient(create_app(settings))
