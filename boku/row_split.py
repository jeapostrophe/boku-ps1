"""An **L**-array item on more than one row (`boku.arrays.ROW_SPLITS`).

In an **L** array every item ends with `0x8001` and its reader finds item n by counting
them, so an item is one row. When a box gives an item more rows
(`research/data/text-boxes.tsv`), the build lays it out as rows back to back, each ended by
`0x8001`, and splits it here: the item keeps its first row, and each further row becomes a
new item appended after the array's last. What draws the new items is each array's own:
the card messages' records (`boku.card_messages`), the help screen's extra row
(`boku.help_screen`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from boku.arrays import array_of
from boku.glyphs import NEWLINE_WORD


class RowSplitRefused(Exception):
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
    """The item numbers the further rows get, after the array's last."""


def splits(words: Mapping[str, Sequence[int]], prefix: str) -> list[Split]:
    """Every item of the **L** array `prefix` in `words` laid out on more than one row, in
    item order; the first new item is numbered after the array's last."""
    array = array_of(prefix)
    if array is None:
        raise RowSplitRefused(f"the catalogue has no {prefix}", ())
    found: list[Split] = []
    following = array.spec
    for item in range(array.spec):
        line_id = f"{prefix}.{item}"
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
