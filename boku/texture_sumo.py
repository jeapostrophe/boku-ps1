"""Bug sumo's bout: the stamina plate, the chalked rank mark and the winning-move banner (PLAN
`GFX-12`). What each is, how the game draws it and every measurement below:
`research/texture-recipes.md` § "Bug sumo's bout".

The English is `sumo@<part>.<key>` in `translation/textures/sumo.txt`. Three parts (`PARTS`),
each built whole or refused, each on a texture the bug-sumo desk loads:

* **move** -- the banner shown when a bout ends: a heading and one strip of lettering per way
  a bout can end -- a real technique's name over its English gloss, any other move alone.
  The page is cleared and each strip set again as horizontal lines, the heading moved to a
  free corner of the atlas's third page, and the code that places the heading, the move and
  the veil behind them is given the new places;
* **plate** -- the stamina plate between the two bars, widened to hold its word in the game's
  glyphs and set down in free texels, the bars moved out from it;
* **rank** -- the rank chalked on the desk, one drawing per rank: the chalk inside the ring is
  refilled from the desk's wood and the rank written in the same chalk.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from boku import texture_paint as paint
from boku.archive import Archive
from boku.reinsert import ByteEdit
from boku.textures import Inventory
from boku.tim import luminance
from boku.typeset import Face

from boku.texture_closeups import emboldened  # isort: skip
from boku.texture_text import (  # isort: skip
    Entry, TextureTextError, centred, centred_across, filled_from_nearest, fits, found, ink_of,
    outlined, overlay_edit,
)  # fmt: skip

FAMILY = "sumo@"
OVERLAY = "MUSI.OVL"
REASON = "GFX-12: bug sumo's bout in English"

# --- the banner ------------------------------------------------------------------------------

BANNER_ATLAS = "_DATA_M_S01100.BIN__0164b4"
"""Drawn at 4bpp; its first 256x256 page holds only the banner's strips."""
BANNER_CLUT, BANNER_CHUNK = 2, 2
PAGE = 256

MOVES = 22
"""The ways a bout can end (`HOW_IT_ENDED`), each a byte of `CELL_TABLE` naming its strip."""
GLOSSED = (0, 1, 2, 3, 4, 6, 8, 9, 10, 11, 12, 14, 15, 16, 17)
"""The ways a bout ends that are real sumo techniques, named in Japanese (glossary § 4b). Each
has an English gloss, `move.gloss-<move>`, drawn under its name (Jay, decisions § 29b)."""
CELL_TABLE = 0x8007A2F0
HOW_IT_ENDED = 0x8008EFC0
HEADING_CELL = 0
HEADING_RECORD, MOVE_RECORD = 0x8008F2D8, 0x8008F2F8
"""What the heading and the move are drawn from: halfwords `u, v, w, h, x, y, drawn w, drawn
h`, the texture page's VRAM `x, y`, the CLUT's, and at +0x18 how far each has faded in, to
0x80."""
RETAIL_COLUMN = 20
"""Retail: a strip is a 20-texel column of vertical lettering."""
RETAIL_ROWS = ((0, 143, 11), (144, 111, 12))
"""Each retail row of columns: its top, its height, how many columns."""
CELLS = sum(count for _, _, count in RETAIL_ROWS)
"""Retail's strips: the heading's and the 22 moves'."""

