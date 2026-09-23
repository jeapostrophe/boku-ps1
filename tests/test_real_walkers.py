"""The fixed-pitch text walkers, run instruction by instruction on the patched executable.

`PLAN TXT-05`: every text surface other than the dialogue steps its pen by a literal (12,
or 10 for one help line), and `asm/` turns each step into a lookup in the advance table. What
a player sees is the x each glyph is drawn at, so that is what is asserted: the game's own
walker is run in `tests.mips` over a string placed in RAM, `glyph_draw` is stubbed to record
its pen, and the x positions are compared with the advances the build's own cell map
reports. Two things must both hold at every hooked site:

* **English moves by its advance**, not by the stock literal;
* **Japanese keeps the surface's stock pitch.** The table holds the dialogue's 14 for every
  cell that is not English, so a body that took the table's value for a Japanese glyph drew
  an untranslated menu at 14 px where the game draws 12 -- measured on the card-check
  screen's second line before this file existed, 32 px wider than stock.

The same string through the retail executable is the control: stock steps 12 for both.
Needs the import and armips; skipped without them.
"""

from __future__ import annotations

import json
import struct

import pytest

from boku.archive import EXE_NAME, OVERLAY_LOAD_ADDRESS
from boku.glyphs import END_WORD as END
from boku.glyphs import NEWLINE_WORD as NEWLINE
from boku.layout import ANSWER_PAIR, CellMapEncoder, answer_pair_code, lay_out_answer_pair
from tests.mips import Machine
from tests.test_vwf_prototype import (
    NEEDS_ARMIPS,
    NEEDS_IMPORT,
    build_without_a_disc,
    vwf_prototype,
)

pytestmark = [NEEDS_IMPORT, NEEDS_ARMIPS]

TEXT = 0x80100000
"""Where a test string is put: main RAM above every image and below the stack."""

HELP_TEXT = 0x80029B20
"""`g_help_text`, the controls-help lines: the Japanese these tests draw."""


@pytest.fixture(scope="module")
def built(tmp_path_factory, archive):
    """`(patched images, stock images, armips symbols, English cell -> (id, advance),
    ids the advance table covers)`."""
    tool = vwf_prototype()
    captured: dict[str, tuple] = {}
    assemble = tool.assemble

    def capture(*arguments, **keywords):
        captured["it"] = assemble(*arguments, **keywords)
        return captured["it"]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tool, "assemble", capture)
        manifest = build_without_a_disc(tool, tmp_path_factory.mktemp("walkers"), patch)
    images, symbols = captured["it"]
    stock = {EXE_NAME: archive.exe} | {
        name: archive.blob(archive.member(name)) for name in tool.DRAWING_OVERLAYS
    }
    cells = {c: (cell["id"], cell["advance"]) for c, cell in manifest["cells"].items()}
    return images, stock, symbols, cells, manifest["table"]["ids"]


def machine(images: dict[str, bytes], overlay: str | None = None) -> Machine:
    tool = vwf_prototype()
    m = Machine()
    m.load(tool.EXE_LOAD_BIAS, images[EXE_NAME])
    if overlay:
        m.load(tool.OVERLAY_BASE, images[overlay])
    return m


def japanese(stock_exe: bytes, count: int) -> list[int]:
    """`count` glyph ids a Japanese menu really draws: the help screen's first line."""
    help_text = HELP_TEXT - vwf_prototype().EXE_LOAD_BIAS
    ids = list(struct.unpack_from(f"<{count}H", stock_exe, help_text))
    assert all(not word & 0x8000 for word in ids), "the help line is shorter than asked"
    return ids


def past_the_table(stock_exe: bytes, table_ids: int) -> int:
    """A glyph id Japanese text draws that the advance table does not reach -- the id
    `vwf_lookup_at` never reads a table byte for. The first on the help screen."""
    start = HELP_TEXT - vwf_prototype().EXE_LOAD_BIAS
    words = struct.unpack_from("<144H", stock_exe, start)
    found = next((w for w in words if table_ids <= w < 0x8000), None)
    assert found is not None, "no help-screen glyph is past the table; pick another source"
    return found


