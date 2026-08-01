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
from collections.abc import Sequence
from pathlib import Path

from wkx_ecosystem_localhost.collectors.claude import collect_claude
from wkx_ecosystem_localhost.collectors.docker import collect_docker
from wkx_ecosystem_localhost.collectors.homebrew import collect_homebrew
from wkx_ecosystem_localhost.collectors.system import collect_system_tools
from wkx_ecosystem_localhost.collectors.toolchains import collect_toolchains
from wkx_ecosystem_localhost.collectors.workspace import collect_workspace, discover_repos
from wkx_ecosystem_localhost.config import Settings, ToolSpec
from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import (
    ClaudeSection,
    DockerSection,
    Flag,
    FlagsSection,
    HomebrewSection,
    SystemToolsSection,
    ToolchainsSection,
    WorkspaceSection,
)

# The two levels from CONTEXT.md: amber (attention) and red (problem). Strings,
# not the Status words, so the wire and the board never inherit up/stabilising/down.
ATTENTION = "attention"
PROBLEM = "problem"


def derive_flags(
    *,
    workspace: WorkspaceSection,
    toolchains: ToolchainsSection,
    system: SystemToolsSection,
    claude: ClaudeSection,
    homebrew: HomebrewSection,
    docker: DockerSection,
) -> list[Flag]:
    """Derive every at-rest Flag from the Sections, with no external ruleset.

    Pure over the Section models: given the same Sections it returns the same
    Flags, so each anomaly pins against a hand-written synthetic model. Each Flag
    names the ``section`` and ``target`` of the row it badges, so the board settles
    it onto the right row without this layer knowing how that row is drawn.

    Args:
        workspace: The workspace Section (per-repo tree state).
        toolchains: The toolchains Section (Python pins and per-repo TypeScript).
        system: The system Section (configured developer CLIs).
        claude: The claude Section (skills, plugins, MCP servers).
        homebrew: The homebrew Section (outdated formulae and casks).
        docker: The docker Section (daemon reachability).

    Returns:
        The open Flags, per-item first then cross-item, in a stable order.
    """
    flags: list[Flag] = []
    flags += _workspace_flags(workspace)
    flags += _homebrew_flags(homebrew)
    flags += _docker_flags(docker)
    flags += _system_flags(system)
    flags += _claude_flags(claude)
    flags += _drift_flags(toolchains, claude)
    return flags


def _workspace_flags(workspace: WorkspaceSection) -> list[Flag]:
    """Per-repo Flags: a dirty tree, a detached HEAD, or a branch with no upstream."""
    flags: list[Flag] = []
    for repo in workspace.repos:
        if repo.dirty:
            flags.append(
                Flag(
                    section="workspace",
                    target=repo.path,
                    level=ATTENTION,
                    code="dirty-tree",
                    message="uncommitted changes",
                )
            )
        if repo.detached_sha is not None:
            flags.append(
                Flag(
                    section="workspace",
                    target=repo.path,
                    level=ATTENTION,
                    code="detached-head",
                    message="detached HEAD",
                )
            )
        if repo.branch is not None and repo.upstream is None:
            flags.append(
                Flag(
                    section="workspace",
                    target=repo.path,
                    level=ATTENTION,
                    code="no-upstream",
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
                    section="homebrew",
                    target=f"{kind}:{package.name}",
                    level=ATTENTION,
                    code="brew-outdated",
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
            section="docker",
            target="daemon",
            level=PROBLEM,
            code="docker-unreachable",
            message="daemon unreachable",
        )
    ]


def _system_flags(system: SystemToolsSection) -> list[Flag]:
    """One Flag per configured tool that is not installed on this machine."""
    return [
        Flag(
            section="system",
            target=tool.name,
            level=PROBLEM,
            code="tool-missing",
            message="not installed",
        )
        for tool in system.tools
        if not tool.present
    ]


def _claude_flags(claude: ClaudeSection) -> list[Flag]:
    """Per-item Claude Flags: a disabled skill or plugin, or an MCP needing auth."""
    flags: list[Flag] = []
    for skill in claude.skills:
        if not skill.enabled:
            flags.append(
                Flag(
                    section="claude",
                    target=f"skill:{skill.name}",
                    level=ATTENTION,
                    code="skill-disabled",
                    message="disabled",
                )
            )
    for plugin in claude.plugins:
        if not plugin.enabled:
            flags.append(
                Flag(
                    section="claude",
                    target=f"plugin:{plugin.name}",
                    level=ATTENTION,
                    code="plugin-disabled",
                    message="disabled",
                )
            )
    for server in claude.mcp_servers:
        if server.needs_auth:
            flags.append(
                Flag(
                    section="claude",
                    target=f"mcp:{server.name}",
                    level=PROBLEM,
                    code="mcp-needs-auth",
                    message="needs auth",
                )
            )
    return flags


def _drift_flags(toolchains: ToolchainsSection, claude: ClaudeSection) -> list[Flag]:
    """Cross-item Flags: drift and shadowing evident only across several rows.

    Python pin drift and TypeScript version drift read across repos; skill-name
    shadowing reads across Origins; an MCP configured in two scopes reads across
    scopes. Each fires only when the divergence is real (more than one distinct
    value, or more than one Origin or scope) and then badges every row that takes
    part, so the drift is legible on each side of it.
    """
    flags: list[Flag] = []

    pins = toolchains.python.repo_pins
    if len({pin.version for pin in pins}) > 1:
        for pin in pins:
            flags.append(
                Flag(
                    section="toolchains",
                    target=f"pin:{pin.repo}",
                    level=ATTENTION,
                    code="python-pin-drift",
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
                        section="toolchains",
                        target=f"ts:{repo.repo}",
                        level=ATTENTION,
                        code="tool-version-drift",
                        message="version differs across repos",
                    )
                )

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
            section="claude",
            target=f"skill:{skill.name}",
            level=ATTENTION,
            code="skill-shadow",
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
                    section="claude",
                    target=f"mcp:{server.name}",
                    level=ATTENTION,
                    code="mcp-two-scopes",
                    message="configured in two scopes",
                )
            )
    return flags


def collect_flags(
    machine: Machine,
    settings: Settings,
    *,
    home: Path,
) -> FlagsSection:
    """Collect the Flag layer: run the Sections' Collectors, then derive the Flags.

    A pure orchestration over the seam. It runs the Collectors whose facts a Flag
    can be derived from and hands their Sections to ``derive_flags``, so the whole
    layer is exercised in tests against a fake machine exactly as production would
    produce it. Repo discovery is shared with the toolchains read so the per-repo
    pins and TypeScript line up with the repos the workspace found.

    Args:
        machine: The seam every Collector reads through.
        settings: Typed configuration (scan roots, depth, and the system tools).
        home: Home directory, for relativising displayed paths.

    Returns:
        The Flag layer Section: the open Flags derivable from the Sections at rest.
    """
    repo_paths: Sequence[Path] = discover_repos(
        machine, settings.scan_roots, max_depth=settings.scan_depth
    )
    workspace = collect_workspace(
        machine, settings.scan_roots, home=home, max_depth=settings.scan_depth
    )
    toolchains = collect_toolchains(machine, repo_paths, home=home)
    system_tools: Sequence[ToolSpec] = settings.system_tools
    system = collect_system_tools(machine, system_tools)
    claude = collect_claude(machine, home=home)
    homebrew = collect_homebrew(machine)
    docker = collect_docker(machine)

    flags = derive_flags(
        workspace=workspace,
        toolchains=toolchains,
        system=system,
        claude=claude,
        homebrew=homebrew,
        docker=docker,
    )
    return FlagsSection(flags=flags)