LINE = 11
"""Rows from one line of a strip to the next: a bold line's ink is rows 1-10 of the glyphs'
12-row cell (but `j`'s dot, on row 0: `strip` refuses a gloss that would touch the name), so
one dark row lies between a descender and a capital under it."""
NAME_TOP, GLOSS_TOP = 0, LINE
"""The row of a strip the name's glyph cell starts on, and its gloss's."""
ALONE_TOP = (LINE + 1) // 2
"""... and a name with no gloss: midway between the two lines it would share."""
CELL = (124, GLOSS_TOP + 12)
"""Ours: a strip is two horizontal lines, the gloss's cell ending on the strip's last row (its
ink never reaches the cell's, so the edge under it is inside). A strip ends by texel 255 (the
draw adds in a byte): two columns of 124, eleven strips a column."""
COLUMN_U = (0, 128)
PER_COLUMN = RETAIL_ROWS[0][2]
"""Cells 0-10 are in the first column, 11-21 in the second, `CELL[1]` rows apart -- the retail
routine's own split at 11, turned on its side. The heading's cell 0 has left the page, so a
move's cell is retail's less one (`CELL_TABLE` rewritten)."""

HEADING = (90, 12)
"""The heading's strip, one line: its `w, h`."""
PAGE_X, HEADING_PAGE_X = 832, 960
"""The texture page of the strips, the atlas's first, and of the heading, its third: VRAM x."""
HEADING_BOX = ((HEADING_PAGE_X - PAGE_X) * 4 + HEADING[0], HEADING_PAGE_X & 0xFF, *HEADING)
"""The heading in the atlas as drawn at 4bpp: page `u, v` are its width and its page's x (the
registers its routine stores them from; research/texture-recipes.md § "The winning-move
banner"), in that page's free corner."""

BAND_RECT = 0x8007A308
RETAIL_BAND = (130, 35, 60, 140)
BAND = (90, 80, 140, 50 + LINE)
"""The grey veil behind the lettering: `x, y, w, h` on screen, a line taller than the two
lines' veil was, so the gloss has the room under it the name had."""
STRIP_X = 98
HEADING_X = STRIP_X + (CELL[0] - HEADING[0]) // 2
"""The heading centred over the strips: a line centred in either is at the same x."""
HEADING_Y, MOVE_Y, ALONE_Y = 89, 109, 99
"""Where the heading and the move are drawn, and the one strip that has no heading over it
(`ALONE`, the draw), centred in the veil."""
ALONE = 20


def cell_box(cell: int) -> paint.Box:
    """Where our strip `cell` (0-21) is in the rebuilt page."""
    column, row = divmod(cell, PER_COLUMN)
    return COLUMN_U[column], row * CELL[1], *CELL


def retail_cell_box(cell: int) -> paint.Box:
    first = RETAIL_ROWS[0][2]
    (top, height, _), k = (RETAIL_ROWS[0], cell) if cell < first else (RETAIL_ROWS[1], cell - first)
    return k * RETAIL_COLUMN, top, RETAIL_COLUMN, height


def retail_cells(archive: Archive) -> dict[str, int]:
    """The retail strip each key of the `move` part is drawn from: the heading's, and each
    move's by the import's own table."""
    table = archive.overlay_bytes(OVERLAY, CELL_TABLE, MOVES)
    out = {"heading": HEADING_CELL, **{str(move): table[move] for move in range(MOVES)}}
    if sorted(out.values()) != list(range(CELLS)):
        raise TextureTextError(
            f"{OVERLAY}'s table at {CELL_TABLE:#x} does not give each move a strip of its own: "
            f"not the revision this recipe was measured on"
        )
    return out


def ours(retail: dict[str, int]) -> dict[str, int]:
    """Our strip for each move: retail's, less the heading's that has left the page."""
    return {key: cell - 1 for key, cell in retail.items() if key != "heading"}


def cells(archive: Archive) -> dict[str, int]:
    return ours(retail_cells(archive))


def _addiu(rt: int, value: int) -> int:
    """`addiu $rt, $zero, value`."""
    return 0x24000000 | rt << 16 | value & 0xFFFF


ZERO, V0, V1, A0, A1, A2, A3 = 0, 2, 3, 4, 5, 6, 7


def _sh(rt: int, offset: int, base: int = V0) -> int:
    """`sh $rt, offset($base)`."""
    return 0xA4000000 | base << 21 | rt << 16 | offset & 0xFFFF


