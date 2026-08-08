"""The generic single-value TTL cache, driven with a fake clock.

A mutable clock (a one-element list read through a closure) lets these tests
advance time deterministically, so the store, the within-TTL hit, and the
expiry-to-miss transition are pinned without any real waiting.
"""

from __future__ import annotations

from collections.abc import Callable

from wkx_ecosystem_localhost.cache import TtlCache


def _fake_clock() -> tuple[list[float], Callable[[], float]]:
    now = [0.0]
    return now, lambda: now[0]


def test_empty_cache_returns_none() -> None:
    _now, clock = _fake_clock()
    cache: TtlCache[str] = TtlCache(60.0, clock)

    assert cache.get() is None


def test_get_within_ttl_returns_the_value() -> None:
    now, clock = _fake_clock()
    cache: TtlCache[str] = TtlCache(60.0, clock)

    now[0] = 100.0
    cache.set("cached")
    now[0] = 150.0  # 50s later, still within the 60s TTL

    assert cache.get() == "cached"


def test_get_after_ttl_elapsed_returns_none() -> None:
    now, clock = _fake_clock()
    cache: TtlCache[str] = TtlCache(60.0, clock)

    now[0] = 100.0
    cache.set("cached")
    now[0] = 170.0  # 70s later, past the 60s TTL

    assert cache.get() is None


def test_expiry_boundary_at_exactly_ttl_is_a_miss() -> None:
    now, clock = _fake_clock()
    cache: TtlCache[str] = TtlCache(60.0, clock)

    now[0] = 100.0
    cache.set("cached")
    now[0] = 160.0  # exactly the TTL later

    assert cache.get() is None


def test_set_refreshes_the_stamp() -> None:
    now, clock = _fake_clock()
    cache: TtlCache[str] = TtlCache(60.0, clock)

    now[0] = 100.0
    cache.set("first")
    now[0] = 150.0
    cache.set("second")  # resets the clock stamp
    now[0] = 200.0  # 50s after the second set, still within TTL

    assert cache.get() == "second"
