"""`PLAN TRN-08`'s render check: every page of a translation drawn as the band would draw it.

    ./make.sh mockup                                   # translation/days -> work/mockup/
    ./make.sh mockup translation/days/day01.txt --events E0121 E0140

One PNG per scene, under `work/mockup/<file>/<EVENT>.png`: each page of each line a tile,
top to bottom in the file's order, drawn with the font sheet's own glyphs at the band's
geometry -- no emulator. A reviewer or Jay eyeballs a day's pages here before the
*rendered* state (`translation/days/README.md`), and plays it for *finalized*.

Nothing about the page is decided here. What is drawn is what `boku build --vwf` would
insert:

* **the lines** are `boku.build.lay_out`'s -- the same wrap, the same label and marks, the
  same encoder -- over the same walk, so a break drawn here is the break the image gets;
* **the widths and cells** are the edit set's character map (`build/vwf/edits.json`, the
  file `boku lint --encoder cellmap` and `boku build --vwf` read);
* **the pixels** are the stock font sheet from your import with the edit set's font-sheet
  edits applied -- the sheet the image is given -- read through the font build's own
  `Sheet`;
* **the geometry** (pen, pitch, band, select box) is the edit set's `layout` record, and
  the line limits are `boku.layout.DIALOGUE_BAND`.

A page with more lines than the band holds draws its extra lines below the band in red; a
line wider than its limit is drawn in red; the next-page pencil's zone on the guarded line
is shaded. The pictures hold the game's glyph pixels, so they live under the gitignored
`work/` and are never tracked (CLAUDE.md § "This repo is public").
"""

from __future__ import annotations

import argparse
import sys
from array import array
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import build_prototype as vwf  # noqa: E402

from boku.archive import ARCHIVE_NAME, DEFAULT_DISC_DIR, Archive, ArchiveError  # noqa: E402
from boku.build import BuildRefused, EditSet, LineResult, lay_out, load_edit_set  # noqa: E402
from boku.layout import DIALOGUE_BAND, BoxSpec, Encoder  # noqa: E402
from boku.lint import DEFAULT_CELLS, translation_paths  # noqa: E402
from boku.movie_block import CELL, SCREEN_WIDTH  # noqa: E402
from boku.packets import PacketRefused, check_destination  # noqa: E402
from boku.png import write_rgba  # noqa: E402
from boku.sites import SiteError, load  # noqa: E402
from boku.translation import SampleScenes  # noqa: E402

DEFAULT_SOURCES = (REPO / "translation" / "days",)
DEFAULT_OUT = REPO / "work" / "mockup"

Colour = tuple[int, int, int]
SCENE: Colour = (72, 92, 72)
BAND: Colour = (28, 30, 48)
INK: Colour = (236, 236, 236)
SHADOW: Colour = (12, 12, 20)
OVER: Colour = (255, 84, 84)
PENCIL: Colour = (104, 88, 36)
CAPTION: Colour = (150, 150, 160)
GAP = 2
"""Rows between one tile and the next."""


class MockupRefused(Exception):
    """An edit set, a disc or a destination this tool will not draw from or into."""


# --- the sheet the image is given -------------------------------------------------------------


def font_sheet(archive: Archive, edit_set: EditSet) -> vwf.Sheet:
    """The stock font TIM with the edit set's font-sheet edits applied, as a `Sheet`.

    Each edit's `old` bytes are checked against the import first, exactly as the image
    build checks them: a sheet drawn from a different dump would draw the wrong pixels in
    silence.
    """
    offset, size = vwf.font_child_range(archive)
    tim = bytearray(archive.boku[offset : offset + size])
    applied = 0
    for edit in edit_set.edits:
        if edit.file != ARCHIVE_NAME or not offset <= edit.offset < offset + size:
            continue
        start = edit.offset - offset
        if bytes(tim[start : start + len(edit.old)]) != edit.old:
            raise MockupRefused(
                f"{edit.reason}: the import does not hold the bytes this edit expects at "
                f"BOKU.BIN+{edit.offset:#x}; the edit set was built from another dump"
            )
        tim[start : start + len(edit.new)] = edit.new
        applied += 1
    if not applied:
        raise MockupRefused("the edit set carries no font-sheet edit; there is no English font")
    return vwf.Sheet(bytes(tim))


