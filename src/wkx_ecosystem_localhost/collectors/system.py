"""The system Collector: a configurable probe of developer CLIs.

Runs each configured tool's version command through the ``Machine`` seam and
reports it as present-with-version or missing. The tool list is typed
configuration with a generic default, so a machine extends the probe by naming
more tools in the environment, never by editing this file.

Every tool reports its version in its own shape (``git version 2.39.5``,
``Docker version 27.4.0, build …``, ``aws-cli/2.22.19 Python/…``, a bare
``v22.12.0``), so ``parse_tool_version`` is a single tolerant reader pinned
against fixtures for each shape. It is pure, so its edge cases pin directly.
Facts only; anomaly judgement is the separate M6 Flag layer.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from wkx_ecosystem_localhost.config import ToolSpec
from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import SystemToolsSection, Tool

logger = logging.getLogger(__name__)

# Per-probe wall-clock ceiling. Generous for a local version command, tight
# enough that a wedged tool degrades one row instead of hanging the board.
PROBE_TIMEOUT_S = 5.0

# The first version-shaped token anywhere in the output: a dotted number of two
# or three parts, with an optional pre-release or build suffix. Anchored on the
# digits (not a leading "v") so ``v22.12.0`` and a bare ``22.12.0`` read alike,
# and stopping before trailing noise so ``Docker version 27.4.0, build bde2b89``
# yields the version, never the build hash.
_VERSION_RE = re.compile(r"\d+\.\d+(?:\.\d+)?(?:[-+.][0-9A-Za-z][0-9A-Za-z.\-+]*)?")


def parse_tool_version(text: str) -> str | None:
    """Extract a version number from a tool's version output.

    Searches for the first version-shaped token, tolerating each tool's own
    format: a labelled ``git version 2.39.5`` or ``Terraform v1.10.2``, a
    slash-packed ``aws-cli/2.22.19 Python/3.12.6``, a ``Docker version 27.4.0,
    build bde2b89`` where the build hash must not win, a multi-line ``code``
    banner whose first line is the version, and a bare ``v22.12.0``.

    Args:
        text: The tool's version output (stdout, or stderr as a fallback).

    Returns:
        The version string, or None when no version-shaped token is present.
    """
    match = _VERSION_RE.search(text)
    return match.group(0) if match else None


def _probe_tool(machine: Machine, spec: ToolSpec, *, timeout: float) -> Tool:
    """Probe one configured tool's presence and version through the seam.

    A non-zero exit (including a missing program) or output with no version-shaped
    token is reported as missing, never raised: an absent tool is a fact to show,
    not an error, so one wedged probe degrades a single row.
    """
    result = machine.run(spec.argv(), timeout=timeout)
    if not result.ok:
        return Tool(name=spec.name, version=None, present=False)
    version = parse_tool_version(result.stdout or result.stderr)
    return Tool(name=spec.name, version=version, present=version is not None)


def collect_system_tools(
    machine: Machine,
    tools: Sequence[ToolSpec],
    *,
    timeout: float = PROBE_TIMEOUT_S,
) -> SystemToolsSection:
    """Collect the system Section: probe each configured tool for its version.

    A pure Collector over the seam. Every probe reaches the host only through
    ``machine``, so the whole Section is exercised in tests against a fake. The
    tools probed are whatever configuration supplies, in order, so extending the
    list needs no change here. No judgement is applied: a missing tool is left as
    a plain fact for the M6 Flag layer to interpret.

    Args:
        machine: The seam every probe runs through.
        tools: The configured tools to probe, in board order.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The Section model: one tool fact per configured tool.
    """
    return SystemToolsSection(tools=[_probe_tool(machine, spec, timeout=timeout) for spec in tools])
