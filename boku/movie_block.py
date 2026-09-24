"""The movie-subtitle block: glyph masks and cues, as `asm/movie.asm` reads them (`FMV-04`).

`research/movies.md` § 7 and § 8 are the specification; this module is its one encoder and
the reference rasteriser the emulator test predicts pixels with. Nothing here reads the
disc: the glyphs come in as the same `Glyph` objects `build_prototype.py` builds the font
sheet from, so the masks are derived from the sheet's source and never retyped, and the
movies come in keyed by the RAM address of their name string (`movie_names`).

Block layout (little-endian, RAM address `BLOCK_RAM`, read by `movie_sub_load` from the
`boku.disc.form1_sectors(len(block))` sectors at `BLOCK_LBA`):

    +0   u32 magic         `MAGIC`; the blit routine is a no-op unless it matches, so an
                           image with the hooks and no block (or filler where the block
                           would be) plays its movies untouched
    +4   u16 cue_count     the playing movie's: 0 in the file, written by `movie_sub_load`
    +6   u16 glyphs_offset  from the block's first byte
    +8   u16 cues_offset   the playing movie's: 0 in the file, written by `movie_sub_load`
    +10  u16 movie_count
    +12  movie[movie_count] {u32 name, u16 cues_offset, u16 cue_count}: `name` is the
                           `g_movie_table` name pointer `movie_play_entry` copies to
                           `g_movie_name`; the loader copies the matching row's two
                           fields to +8 and +4, and leaves +4 at 0 when no row matches
    cues_offset: cue[]      {u16 start_frame, u16 end_frame, u16 lines_offset, u16 0}
    lines_offset: line*     {u16 x, u16 y, u8 glyph_index..., 0xFF, u8 0 if needed to make
                           the line an even length}, ended by u16 x = 0xFFFF: every header
                           is halfword-aligned, and the routine rounds its cursor up to the
                           next even byte after each 0xFF rather than trusting the count
    clips_offset: clips     (VO-03) {u16 clip_count, u16 0, clip[clip_count] {u16 index,
                           u16 words_offset}}, each clip's words before it: subtitles for
                           native `g_xa_clips` plays -- dialogue words ending in `0x8000`,
                           drawn by the dialogue renderer (`asm/voice.asm`), not by the masks
    glyphs_offset - 4       {u16 clips_offset, u16 0}: where `clip_sub_play` finds the clips
    glyphs_offset: record[] `RECORD_SIZE` bytes each, index = the u8 in a line:
                           {u8 advance, u8[3] 0, u16 glyph[MASK], u16 outline[MASK], u8[4] 0}

A mask row's bit `15 - c` is column `c` of a `MASK` x `MASK` cell whose column 1, row 1 is
the 12 x 12 glyph's origin, so the 1-px outline has room on every side; the cell's column
0 sits at pen x - 1 and its row 0 at line y - 1. A frame is in a cue when
`start <= frame <= end` (STR header numbers, 1-based). Colours: `WHITE` where the glyph
mask is set, else `DARK` where the outline is; a later glyph or line overwrites an earlier
one, which is also the order the routine draws in.

A cue with a panel (FMV-06) is the same lines, each preceded by a line of `PANEL_MASKS`
tiles at its own y: one more record after the font's, drawn as a glyph is, so the routine
needs no change.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from boku.archive import EXE_LOAD_BIAS
from boku.disc import form1_sectors
from boku.glyphs import END_WORD, iter_tokens, unencodable_by, words_of
from boku.relocate import MOVIE_BLOCK_RESERVE

MAGIC = 0x42534B42
"""`b"BKSB"` as the little-endian word the routine compares."""
BLOCK_RAM = 0x801C0000
"""Above the movie arena's end (`research/movies.md` § 2.1: `0x8018D3F4` retail, `0x3000`
higher under `asm/arena.asm`) and 250 KB under the stack's measured low-water mark."""
BLOCK_LBA = MOVIE_BLOCK_RESERVE.start
"""The block's first sector: the start of the run the relocation allocator never hands out
(`boku.relocate.MOVIE_BLOCK_RESERVE`), so every build -- the prototype's own image and
`boku build --vwf` -- writes it to the same LBA the executable was assembled to read."""
BLOCK_MAX_SECTORS = MOVIE_BLOCK_RESERVE.count
"""The reserve's size; `encode_block` refuses a block that would not fit it."""
MOVIE_TABLE = 0x80029604
"""`g_movie_table`: `MOVIE_ENTRIES` entries of `MOVIE_ENTRY_SIZE` bytes, the name pointer
first (`research/movies.md` § 1)."""
MOVIE_ENTRIES = 27
MOVIE_ENTRY_SIZE = 0x18
MOVIE_ENTRY_FRAMES = 12
"""Offset in an entry of `u32 frames`, the stop frame (`research/movies.md` § 1)."""
MOVIE_NAME_PREFIX = "\\__STR\\"
MOVIE_NAME_SUFFIX = ".IKI;1"
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
HEADER_SIZE = 12
MOVIE_ROW_SIZE = 8
CLIP_HEADER = struct.Struct("<HH")
"""The clips' {u16 count, u16 0}."""
CLIP_ROW = struct.Struct("<HH")
"""A clip's {u16 index, u16 words_offset}."""
CLIP_TRAILER = struct.Struct("<HH")
"""{u16 clips_offset, u16 0}, just before the glyph table."""
CLIP_HEADER_SIZE, CLIP_ROW_SIZE, CLIP_TRAILER_SIZE = (
    CLIP_HEADER.size,
    CLIP_ROW.size,
    CLIP_TRAILER.size,
)
GLYPHS_OFFSET_FIELD = 6
"""Where the header holds `glyphs_offset`; `clip_sub_play` finds the clips from it."""
END_OF_LINE = 0xFF
END_OF_LINES = 0xFFFF
U16_MAX = 0xFFFF
"""The largest value the block's count and offset fields hold."""
WHITE = (0xFF, 0xFF, 0xFF)
DARK = (0x18, 0x18, 0x14)
"""`g_text_flags & 4`'s shadow colour (`research/font.md` § The draw code)."""
LINE_WIDTH = SCREEN_WIDTH - 2
"""The widest line, in pixels of advance: the outline takes a column on either side."""
LINE_Y = (200, 200 + MASK)
"""The two lines' cell tops, a whole mask apart so no outline overlaps the line above.
Ink to row 225, outline to 226 -- inside DuckStation's ~232 visible rows
(`research/vwf-prototype.md` § Round 2) and clear of the 240-row frame."""
_BOTTOM_MARGIN = FRAME_HEIGHT - (LINE_Y[-1] - 1 + MASK)
"""Rows below the bottom position's last drawn row (its outline)."""
LINE_Y_TOP = (_BOTTOM_MARGIN + 1, _BOTTOM_MARGIN + 1 + MASK)
"""The two rows mirrored to the top of the frame: the first drawn row (a cell's row 0 is at
line y - 1) is as far from row 0 as the bottom position's last is from row 239."""
PANEL_PAD_X = 4
"""Pixels of panel either side of the widest line's advance (then rounded up to whole tiles).
Vertically the panel is the lines' own cells: each already has paper above the capitals and
below the descenders, and less than a whole tile row of pad would cost a whole row of tiles."""
POSITIONS = {"bottom": LINE_Y, "top": LINE_Y_TOP}
"""Where a cue may sit (`translation/README.md` § movies.txt): the name the cue file uses ->
the cell tops of its lines."""


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
    line_y: tuple[int, ...] = LINE_Y
    """Each line is centred on the screen with its cell top at `line_y[i]` (`POSITIONS`)."""
    panel: bool = False
    """Whether a dark panel is drawn behind the lines (FMV-06)."""


