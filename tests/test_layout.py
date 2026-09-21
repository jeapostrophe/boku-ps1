"""Breaking English into lines and pages, measured in pixels rather than in characters.

Every number the wrapper is checked against here comes from the encoder it was given, not
from a character count written into the test: a test that asserted "43 characters fit" and
a wrapper that counted characters would agree with each other and with nothing the screen
does. The widths come out of `measure`, and the box out of `research/vwf-prototype.md`'s
measurements on the running prototype.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from boku.glyphs import END_WORD, NEWLINE_WORD, PAD_WORD, PAGE_WORD, GlyphTable, words_of
from boku.layout import (
    DIALOGUE_BAND,
    SPEECH_MARKS,
    STOCK_ADVANCE,
    BoxSpec,
    CellMapEncoder,
    LayoutError,
    StockEncoder,
    lay_out_array,
    lay_out_message,
    lay_out_select,
    measure,
    unencodable,
    wrap,
)
from tests.test_vwf_prototype import vwf_layout, vwf_prototype

REPO_ROOT = Path(__file__).resolve().parent.parent


def pencil_rows() -> int:
    """How many of the band's last rows the next-page pencil sits in.

    Read out of `asm/dialogue.asm`'s `PENCIL_Y equ (BAND_Y + BAND_H - N)`, which is the one
    home of that number: the marker moves with the band, so a band moved in the assembly
    and a guard left behind here would be a wrap that guards the wrong line.
    """
    source = (REPO_ROOT / "asm" / "dialogue.asm").read_text(encoding="utf-8")
    found = re.search(r"PENCIL_Y\s+equ\s+\(BAND_Y \+ BAND_H - (\d+)\)", source)
    assert found, "asm/dialogue.asm no longer places the pencil relative to the band"
    return int(found.group(1))


CELLS = {
    " ": (10, 4),
    "i": (300, 2),
    "m": (301, 10),
    "a": (302, 6),
    "b": (303, 6),
    "c": (304, 6),
    "!": (19, 2),
}
"""A cell map in the shape `tools/vwf/build_prototype.py` writes: id and pixel advance."""


def cell_encoder(**kwargs) -> CellMapEncoder:
    return CellMapEncoder(CELLS, **kwargs)


def raw(*words: int) -> bytes:
    return b"".join(w.to_bytes(2, "little") for w in words)


# --- measuring and wrapping --------------------------------------------------------------------


def test_a_line_is_measured_by_the_encoders_advances_not_by_its_length():
    encoder = cell_encoder()
    assert measure(encoder, "mmm") == 30
    assert measure(encoder, "iii") == 6
    assert len("mmm") == len("iii"), "the point: same characters, five times the width"


def test_the_wrapper_breaks_where_the_pixels_run_out():
    """The break moves with the width function, which is what a fixed-pitch test cannot see."""
    encoder = cell_encoder()
    box = BoxSpec(width=measure(encoder, "abc abc"), lines=4, name="narrow")
    assert len("abc abc abc") == len("iii iii iii")
    assert wrap(encoder, "abc abc abc", box) == ["abc abc", "abc"]
    assert wrap(encoder, "iii iii iii", box) == ["iii iii iii"], "same length, a third the width"


def test_a_break_the_translator_asked_for_is_kept():
    encoder = cell_encoder()
    assert wrap(encoder, "abc\nabc", BoxSpec(width=999, lines=4)) == ["abc", "abc"]


def test_a_word_wider_than_the_box_is_reported_and_never_cut():
    encoder = cell_encoder()
    box = BoxSpec(width=measure(encoder, "abc"), lines=4, name="narrow")
    laid = lay_out_message("E0001.0", ["abcabc"], raw(0x100, END_WORD), encoder, box)
    assert not laid.fits
    assert "does not break" in laid.problems[0]
    assert "abcabc" in laid.problems[0], "the refusal has to name the text it could not fit"
    assert laid.pages == (("abcabc",),), "the English came back whole"


def test_the_guarded_lines_get_the_narrower_width_the_pencil_leaves():
    """The next-page pencil sits in the band's last 11 rows, which only line 3 crosses, so
    every line from `guarded_from` on is shorter and the lines before it are not."""
    encoder = StockEncoder(GlyphTable.load())
    assert DIALOGUE_BAND.width_of_line(1) == DIALOGUE_BAND.width
    assert DIALOGUE_BAND.guarded_width < DIALOGUE_BAND.width
    for number in range(DIALOGUE_BAND.guarded_from, DIALOGUE_BAND.lines + 1):
        assert DIALOGUE_BAND.width_of_line(number) == DIALOGUE_BAND.guarded_width
    wide = "ab " * 40
    lines = wrap(encoder, wide, DIALOGUE_BAND)
    assert measure(encoder, lines[0]) <= DIALOGUE_BAND.width
    assert measure(encoder, lines[DIALOGUE_BAND.guarded_from - 1]) <= DIALOGUE_BAND.guarded_width


def test_the_band_holds_the_lines_its_geometry_has_room_for():
    """The last line's 12-row cell must end inside the band, and one more would not.

    The geometry is the renderer's own -- `tools/vwf/build_prototype.Layout`, whose fields
    are what `asm/vwf.asm` is assembled with (Jay's ruling, `research/vwf-prototype.md`
    § "The ruled band") -- so moving the band or the pitch there and not here is a red
    test rather than a `DIALOGUE_BAND` that quietly describes a band nothing draws.

    `guarded_from` is the same sum: the pencil occupies the band's last `pencil_rows()`
    rows, and the guard belongs on the first line whose cell and its drop shadow reach up
    into them. Under Round 2's geometry that is line 3 alone; it was 2 *and* 3 while the
    pencil was stock at row 220, which is why it is derived rather than written down.
    """
    layout = vwf_layout()
    cell = 12  # a glyph cell is 12 rows (`research/font.md`), as `build_prototype.CELL` says
    assert cell == vwf_prototype().CELL
    fits = (layout.band_y + layout.band_h - layout.pen_y - cell) // layout.line_pitch + 1
    assert DIALOGUE_BAND.lines == fits
    assert DIALOGUE_BAND.width == layout.wrap_width

    pencil_top = layout.band_y + layout.band_h - pencil_rows()
    reaches = [
        number
        for number in range(1, DIALOGUE_BAND.lines + 1)
        # The cell's last row is `+ cell - 1` and its shadow is drawn one row below that.
        if layout.pen_y + (number - 1) * layout.line_pitch + cell >= pencil_top
    ]
    assert reaches, "no line reaches the pencil; the band and the marker have come apart"
    assert DIALOGUE_BAND.guarded_from == reaches[0]


# --- the speaker label and the marks, as text on the lines they sit on ----------------------


def test_the_opening_run_leads_page_1_and_the_closing_run_ends_the_last_page():
    """`Uncle「` is drawn in front of the first word and `」` after the last, as cells the
    renderer draws like any other, and the wrap measures them where they are."""
    encoder = cell_encoder()
    laid = lay_out_message(
        "E1.0",
        ("abc abc", "abc"),
        raw(1, PAGE_WORD, 7, 1, END_WORD),
        encoder,
        BoxSpec(width=999, lines=4),
        opening="ai!",
        closing="!",
    )
    assert laid.pages == (("ai!abc abc",), ("abc!",))
    cells = {c: CELLS[c][0] for c in CELLS}
    assert laid.words[:4] == (cells["a"], cells["i"], cells["!"], cells["a"])
    assert laid.words[-3:] == (cells["c"], cells["!"], END_WORD)
    assert laid.widths[0][0] == measure(encoder, "ai!abc abc")


def test_the_opening_run_is_charged_to_line_1_and_the_break_moves_for_it():
    """The narrowest red: the same page breaks a word earlier with the label in front."""
    encoder = cell_encoder()
    box = BoxSpec(width=measure(encoder, "abc abc abc"), lines=4)
    plain = lay_out_message("E1.0", ("abc abc abc abc",), raw(1, END_WORD), encoder, box)
    labelled = lay_out_message(
        "E1.0", ("abc abc abc abc",), raw(1, END_WORD), encoder, box, opening="ab!"
    )
    assert plain.pages[0] == ("abc abc abc", "abc")
    assert labelled.pages[0] == ("ab!abc abc", "abc abc")


def test_a_mark_the_font_cannot_draw_is_reported_like_any_other_character():
    encoder = cell_encoder()
    laid = lay_out_message(
        "E1.0", ("abc",), raw(1, END_WORD), encoder, BoxSpec(width=999, lines=4), opening="Z「"
    )
    assert any("draws no cell for 'Z「'" in problem for problem in laid.problems)


# --- pages, which never move -------------------------------------------------------------------


def test_the_page_timers_of_the_original_are_carried_through_one_for_one():
    """`0x8002 p` is the voice clip's own frame countdown; the English inherits every one."""
    original = raw(0x100, PAGE_WORD, 120, 0x101, PAGE_WORD, 57, 0x102, END_WORD)
    laid = lay_out_message(
        "E0001.0", ["aaa", "bbb", "ccc"], original, cell_encoder(), BoxSpec(999, 4)
    )
    assert laid.fits, laid.problems
    assert [w for w in laid.words if w == PAGE_WORD]
    pages = [laid.words[i + 1] for i, w in enumerate(laid.words) if w == PAGE_WORD]
    assert pages == [120, 57]


