"""Typed configuration built once at the entry point and passed down explicitly.

Machine-specific values (scan roots, the system-tools probe) come from a TOML
file, the environment, or ``.env``; the defaults are computed at runtime, never
literal paths, so the public repo stays machine-neutral. The bind host is
deliberately absent: the board is loopback-only as a security property, not a
setting.

Configuration and secrets are split, which diverges from
``standards/python/standards/configuration.md`` until that standard changes.
Configuration lives in ``wkx-ecosystem-localhost.toml`` (flat keys, one to one
onto the fields below); ``.env`` is reserved for ``SecretStr`` values, of which
there are none yet. Precedence, highest first: explicit arguments, the
environment, ``.env``, the TOML file, then the computed defaults.
"""

from __future__ import annotations

import logging
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from wkx_ecosystem_localhost.exceptions import ConfigError
from wkx_ecosystem_localhost.models import Section
from wkx_ecosystem_localhost.redaction import relativise

logger = logging.getLogger(__name__)

# The one env prefix for this board's own variables. Named for the repo so it
# never collides with the wider wkx-* environment.
ENV_PREFIX = "WKX_ECO_LOCAL_"

# The prefix these variables used before the WKX_ECO_LOCAL_ rename. A leftover
# variable under it that names a real field (e.g. WKX_ECO_PORT) is caught at
# startup instead of silently reverting the field to its default.
LEGACY_ENV_PREFIX = "WKX_ECO_"

# Env-only override for the configuration file path. Deliberately not a Settings
# field: it names the file the fields are read from, so it cannot itself be read
# from that file, and it is exempt from the unknown-variable scan.
CONFIG_FILE_ENV = f"{ENV_PREFIX}CONFIG_FILE"

# The configuration file, read from the working directory (the repo root for both
# the launchd instance and ``uv run``). Gitignored; a machine keeps its own.
DEFAULT_CONFIG_FILE = Path("wkx-ecosystem-localhost.toml")

# The provenance labels a /api/config value can carry, most-specific first.
Source = Literal["default", "file", "env"]


class _Unset:
    """Sentinel type distinguishing an unsupplied argument from an explicit None."""


_UNSET = _Unset()


def resolve_config_file(
    environ: Mapping[str, str], override: Path | str | _Unset | None = _UNSET
) -> Path | None:
    """Resolve which TOML file the configuration is read from.

    Args:
        environ: The environment to read the path override from.
        override: An explicit choice. ``_UNSET`` (the default) resolves the path
            from ``WKX_ECO_LOCAL_CONFIG_FILE`` or falls back to the default file
            in the working directory. ``None`` opts the file source out entirely,
            the way ``_env_file=None`` opts out of ``.env``; the suite passes it so
            it never reads a real file. An explicit path is used verbatim.

    Returns:
        The path to read, or None when the file source is opted out.
    """
    if isinstance(override, _Unset):
        raw = environ.get(CONFIG_FILE_ENV)
        return Path(raw).expanduser() if raw else DEFAULT_CONFIG_FILE
    if override is None:
        return None
    return Path(override).expanduser()


def _default_scan_roots() -> list[Path]:
    """Compute the default repo scan roots at runtime."""
    return [Path.home() / "dev"]


class ToolSpec(BaseModel):
    """One developer CLI the system Collector probes for presence and version.

    ``name`` is the program to run (also its board label). ``version_args`` is how
    the tool is asked its version; it defaults to ``--version``, which every tool in
    the generic default list understands, and can be overridden per tool for one
    that reports its version some other way. Because the whole list is typed
    configuration, a machine extends the probe by naming more tools in the
    configuration, never by editing code.
    """

    name: str
    version_args: tuple[str, ...] = ("--version",)

    def argv(self) -> tuple[str, ...]:
        """The fixed argument list to run for this tool's version."""
        return (self.name, *self.version_args)


# The generic default probe: the developer CLIs common to this kind of machine.
# A literal list of names, not machine-specific paths, so the default stays
# machine-neutral; a machine adds to it through configuration, never in code.
_DEFAULT_SYSTEM_TOOL_NAMES = (
    "git",
    "gh",
    "uv",
    "ruff",
    "ty",
    "pre-commit",
    "docker",
    "terraform",
    "aws",
    "code",
    "node",
)


