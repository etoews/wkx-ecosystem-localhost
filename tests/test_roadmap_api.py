"""The Roadmap column's slice of the /api/workspace contract, over the fake seam.

Drives the real app and Collectors over HTTP: a repo with a ROADMAP.md rides its
progress on the existing workspace payload, a repo without carries None, and a
submodule (a row of /api/submodules) carries no roadmap at all, because a pinned
checkout's roadmap belongs upstream. Only the machine seam is faked.
"""

from __future__ import annotations

import fixtures
from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.collectors.roadmap import ROADMAP_FILENAME
from wkx_ecosystem_localhost.config import Settings

# Two ticked of four task items, so the ratio is an unambiguous 0.5.
ROADMAP_TEXT = "# Roadmap\n- [x] one\n- [x] two\n- [ ] three\n- [ ] four\n"


def _repos_by_name(client: TestClient) -> dict[str, dict[str, object]]:
    body = client.get("/api/workspace").json()
    return {repo["name"]: repo for repo in body["repos"]}


def _client_with_web_roadmap() -> TestClient:
    machine, home, roots = fixtures.build_workspace()
    machine.files[fixtures.WEB / ROADMAP_FILENAME] = ROADMAP_TEXT
    settings = Settings(_env_file=None, _config_file=None, scan_roots=roots)
    return TestClient(create_app(settings, machine=machine, home=home))


def test_repo_roadmap_rides_the_workspace_payload() -> None:
    repos = _repos_by_name(_client_with_web_roadmap())

    assert repos["web"]["roadmap"] == {"ticked": 2, "total": 4}


def test_a_repo_with_no_roadmap_file_carries_none() -> None:
    repos = _repos_by_name(_client_with_web_roadmap())

    assert repos["api"]["roadmap"] is None


def test_a_submodule_row_carries_no_roadmap() -> None:
    machine, home, roots = fixtures.build_submodule_workspace()
    machine.files[fixtures.APP / ROADMAP_FILENAME] = ROADMAP_TEXT
    settings = Settings(_env_file=None, _config_file=None, scan_roots=roots)
    client = TestClient(create_app(settings, machine=machine, home=home))

    repos = _repos_by_name(client)
    submodules = client.get("/api/submodules").json()["submodules"]

    # The parent repo rides its roadmap; a submodule is a row of /api/submodules
    # and has no roadmap field at all.
    assert repos["app"]["roadmap"] == {"ticked": 2, "total": 4}
    assert submodules
    assert all("roadmap" not in sub for sub in submodules)
