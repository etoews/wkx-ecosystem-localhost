"""The submodule-drift Collector: pin each submodule against its latest release.

Every submodule of every discovered repo is reported as three facts: the version
its parent pins it at, the highest stable release its remote lists, and how many
releases sit between the two. The pin is local and cheap (``git describe`` on the
already-checked-out commit), so it lands with the first page render. The remote
tag listing is a network call, so it rides the same bounded pool and SSE
machinery as the background fetch: each submodule's ``latest`` and ``behind``
fill in the moment its listing lands, and no submodule objects are ever fetched.

The parsing is pure: ``.gitmodules`` into specs, ``git ls-remote --tags`` into
tag names, and the semver ranking lives in its own module. Everything reaches the
host only through the ``Machine`` seam, so the whole Collector runs against a
fake in tests.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from wkx_ecosystem_localhost.github import (
    github_link,
    release_differs,
    release_tag_from_redirect,
    releases_latest_url,
)
from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import Submodule, SubmoduleEvent, SubmoduleSection
from wkx_ecosystem_localhost.redaction import relativise
from wkx_ecosystem_localhost.semver import (
    SemVer,
    count_behind,
    parse_pinned,
    parse_semver,
    select_latest,
)

logger = logging.getLogger(__name__)

# The submodule config file at a repo root. Read directly through the seam and
# parsed here, so no git command is needed to enumerate a repo's submodules.
GITMODULES = ".gitmodules"

# The pin is read from tags on the already-checked-out commit. No network, no
# object transfer: --tags lets a lightweight tag describe the commit too.
DESCRIBE_ARGV = ("git", "describe", "--tags")

# List the remote's tags without fetching any objects. The url is the only
# variable argument, appended by ``ls_remote_tags_argv``.
_LS_REMOTE_TAGS = ("git", "ls-remote", "--tags")

# The board's one outbound non-git HTTP call (ADR 0002): follow the public
# releases/latest redirect to read GitHub's blessed release token-free. The flags
# are fixed and read-only. ``-q`` ignores any ``~/.curlrc`` so no user config can
# inject a credential or a netrc; ``-s`` silences progress; ``-I -L`` follows the
# redirect with a HEAD; ``-o /dev/null`` drops the body; and ``-w`` prints only the
# final URL. The url is the only variable argument, appended by
# ``releases_latest_argv``. No token, no login, no authenticated API.
_CURL_RELEASE = ("curl", "-q", "-s", "-I", "-L", "-o", "/dev/null", "-w", "%{url_effective}")

# The pin is a fast local command; the remote listing and the release lookup are
# network calls, so they get more generous ceilings and still stay bounded so an
# unreachable remote degrades one row instead of hanging the stream.
DESCRIBE_TIMEOUT_S = 5.0
LS_REMOTE_TIMEOUT_S = 10.0
CURL_TIMEOUT_S = 8.0

_SUBMODULE_HEADER_RE = re.compile(r'^\[submodule "(?P<name>.+)"\]$')
_TAG_REF_PREFIX = "refs/tags/"
# ls-remote lists an annotated tag twice: the tag object and its peeled target
# (ref^{}). The peeled line is dropped so each tag is counted once.
_PEELED_SUFFIX = "^{}"


def ls_remote_tags_argv(url: str) -> tuple[str, ...]:
    """Build the fixed ``git ls-remote --tags <url>`` argv for a submodule url."""
    return (*_LS_REMOTE_TAGS, url)


def releases_latest_argv(release_url: str) -> tuple[str, ...]:
    """Build the fixed curl argv that prints the resolved ``releases/latest`` URL.

    ``release_url`` is the credential-free ``.../releases/latest`` URL from
    :func:`releases_latest_url`, so no secret can ride into the outbound request.
    """
    return (*_CURL_RELEASE, release_url)


@dataclass(frozen=True)
class SubmoduleSpec:
    """A submodule located in a parent repo, with its pin resolved locally.

    ``rel_path`` is the submodule's path relative to ``repo_path`` and ``url`` is
    the remote used for the tag listing (never displayed, so no redaction is owed
    here). ``pinned`` is the ``git describe`` result, or None when the commit is
    not on or after any tag.
    """

    repo_path: Path
    name: str
    rel_path: str
    url: str
    pinned: str | None

    @property
    def abs_path(self) -> Path:
        """The submodule's absolute path, for probing and for display."""
        return self.repo_path / self.rel_path


@dataclass(frozen=True)
class ProbeOutcome:
    """The parsed result of listing one submodule's remote tags.

    ``unknown`` is True when the remote could not be listed (unreachable or
    credential-gated). When the listing succeeds but carries no version tags, the
    outcome is known-good yet ``latest`` and ``behind`` are None.
    ``github_release`` is the release GitHub blesses as latest, surfaced only when
    it differs from ``latest``; it is None for a non-GitHub submodule, a failed or
    release-less lookup, or when it names the version already shown.
    """

    latest: str | None
    behind: int | None
    unknown: bool
    github_release: str | None = None


