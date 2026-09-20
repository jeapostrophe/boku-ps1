"""`walk_block`: how a block's bytecode and its offset table decide what the text is.

A message's *length* is not stored anywhere. It is whatever the reader reads, and which
reader that is depends on the opcode that names the entry: a `MSG`/`XAMSG` runs to the
first `0x8000`, a `SELECT` has no `0x8000` at all and runs for exactly the number of lines
the executable holds for its type and variant. So the same bytes are two different
lengths depending on one operand, and every claim in between — the pad after the text, the
12-byte voice key, the message index being in range — is checked here rather than trusted.
"""

from __future__ import annotations

from boku.events import Block
from boku.glyphs import END_WORD, NEWLINE_WORD, PAGE_WORD
from boku.sites import (
    control_words,
    glyph_count,
    iter_instructions,
    page_structure,
    page_waits,
    scan_text,
    walk_block,
)
from tests import synth_archive as synth

XAMSG, MSG, SELECT, END = 0x0D, 0x0E, 0x21, 0x15


def lines_always(count: int):
    return lambda _type, _variant: count


def code_naming(*instructions: bytes) -> bytes:
    return b"".join(instructions) + synth.instruction(END, 1)


def xamsg(index: int) -> bytes:
    return synth.instruction(XAMSG, 4, bytes([1, 0x71, index, 0, 0]))


def select(index: int, select_type: int = 3, variant: int = 1) -> bytes:
    return synth.instruction(SELECT, 3, bytes([select_type, variant, index, 0]))


# --- what the walk finds -------------------------------------------------------------------


def test_a_voiced_message_runs_to_its_terminator_and_reports_its_pad():
    text = synth.words(0x100, 0x101, END_WORD, 0xCDCD)  # 2 bytes of build-tool pad
    problems: list[str] = []
    block = Block(
        synth.block(
            [synth.cast([]), synth.condition(), code_naming(xamsg(0)), synth.voice_key(), text]
        )
    )
    entries = walk_block(block, lines_always(3), problems, "here")
    assert problems == []
    text_at = block.entry_span(4)[0]
    assert entries == [(0, text_at, 6, "MSG", 2, True)]


def test_an_unvoiced_message_is_the_same_site_with_no_voice_key():
    text = synth.words(0x100, END_WORD)
    problems: list[str] = []
    entries = walk_block(
        Block(
            synth.block(
                [
                    synth.cast([]),
                    synth.condition(),
                    code_naming(synth.instruction(MSG, 4, bytes([0, 0, 0, 0, 0]))),
                    None,
                    text,
                ]
            )
        ),
        lines_always(3),
        problems,
        "here",
    )
    assert problems == []
    assert [(kind, voiced) for _i, _o, _s, kind, _sl, voiced in entries] == [("MSG", False)]


def test_a_select_is_as_long_as_the_executable_says_and_has_no_terminator():
    """Three lines here; ask for two and the third becomes somebody else's bytes."""
    text = synth.words(0x100, NEWLINE_WORD, 0x101, NEWLINE_WORD, 0x102, NEWLINE_WORD)
    block = Block(
        synth.block([synth.cast([]), synth.condition(), code_naming(select(0)), None, text])
    )
    problems: list[str] = []
    assert walk_block(block, lines_always(3), problems, "here")[0][2] == 12
    assert walk_block(block, lines_always(2), problems, "here")[0][2] == 8
    assert [p for p in problems if "slack" in p], "the short read leaves a 4-byte pad"
    assert walk_block(block, lines_always(3), [], "here")[0][3] == "SEL3.1"


def test_a_message_no_opcode_names_is_a_problem():
    """`research/text-format.md`: with opcode 0x0E unknown the walk reported 585 of these."""
    text = synth.words(0x100, END_WORD)
    problems: list[str] = []
    walk_block(
        Block(synth.block([synth.cast([]), synth.condition(), code_naming(), None, text])),
        lines_always(3),
        problems,
        "here",
    )
    assert any("named by no MSG/XAMSG/SELECT opcode" in p for p in problems)


