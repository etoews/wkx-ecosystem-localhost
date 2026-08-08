"""The docker Collector, driven over the fake seam with synthetic fixtures.

Exercises the assembled Section: daemon reachable with container and image counts
and the reclaimable disk summed across resource types, and a down daemon landing
as a plain fact rather than an error.
"""

from __future__ import annotations

import fixtures

from wkx_ecosystem_localhost.collectors.docker import collect_docker


def test_reachable_daemon_reports_counts_and_reclaimable() -> None:
    section = collect_docker(fixtures.build_docker_workspace())

    assert section.daemon_reachable is True
    assert section.containers_running == 2
    assert section.containers_total == 5
    assert section.images == 12
    # 1.2GB + 80MB + 450MB + 1.5GB summed and humanised, in decimal units.
    assert section.reclaimable == "3.23 GB"
    # 2.5GB + 120MB + 500MB + 1.5GB total size, summed and humanised.
    assert section.total_disk == "4.62 GB"


def test_down_daemon_reports_a_plain_fact_not_an_error() -> None:
    section = collect_docker(fixtures.build_docker_down())

    assert section.daemon_reachable is False
    assert section.containers_running == 0
    assert section.containers_total == 0
    assert section.images == 0
    assert section.reclaimable is None
    assert section.total_disk is None