def pens(draws) -> list[int]:
    return [x for _, x, _ in draws]


def expected(start: int, steps: list[int]) -> list[int]:
    out = [start]
    for step in steps[:-1]:
        out.append(out[-1] + step)
    return out


# --- text_draw_line_h / text_draw_h: item names, kite names, fishing, descriptions ----------------

TEXT_DRAW_LINE_H = 0x800437F4
TEXT_DRAW_H = 0x80043864


@pytest.mark.parametrize("walker", [TEXT_DRAW_LINE_H, TEXT_DRAW_H])
def test_the_item_walkers_advance_english_by_its_width_and_japanese_by_12(built, walker):
    images, stock, _, cells, table_ids = built
    word = "Wil"
    ids = [cells[c][0] for c in word]
    kana = japanese(stock[EXE_NAME], 3)

    far = past_the_table(stock[EXE_NAME], table_ids)
    for image, english_steps in ((images, [cells[c][1] for c in word]), (stock, [12, 12, 12])):
        m = machine(image)
        m.call(walker, m.halfwords(TEXT, [*ids, END]), 40, 90)
        assert pens(m.draws) == expected(40, english_steps), "English"
        assert [glyph for glyph, _, _ in m.draws] == ids

        m = machine(image)
        m.call(walker, m.halfwords(TEXT, [*kana, END]), 40, 90)
        assert pens(m.draws) == expected(40, [12, 12, 12]), "Japanese keeps the stock pitch"

        m = machine(image)
        m.call(walker, m.halfwords(TEXT, [far, far, END]), 40, 90)
        assert pens(m.draws) == [40, 52], "an id past the table keeps the stock pitch"


def test_a_description_line_break_returns_the_pen_to_the_left_edge(built):
    images, _, _, cells, _ = built
    first, second = [cells[c][0] for c in "ab"], [cells["c"][0]]
    m = machine(images)
    m.call(TEXT_DRAW_H, m.halfwords(TEXT, [*first, NEWLINE, *second, END]), 184, 126)
    assert m.draws == [
        (first[0], 184, 126),
        (first[1], 184 + cells["a"][1], 126),
        (second[0], 184, 142),
    ]


# --- the controls-help screen (START in free roam) ----------------------------------------------

TEXT_DRAW_RIGHT = 0x80035360
HELP_LINE_DRAW = 0x80035448


def test_text_draw_right_lands_glyph_zero_at_x_and_steps_by_width(built):
    """Its name says right-aligned; it is not: a count pass adds a step per glyph, then the
    draw pass walks back subtracting the same steps, so glyph 0 lands at x. Both passes
    must take the same widths or the line slides."""
    images, stock, _, cells, _ = built
    word = "Wil"
    ids = [cells[c][0] for c in word]
    kana = japanese(stock[EXE_NAME], 3)
    m = machine(images)
    m.call(TEXT_DRAW_RIGHT, m.halfwords(TEXT, [*ids, NEWLINE]), 172, 44)
    assert sorted(m.draws, key=lambda d: d[1]) == [
        (glyph, x, 44)
        for glyph, x in zip(ids, expected(172, [cells[c][1] for c in word]), strict=True)
    ]
    for image in (images, stock):
        m = machine(image)
        m.call(TEXT_DRAW_RIGHT, m.halfwords(TEXT, [*kana, NEWLINE]), 172, 44)
        assert sorted(pens(m.draws)) == [172, 184, 196]


def test_the_help_screen_s_ten_pixel_line_keeps_ten_for_japanese(built):
    images, stock, _, cells, _ = built
    word = "Wil"
    ids = [cells[c][0] for c in word]
    kana = japanese(stock[EXE_NAME], 3)
    m = machine(images)
    m.halfwords(HELP_TEXT, [*ids, NEWLINE])
    m.call(HELP_LINE_DRAW, 0, 150, 44)
    assert pens(m.draws) == expected(150, [cells[c][1] for c in word])
    for image in (images, stock):
        m = machine(image)
        m.halfwords(HELP_TEXT, [*kana, NEWLINE])
        m.call(HELP_LINE_DRAW, 0, 150, 44)
        assert pens(m.draws) == [150, 160, 170]


