"""The claude Collector: skills, plugins, and MCP servers with their Origins.

Reports the Claude environment as facts. Skills come from the user skills
directory and from each installed plugin. Plugins join the installed manifest with
the marketplace map and the enabled state from settings, so version, marketplace
repo, and enabled state read at a glance. MCP servers come from each plugin, from
the Claude user config, and carry an auth-needed state from the auth cache.

Everything reaches the host only through the ``Machine`` seam: manifests, front
matter, and the user config are read as files, and directories are listed to
discover skills. The parsing functions below are pure so their edge cases pin
directly against synthetic fixtures.

Two disciplines hold the whole Section safe to screenshot. The Claude user config
is read narrowly, ``parse_user_config_mcp`` extracting only the MCP server subset
so account, machine, and telemetry fields are never touched. And an MCP server is
reported as a name, an Origin, a transport, and an auth-needed flag only, never
its command, URL, headers, or environment, so a token embedded in a server config
cannot ride onto the board. Facts only; anomaly judgement is the separate M6 Flag
layer.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import ClaudeSection, McpServer, Plugin, Skill
from wkx_ecosystem_localhost.redaction import relativise

logger = logging.getLogger(__name__)

# Everything the Collector reads lives under the user's Claude config directory,
# computed from home so no default carries a machine-specific literal.
_CLAUDE_DIR = ".claude"
_SKILLS_DIR = "skills"
_SKILL_FILE = "SKILL.md"
_PLUGINS_DIR = "plugins"
_INSTALLED_PLUGINS = "installed_plugins.json"
_KNOWN_MARKETPLACES = "known_marketplaces.json"
_AUTH_CACHE = "mcp-needs-auth-cache.json"
_SETTINGS = "settings.json"
_SETTINGS_LOCAL = "settings.local.json"
_USER_CONFIG = ".claude.json"
_PLUGIN_MCP = ".mcp.json"

# The Origin words for a Claude asset, matching CONTEXT.md exactly.
_ORIGIN_USER = "user"
_ORIGIN_PROJECT = "project"

_FRONTMATTER_FENCE = "---"

# Skills can nest a couple of category folders deep; this caps the descent as a
# backstop against a pathologically deep (or, via a real directory, cyclic) tree.
_SKILLS_MAX_DEPTH = 4


@dataclass(frozen=True)
class InstalledPlugin:
    """One entry parsed from ``installed_plugins.json``.

    ``key`` is the raw ``<name>@<marketplace>`` string; ``name`` and
    ``marketplace`` are its two halves. ``version`` is the recorded version
    verbatim (``unknown`` when the manifest has no better answer). ``install_path``
    is the raw (not yet relativised) install location, or None when absent.
    """

    key: str
    name: str
    marketplace: str
    version: str
    install_path: str | None


@dataclass(frozen=True)
class McpServerSpec:
    """One MCP server reduced to the only two facts safe to carry forward.

    ``name`` is the server's key and ``transport`` its connection kind. The
    command, URL, headers, and environment are deliberately dropped here so no
    secret can travel past this point.
    """

    name: str
    transport: str


def parse_skill_frontmatter(text: str) -> tuple[str | None, str | None]:
    """Read a skill's ``name`` and ``description`` from its ``SKILL.md`` front matter.

    The front matter is a leading ``---`` fenced block of simple ``key: value``
    lines. Only ``name`` and ``description`` are read; the body after the closing
    fence is never parsed, so a ``key: value`` shaped line in prose cannot be
    mistaken for metadata. A file with no front matter yields two Nones.

    Args:
        text: The contents of a ``SKILL.md``.

    Returns:
        The ``(name, description)`` pair, each None when the file declares neither
        a front-matter block nor that key.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return None, None

    name: str | None = None
    description: str | None = None
    for line in lines[1:]:
        if line.strip() == _FRONTMATTER_FENCE:
            break
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if key == "name" and value:
            name = value
        elif key == "description" and value:
            description = value
    return name, description


def _load_json(text: str) -> object:
    """Parse JSON, returning None instead of raising so one bad file degrades a row."""
    try:
        return json.loads(text)
    except ValueError:
        return None


