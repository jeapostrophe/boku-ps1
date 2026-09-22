"""The movie-subtitle block: glyph masks and cues, as `asm/movie.asm` reads them (`FMV-04`).

`research/movies.md` § 7 is the specification; this module is its one encoder and the
reference rasteriser the emulator test predicts pixels with. Nothing here reads the disc:
the glyphs come in as the same `Glyph` objects `build_prototype.py` builds the font sheet
from, so the masks are derived from the sheet's source and never retyped.

Block layout (little-endian, RAM address `BLOCK_RAM`, read by `movie_sub_load` from the
`boku.disc.form1_sectors(len(block))` sectors at `BLOCK_LBA`):

    +0   u32 magic         `MAGIC`; the blit routine is a no-op unless it matches, so an
                           image with the hooks and no block (or filler where the block
                           would be) plays its movies untouched
    +4   u16 cue_count
    +6   u16 glyphs_offset  from the block's first byte
    +8   cue[cue_count]     {u16 start_frame, u16 end_frame, u16 lines_offset, u16 0}
    lines_offset: line*     {u16 x, u16 y, u8 glyph_index..., 0xFF, u8 0 if needed to make
                           the line an even length}, ended by u16 x = 0xFFFF: every header
                           is halfword-aligned, and the routine rounds its cursor up to the
                           next even byte after each 0xFF rather than trusting the count
    glyphs_offset: record[] `RECORD_SIZE` bytes each, index = the u8 in a line:
                           {u8 advance, u8[3] 0, u16 glyph[MASK], u16 outline[MASK], u8[4] 0}

A mask row's bit `15 - c` is column `c` of a `MASK` x `MASK` cell whose column 1, row 1 is
the 12 x 12 glyph's origin, so the 1-px outline has room on every side; the cell's column
0 sits at pen x - 1 and its row 0 at line y - 1. A frame is in a cue when
`start <= frame <= end` (STR header numbers, 1-based). Colours: `WHITE` where the glyph
mask is set, else `DARK` where the outline is; a later glyph or line overwrites an earlier
one, which is also the order the routine draws in.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from boku.glyphs import unencodable_by

MAGIC = 0x42534B42
"""`b"BKSB"` as the little-endian word the routine compares."""
BLOCK_RAM = 0x801C0000
"""Above the movie arena's end (`research/movies.md` § 2.1: `0x8018D3F4` retail, `0x3000`
higher under `asm/arena.asm`) and 250 KB under the stack's measured low-water mark."""
BLOCK_LBA = 1040
"""Near the top of the relocation arena (`boku.relocate.PREFIX_FILLER`), which the allocator
fills from the bottom: milestone 1 of `FMV-04` writes here directly, and `write_movie_block`
refuses a block that does not fall inside that run. The cue-file unit hands the block to the
allocator instead."""
SCREEN_WIDTH = 320
"""Pixels across the frame -- the movie's and the dialogue renderer's alike, so
`tools/vwf/build_prototype.py` measures its margins against this one."""
FRAME_HEIGHT = 240
SLICE_WIDTH = 16
"""Pixels per MDEC slice: the width of the buffer `movie_dctout_cb` uploads."""
SLICES = SCREEN_WIDTH // SLICE_WIDTH
CELL = 12
"""The font sheet's glyph cell: 12 x 12 one-bit pixels (`research/font.md`). Here because
`tools/vwf/build_prototype.py` builds the sheet and the masks from one number."""
MASK = 14
RECORD_SIZE = 64
"""Advance + two 14-row masks is 60 bytes; 64 makes the record index a shift."""
CUE_SIZE = 8
END_OF_LINE = 0xFF
END_OF_LINES = 0xFFFF
U16_MAX = 0xFFFF
"""The largest value the block's count and offset fields hold."""
WHITE = (0xFF, 0xFF, 0xFF)
DARK = (0x18, 0x18, 0x14)
"""`g_text_flags & 4`'s shadow colour (`research/font.md` § The draw code)."""
LINE_Y = (200, 200 + MASK)
"""The two lines' cell tops, a whole mask apart so no outline overlaps the line above.
Ink to row 225, outline to 226 -- inside DuckStation's ~232 visible rows
(`research/vwf-prototype.md` § Round 2) and clear of the 240-row frame."""


class GlyphLike(Protocol):
    rows: tuple[int, ...]
    advance: int


class BlockError(Exception):
    pass


@dataclass(frozen=True)
class Cue:
    start: int
    end: int
    lines: tuple[str, ...]
    """Each line is centred on the screen at `LINE_Y[i]`."""


@dataclass(frozen=True)
class Masks:
    glyph: tuple[int, ...]
    outline: tuple[int, ...]


def masks_of(rows: Sequence[int]) -> Masks:
    """The 14 x 14 glyph and outline masks of a 12 x 12 cell (bit 11 = column 0).

    The glyph lands at (1, 1); the outline is its 8-neighbour dilation minus itself.
    """
    if len(rows) != CELL:
        raise BlockError(f"a glyph has {CELL} rows, not {len(rows)}")
    glyph = [0] + [(row << 3) & 0x7FF8 for row in rows] + [0]
    dilated = []
    for y in range(MASK):
        acc = 0
        for dy in (-1, 0, 1):
            source = y + dy
            if 0 <= source < MASK:
                acc |= glyph[source] | (glyph[source] << 1) | (glyph[source] >> 1)
        dilated.append(acc & 0xFFFF)
    return Masks(tuple(glyph), tuple(d & ~g & 0xFFFF for d, g in zip(dilated, glyph, strict=True)))


def text_width(text: str, font: Mapping[str, GlyphLike]) -> int:
    return sum(font[c].advance for c in text)