def _sll(rd: int, rt: int, shift: int) -> int:
    return rt << 16 | rd << 11 | shift << 6


def _addu(rd: int, rs: int, rt: int) -> int:
    return rs << 21 | rt << 16 | rd << 11 | 0x21


def _subu(rd: int, rs: int, rt: int) -> int:
    return rs << 21 | rt << 16 | rd << 11 | 0x23


def _j(target: int) -> int:
    return 0x08000000 | (target >> 2) & 0x3FFFFFF


MOVE_JOIN = 0x80086630
"""Where the move's routine, a column picked, computes the strip's `v`."""


def banner_code() -> list[tuple[int, int, int]]:
    """The words of `MUSI.OVL` that place the banner, `(RAM address, retail, ours)`, in the
    routines that fill `HEADING_RECORD` and `MOVE_RECORD`; what each does is
    research/texture-recipes.md § "The winning-move banner"."""
    w, h = CELL
    hw, hh = HEADING
    return [
        (0x800865A0, _sh(ZERO, HEADING_RECORD & 0xFFFF), _addiu(V1, HEADING_PAGE_X)),
        (0x800865A8, _addiu(A1, RETAIL_COLUMN), _addiu(A1, hw)),  # the heading's w, and u
        (0x800865AC, _addiu(A0, 128), _addiu(A0, hh)),  # ... and h
        (0x800865B0, _addiu(V1, 163), _sh(V1, 2)),  # v: 960's low byte
        (0x800865B4, _sh(V1, 8), _sh(V1, 0x10)),  # the page
        (0x800865B8, _addiu(V1, 42), _addiu(V1, HEADING_Y)),
        (0x800865C0, _addiu(V1, PAGE_X), _addiu(V1, HEADING_X)),
        (0x800865C4, _sh(V1, 0x10), _sh(V1, 8)),  # x
        (0x800865D4, _sh(ZERO, 2), _sh(A1, 0)),  # u
        (0x8008661C, _addu(A3, ZERO, ZERO), _addiu(A2, h)),  # h, before the branch
        (0x80086620, _j(MOVE_JOIN + 4), _j(MOVE_JOIN)),
        (0x80086624, _addiu(A2, RETAIL_ROWS[0][1]), _addu(A3, ZERO, ZERO)),  # the first column
        (0x8008662C, _addiu(A3, RETAIL_ROWS[1][0]), _addiu(A3, COLUMN_U[1])),  # the second
        (0x80086630, _addiu(A2, RETAIL_ROWS[1][1]), _sll(V0, V1, 1)),
        (0x80086634, _sll(V0, V1, 2), _addu(V0, V0, V1)),
        (0x80086638, _addu(V0, V0, V1), _sll(V0, V0, 3)),
        (0x8008663C, _sll(V1, V0, 2), _subu(V1, V0, V1)),  # 24c - c
        (0x80086648, _sh(V1, MOVE_RECORD & 0xFFFF), _sh(V1, (MOVE_RECORD + 2) & 0xFFFF)),  # to v
        (0x8008664C, _addiu(V0, RETAIL_COLUMN), _addiu(V0, w)),
        (0x80086660, _sh(A3, 2, A1), _sh(A3, 0, A1)),  # the picked value, to u instead of v
        (0x80086670, _addiu(V0, 150), _addiu(V0, ALONE_Y)),
        (0x80086674, _addiu(V0, 142), _addiu(V0, MOVE_Y)),
        (0x80086678, _sh(V0, 8, A1), _sh(V0, 0xA, A1)),  # the move's own place is its y
        (0x80086684, _addiu(V1, 46), _addiu(V1, STRIP_X)),
        (0x80086688, _sh(V1, 0xA), _sh(V1, 8)),  # ... and the shared one its x
        (0x8008668C, _addiu(V1, RETAIL_COLUMN), _addiu(V1, w)),
    ]


