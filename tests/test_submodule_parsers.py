"""Parser edge cases for the submodule Collector, over synthetic fixtures.

The two pure parsers on the submodule path: reading ``.gitmodules`` into
``(name, path, url)`` triples, and reading ``git ls-remote --tags`` output into
distinct tag names. Both feed the semver ranking tested separately.
"""

from __future__ import annotations

import fixtures

from wkx_ecosystem_localhost.collectors.submodules import (
    parse_gitmodules,
    parse_ls_remote_tags,
)


def test_parse_gitmodules_reads_every_fully_specified_submodule() -> None:
    triples = parse_gitmodules(fixtures.GITMODULES_APP)

    assert triples == [
        ("libs/widgets", "libs/widgets", fixtures.WIDGETS_URL),
        ("tools/kit", "tools/kit", fixtures.KIT_URL),
    ]


def test_parse_gitmodules_skips_a_stanza_missing_its_url() -> None:
    text = '[submodule "half"]\n\tpath = half\n'
    assert parse_gitmodules(text) == []


def test_parse_gitmodules_of_an_empty_file_is_empty() -> None:
    assert parse_gitmodules("") == []


def test_parse_ls_remote_tags_dedupes_the_peeled_annotated_tag() -> None:
    tags = parse_ls_remote_tags(fixtures.LS_REMOTE_WIDGETS)

    # 2.0.0 is listed twice (the tag object and its peeled ^{} target) but
    # appears once, and order is preserved.
    assert tags == ["1.0.0", "1.2.0", "1.3.0", "2.0.0", "2.1.0-rc.1"]


def test_parse_ls_remote_tags_ignores_non_tag_refs() -> None:
    text = "aaaa\trefs/heads/main\nbbbb\trefs/tags/1.0.0\ncccc\tHEAD\n"
    assert parse_ls_remote_tags(text) == ["1.0.0"]


def test_parse_ls_remote_tags_of_empty_output_is_empty() -> None:
    assert parse_ls_remote_tags("") == []