def test_more_pages_than_the_original_has_is_a_lint_error_and_not_a_new_page():
    original = raw(0x100, PAGE_WORD, 120, 0x101, END_WORD)
    laid = lay_out_message(
        "E0001.0", ["aaa", "bbb", "ccc"], original, cell_encoder(), BoxSpec(999, 4)
    )
    assert not laid.fits
    assert "the original has 2 page(s) and the English 3" in laid.problems[0]


def test_fewer_pages_than_the_original_has_is_also_refused():
    """A page break left out would strand a timer and stop the box turning by itself."""
    original = raw(0x100, PAGE_WORD, 120, 0x101, END_WORD)
    laid = lay_out_message("E0001.0", ["aaa"], original, cell_encoder(), BoxSpec(999, 4))
    assert not laid.fits
    assert "the original has 2 page(s) and the English 1" in laid.problems[0]


def test_a_page_that_needs_more_lines_than_the_box_holds_is_reported_with_both_numbers():
    encoder = cell_encoder()
    box = BoxSpec(width=measure(encoder, "abc"), lines=2, name="two lines")
    laid = lay_out_message("E0001.0", ["abc abc abc"], raw(0x100, END_WORD), encoder, box)
    assert not laid.fits
    assert "3 lines in two lines, which holds 2" in laid.problems[0]
    assert "never a shorter line" in laid.problems[0]