def test_a_bytecode_operand_past_the_last_message_is_a_problem():
    text = synth.words(0x100, END_WORD)
    problems: list[str] = []
    walk_block(
        Block(synth.block([synth.cast([]), synth.condition(), code_naming(xamsg(4)), None, text])),
        lines_always(3),
        problems,
        "here",
    )
    assert any("names message 4 of 1" in p for p in problems)


def test_a_message_that_does_not_terminate_inside_its_entry_is_a_problem():
    problems: list[str] = []
    entries = walk_block(
        Block(
            synth.block(
                [
                    synth.cast([]),
                    synth.condition(),
                    code_naming(xamsg(0)),
                    None,
                    synth.words(0x100, 0x101),
                ]
            )
        ),
        lines_always(3),
        problems,
        "here",
    )
    assert entries == []
    assert any("does not terminate" in p for p in problems)


def test_a_voice_key_that_is_not_12_bytes_is_a_problem():
    problems: list[str] = []
    walk_block(
        Block(
            synth.block(
                [
                    synth.cast([]),
                    synth.condition(),
                    code_naming(xamsg(0)),
                    synth.voice_key() + bytes(4),
                    synth.words(0x100, END_WORD),
                ]
            )
        ),
        lines_always(3),
        problems,
        "here",
    )
    assert any("key 0 is 16 bytes" in p for p in problems)


def test_a_null_text_named_as_a_message_is_a_problem_but_voice_only_is_not():
    problems: list[str] = []
    walk_block(
        Block(
            synth.block(
                [synth.cast([]), synth.condition(), code_naming(xamsg(0)), synth.voice_key(), None]
            )
        ),
        lines_always(3),
        problems,
        "here",
    )
    assert any("null text 0" in p for p in problems)

    clean: list[str] = []
    entries = walk_block(
        Block(
            synth.block(
                [
                    synth.cast([]),
                    synth.condition(),
                    code_naming(synth.instruction(0x0F, 4, bytes([0, 0, 0, 0, 0]))),
                    synth.voice_key(),
                    None,
                ]
            )
        ),
        lines_always(3),
        clean,
        "here",
    )
    assert clean == [] and entries == []


# --- the lenient instruction walk -------------------------------------------------------------


def test_the_site_walker_advances_by_the_size_byte_and_stops_at_the_pad():
    code = xamsg(2) + synth.instruction(END, 1) + bytes(2)
    walked = list(iter_instructions(code))
    assert [(i.pc, i.op) for i in walked] == [(0, XAMSG), (8, END)]
    # The lenient walker and the strict one now name this operand the same way; it used
    # to be `a[2]` here and `b[4]` in `boku.events`, from two different bases.
    assert walked[0].message_index == 2
    assert list(iter_instructions(bytes(4))) == [], "a zero size byte is the 4-byte pad"


# --- reading a decoded line ----------------------------------------------------------------------


def test_the_layout_is_columns_per_page_with_the_page_break_ending_a_page():
    raw = synth.words(1, 2, NEWLINE_WORD, 3, PAGE_WORD, 102, 4, END_WORD)
    assert page_structure(raw) == [[2, 1], [1]]
    assert page_waits(raw) == [102]
    assert glyph_count(raw) == 4, "a page break's parameter is not a drawn cell"
    assert control_words(raw) == {END_WORD: 1, NEWLINE_WORD: 1, PAGE_WORD: 1}


# --- the heuristic scan, which the structural walk has to explain ----------------------------


def test_the_scan_finds_a_run_of_glyphs_ending_in_a_terminator():
    blob = bytes(8) + synth.words(0x100, 0x101, NEWLINE_WORD, 0x102, END_WORD) + bytes(8)
    assert scan_text(blob) == [(8, 8 + 10)]


def test_the_scan_stops_at_an_id_it_cannot_see_which_is_why_it_needs_the_walk():
    """Ids above `GLYPH_SCAN_MAX` cut the run, so the scan under-counts. The walk is the truth."""
    blob = synth.words(0x600, 0x100, 0x101, 0x102, END_WORD)
    assert scan_text(blob) == [(2, len(blob))]
    short = synth.words(0x600, 0x100, 0x101, END_WORD)
    assert scan_text(short) == [], "two visible glyphs is below the scan's threshold"
