"""The code-file arrays and the two surfaces that have no array at all.

Each array is walked the way its own reader walks it, so the interesting cases are the
ones where the shapes differ: an `E` item ends on `0x8000` and may contain newlines, an
`L` item ends on *any* bit-15 word, a select ends after the line count the executable
holds, and a raw array has no control word to stop at and ends where its reader's loop
bound says. Getting one wrong runs the walk into the next symbol, which is what the
`ArrayError`s below are for.
"""

from __future__ import annotations

import pytest

from boku.arrays import (
    ArrayDef,
    ArrayError,
    CodeLabel,
    SelectTables,
    describe_label,
    read_code_labels,
    walk_array,
)
from boku.glyphs import END_WORD, NEWLINE_WORD
from tests import synth_archive as synth
from tests.test_glyphs import table

BASE = 0x80010000


def image(raw: bytes) -> synth.FakeImage:
    return synth.FakeImage({"exe": (BASE, raw)})


def define(shape: str, spec) -> ArrayDef:
    return ArrayDef("exe", BASE, shape, spec, "a reader", "a purpose")


def lines_always(count: int):
    return lambda _type, _variant: count


# --- the four shapes ----------------------------------------------------------------------


def test_an_e_array_splits_on_its_terminators_and_keeps_newlines_inside_an_item():
    raw = synth.words(1, NEWLINE_WORD, 2, END_WORD, 3, END_WORD) + synth.words(0xFFFF)
    walk = walk_array(image(raw), define("E", 2), lines_always(0))
    assert walk.items == 2
    assert walk.end == BASE + 12
    assert walk.drawn_cells == 3
    assert walk.strings == ((BASE, BASE + 8), (BASE + 8, BASE + 12))
    assert walk.line_ids == ("exe@80010000.0", "exe@80010000.1")


def test_an_l_array_ends_an_item_at_any_bit_15_word():
    raw = synth.words(1, 2, END_WORD, 3, NEWLINE_WORD) + synth.words(0xFFFF)
    walk = walk_array(image(raw), define("L", 2), lines_always(0))
    assert walk.strings == ((BASE, BASE + 6), (BASE + 6, BASE + 10))
    assert walk.drawn_cells == 3


def test_a_select_is_one_string_however_many_lines_it_holds():
    raw = synth.words(1, NEWLINE_WORD, 2, NEWLINE_WORD, 3, NEWLINE_WORD) + synth.words(0xFFFF)
    walk = walk_array(image(raw), define("S", (3, 1)), lines_always(3))
    assert walk.items == 3, "the TSV counts a select's lines"
    assert walk.line_ids == ("exe@80010000",), "but it is one translatable unit"
    assert walk.strings == ((BASE, BASE + 12),)


def test_the_select_line_count_decides_where_the_walk_stops():
    """The count comes from `g_select_lines`; a wrong one eats the next symbol."""
    raw = synth.words(1, NEWLINE_WORD, 2, NEWLINE_WORD, 3, NEWLINE_WORD) + synth.words(0xFFFF)
    assert walk_array(image(raw), define("S", (3, 1)), lines_always(2)).end == BASE + 8


def test_a_raw_array_has_no_control_word_and_ends_where_its_loop_bound_says():
    raw = synth.words(1, 2, 0, 3, 4, 5) + synth.words(END_WORD)
    walk = walk_array(image(raw), define("R", (2, 3)), lines_always(0))
    assert walk.items == 2
    assert walk.end == BASE + 12
    assert walk.drawn_cells == 5, "the blank cell is not counted as a drawn glyph in the TSV"
    assert walk.line_ids == ("exe@80010000.0", "exe@80010000.1")


def test_a_raw_array_that_runs_into_a_control_word_is_refused():
    """It means the row or cell count is wrong and the walk has left the array."""
    raw = synth.words(1, 2, END_WORD, 3)
    with pytest.raises(ArrayError, match="raw array holds a control word"):
        walk_array(image(raw), define("R", (2, 2)), lines_always(0))


def test_an_e_item_containing_a_page_break_is_refused():
    """Only `0x8001` occurs inside an item; anything else means the shape is wrong."""
    raw = synth.words(1, 0x8002, 2, END_WORD)
    with pytest.raises(ArrayError, match="inside an E item"):
        walk_array(image(raw), define("E", 1), lines_always(0))


def test_an_overlay_array_is_named_by_its_file_offset_and_the_exe_by_its_ram_address():
    assert define("E", 1).line_id_prefix == "exe@80010000"
    overlay = ArrayDef("hhon", 0x80079A08 + 0x5328, "E", 1, "r", "p")
    assert overlay.line_id_prefix == "hhon@5328"
    assert overlay.file_offset == 0x5328
    assert overlay.file_name == "HHON.OVL"


# --- labels built from instruction immediates -------------------------------------------------


