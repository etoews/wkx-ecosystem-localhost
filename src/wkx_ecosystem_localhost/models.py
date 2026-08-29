"""Typed models the API serialises verbatim.

Each Collector is a pure function from probe results to one of these models; the
JSON API returns them unchanged. Values are already display-ready: paths are
home-relative, emails are masked, and remote URLs have had credentials stripped
before they reach a model, so nothing downstream has to redact again.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class Section(StrEnum):
    """The board's ten top-level Sections, each addressed by its panel label.

    The single source of the Section names. It types ``Flag.section`` so a Flag can
    only ever name a real Section, backs ``Settings.sections_off`` so an unknown name
    fails fast, and each member's value equals the ``id`` of the panel that renders
    it in ``index.html``. As a ``StrEnum`` a member is its own string, so the JSON
    API serialises it verbatim (``Section.GIT_CONFIG`` is ``"git-config"``) and no
    caller has to convert. Needs attention is deliberately absent: it is a
    cross-cutting summary, not a Section, so it can be Hidden but never Off.
    """

    WORKSPACE = "workspace"
    TOOLCHAINS = "toolchains"
    CLAUDE = "claude"
    HOMEBREW = "homebrew"
    SYSTEM = "system"
    DOCKER = "docker"
    FOOTPRINT = "footprint"
    EDITOR = "editor"
    GIT_CONFIG = "git-config"
    CONFIG = "config"


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
    ``github`` is the ``https://github.com/owner/repo`` link derived from the
    primary remote (preferring ``remote.origin.url``), or None when that remote is
    not a GitHub remote. Like every remote fact it exposes only owner and repo,
    never a credential.
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
    github: str | None = None
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
    state rather than an invented count. ``github`` is the
    ``https://github.com/owner/repo`` link derived from the submodule's remote, or
    None when that remote is not a GitHub remote; it exposes only owner and repo.
    ``github_release`` is the release GitHub blesses as latest, read token-free over
    the same SSE probe (ADR 0002) and surfaced only when it differs from the
    tag-based ``latest``; it stays None for a non-GitHub submodule, an unreachable
    or release-less repo, or when it names the version already shown, so the common
    case stays quiet. Like ``latest`` and ``behind`` it is None here until the probe
    lands.
    """

    name: str
    repo: str
    path: str
    pinned: str | None
    latest: str | None = None
    behind: int | None = None
    unknown: bool = False
    github: str | None = None
    github_release: str | None = None


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
    ``github_release`` is the release GitHub blesses as latest for a GitHub
    submodule, surfaced only when it differs from the tag-based ``latest`` (ADR
    0002); it is None for a non-GitHub, unreachable, or release-less submodule, or
    when it names the version already shown, so the board augments the row only when
    the two facts genuinely disagree.
    """

    submodule: str
    latest: str | None = None
    behind: int | None = None
    unknown: bool = False
    github_release: str | None = None


class UvPython(BaseModel):
    """One interpreter uv knows about, from ``uv python list``.

    ``installed`` distinguishes an interpreter present on this machine from one uv
    merely offers to download; only installed interpreters reach the board.
    ``path`` is the home-relative path uv reports for it, or None when uv gives no
    path.
    """

    implementation: str
    version: str
    installed: bool
    path: str | None = None


class RepoPin(BaseModel):
    """One repo's Python pin, read from its ``.python-version``.

    ``repo`` is the home-relative repo path and ``version`` is the pinned
    interpreter version verbatim.
    """

    repo: str
    version: str


class Tool(BaseModel):
    """A command-line tool's presence and version, as a bare fact.

    ``present`` is False and ``version`` None when the tool is not on this
    machine: an absent toolchain is a fact to show, never an error. When present,
    ``version`` is the reported version with any leading ``v`` stripped.
    """

    name: str
    version: str | None = None
    present: bool


class SystemToolsSection(BaseModel):
    """The system Section: each configured developer CLI as present-or-missing.

    One ``Tool`` per configured tool, in the configured order. A present tool
    carries its parsed version; a missing one carries None, which the board renders
    as a plain "missing" fact rather than an error. The list of tools probed is
    configuration, so the Section grows without any code change.
    """

    tools: list[Tool]


class RepoTypeScript(BaseModel):
    """A repo's declared versus installed TypeScript, so drift reads at a glance.

    ``declared`` is the spec from the repo's ``package.json`` (for example
    ``^5.3.3``) and ``installed`` is the concrete version resolved under
    ``node_modules/typescript``. Either is None when that fact is absent: a repo
    can declare TypeScript without having installed it, or carry an installed copy
    it no longer declares.
    """

    repo: str
    declared: str | None = None
    installed: str | None = None


class PythonToolchain(BaseModel):
    """The Python side of the toolchains Section, all facts side by side.

    ``interpreters`` are the installed interpreters uv manages, ``global_pin`` is
    the uv global ``.python-version`` (None when unset), ``repo_pins`` are the
    per-repo pins, and ``system`` is the ``python3`` found on the path.
    """

    interpreters: list[UvPython]
    global_pin: str | None = None
    repo_pins: list[RepoPin]
    system: Tool


class NodeToolchain(BaseModel):
    """The Node and TypeScript side of the toolchains Section.

    ``node``, ``npm``, and ``tsc`` are the global tools; ``package_managers``
    lists pnpm and bun but only the ones actually present, so an absent one is
    simply not shown. ``repos`` carries the per-repo declared-versus-installed
    TypeScript for every repo that declares or installs it.
    """

    node: Tool
    npm: Tool
    tsc: Tool
    package_managers: list[Tool]
    repos: list[RepoTypeScript]


class ToolchainsSection(BaseModel):
    """The toolchains Section: the whole language story in one panel."""

    python: PythonToolchain
    node: NodeToolchain


class Skill(BaseModel):
    """One skill on this machine, with the Origin it came from.

    ``origin`` is the single word (or ``<plugin>@<marketplace>`` pair) that answers
    where the skill came from: ``user`` for one authored locally under
    ``~/.claude/skills``, or the plugin pair for one a plugin ships. ``enabled`` is
    the skill's own state, not its plugin's: a user skill is enabled unless the
    ``skillOverrides`` setting sets it to ``off``, and a plugin skill is always
    enabled because a plugin skill has no switch of its own. ``plugin_enabled``
    carries the owning plugin's enabled state for a plugin skill and is None for a
    user skill, so the board can note a skill whose plugin is off without turning
    that into the skill's own disabled state. ``visibility`` is the non-default
    ``skillOverrides`` tier of a user skill — ``name-only`` or
    ``user-invocable-only`` — and None for a fully on skill or any plugin skill, so
    the board shows the visibility fact without raising a Flag. ``description`` is
    the one-line summary from the skill's front matter, or None when it declares
    none.
    """

    name: str
    origin: str
    description: str | None = None
    enabled: bool
    plugin_enabled: bool | None = None
    visibility: str | None = None


class Plugin(BaseModel):
    """One installed plugin, joined across the manifest, marketplace, and settings.

    ``name`` and ``marketplace`` are the two halves of the ``<name>@<marketplace>``
    key. ``repo`` is the marketplace's GitHub ``owner/repo`` from the known
    marketplaces map, or None when the marketplace is not a GitHub source.
    ``version`` is the installed version verbatim (``unknown`` when the manifest
    records no version). ``enabled`` is the settings enabled state, so a disabled
    plugin is shown and badged rather than filtered. ``install_path`` is the
    home-relative install location, or None when the manifest records none.
    """

    name: str
    marketplace: str
    repo: str | None = None
    version: str
    enabled: bool
    install_path: str | None = None


class McpServer(BaseModel):
    """One MCP server on this machine, as a bare fact with its Origin.

    ``origin`` is where the server is configured: ``user`` or ``project`` for one
    in the Claude user config, or the ``<plugin>@<marketplace>`` pair for one a
    plugin ships. ``transport`` is the connection kind (``stdio``, ``http``, or
    ``sse``), derived from the config shape, never carrying the command, URL,
    headers, or environment, so no secret rides along. ``needs_auth`` is True when
    the server is recorded in the auth-needed cache, so the board shows a server
    that still needs authenticating without ever touching a credential.
    """

    name: str
    origin: str
    transport: str
    needs_auth: bool


class ClaudeSection(BaseModel):
    """The claude Section: skills, plugins, and MCP servers, each with its Origin.

    Everything installed is present; enabled or disabled is a badge on the row, not
    a filter. Only the MCP server subset of the Claude user config is ever read;
    account, machine, and telemetry fields are never touched.
    """

    skills: list[Skill]
    plugins: list[Plugin]
    mcp_servers: list[McpServer]


class OutdatedPackage(BaseModel):
    """One Homebrew package with a newer version available.

    ``installed`` is the version (or versions) currently on this machine, joined
    for display when Homebrew records more than one; ``current`` is the version
    Homebrew would upgrade it to. A formula and a cask share this shape; which
    list a package sits in is the only thing that tells them apart.
    """

    name: str
    installed: str
    current: str


class HomebrewSection(BaseModel):
    """The homebrew Section: outdated formulae and casks, or Homebrew's absence.

    ``present`` is False when ``brew`` is not installed on this machine, which the
    board renders as a plain fact rather than an error. When present, ``formulae``
    and ``casks`` carry the outdated packages (either may be empty when everything
    is current); the board reads the counts straight off the list lengths.
    """

    present: bool
    formulae: list[OutdatedPackage] = []
    casks: list[OutdatedPackage] = []


class DockerSection(BaseModel):
    """The docker Section: daemon reachability and a few disk-and-container facts.

    ``daemon_reachable`` is False when ``docker info`` cannot reach the daemon
    (down, or the CLI absent); the board renders that as a fact, never an error,
    and the remaining fields stay at their empty defaults. When reachable,
    ``containers_running`` and ``containers_total`` are the running and the total
    container counts, ``images`` the image count, ``total_disk`` the display-ready
    total disk usage (for example ``4.62 GB``) summed across what ``docker system
    df`` reports, and ``reclaimable`` the reclaimable slice of that (for example
    ``3.23 GB``); each is None when that probe cannot be read.
    """

    daemon_reachable: bool
    containers_running: int = 0
    containers_total: int = 0
    images: int = 0
    total_disk: str | None = None
    reclaimable: str | None = None


class RepoFootprint(BaseModel):
    """One repo's disk footprint: its regenerable ``.venv`` and ``node_modules``.

    ``path`` is home-relative. ``venv`` and ``node_modules`` are the display-ready
    sizes of those two directories (for example ``92.27 MB``), each None when that
    directory is absent, so a repo carrying only one still shows the one it has.
    ``total`` is the display-ready sum of whichever are present, and ``total_bytes``
    the same sum kept raw and unrounded so the board can rank repos by true size
    before rendering the humanised figures.
    """

    name: str
    path: str
    venv: str | None
    node_modules: str | None
    total: str
    total_bytes: int


class FootprintSection(BaseModel):
    """The footprint Section: per-repo disk usage alongside the Docker disk.

    ``repos`` carries one entry per repo that has a ``.venv`` or ``node_modules``,
    biggest first, and ``repos_total`` is the display-ready sum across them.
    ``docker_reachable`` mirrors the docker Section: when False the daemon could
    not be reached and ``docker_total`` and ``docker_reclaimable`` stay None; when
    True they are the display-ready total and reclaimable Docker disk, either None
    when that probe could not be read. No Flags derive from footprint: it is a
    plain size accounting, not a judgement.
    """

    repos: list[RepoFootprint]
    repos_total: str
    docker_reachable: bool
    docker_total: str | None
    docker_reclaimable: str | None


class Flag(BaseModel):
    """A data-evident anomaly, badged inline on the row carrying the fact.

    Derived purely from facts a Collector already gathered, with no external
    ruleset. ``section`` and ``target`` address the exact row the badge lands on
    (for example ``workspace`` and a repo's home-relative path); the board keys its
    rows by the same pair, so a Flag settles onto the right row without the layer
    knowing anything about how that row is drawn. ``section`` is a ``Section`` so a
    Flag can only ever name a real Section; it serialises as its plain label.
    ``level`` is ``attention`` (amber) or ``problem`` (red), the two levels from
    CONTEXT.md. ``category`` is the stable hyphenated Category id of the anomaly (so
    the board rolls Flags up by it, styles or de-duplicates by it, and a Mute names
    one) and ``message`` its short, display-ready phrasing.
    """

    section: Section
    target: str
    level: str
    category: str
    message: str


class FlagsSection(BaseModel):
    """The Flag layer: every open Flag derivable from the Sections at rest.

    A cross-cutting layer: the board badges each Flag onto the row it names and
    rolls the open count up in the Needs attention summary panel (tally tiles plus
    a per-category breakdown), with no Section of its own. Two Flags need a
    background fetch to know they are open (a repo behind its
    remote, a submodule behind its tags); those arrive over SSE and are raised by
    the board as those events land, so they are deliberately absent from this
    at-rest list.
    """

    flags: list[Flag]


class EditorExtension(BaseModel):
    """One installed VS Code extension, as a bare fact.

    ``id`` is the ``publisher.name`` identifier as ``code`` reports it, and
    ``version`` its installed version verbatim; ``version`` is None when the line
    carried no ``@version`` suffix, so a version-less entry still shows the one
    fact it has rather than being dropped.
    """

    id: str
    version: str | None = None


class EditorSection(BaseModel):
    """The editor Section: VS Code's presence, version, and installed extensions.

    ``installed`` is False when ``code --version`` cannot be run (VS Code's CLI
    absent, or not on the path); the board renders that as a fact, never an error,
    and the remaining fields stay at their empty defaults. When installed,
    ``version`` is the parsed CLI version and ``extensions`` the installed
    extensions in the order ``code`` lists them (empty when the extensions probe
    itself could not be read).
    """

    installed: bool
    version: str | None = None
    extensions: list[EditorExtension] = []


class GitConfigEntry(BaseModel):
    """One key in the global gitconfig chain, shown with targeted redaction.

    ``value`` is already display-ready per ADR 0001: a secret-bearing family is
    masked to bullets, a URL value is credential-stripped, and any home path in it
    is rewritten to ``~``. ``origin`` is the home-relative file the key was read
    from (an included file appears with its own path). ``masked`` is True when the
    value was replaced rather than shown, ``credentials`` is True when the raw value
    carried embedded URL credentials (which also forces the value masked), and
    ``shadowed`` is True when a later entry sets the same single-valued key to a
    different value, so git's last-wins means this earlier one has no effect.
    """

    key: str
    value: str
    origin: str
    masked: bool = False
    shadowed: bool = False
    credentials: bool = False


class GitInclude(BaseModel):
    """One ``include``/``includeIf`` directive from the global gitconfig chain.

    ``condition`` is None for a plain ``include.path`` and the ``includeIf``
    condition (for example ``gitdir:~/dev/etoews/``) for a conditional one.
    ``path`` is the home-relative target file, resolved from a ``~/`` prefix or
    against the including file's directory. ``exists`` is whether that target file
    could be read, so a directive pointing at a missing file shows as broken rather
    than silently doing nothing.
    """

    condition: str | None
    path: str
    exists: bool


class GitConfigSection(BaseModel):
    """The git-config Section: the whole global gitconfig chain as facts.

    ``entries`` is every non-include key in origin order, each display-ready and
    self-describing (masked, shadowed, or carrying credentials). ``includes`` is the
    include directives with their targets resolved and existence checked.
    ``identity_present`` is whether a ``user.email`` is set anywhere in the chain, so
    a machine with no committing identity shows as a plain fact. Unlike the M1
    per-repo view this is deny-nothing: every key is shown, secrets masked (ADR 0001).
    """

    entries: list[GitConfigEntry]
    includes: list[GitInclude]
    identity_present: bool


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
