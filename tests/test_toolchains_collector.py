"""The toolchains Collector, driven over the fake seam with synthetic fixtures.

Exercises the assembled Section: uv interpreters de-duplicated and relativised,
the global and per-repo Python pins, the system python3, the present-only package
managers, and the per-repo declared-versus-installed TypeScript, plus an absent
tool landing as an absent fact rather than an error.
"""

from __future__ import annotations

import fixtures
from fakes import FakeMachine

from wkx_ecosystem_localhost.collectors.toolchains import collect_toolchains


def _section() -> object:
    machine, home, _roots = fixtures.build_toolchains_workspace()
    return collect_toolchains(machine, [fixtures.WEB, fixtures.API, fixtures.CLI], home=home)


def test_uv_interpreters_are_installed_only_deduped_and_relativised() -> None:
    section = _section()

    versions = [(i.implementation, i.version) for i in section.python.interpreters]
    # Only installed lines, and the doubly-listed 3.14.4 collapses to one.
    assert versions == [("cpython", "3.14.4"), ("cpython", "3.13.13")]
    assert section.python.interpreters[0].path == "~/.local/bin/python3.14"


def test_global_and_per_repo_pins_are_reported() -> None:
    section = _section()

    assert section.python.global_pin == "3.14.4"
    pins = {pin.repo: pin.version for pin in section.python.repo_pins}
    assert pins == {"~/dev/acme/web": "3.14.4", "~/dev/acme/api": "3.13.13"}


def test_system_python3_is_reported_as_present() -> None:
    section = _section()

    assert section.python.system.present is True
    assert section.python.system.version == "3.14.5"


def test_global_node_and_npm_are_present_and_tsc_is_absent() -> None:
    section = _section()

    assert section.node.node.version == "24.15.0"
    assert section.node.npm.version == "11.12.1"
    # tsc is not installed: an absent fact, not an error.
    assert section.node.tsc.present is False
    assert section.node.tsc.version is None


def test_only_present_package_managers_are_listed() -> None:
    section = _section()

    names = [tool.name for tool in section.node.package_managers]
    # pnpm is present; bun is absent, so it does not appear at all.
    assert names == ["pnpm"]
    assert section.node.package_managers[0].version == "9.1.0"


def test_per_repo_typescript_shows_declared_versus_installed_drift() -> None:
    section = _section()

    by_repo = {repo.repo: repo for repo in section.node.repos}
    web = by_repo["~/dev/acme/web"]
    assert web.declared == "^5.4.0"
    assert web.installed == "5.3.3"


def test_declared_typescript_without_an_install_is_reported_absent() -> None:
    section = _section()

    by_repo = {repo.repo: repo for repo in section.node.repos}
    api = by_repo["~/dev/acme/api"]
    assert api.declared == "~5.2.0"
    assert api.installed is None


def test_a_manifest_without_typescript_is_not_a_typescript_row() -> None:
    section = _section()

    repos = {repo.repo for repo in section.node.repos}
    assert "~/dev/acme/cli" not in repos


def test_an_empty_machine_yields_absent_facts_not_errors() -> None:
    section = collect_toolchains(FakeMachine(), [], home=fixtures.HOME)

    assert section.python.interpreters == []
    assert section.python.global_pin is None
    assert section.python.repo_pins == []
    assert section.python.system.present is False
    assert section.node.node.present is False
    assert section.node.package_managers == []
    assert section.node.repos == []
