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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from boku.glyphs import (
    END_WORD,
    NEWLINE_WORD,
    PAD_WORD,
    PAGE_WORD,
    GlyphTable,
    unencodable_by,
    words_of,
)
from boku.sites import page_waits

STOCK_ADVANCE = 14
"""Every fixed-pitch surface steps 14 px per cell (`research/vwf-prototype.md`)."""


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


# --- the box ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class BoxSpec:
    """What one text surface can hold, in pixels and lines.

    Measured for the dialogue band on the running prototype
    (`research/vwf-prototype.md` § "Measurements for `TXT-07`"); every other surface is
    still to be measured, which is what `PLAN TXT-07` is.
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

    def width_of_line(self, number: int) -> int:
        """The usable width of line `number` (1-based), pencil included."""
        if self.guarded_from and number >= self.guarded_from:
            return self.guarded_width
        return self.width


DIALOGUE_BAND = BoxSpec(
    width=272,
    lines=4,
    guarded_from=4,
    guarded_width=238,
    name="the dialogue band",
)
"""The band `TXT-04`/`TXT-05` draw in, measured on Beetle PSX at pen (24, 176), pitch 13:
272 usable px, four clean lines, and the next-page pencil at x >= 267 on rows 220-229, so a
fourth line must end before x ~ 262 = 24 + 238 (`research/vwf-prototype.md`)."""


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


def wrap(
    encoder: Encoder, text: str, box: BoxSpec, first_line: int = 1, reserve: int = 0
) -> list[str]:
    """Greedy word wrap by pixel width. `\\n` in `text` is a break the translator asked for.

    Greedy, not balanced: the engine draws left to right from a fixed pen, so the only
    thing a smarter algorithm would buy is evenness, and evenness is a typographic choice
    that is not this unit's to make.

    `reserve` is pixels taken off the head of **line 1 only** — the speaker label drawn in
    front of it. It cannot be subtracted from `box.width`, which would take the pixels off
    every line of the page and report a page that fits as one line too many;
    `boku.lint.LabelledBox` is the lint's form of the same rule, measured over decoded
    text rather than over the words a build inserts.
    """
    out: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            limit = box.width_of_line(first_line + len(out))
            if first_line + len(out) == 1:
                limit = max(limit - reserve, 1)
            if line and measure(encoder, candidate) > limit:
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
    reserve: int = 0,
) -> LaidOut:
    """One message: wrapped, paginated against the original's timers, encoded to words.

    `reserve` is the speaker label's pixels, charged to **page 1's first line only** and
    to no other (`wrap`). It is charged for a label **nothing draws yet**: `asm/` has no
    speaker-label path and this function never emits `entry.speaker`, so today's image
    loses the speaker name and wraps page 1's first line a word early. That is the
    deliberate trade while `TXT-05`'s label design is open — the lint already charges the
    same pixels (`boku.lint` § "The label on line 1"), and a build that measured without
    them would pass lines the lint fails and, the day the label is drawn, run the English
    underneath it. `--no-label` measures the bare English on both sides.

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
    missing = unencodable(encoder, "".join(pages))
    if missing:
        problems.append(f"{line_id}: the {encoder.name} draws no cell for {''.join(missing)!r}")
    # The label opens the message, so its pixels are page 1's alone.
    broken = [
        wrap(encoder, page, box, reserve=reserve if number == 0 else 0)
        for number, page in enumerate(pages)
    ]
    widths = [[measure(encoder, line) for line in page] for page in broken]
    if reserve and widths and widths[0]:
        # The label's pixels are really on that line, so a finding quotes the real width
        # against the real limit -- the same arithmetic `boku.lint.fit_page` reports with.
        widths[0][0] += reserve
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


def lay_out_array(
    line_id: str,
    text: str,
    original: bytes,
    encoder: Encoder,
    size: int,
) -> LaidOut:
    """One item of a code-file array: the English, then the item's own terminator.

    An array has **no slack** — the next symbol starts where it ends — and its neighbours
    are found by scanning past its control words, so an item is replaced at
    equal-or-smaller size and its terminator is carried straight over
    (`research/text-format.md` § "Text arrays in code files"). Growth means relocating the
    array and patching the `lui`/`addiu` pairs that reach it, which is not this unit's.

    Only an item with a single trailing control word is laid out. A group drawn whole (an
    **S** array: a select or a line list inside the executable) is several lines in one
    site, and how English is divided between them is a decision nobody has made — so it is
    reported rather than guessed at.

    There is no pixel lint here: the 20 fixed-pitch surfaces these arrays feed have not
    been measured (`PLAN TXT-07`), so the only limit that is known is the byte length.
    """
    words = words_of(original)
    controls = [index for index, word in enumerate(words) if word & 0x8000]
    problems: list[str] = []
    if controls != [len(words) - 1]:
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
    missing = unencodable(encoder, text)
    if missing:
        problems.append(f"{line_id}: the {encoder.name} draws no cell for {''.join(missing)!r}")
    new = (*(_cell(encoder, character) for character in text), words[-1])
    if 2 * len(new) > size:
        problems.append(
            f"{line_id}: {text!r} needs {2 * len(new)} bytes and the array item holds "
            f"{size}, {2 * len(new) - size} over. An array has no slack; relocating it and "
            f"repointing the lui/addiu pairs that reach it is not this unit's (PLAN PIPE-03)"
        )
    return LaidOut(
        line_id=line_id,
        words=new,
        pages=((text,),),
        widths=((measure(encoder, text),),),
        problems=tuple(problems),
    )


def lay_out_select(
    line_id: str,
    options: Sequence[str],
    original: bytes,
    shape: tuple[int, int],
    encoder: Encoder,
    box: BoxSpec = DIALOGUE_BAND,
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
        if width > box.width:
            problems.append(
                f"{line_id} line {index}: {width} px in {box.width}, {width - box.width} "
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
