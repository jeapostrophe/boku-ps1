"""The small buttons drawn in textures: stone "Back" plaques and paper speech balloons
(PLAN `GFX-07`; `research/texture-recipes.md` § "Buttons").

Every button is a row of `BUTTONS`, measured on the import: which texture, which kind, the
box the Japanese is in, the CLUT the screen draws it through, and the face the English is set
in. Its English is `btn@<member>.<key>` in `translation/textures/`. The family builds the
buttons it is given, a texture at a time, so each texture's edits come from one canvas.

The recipes (`RECIPES`), after Jay's ruling (2026-09-23): a **stone** is textured, so only
the Japanese's own pixels change -- its ink and the antialias touching it -- each refilled from
the nearest clean pixel of the stone, and the English is set bold in the game's glyphs in the
ink the Japanese used; a **plank** is the same on a board, and a **plate** the same on a
dithered plate at the glyphs' own weight. A **balloon** is flat paper, so the whole label
area is blanked to paper first and the English set on it, every inked pixel keeping a pixel of
paper round it; `layout` widens and repacks balloons where their texture has room.
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
from boku.typeset import Face, face_named

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
    """`stone`, `plank`, `plate`, `balloon` or `label` (`RECIPES`)."""
    box: paint.Box
    """A stone: the rows and columns the Japanese is inked in (`STONE_TEXT`). A plank: the
    board. A plate or a balloon: the whole sprite, outline and tail included. A label: the
    part of the card its type is printed in."""
    clut: int
    """The CLUT the screen draws it through (measured on Beetle)."""
    drawn_4bpp: bool = False
    """The TIM is declared 8bpp and the game draws this sprite from it at 4bpp."""
    chunk: int = 0
    """Drawn at 4bpp: which 16 entries of `clut` (from `16 * chunk`)."""
    face: str = "game"
    """`game` (the dialogue glyphs) or a tracked pixel face (`bean`)."""
    widen: Widen | None = None
    text: paint.Box | None = None
    """A plate or balloon whose sprite carries a picture beside the Japanese (bug sumo's swap
    plate and its arrow): the part of `box`, relative to it, the Japanese is in
    (`text_area`)."""

    @property
    def placed(self) -> paint.Box:
        """Where `layout` leaves the art: widened, and set down at `widen.to` if given."""
        if not self.widen:
            return self.box
        x, y, w, h = self.box
        x, y = self.widen.to or (x, y)
        return x, y, w + self.widen.extra, h

    @property
    def split(self) -> int:
        """The column of `box` widening inserts in front of (the middle)."""
        return self.box[2] // 2


@dataclass(frozen=True)
class AtlasEntry:
    """One entry of a screen's atlas table, `{u16 x_words, y, w_words, h, mode, clut}`
    (`research/texture-recipes.md` § "Buttons"), `at` bytes from the texture's first copy in
    `BOKU.BIN`, as measured."""

    at: int
    entry: tuple[int, int, int, int, int, int]

    @property
    def per_word(self) -> int:
        """Texels per VRAM word: 2 at 8bpp (mode 0x80), 4 at 4bpp."""
        return 2 if self.entry[4] & 0x80 else 4

    def edit(self, archive: Archive, inv: Inventory, texture: str, move, extra, what) -> ByteEdit:
        x_words, y, w_words, h, mode, clut = self.entry
        per_word = self.per_word
        if move[0] % per_word or extra % per_word:
            raise TextureTextError(f"{what}: {move[0]} and {extra} texels are not whole VRAM words")
        first = next(o for o in inv.get(texture).occurrences if o.file == ARCHIVE_NAME)
        new = (x_words + move[0] // per_word, y + move[1], w_words + extra // per_word, h, mode,
               clut)  # fmt: skip
        return _checked(archive, first.file_offset + self.at, "<6H", self.entry, new, what)


@dataclass(frozen=True)
class SpriteRecord:
    """A 22-byte sprite record of an overlay, `{u16 semi, s16 x, y, u8 u, v, u16 w, h, …}`,
    at RAM `ram`, drawn `width` texels wide as measured (bug sumo, `MUSI.OVL`)."""

    overlay: str
    ram: int
    width: int

    def edit(self, archive: Archive, inv: Inventory, texture: str, move, extra, what) -> ByteEdit:
        if move != (0, 0):
            raise TextureTextError(f"{what}: a sprite record's balloon widens in place")
        at = archive.overlay_offset(self.overlay, self.ram + 8)
        return _checked(archive, at, "<H", (self.width,), (self.width + extra,), what)


def _checked(archive: Archive, at: int, fmt: str, old, new, what: str) -> ByteEdit:
    before = struct.pack(fmt, *old)
    if archive.boku[at : at + len(before)] != before:
        raise TextureTextError(f"{what}: the sprite's size at BOKU.BIN {at:#x} is not the one "
                               f"measured")  # fmt: skip
    return ByteEdit(ARCHIVE_NAME, at, before, struct.pack(fmt, *new),
                    f"GFX-07: {what} widened for English")  # fmt: skip


@dataclass(frozen=True)
class Widen:
    """A balloon made wider for the game's glyphs: its centre column repeated `extra` times,
    placed at `to` (canvas x, y; where it was if None) in texels that must be transparent or
    be other widened balloons' old places, and every stored size of its sprite grown (and
    moved) to match."""

    extra: int
    """Texels the sprite grows by. The art grows by two columns at a time (the pair at its
    centre repeated), so a dither keeps its phase."""
    sizes: tuple[AtlasEntry | SpriteRecord, ...]
    to: tuple[int, int] | None = None
    stretch: int | None = None
    """Columns inserted into the art, if not `extra`: more when the sprite ends in transparent
    columns the stretched art may take (they must be transparent on every row)."""


STONE_TEXT = (6, 2, 33, 13)
"""Where the Japanese is on a stone, from the stone's top-left opaque corner (every stone is
the same drawing; `research/texture-recipes.md` § "Buttons")."""
EDGE = 2
"""A dark pixel this close to a transparent one is the stone's outline, not the Japanese."""