# --- TITLE.OVL: the step bodies of surfaces 17, 19, 20 ------------------------------------------

S0, S1, S5, V1 = 16, 17, 21, 3


@pytest.mark.parametrize(
    ("body", "pointer", "pen_in", "pen_out"),
    [
        ("vwf_step_s5_s0", S0, S5, S5),
        ("vwf_step_v1_s0_s1", S1, S0, V1),
        ("vwf_step_s1_s0_next", S0, S1, S1),
    ],
)
def test_a_title_walker_steps_japanese_by_its_stock_12(built, body, pointer, pen_in, pen_out):
    """The step bodies read the id just drawn at -2(pointer). Japanese at 14 was the
    card-check screen's second line drawn 32 px wider than the retail game draws it."""
    images, stock, symbols, cells, table_ids = built
    for glyph, step in (
        (cells["W"][0], cells["W"][1]),
        (japanese(stock[EXE_NAME], 1)[0], 12),
        (past_the_table(stock[EXE_NAME], table_ids), 12),
    ):
        m = machine(images, "TITLE.OVL")
        m.halfwords(TEXT, [glyph, END])
        m.call(symbols[body], registers={pointer: TEXT + 2, pen_in: 100})
        assert m.regs[pen_out] == 100 + step, f"glyph {glyph}"
        if body.endswith("_next"):
            assert m.regs[pointer] == TEXT + 4, "the body steps the pointer past the next word"


def test_the_manifest_cells_are_the_ones_the_table_holds(built):
    """The walkers' expectations come from the manifest's cell map; that map must be the
    table the executable carries, or every test above measures the build's own typing."""
    images, _, symbols, cells, _ = built
    tool = vwf_prototype()
    table = symbols["vwf_advance"] - tool.EXE_LOAD_BIAS
    exe = images[EXE_NAME]
    for character, (glyph, advance) in cells.items():
        assert exe[table + glyph] == advance, json.dumps(character)


# --- TITLE.OVL surface 18: the card screens' two answers -------------------------------------

ANSWERS_DRAW = 0x8007CF7C
ANSWERS = 0x80081480
"""The five raw glyphs `title@7A78.0` names: the first answer, then the second."""


def test_the_two_answers_are_proportional_and_the_second_starts_where_the_stock_one_did(built):
    """Record 1 of `g_mc_msg` has a layout past 1, so the drawer runs. Stock: はい at 0x70 and
    0x7C, いいえ from 0xAC. English (with SPLIT rewritten as the build rewrites it): the
    first answer set proportionally from 0x70, the second from the same 0xAC."""
    images, stock, _, cells, _ = built
    japanese_words = list(
        struct.unpack("<5H", stock["TITLE.OVL"][ANSWERS - OVERLAY_LOAD_ADDRESS :][:10])
    )
    for image in (images, stock):
        m = machine(image, "TITLE.OVL")
        m.call(ANSWERS_DRAW, 1)
        assert pens(m.draws) == [0x70, 0x7C, 0xAC, 0xB8, 0xC4], "Japanese as the retail game"
        assert [glyph for glyph, _, _ in m.draws] == japanese_words

    encoder = CellMapEncoder(cells)
    original = stock["TITLE.OVL"][ANSWERS - OVERLAY_LOAD_ADDRESS :][:10]
    for first, second in (("Yes", "No"), ("Ok", "No")):
        # The build's own layout and code words, not a copy of their arithmetic.
        laid = lay_out_answer_pair(
            ANSWER_PAIR.line_id, f"{first} | {second}", original, encoder, 299
        )
        m = machine(images, "TITLE.OVL")
        m.halfwords(ANSWERS, list(laid.words))
        for ram, word in answer_pair_code(laid).items():
            m.write(ram, 4, word)
        m.call(ANSWERS_DRAW, 1)
        assert pens(m.draws) == [
            *expected(ANSWER_PAIR.first_x, [cells[c][1] for c in first]),
            *expected(ANSWER_PAIR.second_x, [cells[c][1] for c in second]),
        ], f"{first} | {second}"
