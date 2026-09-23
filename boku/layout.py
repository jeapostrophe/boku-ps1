"""Breaking English into lines and pages, in pixels, for a box that does not wrap.

**The engine has no wrap logic.** A line that is too long is clipped at the right screen
edge, silently, with no wrap and nothing else disturbed — measured on Beetle PSX with a
56-character fixture (`research/vwf-prototype.md` § Measurements). So the line breaks are
*data*: this module puts them in, and `PIPE-06`'s lint measures the result in the same
pixels.

Three things it will not do quietly
-----------------------------------
* **Pages never move.** A voiced message's page breaks carry a frame countdown that turns
  the page in time with the clip (`research/text-format.md`, control word `0x8002`), and
  `0x8002` occurs *only* in voiced messages. So the English must have exactly the page
  count the original has, and each page keeps the original's operand. More pages than the
  original is a lint error naming both counts — never a page silently added, and never
  text moved across a break to make it fit.
* **Select boxes never change their line count.** `L` comes out of the executable
  (`g_select_lines`), not out of the data, so the options map 1:1 or it is an error.
* **Nothing is cut to fit** (README § "Who this is for"). A page that needs more lines
  than the box has, or a word wider than the box, is reported with its numbers; the
  English is returned unchanged and the build decides what to do about it.

The width function is the encoder's
-----------------------------------
`StockEncoder` spells English with the sheet's own full-width Latin cells, which every
surface steps at a fixed 14 px — that is what `boku trial` writes and what a build with no
renderer patch can draw. `CellMapEncoder` reads the character -> cell map and per-cell
advance that `TXT-05`'s font build emits (`tools/vwf/build_prototype.py`'s `manifest.json`
-> `cells`), which is the seam the variable-width renderer plugs into: nothing here knows
how that file is produced, only that it maps a character to a cell id and a pixel advance.

The one measurement worth restating, because it is a trap: **the English space is its own
cell** under the VWF build (id 10, advance 4) and glyph 0 stays the 14-px Japanese space.
Encoding English through NFKC of the stock table would spell it with glyph 0 and move
every word (`research/vwf-prototype.md`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import NamedTuple, Protocol
from unicodedata import category

from boku.arrays import COUNTED_CELLS
from boku.glyphs import (
    END_WORD,
    NEWLINE_WORD,
    PAD_WORD,
    PAGE_WORD,
    SHEET_SLOTS,
    GlyphTable,
    unencodable_by,
    words_of,
)
from boku.sites import page_waits
from boku.voice import subtitle_waits

STOCK_ADVANCE = 14
"""The dialogue's step per cell, 14 px, and what a `StockEncoder` charges by default. The
menus step less -- 12, or 10 on one help line -- which a `BoxSpec`'s `pitch` carries
(`research/data/text-boxes.tsv`)."""

AVERAGE_PX_PER_CHARACTER = 5.85
"""Measured over the prototype's sample lines (`research/vwf-prototype.md` § "Measurements
for TXT-07"). Only for estimates that need "about N characters a line"; the lint measures
the real thing."""

SPEECH_MARKS = {"「": "」", "『": "』"}
"""The marks the original draws around speech and narration, opening -> closing. The
translation text carries none (style guide § 9); `original_marks` reads which the Japanese
drew and `lay_out_message` puts them back around the English."""


class LayoutError(Exception):
    """A box specification or a cell map this module cannot work with."""


# --- encoders -----------------------------------------------------------------------------


class Encoder(Protocol):
    """Character -> (the cell that draws it, what the pen advances by).

    Two implementations ship: the stock glyph table, and the cell map `TXT-05`'s font
    build emits. A third — a baked OFL face — only has to answer the same two questions.
    """

    name: str

    def glyph(self, character: str) -> int | None:
        """The cell id that draws `character`, or `None` if this font has none."""

    def advance(self, character: str) -> int:
        """Pixels the pen moves after drawing it."""


@dataclass(frozen=True)
class StockEncoder:
    """The game's own sheet: full-width Latin cells, every one stepping `STOCK_ADVANCE`.

    The map is NFKC-derived inside `GlyphTable`, not transcribed, so it cannot drift from
    `research/data/glyph-table.tsv`. This is what `boku trial` drew "Hello, Boku!" with.
    """

    table: GlyphTable
    fixed_advance: int = STOCK_ADVANCE
    name: str = "stock glyph table"

    @classmethod
    def load(cls) -> StockEncoder:
        return cls(GlyphTable.load())

    def glyph(self, character: str) -> int | None:
        # ASCII through the NFKC map. The marks a message is dressed with are the sheet's
        # own cells, which the stock vertical renderer draws the right way up; no other
        # non-ASCII character is something English is spelled with.
        if character in SPEECH_MARKS or character in SPEECH_MARKS.values():
            return self.table.from_character.get(character)
        return self.table.to_glyph.get(character)

    def advance(self, character: str) -> int:
        return self.fixed_advance


@dataclass(frozen=True)
class CellMapEncoder:
    """A character -> cell map with a per-cell advance, as `TXT-05`'s font build emits it.

    The file is read, never imported: `tools/vwf/` builds the font and this package builds
    the image, and the cell map is the whole interface between them. Its shape is
    `{"cells": {"A": {"id": 292, "advance": 9}, ...}}`; a bare `{"A": {...}}` mapping is
    accepted too, so a hand-written map needs no wrapper.
    """

    cells: Mapping[str, tuple[int, int]]
    fixed_advance: int = STOCK_ADVANCE
    name: str = "cell map"

    @classmethod
    def from_json(cls, path: Path) -> CellMapEncoder:
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise LayoutError(f"{path}: {error}") from error
        return cls.from_document(document, Path(path).name)

    @classmethod
    def from_document(cls, document: object, where: str = "cell map") -> CellMapEncoder:
        """The same map from an already-parsed document, so a caller holding one — the
        `TXT-05` edit set — compares and measures without re-reading the file."""
        cells = document.get("cells", document) if isinstance(document, dict) else None
        if not isinstance(cells, dict) or not cells:
            raise LayoutError(
                f"{where} holds no `cells` map; a font build writes one character -> "
                f'{{"id": <cell>, "advance": <pixels>}} per entry'
            )
        out: dict[str, tuple[int, int]] = {}
        for character, entry in cells.items():
            if len(character) != 1 or not isinstance(entry, dict) or "id" not in entry:
                raise LayoutError(f"{where}: {character!r} -> {entry!r} is not a cell entry")
            out[character] = (int(entry["id"]), int(entry.get("advance", STOCK_ADVANCE)))
        return cls(out, name=f"cell map {where}")

    def glyph(self, character: str) -> int | None:
        entry = self.cells.get(character)
        return None if entry is None else entry[0]

    def advance(self, character: str) -> int:
        entry = self.cells.get(character)
        return self.fixed_advance if entry is None else entry[1]


def unencodable(encoder: Encoder, text: str) -> list[str]:
    """Characters `text` needs and this font has no cell for, in order, without repeats."""
    return unencodable_by(lambda character: encoder.glyph(character) is not None, text)


def _cell(encoder: Encoder, character: str) -> int:
    """The cell for one character; the blank cell when the font has none.

    A missing character is already a reported problem, and a `LaidOut` that carries one is
    never written — the substitution exists so that the *rest* of the report (widths, line
    breaks, how far over it is) can still be computed and shown.
    """
    cell = encoder.glyph(character)
    return PAD_WORD if cell is None else cell


def measure(encoder: Encoder, run: str) -> int:
    """Pixel width of one run of text, which is the sum of its advances."""
    return sum(encoder.advance(character) for character in run)


# --- the sheet's own glyphs, in an array item ------------------------------------------------

GLYPH_TOKEN = re.compile(r"\{G:(\d+)\}")
"""`{G:n}`: one cell of the game's own sheet, by id (`boku.glyphs`' token)."""


@cache
def _sheet() -> GlyphTable:
    return GlyphTable.load()


SHEET_CELL_PROBLEMS = ("draws no cell", "not the sheet's own glyph", "names no cell")
"""What each of `sheet_cells`' problems says, so a lint files them all as `unencodable`."""