def _as_dict(value: object) -> dict[str, object]:
    """Return ``value`` as a string-keyed dict, or an empty one when it is not a dict.

    JSON objects always have string keys, so this both narrows the type for the
    checker and reduces every "not a dict" case to the same empty-map handling.
    """
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def parse_installed_plugins(text: str) -> list[InstalledPlugin]:
    """Parse ``installed_plugins.json`` into one entry per installed plugin.

    The manifest maps a ``<name>@<marketplace>`` key to a list of install records;
    the first record supplies the version and install path. A key with no ``@`` or
    an empty install list is skipped rather than half-reported. Malformed JSON
    yields an empty list.

    Args:
        text: The contents of ``installed_plugins.json``.

    Returns:
        Installed plugins in manifest order.
    """
    plugins_map = _as_dict(_as_dict(_load_json(text)).get("plugins"))

    plugins: list[InstalledPlugin] = []
    for key, records in plugins_map.items():
        name, sep, marketplace = key.rpartition("@")
        if not sep or not name or not marketplace:
            continue
        if not isinstance(records, list) or not records:
            continue
        record = _as_dict(records[0])
        if not record:
            continue
        version = record.get("version")
        install_path = record.get("installPath")
        plugins.append(
            InstalledPlugin(
                key=key,
                name=name,
                marketplace=marketplace,
                version=version if isinstance(version, str) else "unknown",
                install_path=install_path if isinstance(install_path, str) else None,
            )
        )
    return plugins


def parse_known_marketplaces(text: str) -> dict[str, str | None]:
    """Parse ``known_marketplaces.json`` into a marketplace-to-repo map.

    Each marketplace records a source; a GitHub source carries the ``owner/repo``
    slug, and any other source (a local directory, say) has no repo. Malformed
    JSON yields an empty map.

    Args:
        text: The contents of ``known_marketplaces.json``.

    Returns:
        Marketplace name to its GitHub ``owner/repo``, or None when the source is
        not a GitHub repo.
    """
    repos: dict[str, str | None] = {}
    for marketplace, entry in _as_dict(_load_json(text)).items():
        repo: str | None = None
        source = _as_dict(entry).get("source")
        if isinstance(source, dict) and source.get("source") == "github":
            candidate = source.get("repo")
            repo = candidate if isinstance(candidate, str) else None
        repos[marketplace] = repo
    return repos


def parse_enabled_plugins(text: str) -> dict[str, bool]:
    """Read the ``enabledPlugins`` map from a settings file.

    Args:
        text: The contents of ``settings.json`` or ``settings.local.json``.

    Returns:
        The ``<name>@<marketplace>`` to enabled-state map, or an empty map when the
        file declares none or cannot be parsed.
    """
    enabled = _as_dict(_as_dict(_load_json(text)).get("enabledPlugins"))
    return {key: bool(value) for key, value in enabled.items()}


def classify_transport(config: object) -> str:
    """Name an MCP server's transport from its config shape, never its values.

    An explicit ``type`` wins; otherwise a server with a ``url`` is treated as
    ``http`` and one with a ``command`` as ``stdio``, defaulting to ``stdio``. Only
    the derived word is returned, never the URL or command, so nothing sensitive
    leaves this function.

    Args:
        config: One server's configuration object.

    Returns:
        One of ``stdio``, ``http``, or ``sse`` (or an explicit type verbatim,
        lower-cased).
    """
    if isinstance(config, dict):
        declared = config.get("type")
        if isinstance(declared, str) and declared.strip():
            return declared.strip().lower()
        if "url" in config:
            return "http"
        if "command" in config:
            return "stdio"
    return "stdio"


def _servers_from_map(servers: object) -> list[McpServerSpec]:
    """Reduce an ``mcpServers`` map to name-and-transport specs, dropping all values."""
    return [
        McpServerSpec(name=name, transport=classify_transport(config))
        for name, config in _as_dict(servers).items()
    ]


def parse_mcp_servers(text: str) -> list[McpServerSpec]:
    """Parse a plugin's ``.mcp.json`` into name-and-transport specs.

    Args:
        text: The contents of a plugin ``.mcp.json``.

    Returns:
        One spec per declared server, in declaration order; empty when the file
        declares none or cannot be parsed.
    """
    return _servers_from_map(_as_dict(_load_json(text)).get("mcpServers"))