def stone_at(texture: str, x: int, y: int, clut: int, chunk: int | None = None) -> Button:
    """A stone whose top-left corner is (x, y); `chunk` given, drawn at 4bpp from that slice."""
    dx, dy, w, h = STONE_TEXT
    return Button(texture, "stone", (x + dx, y + dy, w, h), clut, chunk is not None, chunk or 0)


def atlas_balloons(texture: str, clut: int, rows: dict) -> dict[str, Button]:
    """Balloons drawn at 4bpp from `texture` by an atlas table, each row `(entry offset from
    the texture, entry as measured, texels to widen, where to move it or None, face)`; the
    sprite's box is the entry's, its CLUT slice the entry's code."""
    out = {}
    for key, (at, entry, extra, to, face) in rows.items():
        size = AtlasEntry(at, entry)
        x_words, y, w_words, h, _mode, code = entry
        widen = Widen(extra, (size,), to) if extra or to else None
        box = (x_words * size.per_word, y, w_words * size.per_word, h)
        out[key] = Button(texture, "balloon", box, clut, True, code % 0x40, face, widen)
    return out


def sumo_balloons(rows: dict) -> dict[str, Button]:
    """Bug sumo's 44x40 balloons, CLUT 2 slice 0: `(corner, records, texels to widen)`."""
    out = {}
    for key, (corner, records, extra) in rows.items():
        sizes = tuple(SpriteRecord("MUSI.OVL", ram, 44) for ram in records)
        widen = Widen(extra, sizes) if extra else None
        out[key] = Button("_DATA_M_S01100.BIN__0164b4", "balloon", (*corner, 44, 40), 2, True,
                          0, widen=widen)  # fmt: skip
    return out


