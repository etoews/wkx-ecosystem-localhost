"""The View: how the operator arranges the board, in a file the board owns.

The View (CONTEXT.md) is the theme, the Hidden and Collapsed panels, and the
Mutes. Unlike the configuration, which the operator writes and the board reads
once at startup, the View is the board's own file: written on every change
through ``PATCH /api/view``, read live on every request, and created on first
write. It holds overrides only — a preference back at its default is dropped — so
a fresh board writes nothing and the file holds only what the operator changed.

Reading is lenient (drop-and-warn): a View that names a panel or Category the
board does not know keeps the rest and records the unknown key, because the board
must never refuse to start on a file it wrote itself. The configuration keeps its
fail-fast posture (``config.py``); only the View is live-read and forgiving.

Writing is serialised and atomic: one preference per call, merged under a
process-level lock, written to a temporary file and then renamed into place, and
refused outright when the file already on disk does not parse. The board never
regenerates the file from memory (ADR 0004).
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import tomlkit
from pydantic import BaseModel, ConfigDict
from tomlkit.exceptions import TOMLKitError

from wkx_ecosystem_localhost.config import _UNSET, ENV_PREFIX, _Unset
from wkx_ecosystem_localhost.exceptions import (
    InvalidPreference,
    ViewParseError,
    ViewWriteError,
)
from wkx_ecosystem_localhost.models import Section

logger = logging.getLogger(__name__)

# Env-only override for the View-file path, the way WKX_ECO_LOCAL_CONFIG_FILE
# overrides the configuration path. Not a Settings field: it names a file the
# board owns, read outside the pydantic-settings precedence entirely.
VIEW_FILE_ENV = f"{ENV_PREFIX}VIEW_FILE"

# The View file, beside the configuration in the working directory (the repo root
# for both the launchd instance and ``uv run``). Gitignored; the board writes it.
DEFAULT_VIEW_FILE = Path("wkx-ecosystem-localhost.view.toml")

# The two explicit themes. An absent theme is auto (the system preference), so it
# is never written to the file.
THEMES: frozenset[str] = frozenset({"light", "dark"})

# Every panel the View may name: the ten Sections plus ``summary`` (Needs
# attention). ``summary`` is not a Section (it can never be Off) but it can be
# Hidden or Collapsed, so it is a valid panel id here.
PANEL_IDS: frozenset[str] = frozenset({"summary"} | {section.value for section in Section})

# The header the board writes at the top of the file, so a reader knows the board
# owns it and hand edits are picked up on the next refresh.
_HEADER = (
    "WKX Ecosystem localhost View.",
    "",
    "The board writes this file; it is the operator's arrangement of the board",
    "(theme, Hidden and Collapsed panels, Mutes), not its configuration. It holds",
    "overrides only. A hand edit is picked up on the next refresh, with no",
    "restart. Delete the file to reset the board to its defaults.",
)


def _known_categories() -> frozenset[str]:
    """The Flag Categories a Mute may name, imported lazily to avoid a cycle.

    ``flags`` imports ``config``; importing it here at module load would risk an
    import cycle, so the registry is read on demand, exactly as ``config`` reads it
    inside its Mute validator.
    """
    from wkx_ecosystem_localhost.collectors.flags import CATEGORIES

    return CATEGORIES


class MuteRule(BaseModel):
    """One Mute: a Flag Category to drop from the badges and the Needs attention tally.

    ``category`` names the Category to suppress; ``target`` narrows the Mute to a
    single item by its exact wire value (a repo's ``~``-relative path,
    ``formula:python@3.12``, ``skill:foo``), or is None to drop the whole Category.
    A Mute is part of the View (ADR 0003, ADR 0004); ``/api/flags`` still reports
    every Flag, and the client drops a muted one at one choke point.

    ``extra="forbid"`` so a misspelt key is caught rather than silently widening the
    rule; a rule that fails to validate is dropped-and-warned when the View is read.
    """

    model_config = ConfigDict(extra="forbid")

    category: str
    target: str | None = None


class View(BaseModel):
    """The effective View: the operator's overrides, defaults omitted.

    ``theme`` is ``light`` or ``dark``, or None for auto (the system preference).
    ``sections_hidden`` and ``sections_collapsed`` are panel ids (a Section value or
    ``summary``). ``mute`` is the Mute rules. Every field holds overrides only, so
    an empty View is a board at its defaults.
    """

    theme: Literal["light", "dark"] | None = None
    sections_hidden: list[str] = []
    sections_collapsed: list[str] = []
    mute: list[MuteRule] = []


class ViewState(BaseModel):
    """A read of the View file: the effective View plus what reading it revealed.

    ``view`` is the effective View with every unknown key already dropped.
    ``unknown_keys`` names each dropped key (an unknown panel id, an unknown Mute
    Category, a malformed rule, an unknown theme), so the config Section can raise
    ``view-unknown-key``. ``file`` is the ``~``-relative path, or None when no View
    file is configured; ``found`` is whether it exists; ``writable`` is whether the
    board could write it (the file, or its directory when the file is absent).
    """

    view: View
    unknown_keys: list[str] = []
    file: str | None = None
    found: bool = False
    writable: bool = False


class ViewPayload(BaseModel):
    """The flattened effective View plus its file state, the shape ``/api/view`` serves.

    The board applies ``theme``, ``sections_hidden``, ``sections_collapsed``, and
    ``mute``; the config Section reads ``file``, ``found``, and ``writable`` for its
    View-file line, and ``unknown_keys`` for the ``view-unknown-key`` Flag. A
    successful ``PATCH`` returns the same shape, and the same shape is pushed over
    the convergence stream so every tab applies one contract.
    """

    theme: Literal["light", "dark"] | None
    sections_hidden: list[str]
    sections_collapsed: list[str]
    mute: list[MuteRule]
    file: str | None
    found: bool
    writable: bool
    unknown_keys: list[str]


def payload_of(state: ViewState) -> ViewPayload:
    """Flatten a read of the View file into the wire payload ``/api/view`` serves."""
    return ViewPayload(
        theme=state.view.theme,
        sections_hidden=state.view.sections_hidden,
        sections_collapsed=state.view.sections_collapsed,
        mute=state.view.mute,
        file=state.file,
        found=state.found,
        writable=state.writable,
        unknown_keys=state.unknown_keys,
    )


class ThemePreference(BaseModel):
    """A validated theme change: ``light``, ``dark``, or None (auto, which removes it)."""

    theme: Literal["light", "dark"] | None


class SectionPreference(BaseModel):
    """A validated Hidden or Collapsed change for one panel.

    ``field`` is ``sections_hidden`` or ``sections_collapsed``; ``panel`` is the
    panel id (validated against the catalogue at parse time); ``on`` adds the
    override when True and removes it when False (back to the visible/expanded
    default).
    """

    field: Literal["sections_hidden", "sections_collapsed"]
    panel: str
    on: bool


Preference = ThemePreference | SectionPreference


def resolve_view_file(
    environ: Mapping[str, str], override: Path | str | _Unset | None = _UNSET
) -> Path | None:
    """Resolve which file the View is read from and written to.

    Mirrors ``config.resolve_config_file``. ``_UNSET`` resolves the path from
    ``WKX_ECO_LOCAL_VIEW_FILE`` or the default file in the working directory;
    ``None`` opts out entirely (the suite passes None so it never touches a real
    file); an explicit path is used verbatim.

    Args:
        environ: The environment to read the path override from.
        override: An explicit choice, ``None`` to opt out, or ``_UNSET`` to resolve
            from the environment or the default.

    Returns:
        The path to read and write, or None when the View file is opted out.
    """
    if isinstance(override, _Unset):
        raw = environ.get(VIEW_FILE_ENV)
        return Path(raw).expanduser() if raw else DEFAULT_VIEW_FILE
    if override is None:
        return None
    return Path(override).expanduser()


def parse_preference(body: object) -> Preference:
    """Validate one PATCH body against the board's catalogue and return it typed.

    One preference per call. The body is ``{"field": "theme", "value": ...}`` with
    the value ``light``, ``dark``, or ``auto``; or ``{"field": "sections_hidden" |
    "sections_collapsed", "panel": <id>, "on": <bool>}``. The panel is checked
    against ``PANEL_IDS`` and the theme against ``THEMES`` here, so an unknown one
    is refused before it can reach the file.

    Args:
        body: The decoded JSON body of the PATCH request.

    Returns:
        The validated preference to merge.

    Raises:
        InvalidPreference: If the body is not a single known preference, or names a
            panel or theme the board does not know.
    """
    if not isinstance(body, Mapping):
        raise InvalidPreference("the request body must be a JSON object")
    field = body.get("field")
    if field == "theme":
        value = body.get("value")
        if value == "auto":
            return ThemePreference(theme=None)
        if value == "light":
            return ThemePreference(theme="light")
        if value == "dark":
            return ThemePreference(theme="dark")
        raise InvalidPreference(f"unknown theme: {value!r}; expected light, dark, or auto")
    if field == "sections_hidden":
        return _section_preference("sections_hidden", body)
    if field == "sections_collapsed":
        return _section_preference("sections_collapsed", body)
    raise InvalidPreference(f"unknown preference field: {field!r}")


def _section_preference(
    field: Literal["sections_hidden", "sections_collapsed"], body: Mapping[Any, object]
) -> SectionPreference:
    """Validate one Hidden/Collapsed PATCH body against the panel catalogue."""
    panel = body.get("panel")
    on = body.get("on")
    if not isinstance(panel, str) or panel not in PANEL_IDS:
        raise InvalidPreference(f"unknown panel id: {panel!r}")
    if not isinstance(on, bool):
        raise InvalidPreference("'on' must be a boolean")
    return SectionPreference(field=field, panel=panel, on=on)


def merge(current: View, preference: Preference) -> View:
    """Apply one preference to the current View, returning the new View.

    Overrides only: a preference back at its default is removed, not stored. Setting
    the theme to auto drops it; showing a Hidden panel or expanding a Collapsed one
    drops it from its list. The panel lists keep insertion order and never hold a
    duplicate.

    Args:
        current: The View read from disk.
        preference: The validated preference to apply.

    Returns:
        A new View with the preference merged in.
    """
    data = current.model_dump()
    if isinstance(preference, ThemePreference):
        data["theme"] = preference.theme
        return View.model_validate(data)
    panels: list[str] = list(data[preference.field])
    if preference.on:
        if preference.panel not in panels:
            panels.append(preference.panel)
    else:
        panels = [panel for panel in panels if panel != preference.panel]
    data[preference.field] = panels
    return View.model_validate(data)


def _view_from_data(data: Mapping[str, object]) -> tuple[View, list[str]]:
    """Build the effective View from parsed TOML, dropping unknown keys with a warning.

    Lenient by design: an unknown theme, an unknown panel id, an unknown Mute
    Category, or a malformed Mute rule is dropped and named in the returned list,
    never raised, so the board never refuses a file it wrote itself. Each dropped
    key is logged at WARNING.

    Args:
        data: The parsed TOML mapping.

    Returns:
        The effective View and the list of dropped, unknown keys.
    """
    unknown: list[str] = []
    theme: Literal["light", "dark"] | None = None
    raw_theme = data.get("theme")
    if raw_theme == "light":
        theme = "light"
    elif raw_theme == "dark":
        theme = "dark"
    elif raw_theme is not None and raw_theme != "auto":
        unknown.append(f"theme: {raw_theme!r}")
        logger.warning("dropping unknown View theme: %r", raw_theme)

    def _known_panels(field: str) -> list[str]:
        raw = data.get(field)
        kept: list[str] = []
        for panel in raw if isinstance(raw, list) else []:
            if isinstance(panel, str) and panel in PANEL_IDS:
                if panel not in kept:
                    kept.append(panel)
            else:
                unknown.append(f"{field}: {panel!r}")
                logger.warning("dropping unknown View panel id in %s: %r", field, panel)
        return kept

    categories = _known_categories()
    raw_mute = data.get("mute")
    mute: list[MuteRule] = []
    for entry in raw_mute if isinstance(raw_mute, list) else []:
        if not isinstance(entry, Mapping):
            unknown.append(f"mute: {entry!r}")
            logger.warning("dropping malformed View mute rule: %r", entry)
            continue
        try:
            rule = MuteRule.model_validate(dict(entry))
        except ValueError:
            unknown.append(f"mute rule: {dict(entry)!r}")
            logger.warning("dropping malformed View mute rule: %r", dict(entry))
            continue
        if rule.category not in categories:
            unknown.append(f"mute category: {rule.category!r}")
            logger.warning("dropping unknown View mute category: %r", rule.category)
            continue
        mute.append(rule)

    view = View(
        theme=theme,
        sections_hidden=_known_panels("sections_hidden"),
        sections_collapsed=_known_panels("sections_collapsed"),
        mute=mute,
    )
    return view, unknown


def _parse_file(path: Path) -> dict[str, object]:
    """Parse the View file, raising ``ViewParseError`` on a syntax error.

    Args:
        path: The existing View file.

    Returns:
        The parsed TOML as a plain mapping.

    Raises:
        ViewParseError: If the file does not parse as TOML.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            return tomlkit.load(handle).unwrap()
    except (TOMLKitError, ValueError) as error:
        raise ViewParseError(f"the View file {path} does not parse: {error}") from error


