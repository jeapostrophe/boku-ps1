"""`PLAN PIPE-06` -- every check made red on purpose, at the narrowest input that shows it.

Each test here builds a translation file that passes, changes **one** thing, and asserts
the lint goes red *with the finding that names the harm* -- not merely that something
failed. The numbers a test asserts on (a box's width, an array item's byte size, the
encoder's advance, the word lists) are read out of the thing under test, never retyped
beside it: a fixture that holds its own copy of the limit passes exactly when the two
copies drift together (`~/.claude/CLAUDE.md` ENG-1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boku.layout import DIALOGUE_BAND, StockEncoder
from boku.lint import (
    ADDITIVE_WORDS,
    ERROR,
    LABEL_MARKS,
    SOURCE_INTENSIFIERS,
    WARNING,
    Options,
    label_allowance,
    lint_rows,
    load_rows,
    translation_paths,
)
from boku.script_store import load_store
from tests.synth_script import SynthStore, write_translation

VOICED = "E9001.0"
UNVOICED = "E9001.1"
CHOICE = "E9001.2"
VOICE_ONLY = "E9001.3"
ARRAY = "exe@80000000.0"


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


# --- the four the reader also reports ---------------------------------------------------------


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


def test_a_select_s_question_is_not_counted_as_an_option(tmp_path):
    """A `[SEL]` whose box opens with a question lists the question as the first field.

    That is the committed convention -- style guide § 13, `translation/days/README.md`
    § shared.txt, and the header of `translation/days/shared.txt` itself -- and it is what
    `boku.layout.lay_out_select` and the reader's `select_fields` both read. Counted as an
    option instead, every prompt-bearing select in the game is a false error, and the
    reader and the lint disagree about the one check they are supposed to share.
    """
    synth = SynthStore.new(tmp_path)
    synth.select(CHOICE, options=2, prompts=1)
    synth.scene("E9001", [CHOICE])
    store = load_store(synth.write())
    shape = store.lines[CHOICE]["select"]
    options = shape["lines"] - shape["prompt_lines"]

    good = [(CHOICE, "[SEL]", "What will you read? | Insects | Kites")]
    assert checks(run(store, tmp_path, good, label=False)) == []

    short = [(CHOICE, "[SEL]", "What will you read? | Insects")]
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
    assert "label included" in finding.message


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
