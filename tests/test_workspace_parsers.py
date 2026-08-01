"""Parser edge cases, tested directly against synthetic fixtures.

Low-altitude tests over the same fixtures the HTTP tests use: porcelain v2
variants, detached HEAD, stash counting, and the config whitelist with its
masking and credential stripping.
"""

from __future__ import annotations

import fixtures
import pytest

from wkx_ecosystem_localhost.collectors.workspace import (
    parse_config,
    parse_stash,
    parse_status,
)


def test_parse_status_clean_branch_with_upstream() -> None:
    status = parse_status(fixtures.STATUS_CLEAN)

    assert status.branch == "main"
    assert status.detached_sha is None
    assert status.upstream == "origin/main"
    assert (status.staged, status.unstaged, status.untracked, status.unmerged) == (0, 0, 0, 0)


def test_parse_status_counts_staged_unstaged_and_untracked() -> None:
    status = parse_status(fixtures.STATUS_DIRTY)

    assert status.branch == "feature/login"
    assert status.upstream == "origin/feature/login"
    assert status.staged == 2
    assert status.unstaged == 2
    assert status.untracked == 2
    assert status.unmerged == 0


def test_parse_status_detached_reports_short_sha_and_no_branch() -> None:
    status = parse_status(fixtures.STATUS_DETACHED)

    assert status.branch is None
    assert status.detached_sha == "3333333"
    assert status.upstream is None
    assert status.unstaged == 1


def test_parse_status_branch_without_upstream() -> None:
    status = parse_status(fixtures.STATUS_NO_UPSTREAM)

    assert status.branch == "wip"
    assert status.upstream is None
    assert status.staged == status.unstaged == status.untracked == 0


def test_parse_status_counts_unmerged_separately() -> None:
    status = parse_status(fixtures.STATUS_UNMERGED)

    assert status.unmerged == 1
    assert status.untracked == 1
    assert status.staged == 0
    assert status.unstaged == 0


def test_parse_status_counts_a_rename_as_staged() -> None:
    status = parse_status(fixtures.STATUS_RENAMED)

    assert status.staged == 1
    assert status.unstaged == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (fixtures.STASH_EMPTY, 0),
        (fixtures.STASH_THREE, 3),
    ],
)
def test_parse_stash_counts_lines(text: str, expected: int) -> None:
    assert parse_stash(text) == expected


def test_parse_config_keeps_only_whitelisted_keys() -> None:
    entries = parse_config(fixtures.CONFIG_MIXED)

    keys = [e.key for e in entries]
    assert keys == [
        "user.name",
        "user.email",
        "init.defaultbranch",
        "core.editor",
        "commit.gpgsign",
        "remote.origin.url",
        "user.email",
    ]


def test_parse_config_drops_key_material() -> None:
    entries = parse_config(fixtures.CONFIG_MIXED)

    keys = {e.key for e in entries}
    assert "user.signingkey" not in keys
    assert "gpg.format" not in keys


def test_parse_config_masks_email_and_carries_raw_for_reveal() -> None:
    entries = parse_config(fixtures.CONFIG_MIXED)
    global_email = next(e for e in entries if e.key == "user.email" and e.scope == "global")

    assert global_email.value == "a•••@example.com"
    assert global_email.raw == "ada.lovelace@example.com"


def test_parse_config_strips_credentials_from_remotes_without_a_raw_leak() -> None:
    entries = parse_config(fixtures.CONFIG_MIXED)
    remote = next(e for e in entries if e.key == "remote.origin.url")

    assert remote.value == "https://github.com/ada/analytical-engine.git"
    assert remote.raw is None
    assert remote.scope == "local"


def test_parse_config_ignores_malformed_lines() -> None:
    text = "\nglobal\tuser.name=Ada\nglobal\tno-equals-here\nnot-a-config-line\n"

    entries = parse_config(text)

    assert [(e.key, e.value) for e in entries] == [("user.name", "Ada")]
