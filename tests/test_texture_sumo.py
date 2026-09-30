"""`boku.texture_sumo` without a disc: the banner's layout, the tracked English, the refusals.

The rebuilt textures and the bout on Beetle are `tests/test_real_texture_sumo.py`'s.
"""

from __future__ import annotations

import re

import pytest

from boku import REPO_ROOT
from boku import texture_paint as paint
from boku import texture_sumo as ts
from boku.texture_text import Entry, TextureTextError, read_entries

ENTRIES = {e.id.removeprefix(ts.FAMILY): e for e in read_entries().values()
           if e.family == ts.FAMILY}  # fmt: skip


class Blocks:
    """A face of 5x9 blocks, 6 apart, each letter's cell 12 rows."""

    name = "blocks"
    space = 4

    def ink(self, text):
        return {(6 * n + dx, 2 + dy) for n, ch in enumerate(text) if ch != " "
                for dx in range(5) for dy in range(9)}  # fmt: skip


def test_the_tracked_english_gives_every_key_of_every_part():
    assert set(ENTRIES) == set(ts.KEYS)


def test_the_banners_moves_are_worded_as_the_move_names_array_words_them():
    """Moves 1-19 are `musi@2C.13`-`.31`, in order (`research/sumo.md` § "The desk's text"):
    that array is never drawn, the banner is, and the two may not come apart."""
    rows = re.findall(r"^musi@2C\.(\d+)\t[^\t]*\t(.+)$",
                      (REPO_ROOT / "translation/days/arrays.txt").read_text(), re.M)  # fmt: skip
    names = {int(n): text for n, text in rows}
    shared = {move: names[move + 12] for move in range(1, 20)}
    assert {move: ENTRIES[f"move.{move}"].text for move in shared} == shared


def test_the_strips_tile_one_page_in_reach_of_the_routine_that_draws_them():
    """`0x80036DE0` adds `u + w` and `v + h` in a byte, so a strip must end by texel 255; and
    no two strips may share a texel."""
    seen: set[tuple[int, int]] = set()
    for cell in range(ts.CELLS):
        x, y, w, h = ts.cell_box(cell)
        assert x + w <= 255 and y + h <= 255, f"strip {cell} at {x, y} runs past a byte"
        points = set(paint.points((x, y, w, h)))
        assert not points & seen, f"strip {cell} shares texels with another"
        seen |= points


def test_a_strip_is_bold_type_centred_with_room_for_its_edge():
    ink = ts.strip(Blocks(), Entry("sumo@move.0", "ab", "t:1"))
    x, y, w, h = paint.extent(ink)
    assert (w, h) == (13, 9)  # two blocks, each made 6 wide, a column of air between them
    assert abs((ts.CELL[0] - w) // 2 - x) <= 1 and y == ts.GLYPH_TOP + 2
    edged = paint.grown(ink, 1, 1, 1, 1)
    assert all(0 <= px < ts.CELL[0] and 0 <= py < ts.CELL[1] for px, py in edged)


def test_a_move_one_letter_too_long_for_its_strip_is_refused_not_cut():
    """A block letter is 6 px bold and a column of air: n letters are 7n - 1 wide, and a
    strip holds its width less a pixel of edge each side."""
    most = (ts.CELL[0] - 2 + 1) // 7
    ts.strip(Blocks(), Entry("sumo@move.0", "x" * most, "t:1"))
    with pytest.raises(TextureTextError, match="nothing is cut to fit"):
        ts.strip(Blocks(), Entry("sumo@move.0", "x" * (most + 1), "t:1"))


@pytest.mark.parametrize("dropped", ["move.20", "rank.king"])
def test_a_part_missing_a_key_is_refused(dropped):
    """The reader builds a part at a time, so a part is whole or refused: a move with no
    English would leave its strip blank, not Japanese."""
    part = dropped.split(".")[0]
    given = [e for key, e in ENTRIES.items() if key.startswith(part) and key != dropped]
    with pytest.raises(TextureTextError, match=re.escape(ts.FAMILY + dropped)):
        ts.sumo(None, None, Blocks(), given)
