"""`boku.code_text`: labels drawn from instruction immediates, and the save title."""

from __future__ import annotations

import pytest

from boku.arrays import SAVE_TITLE_BYTES, SAVE_TITLE_LINE_ID, CodeLabel
from boku.code_text import (
    DAY,
    SLOT,
    code_label_edits,
    full_width,
    lay_out_code_label,
    lay_out_save_title,
    save_title_parts,
    split_title_blob,
)
from boku.glyphs import GlyphTable, words_to_bytes
from boku.layout import CellMapEncoder

CELLS = CellMapEncoder({"W": (700, 9), "L": (701, 7), "a": (702, 6)})


def test_a_label_with_one_character_per_drawn_glyph_is_those_cells_in_draw_order():
    """`W L`: two drawn glyphs; the space is where the code draws a number, not a glyph."""
    laid = lay_out_code_label("exe@code:800377F8", [(0x26A, 0x4B9)], "W L", CELLS)
    assert laid.problems == ()
    assert laid.words == (700, 701)


def test_a_label_needing_more_glyphs_than_the_code_draws_is_refused_with_the_counts():
    laid = lay_out_code_label("exe@code:800377F8", [(0x26A, 0x4B9)], "Wa L", CELLS)
    assert laid.problems == (
        "exe@code:800377F8: the code draws [2] glyph(s) per run and 'Wa L' needs [3]; a label "
        "is placed one character per drawn glyph, and more glyphs than the function draws "
        "is a change to its layout, not a substitution",
    )


def test_runs_are_separated_where_the_code_draws_a_computed_digit():
    laid = lay_out_code_label("title@code:x", [(1,), (2, 3)], "W / aL", CELLS)
    assert laid.problems == ()
    assert laid.words == (700, 702, 701)


class _Archive:
    """Just enough of `Archive` for one label in the executable."""

    def __init__(self, words: dict[int, int]) -> None:
        self.words = words

    def exe_bytes(self, ram: int, n: int) -> bytes:
        return self.words[ram].to_bytes(4, "little")


def test_every_site_of_a_drawn_glyph_is_rewritten_even_down_two_branches():
    """`winloss_draw` loads each of its two glyphs in two branches: four instructions."""
    addiu = 0x24040000  # addiu a0, zero, 0
    sites = ((0x80037000, 0x26A), (0x80037010, 0x4B9), (0x80037020, 0x26A), (0x80037030, 0x4B9))
    label = CodeLabel("exe", 0x80036F00, ((0x26A, 0x4B9),), sites, "wins, losses", (0, 1, 0, 1))
    archive = _Archive({ram: addiu | glyph for ram, glyph in sites})
    edits = code_label_edits(archive, label, (700, 701))
    assert [(e.offset, int.from_bytes(e.new, "little") & 0xFFFF) for e in edits] == [
        (0x80037000 - 0x8000F800, 700),
        (0x80037010 - 0x8000F800, 701),
        (0x80037020 - 0x8000F800, 700),
        (0x80037030 - 0x8000F800, 701),
    ]
    assert all(int.from_bytes(e.new, "little") >> 16 == addiu >> 16 for e in edits)


def test_the_save_title_is_three_full_width_parts_around_the_slot_and_the_day():
    parts = save_title_parts(f"Boku's Memories {SLOT} August {DAY}")
    assert parts == tuple(
        full_width(part).encode("shift_jis") for part in ("Boku's Memories ", " August ", "")
    )
    assert all(len(part) % 2 == 0 for part in parts), "every character is two bytes"


def test_a_title_the_widest_slot_and_day_overrun_is_refused_at_the_byte():
    """Slot 15 and day 31 add eight bytes and the terminator one: 64 is the field."""
    room = (SAVE_TITLE_BYTES - 2 * 2 * 2 - 1) // 2  # full-width characters that still fit
    fits = f"{'A' * room}{SLOT}{DAY}"
    assert not isinstance(save_title_parts(fits), str)
    over = f"{'A' * (room + 1)}{SLOT}{DAY}"
    assert "65 bytes" in save_title_parts(over)


def test_a_title_without_its_two_places_is_refused():
    assert "{slot} and then {day}" in save_title_parts("Boku's Memories August")
    assert "{slot} and then {day}" in save_title_parts(f"A {DAY} B {SLOT}")


def test_the_laid_out_title_carries_its_parts_nul_terminated_in_its_words():
    laid = lay_out_save_title(SAVE_TITLE_LINE_ID, f"Boku's Memories {SLOT} August {DAY}")
    blob = words_to_bytes(laid.words)
    starts = split_title_blob(blob)
    parts = save_title_parts(f"Boku's Memories {SLOT} August {DAY}")
    assert [blob[s : s + len(p)] for s, p in zip(starts, parts, strict=True)] == list(parts)
    assert all(blob[s + len(p)] == 0 for s, p in zip(starts, parts, strict=True))


@pytest.mark.parametrize("character", ["é"])
def test_a_character_with_no_full_width_shift_jis_form_is_named(character):
    assert repr(character) in save_title_parts(f"{character}{SLOT}{DAY}")


def test_a_character_the_original_glyph_already_spells_keeps_that_glyph():
    """The extras screen's `/31`: the sheet's own full-width cells beside computed full-width
    digits. The English spells the same characters, so the ids stay; an English cell there
    would draw narrow digits between full-width ones."""
    table = GlyphTable.load()
    slash, three = table.to_glyph["/"], table.to_glyph["3"]
    encoder = CellMapEncoder({"/": (703, 4), "3": (704, 6)})
    laid = lay_out_code_label("title@code:x", [(slash, three)], "/3", encoder)
    assert laid.words == (slash, three)
    changed = lay_out_code_label("title@code:x", [(slash, three)], "3/", encoder)
    assert changed.words == (704, 703), "a different character takes its English cell"


def test_a_run_shorter_than_the_code_draws_is_padded_with_the_blank_cell():
    laid = lay_out_code_label("exe@code:80037544", [(1, 2, 3, 4)], "WL", CELLS)
    assert laid.problems == ()
    assert laid.words == (700, 701, 0, 0)


def test_a_glyph_token_is_one_drawn_glyph_as_the_extract_writes_it():
    """`title@code:8007C8EC` is extracted as `{G:1456} / {G:1456}`: one cell per run."""
    laid = lay_out_code_label(
        "title@code:8007C8EC", [(1456,), (1456,)], "{G:1456} / {G:1456}", CELLS
    )
    assert laid.problems == ()
    assert laid.words == (1456, 1456)


@pytest.mark.parametrize("typed", ["-", "~", '"'])
def test_ascii_strict_shift_jis_has_no_full_width_code_for_still_titles(typed):
    """U+FF0D, U+FF5E and U+FF02 exist only in cp932; the card's BIOS draws the JIS forms."""
    parts = save_title_parts(f"Boku{typed}{SLOT}{DAY}")
    assert not isinstance(parts, str), parts