def mips(op: int, rs: int, rt: int, imm: int) -> bytes:
    return ((op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)).to_bytes(4, "little")


def jal(target: int) -> bytes:
    return ((0x03 << 26) | ((target & 0x03FFFFFF) >> 2)).to_bytes(4, "little")


NOP = bytes(4)
JR_RA = (0x03E00008).to_bytes(4, "little")
GLYPH_DRAW = 0x8002BA2C


def test_a_label_is_read_out_of_the_immediates_its_draws_are_given(monkeypatch):
    code = (
        mips(0x09, 0, 4, 0x21F)  # addiu a0, zero, 0x21F
        + jal(GLYPH_DRAW)
        + NOP
        + jal(GLYPH_DRAW)
        + mips(0x09, 0, 4, 0x382)  # the delay slot carries this call's id
        + JR_RA
        + NOP
        + mips(0x09, 0, 4, 0x999)  # past the return: must not be read
    )
    monkeypatch.setattr("boku.arrays.CODE_LABELS", (("exe", BASE, "a label"),))
    (label,) = read_code_labels(image(code))
    assert label.runs == ((0x21F, 0x382),)
    assert label.line_id == f"exe@code:{BASE:X}"
    assert 0x999 not in label.glyph_ids, "the scan stops at jr ra and its delay slot"


def test_a_draw_whose_id_is_computed_breaks_the_run(monkeypatch):
    code = (
        mips(0x09, 0, 4, 0x3C)
        + jal(GLYPH_DRAW)
        + NOP
        + jal(GLYPH_DRAW)  # no literal since the last draw: a computed digit
        + NOP
        + mips(0x09, 0, 4, 0x1B8)
        + jal(GLYPH_DRAW)
        + NOP
        + JR_RA
        + NOP
    )
    monkeypatch.setattr("boku.arrays.CODE_LABELS", (("exe", BASE, "a label"),))
    (label,) = read_code_labels(image(code))
    assert label.runs == ((0x3C,), (0x1B8,))


def test_a_call_to_something_other_than_glyph_draw_is_not_a_label(monkeypatch):
    code = mips(0x09, 0, 4, 0x21F) + jal(0x80012345) + NOP + JR_RA + NOP
    monkeypatch.setattr("boku.arrays.CODE_LABELS", (("exe", BASE, "a label"),))
    (label,) = read_code_labels(image(code))
    assert label.runs == ()


def test_a_label_is_rendered_with_its_runs_separated():
    # Full-width cells: the sheet has no half-width set (research/font.md).
    sheet = table({0x3C: "８", 0x1B8: "月"})  # noqa: RUF001
    label = CodeLabel("title", 0x8007BB60, ((0x3C, 0x1B8), (0x999,)), (), "the date")
    assert describe_label(label, sheet) == "８月 / {G:2457}"


# --- the walk's bounds ------------------------------------------------------------------------


def test_a_count_that_runs_off_the_end_of_the_image_names_the_array():
    """An `E` array told to find more items than the symbol holds walks to the image's end.

    It used to leave `struct` to raise `IndexError: tuple index out of range` at whatever
    depth it reached, which no caller catches and which names neither the array nor the
    file.
    """
    raw = synth.words(1, END_WORD, 2, END_WORD)  # two items, and nothing after them
    with pytest.raises(ArrayError, match=r"ran off the end of SCPS_100\.88"):
        walk_array(image(raw), define("E", 3), lines_always(0))


def test_a_raw_array_that_does_not_fit_in_its_file_is_refused():
    raw = synth.words(1, 2, 3)
    with pytest.raises(ArrayError, match="does not fit"):
        walk_array(image(raw), define("R", (2, 3)), lines_always(0))


# --- the select tables ------------------------------------------------------------------------


def select_tables() -> SelectTables:
    builder = synth.ExeBuilder()
    builder.select_tables(bytes([0, 3, 6, 9, 0, 0, 0, 0]), bytes(range(1, 13)), bytes(12))
    return SelectTables(synth.FakeExe(builder.build()))


def test_a_select_shape_is_read_through_its_base_table():
    tables = select_tables()
    assert tables.lines(1, 1) == 1, "g_select_lines[g_select_base[0] + 0]"
    assert tables.lines(2, 3) == 6, "g_select_lines[3 + 2]"
    assert tables(4, 1) == 10


@pytest.mark.parametrize(
    ("select_type", "variant"),
    [(0, 1), (1, 0), (-1, 1), (1, -1), (9, 1), (4, 9)],
)
def test_a_select_index_outside_its_table_is_refused_rather_than_wrapped(
    select_type: int, variant: int
):
    """`type` or `variant` 0 used to index `base[-1]` and `lines[-1]`, which is a real
    entry at the far end of the table -- and a *different* one in each of the two readers
    that implemented this lookup."""
    with pytest.raises(ArrayError):
        select_tables().shape(select_type, variant)
