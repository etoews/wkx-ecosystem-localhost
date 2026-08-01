"""The workspace Collector: discover repos and report their state.

The tracer bullet Collector wired end to end. It discovers every git repo under
the configured roots, reads each one's working-tree state and a whitelisted,
redacted slice of its git config, and returns a typed model. Every read goes
through the ``Machine`` seam; the parsing functions below are pure so their edge
cases can be pinned directly against synthetic fixtures.

ahead/behind is deliberately left as None here: it needs a background fetch and
is streamed over SSE in M2. Until then the board renders it as "pending".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import ConfigEntry, Repo, WorkspaceSection
from wkx_ecosystem_localhost.redaction import (
    mask_email,
    relativise,
    relativise_text,
    strip_credentials,
)

# The exact, fixed argument lists each probe runs. Named constants so tests wire
# their fake against the same argv the Collector emits, never a guess at it.
STATUS_ARGV = ("git", "status", "--porcelain=v2", "--branch")
STASH_ARGV = ("git", "stash", "list")
CONFIG_ARGV = ("git", "config", "--list", "--show-scope")

# Per-probe wall-clock ceiling. Generous for a local git command, tight enough
# that a wedged repo degrades one row instead of hanging the board.
PROBE_TIMEOUT_S = 5.0

# Directory names pruned during discovery. Anything starting with "." is pruned
# too (covering .venv, .tox, and the like), so only the non-hidden noise needs
# naming here.
_SKIP_DIR_NAMES = frozenset({"node_modules", "venv"})

_GIT_MARKER = ".git"

# git config keys safe to display verbatim. Whitelist, not blacklist: a key not
# named here never reaches the board, so signing keys and anything else
# sensitive are dropped by default rather than by remembering to exclude them.
# user.email (masked) and remote.*.url (credential-stripped) are handled
# specially below and so are intentionally absent from this set.
_SAFE_CONFIG_KEYS = frozenset(
    {
        "user.name",
        "init.defaultbranch",
        "core.editor",
        "core.autocrlf",
        "core.ignorecase",
        "pull.rebase",
        "pull.ff",
        "push.default",
        "push.autosetupremote",
        "fetch.prune",
        "rebase.autostash",
        "commit.gpgsign",
        "tag.gpgsign",
    }
)

_REMOTE_URL_KEY = re.compile(r"^remote\..+\.url$")

_HEAD_PREFIX = "# branch.head "
_OID_PREFIX = "# branch.oid "
_UPSTREAM_PREFIX = "# branch.upstream "
_DETACHED = "(detached)"
_SHORT_SHA_LEN = 7


def discover_repos(machine: Machine, roots: Sequence[Path], *, max_depth: int) -> list[Path]:
    """Find every git repo under ``roots``.

    Walks each root, stopping the moment a directory contains a ``.git`` entry:
    a repo is one unit, so its interior (and any vendored or submodule repos
    within) is not descended into. Hidden directories and dependency directories
    (``node_modules``, virtualenvs) are pruned, and ``max_depth`` caps the descent
    so a pathological tree cannot run the scan away.

    Args:
        machine: The seam used to list directories.
        roots: Directories to scan. Missing ones contribute nothing.
        max_depth: The deepest directory level below a root that is descended
            into (a root is depth 0).

    Returns:
        Repo root paths, de-duplicated and sorted for a stable board order.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            path, depth = stack.pop()
            if path in seen:
                continue
            seen.add(path)

            entries = machine.list_dir(path)
            if any(entry.name == _GIT_MARKER for entry in entries):
                found.append(path)
                continue
            if depth >= max_depth:
                continue
            for entry in entries:
                if not entry.is_dir:
                    continue
                if entry.name.startswith(".") or entry.name in _SKIP_DIR_NAMES:
                    continue
                stack.append((path / entry.name, depth + 1))
    return sorted(found)


@dataclass(frozen=True)
class RepoStatus:
    """The parsed result of ``git status --porcelain=v2 --branch``.

    ``branch`` and ``detached_sha`` are mutually exclusive. Counts follow the
    porcelain ``<XY>`` field: an entry is staged when its index status is not
    ``.`` and unstaged when its worktree status is not ``.``. Unmerged entries
    are counted on their own so a conflict is not double-counted as both.
    """

    branch: str | None
    detached_sha: str | None
    upstream: str | None
    staged: int
    unstaged: int
    untracked: int
    unmerged: int


def parse_status(text: str) -> RepoStatus:
    """Parse porcelain v2 branch output into a ``RepoStatus``.

    Args:
        text: The stdout of ``git status --porcelain=v2 --branch``.

    Returns:
        The branch or detached short SHA, the upstream if any, and staged,
        unstaged, untracked, and unmerged counts. The ``# branch.ab`` header is
        ignored on purpose: ahead/behind is an M2 concern.
    """
    branch: str | None = None
    upstream: str | None = None
    oid: str | None = None
    detached = False
    staged = unstaged = untracked = unmerged = 0

    for line in text.splitlines():
        if line.startswith(_OID_PREFIX):
            oid = line[len(_OID_PREFIX) :]
        elif line.startswith(_HEAD_PREFIX):
            head = line[len(_HEAD_PREFIX) :]
            if head == _DETACHED:
                detached = True
            else:
                branch = head
        elif line.startswith(_UPSTREAM_PREFIX):
            upstream = line[len(_UPSTREAM_PREFIX) :]
        elif line.startswith(("1 ", "2 ")):
            index_status, worktree_status = line.split(maxsplit=2)[1]
            if index_status != ".":
                staged += 1
            if worktree_status != ".":
                unstaged += 1
        elif line.startswith("u "):
            unmerged += 1
        elif line.startswith("? "):
            untracked += 1

    detached_sha = oid[:_SHORT_SHA_LEN] if detached and oid else None
    return RepoStatus(branch, detached_sha, upstream, staged, unstaged, untracked, unmerged)