class SheetCells(NamedTuple):
    """An array item's text as cells, the pixels they step, and what could not be drawn."""

    cells: tuple[int, ...]
    width: int
    problems: tuple[str, ...]


def sheet_cells(encoder: Encoder, text: str, pitch: int = 0) -> SheetCells:
    """`text` in `encoder`'s cells, falling back to the game's own sheet for the rest.

    The menus draw the sheet's button glyphs, arrows and rules beside the English, so an
    item may name one as `{G:n}`, or write a symbol the sheet draws and the English font
    does not (○ × ↓) -- a symbol only: a kana or kanji is Japanese left untranslated.
    Either is that cell, stepped at the surface's stock `pitch` -- what the walkers advance
    a cell that is not English (`asm/walkers.asm`, `vwf_lookup_at`). A cell the cell map
    has redrawn as an English letter no longer draws the sheet's glyph, so naming it is a
    problem, not a passthrough.
    """  # noqa: RUF002
    stock = pitch or getattr(encoder, "fixed_advance", STOCK_ADVANCE)
    redrawn = (
        {cell: character for character, (cell, _) in encoder.cells.items()}
        if isinstance(encoder, CellMapEncoder)
        else {}
    )
    cells: list[int] = []
    width = 0
    missing: list[str] = []
    problems: list[str] = []

    def own(cell: int) -> None:
        nonlocal width
        if cell in redrawn:
            problems.append(
                f"cell {cell} draws {redrawn[cell]!r} in the {encoder.name}, not the sheet's "
                f"own glyph"
            )
        cells.append(cell)
        width += stock

    position = 0
    for match in (*GLYPH_TOKEN.finditer(text), None):
        for character in text[position : match.start() if match else len(text)]:
            cell = encoder.glyph(character)
            if cell is not None:
                cells.append(cell)
                width += encoder.advance(character)
            elif character in _sheet().from_character and category(character)[0] == "S":
                own(_sheet().from_character[character])
            else:
                if character not in missing:
                    missing.append(character)
                cells.append(PAD_WORD)
                width += encoder.advance(character)
        if match:
            cell = int(match.group(1))
            if cell < SHEET_SLOTS:
                own(cell)
            else:
                problems.append(
                    f"{match.group(0)} names no cell; the sheet holds ids 0-{SHEET_SLOTS - 1}"
                )
                cells.append(PAD_WORD)
                width += stock
            position = match.end()
    if missing:
        problems.insert(0, f"the {encoder.name} draws no cell for {''.join(missing)!r}")
    return SheetCells(tuple(cells), width, tuple(problems))


