"""The small buttons drawn in textures: stone "Back" plaques and paper speech balloons
(PLAN `GFX-07`; `research/texture-recipes.md` § "Buttons").

Every button is a row of `BUTTONS`, measured on the import: which texture, which kind, the
box the Japanese is in, the CLUT the screen draws it through, and the face the English is set
in. Its English is `btn@<member>.<key>` in `translation/textures/`. The family builds the
buttons it is given, a texture at a time, so each texture's edits come from one canvas.

Two recipes, after Jay's ruling (2026-09-23): a **stone** is textured, so only the Japanese's
own pixels change -- its ink and the antialias touching it -- each refilled from the nearest
clean pixel of the stone, and the English is set bold in the game's glyphs in the ink the
Japanese used. A **balloon** is flat paper, so the whole label area is blanked to paper first
and the English set on it, every inked pixel keeping a pixel of paper between it and the
outline.
"""

from __future__ import annotations

import struct
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from boku import texture_paint as paint
from boku.archive import ARCHIVE_NAME, Archive
from boku.reinsert import ByteEdit
from boku.textures import Inventory
from boku.tim import luminance
from boku.typeset import Face, pixel_face

from boku.texture_text import (  # isort: skip
    Entry, TextureTextError, centred, fits, found, ink_of, lines_of,
)  # fmt: skip

FAMILY = "btn@"

INK_DARK = 75
"""Luminance under which a stone's pixel is the Japanese's ink: the bottom of the stone's
ramp (entries 12-15 of the stones measured), darker than any of its texture."""
SOFT = 160
"""Luminance under which a pixel touching the ink is the ink's antialias."""
DONOR_MARGIN = 4
"""How far round the Japanese's box a refill may take its colour from."""
PAPER = 200
"""Luminance over which a balloon's pixel may be its paper (the most used such is)."""


@dataclass(frozen=True)
class Button:
    texture: str
    kind: str
    """`stone` or `balloon`."""
    box: paint.Box
    """A stone: the rows and columns the Japanese is inked in (`STONE_TEXT`). A balloon: the
    whole sprite, outline and tail included."""
    clut: int
    """The CLUT the screen draws it through (measured on Beetle)."""
    drawn_4bpp: bool = False
    """The TIM is declared 8bpp and the game draws this sprite from it at 4bpp."""
    chunk: int = 0
    """Drawn at 4bpp: which 16 entries of `clut` (from `16 * chunk`)."""
    face: str = "game"
    """`game` (the dialogue glyphs) or a tracked pixel face (`bean`)."""
    widen: Widen | None = None


@dataclass(frozen=True)
class Widen:
    """A balloon made wider for the game's glyphs: its centre column repeated `extra` times, the
    right half moved right into texels that must be transparent, and `w_words` of its atlas
    entry grown to match (the entry format: `research/texture-recipes.md` § "Buttons")."""

    extra: int
    """Texels added; a multiple of the texels per VRAM word (4 at 4bpp)."""
    entry_at: int
    """The atlas entry's offset in `BOKU.BIN` from the texture's first copy there."""
    entry: tuple[int, int, int, int, int, int]
    """The entry as measured, checked before it is changed."""


STONE_TEXT = (6, 2, 33, 13)
"""Where the Japanese is on a stone, from the stone's top-left opaque corner (every stone is
the same drawing; `research/texture-recipes.md` § "Buttons")."""
EDGE = 2
"""A dark pixel this close to a transparent one is the stone's outline, not the Japanese."""


def stone_at(texture: str, x: int, y: int, clut: int, chunk: int | None = None) -> Button:
    """A stone whose top-left corner is (x, y); `chunk` given, drawn at 4bpp from that slice."""
    dx, dy, w, h = STONE_TEXT
    return Button(texture, "stone", (x + dx, y + dy, w, h), clut, chunk is not None, chunk or 0)


BUTTONS: dict[str, Button] = {
    # The stone "Back" plaques, at the corner each was found at, through the CLUT (and 4bpp
    # slice) the screen draws it in.
    "T_CONFIG.back": stone_at("_DATA_T_CONFIG.BIN__000014", 73, 41, 4),  # settings
    "M_S01001.back": stone_at("_DATA_M_S01001.BIN__000014", 233, 105, 2),  # load / save
    "T_MEMORY.back": stone_at("_DATA_T_MEMORY.BIN__000014", 49, 155, 1),  # the album
    "NIKKI_W.back": stone_at("_DATA_NIKKI_W.BIN__005450", 0, 104, 1, chunk=0),  # diary
    "M_S01100.back": stone_at("_DATA_M_S01100.BIN__000014", 656, 212, 1, chunk=0),  # sumo desk
    "TK_WAL.back": stone_at("_DATA_TK_WAL.BIN__00009c", 45, 201, 0, chunk=1),  # kite record
    "TZICON.back": stone_at("_DATA_TZICON.BIN__00006c", 0, 72, 0),  # kite book
    "PK_WAL.back": stone_at("_DATA_PK_WAL.BIN__0000e4", 73, 81, 4),  # the bag
    "MZ00.back": stone_at("_DATA_MZ00.BIN__000350", 321, 1, 0),  # specimen grid
    "SAMP.back": stone_at("_DATA_SAMP.BIN__014e48", 318, 24, 5),  # specimen box
    # The diary's idle hint おやすみ, drawn at screen (40, 16) after a second without input
    # (atlas entry 6 of the table in front of the sheet; ZUKAN.OVL places it).
    "NIKKI_W.good_night": Button(
        "_DATA_NIKKI_W.BIN__005450",
        "balloon",
        (4, 64, 44, 40),
        1,
        drawn_4bpp=True,
        chunk=1,
        widen=Widen(4, -0xC, (0, 64, 12, 40, 0, 0x41)),
    ),
}


