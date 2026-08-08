"""The docker Collector: daemon reachability and a few container-and-disk facts.

Two read-only probes through the ``Machine`` seam: ``docker info`` for the daemon
and its container and image counts, and ``docker system df`` for the total and
reclaimable disk. A daemon that cannot be reached (down, or the CLI absent) is a fact, never
an error: the Section reports ``daemon_reachable=False`` and the board renders it
plainly. The count reader and the size parsers are pure, so their edge cases pin
directly against synthetic fixtures. Facts only; anomaly judgement is the separate
M6 Flag layer.
"""

from __future__ import annotations

import json
import logging
import re

from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import DockerSection

logger = logging.getLogger(__name__)

# The two probes this Collector runs. ``info`` reports the daemon and its counts
# as one JSON object; ``system df`` reports one JSON object per resource type,
# each carrying a reclaimable size, so the whole reclaimable disk sums in one call.
DOCKER_INFO_ARGV = ("docker", "info", "--format", "{{json .}}")
DOCKER_DF_ARGV = ("docker", "system", "df", "--format", "{{json .}}")

# Per-probe wall-clock ceiling. Generous for a local daemon query, tight enough
# that a wedged daemon degrades this one Section rather than hanging the board.
PROBE_TIMEOUT_S = 10.0

# Docker humanises sizes with decimal (1000-based) units, so the multipliers are
# powers of 1000 keyed by the lowercase unit. A size token is a number and a unit,
# for example ``1.23GB`` or ``623.3MB`` or ``0B``.
_UNIT_MULTIPLIERS = {
    "b": 1,
    "kb": 1_000,
    "mb": 1_000_000,
    "gb": 1_000_000_000,
    "tb": 1_000_000_000_000,
    "pb": 1_000_000_000_000_000,
}
_SIZE_RE = re.compile(r"^\s*([\d.]+)\s*([a-zA-Z]+)\s*$")
_UNIT_LADDER = ["B", "kB", "MB", "GB", "TB", "PB"]


def parse_size(token: str) -> float | None:
    """Parse a Docker size token such as ``1.23GB`` into a byte count.

    Docker's units are decimal (1000-based), so ``1kB`` is 1000 bytes. A token
    that is not a number followed by a known unit yields None, so an unexpected
    shape degrades a single figure rather than raising.

    Args:
        token: A size token, for example ``623.3MB`` or ``0B``.

    Returns:
        The size in bytes, or None when the token cannot be read.
    """
    match = _SIZE_RE.match(token)
    if match is None:
        return None
    multiplier = _UNIT_MULTIPLIERS.get(match.group(2).lower())
    if multiplier is None:
        return None
    try:
        return float(match.group(1)) * multiplier
    except ValueError:
        return None


def parse_reclaimable(field: str) -> float | None:
    """Read the byte count from a ``docker system df`` reclaimable field.

    The field pairs a size with a percentage, for example ``1.2GB (48%)``; only
    the leading size is read. An empty or unreadable field yields None.

    Args:
        field: The ``Reclaimable`` field, for example ``1.2GB (48%)``.

    Returns:
        The reclaimable bytes, or None when the field cannot be read.
    """
    head = field.split()[0] if field.split() else ""
    return parse_size(head)


def humanise_size(num_bytes: float) -> str:
    """Render a byte count as a display-ready decimal size such as ``3.23 GB``.

    Uses the same decimal ladder Docker reports in, and trims trailing zeros so a
    whole number reads as ``2 GB`` rather than ``2.00 GB``.

    Args:
        num_bytes: The size in bytes.

    Returns:
        A short human string with a unit, for example ``512 B`` or ``3.23 GB``.
    """
    value = float(num_bytes)
    for unit in _UNIT_LADDER:
        if value < 1000 or unit == _UNIT_LADDER[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            trimmed = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{trimmed} {unit}"
        value /= 1000
    # Unreachable: the loop always returns on the last unit.
    return f"{value} PB"


def _int_field(data: dict[str, object], key: str) -> int:
    """Read an integer count from the info payload, defaulting to 0 when absent."""
    value = data.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _disk(machine: Machine, *, timeout: float) -> tuple[str | None, str | None]:
    """Sum the total and reclaimable disk ``docker system df`` reports, display-ready.

    Each line is one resource type carrying a total ``Size`` and a
    ``Reclaimable`` slice of it; both are summed across the resource types in one
    pass and humanised. Either figure is None when no line yielded a readable
    value, so the board shows a labelled unknown rather than an invented zero, and
    both are None when the probe cannot be read at all.

    Returns:
        A ``(total_disk, reclaimable)`` pair, each a display-ready size or None.
    """
    result = machine.run(DOCKER_DF_ARGV, timeout=timeout)
    if not result.ok:
        return None, None
    total = 0.0
    reclaimable = 0.0
    total_seen = False
    reclaimable_seen = False
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError, TypeError:
            continue
        if not isinstance(row, dict):
            continue
        size_field = row.get("Size")
        if isinstance(size_field, str):
            size = parse_size(size_field)
            if size is not None:
                total += size
                total_seen = True
        reclaimable_field = row.get("Reclaimable")
        if isinstance(reclaimable_field, str):
            slice_ = parse_reclaimable(reclaimable_field)
            if slice_ is not None:
                reclaimable += slice_
                reclaimable_seen = True
    return (
        humanise_size(total) if total_seen else None,
        humanise_size(reclaimable) if reclaimable_seen else None,
    )


def collect_docker(machine: Machine, *, timeout: float = PROBE_TIMEOUT_S) -> DockerSection:
    """Collect the docker Section: daemon reachability, counts, and reclaimable disk.

    A pure Collector over the seam. Both probes reach the host only through
    ``machine``, so the whole Section is exercised in tests against a fake. A
    non-zero ``docker info`` (daemon down, or the CLI absent) reports
    ``daemon_reachable=False`` with empty counts: an unreachable daemon is a fact
    to show, not an error. No judgement is applied; the down state is left plain
    for the M6 Flag layer.

    Args:
        machine: The seam both probes run through.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The Section model: reachable with counts and reclaimable disk, or down.
    """
    info = machine.run(DOCKER_INFO_ARGV, timeout=timeout)
    if not info.ok:
        return DockerSection(daemon_reachable=False)
    try:
        data = json.loads(info.stdout)
    except ValueError, TypeError:
        data = None
    if not isinstance(data, dict):
        return DockerSection(daemon_reachable=False)
    total_disk, reclaimable = _disk(machine, timeout=timeout)
    return DockerSection(
        daemon_reachable=True,
        containers_running=_int_field(data, "ContainersRunning"),
        containers_total=_int_field(data, "Containers"),
        images=_int_field(data, "Images"),
        total_disk=total_disk,
        reclaimable=reclaimable,
    )