def fixed_balloons(texture: str, clut: int, chunk: int, rows: dict) -> dict[str, Button]:
    """44x40 balloons drawn at 4bpp that stay their size: `(corner, face)`."""
    return {key: Button(texture, "balloon", (*corner, 44, 40), clut, True, chunk, face)
            for key, (corner, face) in rows.items()}  # fmt: skip


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
    "MZKAN.back": stone_at("_DATA_MZKAN.BIN__000048", 0, 0, 1),  # the insect book
    "FS_WAL.back": stone_at("_DATA_FS_WAL.BIN__0000d8", 45, 201, 0, chunk=3),  # fishing record
    # The diary's idle hint おやすみ, drawn at screen (40, 16) after a second without input
    # (atlas entry 6 of the table in front of the sheet; ZUKAN.OVL places it).
    "NIKKI_W.good_night": Button(
        "_DATA_NIKKI_W.BIN__005450",
        "balloon",
        (4, 64, 44, 40),
        1,
        drawn_4bpp=True,
        chunk=1,
        widen=Widen(4, (AtlasEntry(-0xC, (0, 64, 12, 40, 0, 0x41)),)),
    ),
    # The desk (`SUB`; its atlas table runs up to the texture). One balloon shows at a time,
    # for the cursor's item. The page-14 band (rows 211-250) is repacked so the tackle and the
    # glove can widen: the tackle widens in place, the cage, glove and net move right.
    **atlas_balloons(
        "_DATA_SUB.BIN__002050",
        1,
        {
            "SUB.kite": (-168, (167, 194, 11, 40, 0, 0x43), 0, None, "game"),
            "SUB.tackle": (-156, (78, 211, 11, 40, 0, 0x43), 12, (312, 211), "game"),
            "SUB.cage": (-144, (89, 211, 11, 40, 0, 0x43), 0, (368, 211), "game"),
            "SUB.empty_handed": (-132, (100, 211, 11, 40, 0, 0x43), 4, (412, 211), "game"),
            "SUB.net": (-120, (111, 211, 11, 40, 0, 0x43), 0, (460, 211), "game"),
            "SUB.back": (-108, (175, 64, 11, 40, 0, 0x43), 0, None, "game"),
        },
    ),
    # Belongings in Bean: the page-15 band holds it and the kite in 96 texels.
    "SUB.belongings": Button(
        "_DATA_SUB.BIN__002050",
        "balloon",
        (712, 194, 48, 40),
        1,
        drawn_4bpp=True,
        chunk=2,
        face="bean",
        widen=Widen(4, (AtlasEntry(-180, (178, 194, 12, 40, 0, 0x42)),), stretch=8),
    ),
    # The bag (`PK_WAL`): its Belongings moves into the empty rows 154-239 of page 14, where
    # it has room for the game's glyphs, and so do the two page balloons (drawn only by an
    # idle hint no code calls -- built so no Japanese is left if one does).
    **atlas_balloons(
        "_DATA_PK_WAL.BIN__0000e4",
        1,
        {
            "PK_WAL.belongings": (-180, (0, 200, 12, 40, 0, 0x40), 28, (264, 160), "game"),
            "PK_WAL.prev_page": (-156, (36, 40, 11, 40, 0, 0x42), 4, (344, 160), "game"),
            "PK_WAL.next_page": (-144, (12, 192, 11, 40, 0, 0x42), 4, (396, 160), "game"),
        },
    ),
    **atlas_balloons(
        "_DATA_TK_WAL.BIN__00009c",
        0,
        {  # the kite record
            "TK_WAL.kite": (-132, (0, 200, 11, 40, 0, 0x00), 0, None, "game"),
        },
    ),
    # The fishing record's つり道具, over the tackle box's picture; the sheet has no free texels
    # measured beside it, so Bean.
    "FS_WAL.tackle": Button(
        "_DATA_FS_WAL.BIN__0000d8",
        "balloon",
        (0, 200, 44, 40),
        0,
        drawn_4bpp=True,
        chunk=0,
        face="bean",
    ),
    # The kite book's 作るたこ決定 (a true 4bpp TIM, 12 VRAM words: no room to widen).
    "TZICON.make_this_kite": Button(
        "_DATA_TZICON.BIN__00006c", "balloon", (0, 0, 48, 40), 2, face="bean"
    ),
    # Bug sumo (`M_S01100`, drawn by `MUSI.OVL`'s 22-byte records; each balloon has a record
    # in both of its tables; the free texels are research's).
    **sumo_balloons(
        {
            "M_S01100.release": ((440, 0), (0x8007A538, 0x8007A5D2), 12),
            "M_S01100.swap": ((440, 40), (0x8007A54E, 0x8007A5E8), 0),
            "M_S01100.cage": ((440, 80), (0x8007A564, 0x8007A5FE), 0),
            "M_S01100.rank": ((440, 120), (0x8007A590, 0x8007A62A), 8),
            "M_S01100.me": ((440, 160), (0x8007A5A6,), 0),
            "M_S01100.gong": ((440, 200), (0x8007A5BC, 0x8007A656), 0),
            "M_S01100.place": ((328, 204), (0x8007A640,), 0),
        }
    ),
    "M_S01100.trade_plate": Button(
        "_DATA_M_S01100.BIN__0164b4",
        "plate",
        (256, 220, 40, 20),
        2,
        drawn_4bpp=True,
        chunk=3,
        text=(12, 2, 26, 16),
        widen=Widen(8, (SpriteRecord("MUSI.OVL", 0x8007A7B4, 40),)),
    ),
    "M_S01100.close": Button("_DATA_M_S01100.BIN__0164b4", "plank", (129, 205, 34, 14), 5),
    # The insect box (`HHON.OVL`; sprite tables in `SAMP.BIN`). No free texels to widen
    # into: what does not fit the game's glyphs is set in Bean. `MZ02` is the same texture
    # as `SAMP.BIN`'s copy of it.
    **fixed_balloons(
        "_DATA_MZ02.BIN__000000",
        4,
        0,
        {
            "MZ02.cage": ((684, 0), "game"),
            "MZ02.release": ((684, 40), "bean"),
            "MZ02.magnifier": ((684, 80), "bean"),
            "MZ02.medicine": ((684, 120), "bean"),
            "MZ02.syringe": ((640, 80), "bean"),
            "MZ02.collecting_box": ((640, 40), "game"),
            "MZ02.remove_specimen": ((640, 120), "sprout"),
            "MZ02.prev_page": ((640, 0), "bean"),
            "MZ02.next_page": ((640, 160), "bean"),
        },
    ),
    "SAMP.species_list": Button(
        "_DATA_SAMP.BIN__014e48", "balloon", (640, 88, 44, 40), 6, drawn_4bpp=True, face="bean"
    ),
    "SAMP.medicine": Button(
        "_DATA_SAMP.BIN__014e48",
        "balloon",
        (640, 48, 48, 40),
        6,
        drawn_4bpp=True,
        chunk=1,
        face="bean",
    ),
    # The radio-exercise attendance card (`PK_ITM`, item 0x6c; seen in the bag): its title
    # beside the radio picture and its footer under the grid, set in Sprout.
    "PK_ITM.title": Button("_DATA_PK_ITM.BIN__00006c", "label", (11, 10, 62, 27), 0, face="sprout"),
    "PK_ITM.footer": Button(
        "_DATA_PK_ITM.BIN__00006c", "label", (4, 139, 104, 10), 0, face="sprout"
    ),
    "SAMP.syringe": Button(
        "_DATA_SAMP.BIN__014e48",
        "balloon",
        (720, 64, 48, 40),
        6,
        drawn_4bpp=True,
        chunk=1,
        face="bean",
    ),
}


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