# --- the box ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class BoxSpec:
    """What one text surface can hold, in pixels and lines.

    The dialogue band was measured on the running prototype
    (`research/vwf-prototype.md` § "Measurements for `TXT-07`"); the menu surfaces measured
    so far are `research/data/text-boxes.tsv`'s rows (`boku.boxes`).
    """

    width: int
    """Usable pixels per line — the pen's left margin mirrored on the right."""
    lines: int
    """Lines that draw cleanly on one page."""
    guarded_from: int = 0
    """First line (1-based) the next-page pencil sits on; 0 = no guard."""
    guarded_width: int = 0
    """What a guarded line has to fit in instead, because the pencil occupies the rest."""
    name: str = "box"
    pitch: int = 0
    """The surface's own step per cell, which is the width of every glyph of a font that
    has none of its own (the stock sheet, `StockEncoder`); 0 = the encoder's."""

    def width_of_line(self, number: int) -> int:
        """The usable width of line `number` (1-based), pencil included."""
        if self.guarded_from and number >= self.guarded_from:
            return self.guarded_width
        return self.width


DIALOGUE_BAND = BoxSpec(
    width=272,
    lines=3,
    guarded_from=3,
    guarded_width=238,
    name="the dialogue band",
)
"""The band `TXT-05` draws in, as Jay ruled it (2026-09-20, the smallest of the mock-ups)
and as moved up for the display (2026-09-21): 37 rows from y = 191, pen (24, 193), line
pitch 11 — three lines whose cells end at row 226, inside the ~232 rows DuckStation's
default crop shows and a TV's title-safe margin; 272 usable px with the left margin
mirrored. The next-page pencil is moved to the band's last 11 rows at x >= 267, which
crosses line 3 only, so that line must end before x ~ 262 = 24 + 238.
`research/vwf-prototype.md` § "The ruled band"."""


SELECT_ROW = BoxSpec(width=248, lines=1, name="a select row")
"""One option of a SELECT as `TXT-05` draws it: a row from `SEL_X` (48) to the dialogue
pen's right margin, 320 - 24 - 48 px, for a renderer built with the default geometry
(`build_prototype.Layout.select_width`, which `tests/test_layout.py` ties this to). A build
with its own `--sel-x`/`--pen-x` records the row it drew in its edit set, and
`select_row_of` reads that instead. A row cannot wrap; the box is measured from the text,
so nothing else caps it (`research/vwf-prototype.md` § "SELECT")."""


