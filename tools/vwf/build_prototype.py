"""`TXT-05` prototype: proportional horizontal dialogue, built into a copy of your image.

    uv run python tools/vwf/build_prototype.py            # -> build/vwf/image.cue
    uv run python tools/vwf/build_prototype.py --edits-only   # -> build/vwf/edits.json

What it does, in order, refusing before the 660 MB copy if anything is off:

1. Reads `disc/files/SCPS_100.88` and `disc/files/BOKU.BIN` (read-only) and the font sheet,
   `ONMEM.BIN` pack child 2 (`research/font.md`).
2. Picks a cell for every English character (`allocate_cells`). A character whose own cell
   no Japanese text uses is left-aligned where it is; every other one -- and every glyph
   the sheet lacks -- goes to a free cell. No cell the Japanese script draws changes by a
   pixel, and its advance stays the stock 14.
3. Rebuilds the sheet and the advance table from the same glyphs, assembles
   `asm/dialogue.asm` twice (first with `ORIGINAL=1`, which must reproduce the retail
   executable byte for byte -- that is the check on every "stock:" comment in the source),
   and encodes the lines of `prototype-lines.tsv` against each site's size and page count.
4. Writes `edits.json` -- the renderer patch as a machine-readable edit set: every
   `(file, offset, old bytes, new bytes)` run it would write into `SCPS_100.88` and
   `BOKU.BIN` (the executable's words and free-space table, the rebuilt overlays, the
   rebuilt font sheet, and -- under `--cursor right` -- the UI sheet the select's hand is
   turned on and the sprite record that gives its new size), plus the character map and
   the width table. **That file is the whole interface to `boku build`**, which applies it
   as verified `ByteEdit`s beside a translation that may *grow* (`PIPE-03`/`PIPE-04`) --
   the thing this script, writing in place, cannot do. `--edits-only` stops here and never
   copies the image.
5. Copies the image, checks that every range it is about to replace holds the bytes
   `disc/files` says it does, writes through `boku.disc.DiscWriter` (fresh EDC/ECC), and
   emits `manifest.json`: every sector, every executable word, the character map.

The typeface is an input (`--font`), because `PLAN TXT-06` is open. With no `--font` the
glyphs are the game's own Latin cells from the contributor's disc plus the placeholder
punctuation in `placeholder-glyphs.txt`. The rebuilt sheet is disc-derived: it lives under
`build/` and is never tracked.

`--days translation/days` takes the English from the reviewed day files instead of the
sample lines (`boku.translation.SampleScenes`, the provisional reader both share): every
message and select whose id the import knows is laid out and written in place; a line that
does not fit its site, or has the wrong page or option count, is left Japanese and listed
in the summary and in `manifest.json` -> `unfitted` -- never cut, never silently dropped.
The `--lines` fixtures then only fill sites the day files do not cover (the array items).

Standard library only. `boku` is imported read-only for the disc writer, the EDC check and
the text-site index; nothing under `boku/` is modified by or for this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from boku import edc  # noqa: E402
from boku.archive import ARCHIVE_NAME, EXE_NAME, Archive, parse_pack  # noqa: E402
from boku.build import verify_sectors  # noqa: E402
from boku.disc import DiscError, DiscImage, DiscWriter, SectorWrite, form1_sectors  # noqa: E402
from boku.glyphs import END_WORD, NEWLINE_WORD, PAGE_WORD, words_of  # noqa: E402
from boku.importer import IMAGE_SHA1, sha1_of  # noqa: E402
from boku.movie_block import (  # noqa: E402
    BLOCK_LBA,
    BLOCK_RAM,
    CELL,
    MAGIC,
    MASK,
    RECORD_SIZE,
    SCREEN_WIDTH,
    BlockError,
    Cue,
    encode_block,
)
from boku.ppf import differing_spans  # noqa: E402
from boku.reinsert import MAP_WORK_AREA_END  # noqa: E402
from boku.relocate import PREFIX_FILLER, Run, SectorEdit, padded  # noqa: E402
from boku.sites import line_key_of, page_waits  # noqa: E402
from boku.text import PlacedSite, SiteIndex, TextError  # noqa: E402
from boku.tim import parse_exact  # noqa: E402
from boku.translation import SampleScenes  # noqa: E402

HERE = Path(__file__).resolve().parent
ASM = REPO / "asm/vwf.asm"
GLYPH_TSV = REPO / "research/data/glyph-table.tsv"
FONT_CANDIDATES = REPO / "research/font-candidates.md"
SAMPLES = REPO / "translation/samples"
DAYS = REPO / "translation/days"
PLACEHOLDERS = HERE / "placeholder-glyphs.txt"
DEFAULT_LINES = HERE / "prototype-lines.tsv"
DEFAULT_ARMIPS = Path.home() / "Dev/dist/armips/build/armips"

EXE_LOAD_BIAS = 0x8000F800
EXE_HEADER = 0x800
"""The PS-X EXE header; the code starts after it (RAM 0x80010000)."""
OVERLAY_BASE = 0x80079A08
"""Where every `.OVL` loads (`research/text-renderer.md` § 3)."""
GLYPH_DRAW = 0x8002BA2C
GLYPH_DRAW_LAYER = 0x8002B9FC
DRAWING_OVERLAYS = ("TITLE.OVL", "TAKO.OVL", "MUSI.OVL", "HHON.OVL")
"""The overlays with `glyph_draw` call sites (`research/text-outside-events.md`)."""
SYSMSG_REMAP = {13: 14}
"""`sysmsg_draw` draws id 13 as 14 (`research/text-outside-events.md` § Readers)."""
FONT_MEMBER = "ONMEM.BIN"
FONT_CHILD = 2
SHEET_COLUMNS = 21
SHEET_PLANES = 4
SHEET_SLOTS = 1512

PAGE_BREAK = " // "
"""How `translation/samples/` writes a page boundary."""

EDITS_NAME = "edits.json"
"""The edit set `boku build --vwf` reads (`boku.build.load_edit_set` is its one reader)."""

MOVIE_BLOCK_NAME = "movie-subtitles.bin"
"""The cue block `asm/movie.asm` reads at every movie (`boku.movie_block`), written under
`files/` and into the image's filler sectors at `BLOCK_LBA`.