def _writable(path: Path) -> bool:
    """Whether the board can write the View file (the file, or its parent when absent)."""
    if path.exists():
        return os.access(path, os.W_OK)
    parent = path.parent if str(path.parent) else Path()
    return parent.exists() and os.access(parent, os.W_OK)


def read_view(path: Path | None, *, home: Path | None = None) -> ViewState:
    """Read the View file live, dropping any unknown key with a warning.

    Called on every request, so a hand edit shows on the next refresh. A missing or
    opted-out file is a board at its defaults, not an error. A file that does not
    parse is logged and read as empty, so the board still loads; the write path is
    where a parse failure refuses the write (``apply_preference``).

    Args:
        path: The View file, or None when the View file is opted out.
        home: Home directory, to relativise the displayed file path to ``~``.

    Returns:
        The effective View, the unknown keys dropped, and the file's state.
    """
    from wkx_ecosystem_localhost.redaction import relativise

    if path is None:
        return ViewState(view=View(), file=None, found=False, writable=False)
    file_display = relativise(path, home) if home is not None else str(path)
    if not path.is_file():
        return ViewState(view=View(), file=file_display, found=False, writable=_writable(path))
    try:
        data = _parse_file(path)
    except ViewParseError:
        logger.warning("View file %s does not parse; reading it as empty", path)
        return ViewState(view=View(), file=file_display, found=True, writable=_writable(path))
    view, unknown = _view_from_data(data)
    return ViewState(
        view=view,
        unknown_keys=unknown,
        file=file_display,
        found=True,
        writable=_writable(path),
    )


