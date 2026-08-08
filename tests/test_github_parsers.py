"""The GitHub owner/repo parser and its link companion, pinned to hand inputs.

These are the guarantees behind every repository link on the board: an https or
scp-style GitHub remote yields its ``owner`` and ``repo``, a non-GitHub remote
yields nothing, and the reconstructed link carries only the owner and repo, never
any credential that rode in the remote URL.
"""

from __future__ import annotations

import pytest

from wkx_ecosystem_localhost.github import (
    github_link,
    parse_owner_repo,
    release_differs,
    release_tag_from_redirect,
    releases_latest_url,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # https, with and without the .git suffix and a trailing slash.
        ("https://github.com/octocat/Hello-World", ("octocat", "Hello-World")),
        ("https://github.com/octocat/Hello-World.git", ("octocat", "Hello-World")),
        ("https://github.com/octocat/Hello-World/", ("octocat", "Hello-World")),
        ("https://github.com/octocat/Hello-World.git/", ("octocat", "Hello-World")),
        # scp-style, with and without the .git suffix.
        ("git@github.com:octocat/Hello-World.git", ("octocat", "Hello-World")),
        ("git@github.com:octocat/Hello-World", ("octocat", "Hello-World")),
        # ssh scheme with the conventional git user.
        ("ssh://git@github.com/octocat/Hello-World.git", ("octocat", "Hello-World")),
        # A tokened https remote: the userinfo must not derail host detection, and
        # only owner and repo survive.
        ("https://ada:ghp_secret@github.com/octocat/Hello-World.git", ("octocat", "Hello-World")),
        # A host with a port.
        ("https://github.com:443/octocat/Hello-World.git", ("octocat", "Hello-World")),
    ],
)
def test_parse_owner_repo_reads_both_github_forms(
    url: str, expected: tuple[str, str]
) -> None:
    assert parse_owner_repo(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        # A non-GitHub host in either form.
        "https://gitlab.com/octocat/Hello-World.git",
        "git@bitbucket.org:octocat/Hello-World.git",
        "https://example.com/acme/widgets.git",
        # Nothing to parse.
        "",
        "not-a-remote-url",
        # GitHub host but no repo segment.
        "https://github.com/",
        "https://github.com/onlyowner",
        "git@github.com:onlyowner",
    ],
)
def test_parse_owner_repo_returns_none_for_a_non_github_or_incomplete_remote(url: str) -> None:
    assert parse_owner_repo(url) is None


def test_github_link_yields_the_repository_url_for_a_github_remote() -> None:
    assert github_link("git@github.com:octocat/Hello-World.git") == (
        "https://github.com/octocat/Hello-World"
    )


def test_github_link_returns_none_for_a_non_github_remote() -> None:
    assert github_link("https://example.com/acme/widgets.git") is None


def test_github_link_never_carries_a_credential_that_rode_in_the_remote() -> None:
    link = github_link("https://ada:ghp_secret@github.com/octocat/Hello-World.git")

    assert link == "https://github.com/octocat/Hello-World"
    assert "ghp_secret" not in (link or "")


def test_releases_latest_url_builds_the_public_redirect_target_for_a_github_remote() -> None:
    assert releases_latest_url("git@github.com:octocat/Hello-World.git") == (
        "https://github.com/octocat/Hello-World/releases/latest"
    )


def test_releases_latest_url_is_none_for_a_non_github_remote() -> None:
    assert releases_latest_url("https://example.com/acme/widgets.git") is None


def test_releases_latest_url_never_carries_a_credential_that_rode_in_the_remote() -> None:
    url = releases_latest_url("https://ada:ghp_secret@github.com/octocat/Hello-World.git")

    assert url == "https://github.com/octocat/Hello-World/releases/latest"
    assert "ghp_secret" not in (url or "")


@pytest.mark.parametrize(
    ("redirect", "expected"),
    [
        # A released repo redirects releases/latest to releases/tag/<TAG>.
        ("https://github.com/acme/widgets/releases/tag/1.3.0", "1.3.0"),
        ("https://github.com/acme/widgets/releases/tag/v2.0.0", "v2.0.0"),
        # A trailing slash on the resolved URL is trimmed.
        ("https://github.com/acme/widgets/releases/tag/1.3.0/", "1.3.0"),
        # A tag carrying a slash arrives percent-encoded and is decoded back.
        ("https://github.com/acme/widgets/releases/tag/release%2Fnightly", "release/nightly"),
    ],
)
def test_release_tag_from_redirect_extracts_the_tag(redirect: str, expected: str) -> None:
    assert release_tag_from_redirect(redirect) == expected


@pytest.mark.parametrize(
    "redirect",
    [
        # A repo with no release redirects to the bare releases page: no /tag/.
        "https://github.com/acme/widgets/releases",
        "https://github.com/acme/widgets/releases/",
        # Nothing usable at all.
        "",
        "https://github.com/acme/widgets",
    ],
)
def test_release_tag_from_redirect_is_none_without_a_tag_segment(redirect: str) -> None:
    assert release_tag_from_redirect(redirect) is None


@pytest.mark.parametrize(
    ("release", "latest", "expected"),
    [
        # The blessed release names an older version than the highest tag: differs.
        ("1.9.0", "2.0.0", True),
        # The blessed release names a version git's semver ranking cannot see.
        ("nightly", "2.0.0", True),
        # A release but no tag-based latest to sit beside: surface it.
        ("2.0.0", None, True),
        # They name the same version, so nothing extra is shown.
        ("2.0.0", "2.0.0", False),
        # The same version formatted differently is still the same version.
        ("v2.0.0", "2.0.0", False),
        ("2.0.0", "v2.0.0", False),
        # No release means nothing differs.
        (None, "2.0.0", False),
        (None, None, False),
    ],
)
def test_release_differs_decides_when_to_surface_the_blessed_release(
    release: str | None, latest: str | None, expected: bool
) -> None:
    assert release_differs(release, latest) is expected
