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
from boku.asm_source import asm_equate
from boku.boxes import box_for
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
        (second[0], 184, 126 + asm_equate("DESC_LINE_STEP", "walkers.asm")),
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


# --- sysmsg_draw (surface 9): insect names, returning a pixel width -------------------------

SYSMSG_DRAW = 0x800379EC
"""`sysmsg_draw(text, line, x, y, vertical)`: line `line` of a list, across when the fifth
argument is 0 (every call in every image); returns what its callers place the next thing by."""


def test_sysmsg_draw_returns_the_line_s_pixel_width_and_steps_by_it(built):
    """Its callers used the glyph count times 12 to place what follows the name, and to
    right-align it in 96 px (MUSI measures a name by drawing it off screen). Patched it
    returns the width in pixels and steps x by it; Japanese is 12 a glyph, so the pixels
    are exactly what every caller computed before."""
    images, stock, _, cells, _ = built
    word, kana = "Wil", japanese(stock[EXE_NAME], 3)
    english = ([cells[c][0] for c in word], [cells[c][1] for c in word])
    for image, (ids, want), returned in (
        (images, english, sum(english[1])),
        (images, (kana, [12] * 3), 36),
        (stock, (kana, [12] * 3), 3),  # the retail count, which its callers multiply by 12
    ):
        m = machine(image)
        width = m.call(SYSMSG_DRAW, m.halfwords(TEXT, [*ids, NEWLINE]), 0, 40, 90)
        assert width == returned, f"{ids}"
        assert pens(m.draws) == expected(40, want)


def run_slice(image: dict[str, bytes], overlay: str | None, start: int, end: int, **regs):
    """The instructions [start, end) of the patched code, run alone with `regs` set: a slice
    copied to scratch RAM and closed with `jr ra`, so a consumer's arithmetic is the file's."""
    tool = vwf_prototype()
    m = machine(image, overlay)
    base = tool.EXE_LOAD_BIAS if overlay is None else tool.OVERLAY_BASE
    blob = image[EXE_NAME if overlay is None else overlay]
    code = blob[start - base : end - base] + struct.pack("<2I", 0x03E00008, 0)
    scratch = 0x80180000
    m.load(scratch, code)
    names = {"v0": 2, "v1": 3, "s0": 16, "s1": 17, "s3": 19, "s5": 21}
    m.call(scratch, registers={names[k]: v for k, v in regs.items()})
    return m


CONSUMERS = [
    (None, 0x8003FF98, 0x8003FFA4, "v1"),  # cage_hud_draw: the next item after the name
    ("HHON.OVL", 0x8007C46C, 0x8007C478, "v1"),
    ("MUSI.OVL", 0x8007D474, 0x8007D480, "s1"),
    ("MUSI.OVL", 0x8007D86C, 0x8007D890, "s0"),  # right-aligned in the field, via sllv s5
    ("MUSI.OVL", 0x8007D910, 0x8007D934, "s0"),  # right-aligned
]
REGISTER = {"v1": 3, "s0": 16, "s1": 17}


@pytest.mark.parametrize(("overlay", "start", "end", "out"), CONSUMERS)
@pytest.mark.parametrize("glyphs", [1, 3, 8])
def test_a_count_consumer_given_pixels_computes_what_stock_did_from_the_count(
    built, overlay, start, end, out, glyphs
):
    """The retail slice given the count and the patched slice given the width that
    Japanese now returns (12 a glyph) must leave the same value -- the stock arithmetic,
    `sllv` by `s5` included (s5 = 1 where MUSI sets it), is the fixture, not a retyped
    formula."""
    images, stock, _, _, _ = built
    before = run_slice(stock, overlay, start, end, v0=glyphs, s3=TEXT, s5=1)
    after = run_slice(images, overlay, start, end, v0=12 * glyphs, s3=TEXT, s5=1)
    assert after.regs[REGISTER[out]] == before.regs[REGISTER[out]]


@pytest.mark.parametrize(("overlay", "start", "end", "out"), CONSUMERS)
def test_a_count_consumer_places_by_an_english_width(built, overlay, start, end, out):
    """An English name 61 px wide: the next item 61 after it, or the right-aligned name at
    the field's width less 61 (the field is what the stock computes for no glyphs)."""
    images, stock, _, _, _ = built
    after = run_slice(images, overlay, start, end, v0=61, s3=TEXT, s5=1).regs[REGISTER[out]]
    if out == "s0":
        field = run_slice(stock, overlay, start, end, v0=0, s3=TEXT, s5=1).regs[16]
        assert after == field - 61
    else:
        assert after == 61


# --- surfaces 11, 25, 26: fish names and sumo move names ---------------------------------------


FISH_NAME_DRAW = 0x8003C5EC
FISH_NAMES = 0x8003DA4C
FISH_INDEX = 0x8003E2A1
"""`sys_title_draw` reads the fish's line index here (`lbu a1,9(a2)`, a2 = 0x8003E298)."""
MOVE_NAME_DRAW = (0x80084F64, 0x800850D8)
MOVE_NAMES = 0x80079A34
"""`musi@2C`, where both walkers' lui/addiu pair points on the retail overlay."""


