"""The homebrew Collector: outdated formulae and casks as a list with a count.

Runs a single ``brew outdated --json=v2`` through the ``Machine`` seam and reports
the outdated packages, split into formulae and casks. Homebrew's absence is a
fact, never an error: a machine without ``brew`` reports ``present=False`` and two
empty lists, so the board renders it plainly. The JSON reader is pure, so its
edge cases pin directly against synthetic fixtures. Facts only; anomaly judgement
is the separate M6 Flag layer.
"""

from __future__ import annotations

import json
import logging

from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import HomebrewSection, OutdatedPackage

logger = logging.getLogger(__name__)

# The one probe this Collector runs. The v2 JSON shape carries formulae and casks
# together, each with its installed and current versions, in a single call.
BREW_OUTDATED_ARGV = ("brew", "outdated", "--json=v2")

# Per-probe wall-clock ceiling. Generous for a local metadata read, tight enough
# that a wedged brew degrades this one Section rather than hanging the board.
PROBE_TIMEOUT_S = 15.0


def _package(entry: object) -> OutdatedPackage | None:
    """Read one outdated entry into a package, or None when it is unusable.

    Homebrew records ``installed_versions`` as a list; it is joined for display so
    a package tracked at more than one version still reads as a single fact. An
    entry missing a name is skipped rather than half-reported.
    """
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    installed = entry.get("installed_versions")
    installed_text = ", ".join(str(v) for v in installed) if isinstance(installed, list) else ""
    current = entry.get("current_version")
    current_text = current if isinstance(current, str) else ""
    return OutdatedPackage(name=name, installed=installed_text, current=current_text)


def parse_brew_outdated(text: str) -> tuple[list[OutdatedPackage], list[OutdatedPackage]]:
    """Parse ``brew outdated --json=v2`` into outdated formulae and casks.

    The v2 payload is an object with ``formulae`` and ``casks`` arrays. Each array
    is read into packages in listing order; a malformed entry is skipped and
    malformed JSON yields two empty lists rather than raising, so one bad payload
    degrades a single Section.

    Args:
        text: The stdout of ``brew outdated --json=v2``.

    Returns:
        A ``(formulae, casks)`` pair of outdated packages.
    """
    try:
        data = json.loads(text)
    except ValueError, TypeError:
        return [], []
    if not isinstance(data, dict):
        return [], []

    def read(key: str) -> list[OutdatedPackage]:
        raw = data.get(key)
        if not isinstance(raw, list):
            return []
        packages = [_package(entry) for entry in raw]
        return [pkg for pkg in packages if pkg is not None]

    return read("formulae"), read("casks")


def collect_homebrew(machine: Machine, *, timeout: float = PROBE_TIMEOUT_S) -> HomebrewSection:
    """Collect the homebrew Section: outdated formulae and casks, or its absence.

    A pure Collector over the seam. The one probe reaches the host only through
    ``machine``, so the whole Section is exercised in tests against a fake. A
    non-zero exit (including a missing ``brew``) reports ``present=False`` with two
    empty lists: an absent Homebrew is a fact to show, not an error. No judgement
    is applied; a package being outdated is left plain for the M6 Flag layer.

    Args:
        machine: The seam the probe runs through.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The Section model: present with any outdated packages, or absent.
    """
    result = machine.run(BREW_OUTDATED_ARGV, timeout=timeout)
    if not result.ok:
        return HomebrewSection(present=False)
    formulae, casks = parse_brew_outdated(result.stdout)
    return HomebrewSection(present=True, formulae=formulae, casks=casks)
