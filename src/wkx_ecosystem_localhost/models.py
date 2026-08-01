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
