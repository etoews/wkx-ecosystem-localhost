"""The suite's Settings builder.

``Settings`` takes a custom ``_config_file`` init kwarg (popped in
``settings_customise_sources``) that the type checker cannot see on the model's
generated ``__init__``, so the one ignore for it lives here rather than at every
call site. Both file sources are opted out by default (``.env`` and the TOML), so
a test reads nothing real; pass ``config_file`` to read a specific file, or
``env_file`` for the rare ``.env`` test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wkx_ecosystem_localhost.config import Settings


def make_settings(
    *,
    env_file: Path | str | None = None,
    config_file: Path | str | None = None,
    **overrides: Any,
) -> Settings:
    """Build ``Settings`` for the suite with both file sources opted out by default.

    ``overrides`` are Settings field values (and, in a few tests, a deliberately
    invalid one to prove ``extra="forbid"`` rejects it), so they are typed ``Any``:
    each is validated at runtime by pydantic, not by the type checker.
    """
    return Settings(_env_file=env_file, _config_file=config_file, **overrides)  # ty: ignore[unknown-argument]