# --- the words that come out -------------------------------------------------------------------


def test_the_words_are_the_cells_of_the_encoder_with_a_newline_between_lines():
    encoder = cell_encoder()
    box = BoxSpec(width=measure(encoder, "abc"), lines=4)
    laid = lay_out_message("E0001.0", ["abc abc"], raw(0x100, END_WORD), encoder, box)
    assert laid.fits, laid.problems
    assert laid.words == (302, 303, 304, NEWLINE_WORD, 302, 303, 304, END_WORD)


def test_the_indent_cell_the_japanese_puts_after_a_newline_is_off_by_default():
    """`research/text-format.md`: `0x0000` there is the authoring tool's one-cell indent
    under the `speaker「` opening, not a guard `dialog_draw` requires -- it is handed to
    `glyph_draw` like any other cell. The prototype confirmed English reads flush to the
    pen without it, so it costs 14 px a line and is opt-in."""
    encoder = cell_encoder()
    box = BoxSpec(width=measure(encoder, "abc"), lines=4)
    plain = lay_out_message("E0001.0", ["abc abc"], raw(0x100, END_WORD), encoder, box)
    indented = lay_out_message(
        "E0001.0", ["abc abc"], raw(0x100, END_WORD), encoder, box, indent_continuations=True
    )
    assert PAD_WORD not in plain.words
    assert indented.words == (302, 303, 304, NEWLINE_WORD, PAD_WORD, 302, 303, 304, END_WORD)


# --- selects -----------------------------------------------------------------------------------


def test_a_select_needs_exactly_the_options_the_executable_has_lines_for():
    original = raw(0x100, NEWLINE_WORD, 0x101, NEWLINE_WORD, 0x102, NEWLINE_WORD)
    encoder = cell_encoder()
    good = lay_out_select("E0001.0", ["a", "b", "c"], original, (3, 0), encoder, BoxSpec(999, 4))
    assert good.fits, good.problems
    assert good.words == (302, NEWLINE_WORD, 303, NEWLINE_WORD, 304, NEWLINE_WORD)

    short = lay_out_select("E0001.0", ["a", "b"], original, (3, 0), encoder, BoxSpec(999, 4))
    assert "draws 3 option(s) and the translation gives 2" in short.problems[0]
    assert short.words == words_of(original), "the refused layout leaves the original words"


def test_a_select_with_prompt_lines_needs_them_supplied():
    original = raw(0x100, NEWLINE_WORD, 0x101, NEWLINE_WORD, 0x102, NEWLINE_WORD)
    laid = lay_out_select("E0001.0", ["a", "b"], original, (3, 1), cell_encoder(), BoxSpec(999, 4))
    assert "opens with 1 prompt line(s) and the translation gives 0" in " ".join(laid.problems)
    with_prompt = lay_out_select(
        "E0001.0", ["a", "b"], original, (3, 1), cell_encoder(), BoxSpec(999, 4), prompts=["c"]
    )
    assert with_prompt.fits, with_prompt.problems
    assert with_prompt.words[0] == 304, "the prompt line comes first"


