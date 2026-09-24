"""Labels printed beside numbers the game draws at run time: the fishing record (`FS_WAL`) and
the bug-trading notebook's record card (`M_S01100`) (PLAN `GFX-07`;
`research/texture-recipes.md` § "Records", which has the method and the measurements).

The English is `rec@<member>.<key>` in `translation/textures/records.txt`; a record takes all
its keys or none. A record drawn in several places on its texture is rebuilt at each.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from boku import texture_paint as paint
from boku.archive import Archive
from boku.reinsert import ByteEdit
from boku.texture_books import INK, MARK
from boku.textures import Inventory
from boku.tim import luminance
from boku.typeset import Face, face_named

from boku.texture_text import (  # isort: skip
    Entry, TextureTextError, fits, found, ink_of, keyed,
)  # fmt: skip

FAMILY = "rec@"


@dataclass(frozen=True)
class Label:
    key: str | None
    """The English's key; None for a Japanese mark the English needs no word for (the 日 after
    a day number: an English date is "Aug. 16")."""
    clear: paint.Box
    """The rectangle the Japanese, its shadow and its antialias are in."""
    room: paint.Box | None = None
    """Where the English may go (`clear` if None)."""
    align: str = "left"
    """`left` or `right` in `room`: a label before a number ends at its room's right edge, one
    after a number starts at its left edge."""
    face: str = "bean"

    def clear_at(self, dx: int, dy: int) -> paint.Box:
        return _moved(self.clear, dx, dy)

    def room_at(self, dx: int, dy: int) -> paint.Box:
        return _moved(self.room or self.clear, dx, dy)


@dataclass(frozen=True)
class Record:
    texture: str
    clut: int
    labels: tuple[Label, ...]
    copies: tuple[tuple[int, int, int], ...] = ((0, 0, 0),)
    """Where the same labels are drawn again: (dx, dy, the 16-entry CLUT slice, which only a
    `drawn_4bpp` record uses)."""
    shadow: bool = False
    """The type has a drop shadow one pixel down and right, and so does the English."""
    drawn_4bpp: bool = False


FS_WAL_LIST = ("bait", "bait_float", "tenkara_small", "tenkara_large")
"""The tackle list's rows, 16 px apart: four on one sprite, the first three on the other."""

RECORDS: dict[str, Record] = {
    # The fishing record: the plate of field labels and the two tackle lists.
    "FS_WAL": Record(
        "_DATA_FS_WAL.BIN__0000d8",
        2,
        (
            Label("fish", (168, 65, 16, 13), (170, 65, 14, 13), face="sprout"),
            Label("size", (73, 80, 37, 17)),
            Label("average", (119, 80, 27, 17), (110, 80, 36, 17), "right"),
            Label("largest", (119, 96, 27, 16), (110, 96, 36, 16), "right"),
            *(Label(key, (48, 155 + 16 * n, 88, 15)) for n, key in enumerate(FS_WAL_LIST)),
            *(Label(key, (136, 113 + 16 * n, 88, 15)) for n, key in enumerate(FS_WAL_LIST[:3])),
        ),
    ),
    # The bug-trading notebook's record card: the offered bug's, the held bug's under it, and
    # the single card.
    "M_S01100": Record(
        "_DATA_M_S01100.BIN__0164b4",
        2,
        (
            Label("caught", (355, 29, 51, 15), (352, 29, 56, 15)),
            Label(None, (422, 29, 12, 15)),
            Label("won", (362, 43, 15, 15), (364, 43, 13, 15)),
            Label("lost", (397, 43, 15, 15), (399, 43, 13, 15)),
            Label("value", (323, 59, 102, 15), (323, 59, 116, 15)),
            Label("value_unit", (367, 73, 48, 14), (369, 73, 70, 14)),
        ),
        copies=((0, 0, 4), (0, 106, 4), (256, 1, 5)),
        shadow=True,
        drawn_4bpp=True,
    ),
}


def clear(canvas: paint.Canvas, clut: int, chunk: int, box: paint.Box, what: str):
    """Refill `box`'s marks (darker than its paper by `MARK`) from the nearest paper; the
    entries the ink and the shadow were drawn in, and where the ink was."""
    palette = canvas.palette(clut, chunk)
    points = paint.points(box)

    def lum(p):
        return luminance(palette[canvas.at(p, stock=True)])

    pale = Counter(canvas.at(p, stock=True) for p in points if lum(p) >= INK)
    if not pale:
        raise TextureTextError(f"{what} shows no paper")
    ground = luminance(palette[pale.most_common(1)[0][0]])
    marks = {p for p in points if lum(p) < ground - MARK}
    ink = found({p for p in marks if lum(p) < INK}, what)
    shade = marks - ink
    left = canvas.fill_from_nearest(marks, set(points) - marks)
    if left:
        raise TextureTextError(f"{what}: {len(left)} pixel(s) had no paper near, {left[:3]}")
    ink_index = canvas.most_used(ink, stock=True)
    shadow_index = canvas.most_used(shade, stock=True) if shade else ink_index
    return ink_index, shadow_index, paint.extent(ink)


def rebuild(canvas: paint.Canvas, record: Record, text: dict[str, Entry], game: Face,
            dx: int, dy: int, chunk: int, name: str) -> None:  # fmt: skip
    """Clear every label of one copy, then set the English: labels share rows, and a clear
    after a stamp would refill from, or over, the English already set."""
    cleared = []
    for label in record.labels:
        box = label.clear_at(dx, dy)
        what = f"{name}'s {label.key or 'mark'} at {box}"
        cleared.append((label, what, clear(canvas, record.clut, chunk, box, what)))
    for label, what, (ink, shadow, (_, jy, _, jh)) in cleared:
        if label.key is None:
            continue
        entry = text[label.key]
        glyphs = paint.normalised(ink_of(face_named(label.face, game), entry))
        _, _, w, h = paint.extent(glyphs)
        rx, ry, rw, rh = label.room_at(dx, dy)
        fits(entry, glyphs, (rx, ry, rw - record.shadow, rh - record.shadow), what)
        x = rx if label.align == "left" else rx + rw - w - record.shadow
        y = min(max(jy + (jh - h) // 2, ry), ry + rh - h - record.shadow)
        if record.shadow:
            canvas.stamp((x + 1, y + 1), glyphs, shadow)
        canvas.stamp((x, y), glyphs, ink)


def _moved(box: paint.Box, dx: int, dy: int) -> paint.Box:
    return box[0] + dx, box[1] + dy, box[2], box[3]


def records(archive: Archive, inv: Inventory, game: Face, entries: Sequence[Entry]):
    """Every record `entries` name, each whole."""
    by_member: dict[str, list[Entry]] = {}
    for entry in entries:
        member = entry.id.removeprefix(FAMILY).rsplit(".", 1)[0]
        if member not in RECORDS:
            raise TextureTextError(f"{entry.where}: there is no record {member!r} (RECORDS)")
        by_member.setdefault(member, []).append(entry)
    edits: list[ByteEdit] = []
    for member, group in by_member.items():
        record = RECORDS[member]
        keys = sorted({label.key for label in record.labels if label.key})
        text = keyed(f"{FAMILY}{member}", group, keys)
        canvas = paint.Canvas(inv.get(record.texture), drawn_4bpp=record.drawn_4bpp)
        for dx, dy, chunk in record.copies:
            rebuild(canvas, record, text, game, dx, dy, chunk, member)
        edits += canvas.patches()
    return edits
