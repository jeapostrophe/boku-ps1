"""`PLAN TXT-05`, `PIPE-07`: the insect box's entries on its two screens.

`hhon@5328` holds one entry per insect (and 60, the empty slot). `HHON.OVL` draws it on the
grid screen (`hhon_entry_draw`, reached from the pair at `GRID_PAIR`) and on the notebook
page of the hub (`hhon_text_scroll_v`, from `NOTEBOOK_PAIR`), both through `text_nth`
from the array's start. English is drawn in rows (`asm/hhon_resident.asm`). Jay's layout
(2026-09-24): the grid shows the whole entry, 14 rows at 11 px; the notebook shows what its
8 rows hold and ends with "..." when the entry goes on -- the full text is one button away
on the grid. So the build writes the array twice into `HHON.OVL`'s tail: the grid's copy,
whole, and the notebook's, each entry cut to `NOTEBOOK_ROWS` (`notebook_words`), and points
each screen's pair at its own (`boku.array_relocate`).
"""

from __future__ import annotations

from boku.boxes import box_for
from boku.glyphs import NEWLINE_WORD
from boku.layout import BoxSpec, Encoder, LaidOut, measure, sheet_cells

ENTRIES = "hhon@5328"
GRID_PAIR = 0x8007B478
"""The `lui` hhon_entry_draw's caller forms the array's start with (`boku.arrays.ANCHORS`)."""
NOTEBOOK_PAIR = 0x8007B594
"""The `lui` hhon_text_scroll_v's caller forms it with."""
NOTEBOOK = "@notebook"
"""Suffix of the words the notebook's copy holds for an entry, and of its unit's prefix."""
NOTEBOOK_ROWS = 8
"""The notebook page's rows at 12 px, from the retail column top to the count below."""
ELLIPSIS = "..."


def is_entry(line_id: str) -> bool:
    return line_id.split(".", 1)[0] == ENTRIES


def is_copy(key: str) -> bool:
    """Is `key` a notebook copy's (`<entry id>@notebook`), not a line's?"""
    return key.endswith(NOTEBOOK)


def notebook_words(laid: LaidOut, encoder: Encoder, box: BoxSpec) -> tuple[int, ...] | None:
    """The notebook's words for an entry laid out in `box` (`laid.pages[0]` its rows), or
    `None` when it fits the page as it is. Past `NOTEBOOK_ROWS` the eighth row loses words
    from its end until "..." fits after them -- all of them, if even one word will not."""
    rows = laid.pages[0] if laid.pages else ()
    if len(rows) <= NOTEBOOK_ROWS:
        return None
    last = rows[NOTEBOOK_ROWS - 1].split(" ")
    while last and measure(encoder, " ".join(last) + ELLIPSIS) > box.width:
        last.pop()
    breaks = [at for at, word in enumerate(laid.words) if word == NEWLINE_WORD]
    head = laid.words[: breaks[NOTEBOOK_ROWS - 2] + 1]  # rows 1-7 and the break after them
    tail = sheet_cells(encoder, " ".join(last) + ELLIPSIS, box.pitch).cells
    return (*head, *tail, laid.words[-1])  # the item's own terminator


def notebook_copy(line_id: str, laid: LaidOut, encoder: Encoder) -> dict[str, tuple[int, ...]]:
    """`{<line id>@notebook: words}` for an entry longer than the page, else nothing; the
    build and the lint both add it to the words the arrays are placed with."""
    box = box_for(line_id) if is_entry(line_id) else None
    cut = notebook_words(laid, encoder, box.spec) if box else None
    return {line_id + NOTEBOOK: cut} if cut is not None else {}