def test_an_option_wider_than_the_box_is_an_error_because_a_select_line_cannot_wrap():
    original = raw(0x100, NEWLINE_WORD, 0x101, NEWLINE_WORD)
    encoder = cell_encoder()
    laid = lay_out_select(
        "E0001.0",
        ["mmmm", "a"],
        original,
        (2, 0),
        encoder,
        BoxSpec(width=measure(encoder, "mm"), lines=4),
    )
    assert "a select line cannot wrap" in laid.problems[0]


# --- code-file arrays, which have no slack at all ---


def test_an_array_item_keeps_its_own_terminator_and_may_not_grow():
    """An array is followed by the next symbol; its item is replaced at equal-or-smaller size."""
    original = raw(0x100, 0x101, 0x102, NEWLINE_WORD)
    encoder = cell_encoder()
    laid = lay_out_array("exe@8003D5F0.8", "ab", original, encoder, len(original))
    assert laid.fits, laid.problems
    assert laid.words == (302, 303, NEWLINE_WORD), "the item's own terminator comes back"

    too_long = lay_out_array("exe@8003D5F0.8", "abcabc", original, encoder, len(original))
    assert "6 over" in too_long.problems[0]
    assert "no slack" in too_long.problems[0]


def test_an_array_group_drawn_whole_is_left_alone_rather_than_divided_by_guesswork():
    """Several lines in one site: how English divides between them is nobody's decision yet."""
    original = raw(0x100, NEWLINE_WORD, 0x101, NEWLINE_WORD)
    laid = lay_out_array("exe@80046158.0", "yes no", original, cell_encoder(), len(original))
    assert not laid.fits
    assert "drawn as a group" in laid.problems[0]
    assert laid.words == words_of(original), "the Japanese is left exactly where it was"


# --- the encoders ------------------------------------------------------------------------------


def test_the_stock_encoder_spells_english_with_the_sheets_full_width_cells():
    table = GlyphTable.load()
    encoder = StockEncoder(table)
    assert encoder.advance("i") == encoder.advance("m") == STOCK_ADVANCE
    assert encoder.glyph("A") == table.to_glyph["A"]
    assert encoder.glyph("あ") is None, "a kana is not something English is spelled with"
    # The marks a message is dressed with are the one exception: the sheet's own cells.
    for mark in (*SPEECH_MARKS, *SPEECH_MARKS.values()):
        assert encoder.glyph(mark) == table.from_character[mark]


def test_the_cell_map_encoder_reads_the_shape_the_font_build_writes(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"cells": {"A": {"id": 292, "advance": 9}, " ": {"id": 10, "advance": 4}}}),
        encoding="utf-8",
    )
    encoder = CellMapEncoder.from_json(path)
    assert encoder.glyph("A") == 292
    assert encoder.advance("A") == 9
    assert encoder.glyph(" ") == 10, "the English space is its own cell, not glyph 0"
    assert encoder.glyph("Z") is None


def test_a_file_that_is_not_a_cell_map_is_refused_rather_than_read_as_an_empty_font(tmp_path):
    path = tmp_path / "not-a-map.json"
    path.write_text(json.dumps({"layout": {"pen_x": 24}}), encoding="utf-8")
    with pytest.raises(LayoutError, match="is not a cell entry"):
        CellMapEncoder.from_json(path)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"cells": {}}), encoding="utf-8")
    with pytest.raises(LayoutError, match="holds no `cells` map"):
        CellMapEncoder.from_json(empty)
    with pytest.raises(LayoutError):
        CellMapEncoder.from_json(tmp_path / "missing.json")


def test_a_character_the_font_cannot_draw_is_named_rather_than_substituted():
    encoder = cell_encoder()
    assert unencodable(encoder, "abc?") == ["?"]
    laid = lay_out_message("E0001.0", ["abc?"], raw(0x100, END_WORD), encoder, BoxSpec(999, 4))
    assert not laid.fits
    assert "draws no cell for '?'" in laid.problems[0]


def test_an_array_item_with_no_english_is_refused_rather_than_blanked():
    """An empty item would write just the terminator, and the game still draws that cell."""
    original = raw(0x100, 0x101, NEWLINE_WORD)
    laid = lay_out_array("exe@8003D5F0.8", "", original, cell_encoder(), len(original))
    assert not laid.fits
    assert "blank an item the game still draws" in laid.problems[0]
