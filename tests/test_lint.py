"""`PLAN PIPE-06` -- every check made red on purpose, at the narrowest input that shows it.

Each test here builds a translation file that passes, changes **one** thing, and asserts
the lint goes red *with the finding that names the harm* -- not merely that something
failed. The numbers a test asserts on (a box's width, an array item's byte size, the
encoder's advance, the word lists) are read out of the thing under test, never retyped
beside it: a fixture that holds its own copy of the limit passes exactly when the two
copies drift together (`~/.claude/CLAUDE.md` ENG-1).
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from boku import REPO_ROOT, exchange_notebook
from boku import layout as layout_module
from boku import lint as lint_module
from boku import translation as translation_module
from boku.archive import EXE_NAME
from boku.boxes import TextBox
from boku.build import VWF_EDITS_FORMAT, load_edit_set
from boku.glyphs import GlyphTable
from boku.layout import (
    DIALOGUE_BAND,
    LABEL_MARKS,
    SELECT_ROW,
    CellMapEncoder,
    LayoutError,
    StockEncoder,
    lay_out_message,
    measure,
    original_marks,
)
from boku.lint import (
    ADDITIVE_WORDS,
    DEFAULT_CELLS,
    ERROR,
    SOURCE_INTENSIFIERS,
    WARNING,
    LabelledBox,
    Options,
    label_allowance,
    lint_movie_file,
    lint_movies,
    lint_rows,
    load_rows,
    make_encoder,
    parse_text,
    renderer_for,
    select_fields,
    translation_paths,
)
from boku.script_store import load_store, original_bytes
from tests.synth_script import SynthStore, write_translation
from tests.test_vwf_prototype import vwf_layout

VOICED = "E9001.0"
UNVOICED = "E9001.1"
CHOICE = "E9001.2"
VOICE_ONLY = "E9001.3"
ARRAY = "exe@80000000.0"
MOVES = "musi@2C.0"


@pytest.fixture
def store(tmp_path: Path):
    """A two-page voiced line, a one-page unvoiced one, a 3-option select and an array."""
    synth = SynthStore.new(tmp_path)
    synth.message(VOICED, [[4], [3]], voiced=True)
    synth.message(UNVOICED, [[5]], voiced=False, speaker="BOKU", slot=0)
    synth.select(CHOICE, options=3)
    synth.array_item(ARRAY, cells=4)
    synth.scene("E9001", [VOICED, UNVOICED, CHOICE], voice_only=[VOICE_ONLY])
    return load_store(synth.write())


def run(store, tmp_path: Path, rows, **options) -> list:
    """Lint one file of `rows` and return the findings."""
    path = write_translation(tmp_path / "day99.txt", rows)
    parsed, findings = load_rows(translation_paths([path]))
    return [*findings, *lint_rows(store, parsed, Options(encoder=StockEncoder.load(), **options))]


def checks(findings) -> list[str]:
    return [finding.check for finding in findings]


def only(findings, check: str):
    matching = [finding for finding in findings if finding.check == check]
    assert matching, f"expected a {check} finding, got {checks(findings)}"
    return matching[0]


GOOD = [
    (VOICED, "Uncle", "One. // Two."),
    (UNVOICED, "Boku", "Three."),
    (CHOICE, "[SEL]", "Yes | No | Again"),
    (VOICE_ONLY, "(voice only)", ""),
    (ARRAY, "Boku", "Item"),
]


def test_a_clean_file_is_clean(store, tmp_path):
    """The baseline every red below is one change away from."""
    assert run(store, tmp_path, GOOD, label=False) == []


# --- ids and select shape ----------------------------------------------------------------------


def test_an_unknown_id_is_an_error(store, tmp_path):
    findings = run(store, tmp_path, [*GOOD, ("E9999.0", "Boku", "Nobody says this.")])
    finding = only(findings, "unknown-id")
    assert finding.severity == ERROR
    assert "E9999.0" in finding.message
    assert "E9999.0" not in store.known_ids


def test_an_id_translated_twice_is_an_error(store, tmp_path):
    """Two files, one id. The second copy is the finding, and it names the first."""
    first = write_translation(tmp_path / "day99.txt", GOOD)
    second = write_translation(tmp_path / "shared99.txt", [(UNVOICED, "Boku", "Three again.")])
    rows, _ = load_rows(translation_paths([first, second]))
    findings = lint_rows(store, rows, Options(encoder=StockEncoder.load(), label=False))
    finding = only(findings, "translated-twice")
    assert finding.severity == ERROR
    assert finding.file == "shared99.txt"
    assert "day99.txt" in finding.message


def test_a_select_with_the_wrong_option_count_is_an_error(store, tmp_path):
    """The count is `g_select_lines`, so it is the store's number that must appear."""
    fixed = store.lines[CHOICE]["select"]["lines"]
    rows = [row for row in GOOD if row[0] != CHOICE]
    findings = run(store, tmp_path, [*rows, (CHOICE, "[SEL]", "Yes | No")], label=False)
    finding = only(findings, "select-options")
    assert finding.severity == ERROR
    assert "2 option(s) given" in finding.message
    assert f"fixes {fixed}" in finding.message