def select_row_of(document: object) -> BoxSpec:
    """The select row a `TXT-05` edit set was assembled with (`layout.select_width`);
    `SELECT_ROW` when the document records none -- a cell map with no layout of its own."""
    layout = document.get("layout") if isinstance(document, dict) else None
    width = layout.get("select_width") if isinstance(layout, dict) else None
    if width is None:
        return SELECT_ROW
    if not isinstance(width, int) or width <= 0:
        raise LayoutError(f"the edit set's layout.select_width is {width!r}, not a pixel count")
    return replace(SELECT_ROW, width=width)


SPEAKER_LABELS = frozenset(
    {
        "Boku",
        "Uncle",
        "Aunt",
        "Moe",
        "Shirabe",
        "Guts",
        "Fat",
        "Specs",
        "Father",
        "Monk",
        "Boy",
        "Woman",
        "Saori",
        "Narrator",
        "All",
    }
)
"""The English speaker labels of `translation/style-guide.md` § 9, which is their one home;
`tests/test_build.py` derives its copy from that sentence so the two cannot drift."""

UNLABELLED_SPEAKERS = frozenset({"", "(unlabelled)"})
"""Speaker fields that name nobody: an examine description, or a row left blank."""


def speaker_label(speaker: str) -> tuple[str, list[str]]:
    """The label run drawn for a translation row's speaker field, and what is wrong with it.

    A chorus row lists its members (`"Shirabe, Moe, Aunt"`) and is drawn as listed — the
    original never labels a chorus, so `lay_out` only asks for one when the Japanese did
    (`original_marks`). Every name must be a label of the style guide: a
    misspelling would otherwise be drawn on screen exactly as typed.
    """
    if speaker in UNLABELLED_SPEAKERS:
        return "", []
    unknown = [name for name in speaker.split(", ") if name not in SPEAKER_LABELS]
    return speaker, unknown


# --- laying one line out ------------------------------------------------------------------------


@dataclass(frozen=True)
class LaidOut:
    """One line's words, the shape they were given, and every lint it failed."""

    line_id: str
    words: tuple[int, ...]
    pages: tuple[tuple[str, ...], ...]
    """The text as broken: one tuple of lines per page."""
    widths: tuple[tuple[int, ...], ...]
    problems: tuple[str, ...]
    """Empty means it fits. A problem is never fixed by shortening the English."""

    @property
    def fits(self) -> bool:
        return not self.problems

    @property
    def longest(self) -> int:
        return max((w for page in self.widths for w in page), default=0)


def wrap(encoder: Encoder, text: str, box: BoxSpec, first_line: int = 1) -> list[str]:
    """Greedy word wrap by pixel width. `\\n` in `text` is a break the translator asked for.

    Greedy, not balanced: the engine draws left to right from a fixed pen, so the only
    thing a smarter algorithm would buy is evenness, and evenness is a typographic choice
    that is not this unit's to make.

    The speaker label needs no special case here: `lay_out_message` puts it in front of
    page 1's first word as text, so it is measured like any other run on that line.
    `LabelledBox` is the lint's form of the same rule, narrowing line 1 by the label's
    pixels over decoded text rather than over the words a build inserts.
    """
    out: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if line and measure(encoder, candidate) > box.width_of_line(first_line + len(out)):
                out.append(line)
                line = word
            else:
                line = candidate
        out.append(line)
    return out


def lay_out_message(
    line_id: str,
    pages: Sequence[str],
    original: bytes,
    encoder: Encoder,
    box: BoxSpec = DIALOGUE_BAND,
    *,
    indent_continuations: bool = False,
    opening: str = "",
    closing: str = "",
) -> LaidOut:
    """One message: wrapped, paginated against the original's timers, encoded to words.

    `opening` is the run drawn in front of page 1's first word — the speaker label and
    the opening mark, `Uncle「` — and `closing` the run drawn after the last page's last
    word, `」`. They are the original's style (style guide § 9, Q7) put back by the
    inserter as text: the renderer draws them like any other cells, so it needs no
    label path, and the wrap measures them where they really are, on line 1 of page 1
    and the last line of the last page and nowhere else. The English itself carries no
    marks; `original_marks` reads which ones the Japanese drew.

    `indent_continuations` re-emits the blank cell the Japanese puts after every `0x8001`.
    It is **off by default and that is deliberate**: `research/text-format.md` measured
    that the word is the authoring tool's one-cell indent under the `speaker「` opening and
    *not* a guard the engine requires — `dialog_draw` resumes at it and hands it to
    `glyph_draw` like any other cell — and the running prototype confirmed English reads
    correctly without it, wrapping flush to the pen (`research/vwf-prototype.md` § "Wrap
    and indent"). Turning it on costs 14 px at the head of every continuation line.
    """
    problems: list[str] = []
    waits = page_waits(original)
    if len(pages) != len(waits) + 1:
        problems.append(
            f"{line_id}: the original has {len(waits) + 1} page(s) and the English "
            f"{len(pages)}; pages turn on the voice clip's own frame countdown, so the "
            f"count is fixed and text may not move across a break"
        )
    return _paginate(
        line_id,
        pages,
        waits,
        encoder,
        box,
        problems,
        indent_continuations=indent_continuations,
        opening=opening,
        closing=closing,
    )