def _default_system_tools() -> list[ToolSpec]:
    """Compute the default system-tools probe list at runtime."""
    return [ToolSpec(name=name) for name in _DEFAULT_SYSTEM_TOOL_NAMES]


class MuteRule(BaseModel):
    """One Mute: a Flag Category to drop from the badges and the tally.

    ``category`` names the Category to suppress and must be one of the board's known
    Categories (``flags.CATEGORIES``); an unknown one fails fast at startup, so a
    typo mutes nothing silently. ``target`` narrows the Mute to a single item by its
    exact wire value — a repo's ``~``-relative path, ``formula:python@3.12``,
    ``skill:foo`` — matched verbatim against ``Flag.target``; when it is None the
    Mute drops the whole Category, including the two the board raises from SSE. A
    Mute suppresses noise, it never states what the machine should look like, so it
    is a view preference, not a ruleset (CONTEXT.md). Muting is applied client-side:
    ``/api/config`` carries the rules and ``/api/flags`` still reports every Flag.

    ``extra="forbid"`` so a misspelt key fails fast rather than being dropped: a
    typo'd ``targett`` would otherwise leave ``target`` None and silently widen the
    rule from one item to the whole Category, the same fail-fast posture the rest of
    the configuration keeps.
    """

    model_config = ConfigDict(extra="forbid")

    category: str
    target: str | None = None