def test_a_select_option_is_measured_against_the_row_the_renderer_draws(store, tmp_path):
    """A select row starts at `SEL_X` and runs to the pen's right margin
    (`build_prototype.Layout.select_width`, 248 px) -- not the dialogue band's 272. An option
    between the two passed this lint and the prototype build refused it (the translation
    lane, 2026-09-22), so the width is the renderer's, read from its own layout here."""
    row_width = vwf_layout().select_width
    encoder = StockEncoder.load()
    step = encoder.advance("M")
    word = "M" * (row_width // step + 1)  # just past the row, well inside the band
    assert row_width < measure(encoder, word) <= DIALOGUE_BAND.width, "no gap to test"
    rows = [row for row in GOOD if row[0] != CHOICE]
    findings = run(store, tmp_path, [*rows, (CHOICE, "[SEL]", f"{word} | No | Again")], label=False)
    assert f"in {row_width}," in only(findings, "select-width").message


def test_the_lint_measures_selects_in_the_row_its_cell_map_s_build_drew(tmp_path):
    """The lint's cell map is the edit set the build installs (`DEFAULT_CELLS`), and that
    file also records the select row the renderer was assembled with; a lint measuring the
    default row against a narrower build would pass options the screen clips."""
    edits = tmp_path / "edits.json"
    edits.write_text(
        json.dumps({"cells": {"A": {"id": 292, "advance": 9}}, "layout": {"select_width": 200}}),
        encoding="utf-8",
    )
    assert renderer_for("cellmap", edits)[1].width == 200
    assert renderer_for("stock", edits)[1] == SELECT_ROW, "the stock renderer's row is retail's"


def test_a_select_s_question_is_not_counted_as_an_option(tmp_path):
    """A `[SEL]` whose box opens with a question lists the question as the first field.

    That is the committed convention -- style guide § 13, `translation/days/README.md`
    § shared.txt, and the header of `translation/days/shared.txt` itself -- and it is what
    `boku.layout.lay_out_select` and `boku.translation.select_fields` both read. Counted as
    an option instead, every prompt-bearing select in the game is a false error.
    """
    synth = SynthStore.new(tmp_path)
    synth.select(CHOICE, options=2, prompts=1)
    synth.scene("E9001", [CHOICE])
    store = load_store(synth.write())
    shape = store.lines[CHOICE]["select"]
    options = shape["lines"] - shape["prompt_lines"]

    good = [(CHOICE, "[SEL]", "Read which? | Insects | Kites")]
    assert checks(run(store, tmp_path, good, label=False)) == []

    short = [(CHOICE, "[SEL]", "Read which? | Insects")]
    finding = only(run(store, tmp_path, short, label=False), "select-options")
    assert finding.severity == ERROR
    assert f"{options - 1} option(s) given" in finding.message
    assert f"fixes {options}" in finding.message
    assert f"{shape['prompt_lines']} prompt line(s)" in finding.message


def test_a_select_written_as_a_message_is_an_error(store, tmp_path):
    rows = [row for row in GOOD if row[0] != CHOICE]
    findings = run(store, tmp_path, [*rows, (CHOICE, "Boku", "Yes")], label=False)
    assert only(findings, "select-shape").severity == ERROR


def test_a_voiced_page_count_mismatch_is_an_error(store, tmp_path):
    """One page where the clip turns two: the countdown cannot move, so this is fatal."""
    pages = len(store.lines[VOICED]["layout"]["pages"])
    assert store.lines[VOICED]["capacity"]["pages_fixed_by_voice"]
    rows = [row for row in GOOD if row[0] != VOICED]
    findings = run(store, tmp_path, [*rows, (VOICED, "Uncle", "One and two.")], label=False)
    finding = only(findings, "page-count")
    assert finding.severity == ERROR
    assert f"the original has {pages}" in finding.message


def test_an_unvoiced_page_count_mismatch_only_warns(store, tmp_path):
    """The same change on a line with no clip: free to re-page, so it is a warning."""
    assert not store.lines[UNVOICED]["capacity"]["pages_fixed_by_voice"]
    rows = [row for row in GOOD if row[0] != UNVOICED]
    findings = run(store, tmp_path, [*rows, (UNVOICED, "Boku", "Three. // Four.")], label=False)
    assert only(findings, "page-count-unvoiced").severity == WARNING
    assert "page-count" not in checks(findings)


# --- the ones only this lint has ---------------------------------------------------------------


def test_a_character_with_no_cell_is_an_error(store, tmp_path):
    """The character is found by asking the encoder, so this cannot pass by luck."""
    encoder = StockEncoder.load()
    missing = next(chr(code) for code in range(0x21, 0x7F) if encoder.glyph(chr(code)) is None)
    rows = [row for row in GOOD if row[0] != UNVOICED]
    findings = run(store, tmp_path, [*rows, (UNVOICED, "Boku", f"Three{missing}")], label=False)
    finding = only(findings, "unencodable")
    assert finding.severity == ERROR
    assert missing in finding.message


def test_a_sheet_symbol_in_a_line_of_dialogue_is_drawn_not_unencodable(store, tmp_path):
    """The lint asks the same question the build does (`boku.layout.WithSheetSymbols`):
    ○ is the sheet's own cell, which the dialogue draws beside the English."""
    rows = [row for row in GOOD if row[0] != UNVOICED]
    findings = run(store, tmp_path, [*rows, (UNVOICED, "Boku", "Press ○.")], label=False)
    assert "unencodable" not in checks(findings)


def test_a_page_one_character_too_wide_is_an_error(store, tmp_path):
    """The narrowest pixel case: the widest line that fits, then one cell more.

    The count comes from the encoder's own advance and the box's own width, so the test
    cannot drift away from either. One unbroken word is used because `wrap` breaks on
    spaces, and a word that cannot break is exactly what the engine clips.
    """
    encoder = StockEncoder.load()
    advance = encoder.advance("M")
    widest = DIALOGUE_BAND.width // advance
    rows = [row for row in GOOD if row[0] != UNVOICED]

    fits = run(store, tmp_path, [*rows, (UNVOICED, "Boku", "M" * widest)], label=False)
    assert "page-width" not in checks(fits), f"{widest} cells should fit; got {fits}"

    over = run(store, tmp_path, [*rows, (UNVOICED, "Boku", "M" * (widest + 1))], label=False)
    finding = only(over, "page-width")
    assert finding.severity == ERROR
    assert f"{(widest + 1) * advance} px in {DIALOGUE_BAND.width}" in finding.message
    assert f"{(widest + 1) * advance - DIALOGUE_BAND.width} over" in finding.message


def test_too_many_lines_on_a_page_is_an_error(store, tmp_path):
    """One line per word, one word more than the box has lines."""
    encoder = StockEncoder.load()
    word = "M" * (DIALOGUE_BAND.width // encoder.advance("M"))
    rows = [row for row in GOOD if row[0] != UNVOICED]
    text = " ".join([word] * (DIALOGUE_BAND.lines + 1))
    findings = run(store, tmp_path, [*rows, (UNVOICED, "Boku", text)], label=False)
    finding = only(findings, "page-lines")
    assert finding.severity == ERROR
    assert f"{DIALOGUE_BAND.lines + 1} lines" in finding.message
    assert f"holds {DIALOGUE_BAND.lines}" in finding.message


def test_the_label_is_charged_to_page_one_line_one(store, tmp_path):
    """A line that fits bare and does not fit once the label is drawn in front of it.

    This is the whole point of the `--label` default: the renderer draws the label in the
    original's style (style guide § 9) and the translation files carry it as a field, so
    a lint that measured only the English would pass a line the band cannot show.
    """
    encoder = StockEncoder.load()
    speaker = "Uncle"
    widest = DIALOGUE_BAND.width // encoder.advance("M")
    rows = [row for row in GOOD if row[0] != VOICED]
    line = [(VOICED, speaker, f"{'M' * widest} // Two.")]

    assert "page-width" not in checks(run(store, tmp_path, [*rows, *line], label=False))

    findings = run(store, tmp_path, [*rows, *line], label=True)
    finding = only(findings, "page-width")
    charged = widest * encoder.advance("M") + encoder.advance("M") * (len(speaker) + 1)
    assert f"{charged} px in {DIALOGUE_BAND.width}" in finding.message
    assert "the label and opening mark included" in finding.message


def test_the_label_narrows_only_page_one_s_first_line(store, tmp_path):
    """A page that fills the band exactly, with the label in front of line 1 alone.

    `BoxSpec` narrows the *tail* of a line (the next-page pencil); the label narrows the
    *head*, and only of page 1's first line. Taken off the box's width instead, every line
    of the page loses those pixels, and a page that fits is reported as one line too many
    -- which is what the three `page-lines` errors on `translation/days/day07.txt` were.

    Every number is asked of the encoder and the box, so the fixture cannot drift from
    either: the page is filled to each line's own limit, one word at a time.
    """
    encoder = StockEncoder.load()
    speaker = "Boku"
    reserve = label_allowance(encoder, speaker, LABEL_MARKS)
    assert reserve > 0, "the label costs nothing, so this test cannot show anything"
    word, gap = encoder.advance("M"), encoder.advance(" ")

    def words_in(limit: int, head: int = 0) -> int:
        """Single-cell words that fit in `limit` px with `head` px already spent."""
        return (limit - head + gap) // (word + gap)

    limits = [DIALOGUE_BAND.width_of_line(n) for n in range(1, DIALOGUE_BAND.lines + 1)]
    exact = words_in(limits[0], reserve) + sum(words_in(limit) for limit in limits[1:])
    charged_everywhere = sum(words_in(limit, reserve) for limit in limits)
    assert charged_everywhere < exact, "the label is too cheap to change the line count"

    rows = [row for row in GOOD if row[0] != UNVOICED]
    text = " ".join(["M"] * exact)
    findings = run(store, tmp_path, [*rows, (UNVOICED, speaker, text)], label=True)
    assert checks(findings) == [], f"{exact} words fill the band exactly; got {findings}"

    over = run(store, tmp_path, [*rows, (UNVOICED, speaker, f"{text} M")], label=True)
    finding = only(over, "page-lines")
    assert f"{DIALOGUE_BAND.lines + 1} lines" in finding.message


def one_message(tmp_path: Path, **message) -> object:
    """A store holding one unvoiced message, dressed as `SynthStore.message` is told."""
    synth = SynthStore.new(tmp_path)
    synth.message(UNVOICED, [[5]], voiced=False, speaker="BOKU", slot=0, **message)
    synth.scene("E9001", [UNVOICED])
    return load_store(synth.write())


def band_filler(encoder, head: int) -> str:
    """Single-cell words filling every line of the band exactly, `head` px already spent."""
    word, gap = encoder.advance("M"), encoder.advance(" ")
    limits = [DIALOGUE_BAND.width_of_line(n) for n in range(1, DIALOGUE_BAND.lines + 1)]
    count = (limits[0] - head + gap) // (word + gap)
    count += sum((limit + gap) // (word + gap) for limit in limits[1:])
    return " ".join(["M"] * count)


def test_the_closing_mark_the_build_appends_is_charged_too(tmp_path):
    """The band filled to the pixel, and the `」` the build puts after the last word.

    The harm, seen on the days build: the lint charged the label and the opening mark and
    nothing for the closer, so a page it passed was refused by `lay_out_message` -- and the
    line stayed Japanese with every gate green. Both sides of that disagreement are asked
    here rather than asserted from a number typed beside them: the same `original_marks`
    the build dresses with says what the marks are, and `lay_out_message` is run over the
    same text to show it really refuses.
    """
    store = one_message(tmp_path, marks=("", "」"))
    encoder = StockEncoder.load()
    table = GlyphTable.load()
    record = store.lines[UNVOICED]
    marks = original_marks(original_bytes(record, table), table)
    assert marks.closing and marks.labelled, f"the fixture draws {marks}; this test needs both"
    text = band_filler(encoder, label_allowance(encoder, "Boku", marks.opening))

    laid = lay_out_message(
        UNVOICED,
        (text,),
        original_bytes(record, table),
        encoder,
        DIALOGUE_BAND,
        opening="Boku" + marks.opening,
        closing=marks.closing,
    )
    assert laid.problems, "the build accepts this page, so there is nothing for the lint to catch"

    findings = run(store, tmp_path, [(UNVOICED, "Boku", text)])
    assert len(findings) == 1 and laid.problems[0].endswith(findings[0].message), (
        f"the build refuses this page with {laid.problems} and the lint says {findings}"
    )


def test_an_unlabelled_speaker_field_is_charged_the_mark_and_nothing_else(tmp_path):
    """`(unlabelled)` names nobody, and the build draws none of those twelve cells.

    `boku.layout.speaker_label` is the one rule for what a speaker field draws, and the
    build asks it; charging the raw field instead reserves a name-sized hole in front of a
    line that has none, and the lint refuses pages the band shows perfectly well.
    """
    store = one_message(tmp_path)
    encoder = StockEncoder.load()
    table = GlyphTable.load()
    marks = original_marks(original_bytes(store.lines[UNVOICED], table), table)
    assert marks.labelled, f"the fixture draws {marks}; an unlabelled one charges nothing"
    text = band_filler(encoder, label_allowance(encoder, "", marks.opening))

    assert run(store, tmp_path, [(UNVOICED, "(unlabelled)", text)]) == []
    assert label_allowance(encoder, "(unlabelled)", marks.opening) > label_allowance(
        encoder, "", marks.opening
    ), "the fixture's speaker field is free, so charging it would cost nothing"


def test_an_array_item_that_grows_is_an_error(store, tmp_path):
    """An array has no slack: the next symbol starts where the item ends."""
    size = store.lines[ARRAY]["capacity"]["bytes"]
    longest = size // 2 - 1  # the item's cells, plus its own terminator
    rows = [row for row in GOOD if row[0] != ARRAY]

    assert "array-bytes" not in checks(
        run(store, tmp_path, [*rows, (ARRAY, "Boku", "M" * longest)], label=False)
    )

    findings = run(store, tmp_path, [*rows, (ARRAY, "Boku", "M" * (longest + 1))], label=False)
    finding = only(findings, "array-bytes")
    assert finding.severity == ERROR
    assert f"needs {size + 2} bytes" in finding.message
    assert f"holds {size}" in finding.message


def test_an_array_glyph_token_the_font_redrew_is_unencodable_not_a_byte_problem(store, tmp_path):
    """`{G:n}` passes the sheet's own cell through; a cell the cell map took for a letter
    no longer draws that glyph, and the finding says so under the check that means it."""
    encoder = CellMapEncoder({"I": (700, 4), "t": (701, 4), "e": (702, 6), "m": (703, 9)})
    rows = [row for row in GOOD if row[0] != ARRAY]
    path = write_translation(tmp_path / "day99.txt", [*rows, (ARRAY, "Boku", "{G:700}")])
    parsed, _ = load_rows(translation_paths([path]))
    findings = [
        finding
        for finding in lint_rows(store, parsed, Options(encoder=encoder, label=False))
        if finding.line_id == ARRAY
    ]
    assert checks(findings) == ["unencodable"]
    assert "cell 700 draws 'I'" in findings[0].message


def test_an_array_item_wider_than_its_measured_box_is_an_error(store, tmp_path):
    """`PLAN TXT-07`: the byte limit is not the only one once a surface's box is measured
    (`research/data/text-boxes.tsv`). The box is the one the build lays the item out in."""
    encoder = StockEncoder.load()
    text = "Item"
    width = measure(encoder, text)
    rows = [row for row in GOOD if row[0] != ARRAY]

    def lint(right: int) -> list:
        boxes = {ARRAY: TextBox(ARRAY, 0, right, 0, 1, "test", "a test frame")}
        path = write_translation(tmp_path / "day99.txt", [*rows, (ARRAY, "Boku", text)])
        parsed, _ = load_rows(translation_paths([path]))
        return lint_rows(store, parsed, Options(encoder=encoder, label=False, boxes=boxes))

    assert "array-width" not in checks(lint(width))
    finding = only(lint(width - 1), "array-width")
    assert finding.severity == ERROR
    assert f"is {width} px" in finding.message and "1 over" in finding.message


def test_a_description_wrapped_past_its_box_s_lines_is_array_lines(store, tmp_path):
    """A box of several lines (an item description) wraps the English; more lines than it
    holds is its own check, not a byte or width one."""
    encoder = StockEncoder.load()
    rows = [row for row in GOOD if row[0] != ARRAY]
    boxes = {ARRAY: TextBox(ARRAY, 0, measure(encoder, "I"), 0, 2, "test", "a narrow frame")}
    path = write_translation(tmp_path / "day99.txt", [*rows, (ARRAY, "Boku", "I I I")])
    parsed, _ = load_rows(translation_paths([path]))
    found = lint_rows(store, parsed, Options(encoder=encoder, label=False, boxes=boxes))
    assert "array-lines" in checks(found), checks(found)


def test_the_additive_word_heuristic_warns_and_only_warns(store, tmp_path):
    """One English sentence against two sources: one with an intensifier, one without.

    Both the English word and the source word come from the lists the check itself uses,
    so the test cannot agree with a stale copy of either.
    """
    added = ADDITIVE_WORDS[0]
    rows = [row for row in GOOD if row[0] != UNVOICED]
    findings = run(store, tmp_path, [*rows, (UNVOICED, "Boku", f"It was {added} true.")])
    finding = only(findings, "additive-word")
    assert finding.severity == WARNING
    assert added in finding.message
    assert not any(f.severity == ERROR for f in findings)


def test_an_em_dash_warns_and_only_warns(store, tmp_path):
    """Style guide § 18: every em dash is a prompt to check the source, never a ban.

    The dash is `lint.EM_DASH`, the character the check looks for; the clean row beside it
    shows the finding is about the dash and not about the row. Measured with `--no-label`
    and a cell map that draws the dash, so no other finding can stand in for this one.
    """
    dashed, plain = f"Three {lint_module.EM_DASH} three.", "Three, three."
    encoder = layout_module.CellMapEncoder({c: (1, 6) for c in dashed + plain}, name="dash map")
    rows = [(UNVOICED, "Boku", dashed)]
    path = write_translation(tmp_path / "day99.txt", rows)
    parsed, _ = load_rows(translation_paths([path]))
    findings = lint_rows(store, parsed, Options(encoder=encoder, label=False))
    finding = only(findings, "em-dash")
    assert finding.severity == WARNING
    assert "§ 18" in finding.message
    assert checks(findings) == ["em-dash"]
    clean = write_translation(tmp_path / "day98.txt", [(UNVOICED, "Boku", plain)])
    parsed, _ = load_rows(translation_paths([clean]))
    assert lint_rows(store, parsed, Options(encoder=encoder, label=False)) == []


MENU = "exe@80001000"
LABEL = "exe@code:80002000"


@pytest.fixture
def surfaces(tmp_path: Path):
    """A code-file menu of three rows and a code-immediate label."""
    synth = SynthStore.new(tmp_path)
    synth.select_array(MENU, lines=3, cells=6)
    synth.code_label(LABEL)
    return load_store(synth.write())


def test_a_code_file_menu_is_a_sel_row_of_its_own_line_count(surfaces, tmp_path):
    """An S array is opened by `select_open_ptr` and drawn as a select: its rows are the
    `[SEL]` fields. The first lint read it as an array item drawn as a group and left it
    Japanese; written as `[SEL]` it was an error. The count is the original's."""
    assert run(surfaces, tmp_path, [(MENU, "[SEL]", "Go? | Yes | No")], label=False) == []
    finding = only(run(surfaces, tmp_path, [(MENU, "[SEL]", "Yes | No")]), "select-options")
    assert finding.severity == ERROR
    assert "3" in finding.message


def test_a_code_file_menu_that_outgrows_its_bytes_is_an_error(surfaces, tmp_path):
    size = surfaces.lines[MENU]["capacity"]["bytes"]
    long = "x" * (size // 2)
    finding = only(run(surfaces, tmp_path, [(MENU, "[SEL]", f"{long} | a | b")]), "array-bytes")
    assert finding.severity == ERROR
    assert f"holds {size}" in finding.message


def test_a_code_file_menu_row_is_measured_against_the_select_row(surfaces, tmp_path):
    """A code-file menu is drawn by `select_draw`: its rows get the select row, not the band."""
    encoder = StockEncoder.load()
    rows = [(MENU, "[SEL]", "Go? | Yes | No")]
    narrow = replace(SELECT_ROW, width=measure(encoder, "Go?") - 1)
    parsed, _ = load_rows(translation_paths([write_translation(tmp_path / "day99.txt", rows)]))
    options = Options(encoder=encoder, label=False, select_row=narrow)
    assert "select-width" in checks(lint_rows(surfaces, parsed, options))


def test_a_code_file_menu_written_as_a_plain_row_says_to_write_sel(surfaces, tmp_path):
    finding = only(run(surfaces, tmp_path, [(MENU, "(unlabelled)", "Go? Yes No")]), "select-shape")
    assert finding.severity == ERROR
    assert "[SEL]" in finding.message


def test_a_code_immediate_label_with_more_glyphs_than_the_code_draws_warns(surfaces, tmp_path):
    """Four drawn glyphs: "Date" is placed by rewriting their immediates, "Caught" needs two
    more draws than the function makes -- a layout change, so a warning with the counts."""
    assert run(surfaces, tmp_path, [(LABEL, "(unlabelled)", "Date")], label=False) == []
    findings = run(surfaces, tmp_path, [(LABEL, "(unlabelled)", "Caught")], label=False)
    assert checks(findings) == ["not-placeable"]
    assert findings[0].severity == WARNING
    assert "draws [4] glyph(s) per run and 'Caught' needs [6]" in findings[0].message


def test_the_save_title_must_say_where_the_slot_and_the_day_go(tmp_path):
    synth = SynthStore.new(tmp_path)
    title = synth.save_title()["id"]
    store = load_store(synth.write())
    good = [(title, "(unlabelled)", "Boku's Memories {slot} August {day}")]
    assert run(store, tmp_path, good, label=False) == []
    finding = only(
        run(store, tmp_path, [(title, "(unlabelled)", "Boku's Memories August")], label=False),
        "save-title",
    )
    assert finding.severity == ERROR


def test_a_settled_phrase_holding_an_intensifier_is_not_an_addition(store, tmp_path):
    """Fat's *ore-sama* is "yours truly" (style guide § 5); the word list's "truly" fired on
    it every time he spoke of himself."""
    assert "truly" in ADDITIVE_WORDS
    rows = [row for row in GOOD if row[0] != UNVOICED]
    findings = run(store, tmp_path, [*rows, (UNVOICED, "Fat", "Leave it to yours truly.")])
    assert "additive-word" not in checks(findings)


def voice_note(line_id: str, words: str, why: str = "fits his voice") -> tuple[str]:
    """A `# VOICE` note as a one-field "row", which `write_translation` writes as it is."""
    return (f"# VOICE {line_id}: {words} -- {why}",)


def test_a_voice_note_settles_the_words_it_names(store, tmp_path):
    """PLAN TRN-16: a flagged word a second-pass translator kept on purpose is recorded once,
    by id, and the heuristic stops asking. The note sits away from its row on purpose: it is
    matched by id, not by position."""
    added = ADDITIVE_WORDS[0]
    rows = [row for row in GOOD if row[0] != UNVOICED]
    line = (UNVOICED, "Boku", f"It was {added} true.")
    assert "additive-word" in checks(run(store, tmp_path, [*rows, line]))
    findings = run(store, tmp_path, [*rows, line, voice_note(UNVOICED, added)])
    assert "additive-word" not in checks(findings)
    assert "voice-note" not in checks(findings)


def test_a_voice_note_settles_only_the_words_it_names(store, tmp_path):
    """A note for one word does not excuse a second word added later."""
    kept, other = ADDITIVE_WORDS[0], ADDITIVE_WORDS[1]
    rows = [row for row in GOOD if row[0] != UNVOICED]
    line = (UNVOICED, "Boku", f"It was {kept} {other} true.")
    finding = only(run(store, tmp_path, [*rows, line, voice_note(UNVOICED, kept)]), "additive-word")
    assert other in finding.message
    assert kept not in finding.message.split("--")[0].split(":")[1]


def test_a_voice_note_for_a_word_the_heuristic_does_not_flag_is_stale(store, tmp_path):
    """The line was rewritten and the word is gone: the note now records nothing true."""
    added = ADDITIVE_WORDS[0]
    rows = [row for row in GOOD if row[0] != UNVOICED]
    findings = run(
        store, tmp_path, [*rows, (UNVOICED, "Boku", "It was true."), voice_note(UNVOICED, added)]
    )
    finding = only(findings, "voice-note")
    assert finding.severity == WARNING
    assert finding.line_id == UNVOICED
    assert added in finding.message


def test_a_voice_note_naming_no_row_of_its_file_is_reported(store, tmp_path):
    findings = run(store, tmp_path, [*GOOD, voice_note("E9001.9", ADDITIVE_WORDS[0])])
    finding = only(findings, "voice-note")
    assert finding.severity == WARNING
    assert finding.line_id == "E9001.9"


def test_a_voice_note_naming_a_list_of_ids_settles_nothing_and_says_so(store, tmp_path):
    """`# NOTE` takes an id list; a VOICE note is one id, so a list would otherwise be passed
    over silently, with the line still flagged and no word why."""
    added = ADDITIVE_WORDS[0]
    rows = [row for row in GOOD if row[0] != UNVOICED]
    line = (UNVOICED, "Boku", f"It was {added} true.")
    note = (f"# VOICE {UNVOICED}, .2: {added} -- his voice",)
    findings = run(store, tmp_path, [*rows, line, note])
    assert "additive-word" in checks(findings)
    assert "one id" in only(findings, "voice-note").message


def test_the_parse_reports_only_what_a_file_cannot_hold(tmp_path):
    """`parse_text`'s findings refuse a translator's answer (`boku.packets.check_answer`) and
    fail the lock check (`boku.locked.committed_english`), so a VOICE note's warnings are the
    lint's to give, not the parse's."""
    text = f"# VOICE {UNVOICED}: just\n# VOICE E9001.9: just -- x\n{UNVOICED}\tBoku\tThree.\n"
    rows, findings = parse_text(text, tmp_path / "day99.txt")
    assert findings == []
    assert [row.line_id for row in rows] == [UNVOICED]


def test_a_voice_note_without_its_reason_does_not_settle_anything(store, tmp_path):
    """The note is the record of a decision; a bare word list records none."""
    added = ADDITIVE_WORDS[0]
    rows = [row for row in GOOD if row[0] != UNVOICED]
    line = (UNVOICED, "Boku", f"It was {added} true.")
    findings = run(store, tmp_path, [*rows, line, (f"# VOICE {UNVOICED}: {added}",)])
    assert "additive-word" in checks(findings)
    assert only(findings, "voice-note").line_id == UNVOICED


def test_the_heuristic_is_silent_when_the_source_has_an_intensifier(tmp_path):
    """The same English, over a line whose Japanese carries one. No finding."""
    synth = SynthStore.new(tmp_path)
    marker = SOURCE_INTENSIFIERS[0]
    synth.message(UNVOICED, [[3]], voiced=False, label=False, prefix=marker)
    synth.scene("E9001", [UNVOICED])
    store = load_store(synth.write())
    rows = [(UNVOICED, "Boku", f"It was {ADDITIVE_WORDS[0]} true.")]
    assert checks(run(store, tmp_path, rows)) == []


def test_the_word_lists_do_not_overlap_by_accident():
    """A source intensifier that is also an English one would silence the check."""
    assert not set(ADDITIVE_WORDS) & set(SOURCE_INTENSIFIERS)
    assert all(word == word.lower() for word in ADDITIVE_WORDS)


def test_a_row_with_no_tab_is_an_error(store, tmp_path):
    path = tmp_path / "day99.txt"
    path.write_text("E9001.0 Uncle One.\n", encoding="utf-8")
    rows, findings = load_rows(translation_paths([path]))
    assert rows == []
    assert [finding.check for finding in findings] == ["malformed"]


def test_the_lint_agrees_with_the_build_s_own_loader(store, tmp_path):
    """`reader-vs-loader`: a row this module and `SampleScenes` read differently."""
    findings = run(store, tmp_path, GOOD, label=False)
    assert "reader-vs-loader" not in checks(findings)


# --- one home per rule -------------------------------------------------------------------------


def test_the_default_cell_map_is_the_edit_set_the_build_installs():
    """The lint measures in the font `./make.sh build-days` actually writes into the image.

    The path is read back out of `make.sh` -- the one place a recurring command is written
    (this repo's CLAUDE.md) -- rather than retyped beside `DEFAULT_CELLS`, so the two
    cannot drift together. The harm was measured: while this pointed at the prototype's
    `manifest.json`, `--edits-only` wrote no manifest at all, so a lint and a build could
    green each other's gates over two different fonts.
    """
    script = (REPO_ROOT / "make.sh").read_text(encoding="utf-8")
    directory = re.search(r'local font="([^"]+)"', script)
    name = re.search(r'--vwf "\$font/([^"]+)"', script)
    assert directory and name, "make.sh no longer builds through a --vwf edit set"
    assert REPO_ROOT / directory.group(1) / name.group(1) == DEFAULT_CELLS


def write_edit_set(path: Path, cells: dict) -> Path:
    """The smallest document `boku build --vwf` accepts, carrying `cells`."""
    path.write_text(
        json.dumps(
            {
                "format": VWF_EDITS_FORMAT,
                "cells": cells,
                "edits": [{"file": EXE_NAME, "offset": 0, "old": "00", "new": "01"}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_the_lint_and_the_build_read_one_font_out_of_one_file(tmp_path):
    """`--encoder cellmap` and `boku build --vwf` over the same file must measure alike.

    Asserted as an equality between the two readers rather than against a width written
    here: a hand-typed advance passes exactly when both readers drift together, which is
    the moment the check was needed.
    """
    cells = {"A": {"id": 292, "advance": 9}, " ": {"id": 10, "advance": 4}}
    path = write_edit_set(tmp_path / "edits.json", cells)
    encoder = make_encoder("cellmap", path)
    assert encoder.cells == load_edit_set(path).encoder.cells
    assert encoder.advance("A") == cells["A"]["advance"]


def test_with_no_cells_switch_the_default_is_read_and_named_when_it_is_missing(
    tmp_path, monkeypatch
):
    """`--cells` overrides; without it the default is read, and a missing one is loud.

    Silence is the failure mode that matters here -- a lint that quietly measured last
    week's font would pass lines the build wraps differently -- so the refusal has to name
    the file it wanted and the command that writes it.
    """
    default = write_edit_set(tmp_path / "edits.json", {"A": {"id": 1, "advance": 9}})
    override = write_edit_set(tmp_path / "other.json", {"A": {"id": 2, "advance": 3}})
    monkeypatch.setattr(lint_module, "DEFAULT_CELLS", default)

    assert make_encoder("cellmap", None).advance("A") == 9
    assert make_encoder("cellmap", override).advance("A") == 3

    default.unlink()
    with pytest.raises(LayoutError, match=re.escape(str(default))) as error:
        make_encoder("cellmap", None)
    assert "./make.sh build-days" in str(error.value)


def test_the_rules_this_module_shares_are_defined_where_they_belong():
    """The lint re-exports them; it does not own them.

    The marks and the label's pixels belong beside `boku.layout.lay_out_message`, which
    inserts the same runs while a build lays words out, and a `[SEL]` row's fields belong
    beside the `TranslationEntry` they are read off. A second definition is a lint and a
    build disagreeing about what is drawn around a line, or about which field is the
    question -- silently, because both would still be internally consistent.
    """
    assert LabelledBox.__module__ == "boku.layout"
    assert label_allowance.__module__ == "boku.layout"
    assert select_fields.__module__ == "boku.translation"
    assert lint_module.original_marks is layout_module.original_marks
    assert lint_module.speaker_label is layout_module.speaker_label
    assert lint_module.select_fields is translation_module.select_fields


# --- the movie cues ------------------------------------------------------------------------------


def test_the_movie_cues_are_linted_with_their_file_and_line(tmp_path):
    """`translation/movies.txt` rides the same report as the day files, each rule a
    `boku.movie_cues` check, each finding pointing at its row."""
    cues = tmp_path / "movies.txt"
    cues.write_text("# note\nM60\t1\t9999\tAB\nM60\t5\t6\tA | B | A\n", encoding="utf-8")
    font = CellMapEncoder({"A": (1, 9), "B": (2, 9), " ": (3, 4)}, name="test")
    found = lint_movies(cues, font, tmp_path / "cells.json")
    assert [(f.file, f.number, f.line_id, f.check, f.severity) for f in found] == [
        ("movies.txt", 2, "M60@1", "cue-frames", ERROR),
        ("movies.txt", 3, "M60@5", "cue-lines", ERROR),
        ("movies.txt", 3, "M60@5", "cue-overlap", ERROR),
    ]


def test_movie_cues_without_a_font_are_checked_and_their_pixels_said_to_be_unmeasured(tmp_path):
    cues = tmp_path / "movies.txt"
    cues.write_text("M60\t1\t2\t" + "A" * 400 + "\n", encoding="utf-8")
    found = lint_movies(cues, None, tmp_path / "named.json")
    assert [(f.check, f.severity) for f in found] == [("cue-unmeasured", WARNING)]
    assert "named.json" in found[0].message, "the warning names a cell map nobody asked for"


def test_a_cue_file_named_on_the_command_line_that_is_not_there_is_an_error(tmp_path):
    """A mistyped `--movies` used to lint nothing and pass; only the default file, which a
    checkout before any cue need not have, may be absent."""
    options = Options(encoder=StockEncoder.load(), box=DIALOGUE_BAND)
    with pytest.raises(OSError):
        lint_movie_file(tmp_path / "movie.txt", options, tmp_path / "cells.json")
    assert lint_movie_file(None, options, None) == []


# --- voice-only subtitles (VO-02) ---------------------------------------------------------------


def test_a_voice_only_row_with_english_is_linted_as_a_subtitle(store, tmp_path):
    """Its English is what the band will draw, so the band's limits apply; there is no
    Japanese to hold it against, and the build and the lint read the row the same way."""
    rows = [row for row in GOOD if row[0] != VOICE_ONLY]
    clean = [*rows, (VOICE_ONLY, "(voice only)", "I thought the well was odd. // So I looked.")]
    assert run(store, tmp_path, clean, label=False) == []

    too_long = " ".join(["wide"] * 60)
    finding = only(
        run(store, tmp_path, [*rows, (VOICE_ONLY, "(voice only)", too_long)], label=False),
        "subtitle-fit",
    )
    assert finding.severity == ERROR
    assert "lines in" in finding.message


def test_a_subtitle_given_twice_is_an_error(store, tmp_path):
    first = write_translation(tmp_path / "day99.txt", [(VOICE_ONLY, "(voice only)", "One.")])
    second = write_translation(tmp_path / "shared99.txt", [(VOICE_ONLY, "(voice only)", "Two.")])
    rows, _ = load_rows(translation_paths([first, second]))
    findings = lint_rows(store, rows, Options(encoder=StockEncoder.load(), label=False))
    assert only(findings, "translated-twice").file == "shared99.txt"


def test_arrays_that_move_are_held_to_the_room_the_build_would_find(tmp_path):
    """A relocatable array's item is no longer held to its own bytes, so the lint asks the
    same question the build does -- does every grown array fit the free space -- through
    `Options.array_room`, and a refusal names the lines left in Japanese."""
    item = "exe@80046214.0"  # item names: a catalogue array with an anchor
    synth = SynthStore.new(tmp_path)
    synth.array_item(item, cells=4)
    store = load_store(synth.write())
    path = write_translation(
        tmp_path / "day99.txt", [(item, "Boku", "M" * 8)]
    )  # past 4 cells, inside the box
    parsed, _ = load_rows(translation_paths([path]))
    asked: list[dict] = []

    def no_room(words, blocks):
        asked.append(dict(words))
        return [(item, "no room")]

    options = Options(encoder=StockEncoder.load(), label=False, array_room=no_room)
    findings = lint_rows(store, parsed, options)
    assert "array-bytes" not in checks(findings), "a moving array is not held to its bytes"
    assert asked and item in asked[0], "the laid-out words were not offered to the room check"
    room = only(findings, "array-room")
    assert (room.line_id, room.message) == (item, "no room")


def test_a_date_label_must_mark_where_its_numbers_go(tmp_path):
    """`exe@code:80037544` is redrawn around its English (`asm/labels.asm`): the row says
    where the month and the day are drawn, and a row that does not is an error, not a
    not-placeable warning -- the drawer can hold any English."""
    synth = SynthStore.new(tmp_path)
    label = synth.code_label("exe@code:80037544")["id"]
    store = load_store(synth.write())
    good = [(label, "(unlabelled)", "Date caught {month}/{day}")]
    assert run(store, tmp_path, good, label=False) == []
    bad = run(store, tmp_path, [(label, "(unlabelled)", "Date caught")], label=False)
    assert checks(bad) == ["date-label"]
    assert bad[0].severity == ERROR


def test_an_unreachable_surface_is_reported_not_held_to_its_bytes(tmp_path):
    """`boku.arrays.UNREACHABLE`: bug sumo's move names are drawn only on a debug path, so
    their English is kept but never written, and the lint says so once, as a warning --
    not an `array-bytes` error for English that no player can see overflow."""
    synth = SynthStore.new(tmp_path)
    synth.array_item(MOVES, cells=4)
    moves = load_store(synth.write())
    findings = run(moves, tmp_path, [(MOVES, "(unlabelled)", "M" * 40)], label=False)
    finding = only(findings, "unreachable")
    assert checks(findings) == ["unreachable"]
    assert finding.severity == WARNING
    assert "Reopen when" in finding.message


def test_a_notebook_name_is_held_to_the_room_beside_the_badge(tmp_path):
    """`exe@8003D2E0.<n>@exchange` (`boku.exchange_notebook`) names a line of the insect
    names: it is laid out in the notebook's own box, and one whose line is not in the script
    is an unknown id like any other."""
    synth = SynthStore.new(tmp_path)
    synth.array_item("exe@8003D2E0.23", cells=8)
    store = load_store(synth.write())
    room = exchange_notebook.box().spec.width // StockEncoder.load().advance("M")
    short = [("exe@8003D2E0.23@exchange", "(unlabelled)", "M" * room)]
    assert run(store, tmp_path, short, label=False) == []
    wide = run(store, tmp_path, [(short[0][0], "(unlabelled)", "M" * (room + 1))], label=False)
    assert checks(wide) == ["array-width"]
    unknown = [("exe@8003D2E0.24@exchange", "(unlabelled)", "M")]
    assert checks(run(store, tmp_path, unknown, label=False)) == ["unknown-id"]
