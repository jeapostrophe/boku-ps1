"""`TXT-05` prototype: proportional horizontal dialogue, built into a copy of your image.

    uv run python tools/vwf/build_prototype.py            # -> build/vwf/image.cue

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
4. Copies the image, checks that every range it is about to replace holds the bytes
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
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from boku import edc  # noqa: E402
from boku.archive import ARCHIVE_NAME, EXE_NAME, Archive, parse_pack  # noqa: E402
from boku.disc import DiscImage, DiscWriter, SectorWrite  # noqa: E402
from boku.glyphs import END_WORD, NEWLINE_WORD, PAGE_WORD, words_of  # noqa: E402
from boku.importer import IMAGE_SHA1, sha1_of  # noqa: E402
from boku.sites import line_key_of, page_waits  # noqa: E402
from boku.text import PlacedSite, SiteIndex, TextError  # noqa: E402
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
CELL = 12
SHEET_COLUMNS = 21
SHEET_PLANES = 4
SHEET_SLOTS = 1512
SCREEN_WIDTH = 320

PAGE_BREAK = " // "
"""How `translation/samples/` writes a page boundary."""


class BuildRefused(Exception):
    """The build will not proceed; `image.img` under `--out` is as it was."""


@dataclass(frozen=True)
class Layout:
    """Everything `PLAN TXT-03` leaves to Jay, as build inputs with the trial's defaults."""

    pen_x: int = 24
    pen_y: int = 176
    line_pitch: int = 13
    band_y: int = 168
    band_h: int = 72
    sel_x: int = 48
    sel_y: int = 174
    sel_pitch: int = 13
    sel_pad: int = 6
    sel_cursor_dx: int = -18
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
    )
    """Fields `asm/vwf.asm` takes as `-equ NAME`, upper-cased."""

    def __post_init__(self) -> None:
        if self.sel_cursor_dx > 0:
            raise BuildRefused("--sel-cursor-dx must be <= 0: the box's corner is measured from it")

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
        if ink and ink[0] != 0:
            raise BuildRefused(
                f"{path}: {match.group(0)} has ink starting at column {ink[0]}; the renderer "
                f"has no bearing, so ink starts at column 0"
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
    """The game's own Latin glyphs, shifted to column 0, advance = ink width + gap.

    A glyph of `NARROW_INK` or less advances one more, for the shadow's sake.
    """
    glyphs = {}
    for character, glyph_id in native_ids().items():
        rows = sheet.get(glyph_id)
        ink = Glyph(rows, 0).ink
        if ink is None:
            continue
        left, right = ink
        width = right - left + 1
        advance = width + layout.gap + (1 if width <= NARROW_INK else 0)
        glyphs[character] = Glyph(tuple((row << left) & 0xFFF for row in rows), advance)
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


def allocate_cells(font: dict[str, Glyph]) -> dict[str, int]:
    """Character -> glyph id, touching only cells the Japanese script never draws.

    A character keeps its native cell when that cell is free; otherwise it takes the lowest
    free cell no character is keeping, so the advance table stays as short as it can.
    """
    free = free_cells()
    native = native_ids()
    cells = {c: native[c] for c in font if native.get(c) in free}
    kept = set(cells.values())
    spare = (i for i in free if i not in kept)
    for character in sorted(font):
        if character not in cells:
            try:
                cells[character] = next(spare)
            except StopIteration:
                raise BuildRefused("the sheet has no free cell left for this font") from None
    return cells


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
    """The site's replacement bytes and the pages as laid out. Refuses; never cuts."""
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
):
    """One armips pass; `files` maps each `-strequ` name (`EXE_PATH`, `TITLE_PATH` ...) to
    the copy armips patches in place. Returns the symbols it defined."""
    symbols = table.with_suffix(".sym")
    command = [str(armips), asm.name, "-sym", str(symbols)]
    for name, value in [*files.items(), ("TABLE_PATH", table)]:
        command += ["-strequ", name, str(value)]
    equates = [(name.upper(), getattr(layout, name)) for name in layout.ARMIPS_EQUATES]
    for name, value in [("TABLE_IDS", ids), *equates, ("ORIGINAL", int(original))]:
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
    armips: Path, asm: Path, images: list[Image], table: bytes, layout: Layout, work: Path
) -> tuple[dict[str, bytes], dict[str, int]]:
    """Returns ({image name: patched bytes}, symbols). Refuses unless the ORIGINAL pass
    reproduces every image byte for byte."""
    table_path = work / "vwf-advance.bin"
    table_path.write_bytes(table)
    checks = {image.equate: work / f"{image.name}.original-pass" for image in images}
    for image in images:
        checks[image.equate].write_bytes(image.stock)
    run_armips(armips, asm, checks, table_path, len(table), layout, original=True)
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
    symbols = run_armips(armips, asm, patched, table_path, len(table), layout, original=False)
    return {image.name: patched[image.equate].read_bytes() for image in images}, symbols