def encode_block(cues: Iterable[Cue], font: Mapping[str, GlyphLike]) -> bytes:
    """The block for `cues`, carrying every glyph of `font` (the VWF set, so the size
    measured is the size the design pays). Refuses text the font cannot draw, a line wider
    than the screen, a line whose rows leave the frame, and anything the count and offset
    fields cannot name -- every refusal a `BlockError`, so the build reports it as the input
    problem it is rather than letting a `struct.error` out."""
    characters = sorted(font)
    if len(characters) > END_OF_LINE:
        raise BlockError(f"{len(characters)} glyphs; a line's index byte reserves {END_OF_LINE:#x}")
    index = {c: i for i, c in enumerate(characters)}
    cues = list(cues)
    if len(cues) > U16_MAX:
        raise BlockError(f"{len(cues)} cues; the block counts them in a u16")
    header = struct.calcsize("<IHH")
    lines_start = header + CUE_SIZE * len(cues)
    line_blobs: list[bytes] = []
    cue_rows: list[tuple[int, int, int]] = []
    cursor = lines_start
    for cue in cues:
        if not 0 <= cue.start <= cue.end <= 0xFFFF:
            raise BlockError(f"cue frames {cue.start}..{cue.end} are not 0 <= start <= end < 65536")
        if len(cue.lines) > len(LINE_Y):
            raise BlockError(f"a cue holds at most {len(LINE_Y)} lines; {cue.lines!r} has more")
        blob = bytearray()
        for text, y in zip(cue.lines, LINE_Y, strict=False):
            missing = unencodable_by(index.__contains__, text)
            if missing:
                raise BlockError(f"the font has no glyph for {''.join(missing)!r}")
            width = text_width(text, font)
            if width > SCREEN_WIDTH - 2:
                raise BlockError(
                    f"{text!r} is {width} px wide; the screen holds {SCREEN_WIDTH - 2}"
                )
            if y < 1 or y + MASK - 1 > FRAME_HEIGHT:
                raise BlockError(f"line y {y} puts rows outside the {FRAME_HEIGHT}-row frame")
            x = (SCREEN_WIDTH - width) // 2
            blob += struct.pack("<HH", x, y)
            blob += bytes(index[c] for c in text) + bytes([END_OF_LINE])
            blob += bytes(len(blob) % 2)
        blob += struct.pack("<HH", END_OF_LINES, 0)
        if cursor > U16_MAX:
            raise BlockError(
                f"a cue's lines start {cursor} bytes in; the cue row names it in a u16"
            )
        cue_rows.append((cue.start, cue.end, cursor))
        line_blobs.append(bytes(blob))
        cursor += len(blob)
    glyphs_offset = (cursor + 3) & ~3
    if glyphs_offset > U16_MAX:
        raise BlockError(
            f"the glyph table would start {glyphs_offset} bytes in; the header names it in a u16"
        )
    out = bytearray(struct.pack("<IHH", MAGIC, len(cues), glyphs_offset))
    for start, end, offset in cue_rows:
        out += struct.pack("<HHHH", start, end, offset, 0)
    out += b"".join(line_blobs)
    out += bytes(glyphs_offset - len(out))
    for c in characters:
        masks = masks_of(font[c].rows)
        record = struct.pack("<B3x", font[c].advance)
        record += struct.pack(f"<{MASK}H", *masks.glyph) + struct.pack(f"<{MASK}H", *masks.outline)
        out += record.ljust(RECORD_SIZE, b"\0")
    return bytes(out)


# --- the reference rasteriser --------------------------------------------------------------


def render(
    block: bytes, frame: int, x_range: range = range(SCREEN_WIDTH)
) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Every pixel the routine writes for `frame` whose x is in `x_range`, in draw order.

    Decoded from the block's *bytes*, not from the objects that made them, so it holds the
    format to the routine as written; `x_range` is a slice's 16 columns when the test is
    about clipping, the whole width when it is about a frame.
    """
    magic, cue_count, glyphs_offset = struct.unpack_from("<IHH", block, 0)
    if magic != MAGIC:
        return {}
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
    for n in range(cue_count):
        start, end, lines_offset, _ = struct.unpack_from("<HHHH", block, 8 + CUE_SIZE * n)
        if not start <= frame <= end:
            continue
        cursor = lines_offset
        while True:
            cursor = (cursor + 1) & ~1
            x, y = struct.unpack_from("<HH", block, cursor)
            cursor += 4
            if x == END_OF_LINES:
                break
            pen = x
            while block[cursor] != END_OF_LINE:
                record = glyphs_offset + RECORD_SIZE * block[cursor]
                cursor += 1
                advance = block[record]
                # Which of the mask's columns land in `x_range` is a property of the glyph,
                # not of its rows: a glyph outside the slice costs one pass over 14 columns
                # instead of 196 membership tests.
                columns = [c for c in range(MASK) if pen - 1 + c in x_range]
                if columns:
                    glyph = struct.unpack_from(f"<{MASK}H", block, record + 4)
                    outline = struct.unpack_from(f"<{MASK}H", block, record + 4 + 2 * MASK)
                    for row in range(MASK):
                        for column in columns:
                            px, bit = pen - 1 + column, 1 << (15 - column)
                            if glyph[row] & bit:
                                pixels[px, y - 1 + row] = WHITE
                            elif outline[row] & bit:
                                pixels[px, y - 1 + row] = DARK
                pen += advance
            cursor += 1
    return pixels


def slice_columns(slice_index: int) -> range:
    """The pixel columns of the `slice_index`-th MDEC slice."""
    return range(SLICE_WIDTH * slice_index, SLICE_WIDTH * (slice_index + 1))
