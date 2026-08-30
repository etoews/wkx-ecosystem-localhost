"""The board's table catalogue and the client-side ids pinned to it.

The catalogue lives in Python beside the Flag CATEGORIES; ``PATCH /api/view``
validates every [columns_hidden], [sort], and [filter] override against it. This
suite pins the ids and column keys the client declares in app.js to the Python
catalogue the way ``test_flags_derive`` pins CATEGORY_LABEL to CATEGORIES, so the
two can never drift.
"""

from __future__ import annotations

import re
from pathlib import Path

from wkx_ecosystem_localhost.collectors.flags import (
    FILTERABLE_SECTIONS,
    TABLES,
    column_keys,
    hideable_keys,
)
from wkx_ecosystem_localhost.models import Section

STATIC = Path(__file__).parent.parent / "src" / "wkx_ecosystem_localhost" / "static"

# The client's TABLE_COLUMNS map: capture the object literal, then each table id
# and the column-key array it maps to. The block runs from the literal to its
# matching close brace, sitting on its own line at column zero.
_MAP_BLOCK = re.compile(r"TABLE_COLUMNS\s*=\s*\{(.*?)\n  \}", re.DOTALL)
_ENTRY = re.compile(r'"([a-z0-9-]+)"\s*:\s*\[([^\]]*)\]')
_KEY = re.compile(r'"([a-z0-9-]+)"')


def _client_table_columns() -> dict[str, list[str]]:
    """The table id -> column keys map the board declares in app.js."""
    app_js = (STATIC / "app.js").read_text()
    match = _MAP_BLOCK.search(app_js)
    assert match, "TABLE_COLUMNS map not found in app.js"
    tables: dict[str, list[str]] = {}
    for table_id, keys in _ENTRY.findall(match.group(1)):
        tables[table_id] = _KEY.findall(keys)
    return tables


# ---------- the Python catalogue ----------


def test_every_catalogue_section_is_a_real_section() -> None:
    values = {section.value for section in Section}

    assert {table.section for table in TABLES.values()} <= values


def test_filterable_sections_are_the_sections_that_own_a_table() -> None:
    assert frozenset(table.section for table in TABLES.values()) == FILTERABLE_SECTIONS


def test_docker_and_summary_own_no_table() -> None:
    # Docker is tiles-only and the summary is the Flag rollup, so neither is
    # filterable and neither appears in the catalogue.
    assert "docker" not in FILTERABLE_SECTIONS
    assert "summary" not in FILTERABLE_SECTIONS


def test_every_table_locks_a_name_column_and_the_flags_rail() -> None:
    for table_id, table in TABLES.items():
        locked = {column.key for column in table.columns if column.locked}
        assert "flags" in locked, table_id
        assert len(locked) >= 2, table_id  # the Flags rail plus at least one identity column


def test_the_example_ids_from_the_milestone_are_present() -> None:
    for table_id in ("workspace", "claude-plugins", "git-config-keys", "config-mutes"):
        assert table_id in TABLES


def test_the_example_column_keys_from_the_milestone_are_present() -> None:
    assert "working-tree" in hideable_keys("workspace")
    assert "node-modules" in hideable_keys("footprint")


def test_hideable_keys_excludes_the_locked_columns() -> None:
    assert "repo" not in hideable_keys("workspace")  # the name column is locked
    assert "flags" not in hideable_keys("workspace")  # the Flags rail is locked
    assert "stash" in hideable_keys("workspace")


def test_column_keys_of_an_unknown_table_is_empty() -> None:
    assert column_keys("nope") == ()
    assert hideable_keys("nope") == frozenset()


# ---------- the client ids pinned to the catalogue ----------


def test_client_table_ids_match_the_catalogue() -> None:
    assert set(_client_table_columns()) == set(TABLES)


def test_client_column_keys_match_the_catalogue_in_order() -> None:
    client = _client_table_columns()
    for table_id, table in TABLES.items():
        assert client[table_id] == [column.key for column in table.columns], table_id
