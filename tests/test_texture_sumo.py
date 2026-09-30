"""`boku.texture_sumo` without a disc: the banner's layout, the tracked English, the refusals.

The rebuilt textures and the bout on Beetle are `tests/test_real_texture_sumo.py`'s.
"""

from __future__ import annotations

import re

import pytest

from boku import REPO_ROOT
from boku import texture_paint as paint
from boku import texture_sumo as ts
from boku.texture_text import Entry, TextureTextError, family_entries

ENTRIES = family_entries(ts.FAMILY)


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


def test_a_real_sumo_technique_is_one_word_as_english_sumo_writes_it():
    """One word, capitalised (glossary § 4b). The techniques are the moves with a gloss, and
    `arrays.txt` is held to the same words by the test above."""
    names = {move: ENTRIES[f"move.{move}"].text for move in ts.GLOSSED}
    assert {m: n for m, n in names.items() if not re.fullmatch(r"[A-Z][a-z]+", n)} == {}


def test_the_strips_tile_one_page_in_reach_of_the_routine_that_draws_them():
    """`0x80036DE0` adds `u + w` and `v + h` in a byte, so a strip must end by texel 255; and
    no two strips may share a texel. The 22 moves' strips are the whole first page."""
    seen: set[tuple[int, int]] = set()
    for cell in range(ts.MOVES):
        x, y, w, h = ts.cell_box(cell)
        assert x + w <= 255 and y + h <= 255, f"strip {cell} at {x, y} runs past a byte"
        points = set(paint.points((x, y, w, h)))
        assert not points & seen, f"strip {cell} shares texels with another"
        seen |= points


def test_the_heading_is_on_the_third_page_where_its_routine_places_it():
    """The heading's patched words, traced in order (the few stores they make, from the
    registers they load): its `u`, its `v`'s low byte and its page are `HEADING_BOX`'s, and
    the box ends by texel 255. On the built overlay the whole routine is run by
    `tests/test_real_texture_sumo.py`."""
    regs, stored = {}, {}
    for ram, _, word in sorted(ts.banner_code()):
        if ram >= MOVE_ROUTINE:
            break
        op, rt, value = word >> 26, word >> 16 & 31, word & 0xFFFF
        if op == 0x09 and word >> 21 & 31 == ts.ZERO:  # addiu $rt, $zero, value
            regs[rt] = value
        elif op == 0x29 and word >> 21 & 31 == ts.V0:  # sh $rt, value($v0)
            stored[value] = regs[rt]
    x, y, w, h = ts.HEADING_BOX
    page = (ts.HEADING_PAGE_X - ts.PAGE_X) * 4  # 4bpp: four texels a VRAM halfword
    assert (stored[0], stored[2] & 0xFF, stored[0x10]) == (x - page, y, ts.HEADING_PAGE_X)
    assert x - page + w <= 255 and y + h <= 255
    assert ts.HEADING_PAGE_X % 64 == 0, "a texture page starts on a multiple of 64"


MOVE_ROUTINE = 0x800865F8


def test_the_heading_is_centred_over_the_strips_as_a_strip_would_centre_it():
    ink = ts.heading(Blocks(), Entry("sumo@move.heading", "abc", "t:1"))
    as_strip = ts.strip(Blocks(), Entry("sumo@move.0", "abc", "t:1"))
    assert ts.HEADING_X + paint.extent(ink)[0] == ts.STRIP_X + paint.extent(as_strip)[0]


def test_a_name_with_a_gloss_is_two_lines_each_centred_with_room_for_its_edge():
    name, gloss = Entry("sumo@move.0", "ab", "t:1"), Entry("sumo@move.gloss-0", "abcd", "t:2")
    ink = ts.strip(Blocks(), name, gloss)
    over = {(x, y) for x, y in ink if y < ts.GLOSS_TOP}
    under = ink - over
    for line, top, letters in ((over, ts.NAME_TOP, 2), (under, ts.GLOSS_TOP, 4)):
        x, y, w, h = paint.extent(line)
        assert (w, h) == (7 * letters - 1, 9)  # each block made 6 wide, a column of air between
        assert abs((ts.CELL[0] - w) // 2 - x) <= 1 and y == top + 2
    edged = paint.grown(ink, 1, 1, 1, 1)
    assert all(0 <= px < ts.CELL[0] and 0 <= py < ts.CELL[1] for px, py in edged)


def test_a_name_with_no_gloss_sits_midway_between_the_two_lines():
    alone = ts.strip(Blocks(), Entry("sumo@move.7", "ab", "t:1"))
    both = ts.strip(Blocks(), Entry("sumo@move.0", "ab", "t:1"), Entry("g", "ab", "t:2"))
    _, top, _, h = paint.extent(alone)
    _, first, _, span = paint.extent(both)
    assert abs((top + h / 2) - (first + span / 2)) <= 0.5


@pytest.mark.parametrize("which", ["name", "gloss"])
def test_a_line_one_letter_too_long_for_its_strip_is_refused_not_cut(which):
    """A block letter is 6 px bold and a column of air: n letters are 7n - 1 wide, and a
    strip holds its width less a pixel of edge each side."""
    most = (ts.CELL[0] - 2 + 1) // 7

    def lines(n):
        name = "x" * (n if which == "name" else 1)
        gloss = "x" * (n if which == "gloss" else 1)
        return Entry("sumo@move.0", name, "t:1"), Entry("sumo@move.gloss-0", gloss, "t:2")

    ts.strip(Blocks(), *lines(most))
    with pytest.raises(TextureTextError, match="nothing is cut to fit"):
        ts.strip(Blocks(), *lines(most + 1))


class Reaching(Blocks):
    """Blocks, but "q" hangs to the glyph cell's last row and "t" rises to its second."""

    def ink(self, text):
        drop = {"q": 1, "t": -1}
        return {(x, y + drop.get(text[x // 6], 0)) for x, y in super().ink(text)}


def test_a_gloss_whose_letters_would_touch_the_names_is_refused():
    """A descender on the cell's last row and a capital on the next line's second leave no
    row for the edge between them: refused, not drawn run together."""
    ts.strip(Reaching(), Entry("sumo@move.0", "q", "t:1"), Entry("sumo@move.gloss-0", "a", "t:2"))
    with pytest.raises(TextureTextError, match="touches the name over it"):
        ts.strip(Reaching(), Entry("sumo@move.0", "q", "t:1"),
                 Entry("sumo@move.gloss-0", "t", "t:2"))  # fmt: skip


@pytest.mark.parametrize("dropped", ["move.20", "rank.king"])
def test_a_part_missing_a_key_is_refused(dropped):
    """The reader builds a part at a time, so a part is whole or refused: a move with no
    English would leave its strip blank, not Japanese."""
    part = dropped.split(".")[0]
    given = [e for key, e in ENTRIES.items() if key.startswith(part) and key != dropped]
    with pytest.raises(TextureTextError, match=re.escape(ts.FAMILY + dropped)):
        ts.sumo(None, None, Blocks(), given)
