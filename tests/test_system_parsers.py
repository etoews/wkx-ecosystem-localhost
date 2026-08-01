"""Parser edge cases for the system Collector, over synthetic fixtures.

The single tolerant reader, ``parse_tool_version``, pinned against each tool's own
version format: labelled, slash-packed, comma-trailed with a build hash, v-prefixed
and multi-line, and bare. Every string here is invented.
"""

from __future__ import annotations

import fixtures
import pytest

from wkx_ecosystem_localhost.collectors.system import parse_tool_version


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (fixtures.GIT_VERSION, "2.39.5"),
        (fixtures.GH_VERSION, "2.63.2"),
        (fixtures.UV_VERSION, "0.5.11"),
        (fixtures.DOCKER_VERSION, "27.4.0"),
        (fixtures.TERRAFORM_VERSION, "1.10.2"),
        (fixtures.AWS_VERSION, "2.22.19"),
        (fixtures.CODE_VERSION, "1.96.0"),
        (fixtures.NODE_VERSION_OUT, "22.12.0"),
        (fixtures.WIDGET_VERSION, "3.2.1"),
    ],
)
def test_parse_tool_version_tolerates_each_tools_format(text: str, expected: str) -> None:
    assert parse_tool_version(text) == expected


def test_parse_tool_version_ignores_a_trailing_build_hash() -> None:
    # The build hash after the comma is not version-shaped, so the version wins.
    assert parse_tool_version("Docker version 27.4.0, build bde2b89") == "27.4.0"


def test_parse_tool_version_reads_a_two_part_version() -> None:
    assert parse_tool_version("toolx 3.2\n") == "3.2"


def test_parse_tool_version_keeps_a_pre_release_suffix() -> None:
    assert parse_tool_version("thing 1.2.3-rc.1\n") == "1.2.3-rc.1"


@pytest.mark.parametrize("text", ["", "   \n", "no version here\n"])
def test_parse_tool_version_absent_when_no_version_shaped_token(text: str) -> None:
    assert parse_tool_version(text) is None