def _document(view: View) -> tomlkit.TOMLDocument:
    """Serialise a View to a TOML document with the board's header, overrides only."""
    doc = tomlkit.document()
    for line in _HEADER:
        doc.add(tomlkit.comment(line) if line else tomlkit.nl())
    doc.add(tomlkit.nl())
    if view.theme is not None:
        doc["theme"] = view.theme
    if view.sections_hidden:
        doc["sections_hidden"] = view.sections_hidden
    if view.sections_collapsed:
        doc["sections_collapsed"] = view.sections_collapsed
    if view.mute:
        rules = tomlkit.aot()
        for rule in view.mute:
            table = tomlkit.table()
            table["category"] = rule.category
            if rule.target is not None:
                table["target"] = rule.target
            rules.append(table)
        doc["mute"] = rules
    return doc


def _write_atomic(path: Path, view: View) -> None:
    """Write the View to ``path`` atomically: a temporary file, then a rename.

    The temporary file is created in the destination directory so the rename is
    atomic on the same filesystem. A failure at any step raises ``ViewWriteError``
    and leaves any existing file untouched.

    Raises:
        ViewWriteError: If the file cannot be written or renamed into place.
    """
    directory = path.parent if str(path.parent) else Path()
    temp_path: Path | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handle_fd, temp_name = tempfile.mkstemp(
            dir=directory, prefix=f".{path.name}.", suffix=".tmp"
        )
        temp_path = Path(temp_name)
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            tomlkit.dump(_document(view), handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as error:
        if temp_path is not None:
            with contextlib.suppress(OSError):
                temp_path.unlink()
        raise ViewWriteError(f"could not write the View file {path}: {error}") from error


# Serialises every write in this process, held across the read-merge-write so two
# concurrent PATCHes never interleave and an atomic rename never lands on a
# half-merged file. Process-level, as the board is a single always-on instance.
_WRITE_LOCK = threading.Lock()


def apply_preference(path: Path, preference: Preference) -> View:
    """Merge one preference into the View file and write it, under the write lock.

    The whole read-merge-write runs under a process-level lock, so two concurrent
    writes serialise rather than clobbering each other. The on-disk file is read
    strictly first: a parse failure refuses the write (the board never regenerates
    the file from memory). The merged View is written atomically and returned.

    Args:
        path: The View file to merge into and write.
        preference: The validated preference to apply.

    Returns:
        The effective View after the merge.

    Raises:
        ViewParseError: If the file on disk does not parse (the write is refused).
        ViewWriteError: If the merged View cannot be written.
    """
    with _WRITE_LOCK:
        if path.is_file():
            current, _unknown = _view_from_data(_parse_file(path))
        else:
            current = View()
        merged = merge(current, preference)
        _write_atomic(path, merged)
        logger.info("wrote the View file %s", path)
        return merged