def _words(archive: Archive, words: Iterable[tuple[int, int, int]]) -> list[ByteEdit]:
    return [_edit(archive, ram, "<I", (old,), (new,)) for ram, old, new in words]


def _edit(archive: Archive, ram: int, fmt: str, old: tuple, new: tuple) -> ByteEdit:
    return overlay_edit(archive, OVERLAY, ram, fmt, old, new, REASON)


def _line(face: Face, entry: Entry, size: tuple[int, int], top: int) -> paint.Ink:
    """One line of lettering: the English with each letter made bold, centred across `size`
    with its glyph cell's top on row `top`, a pixel left all round it for its edge."""
    text = emboldened(face, entry, entry.text, False)
    return centred_across(entry, text, size, top, "a strip of the banner")


def strip(face: Face, name: Entry, gloss: Entry | None = None) -> paint.Ink:
    """A move's lettering, relative to its strip's corner: the name over its gloss, or a name
    with none midway between the two lines."""
    if gloss is None:
        return _line(face, name, CELL, ALONE_TOP)
    over, under = _line(face, name, CELL, NAME_TOP), _line(face, gloss, CELL, GLOSS_TOP)
    if paint.grown(over, 1, 1, 1, 1) & under:
        raise TextureTextError(
            f"{gloss.where}: {gloss.text!r} touches the name over it with no edge between; "
            f"the lines are {LINE} rows apart"
        )
    return over | under


def heading(face: Face, entry: Entry) -> paint.Ink:
    return _line(face, entry, HEADING, NAME_TOP)


def banner(archive: Archive, inv: Inventory, face: Face, text: dict[str, Entry]):
    canvas = paint.Canvas(inv.get(BANNER_ATLAS), drawn_4bpp=True)
    palette = canvas.palette(BANNER_CLUT, BANNER_CHUNK)
    retail = retail_cells(archive)
    lettering: paint.Ink = set()
    for key, cell in retail.items():
        box = set(paint.points(retail_cell_box(cell)))
        found({p for p in box if canvas.at(p)}, f"the banner's strip for {FAMILY}move.{key}")
        lettering |= box
    inked = [p for p in paint.points((0, 0, PAGE, PAGE)) if canvas.at(p)]
    if not set(inked) <= lettering:
        raise TextureTextError(
            f"{BANNER_ATLAS}'s first page is not the {CELLS} strips this recipe was measured on"
        )
    if any(canvas.at(p) for p in paint.points(HEADING_BOX)):
        raise TextureTextError(f"{BANNER_ATLAS}: the texels at {HEADING_BOX} are not free")
    fill = canvas.most_used(inked)
    edge = min({canvas.at(p) for p in inked}, key=lambda index: luminance(palette[index]))
    canvas.fill((0, 0, PAGE, PAGE), 0)
    ink = heading(face, text["move.heading"])
    outlined(canvas.pixels, canvas.width, HEADING_BOX, ink, fill, edge)
    strips = ours(retail)
    for key, cell in strips.items():
        ink = strip(face, text[f"move.{key}"], text.get(f"move.gloss-{key}"))
        outlined(canvas.pixels, canvas.width, cell_box(cell), ink, fill, edge)
    moves = [str(move) for move in range(MOVES)]
    was, now = tuple(retail[m] for m in moves), tuple(strips[m] for m in moves)
    return [
        *canvas.patches(),
        *_words(archive, banner_code()),
        _edit(archive, CELL_TABLE, f"<{MOVES}B", was, now),
        _edit(archive, BAND_RECT, "<4h", RETAIL_BAND, BAND),
    ]


# --- the stamina plate -------------------------------------------------------------------------