def changed_words(stock: bytes, patched: bytes, gap: range) -> list[dict[str, str]]:
    """Every changed executable word outside the gap (file offsets), which the manifest hashes."""
    out = []
    for offset in range(0, len(stock), 4):
        if offset in gap:
            continue
        if stock[offset : offset + 4] != patched[offset : offset + 4]:
            out.append(
                {
                    "ram": f"0x{offset + EXE_LOAD_BIAS:08X}",
                    "file": f"0x{offset:X}",
                    "old": stock[offset : offset + 4].hex(" "),
                    "new": patched[offset : offset + 4].hex(" "),
                }
            )
    return out


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
)
"""`Layout` fields the command line sets (`--pen-x` ...)."""


def build(args: argparse.Namespace) -> dict[str, object]:
    layout = Layout(**{name: getattr(args, name) for name in LAYOUT_ARGUMENTS})
    source, out = Path(args.image), Path(args.out).resolve()
    if (REPO / "disc").resolve() in [out, *out.parents]:
        raise BuildRefused("--out is under disc/, which no tool writes to")
    if not args.skip_image_hash and sha1_of(source) != IMAGE_SHA1:
        raise BuildRefused(f"{source} is not the dump the addresses were measured on")

    archive = Archive(Path(args.disc))
    archive.require_clean()
    index = SiteIndex.from_disc(Path(args.disc))
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
    cells = allocate_cells(font)
    drawn = set().union(*(glyph_ids_in(raw) for raw in site_bytes.values()))
    clash = sorted(drawn & set(cells.values()))
    if clash:
        raise BuildRefused(
            f"cells {clash} were about to be redrawn, and text on this disc draws them; "
            f"the free-id list in {FONT_CANDIDATES.name} is wrong for this image"
        )
    clash = sorted(code_glyph_ids(archive) & set(cells.values()))
    if clash:
        raise BuildRefused(
            f"cells {clash} were about to be redrawn, and code on this disc draws them by "
            f"id (an immediate, a digit, or sysmsg's remap); the free-id list in "
            f"{FONT_CANDIDATES.name} is wrong for this image"
        )
    table = bytearray([layout.fixed_advance]) * (max(cells.values()) + 1)
    for character, glyph_id in cells.items():
        sheet.put(glyph_id, font[character].rows)
        table[glyph_id] = font[character].advance
    new_tim = bytes(sheet.data)

    work = out / "files"
    work.mkdir(parents=True, exist_ok=True)
    (work / "font-sheet.tim").write_bytes(new_tim)
    images = [Image(EXE_NAME, stock_exe, EXE_LOAD_BIAS)] + [
        Image(name, archive.blob(archive.member(name)), OVERLAY_BASE) for name in DRAWING_OVERLAYS
    ]
    patched, symbols = assemble(
        Path(args.armips), Path(args.asm), images, bytes(table), layout, work
    )
    patched_exe = patched[EXE_NAME]
    patched_overlays = {
        name: patched[name]
        for name in DRAWING_OVERLAYS
        if patched[name] != archive.blob(archive.member(name))
    }

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
        replace_range(writer, exe_entry, EXE_NAME, 0, stock_exe, patched_exe, ledger)
        replace_range(writer, archive_entry, ARCHIVE_NAME, font_offset, stock_tim, new_tim, ledger)
        for name, new_overlay in patched_overlays.items():
            member = archive.member(name)
            replace_range(
                writer,
                archive_entry,
                name,
                member.offset,
                archive.blob(member),
                new_overlay,
                ledger,
            )
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

    gap_range = range(symbols["vwf_advance"] - EXE_LOAD_BIAS, symbols["vwf_free"] - EXE_LOAD_BIAS)
    manifest = {
        "format": 1,
        "source_sha1": IMAGE_SHA1 if not args.skip_image_hash else None,
        "result_sha1": sha1_of(image),
        "layout": layout.__dict__
        | {"wrap_width": layout.wrap_width, "select_width": layout.select_width},
        "font": args.font or "the game's own Latin cells, re-aligned, plus placeholder-glyphs.txt",
        "table": {
            "ram": f"0x{symbols['vwf_advance']:08X}",
            "ids": len(table),
            "sha1": hashlib.sha1(table).hexdigest(),
        },
        "gap": {
            "ram": f"0x{symbols['vwf_advance']:08X}",
            "first_free_byte": f"0x{symbols['vwf_free']:08X}",
            "hooks": {
                name: f"0x{symbols[name]:08X}"
                for name in sorted(symbols)
                if name.startswith("vwf_") and name not in ("vwf_advance", "vwf_free")
            },
            "sha1": hashlib.sha1(patched_exe[gap_range.start : gap_range.stop]).hexdigest(),
        },
        "cells": {
            character: {"id": cells[character], "advance": font[character].advance}
            for character in sorted(cells)
        },
        "exe_words": changed_words(stock_exe, patched_exe, gap_range),
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
    defaults = Layout()
    for name in LAYOUT_ARGUMENTS:
        parser.add_argument(
            f"--{name.replace('_', '-')}", type=int, default=getattr(defaults, name)
        )
    try:
        manifest = build(parser.parse_args())
    except BuildRefused as error:
        print(f"build_prototype: {error}", file=sys.stderr)
        return 1
    table, gap = manifest["table"], manifest["gap"]
    print(f"wrote {Path(parser.parse_args().out) / 'image.cue'}")
    print(
        f"  advance table: {table['ids']} bytes at {table['ram']}, then "
        f"{' '.join(gap['hooks'])}; gap free from {gap['first_free_byte']}"
    )
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