def lay_out_subtitle(
    line_id: str,
    pages: Sequence[str],
    ticks: int,
    encoder: Encoder,
    box: BoxSpec = DIALOGUE_BAND,
) -> LaidOut:
    """A voice-only clip's subtitle (`VO-02`): the translator's pages, timed to the clip.

    There is no original to follow — the entry had no text — so the page count is the
    translator's and each page's operand is its share of the clip's `ticks`
    (`boku.voice.subtitle_waits`). Drawn undressed: the clip has no label or marks on the
    disc to put back (`original_marks` reads them off Japanese text that does not exist).
    """
    return _paginate(line_id, pages, subtitle_waits(pages, ticks), encoder, box, [])


def _paginate(
    line_id: str,
    pages: Sequence[str],
    waits: Sequence[int],
    encoder: Encoder,
    box: BoxSpec,
    problems: list[str],
    *,
    indent_continuations: bool = False,
    opening: str = "",
    closing: str = "",
) -> LaidOut:
    """Wrap each page into the box, lint it, and encode it with `waits` after each break."""
    dressed = list(pages)
    if dressed:
        dressed[0] = opening + dressed[0]
        dressed[-1] = dressed[-1] + closing
    missing = unencodable(encoder, "".join(dressed))
    if missing:
        problems.append(f"{line_id}: the {encoder.name} draws no cell for {''.join(missing)!r}")
    broken = [wrap(encoder, page, box) for page in dressed]
    widths = [[measure(encoder, line) for line in page] for page in broken]
    for number, (page, page_widths) in enumerate(zip(broken, widths, strict=True), start=1):
        if len(page) > box.lines:
            problems.append(
                f"{line_id} page {number}: {len(page)} lines in {box.name}, which holds "
                f"{box.lines}; the fix is another page or a wider box, never a shorter line"
            )
        for index, width in enumerate(page_widths, start=1):
            limit = box.width_of_line(index)
            if width > limit:
                problems.append(
                    f"{line_id} page {number} line {index}: {width} px in {limit}, "
                    f"{width - limit} over ({page[index - 1]!r} does not break)"
                )
    words: list[int] = []
    for number, page in enumerate(broken):
        if number:
            words += [PAGE_WORD, waits[number - 1] if number <= len(waits) else 0]
        for index, line in enumerate(page):
            if index:
                words.append(NEWLINE_WORD)
            if index and indent_continuations:
                words.append(PAD_WORD)
            words += [_cell(encoder, c) for c in line]
    words.append(END_WORD)
    return LaidOut(
        line_id=line_id,
        words=tuple(words),
        pages=tuple(tuple(p) for p in broken),
        widths=tuple(tuple(w) for w in widths),
        problems=tuple(problems),
    )


def holds(box: BoxSpec | None, words: Sequence[int]) -> int:
    """Lines an item may take in `box`: the box's own count for an item ending in `0x8000`
    -- an **E** item, which `text_nth` finds by that word, so a `0x8001` inside it moves
    nothing and `text_draw_h` starts a line there -- and 1 for any other."""
    return box.lines if box is not None and words and words[-1] == END_WORD else 1


