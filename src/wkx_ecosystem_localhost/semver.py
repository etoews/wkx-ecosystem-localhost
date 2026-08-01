"""Semantic-version parsing and precedence, for ranking submodule tags.

A submodule's drift is a question about versions: which remote tag is the latest
release, and how many releases the pinned commit sits behind it. That is a
semver question, so the parsing and ordering live here as pure functions with no
Machine or network involved, and their edge cases are pinned directly against
synthetic tag lists.

The rules follow the Semantic Versioning precedence spec: a leading ``v`` is
optional and ignored, build metadata (``+...``) never affects ordering, and a
pre-release version is lower than the same core release. Pre-release identifiers
are compared left to right, numeric ones below alphanumeric ones, and a longer
run of identifiers outranks a shorter prefix of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# major.minor.patch, an optional v/V prefix, an optional -pre-release, and
# optional +build metadata. Anything that does not match this shape is not a
# version tag we rank (a moving tag like "latest" or "stable" is simply ignored).
_SEMVER_RE = re.compile(
    r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)

# A git-describe suffix: "-<commits>-g<abbrev>" appended when the described
# commit is past the nearest tag. Stripped from a pinned describe so a submodule
# a few commits ahead of its tag still ranks against the tag it is based on.
_DESCRIBE_SUFFIX_RE = re.compile(r"-\d+-g[0-9A-Fa-f]+$")


@dataclass(frozen=True)
class SemVer:
    """One parsed semantic version, retaining the original tag for display.

    ``prerelease`` is the tuple of dot-separated identifiers after the ``-`` (an
    empty tuple for a stable release). ``original`` is the tag exactly as it was
    listed remotely, so the board can show ``v1.2.0`` or ``1.2.0`` as the project
    itself tags them, while ordering ignores the ``v``.
    """

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...]
    original: str

    @property
    def is_prerelease(self) -> bool:
        """True when this version carries a pre-release identifier."""
        return bool(self.prerelease)


def parse_semver(tag: str) -> SemVer | None:
    """Parse a tag into a ``SemVer``, or None when it is not a version.

    Args:
        tag: A tag name, with or without a leading ``v`` and with optional
            pre-release and build-metadata parts.

    Returns:
        The parsed version, or None for anything that is not ``major.minor.patch``
        shaped (a moving tag, a date, an empty string), so a non-version tag is
        dropped rather than mis-ranked.
    """
    match = _SEMVER_RE.match(tag.strip())
    if match is None:
        return None
    major, minor, patch, pre = match.groups()
    prerelease = tuple(pre.split(".")) if pre else ()
    return SemVer(int(major), int(minor), int(patch), prerelease, tag.strip())


def parse_pinned(describe: str) -> SemVer | None:
    """Parse a ``git describe`` string, tolerating its commit-offset suffix.

    ``git describe --tags`` prints the bare tag when a commit sits exactly on it
    (``1.0.0``) and appends ``-<n>-g<abbrev>`` when it is ``n`` commits past
    (``1.0.0-2-gabc1234``). The suffix is stripped so the pinned commit ranks
    against the release it is based on.

    Args:
        describe: The stdout of ``git describe --tags`` for the pinned commit.

    Returns:
        The parsed base version, or None when it is not version-shaped.
    """
    return parse_semver(_DESCRIBE_SUFFIX_RE.sub("", describe.strip()))


def _identifier_key(identifier: str) -> tuple[int, int, str]:
    """Order one pre-release identifier: numeric ones below alphanumeric ones."""
    if identifier.isdigit():
        return (0, int(identifier), "")
    return (1, 0, identifier)


def precedence_key(version: SemVer) -> tuple[Any, ...]:
    """Return a sort key giving semver precedence under normal tuple ordering.

    A stable release outranks any pre-release of the same core version, so the
    stable case carries a higher marker (1) and an empty identifier run; a
    pre-release carries marker 0 and its identifiers, so a longer run of equal
    prefixes outranks a shorter one exactly as the spec requires. The key is a
    heterogeneous tuple (cores, a marker, then identifier keys), so it is typed
    ``Any`` to stay orderable, the standard shape for a comparison sort key.
    """
    core = (version.major, version.minor, version.patch)
    if not version.prerelease:
        return (core, 1, ())
    return (core, 0, tuple(_identifier_key(i) for i in version.prerelease))


def select_latest(versions: list[SemVer]) -> SemVer | None:
    """Pick the highest release, excluding pre-releases unless none are stable.

    Args:
        versions: The parsed version tags, in any order.

    Returns:
        The highest stable version by precedence, or the highest pre-release when
        the project has only ever tagged pre-releases, or None for an empty list.
    """
    if not versions:
        return None
    stable = [v for v in versions if not v.is_prerelease]
    pool = stable if stable else versions
    return max(pool, key=precedence_key)


def count_behind(pinned: SemVer, versions: list[SemVer]) -> int:
    """Count how many releases sit strictly above the pinned version.

    Uses the same pool as ``select_latest`` (stable tags, or every tag when none
    are stable), so "N tags behind" counts releases of the same kind the latest
    is drawn from rather than every intermediate pre-release.

    Args:
        pinned: The version the submodule commit is pinned at.
        versions: The parsed remote version tags.

    Returns:
        The number of pool versions ranking strictly above ``pinned``.
    """
    stable = [v for v in versions if not v.is_prerelease]
    pool = stable if stable else versions
    pinned_key = precedence_key(pinned)
    return sum(1 for v in pool if precedence_key(v) > pinned_key)