# --- drawing --------------------------------------------------------------------------------------


@dataclass
class Canvas:
    """An RGB picture, drawn into at the PlayStation's own pixel scale."""

    width: int
    height: int
    pixels: bytearray

    @classmethod
    def blank(cls, width: int, height: int, colour: Colour) -> Canvas:
        return cls(width, height, bytearray(colour) * (width * height))

    def put(self, x: int, y: int, colour: Colour) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            at = 3 * (y * self.width + x)
            self.pixels[at : at + 3] = bytes(colour)

    def get(self, x: int, y: int) -> Colour:
        at = 3 * (y * self.width + x)
        return tuple(self.pixels[at : at + 3])  # type: ignore[return-value]

    def fill(self, x: int, y: int, width: int, height: int, colour: Colour) -> None:
        left, right = max(x, 0), min(x + width, self.width)
        if right <= left:
            return
        run = bytes(colour) * (right - left)
        for row in range(max(y, 0), min(y + height, self.height)):
            at = 3 * (row * self.width + left)
            self.pixels[at : at + len(run)] = run

    def paste(self, other: Canvas, y: int) -> None:
        start = 3 * y * self.width
        self.pixels[start : start + len(other.pixels)] = other.pixels

    def png(self, scale: int = 1) -> bytes:
        count = self.width * self.height
        rgba = bytearray(b"\xff" * (4 * count))
        for channel in range(3):
            rgba[channel::4] = self.pixels[channel::3]
        if scale > 1:
            words = array("I", bytes(rgba))
            wide = array("I", bytes(4 * count * scale))
            for step in range(scale):
                wide[step::scale] = words
            stride = 4 * self.width * scale
            raw = bytes(wide)
            rgba = bytearray().join(
                raw[row : row + stride] * scale for row in range(0, len(raw), stride)
            )
        return write_rgba(self.width * scale, self.height * scale, bytes(rgba))


Glyphs = Callable[[int], Sequence[int]]
"""Cell id -> its twelve rows, bit 11 = column 0 (`build_prototype.Sheet.get`)."""

SHADOW_DX = 1
"""The renderer draws every glyph twice, the second copy one column right: the drop shadow
(`build_prototype.load_glyph_file`)."""


