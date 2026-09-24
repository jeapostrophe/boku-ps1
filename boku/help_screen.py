"""`PLAN PIPE-07`: the controls-help screen's bottom sentence on three rows.

`help_screen_draw` (`0x80035674`) draws help lines 0-12 at `g_help_pos` (`0x80029904`, an
(x, y) byte pair each), one row per item of `exe@80029B20` (an **L** array: each item ends
with `0x8001`). The bottom sentence is lines 11 and 12, at y 170 and 184 in the Japanese; the
English of line 11 needs two rows. The build splits it the way it splits a card message
(`boku.row_split`): line 11 keeps its first row, and the second becomes an item after the
array's last, which `asm/help_resident.asm` (`vwf_help_extra_row`, called from
`help_screen_draw`) draws at line 12's place while line 12 moves one row down. That move is
the build's own edit and is what tells the routine to draw: only at exactly one row below its
retail y, which a line 11 left in Japanese never gets.
"""

from __future__ import annotations

from collections.abc import Sequence

from boku.archive import EXE_LOAD_BIAS, EXE_NAME, Archive
from boku.arrays import HELP_TEXT, array_of
from boku.reinsert import ByteEdit
from boku.row_split import RowSplitRefused, Split

HELP_POS = 0x80029904
"""`g_help_pos`: an (x, y) byte pair per help line 0-12."""
SPLIT_LINE = 11
"""The one line that may take a second row: the bottom sentence's first half."""
NEXT_LINE = 12
"""The line under it, which moves down a row to make room."""


def y_at(line: int) -> int:
    """The address of help line `line`'s y in `g_help_pos`."""
    return HELP_POS + 2 * line + 1


def pos_y(archive: Archive, line: int) -> int:
    return archive.exe_bytes(y_at(line), 1)[0]


def row_pitch(archive: Archive) -> int:
    """The bottom lines' spacing, from their retail rows."""
    return pos_y(archive, NEXT_LINE) - pos_y(archive, SPLIT_LINE)


def help_edits(archive: Archive, found: Sequence[Split]) -> list[ByteEdit]:
    """Line 12 one row down when line 11 was split in two; refuses any other split -- the
    routine draws one extra row, for line 11."""
    if not found:
        return []
    bad = [s.line_id for s in found if s.item != SPLIT_LINE or len(s.rest) != 1]
    if bad:
        raise RowSplitRefused(
            f"{', '.join(bad)}: the help screen draws one extra row, the second of line "
            f"{SPLIT_LINE}",
            bad,
        )
    y = pos_y(archive, NEXT_LINE)
    return [
        ByteEdit(
            EXE_NAME,
            y_at(NEXT_LINE) - EXE_LOAD_BIAS,
            bytes([y]),
            bytes([y + row_pitch(archive)]),
            f"{HELP_TEXT}.{NEXT_LINE} a row down for line {SPLIT_LINE}'s second (PLAN PIPE-07)",
        )
    ]


def help_equates(archive: Archive) -> dict[str, int]:
    """What `asm/help_resident.asm` is assembled with: where line 11's x and line 12's y
    are, line 12's retail y and the row pitch, and the item line 11's second row becomes
    (the first after the array's last, `boku.row_split`)."""
    array = array_of(HELP_TEXT)
    if array is None:
        raise RowSplitRefused(f"the catalogue has no {HELP_TEXT}", ())
    return {
        "HELP_SPLIT_X": y_at(SPLIT_LINE) - 1,
        "HELP_NEXT_Y": y_at(NEXT_LINE),
        "HELP_EXTRA_ITEM": array.spec,
        "HELP_NEXT_Y_RETAIL": pos_y(archive, NEXT_LINE),
        "HELP_ROW_PITCH": row_pitch(archive),
    }
