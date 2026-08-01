"""Parser edge cases for the background-fetch Collector, over synthetic output.

The one parser in the fetch path: turning ``git rev-list --left-right --count``
output into an ``(ahead, behind)`` pair, and refusing anything that is not the
expected two-integer line.
"""

from __future__ import annotations

import pytest

from wkx_ecosystem_localhost.collectors.fetch import parse_ahead_behind


def test_parse_ahead_behind_reads_behind_then_ahead() -> None:
    # rev-list prints "<behind>\t<ahead>"; the parser returns (ahead, behind).
    assert parse_ahead_behind("1\t3\n") == (3, 1)


def test_parse_ahead_behind_level_is_zero_zero() -> None:
    assert parse_ahead_behind("0\t0\n") == (0, 0)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n",
        "5",
        "1 2 3",
        "abc\tdef",
        "1\tx",
    ],
)
def test_parse_ahead_behind_rejects_malformed_output(text: str) -> None:
    assert parse_ahead_behind(text) is None
