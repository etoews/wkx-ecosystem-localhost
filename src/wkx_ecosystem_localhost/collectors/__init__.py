"""Collectors: pure functions from ``Machine`` probe results to typed models.

A Collector never touches subprocess or the filesystem directly; it reaches the
host only through the ``Machine`` seam and returns a model the API serialises
verbatim.
"""

import json
from typing import Any


def loads_or_none(text: str) -> Any | None:
    """``json.loads(text)``, or None if it is not valid JSON.

    Centralises the "a bad file or probe output degrades one row, never raises"
    contract every Collector needs, so the parse is written once and each caller
    keeps only the shape check it cares about (usually ``isinstance(data, dict)``).
    Returns ``Any`` like ``json.loads`` itself, so a caller narrows the parsed,
    untrusted value with its own ``isinstance`` check rather than a cast.
    """
    try:
        return json.loads(text)
    except ValueError, TypeError:
        return None
