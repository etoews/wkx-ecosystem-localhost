"""Parser edge cases for the editor Collector, over synthetic fixtures.

The two pure readers pinned against VS Code's own shapes: ``parse_code_version``
taking the version banner's first line, and ``parse_extensions`` splitting each
``publisher.name@version`` line into an id and a version. Every string here is
invented.
"""

from __future__ import annotations

import pytest

from wkx_ecosystem_localhost.collectors.editor import (
    parse_code_version,
    parse_extensions,
)


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        # The real three-line banner: version, commit hash, arch.
        ("1.96.0\n138f619c86f1199955d53b4166bef66ef252935c\narm64\n", "1.96.0"),
        # A bare single line.
        ("1.100.2\n", "1.100.2"),
        # Leading blank lines and surrounding whitespace are skipped and stripped.
        ("\n\n   1.96.0   \nhash\n", "1.96.0"),
    ],
)
def test_parse_code_version_takes_the_first_non_empty_line(stdout: str, expected: str) -> None:
    assert parse_code_version(stdout) == expected


@pytest.mark.parametrize("stdout", ["", "   ", "\n\n", "  \n \t \n"])
def test_parse_code_version_absent_when_no_content(stdout: str) -> None:
    assert parse_code_version(stdout) is None


def test_parse_extensions_splits_id_and_version_preserving_order() -> None:
    stdout = (
        "ms-python.python@2024.22.0\nesbenp.prettier-vscode@11.0.0\ndbaeumer.vscode-eslint@3.0.10\n"
    )
    extensions = parse_extensions(stdout)

    assert [(e.id, e.version) for e in extensions] == [
        ("ms-python.python", "2024.22.0"),
        ("esbenp.prettier-vscode", "11.0.0"),
        ("dbaeumer.vscode-eslint", "3.0.10"),
    ]


def test_parse_extensions_line_without_an_at_has_no_version() -> None:
    extensions = parse_extensions("ms-python.python\n")

    assert len(extensions) == 1
    assert extensions[0].id == "ms-python.python"
    assert extensions[0].version is None


def test_parse_extensions_splits_on_the_last_at_only() -> None:
    # rsplit keeps an id that itself contains an "@" whole, taking only the version.
    extensions = parse_extensions("scope@vendor.plugin@1.2.3\n")

    assert extensions[0].id == "scope@vendor.plugin"
    assert extensions[0].version == "1.2.3"


@pytest.mark.parametrize("stdout", ["", "\n\n", "   \n  \n"])
def test_parse_extensions_empty_when_no_lines(stdout: str) -> None:
    assert parse_extensions(stdout) == []


def test_parse_extensions_skips_blank_lines_between_entries() -> None:
    extensions = parse_extensions("a.one@1.0.0\n\n\nb.two@2.0.0\n")

    assert [e.id for e in extensions] == ["a.one", "b.two"]
