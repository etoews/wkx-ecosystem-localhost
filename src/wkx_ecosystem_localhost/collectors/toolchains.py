"""The toolchains Collector: the whole language story as facts.

Reports the Python and the Node/TypeScript toolchains side by side. Python: the
interpreters uv finds, uv-managed or not, and each repo's ``.venv`` interpreter,
each with the current release uv offers for it, and the system ``python3``.
Node/TypeScript: the global ``node``, ``npm``, and ``tsc``, the alternative
package managers only when present, and per repo the declared versus installed
TypeScript so drift is visible.

Everything reaches the host only through the ``Machine`` seam: version probes run
fixed argv lists, and the venv configs and manifests are read as files. The parsing
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
    PythonInterpreter,
    PythonToolchain,
    RepoPython,
    RepoTypeScript,
    Tool,
    ToolchainsSection,
)
from wkx_ecosystem_localhost.redaction import relativise

logger = logging.getLogger(__name__)

# The exact, fixed argument lists each probe runs. Named constants so tests wire
# their fake against the same argv the Collector emits, never a guess at it.
# --python-preference managed lists every interpreter uv can find, uv-managed or
# not, overriding an operator's uv.toml that sets only-managed (which would hide
# Homebrew's and the OS's interpreters from the board).
UV_PYTHON_LIST_ARGV = ("uv", "python", "list", "--python-preference", "managed")
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
_PYVENV_CFG_REL = Path(".venv") / "pyvenv.cfg"
_VENV_PYTHON_REL = Path(".venv") / "bin" / "python"

# What installed an interpreter, read off its path (or its symlink target).
SOURCE_UV = "uv"
SOURCE_HOMEBREW = "homebrew"
SOURCE_MACOS = "macos"
SOURCE_OTHER = "other"
_UV_PYTHON_DIR = "/uv/python/"
_HOMEBREW_MARKERS = ("/opt/homebrew/", "/Cellar/", "Cellar/")
_MACOS_PREFIXES = ("/usr/bin/", "/System/", "/Library/Developer/", "/Applications/Xcode")
# The release at the head of a pyvenv.cfg version: uv writes version_info = 3.14.4,
# virtualenv 3.12.1.final.0, and the stdlib venv version = 3.12.1.
_VENV_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")

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
    line; the Collector relativises it before it reaches a model. ``target`` is the
    right side when uv reports a symlink as ``A -> B``, else None.
    """

    implementation: str
    version: str
    installed: bool
    path: str | None
    target: str | None = None


def strip_ansi(text: str) -> str:
    """Remove ANSI colour escape sequences from ``text``."""
    return _ANSI_RE.sub("", text)


def parse_uv_python_list(text: str) -> list[UvPythonEntry]:
    """Parse ``uv python list`` into one entry per line.

    Colour codes are stripped first. Each line is a key followed by either a path
    (the interpreter is installed) or ``<download available>`` (it is not). A
    line whose key does not parse as ``<impl>-<version>-<platform>`` is skipped
    rather than half-reported. When uv reports a symlink as ``A -> B``, the
    user-facing left side is kept as the path and the right side as the target.

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
        target: str | None = None
        if not rest or rest == _DOWNLOAD_AVAILABLE:
            installed, path = False, None
        else:
            installed = True
            path, arrow, right = rest.partition(" -> ")
            path = path.strip()
            target = right.strip() if arrow else None
        entries.append(
            UvPythonEntry(match.group("impl"), match.group("version"), installed, path, target)
        )
    return entries


def interpreter_source(path: str, target: str | None = None) -> str:
    """Say what installed an interpreter, from its raw path and symlink target.

    uv's own interpreters live under a ``uv/python`` directory (a ``~/.local/bin``
    shim links into it); Homebrew's live under ``/opt/homebrew`` or link into a
    ``Cellar``; the OS and its developer tools ship theirs under ``/usr/bin``,
    ``/System``, ``/Library/Developer``, or Xcode. Anything else is ``other``.
    """
    places = (path, target or "")
    if any(_UV_PYTHON_DIR in place for place in places):
        return SOURCE_UV
    if any(marker in place for place in places for marker in _HOMEBREW_MARKERS):
        return SOURCE_HOMEBREW
    if path.startswith(_MACOS_PREFIXES):
        return SOURCE_MACOS
    return SOURCE_OTHER


def parse_pyvenv_cfg(text: str) -> tuple[str, str, str] | None:
    """Read a venv's ``pyvenv.cfg`` into its implementation, version, and home.

    ``version_info`` (uv, virtualenv) is preferred over ``version`` (the stdlib
    venv), and trimmed to its release (``3.12.1.final.0`` reads as ``3.12.1``).
    ``implementation`` defaults to ``cpython`` when the file does not name one.

    Returns:
        ``(implementation, version, home)`` lower-casing the implementation, or
        None when the file names no parseable version.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip().lower()] = value.strip()
    raw = values.get("version_info") or values.get("version") or ""
    match = _VENV_VERSION_RE.match(raw)
    if match is None:
        return None
    implementation = values.get("implementation", "cpython").lower()
    return implementation, match.group(0), values.get("home", "")


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


def _collect_python(
    machine: Machine, repo_paths: Sequence[Path], *, home: Path, timeout: float
) -> PythonToolchain:
    """Assemble the Python side: every interpreter, each repo's venv, and python3."""
    list_result = machine.run(UV_PYTHON_LIST_ARGV, timeout=timeout)
    entries = parse_uv_python_list(list_result.stdout) if list_result.ok else []
    interpreters: list[PythonInterpreter] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        if not entry.installed or entry.path is None:
            continue
        source = interpreter_source(entry.path, entry.target)
        # uv lists an interpreter once per link to it (a bin shim and its target,
        # Homebrew's python3 and python3.14); one row per interpreter is enough.
        key = (entry.implementation, entry.version, source)
        if key in seen:
            continue
        seen.add(key)
        interpreters.append(
            PythonInterpreter(
                implementation=entry.implementation,
                version=entry.version,
                source=source,
                path=relativise(Path(entry.path), home),
                current=newer_stable(entry, entries) or entry.version,
            )
        )

    repos: list[RepoPython] = []
    for repo_path in repo_paths:
        cfg = machine.read_file(repo_path / _PYVENV_CFG_REL)
        parsed = parse_pyvenv_cfg(cfg) if cfg else None
        if parsed is None:
            continue
        implementation, version, venv_home = parsed
        venv = UvPythonEntry(implementation, version, True, None)
        repos.append(
            RepoPython(
                repo=relativise(repo_path, home),
                version=version,
                source=interpreter_source(venv_home.rstrip("/") + "/"),
                path=relativise(repo_path / _VENV_PYTHON_REL, home),
                current=newer_stable(venv, entries) or version,
            )
        )

    system = _tool(machine, "python3", PYTHON3_VERSION_ARGV, timeout=timeout)
    return PythonToolchain(interpreters=interpreters, repos=repos, system=system)


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
            for each repo's ``.venv`` interpreter and per-repo TypeScript.
        home: Home directory, for relativising displayed paths.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The Section model: the Python toolchain and the Node/TypeScript toolchain.
    """
    return ToolchainsSection(
        python=_collect_python(machine, repo_paths, home=home, timeout=timeout),
        node=_collect_node(machine, repo_paths, home=home, timeout=timeout),
    )