class Settings(BaseSettings):
    """Configuration from the TOML file, the environment, and ``.env``.

    Built once in the CLI entry point; pass the instance down explicitly. Never
    re-read the environment deeper in the stack. Pass ``_config_file=None`` to opt
    out of the TOML source (tests do, so the suite never reads a real file); pass a
    path to read a specific file.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        extra="forbid",
    )

    scan_roots: list[Path] = Field(default_factory=_default_scan_roots)
    scan_depth: int = 8
    port: int = 8787

    # The developer CLIs the system Section probes. A generic default a machine
    # extends through configuration (a [[system_tools]] table in the TOML, or
    # WKX_ECO_LOCAL_SYSTEM_TOOLS as a JSON list), so a new tool changes the probe
    # with no code change.
    system_tools: list[ToolSpec] = Field(default_factory=_default_system_tools)

    # The Sections switched off. An Off Section is not collected, its route is not
    # registered, and it raises no Flags; the client removes its panel before any
    # fetch fires. Typed by the Section enum, so an unknown name fails fast the way
    # extra="forbid" rejects an unknown key. Needs attention is not a Section and so
    # can never appear here.
    sections_off: list[Section] = Field(default_factory=list)

    # Background-fetch pool: how many repos are fetched at once, and the
    # per-fetch wall-clock ceiling. Bounded so the one write the board performs
    # can never swamp the machine or hang on an unreachable remote.
    fetch_workers: int = 4
    fetch_timeout: float = 10.0

    # How long, in seconds, a computed footprint Section is served from cache
    # before it is recomputed. The footprint probe walks whole directory trees
    # with ``du``, so it is run synchronously behind this cache rather than on
    # every request.
    footprint_cache_ttl: float = 60.0

    # How long, in seconds, one repo discovery walk is shared before the roots are
    # walked again. Every board load asks several routes and the Flag layer for the
    # repos under the scan roots; without this cache each re-walks the trees, and
    # the per-directory Exclude matching makes that walk costlier still. Mirrors
    # footprint_cache_ttl: the roots are walked once and the result served from
    # cache for the rest of the window.
    discovery_cache_ttl: float = 60.0

    # Discovery Excludes: globs matched with ``PurePath.full_match`` against the
    # ``~``-relative path the board displays. A matching directory is pruned from
    # discovery, so an excluded subtree is never descended and none of its repos is
    # reported. An excluded repo is absent from the board and raises no Flags
    # (Exclude, not a Mute). Set in the TOML (``exclude = [...]``) or as
    # WKX_ECO_LOCAL_EXCLUDE (a JSON list); the built-in prunes stay built-in.
    exclude: list[str] = Field(default_factory=list)

    # Muted Categories: a client-side view preference the board carries on
    # /api/config. Each rule names a Flag Category, optionally narrowed to one item
    # by its exact wire target; the client drops a matching Flag before it badges a
    # row or counts in the tally, and reports how many it muted. /api/flags still
    # reports every Flag: the API is the inventory. Set in the TOML as an inline
    # array (mute = [ { category = "brew-outdated" } ]) or as WKX_ECO_LOCAL_MUTE (a
    # JSON list). An unknown category fails fast against flags.CATEGORIES.
    mute: list[MuteRule] = Field(default_factory=list)

    @field_validator("scan_roots", mode="after")
    @classmethod
    def _expand_scan_roots(cls, roots: list[Path]) -> list[Path]:
        """Expand a leading ``~`` in each scan root, from the TOML or the environment."""
        return [root.expanduser() for root in roots]

    @field_validator("sections_off", mode="after")
    @classmethod
    def _config_is_never_off(cls, sections: list[Section]) -> list[Section]:
        """Reject ``config`` in ``sections_off``: the config Section cannot be Off.

        ``/api/config`` is the board's own effective-configuration view, which the
        client boots from to learn what is Off in the first place, so it is served
        unconditionally. Turning it Off would leave that route up while the panel
        vanished, a half-off state CONTEXT.md's Off rules out. Like needs attention,
        the config Section can be Hidden from the ``sections`` menu, but never Off.

        Raises:
            ValueError: If ``config`` appears in ``sections_off``.
        """
        if Section.CONFIG in sections:
            raise ValueError(
                "config cannot be switched off: it is the board's own "
                "effective-configuration view and the client boots from it. "
                "Hide it from the sections menu instead."
            )
        return sections

    @field_validator("mute", mode="after")
    @classmethod
    def _mute_categories_are_known(cls, rules: list[MuteRule]) -> list[MuteRule]:
        """Reject a Mute naming a Category the board never raises.

        Each rule's ``category`` must be one of the board's known Flag Categories
        (``flags.CATEGORIES``), so a typo such as ``brew-outdate`` fails fast at
        startup — the way ``extra="forbid"`` rejects an unknown key — rather than
        silently muting nothing. ``CATEGORIES`` is imported inside the validator
        because ``flags`` imports this module; the local import keeps that from
        being a circular import at load time.

        Raises:
            ValueError: If any rule names a Category not in the registry, naming each.
        """
        from wkx_ecosystem_localhost.collectors.flags import CATEGORIES

        unknown = sorted({rule.category for rule in rules if rule.category not in CATEGORIES})
        if unknown:
            joined = ", ".join(unknown)
            raise ValueError(
                f"unknown mute category/categories: {joined}. Each must name a Flag "
                "Category the board raises; check for a typo."
            )
        return rules

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Wire the TOML source in and fix the precedence.

        Highest priority first: explicit arguments, the environment, ``.env``, the
        TOML file, then the computed defaults. The env-only ``_config_file`` init
        argument selects the file (or opts the source out with ``None``); it is
        popped here so it never reaches validation under ``extra="forbid"``.
        """
        init_kwargs = getattr(init_settings, "init_kwargs", {})
        override = init_kwargs.pop("_config_file", _UNSET)
        config_file = resolve_config_file(os.environ, override)
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        if config_file is not None:
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=config_file))
        return tuple(sources)


def _known_env_names() -> set[str]:
    """The full set of ``WKX_ECO_LOCAL_*`` variable names the board understands."""
    names = {f"{ENV_PREFIX}{field.upper()}" for field in Settings.model_fields}
    names.add(CONFIG_FILE_ENV)
    return names


