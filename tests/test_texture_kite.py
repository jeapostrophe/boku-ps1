"""`boku.texture_kite` without a disc: the labels' layout and the tracked English.

The rebuilt sheets and the HUD on Beetle are `tests/test_real_texture_kite.py`'s.
"""

from __future__ import annotations

from itertools import combinations, pairwise

import pytest

from boku import texture_kite as tk
from boku import texture_paint as paint
from boku.texture_text import Entry, TextureTextError, family_entries

ENTRIES = family_entries(tk.FAMILY)

SCREEN_WIDTH = 320
UNITS = (352, 136, 48, 16)
"""`m` and `m/h` on the sheet, right of the Japanese labels (measured)."""


def test_the_tracked_english_gives_every_label():
    assert set(ENTRIES) == {f"hud.{key}" for key in tk.LABELS}


def test_no_two_labels_share_a_texel_and_none_takes_a_units():
    """The cells are in one texture page with the units the HUD draws beside the numbers."""
    cells = {key: set(paint.points(label.cell)) for key, label in tk.LABELS.items()}
    for a, b in combinations(cells, 2):
        assert not cells[a] & cells[b], f"{a} and {b} share texels"
    units = set(paint.points(UNITS))
    for key, cell in cells.items():
        assert not cell & units, f"{key}'s cell runs into the units"


def test_each_cell_is_in_reach_of_a_sprites_byte_of_u():
    for key, label in tk.LABELS.items():
        x, _, w, _ = label.cell
        assert x >= tk.PAGE_X and x - tk.PAGE_X + w <= 256, key


def test_each_label_is_drawn_about_the_point_retail_drew_it_about_and_clear_of_the_next():
    """A label names the number under it (or the compass beside it): wider, it stays centred
    where the Japanese was, on the screen and clear of its neighbours."""
    spans = []
    for key, label in tk.LABELS.items():
        (_, _, rw, _), (_, _, w, _) = label.retail, label.cell
        assert 2 * label.x + w == 2 * label.retail_x + rw, f"{key} is not centred on retail's"
        assert label.x >= 0 and label.x + w <= SCREEN_WIDTH, f"{key} runs off the screen"
        spans.append((label.x, label.x + w, key))
    spans.sort()
    for (_, end, a), (start, _, b) in pairwise(spans):
        assert end <= start, f"{a} is drawn over {b}"


class Bar:
    """A face whose every string is one solid bar: `width` columns, rows 1 to `bottom`."""

    def __init__(self, width: int, bottom: int) -> None:
        self.width, self.bottom = width, bottom

    def ink(self, text):
        return {(x, y) for x in range(self.width) for y in range(1, self.bottom + 1)}


@pytest.mark.parametrize("key", sorted(tk.LABELS))
@pytest.mark.parametrize("over", [(0, 0), (1, 0), (0, 1)], ids=["fits", "wide", "low"])
def test_a_label_and_its_edge_fit_its_cell_or_are_refused(key, over):
    """The narrowest cases: ink as wide as the cell less a texel of edge each side, reaching
    the row above the last (its edge on the last) -- and one texel more either way."""
    _, _, w, h = cell = tk.LABELS[key].cell
    face = Bar(w - 2 + over[0], h - 2 - tk.GLYPH_TOP + over[1])
    entry = Entry(f"kite@hud.{key}", "x", "t:1")
    if over == (0, 0):
        ink = tk.label_ink(face, entry, cell)
        assert paint.extent(paint.grown(ink, 1, 1, 1, 1)) == (0, tk.GLYPH_TOP, w, h - tk.GLYPH_TOP)
    else:
        with pytest.raises(TextureTextError, match="nothing is cut to fit"):
            tk.label_ink(face, entry, cell)
