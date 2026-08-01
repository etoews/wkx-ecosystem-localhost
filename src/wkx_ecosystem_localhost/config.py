"""Typed configuration built once at the entry point and passed down explicitly.

Machine-specific values (scan roots) come from the environment or .env; the
defaults are computed at runtime, never literal paths, so the public repo stays
machine-neutral. The bind host is deliberately absent: the board is
loopback-only as a security property, not a setting.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_scan_roots() -> list[Path]:
    """Compute the default repo scan roots at runtime."""
    return [Path.home() / "dev"]


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
