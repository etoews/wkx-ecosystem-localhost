"""Structural invariants over the M8 token-highlight assets.

Hovering or keyboard-focusing a repo name, a tool name, or a version lights
every cell that shares its (kind, identical value) across the whole board, in
the reserved --match colour. Two structural lines hold that wiring in place
without a browser: a token cell must carry the (kind, value) identity app.js
matches on, and the highlight the layer switches on must be drawn with --match,
the one colour reserved for it. These tests cross-check the two static assets so
a rename on either side fails loudly rather than silently dropping the highlight.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).parent.parent / "src" / "wkx_ecosystem_localhost" / "static"

# The two halves of a token cell's identity, stamped through the element dataset.
TOKEN_IDENTITY = ("tokenKind", "tokenValue")
# classList.add("…") — the runtime switch that paints a match. tok-* names only.
CLASSLIST_ADD = re.compile(r"classList\.add\(([^)]*)\)")
TOK_CLASS = re.compile(r'"(tok-[A-Za-z0-9_-]+)"')
# One flat CSS rule. Media/keyframe wrappers parse sloppily, but their inner
# rules still surface as their own matches, which is all this check needs.
CSS_RULE = re.compile(r"([^{}]+)\{([^}]*)\}")
CSS_CLASS = re.compile(r"\.([A-Za-z0-9_-]+)")
# A declaration that reads the reserved match colour (not merely defines it).
USES_MATCH = re.compile(r"var\(\s*--match\s*\)")


def applied_token_classes(app_js: str) -> set[str]:
    classes: set[str] = set()
    for call in CLASSLIST_ADD.findall(app_js):
        classes.update(TOK_CLASS.findall(call))
    return classes


def match_coloured_classes(styles_css: str) -> set[str]:
    classes: set[str] = set()
    for selectors, declarations in CSS_RULE.findall(styles_css):
        if USES_MATCH.search(declarations):
            classes.update(CSS_CLASS.findall(selectors))
    return classes


def test_token_cells_carry_a_kind_and_value_identity() -> None:
    app_js = (STATIC / "app.js").read_text()
    for attr in TOKEN_IDENTITY:
        assert f"dataset.{attr}" in app_js, (
            f"app.js never stamps dataset.{attr}; a token cell needs both its "
            "kind and its value to match same-kind values across the board."
        )
    assert "[data-token-kind]" in app_js, (
        "app.js never reads the token identity back with [data-token-kind]; "
        "the tagging is dead weight unless the highlight layer queries it."
    )


def test_every_applied_highlight_class_is_drawn_with_the_match_colour() -> None:
    app_js = (STATIC / "app.js").read_text()
    styles_css = (STATIC / "styles.css").read_text()

    applied = applied_token_classes(app_js)
    match_coloured = match_coloured_classes(styles_css)

    undrawn = applied - match_coloured
    assert undrawn == set(), (
        f"Classes {sorted(undrawn)} are switched on in app.js to mark a token "
        "match but styles.css never draws them with var(--match). The match "
        "highlight must use --match, the colour reserved for it."
    )


def test_the_check_still_sees_both_sides() -> None:
    # Guard the guard: if the highlight classes or the --match rules are ever
    # renamed away, these sets going empty would make the cross-check above pass
    # vacuously. This canary fails loudly instead.
    app_js = (STATIC / "app.js").read_text()
    styles_css = (STATIC / "styles.css").read_text()

    assert applied_token_classes(app_js), "no tok-* highlight classes applied in app.js"
    assert match_coloured_classes(styles_css), "no class drawn with var(--match) in styles.css"
