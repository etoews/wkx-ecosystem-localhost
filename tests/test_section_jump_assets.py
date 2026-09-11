"""Structural invariants over the section-jump palette assets.

`g` (or `/`) opens a centred palette that lists the shown Sections and jumps to
one. Three structural lines hold that wiring in place without a browser:

- The overlay paints as `display: flex` when shown, so it MUST carry an explicit
  `.jump[hidden] { display: none }` guard — a flex display beats the user-agent
  `[hidden]` rule, and without the guard the palette can never close (the fault a
  throwaway prototype hit and this feature was written to avoid).
- app.js binds the shortcut and leaves text fields alone, so opening the palette
  never steals a keystroke from the Section Filter.
- The active row is drawn in --sky, the board's one wayfinding colour, so a jump
  row reads as "a Section starts here" exactly as a needs-attention Category link
  does.

These cross-check the two static assets so a rename or a dropped guard on either
side fails loudly rather than silently breaking the palette.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).parent.parent / "src" / "wkx_ecosystem_localhost" / "static"

# One flat CSS rule. Media/keyframe wrappers parse sloppily, but their inner
# rules still surface as their own matches, which is all these checks need.
CSS_RULE = re.compile(r"([^{}]+)\{([^}]*)\}")
DISPLAY_NONE = re.compile(r"display\s*:\s*none")


def rule_declarations(styles_css: str, selector: str) -> list[str]:
    return [decls for sels, decls in CSS_RULE.findall(styles_css) if selector in sels]


def test_jump_overlay_is_guarded_against_its_flex_display() -> None:
    styles_css = (STATIC / "styles.css").read_text()

    shown = rule_declarations(styles_css, ".jump ")
    assert any("display" in d and "flex" in d for d in shown), (
        ".jump no longer paints as a flex overlay; if it draws another way this "
        "guard test needs revisiting."
    )
    guarded = rule_declarations(styles_css, ".jump[hidden]")
    assert guarded and any(DISPLAY_NONE.search(d) for d in guarded), (
        "styles.css never gives .jump[hidden] display:none. The flex display "
        "beats the UA [hidden] rule, so without this guard the palette can never "
        "close — the same guard .disc-menu carries."
    )


def test_jump_binds_the_shortcut_and_spares_text_fields() -> None:
    app_js = (STATIC / "app.js").read_text()

    assert '"g"' in app_js and '"/"' in app_js, "app.js no longer opens the jump palette on g or /."
    assert "typingInField" in app_js, (
        "app.js opens the palette without checking for a focused field; the "
        "shortcut would swallow a keystroke meant for the Section Filter."
    )
    assert "scrollIntoView" in app_js, "app.js never scrolls the chosen Section into view."


def test_active_jump_row_wears_the_wayfinding_sky() -> None:
    styles_css = (STATIC / "styles.css").read_text()

    active = rule_declarations(styles_css, "is-active")
    jump_active = [
        d for sels, d in CSS_RULE.findall(styles_css) if "jump" in sels and "is-active" in sels
    ]
    assert jump_active and any("var(--sky)" in d for d in jump_active), (
        "the active jump row is not drawn with --sky; a jump row should read as "
        "wayfinding, the one meaning --sky carries on this board."
    )
    assert active, "no is-active rule found at all; the palette lost its selection style."
