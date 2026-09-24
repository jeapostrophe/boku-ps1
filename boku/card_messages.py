"""`PLAN TXT-07`: a memory-card message on more than one line.

`mc_msg_draw` (`TITLE.OVL` `0x8007CB54`) draws one *record* of `g_mc_msg` (`TITLE`
`0x800814C0`, 32 records `{rows, layout, item[3]}`, an unused slot 99): up to three items of
`exe@8003D5F0`, one per row, row k at `g_mc_msg_y[layout] + 16k`. Each item ends with
`0x8001` (an **L** array) and the reader finds item n by counting those, so an item holds
exactly one row. When a box gives an item more rows (`research/data/text-boxes.tsv`), the
build lays it out as rows back to back, each ended by `0x8001`, and this module splits it:
the item keeps its first row, each further row becomes a new item appended after the
array's last, and every record that shows the item gains those rows. The record's layout
moves to the one whose first row is nearest 8 px higher per row gained, so the block stays
centred where it was (research/vwf-prototype.md § "The fixed-pitch boxes" has the
measurements).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from boku.archive import ARCHIVE_NAME, Archive
from boku.arrays import ROW_SPLIT, array_of
from boku.glyphs import NEWLINE_WORD
from boku.reinsert import ByteEdit

RECORDS = 0x800814C0
"""`g_mc_msg`, in `TITLE.OVL`."""
RECORD_COUNT = 32
RECORD_BYTES = 5
UNUSED = 99
MAX_ROWS = 3
LAYOUT_Y = 0x80079BDC
"""`g_mc_msg_y`, one halfword per layout, copied to the stack by `mc_msg_draw`."""
LAYOUTS = 7
LAYOUTS_AT_PEN_34 = range(5)
"""Layouts 5 and 6 start their rows at x 74 (`mc_msg_draw`), a different box; a record
using one is not re-laid out."""
TITLE = "TITLE.OVL"


class CardSplitRefused(Exception):
    def __init__(self, message: str, lines: Sequence[str]) -> None:
        super().__init__(message)
        self.lines = tuple(lines)


@dataclass(frozen=True)
class Split:
    line_id: str
    item: int
    head: tuple[int, ...]
    """The item's first row, ended by `0x8001`: what it keeps."""
    rest: tuple[tuple[int, ...], ...]
    """Its further rows, each an item of its own, ended by `0x8001`."""
    added: tuple[int, ...]
    """The item numbers the further lines get, after the array's last."""


def splits(words: Mapping[str, Sequence[int]]) -> list[Split]:
    """Every item of `exe@8003D5F0` in `words` laid out on more than one row, in item
    order; the first new item is numbered after the array's last."""
    array = array_of(ROW_SPLIT)
    if array is None:
        raise CardSplitRefused(f"the catalogue has no {ROW_SPLIT}", ())
    items = array.spec
    found: list[Split] = []
    following = items
    for item in range(items):
        line_id = f"{ROW_SPLIT}.{item}"
        rows: list[tuple[int, ...]] = []
        row: list[int] = []
        for word in words.get(line_id, ()):
            row.append(word)
            if word == NEWLINE_WORD:
                rows.append(tuple(row))
                row = []
        if len(rows) < 2:
            continue
        head, *rest = rows
        added = tuple(range(following, following + len(rest)))
        following += len(rest)
        found.append(Split(line_id, item, head, tuple(rest), added))
    return found


def _records(archive: Archive) -> list[list[int]]:
    table = archive.overlay_bytes(TITLE, RECORDS, RECORD_BYTES * RECORD_COUNT)
    return [list(table[i : i + RECORD_BYTES]) for i in range(0, len(table), RECORD_BYTES)]


def _layout_y(archive: Archive) -> list[int]:
    raw = archive.overlay_bytes(TITLE, LAYOUT_Y, 2 * LAYOUTS)
    return [int.from_bytes(raw[i : i + 2], "little", signed=True) for i in range(0, len(raw), 2)]


def record_edits(archive: Archive, found: Sequence[Split]) -> list[ByteEdit]:
    """The `g_mc_msg` records to rewrite so every split item's rows are drawn; refuses,
    naming the line, a record that would pass three rows or uses a layout at pen 74."""
    if not found:
        return []
    by_item = {split.item: split for split in found}
    ys = _layout_y(archive)
    edits: list[ByteEdit] = []
    for number, (rows, layout, *slots) in enumerate(_records(archive)):
        shown = slots[:rows]
        if not any(item in by_item for item in shown):
            continue
        new: list[int] = []
        involved: list[str] = []
        for item in shown:
            new.append(item)
            if item in by_item:
                new += by_item[item].added
                involved.append(by_item[item].line_id)
        why = None
        if len(new) > MAX_ROWS:
            why = f"would draw {len(new)} rows and a record holds {MAX_ROWS}"
        elif layout not in LAYOUTS_AT_PEN_34:
            why = f"uses layout {layout}, whose rows start at x 74, a box of its own"
        if why:
            raise CardSplitRefused(
                f"{', '.join(involved)}: g_mc_msg record {number} {why}", involved
            )
        target = ys[layout] - 8 * (len(new) - rows)
        moved = min(LAYOUTS_AT_PEN_34, key=lambda k: (abs(ys[k] - target), k))
        record = bytes([len(new), moved, *new, *[UNUSED] * (MAX_ROWS - len(new))])
        at = RECORDS + RECORD_BYTES * number
        edits.append(
            ByteEdit(
                ARCHIVE_NAME,
                archive.overlay_offset(TITLE, at),
                archive.overlay_bytes(TITLE, at, RECORD_BYTES),
                record,
                f"g_mc_msg[{number}]: {', '.join(involved)} over {len(new)} rows (PLAN TXT-07)",
            )
        )
    return edits