def lay_out_array(
    line_id: str,
    text: str,
    original: bytes,
    encoder: Encoder,
    size: int | None,
    box: BoxSpec | None = None,
) -> LaidOut:
    """One item of a code-file array: the English, then the item's own terminator.

    An array has **no slack** — the next symbol starts where it ends — and its neighbours
    are found by scanning past its control words, so an item is replaced at
    equal-or-smaller size and its terminator is carried straight over
    (`research/text-format.md` § "Text arrays in code files"). A grown array moves whole
    instead (`boku.array_relocate`): the build passes `size=None` for one that can, and
    the item's own bytes for one that cannot.

    `box` is the surface's measured frame (`boku.boxes`, `research/data/text-boxes.tsv`,
    `PLAN TXT-07`); an item whose surface has no measured box yet is held to its bytes
    alone. Where the box `holds` more than one line the English is wrapped to it by
    pixels, a `0x8001` at each break, and the item keeps its own terminator. Any other
    item with a control word inside it, or a raw row with none, is drawn by a surface
    nobody has measured, so where English breaks is not known -- it is reported rather
    than guessed at. A code-file menu (an **S** array)
    is not this function's: it is a `[SEL]` row, `lay_out_array_select`.
    """
    words = words_of(original)
    controls = [index for index, word in enumerate(words) if word & 0x8000]
    problems: list[str] = []
    if box is not None and box.pitch and isinstance(encoder, StockEncoder):
        encoder = replace(encoder, fixed_advance=box.pitch)
    wraps = holds(box, words) > 1
    if controls != [len(words) - 1] and not wraps:
        return LaidOut(
            line_id=line_id,
            words=words,
            pages=((text,),),
            widths=((measure(encoder, text),),),
            problems=(
                f"{line_id}: this array item holds {len(controls)} control word(s) and is "
                f"drawn as a group; how English divides between its lines is undecided, so "
                f"it is left in Japanese",
            ),
        )
    if not text:
        problems.append(
            f"{line_id}: no English was given for this array item; writing it empty would "
            f"blank an item the game still draws"
        )
    lines = wrap(encoder, text, box) if wraps else [text]
    pitch = box.pitch if box is not None else 0
    laid_lines = [sheet_cells(encoder, line, pitch) for line in lines]
    for drawn in dict.fromkeys(p for laid in laid_lines for p in laid.problems):
        problems.append(f"{line_id}: {drawn}")
    widths = tuple(laid.width for laid in laid_lines)
    if box is not None and len(lines) > box.lines:
        problems.append(
            f"{line_id}: {text!r} takes {len(lines)} lines and {box.name} holds {box.lines}"
        )
    for line, width in zip(lines, widths, strict=True):
        if box is not None and width > box.width:
            problems.append(
                f"{line_id}: {line!r} is {width} px and {box.name} holds {box.width}, "
                f"{width - box.width} over"
            )
    cells: list[int] = []
    for number, laid in enumerate(laid_lines):
        if number:
            cells.append(NEWLINE_WORD)
        cells += laid.cells
    new = (*cells, words[-1])
    counted = COUNTED_CELLS.get(line_id)
    if counted is not None:
        digits = {sheet_cells(encoder, digit).cells[0] for digit in "0123456789"}
        if not all(cell in digits for cell in new[counted.start : counted.stop]):
            problems.append(
                f"{line_id}: the program writes its count into cells {counted.start}-"
                f"{counted.stop - 1} before drawing, so the English has digits there"
            )
    if size is not None and 2 * len(new) > size:
        problems.append(
            f"{line_id}: {text!r} needs {2 * len(new)} bytes and the array item holds "
            f"{size}, {2 * len(new) - size} over. An array has no slack, and this one "
            f"cannot move (boku.array_relocate)"
        )
    return LaidOut(
        line_id=line_id,
        words=new,
        pages=(tuple(lines),),
        widths=(widths,),
        problems=tuple(problems),
    )


@dataclass(frozen=True)
class AnswerPair:
    """The card screens' two answers: one row of raw glyphs that `TITLE.OVL`'s drawer
    (`0x8007CF7C`) splits after a code constant and bounds by another.

    The translation writes it `Yes | No` (`translation/days/README.md`), and the build
    rewrites the two constants from it -- `SPLIT` is the index of the first answer's last
    glyph, `COUNT` how many glyphs are drawn -- so the renderer patch (`asm/title.asm`
    surface 18) restates neither. Every address here is checked against the disc by
    `tests/test_real_boxes.py`.
    """

    line_id: str
    member: str
    split_ram: int
    stock_split: int
    """`addiu v0,zero,1`: the retail word, which each rewrite checks is there first."""
    count_ram: int
    stock_count: int
    """`slti v0,v0,5`."""
    first_x: int
    second_x: int


ANSWER_PAIR = AnswerPair(
    line_id="title@7A78.0",
    member="TITLE.OVL",
    split_ram=0x8007D03C,
    stock_split=0x24020001,
    count_ram=0x8007D064,
    stock_count=0x28420005,
    first_x=0x70,
    second_x=0xAC,
)


