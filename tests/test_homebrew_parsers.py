"""Parser edge cases for the homebrew Collector, over synthetic fixtures.

The single pure reader, ``parse_brew_outdated``, pinned against the v2 payload:
formulae and casks split apart, an installed-versions list joined for display,
malformed entries skipped, and malformed JSON degrading to two empty lists. Every
string here is invented.
"""

from __future__ import annotations

import fixtures

from wkx_ecosystem_localhost.collectors.homebrew import parse_brew_outdated


def test_splits_formulae_and_casks() -> None:
    formulae, casks = parse_brew_outdated(fixtures.BREW_OUTDATED_JSON)

    assert [f.name for f in formulae] == ["wget", "ripgrep", "openssl@3"]
    assert [c.name for c in casks] == ["firefox", "docker"]


def test_reads_installed_and_current_versions() -> None:
    formulae, _casks = parse_brew_outdated(fixtures.BREW_OUTDATED_JSON)

    wget = next(f for f in formulae if f.name == "wget")
    assert wget.installed == "1.21.3"
    assert wget.current == "1.21.4"


def test_joins_multiple_installed_versions() -> None:
    formulae, _casks = parse_brew_outdated(fixtures.BREW_OUTDATED_JSON)

    openssl = next(f for f in formulae if f.name == "openssl@3")
    assert openssl.installed == "3.3.1, 3.3.2"


def test_empty_payload_yields_two_empty_lists() -> None:
    formulae, casks = parse_brew_outdated(fixtures.BREW_OUTDATED_EMPTY)

    assert formulae == []
    assert casks == []


def test_malformed_json_degrades_to_empty_lists() -> None:
    formulae, casks = parse_brew_outdated("not json at all")

    assert formulae == []
    assert casks == []


def test_a_nameless_entry_is_skipped() -> None:
    formulae, _casks = parse_brew_outdated(
        '{"formulae": [{"current_version": "2.0"}, {"name": "ok",'
        ' "installed_versions": ["1.0"], "current_version": "2.0"}], "casks": []}'
    )

    assert [f.name for f in formulae] == ["ok"]