PLATE_ATLAS = "_DATA_M_S01000.BIN__017d24"
"""Drawn at 4bpp from the texture page at the image's x 256 (so `u` is the canvas x less
512), CLUT 0, its second 16 entries."""
PLATE_CLUT, PLATE_CHUNK = 0, 1
PLATE_PAGE_X = 512
PLATE = (592, 193, 36, 20)
PLATE_FACE = (2, 2, 31, 15)
"""The plate's flat face, from its corner: what its frame and its two shadow rows surround."""
PLATE_EXTRA = 20
"""Texels the plate grows by: its face is 31 wide and the word, with its shadow, 47."""
PLATE_TO = (652, 210)
"""Where the widened plate is set down: texels no sprite uses (all entry 0)."""

PLATE_RECORD, RIGHT_FILL, RIGHT_FRAME = 0x80079DE8, 0x80079DCC, 0x80079E20
"""Three of the bout's HUD records: `s16 x` at +2, `u8 u, v` at +6, `u8` texture `w` at +0xC."""
PLATE_WIDTH = 0x8008F286
"""The plate's drawn width, which the HUD opens to."""
RETAIL_PLATE_UV = (80, 193)
RIGHT_X = 180
"""Where retail draws the right bar's frame and its fill."""
HALF = PLATE_EXTRA // 2 - 2
"""How far each bar moves out. Retail draws the plate's 36 texels 40 wide; ours is drawn as
wide as it is, so of the 20 texels added 16 are new width on screen."""


def plate_code() -> list[tuple[int, int, int]]:
    """The words of the HUD's routine that hold the plate's width, `(RAM address, retail,
    ours)`: the floor its counter falls to while the plate opens two pixels a frame -- a lower
    floor is a wider plate -- and each left-hand sprite's resting place."""
    return [
        (0x80082954, 0x2842008D, 0x2842008D - HALF),  # slti $v0, $v0: one over the floor
        (0x80082C0C, _addiu(V0, 0x8C), _addiu(V0, 0x8C - HALF)),  # the floor
        (0x80082C4C, _addiu(V0, 0x88), _addiu(V0, 0x88 - HALF)),  # the left fill's right end
        (0x80082CCC, _addiu(V0, 0x88), _addiu(V0, 0x88 - HALF)),  # the plate's x
        (0x80082CF0, _addiu(V0, 0x28), _addiu(V0, 0x28 - HALF)),  # the left frame's x
    ]