def parse_gitmodules(text: str) -> list[tuple[str, str, str]]:
    """Parse a ``.gitmodules`` file into ``(name, path, url)`` triples.

    Only submodules that declare both a ``path`` and a ``url`` are returned; a
    stanza missing either is skipped rather than half-reported. Keys are matched
    case-insensitively on their local part, as git config allows.

    Args:
        text: The contents of a repo's ``.gitmodules`` file.

    Returns:
        One triple per fully specified submodule, in file order.
    """
    stanzas: list[tuple[str, dict[str, str]]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        header = _SUBMODULE_HEADER_RE.match(line)
        if header is not None:
            current = {}
            stanzas.append((header.group("name"), current))
        elif current is not None and "=" in line:
            key, _, value = line.partition("=")
            current[key.strip().lower()] = value.strip()

    triples: list[tuple[str, str, str]] = []
    for name, kv in stanzas:
        path, url = kv.get("path"), kv.get("url")
        if path and url:
            triples.append((name, path, url))
    return triples


def parse_ls_remote_tags(text: str) -> list[str]:
    """Extract tag names from ``git ls-remote --tags`` output.

    Each line is ``<sha>\\t<ref>``; only ``refs/tags/`` refs are kept, the peeled
    ``^{}`` duplicate of an annotated tag is dropped, and order is preserved with
    duplicates removed.

    Args:
        text: The stdout of ``git ls-remote --tags <url>``.

    Returns:
        The distinct tag names, in listing order.
    """
    tags: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        _sha, tab, ref = line.partition("\t")
        if not tab or not ref.startswith(_TAG_REF_PREFIX):
            continue
        tag = ref[len(_TAG_REF_PREFIX) :]
        if tag.endswith(_PEELED_SUFFIX):
            tag = tag[: -len(_PEELED_SUFFIX)]
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def discover_submodules(
    machine: Machine, repo_paths: Sequence[Path], *, timeout: float = DESCRIBE_TIMEOUT_S
) -> list[SubmoduleSpec]:
    """Enumerate every submodule of every repo and resolve each pin locally.

    Reads each repo's ``.gitmodules`` through the seam and, for every submodule
    found, runs the local ``git describe`` to read the pinned version. No network
    call happens here, so the result is ready for the first page render.

    Args:
        machine: The seam used to read files and run the describe probe.
        repo_paths: The repos discovered for the workspace Section.
        timeout: Per-describe wall-clock ceiling in seconds.

    Returns:
        One spec per fully specified submodule, in repo-then-file order.
    """
    specs: list[SubmoduleSpec] = []
    for repo_path in repo_paths:
        text = machine.read_file(repo_path / GITMODULES)
        if not text:
            continue
        for name, rel_path, url in parse_gitmodules(text):
            abs_path = repo_path / rel_path
            result = machine.run(DESCRIBE_ARGV, cwd=abs_path, timeout=timeout)
            pinned = result.stdout.strip() if result.ok and result.stdout.strip() else None
            specs.append(SubmoduleSpec(repo_path, name, rel_path, url, pinned))
    return specs


def lookup_github_release(
    machine: Machine, spec: SubmoduleSpec, latest: SemVer | None, *, timeout: float = CURL_TIMEOUT_S
) -> str | None:
    """Read GitHub's blessed latest release for a submodule, or None when it agrees.

    For a GitHub submodule only, follows the public ``releases/latest`` redirect
    with the bounded, read-only, unauthenticated curl and parses the release tag
    from where it lands (ADR 0002). The tag is returned only when it differs from
    the tag-based ``latest`` already computed, so the board augments the row only
    when the two facts genuinely disagree. A non-GitHub submodule, a curl that
    exits non-zero (no network, a timeout, a rate limit), or a repo with no release
    all yield None, a silent fall back to the tag-based latest, never an error.

    Args:
        machine: The seam the curl runs through.
        spec: The submodule, carrying its remote url.
        latest: The highest semver tag from the listing, or None when there was
            none, used to decide whether the release differs.
        timeout: Per-lookup wall-clock ceiling in seconds.

    Returns:
        The blessed release tag when it differs from the tag-based latest, else
        None.
    """
    release_url = releases_latest_url(spec.url)
    if release_url is None:
        return None
    result = machine.run(releases_latest_argv(release_url), timeout=timeout)
    if not result.ok:
        logger.info("submodule release lookup could not complete for %s", spec.name)
        return None
    release = release_tag_from_redirect(result.stdout)
    latest_tag = latest.original if latest is not None else None
    return release if release_differs(release, latest_tag) else None


def probe_submodule(
    machine: Machine,
    spec: SubmoduleSpec,
    *,
    timeout: float = LS_REMOTE_TIMEOUT_S,
    curl_timeout: float = CURL_TIMEOUT_S,
) -> ProbeOutcome:
    """List one submodule's remote tags and rank them against its pin.

    Runs the non-interactive ``git ls-remote --tags`` through the seam, keeps only
    the version tags, and reports the highest stable release and how many releases
    the pin sits behind it. A listing that exits non-zero (credentials, no
    network, a timeout) yields an unknown outcome rather than raising, so one
    unreachable remote costs a single row, never the stream. For a GitHub
    submodule it also reads GitHub's blessed release over the same probe, surfacing
    it only when it differs from the tag-based latest; the tag-based ``latest`` and
    ``behind`` are computed exactly as before, untouched by the release lookup.

    Args:
        machine: The seam the listing and the release lookup run through.
        spec: The submodule, carrying its remote url and resolved pin.
        timeout: Per-listing wall-clock ceiling in seconds.
        curl_timeout: Per-release-lookup wall-clock ceiling in seconds.

    Returns:
        The submodule's latest release, tags-behind count, and any differing GitHub
        release, or an unknown outcome when the remote could not be listed.
    """
    result = machine.run(ls_remote_tags_argv(spec.url), timeout=timeout)
    if not result.ok:
        logger.info("submodule tag listing could not complete for %s", spec.name)
        return ProbeOutcome(latest=None, behind=None, unknown=True)

    versions = [v for v in (parse_semver(t) for t in parse_ls_remote_tags(result.stdout)) if v]
    latest = select_latest(versions)
    github_release = lookup_github_release(machine, spec, latest, timeout=curl_timeout)
    if latest is None:
        return ProbeOutcome(
            latest=None, behind=None, unknown=False, github_release=github_release
        )

    pinned = parse_pinned(spec.pinned) if spec.pinned else None
    behind = count_behind(pinned, versions) if pinned is not None else None
    return ProbeOutcome(
        latest=latest.original, behind=behind, unknown=False, github_release=github_release
    )


def collect_submodules(
    machine: Machine,
    repo_paths: Sequence[Path],
    *,
    home: Path,
    timeout: float = DESCRIBE_TIMEOUT_S,
) -> SubmoduleSection:
    """Collect the submodules Section: discover and pin, remote listing pending.

    The pure, local half of the Collector. Every submodule is reported with its
    pin resolved; ``latest`` and ``behind`` are left None because they are the one
    network truth, streamed over SSE so the page never blocks.

    Args:
        machine: The seam.
        repo_paths: The repos discovered for the workspace Section.
        home: Home directory, for relativising displayed paths.
        timeout: Per-describe wall-clock ceiling in seconds.

    Returns:
        The Section model: one entry per submodule, home-relative, with latest and
        behind pending until the SSE probe lands.
    """
    specs = discover_submodules(machine, repo_paths, timeout=timeout)
    submodules = [
        Submodule(
            name=spec.name,
            repo=relativise(spec.repo_path, home),
            path=relativise(spec.abs_path, home),
            pinned=spec.pinned,
            github=github_link(spec.url),
        )
        for spec in specs
    ]
    return SubmoduleSection(submodules=submodules)


def stream_submodule_probes(
    machine: Machine,
    repo_paths: Sequence[Path],
    *,
    home: Path,
    max_workers: int,
    describe_timeout: float = DESCRIBE_TIMEOUT_S,
    ls_remote_timeout: float = LS_REMOTE_TIMEOUT_S,
    curl_timeout: float = CURL_TIMEOUT_S,
) -> Iterator[SubmoduleEvent]:
    """List every submodule's remote tags on a bounded pool, streaming each result.

    Discovery and the local pins run first, then the remote listings run
    concurrently on at most ``max_workers`` threads with results yielded in
    completion order, so a fast remote's numbers reach the board while a slow one
    is still in flight. Each event is keyed by the submodule's home-relative path,
    matching the Section so the board fills the right row.

    Args:
        machine: The seam every read and listing runs through.
        repo_paths: The repos discovered for the workspace Section.
        home: Home directory, for relativising each submodule's path.
        max_workers: Ceiling on concurrent tag listings.
        describe_timeout: Per-describe wall-clock ceiling in seconds.
        ls_remote_timeout: Per-listing wall-clock ceiling in seconds.
        curl_timeout: Per-release-lookup wall-clock ceiling in seconds.

    Yields:
        One ``SubmoduleEvent`` per submodule, in the order the listings complete.
    """
    specs = discover_submodules(machine, repo_paths, timeout=describe_timeout)
    if not specs:
        return
    workers = max(1, min(max_workers, len(specs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                probe_submodule,
                machine,
                spec,
                timeout=ls_remote_timeout,
                curl_timeout=curl_timeout,
            ): spec
            for spec in specs
        }
        for future in as_completed(futures):
            spec = futures[future]
            outcome = future.result()
            yield SubmoduleEvent(
                submodule=relativise(spec.abs_path, home),
                latest=outcome.latest,
                behind=outcome.behind,
                unknown=outcome.unknown,
                github_release=outcome.github_release,
            )
