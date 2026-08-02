"""Structural invariants over the static board assets.

A table element (td, th, tr) must keep its table display: a td displayed as
anything but table-cell falls out of the table model. Its row border floats at
content height rather than the row boundary, colSpan is ignored, and its
content pollutes column sizing. Flex layout inside a cell belongs on an inner
wrapper element, never on the cell itself. These tests hold that line by
cross-checking the classes app.js applies to table elements against the
classes styles.css gives a display-altering declaration.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).parent.parent / "src" / "wkx_ecosystem_localhost" / "static"

# el("td"|"th"|"tr", "<classes>") — a table element built with a class literal.
EL_TABLE_CLASS = re.compile(r'el\(\s*"(?:td|th|tr)"\s*,\s*"([^"]+)"')
# U.td(<content>, "<classes>") — the shared cell helper's class argument. The
# content argument is matched as balanced-enough tokens: string literals, one
# level of nested call parentheses, or any bare token that is not a paren.
U_TD_CLASS = re.compile(
    r'U\.td\(\s*(?:"[^"]*"|\((?:[^()]|\([^()]*\))*\)|[^(),"])*,\s*"([^"]+)"\s*\)',
    re.DOTALL,
)
# One flat CSS rule. Media/keyframe wrappers parse sloppily, but their inner
# rules still surface as their own matches, which is all this check needs.
CSS_RULE = re.compile(r"([^{}]+)\{([^}]*)\}")
# A display value that demotes a table element. Any table-* value keeps it.
DISPLAY_ALTERING = re.compile(r"display\s*:\s*(?!table)")
CSS_CLASS = re.compile(r"\.([A-Za-z0-9_-]+)")


def table_element_classes(app_js: str) -> set[str]:
    classes: set[str] = set()
    for pattern in (EL_TABLE_CLASS, U_TD_CLASS):
        for match in pattern.finditer(app_js):
            classes.update(match.group(1).split())
    return classes


def display_altering_classes(styles_css: str) -> set[str]:
    classes: set[str] = set()
    for selectors, declarations in CSS_RULE.findall(styles_css):
        if DISPLAY_ALTERING.search(declarations):
            classes.update(CSS_CLASS.findall(selectors))
    return classes


def test_no_display_altering_class_lands_on_a_table_element() -> None:
    app_js = (STATIC / "app.js").read_text()
    styles_css = (STATIC / "styles.css").read_text()

    offending = table_element_classes(app_js) & display_altering_classes(styles_css)

    assert offending == set(), (
        f"Classes {sorted(offending)} are applied to td/th/tr in app.js but "
        "styles.css gives them a non-table display. Move the layout onto an "
        "inner wrapper element (see wkxUI.cellFlex) so the cell stays a cell."
    )


def test_the_check_still_sees_both_sides() -> None:
    # Guard the guard: if refactoring ever renames the construction helpers or
    # strips every class, these sets going empty would make the invariant test
    # pass vacuously. This canary fails loudly instead.
    app_js = (STATIC / "app.js").read_text()
    styles_css = (STATIC / "styles.css").read_text()

    assert table_element_classes(app_js), "no classed table elements found in app.js"
    assert display_altering_classes(styles_css), "no display-altering classes found in styles.css"