def check_environment(environ: Mapping[str, str] | None = None) -> None:
    """Fail fast on a stray ``WKX_ECO_LOCAL_*`` variable, or a leftover ``WKX_ECO_*``.

    ``pydantic-settings`` reads declared fields only, so a misspelt variable such as
    ``WKX_ECO_LOCAL_PROT`` is silently ignored, and a variable still under the old
    ``WKX_ECO_`` prefix (from before the rename) is ignored the same way. This scan
    closes both gaps: it names every ``WKX_ECO_LOCAL_*`` variable that matches no
    field, and every leftover ``WKX_ECO_*`` variable whose name is a field under the
    old prefix, and refuses to start — the fail-fast posture ``extra="forbid"`` gives
    the TOML.

    Args:
        environ: The environment to scan. Defaults to the process environment.

    Raises:
        ConfigError: If a ``WKX_ECO_LOCAL_*`` variable matches no field, or a
            ``WKX_ECO_*`` variable names a field under the old prefix, naming each.
    """
    env = os.environ if environ is None else environ
    known = _known_env_names()
    unknown = sorted(
        name for name in env if name.upper().startswith(ENV_PREFIX) and name.upper() not in known
    )
    if unknown:
        joined = ", ".join(unknown)
        logger.error("unknown %s environment variable(s): %s", ENV_PREFIX, joined)
        raise ConfigError(
            f"unknown {ENV_PREFIX} environment variable(s): {joined}. "
            "Each must match a configuration field; check for a typo."
        )

    field_names = {field.upper() for field in Settings.model_fields}
    legacy = sorted(
        name
        for name in env
        if name.upper().startswith(LEGACY_ENV_PREFIX)
        and not name.upper().startswith(ENV_PREFIX)
        and name.upper().removeprefix(LEGACY_ENV_PREFIX) in field_names
    )
    if legacy:
        joined = ", ".join(legacy)
        logger.error("legacy %s environment variable(s): %s", LEGACY_ENV_PREFIX, joined)
        raise ConfigError(
            f"{joined} use the old {LEGACY_ENV_PREFIX} prefix; the board now reads "
            f"{ENV_PREFIX}* — rename, for example, {LEGACY_ENV_PREFIX}PORT to {ENV_PREFIX}PORT."
        )


class ConfigItem(BaseModel):
    """One scalar setting's effective value with where it came from.

    ``value`` is already display-ready: paths are relativised to ``~`` so no
    username leaks. ``source`` is the layer the value won on: ``default`` for a
    computed default, ``file`` for the TOML, ``env`` for the environment.
    """

    key: str
    value: str
    source: Source


class ConfigToolList(BaseModel):
    """The system-tools probe list as effective configuration, rendered as a table.

    ``source`` is where the whole list came from (a default list, the TOML, or the
    environment); ``tools`` is the effective list in order. ``exclude``,
    ``sections_off``, and ``mute`` sit beside this block, each its own typed block
    and table, without disturbing this one.
    """

    source: Source
    tools: list[ToolSpec]


class ConfigExcludes(BaseModel):
    """The discovery Exclude globs as effective configuration, rendered as a table.

    ``source`` is where the whole list came from (the empty default, the TOML, or the
    environment); ``globs`` is the effective list in order. Each glob prunes every
    directory whose ``~``-relative path it full-matches from discovery, so an
    excluded subtree is absent from the board and raises no Flags (Exclude, not a
    Mute). Sits beside ``system_tools`` as its own typed block, the pattern
    ``sections_off`` and ``mute`` follow.
    """

    source: Source
    globs: list[str]


class ConfigSectionsOff(BaseModel):
    """The Off Sections as effective configuration, rendered as its own table.

    Another list-shaped setting following ``system_tools`` into its own typed block,
    per the pattern A set. ``source`` is where the list came from (an empty default,
    the TOML, or the environment); ``sections`` is the effective list of Sections
    switched off, so the config Section can name exactly which panels the board
    dropped.
    """

    source: Source
    sections: list[Section]


class ConfigMutes(BaseModel):
    """The Mute rules as effective configuration, rendered as its own table.

    The list-shaped setting following ``system_tools`` into its own typed block, the
    pattern A set. ``source`` is where the list came from (an empty default, the
    TOML, or the environment); ``rules`` is the effective Mute rules in order, each a
    Category and an optional exact target. Muting is a client-side view preference:
    the board lists the rules here, and the client drops the muted Flags before they
    badge a row or count in the tally, but ``/api/flags`` still reports every Flag.
    """

    source: Source
    rules: list[MuteRule]