@dataclass(frozen=True)
class Masks:
    glyph: tuple[int, ...]
    outline: tuple[int, ...]


PANEL_MASKS = Masks((0,) * MASK, (0xFFFC,) * MASK)
"""The panel tile's record: no glyph, outline on every one of the 14 x 14 -- a `DARK` cell."""


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


def movie_names(exe: bytes) -> dict[str, int]:
    """Each movie file's stem (`M27`) -> the RAM address of its name string, read out of
    `g_movie_table` in the executable. Entries playing one file share one string (the
    opening's three ids do), so the key the loader matches is the file's, not the id's."""
    out: dict[str, int] = {}
    for entry in range(MOVIE_ENTRIES):
        at = MOVIE_TABLE + MOVIE_ENTRY_SIZE * entry - EXE_LOAD_BIAS
        (name,) = struct.unpack_from("<I", exe, at)
        start = name - EXE_LOAD_BIAS
        text = exe[start : exe.index(b"\0", start)].decode("ascii")
        if not (text.startswith(MOVIE_NAME_PREFIX) and text.endswith(MOVIE_NAME_SUFFIX)):
            raise BlockError(f"g_movie_table[{entry}] names {text!r}, not an .IKI under __STR")
        stem = text[len(MOVIE_NAME_PREFIX) : -len(MOVIE_NAME_SUFFIX)]
        if out.setdefault(stem, name) != name:
            raise BlockError(f"{stem} has two name strings, 0x{out[stem]:08X} and 0x{name:08X}")
    return out


