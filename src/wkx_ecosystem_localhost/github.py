"""Derive a repository's GitHub link from its remote URL, purely and with no I/O.

A GitHub remote comes in two shapes: the https form
(``https://github.com/owner/repo`` with an optional ``.git`` and/or trailing
slash) and the scp-style form (``git@github.com:owner/repo``). Both name the same
``owner`` and ``repo``; a non-GitHub remote names neither. The link is
reconstructed from just those two parts, so no credential that rode in the remote
URL can ever survive into what the board displays.
"""

from __future__ import annotations

from urllib.parse import unquote

from wkx_ecosystem_localhost.redaction import strip_credentials
from wkx_ecosystem_localhost.semver import parse_semver, precedence_key

_GITHUB_HOST = "github.com"
_GIT_SUFFIX = ".git"
_SCHEME_SEP = "://"

# The public path a repo exposes for its blessed "latest release", and the marker
# its redirect target carries when a release exists. A repo with no release
# redirects to the bare ``/releases`` page, which has no ``/tag/`` segment.
_RELEASES_LATEST_PATH = "/releases/latest"
_RELEASES_TAG_MARKER = "/releases/tag/"


def _split_host_path(url: str) -> tuple[str | None, str]:
    """Split a remote URL into its host and the path that follows it.

    Handles both a scheme URL (``https://host/path``, ``ssh://git@host/path``) and
    the scp-style form (``git@host:path``). The userinfo has already been stripped
    for scheme URLs, so the authority is the bare host, optionally with a port;
    the port is dropped. For the scp form the leading ``user@`` is dropped. A URL
    in neither shape yields ``(None, "")``.
    """
    if _SCHEME_SEP in url:
        _scheme, _, rest = url.partition(_SCHEME_SEP)
        authority, _, path = rest.partition("/")
        host = authority.partition(":")[0]
        return host, path
    if ":" in url:
        before, _, path = url.partition(":")
        host = before.rpartition("@")[2]
        return host, path
    return None, ""


def parse_owner_repo(url: str) -> tuple[str, str] | None:
    """Derive ``(owner, repo)`` from a GitHub remote URL.

    Credentials are stripped first, so a tokened https remote cannot derail host
    detection. The result is None for a non-GitHub host, an empty string, or a URL
    that does not carry both an owner and a repo.

    Args:
        url: The raw remote URL, in either the https or the scp-style form.

    Returns:
        The ``(owner, repo)`` pair with any ``.git`` suffix removed, or None when
        the remote is not a fully specified GitHub remote.
    """
    host, path = _split_host_path(strip_credentials(url.strip()))
    if host is None or host.lower() != _GITHUB_HOST:
        return None
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(_GIT_SUFFIX)
    if not owner or not repo:
        return None
    return owner, repo


def github_link(url: str) -> str | None:
    """Build the ``https://github.com/owner/repo`` link for a GitHub remote.

    The companion to :func:`parse_owner_repo`: it reconstructs the canonical
    repository link from just the owner and repo, so the link exposes only those
    two, never a credential from the original remote.

    Args:
        url: The raw remote URL, in either the https or the scp-style form.

    Returns:
        The repository link, or None when the remote is not a GitHub remote.
    """
    owner_repo = parse_owner_repo(url)
    if owner_repo is None:
        return None
    owner, repo = owner_repo
    return f"https://{_GITHUB_HOST}/{owner}/{repo}"


def releases_latest_url(url: str) -> str | None:
    """Build the public ``releases/latest`` URL to follow for a GitHub remote.

    Reuses :func:`github_link`, so the URL is rebuilt from just the owner and repo
    and any credential that rode in the remote is stripped first: nothing sensitive
    can ever reach the outbound request (ADR 0002).

    Args:
        url: The raw remote URL, in either the https or the scp-style form.

    Returns:
        The ``https://github.com/owner/repo/releases/latest`` URL, or None when the
        remote is not a GitHub remote.
    """
    link = github_link(url)
    return f"{link}{_RELEASES_LATEST_PATH}" if link is not None else None


def release_tag_from_redirect(url: str) -> str | None:
    """Extract the release tag from a resolved ``releases/latest`` redirect URL.

    GitHub redirects ``.../releases/latest`` to ``.../releases/tag/<TAG>`` when the
    repository has a published release, and to the bare ``.../releases`` page (no
    ``/tag/`` segment) when it has none. The tag is the segment after the
    ``/releases/tag/`` marker, percent-decoded so a tag carrying a slash reads back
    whole, so a repo with no release yields None rather than an invented tag.

    Args:
        url: The final URL the ``releases/latest`` request resolved to.

    Returns:
        The release tag, or None when the URL carries no ``/releases/tag/`` segment.
    """
    _before, marker, tail = url.strip().partition(_RELEASES_TAG_MARKER)
    if not marker or not tail:
        return None
    segment = tail.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    return unquote(segment) or None


def release_differs(release: str | None, latest: str | None) -> bool:
    """Decide whether a GitHub release should be surfaced beside the tag-based latest.

    The board keeps the common case quiet: it surfaces the GitHub-blessed release
    only when it names a different version than the highest semver tag already
    shown. A missing release never differs. Two tags that are the same version
    formatted differently (``v2.0.0`` and ``2.0.0``) do not differ; a release on a
    tag git's semver ranking cannot see, an older release or a non-version tag such
    as ``nightly``, does, and so does a release when there is no tag-based latest to
    sit beside.

    Args:
        release: The GitHub-blessed release tag, or None when there is no release.
        latest: The highest semver tag from ``git ls-remote``, or None when the
            listing found no usable version tags.

    Returns:
        True when the release should be shown labelled alongside the tag.
    """
    if release is None:
        return False
    if release == latest:
        return False
    if latest is None:
        return True
    parsed_release, parsed_latest = parse_semver(release), parse_semver(latest)
    if parsed_release is None or parsed_latest is None:
        return True
    return precedence_key(parsed_release) != precedence_key(parsed_latest)
