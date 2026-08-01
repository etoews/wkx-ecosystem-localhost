"""Redaction helpers: masking, credential stripping, home-relativisation.

These are the guarantees that make a screenshot of the board safe to share, so
they are pinned directly against hand-written inputs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wkx_ecosystem_localhost.redaction import (
    mask_email,
    relativise,
    relativise_text,
    strip_credentials,
)


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("ada.lovelace@example.com", "a•••@example.com"),
        ("x@example.org", "x•••@example.org"),
        ("first.last@sub.domain.io", "f•••@sub.domain.io"),
        ("not-an-email", "•••"),
        ("", "•••"),
    ],
)
def test_mask_email_hides_the_local_part_and_keeps_the_domain(email: str, expected: str) -> None:
    assert mask_email(email) == expected


def test_mask_email_does_not_leak_the_local_part_length() -> None:
    short = mask_email("ab@example.com")
    long = mask_email("abcdefghijk@example.com")

    assert short == long == "a•••@example.com"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://user:token@github.com/o/r.git", "https://github.com/o/r.git"),
        ("https://ghp_secret@github.com/o/r.git", "https://github.com/o/r.git"),
        ("https://github.com/o/r.git", "https://github.com/o/r.git"),
        ("ssh://git@github.com/o/r.git", "ssh://github.com/o/r.git"),
        ("https://x-token:pw@host:8443/o/r.git", "https://host:8443/o/r.git"),
        ("git@github.com:o/r.git", "git@github.com:o/r.git"),
        ("../relative/path", "../relative/path"),
    ],
)
def test_strip_credentials_removes_userinfo_from_scheme_urls(url: str, expected: str) -> None:
    assert strip_credentials(url) == expected


@pytest.mark.parametrize(
    ("path", "home", "expected"),
    [
        (Path("/home/dev/acme/web"), Path("/home"), "~/dev/acme/web"),
        (Path("/home"), Path("/home"), "~"),
        (Path("/opt/elsewhere/repo"), Path("/home"), "/opt/elsewhere/repo"),
    ],
)
def test_relativise_rewrites_paths_under_home(path: Path, home: Path, expected: str) -> None:
    assert relativise(path, home) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/home/dev/bin/editor --wait", "~/dev/bin/editor --wait"),
        ("/home", "~"),
        ("code --wait", "code --wait"),
        ("/home-backup/x", "/home-backup/x"),
    ],
)
def test_relativise_text_rewrites_only_a_real_home_prefix(text: str, expected: str) -> None:
    assert relativise_text(text, Path("/home")) == expected
