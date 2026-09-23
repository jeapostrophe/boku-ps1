"""What each non-dialogue text box can hold, in pixels (`PLAN TXT-07`).

`research/data/text-boxes.tsv` is the one home of the numbers: per line id (or `<array>.*`
for every item of an array), the x the surface's walker starts the item at and the column
`right` where its frame begins, so an item may advance `right - x` pixels. The rows were
measured on screenshots of the stock game, or derived from the code's own literals where a
row says so (`basis`), and `tests/test_real_boxes.py` checks every derived x against the
bytes of the contributor's disc. Where each surface stands is
`research/vwf-prototype.md` § "The fixed-pitch surfaces".

A line id with no row belongs to a surface nobody has measured yet; `box_for` answers
`None` and the build holds it to its bytes alone, which is the only limit known there.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from boku import REPO_ROOT
from boku.layout import BoxSpec

BOXES_TSV = REPO_ROOT / "research" / "data" / "text-boxes.tsv"
COLUMNS = ("line_id", "x", "right", "pitch", "surface", "basis")
EVERY_ITEM = ".*"


class BoxError(Exception):
    pass


@dataclass(frozen=True)
class TextBox:
    line_id: str
    x: int
    right: int
    pitch: int
    """The walker's stock step per cell (12; 10 on `help_line_draw`)."""
    surface: str
    basis: str

    @property
    def spec(self) -> BoxSpec:
        """One line, `right - x` pixels wide."""
        return BoxSpec(
            width=self.right - self.x,
            lines=1,
            name=f"surface {self.surface}'s box",
            pitch=self.pitch,
        )


@cache
def load_boxes(path: Path = BOXES_TSV) -> dict[str, TextBox]:
    """Every row, keyed by its line id; refuses a malformed table rather than skip a row."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise BoxError(f"{path.name}: the columns are {reader.fieldnames}, not {COLUMNS}")
        boxes: dict[str, TextBox] = {}
        for number, row in enumerate(reader, start=2):
            try:
                box = TextBox(
                    row["line_id"],
                    int(row["x"]),
                    int(row["right"]),
                    int(row["pitch"]),
                    row["surface"],
                    row["basis"],
                )
            except (TypeError, ValueError) as error:
                raise BoxError(f"{path.name} row {number}: {error}") from None
            if box.right <= box.x:
                raise BoxError(f"{path.name} row {number}: right {box.right} is not past x")
            if box.line_id in boxes:
                raise BoxError(f"{path.name} row {number}: {box.line_id} is listed twice")
            boxes[box.line_id] = box
    return boxes


def box_for(line_id: str, boxes: dict[str, TextBox] | None = None) -> TextBox | None:
    """The row for `line_id`: its own, else its array's `.*` row, else `None`."""
    boxes = load_boxes() if boxes is None else boxes
    if line_id in boxes:
        return boxes[line_id]
    array = line_id.rpartition(".")[0]
    return boxes.get(array + EVERY_ITEM) if array else None