def test_the_fish_name_walker_steps_english_by_width_and_japanese_by_12(built):
    images, stock, _, cells, _ = built
    kana = japanese(stock[EXE_NAME], 3)
    for image, ids, steps in (
        (images, [cells[c][0] for c in "Wil"], [cells[c][1] for c in "Wil"]),
        (images, kana, [12] * 3),
        (stock, kana, [12] * 3),
    ):
        m = machine(image)
        m.halfwords(FISH_NAMES, [*ids, NEWLINE])
        m.write(FISH_INDEX, 1, 0)
        m.call(FISH_NAME_DRAW)
        assert pens(m.draws) == expected(m.draws[0][1], steps), f"{ids}"


@pytest.mark.parametrize("walker", MOVE_NAME_DRAW)
def test_the_sumo_move_walkers_step_english_by_width_and_japanese_by_12(built, walker):
    images, stock, _, cells, _ = built
    kana = japanese(stock[EXE_NAME], 3)
    for image, ids, steps in (
        (images, [cells[c][0] for c in "Wil"], [cells[c][1] for c in "Wil"]),
        (images, kana, [12] * 3),
        (stock, kana, [12] * 3),
    ):
        m = machine(image, "MUSI.OVL")
        m.halfwords(MOVE_NAMES, [*ids, NEWLINE])
        m.call(walker, 0, 0)
        assert pens(m.draws) == expected(m.draws[0][1], steps), f"{ids}"


# --- the insect box: hhon_entry_draw (the grid) and hhon_text_scroll_v (the notebook) ----------

HHON = "HHON.OVL"
GRID_DRAW = 0x8007C278
NOTEBOOK_DRAW = 0x8007C1C4
NOTEBOOK_GLYPH = 0x8002B9FC
"""The notebook walker's glyph drawer (a clipped `glyph_draw`); recorded as a stub."""
PLACEHOLDER = 60
SCROLL = 200


def _hhon_draws(image, walker, words, index=0):
    m = machine(image, HHON)
    m.stubs[NOTEBOOK_GLYPH] = []
    text = m.halfwords(TEXT, words)
    if walker == GRID_DRAW:
        m.call(GRID_DRAW, text, index)
        return [(x, y) for _, x, y in m.draws]
    m.call(NOTEBOOK_DRAW, text, 0, SCROLL, index)
    return [(x, y) for _, x, y, *_ in m.stubs[NOTEBOOK_GLYPH]]


@pytest.mark.parametrize("walker", [GRID_DRAW, NOTEBOOK_DRAW])
@pytest.mark.parametrize("index", [0, PLACEHOLDER])
def test_an_untranslated_insect_entry_keeps_its_retail_columns(built, walker, index):
    """Japanese with a column break: the patched walker draws every glyph where the retail
    one does -- the stock images' own run is the fixture."""
    images, stock, _, _, _ = built
    kana = japanese(stock[EXE_NAME], 3)
    words = [*kana[:2], NEWLINE, kana[2], END]
    retail = _hhon_draws(stock, walker, words, index)
    assert len({x for x, _ in retail}) == 2, "the fixture draws no second column"
    assert _hhon_draws(images, walker, words, index) == retail


@pytest.mark.parametrize(
    ("walker", "line_id", "pitch"),
    [(GRID_DRAW, "hhon@5328.0", 11), (NOTEBOOK_DRAW, None, 12)],
)
@pytest.mark.parametrize("index", [0, PLACEHOLDER])
def test_an_english_insect_entry_is_drawn_in_rows(built, walker, line_id, pitch, index):
    """English: across by each glyph's width, a break down one row (11 px on the grid,
    Jay's option A; 12 on the notebook) and back to the left edge -- the grid's from its
    box (`text-boxes.tsv`), the notebook's `HHON_NB_LEFT`."""
    images, _, _, cells, _ = built
    first, second = [cells[c][0] for c in "ab"], [cells["c"][0]]
    draws = _hhon_draws(images, walker, [*first, NEWLINE, *second, END], index)
    left = box_for(line_id).x if line_id else asm_equate("HHON_NB_LEFT", "hhon_resident.asm")
    (x0, y0), (x1, y1), (x2, y2) = draws
    assert (x0, x1 - x0, x2) == (left, cells["a"][1], left)
    assert (y1, y2 - y0) == (y0, pitch)
    if line_id:
        assert y0 == 16, "Jay's option A (2026-09-24): rows from y 16"
    else:  # the notebook's first row hangs where retail's first column did
        kana = japanese(built[1][EXE_NAME], 1)
        assert y0 == _hhon_draws(built[1], walker, [*kana, END], index)[0][1]


SEX_MARK = 37
"""♂ (`GlyphTable`): a sheet cell with no English advance, which real entries draw inside
English ("Miyama Stag Beetle ♂.")."""


@pytest.mark.parametrize(("walker", "pitch"), [(GRID_DRAW, 11), (NOTEBOOK_DRAW, 12)])
def test_a_sheet_cell_stays_in_an_english_entry_s_row(built, walker, pitch):
    """Narrowest: one ♂ between two letters. The mark steps across by the sheet's 12 like
    any cell of the row, not down a column, and the next row starts one pitch below: the
    entry is English from its first glyph. (An empty row is not drawn: the retail loop
    draws the word at a break's target before testing it, and no entry has one.)"""
    images, _, _, cells, _ = built
    a, b, c = (cells[ch][0] for ch in "abc")
    draws = _hhon_draws(images, walker, [a, SEX_MARK, b, NEWLINE, c, END])
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = draws
    assert (x1 - x0, x2 - x1, x3) == (cells["a"][1], 12, x0)
    assert (y1, y2, y3 - y0) == (y0, y0, pitch)
