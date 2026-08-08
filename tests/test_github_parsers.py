"""The GitHub owner/repo parser and its link companion, pinned to hand inputs.

These are the guarantees behind every repository link on the board: an https or
scp-style GitHub remote yields its ``owner`` and ``repo``, a non-GitHub remote
yields nothing, and the reconstructed link carries only the owner and repo, never
any credential that rode in the remote URL.
"""

from __future__ import annotations

import pytest

from wkx_ecosystem_localhost.github import github_link, parse_owner_repo


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