def plate(archive: Archive, inv: Inventory, face: Face, text: dict[str, Entry]):
    entry = text["plate.stamina"]
    canvas = paint.Canvas(inv.get(PLATE_ATLAS), drawn_4bpp=True)
    palette = canvas.palette(PLATE_CLUT, PLATE_CHUNK)
    x0, y0, w, h = PLATE
    fx, fy, fw, fh = PLATE_FACE
    what = "the stamina plate"
    face_box = paint.points((x0 + fx, y0 + fy, fw, fh))
    ground = canvas.most_used(face_box)
    level = luminance(palette[ground])
    lum = {p: luminance(palette[canvas.at(p)]) for p in face_box}
    light = canvas.most_used(found({p for p in face_box if lum[p] > level}, what))
    shade = canvas.most_used(found({p for p in face_box if lum[p] < level}, what))
    wide = (*PLATE_TO, w + PLATE_EXTRA, h)
    if any(canvas.at(p) for p in paint.points(wide)):
        raise TextureTextError(f"{what}: the texels at {wide} are not free")
    rows = [[canvas.at((x0 + x, y0 + y)) for x in range(w)] for y in range(h)]
    for y in range(fy, fy + fh):
        rows[y][fx : fx + fw] = [ground] * fw
    split = w // 2
    canvas.fill(PLATE, 0)
    for y, row in enumerate(rows):
        # the pair of columns at the centre repeated: a pair, so a dither would keep its phase
        row = row[:split] + row[split : split + 2] * (PLATE_EXTRA // 2) + row[split:]
        start = (wide[1] + y) * canvas.width + wide[0]
        canvas.pixels[start : start + len(row)] = bytes(row)
    room = (wide[0] + fx, wide[1] + fy, fw + PLATE_EXTRA, fh)
    word = paint.normalised(ink_of(face, entry))
    shadowed = word | {(x + 1, y + 1) for x, y in word}
    fits(entry, paint.grown(shadowed, 1, 1, 1, 1), room, what)
    at = centred(shadowed, room)
    canvas.stamp((at[0] + 1, at[1] + 1), word, shade)
    canvas.stamp(at, word, light)
    records = [
        _edit(archive, PLATE_RECORD + 6, "<BB", RETAIL_PLATE_UV, (wide[0] - PLATE_PAGE_X, wide[1])),
        _edit(archive, PLATE_RECORD + 0xC, "<B", (w,), (w + PLATE_EXTRA,)),
        _edit(archive, RIGHT_FILL + 2, "<h", (RIGHT_X,), (RIGHT_X + HALF,)),
        _edit(archive, RIGHT_FRAME + 2, "<h", (RIGHT_X,), (RIGHT_X + HALF,)),
    ]
    return [*canvas.patches(), *_words(archive, plate_code()), *records]


# --- the rank mark ---------------------------------------------------------------------------

MARK = (64, 56)
"""A rank mark: a chalk ring with the rank written in it, the stick of chalk lying across its
top right corner."""
CHALK = 150
"""Luminance over which a pixel of a mark is chalk."""
WOOD = 80
"""... and under which it is the desk's wood, clean of chalk dust."""


@dataclass(frozen=True)
class RankMark:
    texture: str
    clut: int
    at: tuple[int, int]
    """The mark's corner. "Weak" is painted into the desk itself; the other two are sprites
    the game draws over it at the same place."""
    inside: tuple[float, float, float, float]
    """The ellipse the ring's inner edge follows, `cx, cy, rx, ry` from the corner: the chalk
    in it is the writing."""
    stick: paint.Box
    """The stick of chalk, which the writing runs up to: never writing."""


RANK_MARKS: dict[str, RankMark] = {
    "weak": RankMark(PLATE_ATLAS, 1, (200, 27), (29.0, 29.5, 21.5, 19.5), (46, 0, 18, 14)),
    "strong": RankMark(
        "_DATA_M_S01100.BIN__000014", 0, (256, 133), (30.5, 28.5, 24.0, 19.5), (45, 0, 19, 19)
    ),
    "king": RankMark(
        "_DATA_M_S01100.BIN__000014", 0, (256, 77), (31.0, 30.0, 23.5, 19.0), (45, 0, 19, 19)
    ),
}


def inside(mark: RankMark) -> paint.Ink:
    """The pixels of the mark's texture inside its ring, without the stick."""
    cx, cy, rx, ry = mark.inside
    ox, oy = mark.at
    stick = set(paint.points(mark.stick))
    return {
        (ox + x, oy + y)
        for x, y in paint.points((0, 0, *MARK))
        if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1 and (x, y) not in stick
    }


def rank_mark(canvas: paint.Canvas, mark: RankMark, entry: Entry, face: Face, what: str) -> None:
    """Refill the chalk inside the ring, and the dust round it, from the wood nearest and
    write the rank there, bold, in the writing's own chalk."""
    area = inside(mark)
    palette = canvas.palette(mark.clut)
    lum = {p: luminance(palette[canvas.at(p)]) for p in paint.points((*mark.at, *MARK))
           if palette[canvas.at(p)][3]}  # fmt: skip
    chalk = sorted(found({p for p in area if lum.get(p, 0) > CHALK}, what))
    mask = {p for p in area if lum.get(p, 0) > WOOD}
    wood = {p for p, v in lum.items() if v <= WOOD}
    worn = [canvas.at(p) for p in chalk]
    filled_from_nearest(canvas, mask, wood, reach=16, what=what)
    word = paint.normalised(emboldened(face, entry, entry.text, False))
    cx, cy, _, _ = mark.inside
    _, _, w, h = paint.extent(word)
    at = (mark.at[0] + round(cx - w / 2), mark.at[1] + round(cy - h / 2))
    if not {(x + at[0], y + at[1]) for x, y in word} <= area:
        raise TextureTextError(
            f"{entry.where}: {entry.text!r} is {w}x{h} px bold and does not fit inside "
            f"{what}'s ring; nothing is cut to fit (README)"
        )
    for x, y in word:
        # each pixel in the chalk of one of the old writing's, so the word is as uneven as
        # the ring beside it
        canvas.stamp((at[0] + x, at[1] + y), {(0, 0)}, worn[(x * 7 + y * 13) % len(worn)])


def rank_marks(archive: Archive, inv: Inventory, face: Face, text: dict[str, Entry]):
    canvases = {mark.texture: paint.Canvas(inv.get(mark.texture)) for mark in RANK_MARKS.values()}
    for name, mark in RANK_MARKS.items():
        what = f"the {name} rank mark"
        rank_mark(canvases[mark.texture], mark, text[f"rank.{name}"], face, what)
    return [edit for canvas in canvases.values() for edit in canvas.patches()]


# --- the family --------------------------------------------------------------------------------


Recipe = Callable[[Archive, Inventory, Face, dict[str, Entry]], list[ByteEdit]]
PARTS: dict[str, tuple[tuple[str, ...], Recipe]] = {
    "plate": (("stamina",), plate),
    "rank": (tuple(RANK_MARKS), rank_marks),
    "move": (
        ("heading", *(str(move) for move in range(MOVES)), *(f"gloss-{m}" for m in GLOSSED)),
        banner,
    ),
}
"""The family's parts: each one's keys (`sumo@<part>.<key>`) and the recipe that builds it."""
KEYS = tuple(f"{part}.{key}" for part, (keys, _) in PARTS.items() for key in keys)


def sumo(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """Every part `entries` name, each with all its keys. (The reader builds a part at a
    time; that the tracked file names every part is `tests/test_texture_sumo.py`'s.)"""
    text = {e.id.removeprefix(FAMILY): e for e in entries}
    edits: list[ByteEdit] = []
    for part in sorted({key.split(".", 1)[0] for key in text}):
        keys, recipe = PARTS.get(part, ((), None))
        want = {f"{part}.{key}" for key in keys}
        given = {key for key in text if key.split(".", 1)[0] == part}
        if given != want:
            odd = ", ".join(sorted(FAMILY + key for key in given ^ want))
            where = min(text[key].where for key in given)
            raise TextureTextError(
                f"{where}: {FAMILY}{part} takes exactly its keys (boku.texture_sumo.PARTS); "
                f"missing or unknown: {odd}"
            )
        edits += recipe(archive, inv, face, text)
    return edits


VIEWS: dict[str, tuple[paint.View, ...]] = {
    f"{FAMILY}move": (
        paint.View(BANNER_ATLAS, True, BANNER_CLUT, BANNER_CHUNK, (0, 0, PAGE, PAGE),
                   (0, 0, PAGE, PAGE)),
        paint.View(BANNER_ATLAS, True, BANNER_CLUT, BANNER_CHUNK,
                   retail_cell_box(HEADING_CELL), HEADING_BOX),
    ),
    f"{FAMILY}plate": (
        paint.View(PLATE_ATLAS, True, PLATE_CLUT, PLATE_CHUNK, PLATE,
                   (*PLATE_TO, PLATE[2] + PLATE_EXTRA, PLATE[3])),
    ),
    f"{FAMILY}rank": tuple(
        paint.View(mark.texture, False, mark.clut, 0, (*mark.at, *MARK), (*mark.at, *MARK))
        for mark in RANK_MARKS.values()
    ),
}  # fmt: skip
"""The reader's pictures of each part, by the group its strings are shown under: a whole atlas
through CLUT 0 at its header's depth shows none of these as the game does."""