def _face(button: Button, game: Face) -> Face:
    return game if button.face == "game" else pixel_face(button.face)


def lines_block(face: Face, lines: Sequence[str], entry: Entry) -> paint.Ink:
    """`lines` set a `face.pitch` apart, each centred on the widest, normalised."""
    inks = [ink_of(face, entry, line) for line in lines]
    widths = [face.measure(line) for line in lines]
    widest = max(widths)
    out: paint.Ink = set()
    for k, (ink, w) in enumerate(zip(inks, widths, strict=True)):
        out |= {(x + (widest - w) // 2, y + k * face.pitch) for x, y in ink}
    return paint.normalised(out)


def _colour(canvas: paint.Canvas, button: Button, point):
    """What `point` of the image the recipe detects in shows through the button's CLUT."""
    return canvas.colour(button.clut, point, stock=True, chunk=button.chunk)


def stone(canvas: paint.Canvas, button: Button, entry: Entry, face: Face, what: str) -> None:
    """Refill the Japanese's ink and its antialias from the stone round it, and set the English
    bold, centred on where the Japanese was, in the ink it used."""
    x0, y0, w, h = button.box
    near = (x0 - DONOR_MARGIN, y0, w + 2 * DONOR_MARGIN, h)
    stone_face = inside_stone(canvas, button, near)
    lum = {p: luminance(_colour(canvas, button, p)) for p in stone_face}
    box = set(paint.points(button.box))
    ink = found({p for p in box & stone_face if lum[p] < INK_DARK}, what)
    soft = {p for p in paint.grown(ink, 1, 1, 1, 1) & box & stone_face - ink if lum[p] < SOFT}
    mask = ink | soft
    donors = {p for p in stone_face - mask if lum[p] >= INK_DARK}
    text = paint.normalised(paint.bold(ink_of(face, entry)))
    fits(entry, text, button.box, what)
    ink_index = canvas.most_used(ink, stock=True)
    left = canvas.fill_from_nearest(mask, donors)
    if left:
        raise TextureTextError(f"{what}: {len(left)} pixel(s) of Japanese had nothing near "
                               f"to be refilled from, first {left[:3]}")  # fmt: skip
    canvas.stamp(centred(text, paint.extent(ink)), text, ink_index)


def inside_stone(canvas: paint.Canvas, button: Button, region: paint.Box) -> paint.Ink:
    """The pixels of `region` more than `EDGE` pixels from anything transparent or off the
    texture: the stone's face and lip, without its outline."""

    def opaque(x: int, y: int) -> bool:
        inside = 0 <= x < canvas.width and 0 <= y < canvas.height
        return inside and bool(_colour(canvas, button, (x, y))[3])

    return {
        (x, y) for x, y in paint.points(region)
        if all(opaque(x + dx, y + dy) for dx in range(-EDGE, EDGE + 1)
               for dy in range(-EDGE, EDGE + 1))
    }  # fmt: skip


def islands(marks: paint.Ink, interior: paint.Ink) -> paint.Ink:
    """The 8-connected groups of `marks` that `interior` surrounds on every side: the type in
    a balloon, not the tail's or the outline's shading that reaches in from the edge."""
    out: paint.Ink = set()
    todo = set(marks)
    while todo:
        group, stack = set(), [todo.pop()]
        while stack:
            p = stack.pop()
            group.add(p)
            for q in paint.grown({p}, 1, 1, 1, 1) & todo:
                todo.discard(q)
                stack.append(q)
        if paint.grown(group, 1, 1, 1, 1) <= interior:
            out |= group
    return out


def widened(canvas: paint.Canvas, button: Button, what: str) -> paint.Box:
    """Repeat the balloon's centre column `widen.extra` times, moving its right half right, in
    both the stock view the recipe detects in and the pixels it writes; the new box."""
    x0, y0, w, h = button.box
    extra = button.widen.extra
    spare = (x0 + w, y0, extra, h)
    if not all(x < canvas.width for x, _ in paint.points(spare)) or any(
        _colour(canvas, button, p)[3] for p in paint.points(spare)
    ):
        raise TextureTextError(
            f"{what}: the {extra} texels right of the balloon are not free for it to widen into"
        )
    split = w // 2
    stock = bytearray(canvas.stock)
    for source in (stock, canvas.pixels):
        for y in range(y0, y0 + h):
            row = source[y * canvas.width + x0 : y * canvas.width + x0 + w]
            source[y * canvas.width + x0 : y * canvas.width + x0 + w + extra] = (
                row[:split] + bytes([row[split]]) * extra + row[split:]
            )
    canvas.stock = bytes(stock)
    return x0, y0, w + extra, h


def entry_edit(archive: Archive, inv: Inventory, button: Button, what: str) -> ByteEdit:
    """The atlas entry's width grown by `widen.extra`, its measured bytes checked."""
    widen = button.widen
    x_words, y, w_words, h, mode, clut = widen.entry
    per_word = 2 if mode & 0x80 else 4
    if widen.extra % per_word:
        raise TextureTextError(f"{what}: {widen.extra} texels is not whole VRAM words")
    first = next(o for o in inv.get(button.texture).occurrences if o.file == ARCHIVE_NAME)
    at = first.file_offset + widen.entry_at
    old = struct.pack("<6H", *widen.entry)
    if archive.boku[at : at + len(old)] != old:
        raise TextureTextError(f"{what}: the atlas entry at BOKU.BIN {at:#x} is not the one "
                               f"measured")  # fmt: skip
    new = struct.pack("<6H", x_words, y, w_words + widen.extra // per_word, h, mode, clut)
    return ByteEdit(ARCHIVE_NAME, at, old, new, f"GFX-07: {what} widened for English")


NUDGES = sorted(((dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)),
                key=lambda d: (d[0] ** 2 + d[1] ** 2, d))  # fmt: skip
"""Where a balloon's English may sit off the Japanese's centre, nearest first: an oval is
narrower at the top than the bottom, so two lines centred can graze it where a step down
clears it."""


def balloon(canvas: paint.Canvas, button: Button, entry: Entry, face: Face, what: str) -> None:
    """Blank the balloon's label to paper and set the English inside its outline, a pixel of
    paper all round every inked pixel; widened first if `button.widen` says so."""
    box = widened(canvas, button, what) if button.widen else button.box
    x0, y0, w, h = box
    pale = [p for p in paint.points(box) if luminance(_colour(canvas, button, p)) > PAPER]
    if not pale:
        raise TextureTextError(f"{what}: no paper in the box the recipe measured")
    paper = canvas.most_used(pale, stock=True)
    interior: paint.Ink = set()
    for y in range(y0, y0 + h):
        xs = [x for x in range(x0, x0 + w) if canvas.at((x, y), stock=True) == paper]
        if xs:
            interior |= {(x, y) for x in range(min(xs), max(xs) + 1)}
    marks = {p for p in interior if canvas.at(p, stock=True) != paper}
    japanese = found(islands(marks, interior), what)
    darkest = [p for p in japanese if paint.dark(_colour(canvas, button, p))]
    ink_index = canvas.most_used(darkest or japanese, stock=True)
    jx, jy, jw, jh = paint.extent(japanese)
    for x, y in set(paint.points((jx - 1, jy - 1, jw + 2, jh + 2))) & interior:
        canvas.pixels[y * canvas.width + x] = paper
    block = lines_block(face, lines_of(entry), entry)
    cx, cy = centred(block, (jx, jy, jw, jh))
    halo = paint.grown(block, 1, 1, 1, 1)
    for dx, dy in NUDGES:
        at = {(x + cx + dx, y + cy + dy) for x, y in halo}
        if at <= interior and all(canvas.at(p) == paper for p in at):
            canvas.stamp((cx + dx, cy + dy), block, ink_index)
            return
    _, _, bw, bh = paint.extent(block)
    raise TextureTextError(
        f"{entry.where}: {entry.text!r} is {bw}x{bh} px in the {face.name} face and "
        f"{what} cannot hold it with a pixel of paper inside its outline; nothing is cut "
        f"to fit (README)"
    )


RECIPES = {"stone": stone, "balloon": balloon}


def buttons(
    archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]
) -> list[ByteEdit]:
    """Every button `entries` name, a texture at a time, plus any atlas entry a widened
    balloon needs."""
    by_texture: dict[tuple[str, bool], list[tuple[Entry, Button]]] = defaultdict(list)
    for entry in entries:
        key = entry.id.removeprefix(FAMILY)
        if key not in BUTTONS:
            raise TextureTextError(
                f"{entry.where}: there is no button {key!r} (boku.texture_buttons.BUTTONS)"
            )
        button = BUTTONS[key]
        by_texture[button.texture, button.drawn_4bpp].append((entry, button))
    edits: list[ByteEdit] = []
    for (texture_id, drawn_4bpp), group in by_texture.items():
        canvas = paint.Canvas(inv.get(texture_id), drawn_4bpp=drawn_4bpp)
        for entry, button in sorted(group, key=lambda eb: eb[0].id):
            what = f"the {entry.id.removeprefix(FAMILY)} button"
            RECIPES[button.kind](canvas, button, entry, _face(button, face), what)
            if button.widen:
                edits.append(entry_edit(archive, inv, button, what))
        edits += canvas.patches()
    return edits
