"""Parser edge cases for the footprint Collector, over synthetic fixtures.

``parse_du_kib`` reads the KiB count from a ``du -sk`` line: its first
whitespace-separated token as an integer, tolerating the trailing path and
degrading a shapeless line to None. Every string here is invented.
"""

from __future__ import annotations

import pytest

from wkx_ecosystem_localhost.collectors.footprint import parse_du_kib


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("90104\t/x/.venv", 90104),
        ("512000\t/home/dev/acme/web/node_modules\n", 512000),
        ("  256000  /padded/path\n", 256000),
        ("0\t/empty/.venv", 0),
    ],
)
def test_parse_du_kib_reads_the_leading_count(stdout: str, expected: int) -> None:
    assert parse_du_kib(stdout) == expected


@pytest.mark.parametrize("stdout", ["", "garbage", "garbage\t/x/.venv", "   ", "\n"])
def test_parse_du_kib_absent_when_unreadable(stdout: str) -> None:
    assert parse_du_kib(stdout) is None
