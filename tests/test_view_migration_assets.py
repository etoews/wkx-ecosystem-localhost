"""Structural invariants over the one-time View migration in app.js.

On the first load after M12, app.js reads the old localStorage keys once, writes
each preference through PATCH /api/view, and deletes the keys only after every
write succeeds (ADR 0004). The suite does not run app.js, so these string checks
hold the migration order in place without a browser: the write comes first, and
the keys are cleared only in the .then that follows the chained writes.
"""

from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).parent.parent / "src" / "wkx_ecosystem_localhost" / "static"


def _app_js() -> str:
    return (STATIC / "app.js").read_text()


def test_migration_reads_the_three_legacy_keys() -> None:
    app_js = _app_js()

    for key in ("wkx-theme", "wkx-sections", "wkx-collapsed"):
        assert key in app_js, f"the migration never reads the legacy key {key}"


def test_migration_clears_the_keys_only_after_the_writes_land() -> None:
    app_js = _app_js()

    # The writes are chained with reduce, and clearLegacy runs only in the .then
    # that follows the chain, so no key is deleted before its write succeeds.
    assert ".then(clearLegacy)" in app_js, (
        "the migration must clear the legacy keys in the .then after the writes, "
        "never before a write has landed"
    )
    # clearLegacy is the one place the keys are removed.
    clear_start = app_js.index("function clearLegacy(")
    clear_body = app_js[clear_start : clear_start + 400]
    for key in ("LEGACY_THEME", "LEGACY_SECTIONS", "LEGACY_COLLAPSED"):
        assert f"removeItem({key})" in clear_body, f"clearLegacy never removes {key}"


def test_the_board_writes_the_view_over_patch() -> None:
    app_js = _app_js()

    assert "/api/view" in app_js
    assert 'method: "PATCH"' in app_js
    # And it listens for the convergence stream so every tab applies a remote write.
    assert "/api/view/stream" in app_js
    assert 'addEventListener("view"' in app_js