**The block and the hooks go into this script's own image and into no `edits.json`.** The
block belongs to no file, so an edit set cannot carry it, and `BLOCK_LBA` is inside the
relocation arena `boku.relocate` hands out (`research/relocation.md`): a `--vwf` image with
the hooks and no block would read whatever the allocator had left there at every movie.
What keeps them out is that the exported executable is a pass of its own, assembled with
`MOVIE_SUBTITLES=0` so that `asm/movie.asm` is never included -- the edit set is cut from
an executable the hooks were never in, rather than from one they were taken back out of.
`PLAN FMV-04` milestone 2 gives the block a carrier, and the hooks travel with it."""
MOVIE_CUE = Cue(
    120,
    300,
    ("Far away, I could see the village", "of Sagi-no-sato at the foot of the mountain..."),
)
"""`FMV-04` milestone 1's one hard-coded cue, aimed at the opening (`M27`, id 23) at STR
frames 120-300 (8-20 s). The block carries no movie key and `movie_sub_blit` asks only
`start <= frame <= end`, so this cue is drawn over **every** movie whose frame numbers reach
120, not the opening alone (`research/movies.md` § 7 counts them); the per-movie key is
milestone 2. The words are a placeholder -- the game's own first narration line, `E0001.0`
in `translation/days/day01.txt` -- not the monologue's translation, which does not exist
yet; the proof is that the pixels land, not what they say."""


class BuildRefused(Exception):
    """The build will not proceed; `image.img` under `--out` is as it was."""


CURSOR_WIDTH = {"right": 24, "down": 16}
"""How wide the select's hand is under each `--cursor` mode: the stock `ONMEM.BIN` sprite
is 16 x 24 and `cursor_edits` turns it to 24 x 16."""
CURSOR_GAP = 2
"""Pixels between the hand's right edge and the option's first glyph. Both offsets Jay ran
are the hand's own width plus this (-26 turned, -18 stock; `research/vwf-prototype.md`
§ Round 2), so the offset follows the sprite rather than being set beside it."""
CURSOR_DX = {mode: -(width + CURSOR_GAP) for mode, width in CURSOR_WIDTH.items()}
"""`sel_cursor_dx` per `--cursor` mode, for a command line that gives none."""


@dataclass(frozen=True)
class Layout:
    """Everything `PLAN TXT-03` leaves to Jay, as build inputs with the trial's defaults."""

    pen_x: int = 24
    pen_y: int = 193
    line_pitch: int = 11
    band_y: int = 191
    band_h: int = 37
    band_brightness: int = 168
    band_blend: int = 2
    """`g_dlgbox_fade[6]`, the level the band sits at while a message is up: stock is
    (224, 1), opaque; (168, 2) is entry 5, additive over the scene -- the translucent look
    Jay chose (2026-09-20; research/renderer-runtime.md § Q2 item 4)."""
    map_area_extra: int = 0x1800
    """Bytes added to the engine's `0x6400` map work area. It costs twice itself from the
    gap between the fixed arena's end and the stack; `asm/arena.asm` holds the guard that
    refuses a raise the measured stack depth cannot afford, and
    research/vwf-prototype.md § "The map work area" the measurement."""
    advance_model: str = "c2"
    """`c2` (the default): each glyph re-aligned to column 0, advance = ink width plus the
    gap. `c1`: the glyph stays at its native bearing and the advance is the ink's right
    edge plus the gap. Jay ranked c1 above c2 on looks and gave lint the casting vote
    (2026-09-20); under the ruled three-line band c1 needs a fourth line on far more pages
    than c2 does, so c2 is what the build installs (`PLAN TXT-07` for both counts)."""
    cursor: str = "right"
    """`right`: the select's hand sprite is rotated at build time to point at its row
    (`cursor_edits`; 24 x 16); `down`: the stock 16 x 24 hand, which pointed at a column,
    is left alone. The hand's width is what `sel_cursor_dx` is measured from, so the two
    move together -- `CURSOR_DX`."""
    sel_x: int = 48
    sel_y: int = 126
    sel_pitch: int = 11
    sel_pad: int = 6
    sel_cursor_dx: int | None = None
    """How far left of the option row the hand is drawn. `None` (the default) takes
    `CURSOR_DX[cursor]`, so `--cursor down` alone does not leave the narrower stock hand
    at the turned one's offset; an explicit `--sel-cursor-dx` still wins."""
    sel_cursor_dy: int = -2
    fixed_advance: int = 14
    gap: int = 1
    """Pixels between one glyph's ink and the next, for glyphs measured from their ink."""

    ARMIPS_EQUATES = (
        "pen_x",
        "pen_y",
        "line_pitch",
        "band_y",
        "band_h",
        "sel_x",
        "sel_y",
        "sel_pitch",
        "sel_pad",
        "sel_cursor_dx",
        "sel_cursor_dy",
        "fixed_advance",
        "band_brightness",
        "band_blend",
        "map_area_extra",
    )
    """Fields `asm/vwf.asm` takes as `-equ NAME`, upper-cased."""

    def __post_init__(self) -> None:
        if self.advance_model not in ("c1", "c2"):
            raise BuildRefused(f"--advance-model is c1 or c2, not {self.advance_model!r}")
        if self.cursor not in CURSOR_DX:
            raise BuildRefused(f"--cursor is right or down, not {self.cursor!r}")
        if self.sel_cursor_dx is None:
            object.__setattr__(self, "sel_cursor_dx", CURSOR_DX[self.cursor])
        if self.sel_cursor_dx > 0:
            raise BuildRefused("--sel-cursor-dx must be <= 0: the box's corner is measured from it")
        if self.map_area_extra < 0 or self.map_area_extra % 4:
            raise BuildRefused("--map-area-extra is a non-negative multiple of 4 (a word count)")

    @property
    def map_work_area_end(self) -> int:
        """Where a map pack's children 0-5 must end under the patched engine."""
        return MAP_WORK_AREA_END + self.map_area_extra

    @property
    def wrap_width(self) -> int:
        """The pen's left margin mirrored on the right."""
        return SCREEN_WIDTH - 2 * self.pen_x

    @property
    def select_width(self) -> int:
        """What an option row may take: from the row's origin to the pen's right margin."""
        return SCREEN_WIDTH - self.pen_x - self.sel_x


# --- glyphs ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Glyph:
    """Twelve rows of twelve 1-bit cells (bit 11 = column 0), and the pen advance."""

    rows: tuple[int, ...]
    advance: int

    @property
    def ink(self) -> tuple[int, int] | None:
        """(leftmost, rightmost) inked column, or None for a blank cell."""
        mask = 0
        for row in self.rows:
            mask |= row
        if not mask:
            return None
        return CELL - mask.bit_length(), CELL - 1 - ((mask & -mask).bit_length() - 1)


SHADOW_GAP = 2
"""Least advance past a glyph's rightmost inked column: one for the drop shadow the
renderer draws at x + 1, one so the next glyph does not sit on it."""


def load_glyph_file(path: Path) -> dict[str, Glyph]:
    """Parse the `glyph U+XXXX advance N` + 12 rows format `placeholder-glyphs.txt` documents."""
    glyphs: dict[str, Glyph] = {}
    lines = [
        line.rstrip("\n")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and line != "#" and not line.startswith("# ")
    ]
    position = 0
    while position < len(lines):
        match = re.fullmatch(r"glyph U\+([0-9A-Fa-f]{4,6}) advance (\d+)", lines[position])
        if not match:
            raise BuildRefused(f"{path}: expected a `glyph` header, found {lines[position]!r}")
        rows = lines[position + 1 : position + 1 + CELL]
        if len(rows) != CELL or any(not re.fullmatch(r"[.#]{12}", row) for row in rows):
            raise BuildRefused(f"{path}: {match.group(0)} is not followed by twelve 12-cell rows")
        character = chr(int(match.group(1), 16))
        glyph = Glyph(
            tuple(int(row.replace(".", "0").replace("#", "1"), 2) for row in rows),
            int(match.group(2)),
        )
        ink = glyph.ink
        if ink and glyph.advance < ink[1] + SHADOW_GAP:
            # The renderer has no bearing of its own: a glyph's left bearing is paper
            # inside its cell, and every glyph is drawn twice, the second copy one column
            # right of the first (the drop shadow). So the ink's shadow lands on column
            # `ink + 1` and the next glyph may not start before `ink + 2`. Both game_font
            # models hit that bound exactly (ink's right edge + 1 + `gap`).
            raise BuildRefused(
                f"{path}: {match.group(0)} has ink to column {ink[1]} but advances only "
                f"{glyph.advance}; the advance must cover the ink and its shadow "
                f"({ink[1] + SHADOW_GAP} at least)"
            )
        glyphs[character] = glyph
        position += 1 + CELL
    return glyphs


