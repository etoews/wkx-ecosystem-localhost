"""Typed models the API serialises verbatim.

Each Collector is a pure function from probe results to one of these models; the
JSON API returns them unchanged. Values are already display-ready: paths are
home-relative, emails are masked, and remote URLs have had credentials stripped
before they reach a model, so nothing downstream has to redact again.
"""

from __future__ import annotations

from pydantic import BaseModel


class ConfigEntry(BaseModel):
    """One whitelisted git config setting, labelled with the scope it came from.

    ``value`` is always safe to display: an email arrives masked and a remote URL
    arrives credential-stripped. ``raw`` carries the unmasked value for the few
    keys the board reveals on demand (currently ``user.email``); it is None for
    everything else so sensitive values are never shipped by accident.
    """

    key: str
    value: str
    scope: str
    raw: str | None = None


class Repo(BaseModel):
    """A discovered git repository and its working-tree state.

    ``branch`` and ``detached_sha`` are mutually exclusive: a repo is either on a
    branch or detached at a short SHA. ``ahead`` and ``behind`` stay None until
    the background fetch lands in M2; the board renders that as "pending".
    """

    name: str
    path: str
    branch: str | None
    detached_sha: str | None
    upstream: str | None
    staged: int
    unstaged: int
    untracked: int
    unmerged: int
    stashes: int
    dirty: bool
    ahead: int | None = None
    behind: int | None = None
    config: list[ConfigEntry]


class WorkspaceSection(BaseModel):
    """The workspace Section: every repo found under the scanned roots."""

    roots: list[str]
    repos: list[Repo]


class Submodule(BaseModel):
    """One submodule of a discovered repo, versioned against its remote tags.

    ``pinned`` is the version the parent repo pins the submodule at, read from
    tags via ``git describe`` (None when the commit is not on or after any tag).
    ``latest`` and ``behind`` stay None until the remote tag listing lands over
    SSE, exactly as ahead/behind does for a repo; the board renders that as
    "pending". ``latest`` is the highest stable remote release and ``behind`` is
    how many releases the pinned commit sits below it. ``unknown`` is True when
    the remote could not be listed at all, so the row shows a labelled unknown
    state rather than an invented count.
    """

    name: str
    repo: str
    path: str
    pinned: str | None
    latest: str | None = None
    behind: int | None = None
    unknown: bool = False


class SubmoduleSection(BaseModel):
    """The submodules Section: every submodule of every discovered repo."""

    submodules: list[Submodule]


class SubmoduleEvent(BaseModel):
    """One submodule's remote-tag result, streamed over SSE as its listing lands.

    ``submodule`` is the home-relative path, matching ``Submodule.path`` so the
    board fills the right row. ``latest`` is the highest stable remote release and
    ``behind`` the number of releases the pinned commit is below it; both are None
    when the remote has no usable version tags. ``unknown`` is True when the remote
    could not be reached, so the row shows a labelled unknown state.
    """

    submodule: str
    latest: str | None = None
    behind: int | None = None
    unknown: bool = False


class FetchEvent(BaseModel):
    """One repo's ahead/behind, streamed over SSE as its background fetch lands.

    ``repo`` is the home-relative path, matching ``Repo.path`` so the board fills
    the right row. ``ahead`` and ``behind`` are counts since the fetch that just
    completed; both are None when the repo has no upstream to compare against.
    ``unknown`` is True when the fetch could not reach the remote at all, so the
    row shows a labelled unknown state rather than a stale or invented count.
    """

    repo: str
    ahead: int | None = None
    behind: int | None = None
    unknown: bool = False
