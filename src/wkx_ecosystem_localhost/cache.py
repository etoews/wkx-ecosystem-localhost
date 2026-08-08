"""A generic single-value cache with a time-to-live.

Holds exactly one value and the clock time it was stored at, so a repeated read
inside the TTL is served from memory and a read past it degrades to a miss. The
clock is injected (defaulting to ``time.monotonic``) so tests advance time with a
fake rather than sleeping. Monotonic time is deliberate: it never jumps backward
on a wall-clock adjustment, so a stored value cannot appear fresh forever.

This is what lets an expensive synchronous Collector be served behind a cheap
cache without a background refresh: the first request pays for the probe, the
rest of the TTL window is free, and the value is recomputed only once it expires.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class TtlCache[T]:
    """A one-slot cache whose stored value expires ``ttl`` seconds after it is set.

    ``get`` returns the stored value while it is fresh and None once the cache is
    empty or the value has expired, so a caller treats a miss and an empty cache
    alike: recompute and ``set``. Expiry is measured against the injected clock,
    and the boundary is exclusive, a value exactly ``ttl`` seconds old is already
    a miss.
    """

    def __init__(self, ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        """Build an empty cache.

        Args:
            ttl: How long, in seconds, a stored value stays fresh.
            clock: The time source, returning a monotonically increasing float.
                Defaults to ``time.monotonic``; tests inject a fake.
        """
        self._ttl = ttl
        self._clock = clock
        self._value: T | None = None
        self._stamp: float | None = None

    def get(self) -> T | None:
        """Return the stored value, or None when the cache is empty or expired."""
        if self._stamp is None:
            return None
        if self._clock() - self._stamp >= self._ttl:
            return None
        return self._value

    def set(self, value: T) -> None:
        """Store ``value``, stamping it with the current clock time."""
        self._value = value
        self._stamp = self._clock()