def lay_out_answer_pair(
    line_id: str,
    text: str,
    original: bytes,
    encoder: Encoder,
    right: int,
    pair: AnswerPair = ANSWER_PAIR,
) -> LaidOut:
    """`Yes | No` as the drawer takes it: both answers back to back in the row's own cells,
    each within its span -- the first up to where the second starts, the second up to
    `right`, the panel's edge (the row's `text-boxes.tsv` box). Unused cells are padding
    the rewritten `COUNT` never reaches."""
    fields = [field.strip() for field in text.split("|")]
    cells = len(words_of(original))
    problems: list[str] = []
    if len(fields) != 2 or not all(fields):
        problems.append(
            f"{line_id}: {text!r} is not two answers; the row is written `Yes | No`, the "
            f"first answer, ` | `, then the second"
        )
        fields = [*fields, "", ""][:2]
    first, second = fields
    missing = unencodable(encoder, first + second)
    if missing:
        problems.append(f"{line_id}: the {encoder.name} draws no cell for {''.join(missing)!r}")
    if len(first) + len(second) > cells:
        problems.append(
            f"{line_id}: {first!r} and {second!r} take {len(first) + len(second)} cells and "
            f"the row holds {cells}"
        )
    widths = (measure(encoder, first), measure(encoder, second))
    for answer, width, room in (
        (first, widths[0], pair.second_x - pair.first_x),
        (second, widths[1], right - pair.second_x),
    ):
        if width > room:
            problems.append(
                f"{line_id}: {answer!r} is {width} px and its span holds {room}, "
                f"{width - room} over"
            )
    words = [_cell(encoder, c) for c in first + second][:cells]
    words += [PAD_WORD] * (cells - len(words))
    return LaidOut(
        line_id=line_id,
        words=tuple(words),
        pages=((first, second),),
        widths=(widths,),
        problems=tuple(problems),
    )


def answer_pair_code(laid: LaidOut) -> dict[int, int]:
    """The two instruction words `laid` needs in `ANSWER_PAIR.member`, by RAM address."""
    first, second = laid.pages[0]
    pair = ANSWER_PAIR
    return {
        pair.split_ram: (pair.stock_split & ~0xFFFF) | (len(first) - 1),
        pair.count_ram: (pair.stock_count & ~0xFFFF) | (len(first) + len(second)),
    }


MENU_IS_SEL = "a menu held in the program; it is written as a [SEL] row, one field per line"
"""What the lint and the build say of a code-file menu written as a plain row."""


def menu_lines(original: bytes) -> int:
    """How many lines a select's words draw: one `0x8001` ends each."""
    return words_of(original).count(NEWLINE_WORD)


def lay_out_array_select(
    line_id: str,
    lines: Sequence[str],
    original: bytes,
    encoder: Encoder,
    size: int | None,
    row: BoxSpec = SELECT_ROW,
) -> LaidOut:
    """A select held in a code file (an **S** array): `lay_out_select`, in its own bytes.

    `select_open_ptr` opens it like an event select, so its lines are the original's
    (`menu_lines`, which is `g_select_lines`' count) and are measured like any select's
    (`research/text-outside-events.md` § "What changed against `REC-03`'s array table").
    Like every array item it has no slack: `size` refuses growth, and `None` is a menu whose
    array the build moves when it grows (`boku.array_relocate`).
    """
    laid = lay_out_select(line_id, lines, original, (menu_lines(original), 0), encoder, row)
    need = 2 * len(laid.words)
    if size is None or need <= size:
        return laid
    return replace(
        laid,
        problems=(
            *laid.problems,
            f"{line_id}: {' | '.join(lines)!r} needs {need} bytes and the array item holds "
            f"{size}, {need - size} over. An array has no slack, and this one cannot move "
            f"(boku.array_relocate)",
        ),
    )


