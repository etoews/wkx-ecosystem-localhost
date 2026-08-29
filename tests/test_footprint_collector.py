"""The footprint Collector, driven over the fake seam with synthetic fixtures.

Exercises the assembled Section: repos ranked biggest-first by true bytes, each
repo's ``.venv`` and ``node_modules`` sizes (or None when absent), a repo with
neither left out, the humanised totals, and the embedded Docker disk figures.
"""

from __future__ import annotations

import fixtures

from wkx_ecosystem_localhost.collectors.footprint import collect_footprint
from wkx_ecosystem_localhost.collectors.workspace import discover_repos


def _section():  # type: ignore[no-untyped-def]
    machine, home, roots = fixtures.build_footprint_workspace()
    repo_paths = discover_repos(machine, roots, home=home, max_depth=8)
    return collect_footprint(machine, repo_paths, home=home)


def test_repos_are_ranked_biggest_first_and_the_empty_one_is_excluded() -> None:
    section = _section()

    # quiet has neither .venv nor node_modules, so it is left out; the rest are
    # ranked by true bytes: web (616.5 MB) > cli (256 MB) > api (46 MB).
    assert [repo.name for repo in section.repos] == ["web", "cli", "api"]


def test_each_repo_carries_its_present_directories_only() -> None:
    section = _section()
    web, cli, api = section.repos

    assert web.path == "~/dev/acme/web"
    assert web.venv == "92.27 MB"
    assert web.node_modules == "524.29 MB"
    assert web.total == "616.55 MB"
    assert web.total_bytes == 616_554_496

    assert cli.venv is None
    assert cli.node_modules == "256 MB"
    assert cli.total == "256 MB"
    assert cli.total_bytes == 256_000_000

    assert api.venv == "46.08 MB"
    assert api.node_modules is None
    assert api.total == "46.08 MB"
    assert api.total_bytes == 46_080_000


def test_repos_total_sums_every_footprint() -> None:
    section = _section()

    # 616,554,496 + 256,000,000 + 46,080,000 = 918,634,496 bytes.
    assert section.repos_total == "918.63 MB"


def test_docker_figures_are_embedded_from_the_docker_collector() -> None:
    section = _section()

    assert section.docker_reachable is True
    assert section.docker_total == "4.62 GB"
    assert section.docker_reclaimable == "3.23 GB"