def encode_block(
    movies: Mapping[int, Sequence[Cue]],
    font: Mapping[str, GlyphLike],
    clips: Mapping[int, Sequence[int]] | None = None,
) -> bytes:
    """The block for `movies` -- name pointer -> its cues -- carrying every glyph of `font`
    (the VWF set, so the size measured is the size the design pays). Refuses text the font
    cannot draw, a line wider than `LINE_WIDTH`, a line whose rows leave the frame, a block
    larger than its reserved sectors, and anything the count and offset fields cannot name
    -- every refusal a `BlockError`, so the build reports it as the input problem it is
    rather than letting a `struct.error` out."""
    characters = sorted(font)
    if len(characters) > END_OF_LINE:
        raise BlockError(f"{len(characters)} glyphs; a line's index byte reserves {END_OF_LINE:#x}")
    index = {c: i for i, c in enumerate(characters)}
    panel = len(characters) if any(c.panel for cues in movies.values() for c in cues) else None
    if panel == END_OF_LINE:
        raise BlockError(
            f"{len(characters)} glyphs leave the panel tile no index below {END_OF_LINE:#x}"
        )
    names = sorted(name for name, cues in movies.items() if cues)
    for name in names:
        if len(movies[name]) > U16_MAX:
            raise BlockError(f"{len(movies[name])} cues; the block counts a movie's in a u16")
    cues = [cue for name in names for cue in movies[name]]
    clip_rows = sorted((clips or {}).items())
    for clip, words in clip_rows:
        if not 0 <= clip <= U16_MAX:
            raise BlockError(f"clip {clip}: a clip row names its index in a u16")
        if not words or words[-1] != END_WORD:
            raise BlockError(f"clip {clip}'s words do not end with END ({END_WORD:#06x})")
    cues_start = HEADER_SIZE + MOVIE_ROW_SIZE * len(names)
    line_blobs: list[bytes] = []
    cue_rows: list[tuple[int, int, int]] = []
    cursor = cues_start + CUE_SIZE * len(cues)
    for cue in cues:
        if not 0 <= cue.start <= cue.end <= 0xFFFF:
            raise BlockError(f"cue frames {cue.start}..{cue.end} are not 0 <= start <= end < 65536")
        if len(cue.lines) > len(cue.line_y):
            raise BlockError(f"a cue holds at most {len(cue.line_y)} lines; {cue.lines!r} has more")
        text_lines = []
        widest = 0
        for text, y in zip(cue.lines, cue.line_y, strict=False):
            missing = unencodable_by(index.__contains__, text)
            if missing:
                raise BlockError(f"the font has no glyph for {''.join(missing)!r}")
            width = text_width(text, font)
            if width > LINE_WIDTH:
                raise BlockError(f"{text!r} is {width} px wide; a movie line holds {LINE_WIDTH}")
            if y < 1 or y + MASK - 1 > FRAME_HEIGHT:
                raise BlockError(f"line y {y} puts rows outside the {FRAME_HEIGHT}-row frame")
            widest = max(widest, width)
            text_lines.append(_line((SCREEN_WIDTH - width) // 2, y, [index[c] for c in text]))
        panel_lines = []
        if cue.panel:  # drawn first, so the text lands on it
            x, tiles = _panel_span(widest)
            panel_lines = [_line(x, y, [panel] * tiles) for y in cue.line_y[: len(text_lines)]]
        blob = b"".join(panel_lines + text_lines) + struct.pack("<HH", END_OF_LINES, 0)
        if cursor > U16_MAX:
            raise BlockError(
                f"a cue's lines start {cursor} bytes in; the cue row names it in a u16"
            )
        cue_rows.append((cue.start, cue.end, cursor))
        line_blobs.append(bytes(blob))
        cursor += len(blob)
    clip_offsets = []
    for _index, words in clip_rows:
        clip_offsets.append(cursor)
        line_blobs.append(struct.pack(f"<{len(words)}H", *words))
        cursor += 2 * len(words)
    clips_offset = cursor
    section = CLIP_HEADER.pack(len(clip_rows), 0) + b"".join(
        CLIP_ROW.pack(clip, offset)
        for (clip, _words), offset in zip(clip_rows, clip_offsets, strict=True)
    )
    cursor += len(section)
    glyphs_offset = ((cursor + 3) & ~3) + CLIP_TRAILER_SIZE
    if glyphs_offset > U16_MAX:
        raise BlockError(
            f"the glyph table would start {glyphs_offset} bytes in; the header names it in a u16"
        )
    out = bytearray(struct.pack("<IHHHH", MAGIC, 0, glyphs_offset, 0, len(names)))
    first = cues_start
    for name in names:
        out += struct.pack("<IHH", name, first, len(movies[name]))
        first += CUE_SIZE * len(movies[name])
    for start, end, offset in cue_rows:
        out += struct.pack("<HHHH", start, end, offset, 0)
    out += b"".join(line_blobs) + section
    out += bytes(glyphs_offset - CLIP_TRAILER_SIZE - len(out))
    out += CLIP_TRAILER.pack(clips_offset, 0)
    for c in characters:
        if not 0 <= font[c].advance <= 0xFF:
            raise BlockError(f"{c!r} advances {font[c].advance} px; a record holds it in a u8")
    records = [(font[c].advance, masks_of(font[c].rows)) for c in characters]
    if panel is not None:
        records.append((MASK, PANEL_MASKS))
    for advance, masks in records:
        record = struct.pack("<B3x", advance)
        record += struct.pack(f"<{MASK}H", *masks.glyph) + struct.pack(f"<{MASK}H", *masks.outline)
        out += record.ljust(RECORD_SIZE, b"\0")
    if form1_sectors(len(out)) > BLOCK_MAX_SECTORS:
        raise BlockError(
            f"the block is {len(out)} bytes, {form1_sectors(len(out))} sectors; its reserved "
            f"run holds {BLOCK_MAX_SECTORS} (boku.relocate.MOVIE_BLOCK_RESERVE)"
        )
    return bytes(out)


def _line(x: int, y: int, indices: Sequence[int]) -> bytes:
    """One line record, padded to an even length so the next header is halfword-aligned."""
    line = struct.pack("<HH", x, y) + bytes([*indices, END_OF_LINE])
    return line + bytes(len(line) % 2)


def _panel_span(width: int) -> tuple[int, int]:
    """`(pen x, tiles)` of a panel row behind lines whose widest is `width` px: `PANEL_PAD_X`
    either side, rounded up to whole tiles and centred, at most the tiles that span the frame
    (the last may run past column 319, which no slice holds, so the routine never draws it)."""
    tiles = min(-(-(width + 2 * PANEL_PAD_X) // MASK), -(-SCREEN_WIDTH // MASK))
    return max(0, (SCREEN_WIDTH - MASK * tiles) // 2) + 1, tiles


def clip_words(block: bytes, index: int) -> tuple[int, ...] | None:
    """The words `clip_sub_play` would open for `g_xa_clips` clip `index`, or `None`: the
    clips found through the trailer before the glyph table, as the routine finds them."""
    if struct.unpack_from("<I", block, 0)[0] != MAGIC:
        return None
    (glyphs,) = struct.unpack_from("<H", block, GLYPHS_OFFSET_FIELD)
    at, _ = CLIP_TRAILER.unpack_from(block, glyphs - CLIP_TRAILER_SIZE)
    count, _ = CLIP_HEADER.unpack_from(block, at)
    for row in range(count):
        key, offset = CLIP_ROW.unpack_from(block, at + CLIP_HEADER_SIZE + CLIP_ROW_SIZE * row)
        if key == index:
            end = next(t.end for t in iter_tokens(block[offset:glyphs]) if t.word == END_WORD)
            return tuple(words_of(block[offset : offset + end]))
    return None


def clip_count(block: bytes) -> int:
    """How many clips the block carries subtitles for; 0 for no block."""
    if len(block) < HEADER_SIZE or struct.unpack_from("<I", block, 0)[0] != MAGIC:
        return 0
    (glyphs,) = struct.unpack_from("<H", block, GLYPHS_OFFSET_FIELD)
    at, _ = CLIP_TRAILER.unpack_from(block, glyphs - CLIP_TRAILER_SIZE)
    return CLIP_HEADER.unpack_from(block, at)[0]


# --- the reference loader and rasteriser ---------------------------------------------------


def select(block: bytes, name: int) -> bytes:
    """The block as `movie_sub_load` leaves it in RAM for the movie named `name`: the
    matching row's `cues_offset` and `cue_count` copied to +8 and +4, or a count of 0 when
    no row matches. Decoded from the bytes, as `render` is."""
    out = bytearray(block)
    if struct.unpack_from("<I", out, 0)[0] != MAGIC:
        return bytes(out)
    struct.pack_into("<H", out, 4, 0)
    (count,) = struct.unpack_from("<H", out, 10)
    for row in range(count):
        key, offset, cues = struct.unpack_from("<IHH", out, HEADER_SIZE + MOVIE_ROW_SIZE * row)
        if key == name:
            struct.pack_into("<H", out, 8, offset)
            struct.pack_into("<H", out, 4, cues)
            break
    return bytes(out)


def render(
    block: bytes, frame: int, x_range: range = range(SCREEN_WIDTH)
) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Every pixel the routine writes for `frame` whose x is in `x_range`, in draw order.

    `block` is the block as it is in RAM once a movie has started -- `select`'s output --
    because the routine draws the cues its +4 and +8 name. Decoded from the block's
    *bytes*, not from the objects that made them, so it holds the format to the routine as
    written; `x_range` is a slice's 16 columns when the test is about clipping, the whole
    width when it is about a frame.
    """
    magic, cue_count, glyphs_offset, cues_offset = struct.unpack_from("<IHHH", block, 0)
    if magic != MAGIC:
        return {}
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
    for n in range(cue_count):
        row = cues_offset + CUE_SIZE * n
        start, end, lines_offset, _ = struct.unpack_from("<HHHH", block, row)
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
