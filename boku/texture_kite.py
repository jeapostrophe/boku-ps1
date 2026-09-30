"""Kite flying's HUD: the three labels over its compass and its numbers (PLAN `GFX-13`). How
the game draws them and every measurement below: `research/texture-recipes.md` § "The
kite-flying HUD".

The English is `kite@hud.<key>` in `translation/textures/kite.txt`, all three or none. The
labels are 4bpp sprites of a sheet both of kite flying's packs carry, each drawn from a
record of `TAKO.OVL`: the strip the Japanese was in is cleared, each label is set in the
game's glyphs in a cell wide enough for it, and its record is given the cell and a place that
keeps it centred where the Japanese was.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from boku import texture_paint as paint
from boku.archive import Archive
from boku.reinsert import ByteEdit
from boku.textures import Inventory
from boku.tim import luminance
from boku.typeset import Face

from boku.texture_text import (  # isort: skip
    Entry, TextureTextError, centred_across, found, ink_of, keyed, outlined, overlay_edit,
)  # fmt: skip

FAMILY = "kite@"
OVERLAY = "TAKO.OVL"
REASON = "GFX-13: kite flying's HUD labels in English"

ATLASES = ("_DATA_TBG00.BIN__00001c", "_DATA_TBG01.BIN__00001c")
"""One per pack, the day's and the afternoon's: a picture in the left of each (they differ)
and the same HUD sheet in the right, drawn at 4bpp."""
PAGE_X = 256
"""The canvas x of the HUD's texture page: a sprite's `u` is its canvas x less this."""
CLUT, CHUNK = 0, 0
LABEL_Y = 190
"""The screen row every label's sprite starts on."""
GLYPH_TOP = 4
"""The row of a cell the glyphs' 12-row cell starts on: capitals stand on the row the
Japanese stood on, and the game's lowest descender's edge is the cell's last row."""
WHITE = 200
"""Luminance over which a texel of the strip is the lettering's white."""
RECORD = "<HhhBBHH"
"""A HUD sprite's record, 22 bytes: a `u16` (1 in the labels'), `s16 x, y`, `u8 u, v`,
`u16 w, h` (then the texture page and the CLUT, which stay)."""


@dataclass(frozen=True)
class Label:
    record: int
    """Its record's RAM address in `TAKO.OVL`."""
    retail: paint.Box
    """The Japanese's sprite on the sheet."""
    retail_x: int
    cell: paint.Box
    """Ours: part of the strip, or texels no sprite used."""

    @property
    def x(self) -> int:
        """Where ours is drawn: centred where retail's was."""
        return self.retail_x + (self.retail[2] - self.cell[2]) // 2


LABELS: dict[str, Label] = {
    "direction": Label(0x80079A8C, (256, 136, 32, 16), 143, (256, 136, 32, 16)),
    "speed": Label(0x80079AA2, (288, 136, 32, 16), 188, (288, 136, 40, 16)),
    "altitude": Label(0x80079AB8, (320, 136, 32, 16), 265, (400, 136, 48, 16)),
}
"""By what the Japanese label says (風向, 風速, 高度), left to right on the screen. A cell is as
wide as the screen has room for about the label's centre, not as wide as today's English."""
STRIP = paint.extent({p for label in LABELS.values() for p in paint.points(label.retail)})
"""Where the Japanese labels are, side by side."""


def label_ink(face: Face, entry: Entry, cell: paint.Box) -> paint.Ink:
    """A label's lettering relative to its cell's corner: centred across the cell, a texel
    left all round it for its edge."""
    return centred_across(entry, ink_of(face, entry), cell[2:], GLYPH_TOP, "its cell on the HUD")


def sheet(canvas: paint.Canvas, face: Face, text: dict[str, Entry], what: str) -> None:
    """Clear the strip and set each label in its cell, in the strip's own white and edge."""
    palette = canvas.palette(CLUT, CHUNK)
    strip = paint.points(STRIP)
    ground = canvas.most_used(strip)
    if palette[ground][3]:
        raise TextureTextError(f"{what}: the labels' ground is not transparent")
    lettering = found({p for p in strip if palette[canvas.at(p)][3]}, what)
    lum = {p: luminance(palette[canvas.at(p)]) for p in lettering}
    fill = canvas.most_used(found({p for p in lettering if lum[p] > WHITE}, what))
    edge = canvas.at(min(lettering, key=lambda p: lum[p]))
    inside = set(strip)
    for key, label in LABELS.items():
        if lettering.isdisjoint(paint.points(label.retail)):
            raise TextureTextError(f"{what}: no lettering in the {key} label's sprite")
        if len({canvas.at(p) for p in paint.points(label.cell) if p not in inside}) > 1:
            raise TextureTextError(f"{what}: the texels at {label.cell} are not free")
    canvas.fill(STRIP, ground)
    for key, label in LABELS.items():
        canvas.fill(label.cell, ground)
        ink = label_ink(face, text[key], label.cell)
        outlined(canvas.pixels, canvas.width, label.cell, ink, fill, edge)


def records(archive: Archive) -> list[ByteEdit]:
    """Each label's record given its cell and its place."""
    edits = []
    for label in LABELS.values():
        (rx, ry, rw, rh), (cx, cy, cw, ch) = label.retail, label.cell
        old = (1, label.retail_x, LABEL_Y, rx - PAGE_X, ry, rw, rh)
        new = (1, label.x, LABEL_Y, cx - PAGE_X, cy, cw, ch)
        edits.append(overlay_edit(archive, OVERLAY, label.record, RECORD, old, new, REASON))
    return edits


def kite(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    text = keyed(f"{FAMILY}hud", entries, list(LABELS))
    edits: list[ByteEdit] = []
    for atlas in ATLASES:
        canvas = paint.Canvas(inv.get(atlas), drawn_4bpp=True)
        sheet(canvas, face, text, f"the kite HUD's labels in {atlas}")
        edits += canvas.patches()
    return [*edits, *records(archive)]


VIEWS: dict[str, tuple[paint.View, ...]] = {
    f"{FAMILY}hud": tuple(
        paint.View(ATLASES[0], True, CLUT, CHUNK, label.retail, label.cell)
        for label in LABELS.values()
    ),
}
"""The reader's pictures of the labels, in `LABELS`' order."""
