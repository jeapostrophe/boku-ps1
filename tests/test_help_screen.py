"""`boku.help_screen`: the controls-help screen's bottom sentence on three rows."""

from __future__ import annotations

import pytest

from boku.archive import EXE_LOAD_BIAS, EXE_NAME
from boku.array_relocate import ArrayRoomRefused, plan_arrays
from boku.arrays import HELP_TEXT, walk_all
from boku.glyphs import NEWLINE_WORD, words_of
from boku.help_screen import NEXT_LINE, SPLIT_LINE, pos_y, y_at

A, B = 0x100, 0x101
TWO_ROWS = (A, NEWLINE_WORD, B, NEWLINE_WORD)


def _walked(archive):
    return next(w for w in walk_all(archive) if w.array.line_id_prefix == HELP_TEXT)


def test_line_11_on_two_rows_appends_its_second_and_moves_line_12_down(archive):
    """Narrowest: line 11 on two rows. Its second row is an item after the array's last,
    and line 12's y in `g_help_pos` moves one retail row (line 11 to line 12) down."""
    walked = _walked(archive)
    plan = plan_arrays(archive, {f"{HELP_TEXT}.{SPLIT_LINE}": TWO_ROWS}, regions=())
    (moved,) = plan.moved
    exe = bytearray(archive.exe)
    for e in plan.edits:
        if e.file == EXE_NAME:
            exe[e.offset : e.end] = e.new
    at = y_at(NEXT_LINE)
    # the retail bottom lines sit at y 170 and 184 (g_help_pos); the third row is 198
    assert (pos_y(archive, SPLIT_LINE), pos_y(archive, NEXT_LINE)) == (170, 184)
    assert exe[at - EXE_LOAD_BIAS] == 198
    blob = bytes(exe[moved.new - EXE_LOAD_BIAS :][: moved.size])
    rows, row = [], []
    for word in words_of(blob):
        row.append(word)
        if word & 0x8000:
            rows.append(row)
            row = []
    assert len(rows) == len(walked.line_ids) + 1
    assert rows[SPLIT_LINE] == [A, NEWLINE_WORD] and rows[-1] == [B, NEWLINE_WORD]


def test_any_other_help_line_on_two_rows_is_refused(archive):
    """The routine draws one extra row, for line 11."""
    line = f"{HELP_TEXT}.{NEXT_LINE}"
    with pytest.raises(ArrayRoomRefused, match="one extra row") as refused:
        plan_arrays(archive, {line: TWO_ROWS}, regions=())
    assert refused.value.lines == (line,)


def test_every_row_split_array_has_a_drawer_for_its_added_rows():
    """An array in `ROW_SPLITS` without an entry in `ROW_DRAWERS` would grow rows nothing
    draws."""
    from boku.array_relocate import ROW_DRAWERS
    from boku.arrays import ROW_SPLITS

    assert set(ROW_DRAWERS) == ROW_SPLITS