def parse_auth_cache(text: str) -> set[str]:
    """Parse ``mcp-needs-auth-cache.json`` into the set of server keys needing auth.

    Args:
        text: The contents of ``mcp-needs-auth-cache.json``.

    Returns:
        The recorded keys; empty when the file is absent or cannot be parsed. Only
        the keys are read, never the cached timestamps or ids.
    """
    return set(_as_dict(_load_json(text)).keys())


def parse_user_config_mcp(text: str) -> tuple[list[McpServerSpec], list[McpServerSpec]]:
    """Read only the MCP server subset of the Claude user config.

    The narrow read: the top-level ``mcpServers`` map becomes the user servers, and
    each project's own ``mcpServers`` becomes the project servers (de-duplicated by
    name in project order). Nothing else in the config is inspected, so account,
    machine, and telemetry fields are never touched, and because each server is
    reduced to a name and a transport, a token in a server's own config never
    leaves this function.

    Args:
        text: The contents of ``~/.claude.json``.

    Returns:
        The ``(user_servers, project_servers)`` pair; both empty when the config
        declares none or cannot be parsed.
    """
    data = _as_dict(_load_json(text))
    user_servers = _servers_from_map(data.get("mcpServers"))

    project_servers: list[McpServerSpec] = []
    seen: set[str] = set()
    for project in _as_dict(data.get("projects")).values():
        for spec in _servers_from_map(_as_dict(project).get("mcpServers")):
            if spec.name in seen:
                continue
            seen.add(spec.name)
            project_servers.append(spec)
    return user_servers, project_servers


def _plugin_auth_key(plugin_name: str, server_name: str) -> str:
    """The auth-cache key a plugin server is recorded under: ``plugin:<plugin>:<server>``."""
    return f"plugin:{plugin_name}:{server_name}"


def _collect_skills(
    machine: Machine,
    home: Path,
    plugins: Sequence[InstalledPlugin],
    enabled: dict[str, bool],
) -> list[Skill]:
    """Discover user skills and each plugin's skills, each with its Origin.

    User skills live under ``~/.claude/skills``; a plugin's skills live under its
    install path's ``skills`` directory. A skill is a directory holding a
    ``SKILL.md``. A user skill is always enabled; a plugin skill mirrors its
    plugin's enabled state, so an installed-but-disabled skill is still shown.
    """
    skills: list[Skill] = []
    skills_root = home / _CLAUDE_DIR / _SKILLS_DIR
    skills.extend(_skills_under(machine, skills_root, origin=_ORIGIN_USER, enabled=True))

    for plugin in plugins:
        if plugin.install_path is None:
            continue
        plugin_skills_root = Path(plugin.install_path) / _SKILLS_DIR
        skills.extend(
            _skills_under(
                machine,
                plugin_skills_root,
                origin=plugin.key,
                enabled=enabled.get(plugin.key, False),
            )
        )
    return skills


def _skills_under(
    machine: Machine, root: Path, *, origin: str, enabled: bool, _depth: int = 0
) -> list[Skill]:
    """List every skill under ``root``, recursing through grouping folders.

    A skill is any directory holding a ``SKILL.md``. The holder is recognised by
    that file rather than by ``is_dir``, so a user skill symlinked in from another
    repo, which the seam reports as a non-directory to stay loop-safe, is still
    found. A child with no ``SKILL.md`` of its own is treated as a grouping folder
    (some plugins file skills by category) and descended into, but only when it is
    a real directory, so a symlink is never followed into a loop; ``_depth`` caps
    the descent as a backstop. Hidden entries are skipped so a dotfile directory is
    never mistaken for a skill tree.
    """
    skills: list[Skill] = []
    for entry in machine.list_dir(root):
        if entry.name.startswith("."):
            continue
        child = root / entry.name
        text = machine.read_file(child / _SKILL_FILE)
        if text is not None:
            parsed_name, description = parse_skill_frontmatter(text)
            skills.append(
                Skill(
                    name=parsed_name or entry.name,
                    origin=origin,
                    description=description,
                    enabled=enabled,
                )
            )
        elif entry.is_dir and _depth < _SKILLS_MAX_DEPTH:
            skills.extend(
                _skills_under(machine, child, origin=origin, enabled=enabled, _depth=_depth + 1)
            )
    return skills