class Sheet:
    """The font TIM's pixel block: four 1-bit planes of 12x12 cells in one 4bpp image."""

    def __init__(self, tim: bytes) -> None:
        magic, flags, clut_length = struct.unpack_from("<III", tim)
        if magic != 0x10 or flags != 8:
            raise BuildRefused(f"font child is not a 4bpp TIM with a CLUT ({magic:#x}, {flags})")
        block = 8 + clut_length
        _, _, _, words_wide, height = struct.unpack_from("<IHHHH", tim, block)
        self.stride = words_wide * 2
        self.start = block + 12
        slots = (height // CELL) * SHEET_COLUMNS * SHEET_PLANES
        if self.stride * 2 != SHEET_COLUMNS * CELL or slots < SHEET_SLOTS:
            raise BuildRefused(f"font TIM is {self.stride * 2}x{height}, not the 252-wide sheet")
        self.data = bytearray(tim)

    def _nibble(self, glyph_id: int, x: int, y: int) -> tuple[int, int, int]:
        column = glyph_id % SHEET_COLUMNS
        plane = (glyph_id // SHEET_COLUMNS) % SHEET_PLANES
        row = glyph_id // (SHEET_COLUMNS * SHEET_PLANES)
        px, py = column * CELL + x, row * CELL + y
        return self.start + py * self.stride + px // 2, 4 * (px & 1), plane

    def get(self, glyph_id: int) -> tuple[int, ...]:
        rows = []
        for y in range(CELL):
            value = 0
            for x in range(CELL):
                offset, shift, plane = self._nibble(glyph_id, x, y)
                value = (value << 1) | ((self.data[offset] >> (shift + plane)) & 1)
            rows.append(value)
        return tuple(rows)

    def put(self, glyph_id: int, rows: tuple[int, ...]) -> None:
        for y in range(CELL):
            for x in range(CELL):
                offset, shift, plane = self._nibble(glyph_id, x, y)
                bit = 1 << (shift + plane)
                if (rows[y] >> (CELL - 1 - x)) & 1:
                    self.data[offset] |= bit
                else:
                    self.data[offset] &= ~bit & 0xFF


def native_ids() -> dict[str, int]:
    """ASCII character -> the sheet cell that draws it, by NFKC of `glyph-table.tsv`.

    Cells the table's notes call vertical-writing forms are left out: they are rotated or
    sit top-right and are wrong in a horizontal line (`research/font.md`).
    """
    mapping: dict[str, int] = {}
    with GLYPH_TSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if not row["character"] or "vertical" in row["notes"]:
                continue
            plain = unicodedata.normalize("NFKC", row["character"])
            if len(plain) == 1 and 0x20 < ord(plain) < 0x7F:
                mapping.setdefault(plain, int(row["index"]))
    return mapping


NARROW_INK = 2
"""Ink this wide or narrower gets one more pixel of advance, so that its shadow (the copy
at x + 1) does not bridge the gap to a repeat of itself: `...` read as a dash at ink + gap
(`research/vwf-prototype.md` § "What the screenshots show")."""


def game_font(sheet: Sheet, layout: Layout) -> dict[str, Glyph]:
    """The game's own Latin glyphs under `layout.advance_model`.

    `c1` keeps every cell's pixels where the sheet has them and advances the pen past the
    ink's right edge plus the gap, so a glyph is drawn at its native bearing and nothing
    on the sheet changes; `c2` shifts the ink to column 0 and advances by its width plus
    the gap. Under either, a glyph of `NARROW_INK` or less advances one more, for the
    shadow's sake.
    """
    glyphs = {}
    for character, glyph_id in native_ids().items():
        rows = sheet.get(glyph_id)
        ink = Glyph(rows, 0).ink
        if ink is None:
            continue
        left, right = ink
        width = right - left + 1
        narrow = 1 if width <= NARROW_INK else 0
        if layout.advance_model == "c1":
            glyphs[character] = Glyph(rows, right + 1 + layout.gap + narrow)
        else:
            glyphs[character] = Glyph(
                tuple((row << left) & 0xFFF for row in rows), width + layout.gap + narrow
            )
    return glyphs


def free_cells() -> list[int]:
    """Glyph ids nothing in the game draws, read from `research/font-candidates.md` § 1.

    That section is the one home of the structural recount; it is parsed here rather than
    copied, and the count it states is checked against the list it gives.
    """
    text = FONT_CANDIDATES.read_text(encoding="utf-8")
    listed = re.search(r"\* Free ids: `([0-9\s-]+)`", text)
    stated = re.search(r"\*\*Free: (\d+) of", text)
    if not listed or not stated:
        raise BuildRefused(f"{FONT_CANDIDATES} no longer carries the free-id list this reads")
    ids: list[int] = []
    for token in listed.group(1).split():
        first, _, last = token.partition("-")
        ids.extend(range(int(first), int(last or first) + 1))
    if len(ids) != int(stated.group(1)):
        raise BuildRefused(
            f"{FONT_CANDIDATES} says {stated.group(1)} ids are free and lists {len(ids)}"
        )
    return ids


def allocate_cells(font: dict[str, Glyph], untouched: set[str] = frozenset()) -> dict[str, int]:
    """Character -> glyph id, touching only cells the Japanese script never draws.

    A character keeps its native cell when that cell is free, or when `untouched` says
    its pixels are the sheet's own (the `c1` model draws nothing there); otherwise it takes
    the lowest free cell no character is keeping, so the advance table stays as short as
    it can.
    """
    free = free_cells()
    native = native_ids()
    cells = {c: native[c] for c in font if native.get(c) in free or c in untouched}
    kept = set(cells.values())
    spare = (i for i in free if i not in kept)
    for character in sorted(font):
        if character not in cells:
            try:
                cells[character] = next(spare)
            except StopIteration:
                raise BuildRefused("the sheet has no free cell left for this font") from None
    return cells


def place_font(
    sheet: Sheet, layout: Layout, font: dict[str, Glyph], drawn: set[int]
) -> tuple[dict[str, int], bytearray, dict[str, int]]:
    """`(character -> cell, the advance table, the cells to redraw)` for one font.

    `drawn` is every cell the Japanese script on this disc draws, and it is what keeps the
    two halves of a cell honest. A character may keep its native cell only if this font
    draws the pixels already there **and** nothing on the disc draws that cell: the sheet
    and the advance table are both indexed by cell id and both are read for Japanese and
    English alike, so a kept cell hands a Japanese page either new pixels or a new width.
    Everything else is copied into a cell the script never draws.
    """
    native = native_ids()
    untouched = {
        c
        for c in font
        if c in native and font[c].rows == sheet.get(native[c]) and native[c] not in drawn
    }
    cells = allocate_cells(font, untouched)
    # Only a cell whose pixels change is written, and only such a cell can clash.
    redrawn = {c: glyph_id for c, glyph_id in cells.items() if c not in untouched}
    clash = sorted(drawn & set(redrawn.values()))
    if clash:
        raise BuildRefused(
            f"cells {clash} were about to be redrawn, and text on this disc draws them; "
            f"the free-id list in {FONT_CANDIDATES.name} is wrong for this image"
        )
    table = bytearray([layout.fixed_advance]) * (max(cells.values()) + 1)
    for character, glyph_id in cells.items():
        table[glyph_id] = font[character].advance
    narrowed = narrowed_cells(table, cells, drawn, layout.fixed_advance)
    if narrowed:
        raise BuildRefused(
            "the advance table would change the width of "
            + ", ".join(f"{glyph_id} ({character!r})" for glyph_id, character in narrowed)
            + " -- cells the Japanese script still draws, which would then be drawn at "
            "English widths and overlap. Those characters need free cells of their own."
        )
    return cells, table, redrawn


def narrowed_cells(
    table: Sequence[int], cells: dict[str, int], drawn: set[int], fixed_advance: int
) -> list[tuple[int, str]]:
    """`(cell, character)` for every cell `drawn` whose advance this font would change.

    The advance table is one array indexed by cell id, and the hooked renderer reads it
    for Japanese and English alike. So a cell that the script still draws and that this
    font gives an English advance is a Japanese page drawn at English widths -- glyphs
    overlapping, with no other symptom and every other gate green. The sibling of the two
    pixel clash checks in `build`, for the other half of what a cell carries.
    """
    by_id = {glyph_id: character for character, glyph_id in cells.items()}
    return sorted(
        (glyph_id, by_id.get(glyph_id, ""))
        for glyph_id in drawn
        if glyph_id < len(table) and table[glyph_id] != fixed_advance
    )


# --- text -----------------------------------------------------------------------------


@dataclass(frozen=True)
class LineSpec:
    site_id: str
    source: str
    label: bool
    wrap: bool
    text: str


def load_samples() -> dict[str, tuple[str, str]]:
    """Line id -> (speaker, English) from `translation/days/` and `translation/samples/`.

    The sample scenes moved into the day files as the translation grew; a `source` in
    `prototype-lines.tsv` may name a line from either."""
    samples = {}
    for path in sorted([*DAYS.glob("*.txt"), *SAMPLES.glob("*.txt")]):
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and re.fullmatch(r"E\d{4}\.\d+", parts[0]):
                samples[parts[0]] = (parts[1], parts[2])
    return samples


def load_lines(path: Path) -> list[LineSpec]:
    samples = load_samples()
    specs = []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader((r for r in handle if not r.startswith("#")), delimiter="\t")
        for row in rows:
            label = row["label"] == "yes"
            if row["source"] == "fixture":
                text = row["text"].replace("\\n", "\n")
            elif row["source"] in samples:
                speaker, text = samples[row["source"]]
                text = f"{speaker}: {text}" if label else text
            else:
                raise BuildRefused(
                    f"{path}: {row['source']} is not in translation/days/ or translation/samples/"
                )
            specs.append(LineSpec(row["site"], row["source"], label, row["wrap"] == "yes", text))
    return specs


UNLABELLED = ("Narrator", "(unlabelled)")
"""Speakers `--label` never prefixes: narration and the examine descriptions."""


def load_days(directory: Path, label: bool) -> tuple[list[LineSpec], tuple[str, ...]]:
    """Every line of `translation/days/*.txt` as a spec, and the reader's complaints.

    A select's options (a prompt first, where the layout has one — `shared.txt`'s rule)
    become one option per line; a message keeps its ` // ` pages and is wrapped. The
    speaker goes in front of the text only with `label`, the inline "Boku: " form the
    prototype has used so far (the label's design is still open).
    """
    source = SampleScenes.from_directory(directory)
    specs = []
    for entry in source:
        if entry.is_select:
            text = "\n".join((*entry.prompts, *entry.options))
        else:
            text = PAGE_BREAK.join(entry.pages)
            if label and entry.speaker not in UNLABELLED:
                text = f"{entry.speaker}: {text}"
        specs.append(LineSpec(entry.line_id, entry.origin, label, not entry.is_select, text))
    return specs, source.problems


def wrap_page(page: str, font: dict[str, Glyph], width: int) -> str:
    """Greedy wrap at spaces. The engine has no wrap logic, so the line breaks are data."""

    def measure(run: str) -> int:
        return sum(font[c].advance for c in run)

    out = []
    for paragraph in page.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if line and measure(candidate) > width:
                out.append(line)
                line = word
            else:
                line = candidate
        out.append(line)
    return "\n".join(out)


def encode_message(
    spec: LineSpec, raw: bytes, font: dict[str, Glyph], cells: dict[str, int], layout: Layout
) -> tuple[bytes, list[str]]:
    """The site's replacement bytes and the pages as laid out. Refuses; never cuts.

    The only limits enforced here are the page count, the font's coverage and the site's
    byte length. **The band's shape is not one of them**: the wrap uses `layout.wrap_width`
    for every line, so neither the three-line box nor the 238 px the next-page pencil
    leaves line 3 is charged. `boku.layout` and `boku lint` are where a page too tall or a
    guarded line too wide is reported (`DIALOGUE_BAND`); a page this function accepts may
    still be one the band cannot draw.
    """
    pages = spec.text.split(PAGE_BREAK)
    waits = page_waits(raw)
    if len(pages) != len(waits) + 1:
        raise BuildRefused(
            f"{spec.site_id}: the original has {len(waits) + 1} pages and the English "
            f"{len(pages)}; pages turn on the voice clip's timers, so the count is fixed"
        )
    missing = sorted({c for c in spec.text if c != "\n" and c not in cells})
    if missing:
        raise BuildRefused(f"{spec.site_id}: the font has no glyph for {''.join(missing)!r}")
    if spec.wrap:
        pages = [wrap_page(page, font, layout.wrap_width) for page in pages]
    words: list[int] = []
    for number, page in enumerate(pages):
        if number:
            words += [PAGE_WORD, waits[number - 1]]
        words += [NEWLINE_WORD if c == "\n" else cells[c] for c in page]
    words.append(END_WORD)
    if 2 * len(words) > len(raw):
        raise BuildRefused(
            f"{spec.site_id}: {spec.text!r} needs {2 * len(words)} bytes and the site holds "
            f"{len(raw)}; this prototype writes in place and nothing is cut to fit"
        )
    words += [0] * (len(raw) // 2 - len(words))
    return struct.pack(f"<{len(words)}H", *words), pages


def encode_select(
    spec: LineSpec, raw: bytes, font: dict[str, Glyph], cells: dict[str, int], layout: Layout
) -> tuple[bytes, list[str]]:
    """A SELECT site's replacement bytes: one option per line, each ended by `0x8001`.

    The line count is the reader's (`g_select_lines[layout]`), which the stock bytes show
    as their count of `0x8001`; a prompt line, where the layout has one, is a line too.
    """
    options = spec.text.split("\n")
    stock_lines = words_of(raw).count(NEWLINE_WORD)
    if len(options) != stock_lines:
        raise BuildRefused(
            f"{spec.site_id}: the layout draws {stock_lines} lines and the English has "
            f"{len(options)}; select_draw reads the count from g_select_lines, not the text"
        )
    missing = sorted({c for c in spec.text if c != "\n" and c not in cells})
    if missing:
        raise BuildRefused(f"{spec.site_id}: the font has no glyph for {''.join(missing)!r}")
    wide = [o for o in options if sum(font[c].advance for c in o) > layout.select_width]
    if wide:
        raise BuildRefused(
            f"{spec.site_id}: {wide[0]!r} is wider than the {layout.select_width} px a row "
            f"has; the engine clips at the screen edge and the box is measured from the text"
        )
    words: list[int] = []
    for option in options:
        words += [cells[c] for c in option] + [NEWLINE_WORD]
    if 2 * len(words) > len(raw):
        raise BuildRefused(
            f"{spec.site_id}: {spec.text!r} needs {2 * len(words)} bytes and the site holds "
            f"{len(raw)}; this prototype writes in place and nothing is cut to fit"
        )
    words += [0] * (len(raw) // 2 - len(words))
    return struct.pack(f"<{len(words)}H", *words), options


def check_placement(entry: PlacedSite, raw: bytes) -> None:
    """Raise unless `raw` (the bytes at the site in `disc/files`) hash to the walk's key.

    `boku.text.check_placement` did this until `boku.build.verify_edits` took over whole
    byte ranges; the prototype keeps the per-site form because it writes sites in place.
    """
    if len(raw) != entry.site.size or line_key_of(raw) != entry.line_key:
        raise TextError(
            f"{entry.line_id}: {entry.file_name}+0x{entry.file_offset:x} does not hold what "
            f"the walk read there ({len(raw)} bytes, key {line_key_of(raw)} vs "
            f"{entry.line_key}); nothing was written"
        )


def encode_array_item(
    spec: LineSpec, raw: bytes, font: dict[str, Glyph], cells: dict[str, int], layout: Layout
) -> tuple[bytes, list[str]]:
    """One item of a text array: its glyphs, then the terminator the stock item ends with
    (`0x8001` in an L array, `0x8000` in an E array; `research/text-outside-events.md`).

    The next item starts right after the terminator and the readers count terminators to
    find item n, so the item keeps its word count: spare words are English spaces before
    the terminator, not zeros after it (id 0 is the 14-px Japanese space, and drawn).
    """
    if "\n" in spec.text or PAGE_BREAK in spec.text:
        raise BuildRefused(f"{spec.site_id}: an array item is one line")
    missing = sorted({c for c in spec.text if c not in cells})
    if missing:
        raise BuildRefused(f"{spec.site_id}: the font has no glyph for {''.join(missing)!r}")
    spare = len(raw) // 2 - 1 - len(spec.text)
    if spare < 0:
        raise BuildRefused(
            f"{spec.site_id}: {spec.text!r} needs {2 * (len(spec.text) + 1)} bytes and the "
            f"site holds {len(raw)}; this prototype writes in place and nothing is cut to fit"
        )
    words = [cells[c] for c in spec.text] + [cells[" "]] * spare + [words_of(raw)[-1]]
    return struct.pack(f"<{len(words)}H", *words), [spec.text]


def glyph_ids_in(raw: bytes) -> set[int]:
    """Glyph ids a site draws: every word below 0x8000 that is not a `0x8002` operand."""
    words = words_of(raw)
    ids = set()
    skip = False
    for word in words:
        if skip:
            skip = False
        elif word == PAGE_WORD:
            skip = True
        elif word < 0x8000:
            ids.add(word)
    return ids


def _a0_immediate(words: list[int], site: int) -> tuple[int, int] | None:
    """The `(base, count)` of ids a `jal glyph_draw` at `words[site]` passes in `a0`.

    Reads the delay slot and up to eight instructions back for the last write to `a0`:
    `addiu/ori a0,zero,imm` is the one id `imm`; `addiu a0,rs,imm` with a live `rs` is the
    digit pattern `0x34 + d` (`research/text-outside-events.md` § "Text made at run time"),
    ten ids from `imm`. Any other write (a load, a move) is an array walk, which the site
    index already covers, and returns None. Mirrors `work/rec04/direct_ids.py`, which
    `research/font.md` § "The draw code" was read from.
    """
    for j in [site + 1, *range(site - 1, max(site - 9, -1), -1)]:
        word = words[j]
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        if op in (9, 13) and rt == 4:  # addiu / ori, rt = a0
            imm = word & 0xFFFF
            return (imm, 1) if rs == 0 else (imm, 10)
        if op == 0 and (word >> 11) & 31 == 4 and j != site + 1:  # R-type writing a0
            return None
        if op in (0x20, 0x21, 0x23, 0x24, 0x25) and rt == 4:  # a load into a0
            return None
    return None


def code_glyph_ids(archive: Archive) -> set[int]:
    """Glyph ids the code passes to `glyph_draw` without reading them from text.

    Derived from the binaries, not retyped: every `jal glyph_draw` / `glyph_draw_layer` in
    the executable and the four drawing overlays is resolved by `_a0_immediate`. Plus the
    remap `sysmsg_draw` applies. This is the set the free-cell list of
    `research/font-candidates.md` § 1 promises to exclude and the text-site gate cannot see.
    """
    images = [(archive.exe[EXE_HEADER:], EXE_LOAD_BIAS + EXE_HEADER)]
    for name in DRAWING_OVERLAYS:
        images.append((archive.blob(archive.member(name)), OVERLAY_BASE))
    calls = {0x0C000000 | ((target >> 2) & 0x3FFFFFF) for target in (GLYPH_DRAW, GLYPH_DRAW_LAYER)}
    ids: set[int] = set(SYSMSG_REMAP) | set(SYSMSG_REMAP.values())
    for data, _ in images:
        count = len(data) // 4
        words = list(struct.unpack_from(f"<{count}I", data))
        for site, word in enumerate(words):
            if word in calls and site + 1 < count:
                found = _a0_immediate(words, site)
                if found:
                    ids.update(range(found[0], found[0] + found[1]))
    return ids


# --- assembling -----------------------------------------------------------------------


def run_armips(
    armips: Path,
    asm: Path,
    files: dict[str, Path],
    table: Path,
    ids: int,
    layout: Layout,
    original: bool,
    extra: Mapping[str, int] = {},
):
    """One armips pass; `files` maps each `-strequ` name (`EXE_PATH`, `TITLE_PATH` ...) to
    the copy armips patches in place, `extra` is every `-equ` the layout does not carry.
    Returns the symbols it defined."""
    symbols = table.with_suffix(".sym")
    command = [str(armips), asm.name, "-sym", str(symbols)]
    for name, value in [*files.items(), ("TABLE_PATH", table)]:
        command += ["-strequ", name, str(value)]
    equates = [(name.upper(), getattr(layout, name)) for name in layout.ARMIPS_EQUATES]
    for name, value in [("TABLE_IDS", ids), *equates, *extra.items(), ("ORIGINAL", int(original))]:
        command += ["-equ", name, str(value)]
    # armips resolves `.include` against the working directory, so run it from asm/.
    done = subprocess.run(
        command, cwd=asm.parent, capture_output=True, text=True, timeout=120, check=False
    )
    if done.returncode != 0:
        raise BuildRefused(f"armips failed on {asm}:\n{done.stdout}{done.stderr}")
    pairs = (line.split() for line in symbols.read_text(encoding="latin-1").splitlines())
    return {pair[1]: int(pair[0], 16) for pair in pairs if len(pair) == 2 and pair[1][0].isalpha()}


@dataclass(frozen=True)
class Image:
    """A file armips patches: its name, the retail bytes, and where it loads in RAM."""

    name: str
    stock: bytes
    load_bias: int
    """RAM address minus file offset."""

    @property
    def equate(self) -> str:
        return f"{self.name.split('.')[0]}_PATH" if self.name != EXE_NAME else "EXE_PATH"


def assemble(
    armips: Path,
    asm: Path,
    images: list[Image],
    table: bytes,
    layout: Layout,
    work: Path,
    extra: Mapping[str, int] = {},
) -> tuple[dict[str, bytes], dict[str, int]]:
    """Returns ({image name: patched bytes}, symbols). Refuses unless the ORIGINAL pass
    reproduces every image byte for byte."""
    table_path = work / "vwf-advance.bin"
    table_path.write_bytes(table)
    checks = {image.equate: work / f"{image.name}.original-pass" for image in images}
    for image in images:
        checks[image.equate].write_bytes(image.stock)
    run_armips(armips, asm, checks, table_path, len(table), layout, original=True, extra=extra)
    for image in images:
        echoed = checks[image.equate].read_bytes()
        if echoed != image.stock:
            where = next(
                i for i, (a, b) in enumerate(zip(echoed, image.stock, strict=True)) if a != b
            )
            raise BuildRefused(
                f"{asm} with ORIGINAL=1 does not reproduce {image.name}: first difference at "
                f"RAM 0x{(where & ~3) + image.load_bias:08X}. A `stock:` block in the source "
                f"is wrong about what the retail file holds, or this is not that file."
            )
        checks[image.equate].unlink()
    patched = {image.equate: work / image.name for image in images}
    for image in images:
        patched[image.equate].write_bytes(image.stock)
    symbols = run_armips(
        armips, asm, patched, table_path, len(table), layout, original=False, extra=extra
    )
    return {image.name: patched[image.equate].read_bytes() for image in images}, symbols


MOVIE_SUB_RECORD_SHIFT = RECORD_SIZE.bit_length() - 1
"""`movie_sub_blit` reaches a glyph record with one `sll`, so the record size is a power of
two and this is its log."""
if 1 << MOVIE_SUB_RECORD_SHIFT != RECORD_SIZE:
    raise BuildRefused(f"a glyph record is {RECORD_SIZE} bytes; the blit indexes it by shift")


def movie_equates(block: bytes) -> dict[str, int]:
    """The `-equ`s `asm/movie.asm` takes: where this block is, and the numbers of its format.

    Every one of them is `boku.movie_block`'s -- the assembly restates none of them, so a
    change to the block's layout cannot leave the routine reading the old one.
    """
    return {
        "MOVIE_SUB_BLOCK": BLOCK_RAM,
        "MOVIE_SUB_LBA": BLOCK_LBA,
        "MOVIE_SUB_SECTORS": form1_sectors(len(block)),
        "MOVIE_SUB_MAGIC": MAGIC,
        "MOVIE_SUB_MASK_ROWS": MASK,
        "MOVIE_SUB_RECORD_SHIFT": MOVIE_SUB_RECORD_SHIFT,
    }


def movie_block_for(font: Mapping[str, Glyph]) -> bytes:
    """`MOVIE_CUE` encoded over `font`, the encoder's refusals reported as this script's.

    `--font` is a build input and the cue is text, so a glyph file without the cue's comma
    or hyphen is an input problem like any other -- not a `BlockError` traceback past
    `main`'s "Nothing further was written".
    """
    try:
        return encode_block([MOVIE_CUE], font)
    except BlockError as error:
        raise BuildRefused(f"the movie cue: {error}. Nothing further was written.") from error


RUN_MERGE_GAP = 32
"""Unchanged bytes two differing runs may straddle before they are emitted separately.

Purely a size knob on `edits.json`: merging costs `old`/`new` bytes that are equal and
saves an entry. The font sheet's cells are four bit-planes sharing a nibble, so a redrawn
cell is twelve six-byte runs 126 bytes apart -- far enough that none of them merge, which
is what keeps the sheet's edit set the ~2.5 KB it actually changes rather than the whole
27 KB image.
"""


def byte_runs(old: bytes, new: bytes) -> list[tuple[int, int]]:
    """`(start, end)` of each differing run of `old` vs `new`, runs closer than
    `RUN_MERGE_GAP` joined. Equal-length inputs; an empty list means they are identical.

    The scan itself is `boku.ppf.differing_spans`, the one difference scanner in the tree;
    this adds the merge. A span that stops at one of its 4 KiB block boundaries is
    rejoined here like any other neighbour, because the gap to the next one is zero.
    """
    if len(old) != len(new):
        raise BuildRefused(f"byte_runs over {len(old)} and {len(new)} bytes")
    runs: list[list[int]] = []
    for start, end in differing_spans(old, new):
        if runs and start - runs[-1][1] <= RUN_MERGE_GAP:
            runs[-1][1] = end
        else:
            runs.append([start, end])
    return [(start, end) for start, end in runs]


# --- what the patch replaces ----------------------------------------------------------


@dataclass(frozen=True)
class RawRange:
    """One whole blob the renderer patch replaces, before it is cut into edit entries.

    `edits.json` and the prototype's own `image.img` are two renderings of one patch, and
    they used to be assembled by two separate pieces of code: the select cursor reached
    the first and not the second, so the image drew the stock downward hand while the
    manifest beside it said 24 x 16. Both now derive from one list of these, which is what
    makes "promised" and "written" the same word.
    """

    file_name: str
    """`SCPS_100.88` or `BOKU.BIN` -- the disc file the offsets are in."""
    base: int
    """Offset of `stock` inside that file."""
    stock: bytes
    new: bytes
    reason: str
    label: str = ""
    """What to call this range in a refusal and in the sector ledger, when the file name
    is not specific enough: an overlay is named, not the archive it lives in."""

    @property
    def written_as(self) -> str:
        return self.label or self.file_name


def file_edits(patch: RawRange) -> list[dict[str, object]]:
    """The edit-set entries for one replaced blob: its differing runs, and nothing else."""
    return [
        {
            "file": patch.file_name,
            "offset": patch.base + start,
            "old": patch.stock[start:end].hex(),
            "new": patch.new[start:end].hex(),
            "reason": f"{patch.reason} +0x{start:x}",
        }
        for start, end in byte_runs(patch.stock, patch.new)
    ]


def edit_entries(ranges: Sequence[RawRange]) -> list[dict[str, object]]:
    """`edits.json`'s `edits`: every differing run of every range, in file order."""
    entries = [entry for patch in ranges for entry in file_edits(patch)]
    entries.sort(key=lambda edit: (edit["file"], edit["offset"]))
    return entries


# --- the select cursor ---------------------------------------------------------------------

UI_SHEET_CHILD = 3
"""`ONMEM.BIN`'s child 3: the 48 x 88 4bpp sheet of the resident UI sprites (the hand, the
pencil, the book icon), uploaded at boot to the page the sprite table's records name."""
SPRITE_TABLE_CHILD = 0
"""`ONMEM.BIN`'s child 0: `u32 count`, then 12-byte records `{u8 u, u8, u8 v, u8, u16 w in
16-bit VRAM units, u16 h, u32}`; the loader fixes up u, the page and the CLUT in RAM
(`*0x80025900`), so the file holds the sheet-relative values."""
HAND_SPRITE = 1
"""Record 1 is the select cursor: 16 x 24 at (0, 32) on the sheet, drawn at the row's origin
plus `SEL_CURSOR_DX/DY` by `select_cursor_update` (asm/select.asm). Its finger points
down, at the column the stock layout ran; the rows the patch draws want it pointing right."""
SPRITE_RECORD_BYTES = 12
TRANSPARENT = 1
"""The palette index the sheet pads its sprites with (0x0000, transparent black). Index 0
of the same CLUT is opaque **white**, so a pixel cannot be read as blank because it is 0 --
which is why nothing here decides ownership from the pixels (`sprite_rects`)."""


def sprite_rects(blob: bytes, table_offset: int, table_size: int) -> list[tuple[int, ...]]:
    """Every sprite of `ONMEM.BIN` child 0 as `(x, y, width, height)` on the UI sheet."""
    (count,) = struct.unpack_from("<I", blob, table_offset)
    if 4 + count * SPRITE_RECORD_BYTES > table_size:
        raise BuildRefused(
            f"{FONT_MEMBER} child {SPRITE_TABLE_CHILD} claims {count} sprite records and "
            f"holds {table_size} bytes"
        )
    rects = []
    for index in range(count):
        record = table_offset + 4 + SPRITE_RECORD_BYTES * index
        u, v, w_units, h = struct.unpack_from("<BxBxHH", blob, record)
        rects.append((u, v, w_units * 4, h))
    return rects


def overlaps(one: tuple[int, ...], other: tuple[int, ...]) -> bool:
    """Do two `(x, y, width, height)` rectangles share a pixel?"""
    x1, y1, w1, h1 = one
    x2, y2, w2, h2 = other
    return x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + h2 and y2 < y1 + h1


def trespassers(
    rects: Sequence[tuple[int, ...]], owner: int, *claimed: tuple[int, ...]
) -> list[int]:
    """Sprites other than `owner` that any of `claimed` would draw over."""
    return [
        index
        for index, rect in enumerate(rects)
        if index != owner and any(overlaps(rect, area) for area in claimed)
    ]


def rotate_ccw(indices: bytes, width: int, height: int) -> bytes:
    """A `width` x `height` block of pixels turned a quarter turn counter-clockwise, as seen
    on screen (y down): what pointed down points right. The result is `height` x `width`."""
    out = bytearray(width * height)
    for y_new in range(width):
        for x_new in range(height):
            out[y_new * height + x_new] = indices[x_new * width + (width - 1 - y_new)]
    return bytes(out)


def cursor_edits(archive: Archive) -> tuple[list[RawRange], dict[str, object]]:
    """`turn_the_hand` over this import's `ONMEM.BIN`."""
    member = archive.member(FONT_MEMBER)
    return turn_the_hand(archive.blob(member), member.offset)


def turn_the_hand(blob: bytes, base: int) -> tuple[list[RawRange], dict[str, object]]:
    """The blobs that turn the select's hand to point right, and what they describe.

    The sprite is rotated in place on the sheet: the 16 x 24 cell becomes 24 x 16 at the
    same `(u, v)`, and the rows the old cell no longer covers are padded transparent. The
    record's `w` and `h` follow. Nothing is drawn: the pixels are the original's, turned,
    and they stay untracked (`edits.json` carries the differing runs, which are the game's
    bytes and gitignored with the rest of `build/`).

    **What makes that safe is the sprite table, not the pixels.** Index 0 of this sheet's
    CLUT is opaque white, so "these columns look blank" is not a question the pixels can
    answer -- the padding beside the hand is index 0 throughout. The check is ownership
    instead: no other record may reach either the cell being vacated or the one being
    claimed, so the turn cannot cover a sprite or blank one.
    """
    pack = parse_pack(blob)
    if pack is None or len(pack.entries) <= UI_SHEET_CHILD:
        raise BuildRefused(f"{FONT_MEMBER} is not the 5-child pack research/font.md describes")
    table_offset, table_size = pack.entries[SPRITE_TABLE_CHILD]
    rects = sprite_rects(blob, table_offset, table_size)
    if len(rects) <= HAND_SPRITE:
        raise BuildRefused(f"{FONT_MEMBER} child {SPRITE_TABLE_CHILD} has no sprite {HAND_SPRITE}")
    u, v, old_w, old_h = rects[HAND_SPRITE]
    if (u, v, old_w, old_h) != (0, 32, 16, 24):
        raise BuildRefused(
            f"{FONT_MEMBER} sprite {HAND_SPRITE} is ({u}, {v}) {old_w} x {old_h}, not the "
            f"16 x 24 hand at (0, 32) this transform was written for"
        )
    turned_rect = (u, v, old_h, old_w)
    trespassed = trespassers(rects, HAND_SPRITE, rects[HAND_SPRITE], turned_rect)
    if trespassed:
        raise BuildRefused(
            f"{FONT_MEMBER} sprite(s) {trespassed} share the rows the hand is turned in "
            f"({u}, {v}) {old_w} x {old_h} -> {old_h} x {old_w}; turning it would draw over "
            f"them or blank them"
        )
    sheet_offset, sheet_size = pack.entries[UI_SHEET_CHILD]
    stock_sheet = blob[sheet_offset : sheet_offset + sheet_size]
    tim = parse_exact(stock_sheet)
    if tim.bpp != 4:
        raise BuildRefused(
            f"{FONT_MEMBER} child {UI_SHEET_CHILD} is {tim.bpp}bpp, not the 4bpp sheet"
        )
    width = tim.width
    pixels = bytearray(tim.indices())
    old_cell = bytes(pixels[(v + y) * width + u + x] for y in range(old_h) for x in range(old_w))
    for y in range(old_h):
        for x in range(old_w):
            pixels[(v + y) * width + u + x] = TRANSPARENT
    turned = rotate_ccw(old_cell, old_w, old_h)
    for y in range(old_w):
        for x in range(old_h):
            pixels[(v + y) * width + u + x] = turned[y * old_h + x]
    new_sheet = tim.with_indices(bytes(pixels)).serialise()
    stock_table = blob[table_offset : table_offset + table_size]
    patched_table = bytearray(stock_table)
    record = 4 + SPRITE_RECORD_BYTES * HAND_SPRITE
    struct.pack_into("<HH", patched_table, record + 4, old_h // 4, old_w)
    ranges = [
        RawRange(
            ARCHIVE_NAME,
            base + sheet_offset,
            stock_sheet,
            new_sheet,
            "VWF select cursor: the hand turned to point right",
        ),
        RawRange(
            ARCHIVE_NAME,
            base + table_offset,
            stock_table,
            bytes(patched_table),
            "VWF select cursor: sprite record w, h",
        ),
    ]
    return ranges, {"sprite": HAND_SPRITE, "was": f"{old_w}x{old_h}", "now": f"{old_h}x{old_w}"}


@dataclass(frozen=True)
class Region:
    """A block of the executable the patch fills wholesale, and the manifest's record of it.

    The free space after the advance table and the movie island are both of these: hundreds
    of changed words each, carried in the manifest as one SHA-1 rather than as word rows.
    Leaving a block out of the word list and hashing it have to be the same act, or its
    bytes go unrecorded -- so `changed_words` takes these objects, which `hashed_region`
    builds with the hash in them, and not bare ranges.
    """

    offsets: range
    """Where the block is in the executable, as file offsets."""
    record: dict[str, object]
    """What the manifest says about it, `sha1` included."""


def hashed_region(
    name: str, start: str, end: str, prefix: str, symbols: Mapping[str, int], exe: bytes
) -> Region:
    """The block between two of armips' symbols, and the manifest record of it.

    `prefix` gathers the symbols inside the block -- `[start, end)`, so the symbol that
    marks the end is the boundary and not a thing in the block, while the one that marks
    the beginning is both and is listed. The block's own address is therefore in `symbols`
    exactly once, and no key of the record repeats it.
    """
    for symbol in (start, end):
        if symbol not in symbols:
            raise BuildRefused(f"{name}: {ASM.name} defined no {symbol}")
    first, last = symbols[start] - EXE_LOAD_BIAS, symbols[end] - EXE_LOAD_BIAS
    if last <= first:
        raise BuildRefused(f"{name}: {end} (0x{symbols[end]:08X}) is not past {start}")
    return Region(
        range(first, last),
        {
            "bytes": last - first,
            "symbols": {
                symbol: f"0x{symbols[symbol]:08X}"
                for symbol in sorted(symbols)
                if symbol.startswith(prefix) and first <= symbols[symbol] - EXE_LOAD_BIAS < last
            },
            "sha1": hashlib.sha1(exe[first:last]).hexdigest(),
        },
    )


def changed_words(stock: bytes, patched: bytes, *regions: Region) -> list[dict[str, str]]:
    """Every changed executable word outside `regions` (file offsets).

    Only the words that differ are considered: `differing_spans` is the tree's one
    difference scanner and a whole-executable word loop was most of this call.
    """
    offsets = {
        offset
        for first, last in differing_spans(stock, patched)
        for offset in range(first & ~3, last, 4)
    }
    return [
        {
            "ram": f"0x{offset + EXE_LOAD_BIAS:08X}",
            "file": f"0x{offset:X}",
            "old": stock[offset : offset + 4].hex(" "),
            "new": patched[offset : offset + 4].hex(" "),
        }
        for offset in sorted(offsets)
        if not any(offset in region.offsets for region in regions)
    ]


# --- the image ------------------------------------------------------------------------


@dataclass
class Ledger:
    """Each changed sector once: as it was before the build and as it is after."""

    first: dict[int, str] = field(default_factory=dict)
    last: dict[int, str] = field(default_factory=dict)
    where: dict[int, tuple[str, int]] = field(default_factory=dict)

    def add(self, writes: list[SectorWrite], name: str, file_lba: int) -> None:
        for write in writes:
            self.first.setdefault(write.lba, write.old_sha1)
            self.last[write.lba] = write.new_sha1
            self.where[write.lba] = (name, (write.lba - file_lba) * edc.FORM1_DATA_SIZE)

    def records(self) -> list[dict[str, object]]:
        return [
            {
                "lba": lba,
                "file": self.where[lba][0],
                "offset": f"0x{self.where[lba][1]:x}",
                "old_sha1": self.first[lba],
                "new_sha1": self.last[lba],
            }
            for lba in sorted(self.first)
            if self.first[lba] != self.last[lba]
        ]


def replace_range(writer, entry, name, offset, expected, new, ledger) -> None:
    """Write `new` over `expected`, having read `expected` back out of the image first."""
    found = writer.read_file_bytes(entry.lba, offset, len(expected))
    if found != expected:
        raise BuildRefused(
            f"{name}+0x{offset:x}: the image does not hold the bytes disc/files does "
            f"({len(expected)} bytes compared). Nothing further was written."
        )
    ledger.add(
        writer.write_file_bytes(entry.lba, offset, new, file_size=entry.size), name, entry.lba
    )


def write_ranges(writer, entries: Mapping[str, object], ranges: Sequence[RawRange], ledger) -> None:
    """Every range of the renderer patch written into the image.

    The one writer of what `edit_entries` promises, over the same list, so the two cannot
    describe different patches (`RawRange`).
    """
    for patch in ranges:
        replace_range(
            writer,
            entries[patch.file_name],
            patch.written_as,
            patch.base,
            patch.stock,
            patch.new,
            ledger,
        )


def write_movie_block(writer: DiscWriter, block: bytes, ledger: Ledger) -> None:
    """The cue block into the filler sectors at `BLOCK_LBA`, which must still be filler.

    `write_data_sector` converts zero Form 2 filler and refuses XA, but it overwrites a
    Form 1 sector without a word, so the span is verified first as any relocation's is: an
    image that already holds a block here (a build over a built image) or a member the
    allocator placed here is a refusal, not a block laid over it.
    """
    data = padded(block)
    run = Run(BLOCK_LBA, form1_sectors(len(block)))
    if not PREFIX_FILLER.contains(run):
        raise BuildRefused(
            f"LBA {run.start}..{run.end - 1} is not inside the relocation arena "
            f"({PREFIX_FILLER.start}..{PREFIX_FILLER.end - 1}), the filler this block is "
            f"laid in. Nothing further was written."
        )
    edit = SectorEdit(run.start, bytes(len(data)), data, f"the movie cue block at LBA {run.start}")
    try:
        verify_sectors(writer, [edit], refused=BuildRefused)
    except DiscError as error:
        # Form 2 carrying anything but zeros: real-time data, which `read_form1_span`
        # refuses to flatten. Here that is an image whose LBA 1040 is XA, not filler.
        raise BuildRefused(
            f"LBA {run.start}..{run.end - 1} cannot be read as filler: {error}. "
            f"Nothing further was written."
        ) from error
    ledger.add(writer.write_data_sectors(edit.lba, edit.new), MOVIE_BLOCK_NAME, BLOCK_LBA)


def font_child_range(archive: Archive) -> tuple[int, int]:
    """(offset, size) inside BOKU.BIN of the font TIM: ONMEM.BIN pack child 2."""
    member = archive.member(FONT_MEMBER)
    pack = parse_pack(archive.blob(member))
    if pack is None or len(pack.entries) <= FONT_CHILD:
        raise BuildRefused(f"{FONT_MEMBER} is not the 5-child pack research/font.md describes")
    offset, size = pack.entries[FONT_CHILD]
    return member.offset + offset, size


LAYOUT_ARGUMENTS = (
    "pen_x",
    "pen_y",
    "line_pitch",
    "band_y",
    "band_h",
    "sel_x",
    "sel_y",
    "sel_pitch",
    "sel_pad",
    "sel_cursor_dx",
    "sel_cursor_dy",
    "gap",
    "band_brightness",
    "band_blend",
    "map_area_extra",
)
"""`Layout` fields the command line sets (`--pen-x` ...), plus `--advance-model`."""


def build(args: argparse.Namespace) -> dict[str, object]:
    layout = Layout(
        **{name: getattr(args, name) for name in LAYOUT_ARGUMENTS},
        advance_model=args.advance_model,
        cursor=args.cursor,
    )
    source, out = Path(args.image), Path(args.out).resolve()
    if (REPO / "disc").resolve() in [out, *out.parents]:
        raise BuildRefused("--out is under disc/, which no tool writes to")
    # `--edits-only` never opens the image: the edits come from `disc/files/` through
    # `Archive` and `SiteIndex`, and every one of them carries the bytes it expects, which
    # is a stronger check on the dump than its hash. Digesting 660 MB to set a bool the
    # mode does not use is the whole of what this guard would do there.
    hash_image = not args.skip_image_hash and not args.edits_only
    if hash_image and sha1_of(source) != IMAGE_SHA1:
        raise BuildRefused(f"{source} is not the dump the addresses were measured on")

    archive = Archive(Path(args.disc))
    archive.require_clean()
    index = SiteIndex.from_disc(Path(args.disc), archive=archive)
    stock_exe = archive.exe
    font_offset, font_size = font_child_range(archive)
    stock_tim = archive.boku[font_offset : font_offset + font_size]
    site_bytes = {
        placed: (stock_exe if placed.file_name == EXE_NAME else archive.boku)[
            placed.file_offset : placed.end
        ]
        for placed in index.placed
    }

    sheet = Sheet(stock_tim)
    if args.font:
        font = load_glyph_file(Path(args.font))
    else:
        font = game_font(sheet, layout) | load_glyph_file(PLACEHOLDERS)
    drawn = set().union(*(glyph_ids_in(raw) for raw in site_bytes.values()))
    cells, table, redrawn = place_font(sheet, layout, font, drawn)
    clash = sorted(code_glyph_ids(archive) & set(redrawn.values()))
    if clash:
        raise BuildRefused(
            f"cells {clash} were about to be redrawn, and code on this disc draws them by "
            f"id (an immediate, a digit, or sysmsg's remap); the free-id list in "
            f"{FONT_CANDIDATES.name} is wrong for this image"
        )
    for character, glyph_id in redrawn.items():
        sheet.put(glyph_id, font[character].rows)
    new_tim = bytes(sheet.data)

    work = out / "files"
    work.mkdir(parents=True, exist_ok=True)
    (work / "font-sheet.tim").write_bytes(new_tim)
    block = movie_block_for(font)
    (work / MOVIE_BLOCK_NAME).write_bytes(block)
    # `Archive.blob` copies, and each overlay is wanted three times below; cut once.
    stock_overlays = {name: archive.blob(archive.member(name)) for name in DRAWING_OVERLAYS}
    images = [Image(EXE_NAME, stock_exe, EXE_LOAD_BIAS)] + [
        Image(name, stock_overlays[name], OVERLAY_BASE) for name in DRAWING_OVERLAYS
    ]
    # Two patch passes over one source. The image is assembled with `asm/movie.asm`; the
    # executable the edit set is cut from is assembled without it, which is what keeps the
    # movie hooks out of `edits.json` (`MOVIE_BLOCK_NAME`). Each pass brings its own
    # `ORIGINAL` gate, so the retail bytes come back under both.
    equates = movie_equates(block)
    arguments = (Path(args.armips), Path(args.asm), images, bytes(table), layout, work)
    exported_images, _ = assemble(*arguments, equates | {"MOVIE_SUBTITLES": 0})
    patched, symbols = assemble(*arguments, equates | {"MOVIE_SUBTITLES": 1})
    patched_exe = patched[EXE_NAME]
    patched_overlays = {
        name: patched[name] for name in DRAWING_OVERLAYS if patched[name] != stock_overlays[name]
    }
    gap = hashed_region(
        "the renderer's free space", "vwf_advance", "vwf_free", "vwf_", symbols, patched_exe
    )
    island = hashed_region(
        "the movie island",
        "movie_sub_frame_no",
        "movie_sub_end",
        "movie_sub_",
        symbols,
        patched_exe,
    )

    provenance = {
        "format": 1,
        "source_sha1": IMAGE_SHA1 if hash_image else None,
        # A scratch `--asm /tmp/variant.asm` is the natural way to try an assembly change,
        # and it is not under the repo, so the path is recorded as it was given.
        "asm": str(Path(args.asm)),
        "layout": layout.__dict__
        | {"wrap_width": layout.wrap_width, "select_width": layout.select_width},
        "font": args.font or "the game's own Latin cells plus placeholder-glyphs.txt",
        "cells_redrawn": len(redrawn),
        "map_work_area_end": layout.map_work_area_end,
        "table": {
            "ram": f"0x{symbols['vwf_advance']:08X}",
            "ids": len(table),
            "sha1": hashlib.sha1(table).hexdigest(),
        },
        "gap": gap.record,
        "cells": {
            character: {"id": cells[character], "advance": font[character].advance}
            for character in sorted(cells)
        },
    }
    # The image's own record, and not `edits.json`'s: only the image this script writes
    # carries the block and the hooks (`MOVIE_BLOCK_NAME`).
    movie_subtitles = {
        "file": f"files/{MOVIE_BLOCK_NAME}",
        "lba": BLOCK_LBA,
        "sectors": form1_sectors(len(block)),
        "ram": f"0x{BLOCK_RAM:08X}",
        "bytes": len(block),
        "sha1": hashlib.sha1(block).hexdigest(),
        "cue": {"start": MOVIE_CUE.start, "end": MOVIE_CUE.end, "lines": list(MOVIE_CUE.lines)},
        "island": island.record,
    }
    ranges = [
        RawRange(EXE_NAME, 0, stock_exe, patched_exe, "VWF executable patch"),
        RawRange(ARCHIVE_NAME, font_offset, stock_tim, new_tim, "VWF font sheet"),
    ]
    if layout.cursor == "right":
        cursor, provenance["cursor"] = cursor_edits(archive)
        ranges += cursor
    ranges += [
        RawRange(
            ARCHIVE_NAME,
            archive.member(name).offset,
            stock_overlays[name],
            patched_overlays[name],
            f"VWF {name} patch",
            label=name,
        )
        for name in sorted(patched_overlays)
    ]
    # `ranges` is what the image is given; the edit set is the same patch cut from the
    # executable assembled without the movie hooks (`MOVIE_BLOCK_NAME`). `ranges[0]` is the
    # executable; nothing else differs between the two passes.
    exported = [replace(ranges[0], new=exported_images[EXE_NAME])]
    edits = edit_entries(exported + ranges[1:])
    (out / EDITS_NAME).write_text(
        json.dumps(provenance | {"edits": edits}, indent=2) + "\n", encoding="utf-8"
    )
    if args.edits_only:
        # `manifest.json` is defined as the record of an image (see this file's docstring),
        # and this mode writes none, so any file of that name left here now describes an
        # image that no longer matches the `edits.json` just written beside it. It is
        # removed rather than left to be read as current.
        (out / "manifest.json").unlink(missing_ok=True)
        return provenance | {"edits": edits}

    specs = load_lines(Path(args.lines))
    unfitted: list[dict[str, str]] = []
    if args.days:
        day_specs, problems = load_days(Path(args.days), args.label)
        unfitted += [{"site": "", "reason": problem} for problem in problems]
        covered = {spec.site_id for spec in day_specs}
        specs = [spec for spec in specs if spec.site_id not in covered] + day_specs
    lines = []
    for spec in specs:
        try:
            copies = index.copies_of(spec.site_id)
        except TextError as error:
            if not args.days:
                raise
            unfitted.append({"site": spec.site_id, "reason": f"not a site of this import: {error}"})
            continue
        kinds = {placed.site.kind for placed in copies}
        if len(kinds) != 1:
            raise BuildRefused(f"{spec.site_id}: its copies are of different kinds {kinds}")
        for placed in copies:
            check_placement(placed, site_bytes[placed])
        if copies[0].site.is_message:
            encode = encode_message
        elif copies[0].site.kind.startswith("SEL"):
            encode = encode_select
        elif copies[0].site.kind in ("ARR-L", "ARR-E"):
            encode = encode_array_item
        else:
            raise BuildRefused(f"{spec.site_id}: {copies[0].site.kind} sites are not written here")
        try:
            encoded, pages = encode(spec, site_bytes[copies[0]], font, cells, layout)
        except BuildRefused as error:
            # A fixture that does not fit is a build error; a translated line that does
            # not fit is a finding, reported and left Japanese (nothing is cut).
            if not args.days or spec.source == "fixture":
                raise
            unfitted.append({"site": spec.site_id, "reason": str(error)})
            continue
        lines.append((spec, copies, encoded, pages))

    image = out / "image.img"
    partial = out / "image.img.partial"
    shutil.copyfile(source, partial)
    ledger = Ledger()
    with DiscWriter(partial) as writer:
        entries = {entry.path: entry for entry in writer.walk()}
        exe_entry, archive_entry = entries[f"/{EXE_NAME}"], entries[f"/{ARCHIVE_NAME}"]
        write_ranges(writer, {EXE_NAME: exe_entry, ARCHIVE_NAME: archive_entry}, ranges, ledger)
        write_movie_block(writer, block, ledger)
        for _, copies, encoded, _ in lines:
            placed: PlacedSite
            for placed in copies:
                entry = exe_entry if placed.file_name == EXE_NAME else archive_entry
                replace_range(
                    writer,
                    entry,
                    placed.file_name,
                    placed.file_offset,
                    site_bytes[placed],
                    encoded,
                    ledger,
                )
        writer.flush()
    sectors = ledger.records()
    with DiscImage(partial) as reader:
        bad = [r["lba"] for r in sectors if not edc.check_sector(reader.read_raw(r["lba"])).ok]
    if bad:
        raise BuildRefused(f"written sectors fail their own EDC/ECC: {bad}")
    partial.replace(image)
    (out / "image.cue").write_text(
        'FILE "image.img" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n', encoding="ascii"
    )

    manifest = provenance | {
        "movie_subtitles": movie_subtitles,
        "result_sha1": sha1_of(image),
        "exe_words": changed_words(stock_exe, patched_exe, gap, island),
        "lines": [
            {
                "site": spec.site_id,
                "source": spec.source,
                "copies": len(copies),
                "site_bytes": len(encoded),
                "pages": pages,
                "page_px": [
                    [sum(font[c].advance for c in row) for row in page.split("\n")]
                    for page in pages
                ],
            }
            for spec, copies, encoded, pages in lines
        ],
        "sectors": sectors,
        "unfitted": unfitted,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--image", default=str(REPO / "disc/image.img"))
    parser.add_argument("--disc", default=str(REPO / "disc"), help="the import (read-only)")
    parser.add_argument("--out", default=str(REPO / "build/vwf"))
    parser.add_argument("--lines", default=str(DEFAULT_LINES))
    parser.add_argument(
        "--days",
        metavar="DIR",
        help="translation/days: write every reviewed line that fits its site in place, "
        "and list the ones that do not (they stay Japanese)",
    )
    parser.add_argument(
        "--label",
        action="store_true",
        help="with --days, prefix each message with its speaker as inline text ('Boku: ')",
    )
    parser.add_argument("--font", help="a glyph file in placeholder-glyphs.txt's format")
    parser.add_argument("--asm", default=str(ASM))
    parser.add_argument("--armips", default=str(DEFAULT_ARMIPS))
    parser.add_argument("--skip-image-hash", action="store_true", help="for repeat builds")
    parser.add_argument(
        "--edits-only",
        action="store_true",
        help=(
            f"write {EDITS_NAME} and stop: the renderer patch as byte edits for `boku build "
            f"--vwf`, with no 660 MB copy and no text written in place"
        ),
    )
    defaults = Layout()
    for name in LAYOUT_ARGUMENTS:
        # The field's default, not the instance's: `sel_cursor_dx` is resolved from
        # `--cursor` in `__post_init__`, and an argparse default read off a built `Layout`
        # would hand every mode the default mode's offset.
        parser.add_argument(
            f"--{name.replace('_', '-')}",
            type=int,
            default=Layout.__dataclass_fields__[name].default,
        )
    parser.add_argument(
        "--cursor",
        choices=("right", "down"),
        default=defaults.cursor,
        help="right: turn the select's hand to point at its row (the default); down: the "
        "stock sprite. --sel-cursor-dx follows the choice unless it is given.",
    )
    parser.add_argument(
        "--advance-model",
        choices=("c1", "c2"),
        default=defaults.advance_model,
        help="c2 (default): ink re-aligned to column 0, advance = ink + gap; c1: the glyph "
        "at its native bearing, advance to the ink's right edge (research/font-candidates.md)",
    )
    args = parser.parse_args()
    try:
        manifest = build(args)
    except BuildRefused as error:
        print(f"build_prototype: {error}", file=sys.stderr)
        return 1
    table, gap = manifest["table"], manifest["gap"]
    # The gap starts at the advance table and the hooks follow it, so the free byte is the
    # one past the block and the hooks are every symbol in it but the table itself.
    hooks = [name for name in gap["symbols"] if name != "vwf_advance"]
    out = Path(args.out)
    print(f"wrote {out / EDITS_NAME if args.edits_only else out / 'image.cue'}")
    print(
        f"  advance table: {table['ids']} bytes at {table['ram']}, then {' '.join(hooks)}; "
        f"gap free from 0x{int(table['ram'], 16) + gap['bytes']:08X}"
    )
    if args.edits_only:
        changed = sum(len(edit["old"]) // 2 for edit in manifest["edits"])
        print(
            f"  {len(manifest['edits'])} byte edit(s) over {changed} bytes, "
            f"{len(manifest['cells'])} glyph cells ({manifest['cells_redrawn']} redrawn, "
            f"model {manifest['layout']['advance_model']}); map work area "
            f"{manifest['map_work_area_end']:#x}"
        )
        return 0
    print(
        f"  {len(manifest['exe_words'])} executable words, {len(manifest['cells'])} glyph "
        f"cells, {len(manifest['lines'])} lines, {len(manifest['sectors'])} sectors"
    )
    unfitted = manifest["unfitted"]
    if unfitted:
        print(f"  {len(unfitted)} lines left Japanese (manifest.json -> unfitted):")
        for entry in unfitted:
            print(f"    {entry['site'] or '-'}: {entry['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
