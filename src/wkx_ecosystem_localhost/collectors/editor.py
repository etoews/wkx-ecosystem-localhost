"""The editor Collector: VS Code's presence, version, and installed extensions.

Two read-only probes through the ``Machine`` seam: ``code --version`` for the CLI
version and ``code --list-extensions --show-versions`` for the installed
extensions. A ``code`` CLI that cannot be run (absent, or not on the path) is a
fact, never an error: the Section reports ``installed=False`` and the board renders
it plainly. The version reader and the extension splitter are pure, so their edge
cases pin directly against synthetic fixtures. Facts only; anomaly judgement is
the separate M6 Flag layer.
"""

from __future__ import annotations

import logging

from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import EditorExtension, EditorSection

logger = logging.getLogger(__name__)

# The two probes this Collector runs. ``--version`` prints a three-line banner
# (version, commit hash, arch); ``--list-extensions --show-versions`` prints one
# ``publisher.name@version`` per line.
CODE_VERSION_ARGV = ("code", "--version")
CODE_EXTENSIONS_ARGV = ("code", "--list-extensions", "--show-versions")

# Per-probe wall-clock ceiling. Generous for a local CLI query, tight enough that
# a wedged ``code`` degrades this one Section rather than hanging the board.
PROBE_TIMEOUT_S = 5.0


def parse_code_version(stdout: str) -> str | None:
    """Read the version from a ``code --version`` banner.

    The banner is three lines (version, commit hash, arch); only the first
    non-empty line, stripped, is the version. Output with no non-empty line yields
    None, so an empty or unreadable probe degrades a single fact rather than
    raising.

    Args:
        stdout: The stdout of ``code --version``.

    Returns:
        The version string, or None when no non-empty line is present.
    """
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def parse_extensions(stdout: str) -> list[EditorExtension]:
    """Parse ``code --list-extensions --show-versions`` into installed extensions.

    Each non-empty line is one ``publisher.name@version`` entry, split on the last
    ``@`` so an id that itself contains an ``@`` stays whole; a line with no ``@``
    yields an id with a None version. Listing order is preserved and blank lines
    are skipped, so an unexpected gap degrades nothing.

    Args:
        stdout: The stdout of ``code --list-extensions --show-versions``.

    Returns:
        The installed extensions, in the order they were listed.
    """
    extensions: list[EditorExtension] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "@" in stripped:
            ext_id, version = stripped.rsplit("@", 1)
            extensions.append(EditorExtension(id=ext_id, version=version))
        else:
            extensions.append(EditorExtension(id=stripped, version=None))
    return extensions


def collect_editor(machine: Machine, *, timeout: float = PROBE_TIMEOUT_S) -> EditorSection:
    """Collect the editor Section: VS Code's presence, version, and extensions.

    A pure Collector over the seam. Both probes reach the host only through
    ``machine``, so the whole Section is exercised in tests against a fake. A
    non-zero ``code --version`` (the CLI absent, or not on the path) reports
    ``installed=False`` with no version and no extensions: an absent editor is a
    fact to show, not an error. When the version probe succeeds but the extensions
    probe cannot be read, the Section is installed with an empty extension list. No
    judgement is applied; the state is left plain for the M6 Flag layer.

    Args:
        machine: The seam both probes run through.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The Section model: installed with version and extensions, or absent.
    """
    version_result = machine.run(CODE_VERSION_ARGV, timeout=timeout)
    if not version_result.ok:
        return EditorSection(installed=False)
    version = parse_code_version(version_result.stdout)
    extensions_result = machine.run(CODE_EXTENSIONS_ARGV, timeout=timeout)
    extensions = parse_extensions(extensions_result.stdout) if extensions_result.ok else []
    return EditorSection(installed=True, version=version, extensions=extensions)
