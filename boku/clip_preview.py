"""An epilogue's subtitle pages as the screen shows them, drawn without an emulator (`VO-09`).

The reader shows each page of an epilogue over the picture it meets, so a page that is up
too briefly, or with the wrong picture, is seen without booting anything. Everything drawn
is read from where the game and the build read it:

* **the picture** from the ending's own pack `OTI0n.BIN` -- two stills, each a map-pack
  background (pieces of an atlas placed on the screen: `research/event-scripts.md` § The
  epilogue's clock), and the production card, which the build typesets in English;
* **the band and the pen** from the edit set's `layout` record, which the renderer is
  assembled with; the band adds its brightness to what is behind it;
* **the glyphs** from the font sheet with the edit set's font-sheet edits applied, by the
  cell and the advance of the edit set's own character map (`boku.layout.CellMapEncoder`).

`tests/test_real_clip_subtitle_beetle.py` holds a frame drawn here to the same frame on
Beetle PSX. The fades between pictures are not drawn: a page is shown over the picture that
is up at its middle. **What this draws is the game's pixels; it is written under `work/`
only** (CLAUDE.md § "This repo is public").
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass

from boku import epilogue
from boku.archive import ARCHIVE_NAME, Archive, parse_pack
from boku.build import EditSet
from boku.layout import Encoder
from boku.png import write_rgba
from boku.tim import Tim, parse_exact
from boku.typeset import CELL, GameFace

WIDTH, HEIGHT = 320, 240
INK = (24, 24, 24)
SHADOW = (144, 144, 136)
SHADOW_AT = ((1, 0), (0, 1))
"""The dialogue text: each glyph in `INK`, over copies of itself in `SHADOW` one pixel right
and one pixel down (measured on Beetle, a subtitle over a still: with these a drawn frame
is the emulator's, pixel for pixel)."""
WHITE = 248
"""The brightest a channel gets: the console's 5 bits, as the emulator shows them."""
FONT_MEMBER, FONT_CHILD = "ONMEM.BIN", 2
"""The glyph sheet (`research/font.md`)."""
STILL_PLACEMENT, STILL_PIECES, STILL_ATLAS = 0, 2, 6
"""A still's children: where each piece goes on the screen, where each is cut from the
atlas, and the atlas (an 8-bit TIM with a CLUT per layer)."""
CARD_CHILD = 2
CARD_AT = (23, 94)
"""Where `ENDOTI` draws the 276 x 33 production card (`0x80079C64`: x `0x17`, y `0x5E`)."""


class PreviewError(Exception):
    """A pack or an edit set that is not what this module was written against."""


@dataclass(frozen=True)
class Band:
    """The dialogue band's geometry, as the edit set records the renderer was built with."""

    pen_x: int
    pen_y: int
    line_pitch: int
    band_y: int
    band_h: int
    band_brightness: int

    @classmethod
    def of(cls, edit_set: EditSet) -> Band:
        record = edit_set.document.get("layout")
        try:
            return cls(**{name: int(record[name]) for name in cls.__dataclass_fields__})
        except (TypeError, KeyError, ValueError) as error:
            raise PreviewError(f"the edit set's layout record has no {error}") from error


def font_sheet_bytes(archive: Archive, edit_set: EditSet) -> bytes:
    """The font TIM the build installs: the import's, with the edit set's edits to it, each
    edit's `old` bytes checked first as the image build checks them. `tools/vwf/mockup.py`
    draws from the same bytes."""
    member = archive.member(FONT_MEMBER)
    pack = parse_pack(archive.blob(member))
    if pack is None or len(pack.entries) <= FONT_CHILD:
        raise PreviewError(f"{FONT_MEMBER} is not the pack research/font.md describes")
    offset, size = pack.entries[FONT_CHILD]
    start = member.offset + offset
    sheet = bytearray(archive.boku[start : start + size])
    applied = 0
    for edit in edit_set.edits:
        if edit.file != ARCHIVE_NAME or not start <= edit.offset < start + size:
            continue
        at = edit.offset - start
        if bytes(sheet[at : at + len(edit.old)]) != edit.old:
            raise PreviewError(
                f"{edit.reason}: the import does not hold the bytes this edit expects at "
                f"BOKU.BIN+{edit.offset:#x}; the edit set was built from another dump"
            )
        sheet[at : at + len(edit.new)] = edit.new
        applied += 1
    if not applied:
        raise PreviewError("the edit set carries no font-sheet edit; there is no English font")
    return bytes(sheet)


def built_font(archive: Archive, edit_set: EditSet) -> GameFace:
    """`font_sheet_bytes` as cells to draw from."""
    return GameFace(parse_exact(font_sheet_bytes(archive, edit_set)), {})


def _children(boku: bytes, archive: Archive, ending: int) -> tuple[bytes, list[tuple[int, int]]]:
    member = archive.member(f"OTI0{ending}.BIN")
    blob = boku[member.offset : member.offset + member.size]
    pack = parse_pack(blob)
    if pack is None or len(pack.entries) <= CARD_CHILD:
        raise PreviewError(f"{member.short_name} is not the three-child pack ENDOTI loads")
    return blob, pack.entries


def still(archive: Archive, ending: int, which: int) -> bytearray:
    """Ending `ending`'s first (`which` 0) or second still: 320 x 240 RGB."""
    blob, entries = _children(archive.boku, archive, ending)
    offset, size = entries[which]
    child = blob[offset : offset + size]
    pack = parse_pack(child)
    if pack is None or len(pack.entries) <= STILL_ATLAS:
        raise PreviewError(f"OTI0{ending} child {which} is not a map-pack background")
    placement, pieces, atlas = (
        child[at : at + length]
        for at, length in (pack.entries[k] for k in (STILL_PLACEMENT, STILL_PIECES, STILL_ATLAS))
    )
    tim = parse_exact(atlas)
    (count,) = struct.unpack_from("<H", pieces)
    if struct.unpack_from("<H", placement, 24)[0] != count:
        raise PreviewError(f"OTI0{ending} child {which}: its two tables disagree on the pieces")
    canvas = bytearray(WIDTH * HEIGHT * 3)
    layers: dict[int, bytes] = {}
    for piece in range(count):
        u, v, w, h, _, clut = struct.unpack_from("<6H", pieces, 4 + 12 * piece)
        x, y = struct.unpack_from("<2h", placement, 28 + 8 * piece)
        if clut // 64 not in layers:
            layers[clut // 64] = tim.decode_rgba(clut // 64)
        if 2 * (u + w) > tim.width or v + h > tim.height:
            raise PreviewError(f"OTI0{ending} child {which}: piece {piece} is outside its atlas")
        _paste(canvas, layers[clut // 64], tim.width, 2 * u, v, 2 * w, h, x, y)
    return canvas


def _paste(canvas: bytearray, rgba: bytes, stride: int, u, v, w, h, x, y) -> None:
    """`w` x `h` of an RGBA image from `(u, v)` to `(x, y)`; a clear pixel draws nothing."""
    for row in range(max(0, -y), min(h, HEIGHT - y)):
        source = 4 * ((v + row) * stride + u)
        for column in range(max(0, -x), min(w, WIDTH - x)):
            at = source + 4 * column
            if rgba[at + 3]:
                to = 3 * ((y + row) * WIDTH + x + column)
                canvas[to : to + 3] = rgba[at : at + 3]


def card(archive: Archive, ending: int, boku: bytes | None = None) -> bytearray:
    """The production card on black; `boku` is the archive's bytes as a build left them
    (`boku.texture_text.patched_archive`), for the card in English."""
    blob, entries = _children(archive.boku if boku is None else boku, archive, ending)
    tim: Tim = parse_exact(blob, entries[CARD_CHILD][0])
    canvas = bytearray(WIDTH * HEIGHT * 3)
    _paste(canvas, tim.decode_rgba(0), tim.width, 0, 0, tim.width, tim.height, *CARD_AT)
    return canvas


def backdrop(archive: Archive, picture: epilogue.Picture, at: int, boku: bytes | None) -> bytearray:
    """What `ENDOTI` shows `at` vsyncs after the subtitle opens, fades apart."""
    showing = picture.showing(at)
    if showing == epilogue.FIRST_STILL:
        return still(archive, picture.ending, 0)
    if showing == epilogue.SECOND_STILL:
        return still(archive, picture.ending, 1)
    if showing == epilogue.CARD:
        return card(archive, picture.ending, boku)
    return bytearray(WIDTH * HEIGHT * 3)


def draw_subtitle(
    canvas: bytearray, lines: Sequence[str], encoder: Encoder, font: GameFace, band: Band
) -> None:
    """The band over `canvas`, and `lines` in it, as `asm/voice.asm` has them drawn."""
    rows = slice(3 * WIDTH * band.band_y, 3 * WIDTH * (band.band_y + band.band_h))
    canvas[rows] = bytes(min(value + band.band_brightness, WHITE) for value in canvas[rows])
    lit: dict[int, list[tuple[int, int]]] = {}
    for number, line in enumerate(lines):
        x, y = band.pen_x, band.pen_y + number * band.line_pitch
        for character in line:
            cell = encoder.glyph(character)
            if cell is not None and cell not in lit:
                bits = font.cell_bits(cell)
                lit[cell] = [(c, r) for r in range(CELL) for c in range(CELL) if bits[r][c]]
            for colour, dx, dy in (*((SHADOW, dx, dy) for dx, dy in SHADOW_AT), (INK, 0, 0)):
                for column, row in lit.get(cell, ()):
                    px, py = x + column + dx, y + row + dy
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        to = 3 * (py * WIDTH + px)
                        canvas[to : to + 3] = bytes(colour)
            x += encoder.advance(character)


def png(canvas: bytes) -> bytes:
    rgba = bytearray(b"\xff" * (WIDTH * HEIGHT * 4))
    for channel in range(3):
        rgba[channel::4] = canvas[channel::3]
    return write_rgba(WIDTH, HEIGHT, bytes(rgba))
