"""Semver parsing and precedence edge cases, over synthetic tag lists.

The drift numbers a submodule shows are only as trustworthy as this ordering, so
the tricky cases are pinned directly: a missing ``v`` prefix, pre-release
exclusion and its fallback, and the pre-release precedence rules from the semver
spec. Every tag here is invented.
"""

from __future__ import annotations

import pytest

from wkx_ecosystem_localhost.semver import (
    count_behind,
    parse_pinned,
    parse_semver,
    precedence_key,
    select_latest,
)


def _parse_all(tags: list[str]) -> list:
    return [v for v in (parse_semver(t) for t in tags) if v is not None]


def test_parses_a_bare_version_without_a_v_prefix() -> None:
    version = parse_semver("1.2.3")
    assert version is not None
    assert (version.major, version.minor, version.patch) == (1, 2, 3)
    assert version.is_prerelease is False
    assert version.original == "1.2.3"


def test_parses_a_v_prefixed_version_but_keeps_the_original_for_display() -> None:
    version = parse_semver("v2.0.0")
    assert version is not None
    assert (version.major, version.minor, version.patch) == (2, 0, 0)
    assert version.original == "v2.0.0"


def test_a_v_prefixed_and_a_bare_tag_compare_equal() -> None:
    bare = parse_semver("1.2.3")
    prefixed = parse_semver("v1.2.3")
    assert bare is not None and prefixed is not None
    assert precedence_key(bare) == precedence_key(prefixed)


@pytest.mark.parametrize("tag", ["latest", "stable", "", "1.2", "1", "release-1", "2024-01-01"])
def test_rejects_non_semver_tags(tag: str) -> None:
    assert parse_semver(tag) is None


def test_build_metadata_is_ignored_for_ordering() -> None:
    plain = parse_semver("1.0.0")
    built = parse_semver("1.0.0+build.7")
    assert plain is not None and built is not None
    assert precedence_key(plain) == precedence_key(built)


def test_a_prerelease_ranks_below_its_stable_release() -> None:
    pre = parse_semver("1.0.0-rc.1")
    stable = parse_semver("1.0.0")
    assert pre is not None and stable is not None
    assert precedence_key(pre) < precedence_key(stable)


def test_prerelease_numeric_identifiers_order_numerically() -> None:
    # 1.0.0-alpha.9 < 1.0.0-alpha.10: numeric identifiers compare as numbers,
    # not as strings (where "10" would sort before "9").
    nine = parse_semver("1.0.0-alpha.9")
    ten = parse_semver("1.0.0-alpha.10")
    assert nine is not None and ten is not None
    assert precedence_key(nine) < precedence_key(ten)


def test_numeric_prerelease_ranks_below_alphanumeric() -> None:
    numeric = parse_semver("1.0.0-1")
    alpha = parse_semver("1.0.0-alpha")
    assert numeric is not None and alpha is not None
    assert precedence_key(numeric) < precedence_key(alpha)


def test_a_longer_prerelease_run_outranks_its_prefix() -> None:
    short = parse_semver("1.0.0-alpha")
    long = parse_semver("1.0.0-alpha.1")
    assert short is not None and long is not None
    assert precedence_key(short) < precedence_key(long)


def test_select_latest_excludes_prereleases_when_a_stable_tag_exists() -> None:
    versions = _parse_all(["1.0.0", "1.1.0", "1.2.0-rc.1"])
    latest = select_latest(versions)
    assert latest is not None
    assert latest.original == "1.1.0"


def test_select_latest_falls_back_to_the_highest_prerelease() -> None:
    versions = _parse_all(["1.0.0-alpha", "1.0.0-beta", "1.0.0-rc.1"])
    latest = select_latest(versions)
    assert latest is not None
    assert latest.original == "1.0.0-rc.1"


def test_select_latest_over_no_versions_is_none() -> None:
    assert select_latest([]) is None


def test_count_behind_counts_only_higher_stable_releases() -> None:
    pinned = parse_semver("1.0.0")
    versions = _parse_all(["0.9.0", "1.0.0", "1.1.0", "2.0.0", "2.1.0-rc.1"])
    assert pinned is not None
    # 1.1.0 and 2.0.0 are higher and stable; 2.1.0-rc.1 is a pre-release and 0.9.0
    # and the pin itself are not above the pin.
    assert count_behind(pinned, versions) == 2


def test_count_behind_is_zero_when_pinned_at_the_latest() -> None:
    pinned = parse_semver("2.0.0")
    versions = _parse_all(["1.0.0", "1.1.0", "2.0.0"])
    assert pinned is not None
    assert count_behind(pinned, versions) == 0


def test_parse_pinned_strips_a_git_describe_offset_suffix() -> None:
    # "1.0.0-2-gabc1234" means two commits past the 1.0.0 tag; it must rank as
    # 1.0.0, not as a pre-release of it.
    pinned = parse_pinned("1.0.0-2-gabc1234")
    assert pinned is not None
    assert (pinned.major, pinned.minor, pinned.patch) == (1, 0, 0)
    assert pinned.is_prerelease is False


def test_parse_pinned_reads_a_clean_tag() -> None:
    pinned = parse_pinned("1.0.0")
    assert pinned is not None
    assert pinned.original == "1.0.0"