def lay_out_select(
    line_id: str,
    options: Sequence[str],
    original: bytes,
    shape: tuple[int, int],
    encoder: Encoder,
    row: BoxSpec = SELECT_ROW,
    prompts: Sequence[str] = (),
) -> LaidOut:
    """One select box: `shape` is `(lines, prompt lines)` read out of the executable.

    Every line ends with `0x8001` and there is no terminator
    (`research/text-format.md` § SELECT). A select line cannot wrap — a second line would
    be a second option — so an over-wide option is a lint error, not a break.
    """
    lines, first = shape
    problems: list[str] = []
    if len(options) != lines - first:
        problems.append(
            f"{line_id}: the box draws {lines - first} option(s) and the translation gives "
            f"{len(options)}; the count is in g_select_lines and options map 1:1"
        )
    if len(prompts) != first:
        problems.append(
            f"{line_id}: the box opens with {first} prompt line(s) and the translation "
            f"gives {len(prompts)}"
        )
    text = list(prompts) + list(options)
    missing = unencodable(encoder, "".join(text))
    if missing:
        problems.append(f"{line_id}: the {encoder.name} draws no cell for {''.join(missing)!r}")
    widths = [measure(encoder, line) for line in text]
    for index, (line, width) in enumerate(zip(text, widths, strict=True), start=1):
        if "\n" in line:
            problems.append(f"{line_id} line {index}: a select line cannot be broken")
        if width > row.width:
            problems.append(
                f"{line_id} line {index}: {width} px in {row.width}, {width - row.width} "
                f"over ({line!r}); a select line cannot wrap"
            )
    words: list[int] = []
    for line in text:
        words += [_cell(encoder, c) for c in line.replace("\n", "")]
        words.append(NEWLINE_WORD)
    if len(text) != lines:
        # Without the right number of lines the words would not describe this box at all;
        # `boku.reinsert.check_words` refuses them, so say so here rather than there.
        words = list(words_of(original))
    return LaidOut(
        line_id=line_id,
        words=tuple(words),
        pages=(tuple(text),),
        widths=(tuple(widths),),
        problems=tuple(problems),
    )


# --- the speaker label and the marks drawn around the English -----------------------------------
#
# One rule, three readers of it. `original_marks` says what the Japanese drew;
# `lay_out_message` puts the same runs back as text while a build lays words out; and
# `LabelledBox` charges their pixels while the lint measures decoded text. They live
# together so neither the marks nor their width can be decided twice.

LABEL_MARKS = "「"
"""The opening mark the original draws after a speaker label. Style guide § 9 leaves the
choice between this and an English quotation mark to the dialogue band; both are one
cell, so which one is charged does not change the verdict."""


class Marks(NamedTuple):
    """What the Japanese drew around one message, read from its words."""

    opening: str
    """`「`, `『`, or empty when page 1's first line opens with none."""
    closing: str
    """The closing mark of `opening`, or empty — a split utterance has none (style guide
    § 9: `E1405.1`-`.2`), and a mark that does not close `opening` is a `problem`."""
    labelled: bool
    """Glyphs stand before the opening mark: a speaker label, `おじ「`."""
    problem: str = ""
    """Why these marks could not be read as a pair, when they could not. The English is
    dressed with what was read and the caller reports this; nothing is substituted."""


def original_marks(original: bytes, table: GlyphTable) -> Marks:
    """The marks and label the Japanese drew, so the English can be dressed the same way.

    A labelled message opens `<speaker>「`; an examine message opens `「` with nothing in
    front of it; narration opens `『`. The closing mark is the last cell before the end
    word, when there is one — and it is `opening`'s own closer or it is a problem, because
    `「…』` dressed as `「…』` is a mark the original does not draw there and `「…」` is a
    guess at which half was wrong.

    The bytes are the site's own: `boku.build` passes what the walk holds and `boku.lint`
    what `boku.script_store.original_bytes` reconstructs, so both dress a line the same.
    """
    words = words_of(original)
    ids = {table.from_character[mark]: mark for mark in SPEECH_MARKS}
    closers = {table.from_character[mark]: mark for mark in SPEECH_MARKS.values()}
    opening, labelled = "", False
    for index, word in enumerate(words):
        if word & 0x8000:
            break
        if word in ids:
            opening, labelled = ids[word], index > 0
            break
    body = words[: words.index(END_WORD)] if END_WORD in words else words
    closing = closers.get(body[-1], "") if body else ""
    if opening and closing and SPEECH_MARKS[opening] != closing:
        return Marks(
            opening,
            "",
            labelled,
            f"the Japanese opens {opening} and closes {closing}; the English would be "
            f"dressed with marks the original does not pair",
        )
    return Marks(opening, closing, labelled)


def label_allowance(encoder: Encoder, speaker: str, marks: str) -> int:
    """Pixels the label takes off the head of page 1's first line."""
    return measure(encoder, f"{speaker}{marks}")


@dataclass(frozen=True)
class LabelledBox(BoxSpec):
    """`box` with its **first line only** narrowed by the label drawn in front of it.

    `BoxSpec` narrows the tail of a line -- the next-page pencil, which sits on the last
    one. The label narrows the head, and only of page 1's first line, so it cannot be
    subtracted from `width`: that takes the pixels off every line of the page and reports
    a page that fits as one line too many.
    """

    reserve: int = 0

    def width_of_line(self, number: int) -> int:
        width = super().width_of_line(number)
        return max(width - self.reserve, 1) if number == 1 else width
