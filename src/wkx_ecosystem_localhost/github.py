"""Derive a repository's GitHub link from its remote URL, purely and with no I/O.

A GitHub remote comes in two shapes: the https form
(``https://github.com/owner/repo`` with an optional ``.git`` and/or trailing
slash) and the scp-style form (``git@github.com:owner/repo``). Both name the same
``owner`` and ``repo``; a non-GitHub remote names neither. The link is
reconstructed from just those two parts, so no credential that rode in the remote
URL can ever survive into what the board displays.
"""

from __future__ import annotations

from wkx_ecosystem_localhost.redaction import strip_credentials

_GITHUB_HOST = "github.com"
_GIT_SUFFIX = ".git"
_SCHEME_SEP = "://"


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
