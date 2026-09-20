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
from boku.sites import page_waits  # noqa: E402
from boku.text import PlacedSite, SiteIndex, check_placement  # noqa: E402

HERE = Path(__file__).resolve().parent
ASM = REPO / "asm/dialogue.asm"
GLYPH_TSV = REPO / "research/data/glyph-table.tsv"
FONT_CANDIDATES = REPO / "research/font-candidates.md"
SAMPLES = REPO / "translation/samples"
PLACEHOLDERS = HERE / "placeholder-glyphs.txt"
DEFAULT_LINES = HERE / "prototype-lines.tsv"
DEFAULT_ARMIPS = Path.home() / "Dev/dist/armips/build/armips"

EXE_LOAD_BIAS = 0x8000F800
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
    fixed_advance: int = 14
    gap: int = 1
    """Pixels between one glyph's ink and the next, for glyphs measured from their ink."""

    @property
    def wrap_width(self) -> int:
        """The pen's left margin mirrored on the right."""
        return SCREEN_WIDTH - 2 * self.pen_x


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


def game_font(sheet: Sheet, layout: Layout) -> dict[str, Glyph]:
    """The game's own Latin glyphs, shifted to column 0, advance = ink width + gap."""
    glyphs = {}
    for character, glyph_id in native_ids().items():
        rows = sheet.get(glyph_id)
        ink = Glyph(rows, 0).ink
        if ink is None:
            continue
        left, right = ink
        glyphs[character] = Glyph(
            tuple((row << left) & 0xFFF for row in rows), right - left + 1 + layout.gap
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
    """Line id -> (speaker, English) from every file in `translation/samples/`."""
    samples = {}
    for path in sorted(SAMPLES.glob("*.txt")):
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
                raise BuildRefused(f"{path}: {row['source']} is not in translation/samples/")
            specs.append(LineSpec(row["site"], row["source"], label, row["wrap"] == "yes", text))
    return specs


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


# --- assembling -----------------------------------------------------------------------


def run_armips(
    armips: Path, asm: Path, exe: Path, table: Path, ids: int, layout: Layout, original: bool
):
    symbols = exe.with_suffix(".sym")
    command = [str(armips), str(asm), "-sym", str(symbols)]
    for name, value in (("EXE_PATH", exe), ("TABLE_PATH", table)):
        command += ["-strequ", name, str(value)]
    for name, value in (
        ("TABLE_IDS", ids),
        ("FIXED_ADVANCE", layout.fixed_advance),
        ("PEN_X", layout.pen_x),
        ("PEN_Y", layout.pen_y),
        ("LINE_PITCH", layout.line_pitch),
        ("BAND_Y", layout.band_y),
        ("BAND_H", layout.band_h),
        ("ORIGINAL", int(original)),
    ):
        command += ["-equ", name, str(value)]
    done = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if done.returncode != 0:
        raise BuildRefused(f"armips failed on {asm}:\n{done.stdout}{done.stderr}")
    pairs = (line.split() for line in symbols.read_text(encoding="latin-1").splitlines())
    return {pair[1]: int(pair[0], 16) for pair in pairs if len(pair) == 2 and pair[1][0].isalpha()}


def assemble(armips: Path, asm: Path, stock: bytes, table: bytes, layout: Layout, work: Path):
    """Returns (patched executable, symbols). Refuses unless the ORIGINAL pass is an identity."""
    table_path = work / "vwf-advance.bin"
    table_path.write_bytes(table)
    check = work / "SCPS_100.88.original-pass"
    check.write_bytes(stock)
    run_armips(armips, asm, check, table_path, len(table), layout, original=True)
    echoed = check.read_bytes()
    if echoed != stock:
        where = next(i for i, (a, b) in enumerate(zip(echoed, stock, strict=True)) if a != b)
        raise BuildRefused(
            f"{asm} with ORIGINAL=1 does not reproduce {EXE_NAME}: first difference at RAM "
            f"0x{(where & ~3) + EXE_LOAD_BIAS:08X}. A `stock:` block in the source is wrong "
            f"about what the retail executable holds, or this is not that executable."
        )
    check.unlink()
    check.with_suffix(".sym").unlink(missing_ok=True)
    patched = work / EXE_NAME
    patched.write_bytes(stock)
    symbols = run_armips(armips, asm, patched, table_path, len(table), layout, original=False)
    return patched.read_bytes(), symbols


def changed_words(stock: bytes, patched: bytes, table: range) -> list[dict[str, str]]:
    """Every changed executable word outside the advance table, which the manifest hashes."""
    out = []
    for offset in range(0, len(stock), 4):
        if offset + EXE_LOAD_BIAS in table:
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


def build(args: argparse.Namespace) -> dict[str, object]:
    layout = Layout(
        pen_x=args.pen_x,
        pen_y=args.pen_y,
        line_pitch=args.line_pitch,
        band_y=args.band_y,
        band_h=args.band_h,
        gap=args.gap,
    )
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
    table = bytearray([layout.fixed_advance]) * (max(cells.values()) + 1)
    for character, glyph_id in cells.items():
        sheet.put(glyph_id, font[character].rows)
        table[glyph_id] = font[character].advance
    new_tim = bytes(sheet.data)

    work = out / "files"
    work.mkdir(parents=True, exist_ok=True)
    (work / "font-sheet.tim").write_bytes(new_tim)
    patched_exe, symbols = assemble(
        Path(args.armips), Path(args.asm), stock_exe, bytes(table), layout, work
    )

    lines = []
    for spec in load_lines(Path(args.lines)):
        copies = index.copies_of(spec.site_id)
        for placed in copies:
            if not placed.site.is_message:
                raise BuildRefused(f"{spec.site_id}: {placed.site.kind} sites are not messages")
            check_placement(placed, site_bytes[placed])
        encoded, pages = encode_message(spec, site_bytes[copies[0]], font, cells, layout)
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

    manifest = {
        "format": 1,
        "source_sha1": IMAGE_SHA1 if not args.skip_image_hash else None,
        "result_sha1": sha1_of(image),
        "layout": layout.__dict__ | {"wrap_width": layout.wrap_width},
        "font": args.font or "the game's own Latin cells, re-aligned, plus placeholder-glyphs.txt",
        "table": {
            "ram": f"0x{symbols['vwf_advance']:08X}",
            "ids": len(table),
            "first_free_byte": f"0x{symbols['vwf_free']:08X}",
            "sha1": hashlib.sha1(table).hexdigest(),
        },
        "cells": {
            character: {"id": cells[character], "advance": font[character].advance}
            for character in sorted(cells)
        },
        "exe_words": changed_words(
            stock_exe, patched_exe, range(symbols["vwf_advance"] & ~3, symbols["vwf_free"])
        ),
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
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--image", default=str(REPO / "disc/image.img"))
    parser.add_argument("--disc", default=str(REPO / "disc"), help="the import (read-only)")
    parser.add_argument("--out", default=str(REPO / "build/vwf"))
    parser.add_argument("--lines", default=str(DEFAULT_LINES))
    parser.add_argument("--font", help="a glyph file in placeholder-glyphs.txt's format")
    parser.add_argument("--asm", default=str(ASM))
    parser.add_argument("--armips", default=str(DEFAULT_ARMIPS))
    parser.add_argument("--skip-image-hash", action="store_true", help="for repeat builds")
    defaults = Layout()
    for name in ("pen_x", "pen_y", "line_pitch", "band_y", "band_h", "gap"):
        parser.add_argument(
            f"--{name.replace('_', '-')}", type=int, default=getattr(defaults, name)
        )
    try:
        manifest = build(parser.parse_args())
    except BuildRefused as error:
        print(f"build_prototype: {error}", file=sys.stderr)
        return 1
    table = manifest["table"]
    print(f"wrote {Path(parser.parse_args().out) / 'image.cue'}")
    print(
        f"  advance table: {table['ids']} bytes at {table['ram']}, gap free from "
        f"{table['first_free_byte']}"
    )
    print(
        f"  {len(manifest['exe_words'])} executable words, {len(manifest['cells'])} glyph "
        f"cells, {len(manifest['lines'])} lines, {len(manifest['sectors'])} sectors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