def _collect_plugins(
    plugins: Sequence[InstalledPlugin],
    marketplaces: dict[str, str | None],
    enabled: dict[str, bool],
    home: Path,
) -> list[Plugin]:
    """Join each installed plugin with its marketplace repo and enabled state."""
    return [
        Plugin(
            name=plugin.name,
            marketplace=plugin.marketplace,
            repo=marketplaces.get(plugin.marketplace),
            version=plugin.version,
            enabled=enabled.get(plugin.key, False),
            install_path=relativise(Path(plugin.install_path), home)
            if plugin.install_path
            else None,
        )
        for plugin in plugins
    ]


def _collect_mcp_servers(
    machine: Machine,
    home: Path,
    plugins: Sequence[InstalledPlugin],
    auth_keys: set[str],
) -> list[McpServer]:
    """Assemble MCP servers from each plugin and from the narrow user-config read.

    Plugin servers come from each plugin's ``.mcp.json`` and are auth-checked under
    the ``plugin:<plugin>:<server>`` key; user and project servers come from the
    narrow read of ``~/.claude.json`` and are auth-checked under their bare name.
    """
    servers: list[McpServer] = []

    for plugin in plugins:
        if plugin.install_path is None:
            continue
        text = machine.read_file(Path(plugin.install_path) / _PLUGIN_MCP)
        if text is None:
            continue
        for spec in parse_mcp_servers(text):
            servers.append(
                McpServer(
                    name=spec.name,
                    origin=plugin.key,
                    transport=spec.transport,
                    needs_auth=_plugin_auth_key(plugin.name, spec.name) in auth_keys,
                )
            )

    config_text = machine.read_file(home / _USER_CONFIG)
    if config_text is not None:
        user_servers, project_servers = parse_user_config_mcp(config_text)
        for spec in user_servers:
            servers.append(
                McpServer(
                    name=spec.name,
                    origin=_ORIGIN_USER,
                    transport=spec.transport,
                    needs_auth=spec.name in auth_keys,
                )
            )
        for spec in project_servers:
            servers.append(
                McpServer(
                    name=spec.name,
                    origin=_ORIGIN_PROJECT,
                    transport=spec.transport,
                    needs_auth=spec.name in auth_keys,
                )
            )

    return servers


def collect_claude(machine: Machine, *, home: Path) -> ClaudeSection:
    """Collect the claude Section: skills, plugins, and MCP servers with Origins.

    A pure Collector over the seam. Every manifest, front-matter file, and the
    Claude user config is read through ``machine``, so the whole Section is
    exercised in tests against a fake. The user config is read narrowly (only the
    MCP server subset) and no MCP server carries its command, URL, headers, or
    environment, so nothing sensitive reaches the board. No judgement is applied:
    a disabled plugin or a server needing auth is left as a plain fact for the M6
    Flag layer to interpret.

    Args:
        machine: The seam every read runs through.
        home: Home directory, for locating the Claude config and relativising
            install paths.

    Returns:
        The Section model: skills, plugins, and MCP servers, each with its Origin.
    """
    plugins_dir = home / _CLAUDE_DIR / _PLUGINS_DIR

    installed_text = machine.read_file(plugins_dir / _INSTALLED_PLUGINS)
    installed = parse_installed_plugins(installed_text) if installed_text else []

    marketplaces_text = machine.read_file(plugins_dir / _KNOWN_MARKETPLACES)
    marketplaces = parse_known_marketplaces(marketplaces_text) if marketplaces_text else {}

    enabled: dict[str, bool] = {}
    for settings_name in (_SETTINGS, _SETTINGS_LOCAL):
        settings_text = machine.read_file(home / _CLAUDE_DIR / settings_name)
        if settings_text is not None:
            enabled.update(parse_enabled_plugins(settings_text))

    auth_text = machine.read_file(home / _CLAUDE_DIR / _AUTH_CACHE)
    auth_keys = parse_auth_cache(auth_text) if auth_text else set()

    return ClaudeSection(
        skills=_collect_skills(machine, home, installed, enabled),
        plugins=_collect_plugins(installed, marketplaces, enabled, home),
        mcp_servers=_collect_mcp_servers(machine, home, installed, auth_keys),
    )