class ConfigView(BaseModel):
    """The read-only effective configuration for the config Section.

    A view, never a write path: the board reports its configuration and shows where
    each value came from, but never changes it. ``file`` is the ``~``-relative path
    of the TOML the values were read from, or None when the file source is off;
    ``found`` is whether that file exists. ``values`` are the scalar settings;
    ``system_tools`` is the probe list, ``exclude`` is the discovery Exclude globs,
    ``sections_off`` is the Off Sections, and ``mute`` is the Mute rules. Each
    list-shaped setting gets its own typed block beside ``system_tools`` so the
    Section grows one table at a time.
    """

    file: str | None
    found: bool
    values: list[ConfigItem]
    system_tools: ConfigToolList
    exclude: ConfigExcludes
    sections_off: ConfigSectionsOff
    mute: ConfigMutes


# The scalar settings shown in the config Section's Settings table, in a stable
# reading order. system_tools is a list and gets its own table, so it is not here.
_SCALAR_FIELDS: tuple[str, ...] = (
    "scan_roots",
    "scan_depth",
    "port",
    "fetch_workers",
    "fetch_timeout",
    "footprint_cache_ttl",
    "discovery_cache_ttl",
)


def _source_of(field: str, toml_keys: set[str], environ: Mapping[str, str]) -> Source:
    """Decide which layer a field's effective value came from.

    Environment beats the file, matching the build precedence. ``.env`` carries no
    non-secret field today, so it is folded into ``env`` for display.
    """
    env_name = f"{ENV_PREFIX}{field.upper()}"
    if any(name.upper() == env_name for name in environ):
        return "env"
    if field in toml_keys:
        return "file"
    return "default"


def _render(field: str, value: object, home: Path) -> str:
    """Render a field's value display-ready, relativising any path to ``~``."""
    if field == "scan_roots" and isinstance(value, list):
        return ", ".join(relativise(root, home) for root in value if isinstance(root, Path))
    return str(value)


def describe(
    settings: Settings,
    *,
    home: Path,
    config_file: Path | None,
    environ: Mapping[str, str],
) -> ConfigView:
    """Build the read-only effective-configuration view for ``GET /api/config``.

    Reads the TOML once more to learn which keys the operator actually set (so a
    value can be tagged ``file``); a missing or opted-out file simply yields no
    keys, so every value reads ``default`` or ``env``.

    Args:
        settings: The built configuration.
        home: Home directory, to relativise displayed paths to ``~``.
        config_file: The TOML path the settings were read from, or None when the
            file source is off (the suite passes None so it never reads a real file).
        environ: The environment, to tag values that came from it.

    Returns:
        The effective configuration with every value tagged by its source.
    """
    found = config_file is not None and config_file.is_file()
    toml_keys: set[str] = set()
    if found and config_file is not None:
        try:
            with config_file.open("rb") as handle:
                toml_keys = set(tomllib.load(handle))
        except OSError, tomllib.TOMLDecodeError:
            # A file that cannot be read could not have built these settings; treat
            # it as contributing no keys rather than failing the view.
            toml_keys = set()
    values = [
        ConfigItem(
            key=field,
            value=_render(field, getattr(settings, field), home),
            source=_source_of(field, toml_keys, environ),
        )
        for field in _SCALAR_FIELDS
    ]
    tools = ConfigToolList(
        source=_source_of("system_tools", toml_keys, environ),
        tools=settings.system_tools,
    )
    excludes = ConfigExcludes(
        source=_source_of("exclude", toml_keys, environ),
        globs=settings.exclude,
    )
    sections_off = ConfigSectionsOff(
        source=_source_of("sections_off", toml_keys, environ),
        sections=settings.sections_off,
    )
    mutes = ConfigMutes(
        source=_source_of("mute", toml_keys, environ),
        rules=settings.mute,
    )
    file_display = relativise(config_file, home) if config_file is not None else None
    return ConfigView(
        file=file_display,
        found=found,
        values=values,
        system_tools=tools,
        exclude=excludes,
        sections_off=sections_off,
        mute=mutes,
    )
