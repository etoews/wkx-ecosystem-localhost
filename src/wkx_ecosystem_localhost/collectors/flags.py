"""The Flag layer: data-evident anomalies derived from the Sections.

The one cross-cutting layer. It gathers no new facts of its own: every Flag is
derived purely from what the other Collectors already reported, with no external
ruleset, exactly as CONTEXT.md defines a Flag. ``derive_flags`` is a pure function
over the Section models, so every per-item and cross-item Flag pins directly
against synthetic models; ``collect_flags`` wires it to the seam by running the
Collectors it depends on and handing their Sections to the pure derivation.

Two Flags need a background fetch before they are known to be open, a repo behind
its remote and a submodule behind its tags. Those arrive over SSE (M2) and are
raised by the board as the events land, so they are deliberately not derived here:
this layer covers only what is evident from the Sections at rest.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from pathlib import Path

from wkx_ecosystem_localhost.collectors.claude import collect_claude
from wkx_ecosystem_localhost.collectors.docker import collect_docker
from wkx_ecosystem_localhost.collectors.git_config import collect_git_config
from wkx_ecosystem_localhost.collectors.homebrew import collect_homebrew
from wkx_ecosystem_localhost.collectors.system import collect_system_tools
from wkx_ecosystem_localhost.collectors.toolchains import collect_toolchains
from wkx_ecosystem_localhost.collectors.workspace import (
    DiscoveryCache,
    collect_workspace,
    discover_repos,
)
from wkx_ecosystem_localhost.config import Settings, ToolSpec
from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import (
    ClaudeSection,
    DockerSection,
    Flag,
    FlagsSection,
    GitConfigSection,
    HomebrewSection,
    NodeToolchain,
    PythonToolchain,
    Section,
    SystemToolsSection,
    Tool,
    ToolchainsSection,
    WorkspaceSection,
)

# The two levels from CONTEXT.md: amber (attention) and red (problem). Strings,
# not the Status words, so the wire and the board never inherit up/stabilising/down.
ATTENTION = "attention"
PROBLEM = "problem"

# Every Flag Category the board can raise: the stable registry a Mute validates a
# rule's ``category`` against, so a misspelt Category fails fast. The seventeen
# derived below, plus ``behind-remote`` and ``submodule-tags-behind`` — the two the
# board raises client-side as its SSE events land (a repo behind its remote, a
# submodule behind its tags). Those two have no server-side home, so they are named
# here explicitly; they are still real Categories an operator can Mute. The client's
# CATEGORY_LABEL map must list exactly these ids (a test cross-checks the two).
CATEGORIES: frozenset[str] = frozenset(
    {
        "dirty-tree",
        "detached-head",
        "no-upstream",
        "behind-remote",
        "brew-outdated",
        "python-pin-drift",
        "tool-version-drift",
        "submodule-tags-behind",
        "docker-unreachable",
        "tool-missing",
        "skill-disabled",
        "plugin-disabled",
        "skill-shadow",
        "mcp-needs-auth",
        "mcp-two-scopes",
        "git-config-conflict",
        "git-include-broken",
        "git-config-credentials",
        "git-no-identity",
    }
)


def derive_flags(
    *,
    workspace: WorkspaceSection,
    toolchains: ToolchainsSection,
    system: SystemToolsSection,
    claude: ClaudeSection,
    homebrew: HomebrewSection,
    docker: DockerSection,
    git_config: GitConfigSection,
    off: Collection[Section] = (),
) -> list[Flag]:
    """Derive every at-rest Flag from the Sections, with no external ruleset.

    Pure over the Section models: given the same Sections it returns the same
    Flags, so each anomaly pins against a hand-written synthetic model. Each Flag
    names the ``section`` and ``target`` of the row it badges, so the board settles
    it onto the right row without this layer knowing how that row is drawn.

    An Off Section raises no Flags: its derivation is skipped, so the Sections it
    would badge stay silent even when their models carry anomalies. The cross-item
    drift derivation reads two Sections at once, so toolchains and claude are gated
    independently, and one being Off never silences the other.

    Args:
        workspace: The workspace Section (per-repo tree state).
        toolchains: The toolchains Section (Python pins and per-repo TypeScript).
        system: The system Section (configured developer CLIs).
        claude: The claude Section (skills, plugins, MCP servers).
        homebrew: The homebrew Section (outdated formulae and casks).
        docker: The docker Section (daemon reachability).
        git_config: The git-config Section (global gitconfig chain).
        off: The Sections switched off in configuration, whose derivation is
            skipped so they raise no Flags.

    Returns:
        The open Flags, per-item first then cross-item, in a stable order.
    """
    flags: list[Flag] = []
    if Section.WORKSPACE not in off:
        flags += _workspace_flags(workspace)
    if Section.HOMEBREW not in off:
        flags += _homebrew_flags(homebrew)
    if Section.DOCKER not in off:
        flags += _docker_flags(docker)
    if Section.SYSTEM not in off:
        flags += _system_flags(system)
    if Section.CLAUDE not in off:
        flags += _claude_flags(claude)
    if Section.GIT_CONFIG not in off:
        flags += _git_config_flags(git_config)
    flags += _drift_flags(toolchains, claude, off)
    return flags


def _workspace_flags(workspace: WorkspaceSection) -> list[Flag]:
    """Per-repo Flags: a dirty tree, a detached HEAD, or a branch with no upstream."""
    flags: list[Flag] = []
    for repo in workspace.repos:
        if repo.dirty:
            flags.append(
                Flag(
                    section=Section.WORKSPACE,
                    target=repo.path,
                    level=ATTENTION,
                    category="dirty-tree",
                    message="uncommitted changes",
                )
            )
        if repo.detached_sha is not None:
            flags.append(
                Flag(
                    section=Section.WORKSPACE,
                    target=repo.path,
                    level=ATTENTION,
                    category="detached-head",
                    message="detached HEAD",
                )
            )
        if repo.branch is not None and repo.upstream is None:
            flags.append(
                Flag(
                    section=Section.WORKSPACE,
                    target=repo.path,
                    level=ATTENTION,
                    category="no-upstream",
                    message="no upstream",
                )
            )
    return flags


def _homebrew_flags(homebrew: HomebrewSection) -> list[Flag]:
    """One Flag per outdated formula and cask, keyed by kind so names never collide."""
    if not homebrew.present:
        return []
    flags: list[Flag] = []
    for kind, packages in (("formula", homebrew.formulae), ("cask", homebrew.casks)):
        for package in packages:
            flags.append(
                Flag(
                    section=Section.HOMEBREW,
                    target=f"{kind}:{package.name}",
                    level=ATTENTION,
                    category="brew-outdated",
                    message="update available",
                )
            )
    return flags


def _docker_flags(docker: DockerSection) -> list[Flag]:
    """A single Flag when the Docker daemon cannot be reached."""
    if docker.daemon_reachable:
        return []
    return [
        Flag(
            section=Section.DOCKER,
            target="daemon",
            level=PROBLEM,
            category="docker-unreachable",
            message="daemon unreachable",
        )
    ]


def _system_flags(system: SystemToolsSection) -> list[Flag]:
    """One Flag per configured tool that is not installed on this machine."""
    return [
        Flag(
            section=Section.SYSTEM,
            target=tool.name,
            level=PROBLEM,
            category="tool-missing",
            message="not installed",
        )
        for tool in system.tools
        if not tool.present
    ]


def _claude_flags(claude: ClaudeSection) -> list[Flag]:
    """Per-item Claude Flags: a disabled skill or plugin, or an MCP needing auth.

    A disabled plugin raises exactly one ``plugin-disabled`` Flag and nothing else
    for its assets: its skills are enabled on their own (a plugin skill has no
    switch, so ``skill.enabled`` never falls false for one), and its MCP servers are
    held back from the ``mcp-needs-auth`` Flag, so the disabled plugin is the single
    fact to fix. Only a skill disabled on its own — a user skill set to ``off`` in
    ``skillOverrides`` — raises ``skill-disabled``.
    """
    disabled_plugin_origins = {
        f"{plugin.name}@{plugin.marketplace}" for plugin in claude.plugins if not plugin.enabled
    }
    flags: list[Flag] = []
    for skill in claude.skills:
        if not skill.enabled:
            flags.append(
                Flag(
                    section=Section.CLAUDE,
                    target=f"skill:{skill.name}",
                    level=ATTENTION,
                    category="skill-disabled",
                    message="disabled",
                )
            )
    for plugin in claude.plugins:
        if not plugin.enabled:
            flags.append(
                Flag(
                    section=Section.CLAUDE,
                    target=f"plugin:{plugin.name}",
                    level=ATTENTION,
                    category="plugin-disabled",
                    message="disabled",
                )
            )
    for server in claude.mcp_servers:
        if server.needs_auth and server.origin not in disabled_plugin_origins:
            flags.append(
                Flag(
                    section=Section.CLAUDE,
                    target=f"mcp:{server.name}",
                    level=PROBLEM,
                    category="mcp-needs-auth",
                    message="needs auth",
                )
            )
    return flags


def _git_config_flags(git_config: GitConfigSection) -> list[Flag]:
    """Per-item git-config Flags: conflicts, broken includes, credentials, no identity.

    A single-valued key set to more than one value is a conflict (a multi-valued
    key holding a list is not); an include pointing at a missing file is broken; a
    value carrying an embedded credential is a leak risk; and a chain with no
    ``user.email`` has no committing identity. Each badges the ``git-config``
    section on the exact key, include path, or identity it concerns.
    """
    flags: list[Flag] = []

    # A conflict is a single-valued key a later entry overrides with a different
    # value. The Collector already marks the earlier entry ``shadowed`` from the
    # raw values, so two values that both redact to bullets are still caught and
    # multi-valued keys (which are never shadowed) are already excluded there.
    conflict_keys: list[str] = []
    seen_conflicts: set[str] = set()
    for entry in git_config.entries:
        if entry.shadowed and entry.key not in seen_conflicts:
            seen_conflicts.add(entry.key)
            conflict_keys.append(entry.key)
    for key in conflict_keys:
        flags.append(
            Flag(
                section=Section.GIT_CONFIG,
                target=key,
                level=ATTENTION,
                category="git-config-conflict",
                message="set to differing values",
            )
        )

    for include in git_config.includes:
        if not include.exists:
            flags.append(
                Flag(
                    section=Section.GIT_CONFIG,
                    target=include.path,
                    level=PROBLEM,
                    category="git-include-broken",
                    message="include file not found",
                )
            )

    for entry in git_config.entries:
        if entry.credentials:
            flags.append(
                Flag(
                    section=Section.GIT_CONFIG,
                    target=entry.key,
                    level=PROBLEM,
                    category="git-config-credentials",
                    message="credentials embedded in value",
                )
            )

    if not git_config.identity_present:
        flags.append(
            Flag(
                section=Section.GIT_CONFIG,
                target="identity",
                level=ATTENTION,
                category="git-no-identity",
                message="no identity in global git config",
            )
        )

    return flags


def _drift_flags(
    toolchains: ToolchainsSection, claude: ClaudeSection, off: Collection[Section]
) -> list[Flag]:
    """Cross-item Flags: drift and shadowing evident only across several rows.

    Python pin drift and TypeScript version drift read across repos; skill-name
    shadowing reads across Origins; an MCP configured in two scopes reads across
    scopes. Each fires only when the divergence is real (more than one distinct
    value, or more than one Origin or scope) and then badges every row that takes
    part, so the drift is legible on each side of it. The toolchains drift and the
    claude shadowing are gated on their own Section, so turning one off leaves the
    other's Flags untouched.
    """
    flags: list[Flag] = []

    if Section.TOOLCHAINS not in off:
        pins = toolchains.python.repo_pins
        if len({pin.version for pin in pins}) > 1:
            for pin in pins:
                flags.append(
                    Flag(
                        section=Section.TOOLCHAINS,
                        target=f"pin:{pin.repo}",
                        level=ATTENTION,
                        category="python-pin-drift",
                        message="pin differs across repos",
                    )
                )

        ts_repos = toolchains.node.repos
        installed = {repo.installed for repo in ts_repos if repo.installed is not None}
        if len(installed) > 1:
            for repo in ts_repos:
                if repo.installed is not None:
                    flags.append(
                        Flag(
                            section=Section.TOOLCHAINS,
                            target=f"ts:{repo.repo}",
                            level=ATTENTION,
                            category="tool-version-drift",
                            message="version differs across repos",
                        )
                    )

    if Section.CLAUDE not in off:
        flags += _shadow_flags(claude)
        flags += _two_scope_flags(claude)
    return flags


def _shadow_flags(claude: ClaudeSection) -> list[Flag]:
    """A Flag on each skill whose name is shared by another Origin."""
    origins_by_name: dict[str, set[str]] = defaultdict(set)
    for skill in claude.skills:
        origins_by_name[skill.name].add(skill.origin)
    shadowed = {name for name, origins in origins_by_name.items() if len(origins) > 1}
    return [
        Flag(
            section=Section.CLAUDE,
            target=f"skill:{skill.name}",
            level=ATTENTION,
            category="skill-shadow",
            message="shadows another origin",
        )
        for skill in claude.skills
        if skill.name in shadowed
    ]


def _two_scope_flags(claude: ClaudeSection) -> list[Flag]:
    """A Flag on each MCP server configured under more than one scope."""
    scopes_by_name: dict[str, set[str]] = defaultdict(set)
    for server in claude.mcp_servers:
        scopes_by_name[server.name].add(server.origin)
    two_scope = {name for name, origins in scopes_by_name.items() if len(origins) > 1}
    seen: set[str] = set()
    flags: list[Flag] = []
    for server in claude.mcp_servers:
        if server.name in two_scope and server.name not in seen:
            seen.add(server.name)
            flags.append(
                Flag(
                    section=Section.CLAUDE,
                    target=f"mcp:{server.name}",
                    level=ATTENTION,
                    category="mcp-two-scopes",
                    message="configured in two scopes",
                )
            )
    return flags


def _empty_toolchains() -> ToolchainsSection:
    """A blank toolchains Section, the placeholder for an Off toolchains.

    ``collect_flags`` skips a Collector whose Section is Off, but ``derive_flags``
    takes every Section by keyword; this supplies the value it never reads (the Off
    guard skips the derivation), so no toolchains probe runs when the Section is Off.
    """
    absent = Tool(name="", present=False)
    return ToolchainsSection(
        python=PythonToolchain(interpreters=[], global_pin=None, repo_pins=[], system=absent),
        node=NodeToolchain(node=absent, npm=absent, tsc=absent, package_managers=[], repos=[]),
    )


def _discover(
    machine: Machine, settings: Settings, *, home: Path, discovery: DiscoveryCache | None
) -> list[Path]:
    """Walk the scan roots, through the shared cache when one is supplied."""
    if discovery is not None:
        return discovery.discover(
            machine,
            settings.scan_roots,
            home=home,
            max_depth=settings.scan_depth,
            excludes=settings.exclude,
        )
    return discover_repos(
        machine,
        settings.scan_roots,
        home=home,
        max_depth=settings.scan_depth,
        excludes=settings.exclude,
    )


def collect_flags(
    machine: Machine,
    settings: Settings,
    *,
    home: Path,
    discovery: DiscoveryCache | None = None,
) -> FlagsSection:
    """Collect the Flag layer: run the Sections' Collectors, then derive the Flags.

    A pure orchestration over the seam. It runs the Collectors whose facts a Flag
    can be derived from and hands their Sections to ``derive_flags``, so the whole
    layer is exercised in tests against a fake machine exactly as production would
    produce it. Repo discovery is shared with the toolchains read so the per-repo
    pins and TypeScript line up with the repos the workspace found.

    An Off Section's Collector does not run and its derivation is skipped, so it
    raises no Flags. Repo discovery is shared with the toolchains read, so it still
    runs when only workspace is Off; a placeholder Section stands in for each Off
    Collector, and the Off guard in ``derive_flags`` keeps it from being read.

    Args:
        machine: The seam every Collector reads through.
        settings: Typed configuration (scan roots, depth, Excludes, the system
            tools, and the Off Sections).
        home: Home directory, for relativising displayed paths.
        discovery: Shared discovery cache. When given, both the toolchains read and
            the workspace read take their repo walk from it, so a board load walks
            the roots once across this layer and every route; when None the walks
            run directly, so a unit test drives the layer without a cache.

    Returns:
        The Flag layer Section: the open Flags derivable from the Sections at rest.
    """
    off = set(settings.sections_off)
    # Repo discovery feeds the toolchains read, the sole consumer of repo_paths here
    # (workspace does its own discovery, sharing the same cache), so it runs whenever
    # toolchains is on — including when workspace is Off. With toolchains Off too, the
    # whole tree walk would go unused, so it is skipped. The Exclude globs prune the
    # walk either way, and the shared cache keeps it to one walk per board load.
    repo_paths: Sequence[Path] = (
        _discover(machine, settings, home=home, discovery=discovery)
        if Section.TOOLCHAINS not in off
        else ()
    )
    workspace = (
        collect_workspace(
            machine,
            settings.scan_roots,
            home=home,
            max_depth=settings.scan_depth,
            excludes=settings.exclude,
            discovery=discovery,
        )
        if Section.WORKSPACE not in off
        else WorkspaceSection(roots=[], repos=[])
    )
    toolchains = (
        collect_toolchains(machine, repo_paths, home=home)
        if Section.TOOLCHAINS not in off
        else _empty_toolchains()
    )
    system_tools: Sequence[ToolSpec] = settings.system_tools
    system = (
        collect_system_tools(machine, system_tools)
        if Section.SYSTEM not in off
        else SystemToolsSection(tools=[])
    )
    claude = (
        collect_claude(machine, home=home)
        if Section.CLAUDE not in off
        else ClaudeSection(skills=[], plugins=[], mcp_servers=[])
    )
    homebrew = (
        collect_homebrew(machine) if Section.HOMEBREW not in off else HomebrewSection(present=False)
    )
    docker = (
        collect_docker(machine)
        if Section.DOCKER not in off
        else DockerSection(daemon_reachable=False)
    )
    git_config = (
        collect_git_config(machine, home=home)
        if Section.GIT_CONFIG not in off
        else GitConfigSection(entries=[], includes=[], identity_present=True)
    )

    flags = derive_flags(
        workspace=workspace,
        toolchains=toolchains,
        system=system,
        claude=claude,
        homebrew=homebrew,
        docker=docker,
        git_config=git_config,
        off=off,
    )
    return FlagsSection(flags=flags)