def stone(
    canvas: paint.Canvas, button: Button, box: paint.Box, entry: Entry, face: Face, what: str
) -> None:
    """Refill the Japanese's ink and its antialias from the stone round it (`inside_stone`),
    and set the English bold, centred on where the Japanese was, in the ink it used."""
    x0, y0, w, h = box
    ground = inside_stone(canvas, button, (x0 - DONOR_MARGIN, y0, w + 2 * DONOR_MARGIN, h))
    lum = {p: luminance(_colour(canvas, button, p)) for p in ground}
    ink = {p for p in set(paint.points(box)) & ground if lum[p] < INK_DARK}
    _repaint(canvas, box, entry, face, what, ground, lum, ink)


def plate(
    canvas: paint.Canvas, button: Button, box: paint.Box, entry: Entry, face: Face, what: str
) -> None:
    """A stone's recipe, in the game's glyphs at their own weight, on a plate whose ground is
    dithered (bug sumo's swap plate): only `button.text` of the sprite is touched, and a pixel
    is refilled from a donor an even number of steps away, so the dither keeps its phase."""
    room = text_area(button, box)
    area = set(paint.points(room))
    lum = {p: luminance(_colour(canvas, button, p)) for p in area}
    ink = {p for p in area if lum[p] < INK_DARK}
    _repaint(canvas, room, entry, face, what, area, lum, ink, bold=False, parity=True)