def parse_stash(text: str) -> int:
    """Count stash entries in the output of ``git stash list``."""
    return sum(1 for line in text.splitlines() if line.strip())


def parse_config(text: str) -> list[ConfigEntry]:
    """Parse ``git config --list --show-scope`` into whitelisted, redacted entries.

    Each input line is ``<scope>\\t<key>=<value>``. Only whitelisted keys survive.
    ``user.email`` is masked, keeping the raw value for on-demand reveal; a remote
    URL is credential-stripped and carries no raw value; everything else is
    dropped so nothing sensitive can slip through.

    Args:
        text: The stdout of ``git config --list --show-scope``.

    Returns:
        Display-ready entries in input order, preserving scope labels and any
        per-scope duplicates (for example a global and a local ``user.email``).
    """
    entries: list[ConfigEntry] = []
    for line in text.splitlines():
        scope, tab, rest = line.partition("\t")
        if not tab:
            continue
        key, sep, value = rest.partition("=")
        if not sep:
            continue
        if key == "user.email":
            entries.append(ConfigEntry(key=key, value=mask_email(value), scope=scope, raw=value))
        elif _REMOTE_URL_KEY.match(key):
            entries.append(ConfigEntry(key=key, value=strip_credentials(value), scope=scope))
        elif key in _SAFE_CONFIG_KEYS:
            entries.append(ConfigEntry(key=key, value=value, scope=scope))
    return entries


def _redact_config_paths(entries: list[ConfigEntry], home: Path) -> list[ConfigEntry]:
    """Rewrite any home path embedded in a whitelisted config value to ``~``.

    A whitelisted key can still carry an absolute home path in its value (an
    editor path, a hooks path), which would leak the username that path
    relativisation exists to hide. The displayed value is scrubbed; ``raw`` (the
    reveal-on-demand email) is left intact and never contains a home path.
    """
    return [
        entry.model_copy(update={"value": relativise_text(entry.value, home)}) for entry in entries
    ]


def collect_repo(
    machine: Machine, repo_path: Path, *, home: Path, timeout: float = PROBE_TIMEOUT_S
) -> Repo:
    """Probe one repo and assemble its display-ready model.

    Runs the three fixed git probes through the seam, parses their output, and
    redacts as it goes: the path is home-relative, the config is whitelisted with
    the email masked and remotes credential-stripped. A probe that exits non-zero
    is treated as "unknown" for that facet rather than failing the repo, so one
    wedged command degrades a single row.

    Args:
        machine: The seam every probe runs through.
        repo_path: The repo's root directory.
        home: Home directory, for relativising the displayed path.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The repo's model, with ahead/behind left as None (pending until M2).
    """
    status_result = machine.run(STATUS_ARGV, cwd=repo_path, timeout=timeout)
    status = (
        parse_status(status_result.stdout)
        if status_result.ok
        else RepoStatus(
            branch=None,
            detached_sha=None,
            upstream=None,
            staged=0,
            unstaged=0,
            untracked=0,
            unmerged=0,
        )
    )

    stash_result = machine.run(STASH_ARGV, cwd=repo_path, timeout=timeout)
    stashes = parse_stash(stash_result.stdout) if stash_result.ok else 0

    config_result = machine.run(CONFIG_ARGV, cwd=repo_path, timeout=timeout)
    config = (
        _redact_config_paths(parse_config(config_result.stdout), home) if config_result.ok else []
    )

    dirty = bool(status.staged or status.unstaged or status.untracked or status.unmerged)
    return Repo(
        name=repo_path.name,
        path=relativise(repo_path, home),
        branch=status.branch,
        detached_sha=status.detached_sha,
        upstream=status.upstream,
        staged=status.staged,
        unstaged=status.unstaged,
        untracked=status.untracked,
        unmerged=status.unmerged,
        stashes=stashes,
        dirty=dirty,
        ahead=None,
        behind=None,
        config=config,
    )


def collect_workspace(
    machine: Machine,
    roots: Sequence[Path],
    *,
    home: Path,
    max_depth: int,
    timeout: float = PROBE_TIMEOUT_S,
) -> WorkspaceSection:
    """Collect the workspace Section: discover repos, then probe each one.

    The pure end-to-end Collector. Discovery and every probe reach the host only
    through ``machine``, so the whole Section is exercised in tests against a fake.

    Args:
        machine: The seam.
        roots: Directories to scan for repos.
        home: Home directory, for relativising displayed paths.
        max_depth: Discovery depth cap.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The Section model: the scanned roots and one entry per discovered repo,
        both rendered home-relative.
    """
    repo_paths = discover_repos(machine, roots, max_depth=max_depth)
    repos = [collect_repo(machine, path, home=home, timeout=timeout) for path in repo_paths]
    return WorkspaceSection(roots=[relativise(root, home) for root in roots], repos=repos)
