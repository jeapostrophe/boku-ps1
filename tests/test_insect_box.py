"""`boku.insect_box`: the notebook's copy of an insect entry, and the two copies' pairs."""

from __future__ import annotations

from boku.archive import OVERLAY_LOAD_ADDRESS
from boku.array_relocate import plan_arrays
from boku.arrays import walk_all
from boku.glyphs import END_WORD, NEWLINE_WORD, words_of
from boku.insect_box import (
    ENTRIES,
    GRID_PAIR,
    NOTEBOOK,
    NOTEBOOK_PAIR,
    NOTEBOOK_ROWS,
    notebook_words,
)
from boku.layout import BoxSpec, CellMapEncoder, LaidOut, measure, sheet_cells, wrap
from boku.pointers import resolve_at

CELLS = {" ": (10, 4), "a": (302, 6), "b": (303, 6), ".": (40, 3)}
ENCODER = CellMapEncoder(CELLS)
BOX = BoxSpec(width=measure(ENCODER, "aa aa"), lines=99, name="entry", pitch=12)


def _laid_rows(rows, box=BOX) -> LaidOut:
    """What `lay_out_array` makes of an entry laid out in these rows."""
    words: list[int] = []
    for number, row in enumerate(rows):
        words += [NEWLINE_WORD] * bool(number) + list(sheet_cells(ENCODER, row, box.pitch).cells)
    return LaidOut("hhon@5328.0", (*words, END_WORD), (tuple(rows),), (), ())


def _laid(text: str) -> LaidOut:
    return _laid_rows(wrap(ENCODER, text, BOX))


def _rows(words):
    return list(_split(words))


def _split(words):
    row = []
    for word in words:
        if word in (NEWLINE_WORD, END_WORD):
            yield row
            row = []
        else:
            row.append(word)


def test_an_entry_the_page_holds_needs_no_copy_of_its_own():
    assert notebook_words(_laid(" ".join(["aa"] * 2 * NOTEBOOK_ROWS)), ENCODER, BOX) is None


def test_a_longer_entry_keeps_its_first_rows_and_ends_the_last_with_an_ellipsis():
    """Narrowest: one row more than the page. Row 8 keeps what fits beside "...", within
    the box, and nothing after it is drawn."""
    text = " ".join(["aa"] * 2 * (NOTEBOOK_ROWS + 1))
    words = notebook_words(_laid(text), ENCODER, BOX)
    rows = _rows(words)
    assert len(rows) == NOTEBOOK_ROWS
    a, dot = CELLS["a"][0], CELLS["."][0]
    assert rows[:-1] == [[a, a, CELLS[" "][0], a, a]] * (NOTEBOOK_ROWS - 1)
    assert rows[-1] == [a, a, dot, dot, dot], "a word dropped for the ellipsis"
    assert words[-1] == END_WORD


def test_an_eighth_row_too_wide_for_any_word_and_the_ellipsis_keeps_only_the_ellipsis():
    """Row 8 a single word as wide as the box: no word fits beside "...", so the row is the
    ellipsis alone, inside the box."""
    rows = ["aa"] * (NOTEBOOK_ROWS - 1) + ["aaaa", "aa"]
    wide = BoxSpec(width=measure(ENCODER, "aaaa"), lines=99, name="entry", pitch=12)
    laid = _laid_rows(rows, wide)
    last = _rows(notebook_words(laid, ENCODER, wide))[-1]
    assert last == [CELLS["."][0]] * 3


def test_each_screen_s_pair_forms_its_own_copy(archive):
    """The grid's pair addresses the whole entries, the notebook's its cut copy -- both in
    `HHON.OVL`'s tail, the only image that reads them."""
    walked = next(w for w in walk_all(archive) if w.array.line_id_prefix == ENTRIES)
    (start, end) = walked.strings[0]
    first = walked.line_ids[0]
    grid = (0x100,) * ((end - start) // 2 + 1) + (END_WORD,)
    note = (0x101,) * 3 + (END_WORD,)
    plan = plan_arrays(archive, {first: grid, first + NOTEBOOK: note}, regions=())
    moved = {m.prefix: m for m in plan.moved}
    assert set(moved) == {ENTRIES, ENTRIES + NOTEBOOK}
    member = archive.member("HHON.OVL")
    code = bytearray(archive.blob(member))
    for e in plan.edits:
        if member.offset <= e.offset < member.offset + member.size:
            code[e.offset - member.offset : e.end - member.offset] = e.new
    code += plan.tails["HHON.OVL"].data

    def read(at, n):
        return bytes(code[at - OVERLAY_LOAD_ADDRESS : at - OVERLAY_LOAD_ADDRESS + n])

    assert resolve_at(read, GRID_PAIR) == moved[ENTRIES].new
    assert resolve_at(read, NOTEBOOK_PAIR) == moved[ENTRIES + NOTEBOOK].new
    assert words_of(read(moved[ENTRIES + NOTEBOOK].new, 2 * len(note))) == note
    assert words_of(read(moved[ENTRIES].new, 2 * len(grid))) == grid


def test_the_days_build_points_each_screen_at_a_copy_that_fits_it(days_built):
    """Read back: the two pairs form different addresses, and every notebook entry is at
    most `NOTEBOOK_ROWS` rows."""

    def read(at, n):
        return days_built.overlay_bytes("HHON.OVL", at, n)

    grid, notebook = resolve_at(read, GRID_PAIR), resolve_at(read, NOTEBOOK_PAIR)
    assert grid != notebook, "one copy for both screens: the notebook would overflow its page"
    walked = next(w for w in walk_all(days_built) if w.array.line_id_prefix == ENTRIES)
    words = words_of(read(notebook, 2 * 16384))
    entries, entry = [], []
    for word in words:
        entry.append(word)
        if word == END_WORD:
            entries.append(entry)
            entry = []
            if len(entries) == len(walked.line_ids):
                break
    assert len(entries) == len(walked.line_ids)
    assert max(e.count(NEWLINE_WORD) + 1 for e in entries) <= NOTEBOOK_ROWS


def test_a_refused_entry_takes_its_notebook_copy_with_it(archive):
    """The room check pops a refused entry's id from the words, not its copy's key; the
    copy alone must not move, or the notebook would show English the grid does not."""
    first = f"{ENTRIES}.0"
    plan = plan_arrays(archive, {first + NOTEBOOK: (0x101, END_WORD)}, regions=())
    assert plan.moved == ()
