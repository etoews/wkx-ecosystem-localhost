"""Typed configuration built once at the entry point and passed down explicitly.

Machine-specific values (scan roots) come from the environment or .env; the
defaults are computed at runtime, never literal paths, so the public repo stays
machine-neutral. The bind host is deliberately absent: the board is
loopback-only as a security property, not a setting.
"""

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    environment, never by editing code.
    """

    name: str
    version_args: tuple[str, ...] = ("--version",)

    def argv(self) -> tuple[str, ...]:
        """The fixed argument list to run for this tool's version."""
        return (self.name, *self.version_args)


# The generic default probe: the developer CLIs common to this kind of machine.
# A literal list of names, not machine-specific paths, so the default stays
# machine-neutral; a machine adds to it through the environment, never in code.
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


class Settings(BaseSettings):
    """Configuration from the environment and .env.

    Built once in the CLI entry point; pass the instance down explicitly.
    Never re-read the environment deeper in the stack.
    """

    model_config = SettingsConfigDict(
        env_prefix="WKX_ECO_",
        env_file=".env",
        extra="forbid",
    )

    scan_roots: list[Path] = Field(default_factory=_default_scan_roots)
    scan_depth: int = 8
    port: int = 8787

    # The developer CLIs the system Section probes. A generic default a machine
    # extends through the environment (WKX_ECO_SYSTEM_TOOLS as a JSON list), so a
    # new tool changes the probe with no code change.
    system_tools: list[ToolSpec] = Field(default_factory=_default_system_tools)

    # Background-fetch pool: how many repos are fetched at once, and the
    # per-fetch wall-clock ceiling. Bounded so the one write the board performs
    # can never swamp the machine or hang on an unreachable remote.
    fetch_workers: int = 4
    fetch_timeout: float = 10.0
