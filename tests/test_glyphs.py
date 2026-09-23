"""The glyph table, and the decode/encode round trip the reinserter will rest on.

The committed table is loaded once for the properties that are about *this* sheet; the
round-trip rules are checked against a table built here, so a change in the sheet cannot
quietly turn a round-trip test green by removing the case it was about.
"""

from __future__ import annotations

import pytest

from boku.glyphs import (
    END_WORD,
    GLYPH_TSV,
    NEWLINE_WORD,
    PAGE_WORD,
    SHEET_SLOTS,
    GlyphTable,
    TextError,
    words_of,
)
from tests import synth_archive as synth


def table(rows: dict[int, str]) -> GlyphTable:
    """A table with the same ambiguity rules as the real one, over a handful of cells."""
    owners: dict[str, list[int]] = {}
    for index, drawn in rows.items():
        owners.setdefault(drawn, []).append(index)
    unambiguous = {i: c for i, c in rows.items() if len(owners[c]) == 1}
    return GlyphTable(
        characters=dict(rows),
        unambiguous=unambiguous,
        to_glyph={},
        from_character={c: i for i, c in unambiguous.items()},
        source_sha1="0" * 40,
    )


# 22 and 1456 are the same character on the real sheet: the vertical and horizontal
# forms of the closing parenthesis (research/font.md).
SHEET = {0: "　", 1: "あ", 2: "い", 22: "）", 1456: "）"}  # noqa: RUF001


# --- the round trip ----------------------------------------------------------------------


def test_control_words_decode_to_the_tokens_a_translator_reads():
    raw = synth.words(1, NEWLINE_WORD, 2, PAGE_WORD, 102, 1, END_WORD)
    assert table(SHEET).decode(raw) == "あ{NL}い{PAGE:102}あ{END}"


def test_a_character_the_sheet_draws_twice_decodes_as_its_id_not_as_the_character():
    """Otherwise the doubled cell would re-encode as 22 wherever the disc had 1456, and
    the site would still be the right length while drawing the wrong glyph."""
    assert table(SHEET).decode(synth.words(1456)) == "{G:1456}"
    assert table(SHEET).decode(synth.words(22)) == "{G:22}"


def test_an_id_the_table_does_not_name_decodes_as_its_id():
    assert table(SHEET).decode(synth.words(999)) == "{G:999}"


@pytest.mark.parametrize(
    "raw",
    [
        synth.words(1, 2, END_WORD),
        synth.words(1, NEWLINE_WORD, 0, 2, END_WORD),
        synth.words(1, PAGE_WORD, 21, 0, 2, END_WORD),
        synth.words(22, 1456, 999),
        synth.words(1, NEWLINE_WORD),
        b"",
    ],
)
def test_decode_then_encode_returns_the_original_bytes(raw: bytes):
    """The property gate (2) applies over every site on the disc; here over the awkward cases."""
    sheet = table(SHEET)
    assert sheet.encode(sheet.decode(raw)) == raw


def test_a_page_break_with_no_parameter_is_refused_rather_than_silently_dropped():
    with pytest.raises(TextError, match="page break at the end"):
        table(SHEET).decode(synth.words(1, PAGE_WORD))


def test_an_odd_length_is_refused_rather_than_truncated():
    with pytest.raises(TextError, match="whole number of 16-bit words"):
        words_of(b"\x01\x00\x02")


def test_a_character_with_no_cell_is_named_rather_than_substituted():
    with pytest.raises(TextError, match="no cell for"):
        table(SHEET).encode("z")


# --- the committed sheet ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def sheet() -> GlyphTable:
    return GlyphTable.load()


def test_the_committed_table_has_one_row_per_slot_of_the_sheet():
    """`SHEET_SLOTS` is what a `{G:n}` token is bounded by; the table is its measurement."""
    rows = GLYPH_TSV.read_text(encoding="utf-8").splitlines()[1:]
    assert [int(row.split("\t")[0]) for row in rows] == list(range(SHEET_SLOTS))


def test_the_committed_sheet_draws_letters_digits_and_the_space(sheet: GlyphTable):
    for character in "ABZabz09 .,!?":
        assert character in sheet.to_glyph, character
    assert sheet.to_glyph[" "] == 0, "glyph 0 is the blank cell"


def test_the_committed_sheet_keeps_every_doubled_character_out_of_the_round_trip(sheet: GlyphTable):
    """Whatever the sheet doubles, `decode` must not spell — this is derived, not listed."""
    doubled = {c for c in sheet.characters.values() if list(sheet.characters.values()).count(c) > 1}
    assert doubled, "a sheet with no doubled cell would make this gate vacuous"
    assert not doubled & set(sheet.from_character)


def test_the_committed_sheet_round_trips_every_cell_it_claims_to_spell(sheet: GlyphTable):
    for index in sorted(sheet.unambiguous):
        raw = index.to_bytes(2, "little")
        assert sheet.encode(sheet.decode(raw)) == raw, index
