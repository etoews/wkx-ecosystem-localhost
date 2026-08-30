"""The M13 View additions: [filter], [columns_hidden], and [sort].

Every test writes over a tmp path, never a real file. The three overrides round
trip through the board's own View file the same way theme, Hidden, and Mute do:
overrides only, validated against the table catalogue, dropped-and-warned on read
when the file names a table, column, or Section the board does not know.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from wkx_ecosystem_localhost.exceptions import InvalidPreference
from wkx_ecosystem_localhost.view import (
    ColumnHiddenPreference,
    FilterPreference,
    SortPreference,
    SortRule,
    View,
    apply_preference,
    merge,
    parse_preference,
    read_view,
)

HOME = Path("/home/someone")


def _view_file(tmp_path: Path) -> Path:
    return tmp_path / "wkx-ecosystem-localhost.view.toml"


# ---------- parsing: Filter ----------


def test_parse_filter_preference() -> None:
    pref = parse_preference({"field": "filter", "section": "workspace", "text": "acme"})

    assert pref == FilterPreference(section="workspace", text="acme")


def test_parse_filter_rejects_an_unknown_section() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference({"field": "filter", "section": "nope", "text": "x"})


def test_parse_filter_rejects_docker_which_owns_no_table() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference({"field": "filter", "section": "docker", "text": "x"})


# ---------- parsing: columns_hidden ----------


def test_parse_columns_hidden_preference() -> None:
    pref = parse_preference(
        {"field": "columns_hidden", "table": "workspace", "column": "stash", "on": True}
    )

    assert pref == ColumnHiddenPreference(table="workspace", column="stash", on=True)


def test_parse_columns_hidden_rejects_an_unknown_table() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference({"field": "columns_hidden", "table": "nope", "column": "x", "on": True})


def test_parse_columns_hidden_rejects_an_unknown_column() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference(
            {"field": "columns_hidden", "table": "workspace", "column": "nope", "on": True}
        )


def test_parse_columns_hidden_rejects_a_locked_column() -> None:
    # The name column is locked, so it can never be written Hidden.
    with pytest.raises(InvalidPreference):
        parse_preference(
            {"field": "columns_hidden", "table": "workspace", "column": "repo", "on": True}
        )


# ---------- parsing: sort ----------


def test_parse_sort_preference() -> None:
    pref = parse_preference(
        {"field": "sort", "table": "workspace", "column": "behind", "direction": "ascending"}
    )

    assert pref == SortPreference(table="workspace", column="behind", direction="ascending")


def test_parse_sort_with_no_direction_is_the_unsorted_state() -> None:
    pref = parse_preference(
        {"field": "sort", "table": "workspace", "column": "behind", "direction": None}
    )

    assert pref == SortPreference(table="workspace", column="behind", direction=None)


def test_parse_sort_rejects_an_unknown_direction() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference(
            {"field": "sort", "table": "workspace", "column": "behind", "direction": "sideways"}
        )


def test_parse_sort_rejects_an_unknown_column() -> None:
    with pytest.raises(InvalidPreference):
        parse_preference(
            {"field": "sort", "table": "workspace", "column": "nope", "direction": "ascending"}
        )


# ---------- merge: overrides only ----------


def test_merge_sets_and_clears_a_filter() -> None:
    withtext = merge(View(), FilterPreference(section="workspace", text="acme"))
    assert withtext.filter == {"workspace": "acme"}

    cleared = merge(withtext, FilterPreference(section="workspace", text=""))
    assert cleared.filter == {}


def test_merge_hides_and_shows_a_column() -> None:
    hidden = merge(View(), ColumnHiddenPreference(table="workspace", column="stash", on=True))
    assert hidden.columns_hidden == {"workspace": ["stash"]}

    shown = merge(hidden, ColumnHiddenPreference(table="workspace", column="stash", on=False))
    assert shown.columns_hidden == {}


def test_merge_never_duplicates_a_hidden_column() -> None:
    once = merge(View(), ColumnHiddenPreference(table="workspace", column="stash", on=True))
    twice = merge(once, ColumnHiddenPreference(table="workspace", column="stash", on=True))

    assert twice.columns_hidden == {"workspace": ["stash"]}


def test_merge_sets_and_clears_a_sort() -> None:
    sorted_ = merge(
        View(), SortPreference(table="workspace", column="behind", direction="descending")
    )
    assert sorted_.sort == {"workspace": SortRule(column="behind", direction="descending")}

    cleared = merge(sorted_, SortPreference(table="workspace", column="behind", direction=None))
    assert cleared.sort == {}


# ---------- the file round trip ----------


def test_the_three_overrides_round_trip_through_the_file(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    apply_preference(path, FilterPreference(section="workspace", text="acme"))
    apply_preference(path, ColumnHiddenPreference(table="workspace", column="stash", on=True))
    apply_preference(
        path, SortPreference(table="workspace", column="behind", direction="ascending")
    )

    view = read_view(path, home=HOME).view

    assert view.filter == {"workspace": "acme"}
    assert view.columns_hidden == {"workspace": ["stash"]}
    assert view.sort == {"workspace": SortRule(column="behind", direction="ascending")}


def test_a_fresh_board_writes_no_file_for_these_overrides(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    # Clearing a filter that was never set leaves the board at its defaults.
    apply_preference(path, FilterPreference(section="workspace", text=""))

    assert read_view(path, home=HOME).view == View()


# ---------- drop-and-warn on read ----------


def test_an_unknown_filter_section_is_dropped_and_warned(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _view_file(tmp_path)
    path.write_text('[filter]\nworkspace = "keep"\nnope = "drop"\n')

    with caplog.at_level(logging.WARNING):
        state = read_view(path, home=HOME)

    assert state.view.filter == {"workspace": "keep"}
    assert any("nope" in key for key in state.unknown_keys)


def test_an_unknown_hidden_column_is_dropped_and_warned(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    path.write_text('[columns_hidden]\nworkspace = ["stash", "nope"]\n')

    state = read_view(path, home=HOME)

    assert state.view.columns_hidden == {"workspace": ["stash"]}
    assert any("nope" in key for key in state.unknown_keys)


def test_a_hidden_locked_column_is_dropped_on_read(tmp_path: Path) -> None:
    # A file naming a locked column Hidden is not honoured; the board only hides
    # hideable columns, so the locked one is dropped-and-warned.
    path = _view_file(tmp_path)
    path.write_text('[columns_hidden]\nworkspace = ["repo"]\n')

    state = read_view(path, home=HOME)

    assert state.view.columns_hidden == {}
    assert any("repo" in key for key in state.unknown_keys)


def test_a_sort_on_an_unknown_column_is_dropped_and_warned(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    path.write_text('[sort.workspace]\ncolumn = "nope"\ndirection = "ascending"\n')

    state = read_view(path, home=HOME)

    assert state.view.sort == {}
    assert any("nope" in key for key in state.unknown_keys)


def test_an_unknown_sort_table_is_dropped_and_warned(tmp_path: Path) -> None:
    path = _view_file(tmp_path)
    path.write_text('[sort.nope]\ncolumn = "x"\ndirection = "ascending"\n')

    state = read_view(path, home=HOME)

    assert state.view.sort == {}
    assert any("nope" in key for key in state.unknown_keys)
