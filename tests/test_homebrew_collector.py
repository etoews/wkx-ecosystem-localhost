"""The homebrew Collector, driven over the fake seam with synthetic fixtures.

Exercises the assembled Section: outdated formulae and casks when Homebrew is
present, and a plain absent fact when ``brew`` is not installed.
"""

from __future__ import annotations

import fixtures

from wkx_ecosystem_localhost.collectors.homebrew import collect_homebrew


def test_present_homebrew_reports_outdated_formulae_and_casks() -> None:
    section = collect_homebrew(fixtures.build_homebrew_workspace())

    assert section.present is True
    assert [f.name for f in section.formulae] == ["wget", "ripgrep", "openssl@3"]
    assert [c.name for c in section.casks] == ["firefox", "docker"]


def test_absent_homebrew_reports_a_plain_fact_not_an_error() -> None:
    section = collect_homebrew(fixtures.build_homebrew_absent())

    assert section.present is False
    assert section.formulae == []
    assert section.casks == []
