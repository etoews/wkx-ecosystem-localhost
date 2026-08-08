"""Parser edge cases for the git-config Collector, over synthetic fixtures.

The three pure functions pinned against invented input: ``parse_git_config``
splitting ``--show-origin`` lines into key/value/origin, ``redact_value`` deciding
what a value shows and whether it is masked per ADR 0001, and ``is_multivar``
recognising the legitimately multi-valued keys that must never read as a conflict.
Every string here is invented, never captured from a real machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wkx_ecosystem_localhost.collectors.git_config import (
    is_multivar,
    parse_git_config,
    redact_value,
)

HOME = Path("/home")

# One synthetic ``git config --global --list --show-origin --includes`` block. Each
# line is ``file:<abs-path>\t<key>=<value>``. It carries: a normal key; a key from
# an included file (a different origin); a single-valued key (``core.editor``)
# duplicated across two origins with different values (a real conflict); a
# multi-valued ``url.<base>.insteadof`` appearing twice with different values (not a
# conflict); an ``include.path`` directive; and an ``includeif.gitdir:<pattern>.path``
# directive.
GITCONFIG_BLOCK = (
    "file:/home/.gitconfig\tuser.email=ada@example.com\n"
    "file:/home/.gitconfig\tcore.editor=vim\n"
    "file:/home/.gitconfig-work\tuser.name=Ada Lovelace\n"
    "file:/home/.gitconfig-work\tcore.editor=code --wait\n"
    "file:/home/.gitconfig\turl.git@github.com:.insteadof=https://github.com/\n"
    "file:/home/.gitconfig\turl.git@github.com:.insteadof=git://github.com/\n"
    "file:/home/.gitconfig\tinclude.path=~/.gitconfig-work\n"
    "file:/home/.gitconfig\tincludeif.gitdir:~/dev/etoews/.path=~/dev/etoews/.gitconfig\n"
)


def test_parse_git_config_reads_every_line_in_order() -> None:
    parsed = parse_git_config(GITCONFIG_BLOCK)
    assert parsed == [
        {"key": "user.email", "value": "ada@example.com", "origin_path": "/home/.gitconfig"},
        {"key": "core.editor", "value": "vim", "origin_path": "/home/.gitconfig"},
        {"key": "user.name", "value": "Ada Lovelace", "origin_path": "/home/.gitconfig-work"},
        {"key": "core.editor", "value": "code --wait", "origin_path": "/home/.gitconfig-work"},
        {
            "key": "url.git@github.com:.insteadof",
            "value": "https://github.com/",
            "origin_path": "/home/.gitconfig",
        },
        {
            "key": "url.git@github.com:.insteadof",
            "value": "git://github.com/",
            "origin_path": "/home/.gitconfig",
        },
        {"key": "include.path", "value": "~/.gitconfig-work", "origin_path": "/home/.gitconfig"},
        {
            "key": "includeif.gitdir:~/dev/etoews/.path",
            "value": "~/dev/etoews/.gitconfig",
            "origin_path": "/home/.gitconfig",
        },
    ]


def test_parse_git_config_splits_value_on_the_first_equals() -> None:
    # An alias value carries its own '=' which must ride along in the value.
    parsed = parse_git_config("file:/home/.gitconfig\talias.lg=log --pretty=oneline\n")
    assert parsed == [
        {"key": "alias.lg", "value": "log --pretty=oneline", "origin_path": "/home/.gitconfig"}
    ]


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "file:/home/.gitconfig\tuser.name",  # no '=' at all
        "user.name=Ada",  # no tab, so no origin
    ],
)
def test_parse_git_config_skips_unshaped_lines(line: str) -> None:
    assert parse_git_config(line) == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("http.https://github.com/.extraheader", "AUTHORIZATION: bearer tok"),
        ("credential.helper", "!aws codecommit credential-helper"),
        ("github.token", "ghp_secret"),
        ("myservice.password", "hunter2"),
        ("acme.apisecret", "sk-live-xyz"),
        ("foo.authorization", "Bearer abc"),
    ],
)
def test_redact_value_masks_the_secret_families(key: str, value: str) -> None:
    assert redact_value(key, value, HOME) == ("•••", True)


def test_redact_value_shows_user_email_unmasked() -> None:
    # user.email is not a secret family on a loopback-only board; ADR 0001.
    assert redact_value("user.email", "ada@example.com", HOME) == ("ada@example.com", False)


def test_redact_value_strips_credentials_from_a_url_value() -> None:
    display, masked = redact_value(
        "remote.origin.url", "https://ada:ghp_tok@github.com/ada/x.git", HOME
    )
    assert display == "https://github.com/ada/x.git"
    assert masked is False


def test_redact_value_relativises_a_home_path_in_the_value() -> None:
    display, masked = redact_value("core.editor", "/home/bin/edit --wait", HOME)
    assert display == "~/bin/edit --wait"
    assert masked is False


@pytest.mark.parametrize(
    "key",
    [
        "url.git@github.com:.insteadof",
        "url.ssh://git@gitlab.com/.insteadOf",
        "remote.origin.pushInsteadOf",
        "remote.origin.fetch",
        "remote.origin.push",
    ],
)
def test_is_multivar_recognises_the_multi_valued_families(key: str) -> None:
    assert is_multivar(key) is True


@pytest.mark.parametrize("key", ["core.editor", "user.email", "user.name", "include.path"])
def test_is_multivar_false_for_single_valued_keys(key: str) -> None:
    assert is_multivar(key) is False
