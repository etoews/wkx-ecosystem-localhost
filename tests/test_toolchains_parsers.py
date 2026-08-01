"""Parser edge cases for the toolchains Collector, over synthetic fixtures.

The pure parsers on the toolchains path: reading ``uv python list`` into entries,
pulling a version out of assorted ``--version`` shapes, and reading declared and
installed TypeScript out of ``package.json`` files. Every string here is invented.
"""

from __future__ import annotations

import fixtures
import pytest

from wkx_ecosystem_localhost.collectors.toolchains import (
    UvPythonEntry,
    parse_declared_typescript,
    parse_installed_typescript,
    parse_uv_python_list,
    parse_version,
    strip_ansi,
)


def test_parse_uv_python_list_reads_installed_and_available_lines() -> None:
    entries = parse_uv_python_list(fixtures.UV_PYTHON_LIST)

    # One entry per line, including the duplicate 3.14.4; de-duplication is the
    # Collector's job, not the parser's.
    assert len(entries) == 5
    assert UvPythonEntry("cpython", "3.15.0a8", False, None) in entries
    assert UvPythonEntry("pypy", "3.11.11", False, None) in entries


def test_parse_uv_python_list_keeps_the_bin_side_of_a_symlink() -> None:
    entries = parse_uv_python_list(fixtures.UV_PYTHON_LIST)

    symlinked = next(e for e in entries if e.path == "/home/.local/bin/python3.14")
    assert symlinked.installed is True
    assert symlinked.path == "/home/.local/bin/python3.14"


def test_parse_uv_python_list_strips_ansi_colour() -> None:
    coloured = "cpython-3.14.4-macos-aarch64-none    \x1b[2m<download available>\x1b[0m\n"

    (entry,) = parse_uv_python_list(coloured)

    assert entry == UvPythonEntry("cpython", "3.14.4", False, None)


def test_parse_uv_python_list_skips_an_unrecognisable_line() -> None:
    assert parse_uv_python_list("not a python key line\n") == []


def test_strip_ansi_removes_only_escape_sequences() -> None:
    assert strip_ansi("\x1b[36m/home/x\x1b[39m") == "/home/x"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Python 3.14.5\n", "3.14.5"),
        ("v24.15.0\n", "24.15.0"),
        ("11.12.1\n", "11.12.1"),
        ("Version 5.3.3\n", "5.3.3"),
        ("", None),
        ("   \n", None),
    ],
)
def test_parse_version_handles_the_common_shapes(text: str, expected: str | None) -> None:
    assert parse_version(text) == expected


def test_parse_declared_typescript_prefers_dev_dependencies() -> None:
    assert parse_declared_typescript(fixtures.WEB_PACKAGE_JSON) == "^5.4.0"


def test_parse_declared_typescript_reads_runtime_dependencies() -> None:
    assert parse_declared_typescript(fixtures.API_PACKAGE_JSON) == "~5.2.0"


def test_parse_declared_typescript_absent_when_not_declared() -> None:
    assert parse_declared_typescript(fixtures.CLI_PACKAGE_JSON) is None


def test_parse_declared_typescript_of_malformed_json_is_none() -> None:
    assert parse_declared_typescript("{ not json") is None


def test_parse_installed_typescript_reads_the_concrete_version() -> None:
    assert parse_installed_typescript(fixtures.WEB_INSTALLED_TS) == "5.3.3"


def test_parse_installed_typescript_of_malformed_json_is_none() -> None:
    assert parse_installed_typescript("") is None
