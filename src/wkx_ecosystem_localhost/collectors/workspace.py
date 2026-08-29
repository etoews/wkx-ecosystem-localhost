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
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from wkx_ecosystem_localhost.cache import TtlCache
from wkx_ecosystem_localhost.github import github_link
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
_ORIGIN_URL_KEY = "remote.origin.url"

_HEAD_PREFIX = "# branch.head "
_OID_PREFIX = "# branch.oid "
_UPSTREAM_PREFIX = "# branch.upstream "
_DETACHED = "(detached)"
_SHORT_SHA_LEN = 7


def _is_excluded(display_path: str, excludes: Sequence[str]) -> bool:
    """Whether the ``~``-relative display path full-matches any Exclude glob.

    Matching is on the same ``~``-relative string the board shows, parsed as a pure
    POSIX path so ``**`` spans any depth and a leading ``~/`` in a pattern matches
    the ``~`` the displayed path already starts with. An empty ``excludes`` matches
    nothing.

    Args:
        display_path: The directory's ``~``-relative path, as the board displays it.
        excludes: The configured Exclude globs.

    Returns:
        True when any glob full-matches the display path.
    """
    candidate = PurePosixPath(display_path)
    return any(candidate.full_match(pattern) for pattern in excludes)


def discover_repos(
    machine: Machine,
    roots: Sequence[Path],
    *,
    home: Path,
    max_depth: int,
    excludes: Sequence[str] = (),
) -> list[Path]:
    """Find every git repo under ``roots``.

    Walks each root, stopping the moment a directory contains a ``.git`` entry:
    a repo is one unit, so its interior (and any vendored or submodule repos
    within) is not descended into. Hidden directories and dependency directories
    (``node_modules``, virtualenvs) are pruned, and ``max_depth`` caps the descent
    so a pathological tree cannot run the scan away.

    An Exclude glob prunes a directory too: any visited directory whose
    ``~``-relative path full-matches a glob in ``excludes`` is neither reported nor
    descended into, so an excluded subtree is absent from the board and raises no
    Flags. This is on top of the built-in prunes, which always apply.

    Args:
        machine: The seam used to list directories.
        roots: Directories to scan. Missing ones contribute nothing.
        home: Home directory, to render each directory's ``~``-relative path for
            Exclude matching (the same form the board displays).
        max_depth: The deepest directory level below a root that is descended
            into (a root is depth 0).
        excludes: Exclude globs, matched with ``PurePath.full_match`` against each
            directory's ``~``-relative path. Empty by default (nothing excluded).

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
            if _is_excluded(relativise(path, home), excludes):
                continue

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
class _DiscoveryKey:
    """The discovery inputs a cached walk is valid for.

    A cached result is served only when these match the current request, so a
    configuration change (different roots, depth, or Excludes) is a miss rather
    than a stale hit. The machine and home are not keyed: they are bound to one
    app instance, which builds a fresh cache, so they cannot change under a hit.
    """

    roots: tuple[Path, ...]
    max_depth: int
    excludes: tuple[str, ...]


class DiscoveryCache:
    """Shares one board load's repo discovery across every route and the Flag layer.

    A board load asks several routes (workspace, submodules, toolchains,
    footprint) and the Flag layer for the repos under the scan roots. Each would
    otherwise re-run ``discover_repos``, walking every tree again and re-matching
    the per-directory Exclude globs. This wraps that walk in a ``TtlCache`` the
    way the footprint Section is wrapped: the first caller of a board load pays
    for the walk and the rest of the TTL window is served from memory.

    The single cached slot holds the walk together with the ``_DiscoveryKey`` it
    was run for, so a request whose inputs differ re-walks instead of taking a
    stale result. One instance is built per ``create_app`` and bound to
    ``app.state``, so a fresh app starts cold and a reload that rebuilds the app
    (picking up a configuration change) starts cold too.
    """

    def __init__(self, ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        """Build an empty discovery cache.

        Args:
            ttl: How long, in seconds, a discovery walk stays fresh.
            clock: The time source passed through to the underlying ``TtlCache``,
                monotonic by default; tests inject a fake to drive expiry.
        """
        self._cache: TtlCache[tuple[_DiscoveryKey, list[Path]]] = TtlCache(ttl, clock)
        # Serialises the cold-cache walk: the sync routes run in Starlette's
        # threadpool, so several can hit an empty cache at once on the first board
        # load; the lock makes them share one walk instead of each walking.
        self._lock = threading.Lock()

    def discover(
        self,
        machine: Machine,
        roots: Sequence[Path],
        *,
        home: Path,
        max_depth: int,
        excludes: Sequence[str] = (),
    ) -> list[Path]:
        """Return the repos under ``roots``, walking once per fresh input set.

        A fresh value for the same inputs (roots, depth, Excludes) is returned
        without re-walking; an empty or expired cache, or a change to any of those
        inputs, re-walks with ``discover_repos`` and stores the result. The
        argument list matches ``discover_repos`` so a caller swaps one for the
        other by threading this cache through.

        Args:
            machine: The seam used to list directories.
            roots: Directories to scan. Part of the cache key.
            home: Home directory, for rendering each directory's ``~``-relative
                path for Exclude matching. Not keyed (bound to the app instance).
            max_depth: Discovery depth cap. Part of the cache key.
            excludes: Exclude globs pruning the walk. Part of the cache key.

        Returns:
            Repo root paths, de-duplicated and sorted; a fresh list each call,
            backed by a single walk per fresh input set within the TTL window.
        """
        key = _DiscoveryKey(roots=tuple(roots), max_depth=max_depth, excludes=tuple(excludes))
        cached = self._cache.get()
        if cached is not None and cached[0] == key:
            return list(cached[1])
        with self._lock:
            # Re-check inside the lock: a concurrent caller may have finished the
            # walk while we waited, so the roots are walked once, not once per
            # caller. A copy is returned so a consumer never mutates the shared slot.
            cached = self._cache.get()
            if cached is not None and cached[0] == key:
                return list(cached[1])
            repos = discover_repos(
                machine, roots, home=home, max_depth=max_depth, excludes=excludes
            )
            self._cache.set((key, repos))
            return list(repos)


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


def primary_remote_url(config: list[ConfigEntry]) -> str | None:
    """Pick the repo's primary remote URL from its whitelisted config entries.

    ``remote.origin.url`` is the primary remote when present; otherwise the first
    ``remote.*.url`` in config order stands in, so a repo whose sole remote is not
    named ``origin`` still resolves. The value returned is already
    credential-stripped, since that is how a remote URL reaches a ``ConfigEntry``.

    Args:
        config: The whitelisted, redacted config entries from ``parse_config``.

    Returns:
        The primary remote URL, or None when the repo declares no remote.
    """
    first: str | None = None
    for entry in config:
        if _REMOTE_URL_KEY.match(entry.key):
            if entry.key == _ORIGIN_URL_KEY:
                return entry.value
            if first is None:
                first = entry.value
    return first


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

    primary_remote = primary_remote_url(config)
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
        github=github_link(primary_remote) if primary_remote else None,
        config=config,
    )


def collect_workspace(
    machine: Machine,
    roots: Sequence[Path],
    *,
    home: Path,
    max_depth: int,
    excludes: Sequence[str] = (),
    timeout: float = PROBE_TIMEOUT_S,
    discovery: DiscoveryCache | None = None,
) -> WorkspaceSection:
    """Collect the workspace Section: discover repos, then probe each one.

    The pure end-to-end Collector. Discovery and every probe reach the host only
    through ``machine``, so the whole Section is exercised in tests against a fake.

    Args:
        machine: The seam.
        roots: Directories to scan for repos.
        home: Home directory, for relativising displayed paths.
        max_depth: Discovery depth cap.
        excludes: Exclude globs pruning matching directories from discovery, so an
            excluded repo is absent from the Section. Empty by default.
        timeout: Per-probe wall-clock ceiling in seconds.
        discovery: Shared discovery cache. When given, the repo walk is taken from
            it so one board load walks the roots once across every route and the
            Flag layer; when None (the default) the walk runs directly, so a unit
            test drives the Collector without a cache.

    Returns:
        The Section model: the scanned roots and one entry per discovered repo,
        both rendered home-relative.
    """
    repo_paths = (
        discovery.discover(machine, roots, home=home, max_depth=max_depth, excludes=excludes)
        if discovery is not None
        else discover_repos(machine, roots, home=home, max_depth=max_depth, excludes=excludes)
    )
    repos = [collect_repo(machine, path, home=home, timeout=timeout) for path in repo_paths]
    return WorkspaceSection(roots=[relativise(root, home) for root in roots], repos=repos)