def text_area(button: Button, box: paint.Box) -> paint.Box:
    """`button.text` placed on the sprite's `box`: stretched if widening went through it,
    moved with the art if it lies right of where widening went."""
    tx, ty, tw, th = button.text
    if button.widen:
        split = button.split
        if tx <= split < tx + tw:
            tw += stretched(button)
        elif tx > split:
            tx += stretched(button)
    return box[0] + tx, box[1] + ty, tw, th


def stretched(button: Button) -> int:
    """Columns inserted into the button's art by its `Widen`."""
    widen = button.widen
    return widen.extra if widen.stretch is None else widen.stretch


def plank(
    canvas: paint.Canvas, button: Button, box: paint.Box, entry: Entry, face: Face, what: str
) -> None:
    """A stone's recipe on a plain board whose Japanese is partly punched through to
    transparency (bug sumo's とじる): `box` is the board, and a transparent pixel in it is ink."""
    colours = {p: _colour(canvas, button, p) for p in paint.points(box)}
    ground = set(colours)
    opaque = {p for p, c in colours.items() if c[3]}
    lum = {p: luminance(c) if c[3] else 0 for p, c in colours.items()}
    ink = {p for p in ground if lum[p] < INK_DARK}
    _repaint(canvas, box, entry, face, what, ground, lum, ink, inked=ink & opaque)


def _repaint(
    canvas, room, entry, face, what, ground, lum, ink, *, inked=None, bold=True, parity=False
) -> None:
    """Refill `ink` and its antialias (darker than `SOFT`, touching it, inside `room`) from the
    nearest pixel of `ground` that is neither, and stamp the English (`bold`) in `room`, in
    the entry `inked` used most, centred where the Japanese was."""
    found(ink, what)
    box = set(paint.points(room))
    soft = {p for p in paint.grown(ink, 1, 1, 1, 1) & box & ground - ink if lum[p] < SOFT}
    mask = ink | soft
    donors = {p for p in ground - mask if lum[p] >= INK_DARK}
    text = ink_of(face, entry)
    text = paint.normalised(paint.bold(text) if bold else text)
    fits(entry, text, room, what)
    ink_index = canvas.most_used(ink if inked is None else inked, stock=True)
    left = canvas.fill_from_nearest(mask, donors, parity=parity)
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


def groups(marks: paint.Ink) -> list[paint.Ink]:
    """The 8-connected groups of `marks`."""
    out, todo = [], set(marks)
    while todo:
        group, stack = set(), [todo.pop()]
        while stack:
            p = stack.pop()
            group.add(p)
            for q in paint.grown({p}, 1, 1, 1, 1) & todo:
                todo.discard(q)
                stack.append(q)
        out.append(group)
    return out


def islands(marks: paint.Ink, interior: paint.Ink, inked: paint.Ink) -> paint.Ink:
    """The type in a balloon, not the tail's or the outline's shading that reaches in from the
    edge: the groups of `marks` that `interior` surrounds on every side and that carry ink
    (`inked` -- a pale speck of shading is no type), and then any other group on only the rows
    those span (a stroke that runs out to the outline, as the last kana of リストへ does)."""
    parts = groups(marks)
    inner = [g for g in parts if paint.grown(g, 1, 1, 1, 1) <= interior and g & inked]
    if not inner:
        return set()
    _, top, _, h = paint.extent(set().union(*inner))
    return set().union(*(g for g in parts if all(top <= y < top + h for _, y in g)))


