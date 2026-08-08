"""Structural invariants over the M8 token-highlight assets.

Hovering or keyboard-focusing a repo name, a tool name, or a version lights
every cell that shares its (kind, identical value) across the whole board, in
the reserved --match colour. Two structural lines hold that wiring in place
without a browser: a token cell must carry the (kind, value) identity app.js
matches on, and the highlight the layer switches on must be drawn with --match,
the one colour reserved for it. These tests cross-check the two static assets so
a rename on either side fails loudly rather than silently dropping the highlight.

M8-B pins that highlight: a click (or Enter/Space on a focused token) makes it
persist after the pointer leaves, Esc or a click on empty space releases it, and
a token exposes its interactive pressed state to assistive tech. A further check
holds that pin/release wiring in place without a browser.
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


def test_pin_and_release_and_aria_are_wired() -> None:
    # M8-B extends the transient highlight into a pinnable one: a click, or
    # Enter/Space on a focused token, pins it so it survives the pointer leaving;
    # Esc or a click on empty space releases it; and the token exposes its
    # interactive, pressed state to assistive tech. These string checks hold that
    # wiring in app.js without a browser, so dropping any half fails loudly.
    app_js = (STATIC / "app.js").read_text()

    # Pinning paints a committed treatment on top of the transient hover origin;
    # tok-pinned is that extra class, so it is also covered by the --match check.
    assert "tok-pinned" in app_js, (
        "app.js never applies tok-pinned; a click must pin the highlight with a "
        "treatment distinct from the transient hover."
    )
    # Release: Esc clears a pinned highlight.
    assert "Escape" in app_js, (
        "app.js never handles the Escape key; Esc must release a pinned highlight."
    )
    # The interaction is exposed to assistive tech as a toggle button's state.
    assert "aria-pressed" in app_js, (
        "app.js never sets aria-pressed; a token cell must expose its pin state "
        "to assistive tech."
    )
    # Pinning cooperates with the cells already wired to a click (expandable
    # plugin rows, sortable headers) rather than triggering both.
    assert "stopPropagation" in app_js, (
        "app.js never calls stopPropagation on the token gesture; pinning must "
        "not also trigger an expandable row or a sortable header underneath it."
    )


def test_the_check_still_sees_both_sides() -> None:
    # Guard the guard: if the highlight classes or the --match rules are ever
    # renamed away, these sets going empty would make the cross-check above pass
    # vacuously. This canary fails loudly instead.
    app_js = (STATIC / "app.js").read_text()
    styles_css = (STATIC / "styles.css").read_text()

    assert applied_token_classes(app_js), "no tok-* highlight classes applied in app.js"
    assert match_coloured_classes(styles_css), "no class drawn with var(--match) in styles.css"
