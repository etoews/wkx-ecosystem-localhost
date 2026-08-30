"""The View module: read, merge, write, the lock, and the drop-and-warn read.

Every test writes over a tmp path, never a real file. The View file is the
board's own file (ADR 0004): it holds overrides only, is read live, is written
atomically under a process-level lock, and refuses a write when the file on disk
does not parse.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

from wkx_ecosystem_localhost.exceptions import (
    InvalidPreference,
    ViewParseError,
    ViewWriteError,
)
from wkx_ecosystem_localhost.view import (
    DEFAULT_VIEW_FILE,
    VIEW_FILE_ENV,
    MuteRule,
    SectionPreference,
    ThemePreference,
    View,
    apply_preference,
    merge,
    parse_preference,
    read_view,
    resolve_view_file,
)

HOME = Path("/home/someone")


def _view_file(tmp_path: Path) -> Path:
    return tmp_path / "wkx-ecosystem-localhost.view.toml"


# ---------- resolving the path ----------


def test_resolve_defaults_to_the_working_directory_file() -> None:
    assert resolve_view_file({}) == DEFAULT_VIEW_FILE


def test_resolve_honours_the_env_override() -> None:
    resolved = resolve_view_file({VIEW_FILE_ENV: "~/custom.view.toml"})

    assert resolved == (Path.home() / "custom.view.toml")


def test_resolve_none_opts_out() -> None:
    assert resolve_view_file({}, None) is None


def test_resolve_uses_an_explicit_path_verbatim(tmp_path: Path) -> None:
    path = _view_file(tmp_path)

    assert resolve_view_file({}, path) == path


# ---------- reading ----------


def test_read_absent_file_is_a_board_at_its_defaults(tmp_path: Path) -> None:
    state = read_view(_view_file(tmp_path), home=HOME)

    assert state.view == View()
    assert state.found is False
    assert state.unknown_keys == []


def test_read_none_path_is_empty_and_unfound() -> None:
    state = read_view(None)

    assert state.view == View()
    assert state.file is None
    assert state.found is False
    assert state.writable is False


def test_read_reports_the_relative_file_path(tmp_path: Path) -> None:
    path = HOME / "wkx-ecosystem-localhost.view.toml"

    state = read_view(path, home=HOME)

    assert state.file == "~/wkx-ecosystem-localhost.view.toml"


# ---------- the round trip and overrides-only writing ----------


def test_theme_round_trips_through_the_file(tmp_path: Path) -> None:
    path = _view_file(tmp_path)

    apply_preference(path, ThemePreference(theme="dark"))

    assert read_view(path, home=HOME).view.theme == "dark"


def test_a_default_value_is_removed_from_the_file(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    apply_preference(path, ThemePreference(theme="dark"))

    apply_preference(path, ThemePreference(theme=None))

    # No `theme = ...` assignment survives; the header comment may mention the word.
    assert not any(
        line.strip().startswith("theme")
        for line in path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )
    assert read_view(path, home=HOME).view.theme is None


def test_hiding_then_showing_a_panel_leaves_no_override(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    apply_preference(path, SectionPreference(field="sections_hidden", panel="docker", on=True))

    apply_preference(path, SectionPreference(field="sections_hidden", panel="docker", on=False))

    assert read_view(path, home=HOME).view.sections_hidden == []


def test_hidden_and_collapsed_panels_persist(tmp_path: Path) -> None:
    path = _view_file(tmp_path)

    apply_preference(path, SectionPreference(field="sections_hidden", panel="docker", on=True))
    apply_preference(path, SectionPreference(field="sections_collapsed", panel="summary", on=True))

    state = read_view(path, home=HOME)
    assert state.view.sections_hidden == ["docker"]
    assert state.view.sections_collapsed == ["summary"]


def test_the_file_carries_the_board_header(tmp_path: Path) -> None:
    path = _view_file(tmp_path)

    apply_preference(path, ThemePreference(theme="light"))

    assert "The board writes this file" in path.read_text()


def test_a_fresh_board_writes_no_file(tmp_path: Path) -> None:
    # Reading never creates the file; only a write does, so a board with no change
    # leaves nothing on disk.
    read_view(_view_file(tmp_path), home=HOME)

    assert not _view_file(tmp_path).exists()


# ---------- merge is pure and overrides-only ----------


def test_merge_never_duplicates_a_panel() -> None:
    view = View(sections_hidden=["docker"])

    merged = merge(view, SectionPreference(field="sections_hidden", panel="docker", on=True))

    assert merged.sections_hidden == ["docker"]


def test_merge_preserves_the_other_fields() -> None:
    view = View(theme="dark", mute=[MuteRule(category="brew-outdated")])

    merged = merge(view, SectionPreference(field="sections_collapsed", panel="config", on=True))

    assert merged.theme == "dark"
    assert merged.mute == [MuteRule(category="brew-outdated")]
    assert merged.sections_collapsed == ["config"]


# ---------- validating a preference against the catalogue ----------


def test_parse_theme_preference() -> None:
    assert parse_preference({"field": "theme", "value": "dark"}).theme == "dark"


def test_parse_theme_auto_clears_the_theme() -> None:
    assert parse_preference({"field": "theme", "value": "auto"}).theme is None


def test_parse_rejects_an_unknown_theme() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference({"field": "theme", "value": "sepia"})


def test_parse_rejects_an_unknown_panel() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference({"field": "sections_hidden", "panel": "nope", "on": True})


def test_parse_rejects_an_unknown_field() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference({"field": "sort", "value": "x"})


def test_parse_rejects_a_non_boolean_on() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference({"field": "sections_hidden", "panel": "docker", "on": "yes"})


# ---------- the parse-failure refusal ----------


def test_a_corrupt_file_refuses_the_write_and_is_untouched(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    path.write_text("this = is = not valid toml\n")

    with pytest.raises(ViewParseError):
        apply_preference(path, ThemePreference(theme="dark"))

    # The board never regenerates the file from memory: the corrupt bytes stay.
    assert path.read_text() == "this = is = not valid toml\n"


def test_a_write_error_surfaces_as_view_write_error(tmp_path: Path) -> None:
    # A directory where the file should be cannot be renamed over, so the write
    # fails and is reported rather than lost.
    path = _view_file(tmp_path)
    path.mkdir()

    with pytest.raises(ViewWriteError):
        apply_preference(path, ThemePreference(theme="dark"))


# ---------- the drop-and-warn read ----------


def test_an_unknown_panel_is_dropped_and_warned(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _view_file(tmp_path)
    path.write_text('sections_hidden = ["docker", "nope"]\n')

    with caplog.at_level(logging.WARNING):
        state = read_view(path, home=HOME)

    assert state.view.sections_hidden == ["docker"]
    assert any("nope" in key for key in state.unknown_keys)
    assert any("nope" in record.getMessage() for record in caplog.records)


def test_an_unknown_mute_category_is_dropped_and_warned(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _view_file(tmp_path)
    path.write_text('[[mute]]\ncategory = "brew-outdate"\n')

    with caplog.at_level(logging.WARNING):
        state = read_view(path, home=HOME)

    assert state.view.mute == []
    assert any("brew-outdate" in key for key in state.unknown_keys)


def test_a_known_mute_category_is_kept(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    path.write_text('[[mute]]\ncategory = "brew-outdated"\ntarget = "formula:git"\n')

    state = read_view(path, home=HOME)

    assert state.view.mute == [MuteRule(category="brew-outdated", target="formula:git")]
    assert state.unknown_keys == []


def test_a_corrupt_file_reads_as_empty_without_raising(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    path.write_text("this = is = not valid toml\n")

    state = read_view(path, home=HOME)

    assert state.view == View()
    assert state.found is True


# ---------- the write lock ----------


def test_concurrent_writes_serialise_without_corruption(tmp_path: Path) -> None:
    # Many threads each hide a distinct panel at once; the process lock serialises
    # the read-merge-write so the file stays parseable and every write lands.
    path = _view_file(tmp_path)
    panels = ["workspace", "toolchains", "claude", "homebrew", "system", "docker"]

    def hide(panel: str) -> None:
        apply_preference(path, SectionPreference(field="sections_hidden", panel=panel, on=True))

    threads = [threading.Thread(target=hide, args=(panel,)) for panel in panels]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    hidden = read_view(path, home=HOME).view.sections_hidden
    assert sorted(hidden) == sorted(panels)
