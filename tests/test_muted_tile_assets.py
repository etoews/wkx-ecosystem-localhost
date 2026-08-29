"""Structural invariants over the Muted tile (M10).

The needs-attention summary carries a fourth tile, Muted, beside Total, Attention,
and Problems. It counts the Flags a Mute rule silenced, so the suppression is never
a silent subtraction. app.js is not run by the suite, so these string and
cross-asset checks hold the tile's wiring in place without a browser: the tile is
built with the "muted" kind, styles.css draws that kind, and the muting choke point
that feeds its count is present.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).parent.parent / "src" / "wkx_ecosystem_localhost" / "static"

# The tiles() spec objects the summary builds, each {value, label, kind?}. The four
# needs-attention tiles are the ones whose labels this check pins.
TILE_LABEL = re.compile(r'label:\s*"([^"]+)"')


def test_summary_renders_the_four_needs_attention_tiles() -> None:
    app_js = (STATIC / "app.js").read_text()
    labels = set(TILE_LABEL.findall(app_js))

    for label in ("Total flags", "Attention", "Problems", "Muted"):
        assert label in labels, f'the needs-attention summary is missing the "{label}" tile'


def test_muted_tile_is_built_with_the_muted_kind() -> None:
    app_js = (STATIC / "app.js").read_text()

    # The Muted tile is tinted with kind "muted", the way Attention and Problems are
    # tinted with theirs, so styles.css can give it its own recessive treatment.
    assert 'kind: "muted"' in app_js, (
        'app.js never builds a tile with kind "muted"; the Muted count needs its '
        "own tile kind so it reads distinctly from the live counts."
    )


def test_muted_tile_kind_is_drawn_in_styles() -> None:
    styles_css = (STATIC / "styles.css").read_text()

    assert ".tile--muted" in styles_css, (
        "styles.css never draws .tile--muted; the kind app.js applies must have a "
        "rule or the Muted count falls back to the neutral tile look."
    )


def test_muting_choke_point_counts_and_hides() -> None:
    # The Muted tile's count is the size of the `muted` set that place() diverts a
    # muted Flag into, keeping it out of the registry decorate() and the live tiles
    # read. Hold that wiring so a refactor cannot quietly route a muted Flag back
    # onto the board or drop it from the count.
    app_js = (STATIC / "app.js").read_text()

    assert "function isMuted(" in app_js, "app.js never decides whether a Flag is muted"
    assert "muted.set(" in app_js, "app.js never diverts a muted Flag into the muted set"
    assert "muted.size" in app_js, "the Muted tile never reads the muted count"
