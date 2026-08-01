"""Parser edge cases for the docker Collector, over synthetic fixtures.

The pure size helpers pinned against Docker's decimal-unit shapes: ``parse_size``
and ``parse_reclaimable`` reading a byte count, and ``humanise_size`` rendering one
back for display. Every string here is invented.
"""

from __future__ import annotations

import pytest

from wkx_ecosystem_localhost.collectors.docker import (
    humanise_size,
    parse_reclaimable,
    parse_size,
)


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("0B", 0.0),
        ("512B", 512.0),
        ("1.2kB", 1_200.0),
        ("80MB", 80_000_000.0),
        ("1.5GB", 1_500_000_000.0),
        ("2TB", 2_000_000_000_000.0),
    ],
)
def test_parse_size_reads_decimal_units(token: str, expected: float) -> None:
    assert parse_size(token) == expected


@pytest.mark.parametrize("token", ["", "GB", "1.2", "1.2ZB", "lots"])
def test_parse_size_absent_when_unreadable(token: str) -> None:
    assert parse_size(token) is None


def test_parse_reclaimable_takes_only_the_leading_size() -> None:
    # The percentage after the size must not be read as part of the byte count.
    assert parse_reclaimable("1.2GB (48%)") == 1_200_000_000.0


def test_parse_reclaimable_absent_when_empty() -> None:
    assert parse_reclaimable("") is None


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1_500_000_000, "1.5 GB"),
        (2_000_000_000, "2 GB"),
        (3_230_000_000, "3.23 GB"),
    ],
)
def test_humanise_size_trims_and_labels(num_bytes: float, expected: str) -> None:
    assert humanise_size(num_bytes) == expected