BLANK = 0
"""The entry a widened balloon's old place is cleared to: transparent in every slice used."""
PAGE = 256
"""Texels across a texture page at 4bpp. A sprite may not cross one; every widened texture
here is uploaded at a page's left edge (VRAM x 832), so its x counts from a page edge."""


def layout(canvas: paint.Canvas, group: Sequence[tuple[Entry, Button]]) -> dict[Button, paint.Box]:
    """Widen (and place) every balloon of `group` that has a `Widen`, in both the stock view
    the recipes detect in and the pixels they write; each button's box afterwards."""
    widened = [b for _, b in group if b.widen]
    boxes = {b: b.box for _, b in group}
    names = {b: e.id for e, b in group}
    if not widened:
        return boxes
    for b in widened:
        if canvas.palette(b.clut, b.chunk)[BLANK][3]:
            raise TextureTextError(f"{names[b]}: entry {BLANK} is not transparent to blank with")
    stock = bytearray(canvas.stock)
    arts = {}
    for b in widened:
        x0, y0, w, h = b.box
        split, extra = b.split, b.widen.extra
        stretch = stretched(b)
        if extra % 2 or stretch < extra:
            raise TextureTextError(f"{names[b]}: widen by an even count, stretch by at least it")
        rows = [stock[y * canvas.width + x0 : y * canvas.width + x0 + w] for y in range(y0, y0 + h)]
        art = [r[:split] + r[split : split + 2] * (stretch // 2) + r[split:] for r in rows]
        palette = canvas.palette(b.clut, b.chunk)
        if any(palette[v][3] for r in art for v in r[w + extra :]):
            raise TextureTextError(f"{names[b]}: the stretched art runs past the sprite")
        arts[b] = [r[: w + extra] for r in art]
    sources = set().union(*(paint.points(b.box) for b in widened))
    taken: paint.Ink = set()
    for b in widened:
        target = x, y, w, h = b.placed
        place = set(paint.points(target))
        if (
            x + w > canvas.width
            or (b.drawn_4bpp and x // PAGE != (x + w - 1) // PAGE)
            or place & taken
            or any(p not in sources and _colour(canvas, b, p)[3] for p in place)
        ):
            raise TextureTextError(f"{names[b]}: the widened balloon's place {target} is not free")
        taken |= place
        boxes[b] = target
    for source in (stock, canvas.pixels):
        for x, y in sources:
            source[y * canvas.width + x] = BLANK
        for b in widened:
            x, y, w, h = boxes[b]
            for dy, row in enumerate(arts[b]):
                source[(y + dy) * canvas.width + x : (y + dy) * canvas.width + x + w] = row
    canvas.stock = bytes(stock)
    return boxes


def size_edits(archive: Archive, inv: Inventory, button: Button, box, what) -> list[ByteEdit]:
    move = (box[0] - button.box[0], box[1] - button.box[1])
    return [size.edit(archive, inv, button.texture, move, button.widen.extra, what)
            for size in button.widen.sizes]  # fmt: skip


NUDGES = sorted(((dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)),
                key=lambda d: (d[0] ** 2 + d[1] ** 2, d))  # fmt: skip
"""Where a balloon's English may sit off the Japanese's centre, nearest first: an oval is
narrower at the top than the bottom, so two lines centred can graze it where a step down
clears it."""


def balloon(
    canvas: paint.Canvas, button: Button, box: paint.Box, entry: Entry, face: Face, what: str
) -> None:
    """Blank the balloon's label to paper and set the English inside its outline (`box`, where
    `layout` left it), a pixel of paper all round every inked pixel."""
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
    if button.text:
        marks &= set(paint.points(text_area(button, box)))
    inked = {p for p in marks if luminance(_colour(canvas, button, p)) < SOFT}
    japanese = found(islands(marks, interior, inked), what)
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


def label(
    canvas: paint.Canvas, button: Button, box: paint.Box, entry: Entry, face: Face, what: str
) -> None:
    """Coloured type printed on a pale card (the radio-exercise card): the Japanese's whole
    rectangle, grown a pixel, is cleared first -- refilled from the card beside it in the
    box's rows, which on flat paper is the paper itself -- and the English lines set centred
    where it was, in the most saturated colour the Japanese used. `box` must hold the type
    and a pixel of card round it, and nothing else printed; the tinted fringe of a hole
    punched through the card (within `EDGE` of transparency) is not type."""
    x0, y0, w, h = box
    colours = {p: _colour(canvas, button, p) for p in paint.points(box)}
    around = {p: _colour(canvas, button, p)
              for p in paint.points((x0 - EDGE, y0 - EDGE, w + 2 * EDGE, h + 2 * EDGE))
              if 0 <= p[0] < canvas.width and 0 <= p[1] < canvas.height}  # fmt: skip
    holes = paint.grown({p for p, c in around.items() if not c[3]}, EDGE, EDGE, EDGE, EDGE)
    ink = found({p for p, c in colours.items() if c[3] and saturation(c) > INK_SATURATION
                 and p not in holes}, what)  # fmt: skip
    jx, jy, jw, jh = paint.extent(ink)
    if jx == x0 or jy == y0 or jx + jw == x0 + w or jy + jh == y0 + h:
        raise TextureTextError(
            f"{what}: the type reaches the edge of its box {box}: the box takes in more than "
            f"the type (a picture's frame, a rule), which would be cleared with it"
        )
    rect = set(paint.points((jx - 1, jy - 1, jw + 2, jh + 2))) & set(colours)
    near = (x0 - LABEL_MARGIN, y0, w + 2 * LABEL_MARGIN, h)
    around = {p: _colour(canvas, button, p) for p in paint.points(near)
              if 0 <= p[0] < canvas.width}  # fmt: skip
    donors = {p for p, c in around.items() if p not in rect and c[3]
              and saturation(c) <= INK_SATURATION and luminance(c) >= PAPER}  # fmt: skip
    strongest = max(saturation(colours[p]) for p in ink)
    core = [p for p in ink if saturation(colours[p]) >= strongest - CORE_SPREAD]
    ink_index = canvas.most_used(core, stock=True)
    block = lines_block(face, lines_of(entry), entry)
    fits(entry, paint.grown(block, 1, 1, 1, 1), box, what)
    left = canvas.fill_from_nearest(rect, donors, reach=LABEL_REACH)
    if left:
        raise TextureTextError(f"{what}: {len(left)} pixel(s) of the label had nothing near to "
                               f"be refilled from, first {left[:3]}")  # fmt: skip
    cx, cy = centred(block, (jx, jy, jw, jh))
    _, _, bw, bh = paint.extent(block)
    # centred on the Japanese, but kept a pixel inside the box when the English is wider
    cx = min(max(cx, x0 + 1), x0 + w - 1 - bw)
    cy = min(max(cy, y0 + 1), y0 + h - 1 - bh)
    canvas.stamp((cx, cy), block, ink_index)


def saturation(colour) -> int:
    return max(colour[:3]) - min(colour[:3])


LABEL_MARGIN = 6
"""How far left and right of a label's box its refill may take the card's colour from. Only
the box's own rows give colour: a rule or a shadow just above or below the type (the grid
over the card's footer) must not be drawn down into it."""
LABEL_REACH = 64
"""How far a cleared pixel looks for a donor: across the widest label, from its own row."""
INK_SATURATION = 40
"""A card's pixel more saturated than this is its printed type (the card is near-white)."""
CORE_SPREAD = 30
"""The type's own colour: within this much saturation of its most saturated pixel."""

RECIPES = {"stone": stone, "plank": plank, "plate": plate, "balloon": balloon, "label": label}


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
        boxes = layout(canvas, group)
        for entry, button in sorted(group, key=lambda eb: eb[0].id):
            what = f"the {entry.id.removeprefix(FAMILY)} button"
            box = boxes[button]
            RECIPES[button.kind](canvas, button, box, entry, face_named(button.face, face), what)
            if button.widen:
                edits += size_edits(archive, inv, button, box, what)
        edits += canvas.patches()
    return edits
