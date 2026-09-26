"""The toolchains Collector: the whole language story as facts.

Reports the Python and the Node/TypeScript toolchains side by side. Python: the
interpreters uv manages, each with the current release uv offers for it, and the
system ``python3``. Node/TypeScript: the global ``node``, ``npm``, and ``tsc``, the
alternative package managers only when present, and per repo the declared versus
installed TypeScript so drift is visible.

Everything reaches the host only through the ``Machine`` seam: version probes run
fixed argv lists, and the pins and manifests are read as files. The parsing
functions are pure so their edge cases pin directly against synthetic fixtures.
Facts only; anomaly judgement is the separate M6 Flag layer.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from wkx_ecosystem_localhost.collectors import loads_or_none
from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import (
    NodeToolchain,
    PythonToolchain,
    RepoTypeScript,
    Tool,
    ToolchainsSection,
    UvPython,
)
from wkx_ecosystem_localhost.redaction import relativise

logger = logging.getLogger(__name__)

# The exact, fixed argument lists each probe runs. Named constants so tests wire
# their fake against the same argv the Collector emits, never a guess at it.
UV_PYTHON_LIST_ARGV = ("uv", "python", "list")
PYTHON3_VERSION_ARGV = ("python3", "--version")
NODE_VERSION_ARGV = ("node", "--version")
NPM_VERSION_ARGV = ("npm", "--version")
TSC_VERSION_ARGV = ("tsc", "--version")
PNPM_VERSION_ARGV = ("pnpm", "--version")
BUN_VERSION_ARGV = ("bun", "--version")

# Per-probe wall-clock ceiling. Generous for a local version command, tight
# enough that a wedged tool degrades one row instead of hanging the board.
PROBE_TIMEOUT_S = 5.0

# Per-repo files read through the seam.
_PACKAGE_JSON = "package.json"
_INSTALLED_TS_REL = Path("node_modules") / "typescript" / "package.json"

# uv colours its output even when captured; strip the escape sequences so the
# parser sees clean text regardless of how uv decides to render.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# uv python list line: "<impl>-<version>-<platform...>  <path | <download available>>".
_DOWNLOAD_AVAILABLE = "<download available>"
# A key splits as <impl>-<version>-<platform-triple>; impl and version are the
# first two dash-separated parts (version may carry a "+freethreaded" suffix).
_UV_KEY_RE = re.compile(r"^(?P<impl>[a-z]+)-(?P<version>[^-\s]+)-")
# A stable release as uv lists it: major.minor.patch with an optional build
# variant such as "+freethreaded". A pre-release ("3.15.0a8", "3.15.0rc2") does
# not match, so it is never offered as an update.
_STABLE_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(\+[0-9a-z]+)?$")


@dataclass(frozen=True)
class UvPythonEntry:
    """One parsed line of ``uv python list``.

    ``installed`` is False for a line uv only offers to download. ``path`` is the
    raw (not yet relativised) path uv reports, or None for a download-available
    line; the Collector relativises it before it reaches a model.
    """

    implementation: str
    version: str
    installed: bool
    path: str | None


def strip_ansi(text: str) -> str:
    """Remove ANSI colour escape sequences from ``text``."""
    return _ANSI_RE.sub("", text)


def parse_uv_python_list(text: str) -> list[UvPythonEntry]:
    """Parse ``uv python list`` into one entry per line.

    Colour codes are stripped first. Each line is a key followed by either a path
    (the interpreter is installed) or ``<download available>`` (it is not). A
    line whose key does not parse as ``<impl>-<version>-<platform>`` is skipped
    rather than half-reported. When uv reports a symlink as ``A -> B``, the
    user-facing left side is kept as the path.

    Args:
        text: The stdout of ``uv python list``.

    Returns:
        One entry per recognised line, in listing order (uv sorts newest first).
    """
    entries: list[UvPythonEntry] = []
    for raw in strip_ansi(text).splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        key, _, rest = line.partition(" ")
        match = _UV_KEY_RE.match(key + "-")
        if match is None:
            continue
        rest = rest.strip()
        if not rest or rest == _DOWNLOAD_AVAILABLE:
            installed, path = False, None
        else:
            installed = True
            path = rest.split(" -> ", 1)[0].strip()
        entries.append(UvPythonEntry(match.group("impl"), match.group("version"), installed, path))
    return entries


def _stable_key(version: str) -> tuple[tuple[int, int, int], str] | None:
    """Split a stable uv version into its release tuple and variant, else None."""
    match = _STABLE_RE.match(version)
    if match is None:
        return None
    release = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return release, match.group(4) or ""


def newer_stable(entry: UvPythonEntry, entries: Sequence[UvPythonEntry]) -> str | None:
    """Return the newest stable release uv offers above ``entry``, or None.

    The candidates are every line of ``uv python list``, installed or not, of the
    same implementation and the same build variant: a free-threaded build is never
    the update for a default build. Any newer stable release counts, a new minor
    as well as a new patch. A pre-release is never a candidate, and an ``entry``
    that is itself a pre-release gets None.

    Args:
        entry: The installed interpreter to check.
        entries: Every parsed line of ``uv python list``.

    Returns:
        The newest stable version above ``entry`` as uv lists it, or None when
        ``entry`` is already the newest stable release on offer.
    """
    own = _stable_key(entry.version)
    if own is None:
        return None
    own_release, own_variant = own
    newest: tuple[tuple[int, int, int], str] | None = None
    for candidate in entries:
        if candidate.implementation != entry.implementation:
            continue
        key = _stable_key(candidate.version)
        if key is None or key[1] != own_variant or key[0] <= own_release:
            continue
        if newest is None or key[0] > newest[0]:
            newest = (key[0], candidate.version)
    return newest[1] if newest is not None else None


def parse_version(text: str) -> str | None:
    """Extract a version number from a tool's ``--version`` output.

    Handles the common shapes: a bare ``1.2.3``, a ``v1.2.3`` (node), and a
    labelled ``Python 3.14.5`` or ``Version 5.3.3`` (python3, tsc). The last
    whitespace-separated token is taken and any leading ``v`` stripped.

    Args:
        text: The tool's version output (stdout, or stderr as a fallback).

    Returns:
        The version string, or None when the output is empty.
    """
    tokens = text.split()
    if not tokens:
        return None
    return tokens[-1].removeprefix("v")


def parse_declared_typescript(package_json_text: str) -> str | None:
    """Read the declared TypeScript spec from a ``package.json``.

    Looks in ``devDependencies`` then ``dependencies`` for a ``typescript`` entry
    and returns its spec verbatim (for example ``^5.3.3``), so the declared range
    can be shown against the concrete installed version. Malformed JSON yields
    None rather than raising, so one bad manifest degrades a single row.

    Args:
        package_json_text: The contents of a repo's ``package.json``.

    Returns:
        The declared spec, or None when TypeScript is not declared or the JSON
        cannot be parsed.
    """
    data = loads_or_none(package_json_text)
    if not isinstance(data, dict):
        return None
    for group in ("devDependencies", "dependencies"):
        deps = data.get(group)
        if isinstance(deps, dict):
            spec = deps.get("typescript")
            if isinstance(spec, str):
                return spec
    return None


def parse_installed_typescript(package_json_text: str) -> str | None:
    """Read the concrete version from an installed ``node_modules/typescript``.

    Args:
        package_json_text: The contents of ``node_modules/typescript/package.json``.

    Returns:
        The installed ``version``, or None when it is absent or the JSON cannot
        be parsed.
    """
    data = loads_or_none(package_json_text)
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None


def _tool(machine: Machine, name: str, argv: Sequence[str], *, timeout: float) -> Tool:
    """Probe one tool's version through the seam and report it as a fact.

    A non-zero exit (including a missing program) or empty output is reported as
    absent, never raised: an absent toolchain is a fact to show, not an error.
    """
    result = machine.run(argv, timeout=timeout)
    if not result.ok:
        return Tool(name=name, version=None, present=False)
    version = parse_version(result.stdout or result.stderr)
    return Tool(name=name, version=version, present=version is not None)


def _collect_python(machine: Machine, *, home: Path, timeout: float) -> PythonToolchain:
    """Assemble the Python side: uv interpreters and the system python3."""
    list_result = machine.run(UV_PYTHON_LIST_ARGV, timeout=timeout)
    interpreters: list[UvPython] = []
    if list_result.ok:
        entries = parse_uv_python_list(list_result.stdout)
        seen: set[tuple[str, str]] = set()
        for entry in entries:
            if not entry.installed:
                continue
            key = (entry.implementation, entry.version)
            if key in seen:
                continue
            seen.add(key)
            interpreters.append(
                UvPython(
                    implementation=entry.implementation,
                    version=entry.version,
                    installed=True,
                    path=relativise(Path(entry.path), home) if entry.path else None,
                    current=newer_stable(entry, entries) or entry.version,
                )
            )

    system = _tool(machine, "python3", PYTHON3_VERSION_ARGV, timeout=timeout)
    return PythonToolchain(interpreters=interpreters, system=system)


def _collect_node(
    machine: Machine, repo_paths: Sequence[Path], *, home: Path, timeout: float
) -> NodeToolchain:
    """Assemble the Node/TypeScript side: globals, package managers, and per-repo TS."""
    node = _tool(machine, "node", NODE_VERSION_ARGV, timeout=timeout)
    npm = _tool(machine, "npm", NPM_VERSION_ARGV, timeout=timeout)
    tsc = _tool(machine, "tsc", TSC_VERSION_ARGV, timeout=timeout)

    # pnpm and bun are the alternatives: probed, but only shown when present.
    package_managers = [
        tool
        for tool in (
            _tool(machine, "pnpm", PNPM_VERSION_ARGV, timeout=timeout),
            _tool(machine, "bun", BUN_VERSION_ARGV, timeout=timeout),
        )
        if tool.present
    ]

    repos: list[RepoTypeScript] = []
    for repo_path in repo_paths:
        manifest = machine.read_file(repo_path / _PACKAGE_JSON)
        if not manifest:
            continue
        declared = parse_declared_typescript(manifest)
        installed_text = machine.read_file(repo_path / _INSTALLED_TS_REL)
        installed = parse_installed_typescript(installed_text) if installed_text else None
        # A repo with a manifest but no TypeScript, declared or installed, is not
        # part of the TypeScript story, so it is not shown.
        if declared is None and installed is None:
            continue
        repos.append(
            RepoTypeScript(
                repo=relativise(repo_path, home),
                declared=declared,
                installed=installed,
            )
        )

    return NodeToolchain(
        node=node,
        npm=npm,
        tsc=tsc,
        package_managers=package_managers,
        repos=repos,
    )


def collect_toolchains(
    machine: Machine,
    repo_paths: Sequence[Path],
    *,
    home: Path,
    timeout: float = PROBE_TIMEOUT_S,
) -> ToolchainsSection:
    """Collect the toolchains Section: the Python and Node/TypeScript facts.

    A pure Collector over the seam. Every version probe and every manifest read
    reaches the host only through ``machine``, so the whole Section is
    exercised in tests against a fake. No judgement is applied: drift is left
    plainly visible for the M6 Flag layer to interpret.

    Args:
        machine: The seam every probe and read runs through.
        repo_paths: The repos discovered for the workspace Section, reused here
            for per-repo TypeScript.
        home: Home directory, for relativising displayed paths.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The Section model: the Python toolchain and the Node/TypeScript toolchain.
    """
    return ToolchainsSection(
        python=_collect_python(machine, home=home, timeout=timeout),
        node=_collect_node(machine, repo_paths, home=home, timeout=timeout),
    )