@cache
def _lit(rows: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
    """The `(column, row)` of every inked pixel of a cell."""
    return tuple(
        (column, row)
        for row, bits in enumerate(rows)
        for column in range(CELL)
        if bits >> (CELL - 1 - column) & 1
    )


def draw_run(
    canvas: Canvas, x: int, y: int, text: str, encoder: Encoder, glyphs: Glyphs, ink: Colour
) -> int:
    """Draw `text` from pen `(x, y)` the way the hooked renderer does: shadow then glyph,
    the pen advancing by the cell map's advance. A character the font has no cell for is
    drawn as a red block of its advance. Returns the pen."""
    for character in text:
        cell = encoder.glyph(character)
        advance = encoder.advance(character)
        if cell is None:
            canvas.fill(x, y + 2, max(advance - 1, 1), CELL - 4, OVER)
        else:
            lit = _lit(tuple(glyphs(cell)))
            for shade, dx in ((SHADOW, SHADOW_DX), (ink, 0)):
                for column, row in lit:
                    canvas.put(x + column + dx, y + row, shade)
        x += advance
    return x


def layout_of(edit_set: EditSet) -> vwf.Layout:
    """The font build's own `Layout`, from the record the edit set carries of it."""
    record = edit_set.document.get("layout")
    if not isinstance(record, dict):
        raise MockupRefused("the edit set carries no `layout` record to draw with")
    names = {field.name for field in fields(vwf.Layout)}
    return vwf.Layout(**{name: value for name, value in record.items() if name in names})


CAPTION_HEIGHT = CELL + 4
"""The strip above each tile that names the line and page."""


def page_top(layout: vwf.Layout) -> int:
    """The screen row a page tile starts at: its caption strip above the band."""
    return layout.band_y - CAPTION_HEIGHT


def select_top(layout: vwf.Layout) -> int:
    """The screen row a select tile starts at: its caption strip above the box."""
    return layout.sel_y - layout.sel_pad - CAPTION_HEIGHT


def _captioned(height: int, caption: str, encoder: Encoder, glyphs: Glyphs) -> Canvas:
    canvas = Canvas.blank(SCREEN_WIDTH, height, SCENE)
    canvas.fill(0, 0, SCREEN_WIDTH, CAPTION_HEIGHT - 2, BAND)
    draw_run(canvas, 4, 1, caption, encoder, glyphs, CAPTION)
    return canvas


def page_tile(
    lines: Sequence[str],
    widths: Sequence[int],
    caption: str,
    layout: vwf.Layout,
    box: BoxSpec,
    encoder: Encoder,
    glyphs: Glyphs,
) -> Canvas:
    """One page of a message, from the caption strip down to below its last line."""
    top = page_top(layout)
    last = layout.pen_y + max(len(lines), box.lines) * layout.line_pitch + CELL
    bottom = max(layout.band_y + layout.band_h, last) + 2
    canvas = _captioned(bottom - top, caption, encoder, glyphs)
    canvas.fill(0, layout.band_y - top, SCREEN_WIDTH, layout.band_h, BAND)
    if box.guarded_from:
        y = layout.pen_y - top + (box.guarded_from - 1) * layout.line_pitch
        x = layout.pen_x + box.guarded_width
        canvas.fill(x, y, layout.pen_x + box.width - x, layout.line_pitch, PENCIL)
    for index, (line, width) in enumerate(zip(lines, widths, strict=True), start=1):
        over = index > box.lines or width > box.width_of_line(index)
        y = layout.pen_y - top + (index - 1) * layout.line_pitch
        draw_run(canvas, layout.pen_x, y, line, encoder, glyphs, OVER if over else INK)
    return canvas


def select_tile(
    lines: Sequence[str],
    widths: Sequence[int],
    caption: str,
    layout: vwf.Layout,
    encoder: Encoder,
    glyphs: Glyphs,
) -> Canvas:
    """A choice menu, its rows at the select box's origin and pitch. A row wider than the
    renderer's `select_width` is drawn red."""
    top = select_top(layout)
    rows = len(lines) * layout.sel_pitch + 2 * layout.sel_pad
    canvas = _captioned(CAPTION_HEIGHT + rows + 2, caption, encoder, glyphs)
    x, width = layout.sel_x - layout.sel_pad, layout.select_width + 2 * layout.sel_pad
    canvas.fill(x, layout.sel_y - layout.sel_pad - top, width, rows, BAND)
    for index, (line, pixels) in enumerate(zip(lines, widths, strict=True)):
        ink = OVER if pixels > layout.select_width else INK
        y = layout.sel_y - top + index * layout.sel_pitch
        draw_run(canvas, layout.sel_x, y, line, encoder, glyphs, ink)
    return canvas


def stack(tiles: Sequence[Canvas]) -> Canvas:
    height = sum(tile.height for tile in tiles) + GAP * (len(tiles) - 1)
    canvas = Canvas.blank(SCREEN_WIDTH, height, (0, 0, 0))
    y = 0
    for tile in tiles:
        canvas.paste(tile, y)
        y += tile.height + GAP
    return canvas


def tiles_of(
    result: LineResult,
    speaker: str,
    is_select: bool,
    layout: vwf.Layout,
    encoder: Encoder,
    glyphs: Glyphs,
) -> list[Canvas]:
    """Every page of one laid-out line, captioned `E0121.0 1/2 Aunt`."""
    laid = result.laid_out
    if laid is None or not laid.pages:
        return []
    if is_select:
        return [select_tile(laid.pages[0], laid.widths[0], result.line_id, layout, encoder, glyphs)]
    total = len(laid.pages)
    return [
        page_tile(
            page,
            widths,
            f"{result.line_id} {number}/{total} {speaker}".rstrip(),
            layout,
            DIALOGUE_BAND,
            encoder,
            glyphs,
        )
        for number, (page, widths) in enumerate(zip(laid.pages, laid.widths, strict=True), 1)
    ]


# --- a run ----------------------------------------------------------------------------------------


@dataclass
class Drawn:
    scenes: int = 0
    pages: int = 0
    over: int = 0
    skipped: int = 0


def event_of(line_id: str) -> str:
    return line_id.split(".", 1)[0]


def draw_file(
    path: Path,
    archive: Archive,
    walk,
    encoder: Encoder,
    glyphs: Glyphs,
    layout: vwf.Layout,
    out: Path,
    events: frozenset[str],
    scale: int,
) -> Drawn:
    entries = [
        entry
        for entry in SampleScenes.from_paths([path])
        if entry.line_id.startswith("E") and (not events or event_of(entry.line_id) in events)
    ]
    tally = Drawn()
    by_event: dict[str, list[Canvas]] = {}
    results = lay_out(archive, walk, entries, encoder, DIALOGUE_BAND)
    for entry, result in zip(entries, results, strict=True):
        if result.laid_out is None:
            tally.skipped += 1
            continue
        tiles = tiles_of(result, entry.speaker, entry.is_select, layout, encoder, glyphs)
        tally.pages += len(tiles)
        tally.over += bool(result.problems)
        by_event.setdefault(event_of(entry.line_id), []).extend(tiles)
    folder = out / path.stem
    folder.mkdir(parents=True, exist_ok=True)
    for event, tiles in by_event.items():
        (folder / f"{event}.png").write_bytes(stack(tiles).png(scale))
    tally.scenes = len(by_event)
    return tally


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "sources",
        nargs="*",
        type=Path,
        metavar="FILE",
        help="translation files or directories of them (default: translation/days)",
    )
    parser.add_argument("--events", nargs="+", default=(), metavar="EVENT")
    parser.add_argument(
        "--edits",
        type=Path,
        default=DEFAULT_CELLS,
        metavar="FILE",
        help=f"the renderer's edit set (default: {DEFAULT_CELLS.relative_to(REPO)})",
    )
    parser.add_argument("--disc", type=Path, default=DEFAULT_DISC_DIR, metavar="DIR")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, metavar="DIR")
    parser.add_argument("--scale", type=int, default=2, help="pixels per screen pixel (default 2)")
    args = parser.parse_args(argv)
    try:
        out = check_destination(args.out)
        archive, walk = load(Path(args.disc))
        if not Path(args.edits).is_file():
            raise MockupRefused(
                f"{args.edits} is not there; `./make.sh build-days` (or "
                f"`uv run python tools/vwf/build_prototype.py --edits-only`) writes it"
            )
        edit_set = load_edit_set(args.edits)
        sheet = font_sheet(archive, edit_set)
        layout = layout_of(edit_set)
    except (
        MockupRefused,
        BuildRefused,
        vwf.BuildRefused,
        PacketRefused,
        ArchiveError,
        SiteError,
        OSError,
    ) as error:
        print(f"mockup: {error}", file=sys.stderr)
        return 2
    paths = translation_paths(args.sources or DEFAULT_SOURCES)
    tally = Drawn()
    for path in paths:
        drawn = draw_file(
            path,
            archive,
            walk,
            edit_set.encoder,
            cache(sheet.get),
            layout,
            out,
            frozenset(args.events),
            args.scale,
        )
        for name in ("scenes", "pages", "over", "skipped"):
            setattr(tally, name, getattr(tally, name) + getattr(drawn, name))
    print(
        f"mockup: {tally.scenes} scene(s), {tally.pages} page(s) drawn from "
        f"{len(paths)} file(s) into {out}; {tally.over} line(s) drawn red (over the band "
        f"or with no cell), {tally.skipped} with no text site"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
