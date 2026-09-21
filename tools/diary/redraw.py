#!/usr/bin/env python3
"""Prototype of the PROGRAMMATIC path for the 94 picture-diary pages (PLAN `GFX-02`).

`GFX-02` has to choose, per texture category, between an image model redrawing a texture in
English and a Claude-drawn subtitle composited on top. The diary is the third option and over
half the work: its prose sits in ruled *vertical* columns on flat paper under the crayon
drawing, so a program can blank that panel, draw horizontal rules and typeset the English —
no image model, no colour decision, and the entry text lives in the translation files.

This script is that option, end to end for one page: export the page TIM through
`boku.textures`, measure the panel from the pixels, rebuild it, typeset an English entry in
either of two 1-bit faces, and hand the result back through `boku.textures` so the edit
becomes verified byte edits and (with `build`) a patched image.

It is a **prototype under `tools/`**, so it takes two liberties the package does not: it runs
under `uv run --no-project --with pillow` (Pillow is used only to scale and stack the
comparison sheet — every pixel that reaches a TIM is written by this file), and its measured
geometry is stated as constants that `measure` re-derives from the disc and checks.

Nothing it writes is committed: every output is a diary page's own pixels, so it lands under
the gitignored `work/diary/` and `build/diary/` (README principle 2).

    uv run --no-project --with pillow python tools/diary/redraw.py measure
    uv run --no-project --with pillow python tools/diary/redraw.py render --page 001
    uv run --no-project --with pillow python tools/diary/redraw.py compare --page 001
    uv run --no-project --with pillow python tools/diary/redraw.py build --page 001
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from boku.archive import Archive  # noqa: E402
from boku.textures import Texture, inventory, patches_for, to_png  # noqa: E402
from boku.tim import Tim  # noqa: E402

WORK_DIR = REPO_ROOT / "work/diary"
BUILD_DIR = REPO_ROOT / "build/diary"
DISC_DIR = REPO_ROOT / "disc"
GLYPH_TSV = REPO_ROOT / "research/data/glyph-table.tsv"
GALMURI_BDF = REPO_ROOT / "reference/fonts/galmuri/Galmuri9.bdf"
FONT_SHEET_ID = "_DATA_ONMEM.BIN__004aa0"
"""The one glyph sheet on the disc (`research/font.md`): `ONMEM.BIN` child 2."""

PAGE_W, PAGE_H = 240, 192


# --- the panel, as measured ----------------------------------------------------------------
#
# Every number here came out of the pixels of all 94 pages and `measure` re-derives it; see
# `research/diary-redraw.md` for how. They are constants rather than a per-run measurement
# because a redraw that silently re-measured a page whose panel is different would typeset
# English over a drawing.


@dataclass(frozen=True)
class Panel:
    """Where the ruled text panel is on a diary page, in page pixels."""

    top: int = 113
    """First paper row, on all 94 pages."""
    repaint_top: int = 117
    """First row the English may occupy. The four rows above it are blanked too — the
    Japanese columns start at 114 — but nothing is *drawn* there, because the crayon
    drawing's V-notch at the book's fold dips as far as row 116 on 56 of the 94 pages."""
    bottom: int = 185
    """Last paper row; 186 is the page's bottom edge and 187+ is the desk under the book."""
    left: int = 1
    """Column 0 is the page's own left edge, a darker line: not ours to repaint."""
    date_left: int = 222
    """The date column `8月　日` and the blank day-numeral slot start here and run to 239."""
    rule_pairs: tuple[tuple[int, int], ...] = (
        (18, 19), (35, 36), (52, 53), (69, 70), (86, 87), (103, 104), (119, 120),
        (136, 137), (153, 154), (170, 171), (187, 188), (204, 205), (221, 222),
    )  # fmt: skip
    """The 13 vertical column rules separating 14 columns, nominally 2 px wide, one every
    17 px except for a single 16 px step at the fold ((103,104) to (119,120)). They are
    drawn artwork, not a generated grid: a rule is 1 or 2 px wide and sits up to two pixels
    either side of its nominal pair, page by page, so both the erase and the check work over
    `rule_window`."""
    day_slot: tuple[int, int, int, int] = (223, 138, 16, 13)
    """x, y, w, h of the gap between 月 and 日 that `nikki_date_upload` composites a
    14x10 numeral tile into (`research/text-outside-events.md` § The picture diary)."""

    def rule_window(self, pair: tuple[int, int]) -> range:
        """Every column a rule of this pair occupies on some page — six of them."""
        return range(pair[0] - 2, pair[1] + 3)

    def rule_steps(self) -> list[int]:
        """The gap between consecutive rules, derived rather than stated."""
        lefts = [pair[0] for pair in self.rule_pairs]
        return [b - a for a, b in pairwise(lefts)]

    @property
    def right(self) -> int:
        """Last column this script may repaint. The date column is left alone."""
        return self.date_left - 1

    @property
    def width(self) -> int:
        return self.right - self.left + 1


PANEL = Panel()

CRAYON_SPREAD = 48
"""How far apart a pixel's R, G and B have to be before it counts as crayon rather than as
paper, rule, fold or ink — every colour the panel itself uses is near-neutral. Measured: at
40 it also catches the pale blue rules two pages draw."""

CREASE = (118, 155)
"""The book's centre fold: a band of shadow and cream paper whose width wanders by a few
pixels from page to page. Used only by `measure_page`, to stop the fold being reported as an
undeclared rule. The *blanking* keeps the fold for an unrelated reason — `page_colours` takes
each column's own modal pale entry — and never consults this."""

INK_ROWS = 12
"""Both faces set into a 12-row band: the game's cell is 12 px, and Galmuri9 is 9 of cap
plus 3 of descender (`research/font-candidates.md`)."""
LINE_PITCH = 13
"""Rows per English line: the ink band plus the rule drawn under it. 13 is the minimum
`research/font-candidates.md` measured for Galmuri9 (12 for the game's own glyphs), and it
is what gets five lines into the panel."""
MAX_RULE_STEP = 17
"""The widest gap between two consecutive vertical rules. Derived from the constants it
checks would be circular, so it is the pitch the columns are actually drawn at."""

DATE_BANDS = 3
"""8, 月 and 日 — the whole of what the date column carries on every one of the 94 pages."""

PAPER_FRACTION = 0.40
"""How much of a row must already be its column's background for the row to be panel paper
rather than the page's drawn top edge. Measured over all 94 pages: rows 110-112 reach at most
0.39 and rows 113 and below never fall under 0.44."""

TEXT_MARGIN = 3
"""Paper left and right of the typeset block, so the text does not touch the page edge."""


def line_tops(panel: Panel = PANEL) -> list[int]:
    """The top row of each English line that fits between the panel's top and bottom."""
    out = []
    y = panel.repaint_top + 1
    while y + INK_ROWS <= panel.bottom:
        out.append(y)
        y += LINE_PITCH
    return out


# --- measurement ------------------------------------------------------------------------------


def luminance(colour: tuple[int, int, int, int]) -> int:
    return (colour[0] * 299 + colour[1] * 587 + colour[2] * 114) // 1000


@dataclass(frozen=True)
class PageColours:
    """The four palette entries a redraw of one page is allowed to use.

    All four are indices into the page's own CLUT, so `boku.tim` never has to approximate:
    the codec refuses an off-palette colour by design and this never offers it one.
    """

    paper: int
    rule: int
    ink: int
    background: tuple[int, ...]
    """One palette index per panel column x, the page's own background at that x with the
    vertical rules taken out — the book's centre fold survives a blanking this way."""


def page_colours(texture: Texture, panel: Panel = PANEL) -> PageColours:
    """Read the paper, rule and ink entries a page already uses out of its own panel."""
    tim = texture.tim
    idx = tim.indices()
    pal = tim.palette_rgba(0)

    def at(x: int, y: int) -> int:
        return idx[y * PAGE_W + x]

    rows = range(panel.top, panel.bottom + 1)
    rule_x = {x for pair in panel.rule_pairs for x in panel.rule_window(pair)}

    body = Counter(at(x, y) for y in rows for x in range(panel.left, panel.right + 1))
    paper = body.most_common(1)[0][0]

    # The background of a column, which is what a blanking has to restore: the page is
    # ruled vertically and creased vertically, so its background is a function of x alone.
    background = []
    for x in range(PAGE_W):
        common = Counter(at(x, y) for y in rows).most_common()
        chosen = next((i for i, _ in common if luminance(pal[i]) >= 180), paper)
        background.append(chosen)
    # A rule column's own background is its neighbour's: this is what erases the rules.
    for pair in panel.rule_pairs:
        window = panel.rule_window(pair)
        donor = window.start - 1
        while donor in rule_x and donor > 0:
            donor -= 1
        for x in window:
            background[x] = background[donor]

    # The rule's own colour, taken from the vertical rules this redraw is about to erase.
    # Only a *pale* non-paper entry qualifies: on the three pages whose rules sit outside
    # their nominal columns the window would otherwise answer with the fold's cream.
    paper_lum = luminance(pal[paper])
    rule_candidates: Counter[int] = Counter()
    for y in rows:
        for x in rule_x:
            if x > panel.right:
                continue
            entry = at(x, y)
            if paper_lum - 80 <= luminance(pal[entry]) <= paper_lum - 8:
                rule_candidates[entry] += 1
    rule = rule_candidates.most_common(1)[0][0] if rule_candidates else paper

    # The ink is the darkest entry the page's own text already uses. The date column is
    # included so that a page with empty columns (NIKKI_000) still finds its ink.
    ink = min(
        (at(x, y) for y in rows for x in range(panel.left, PAGE_W)),
        key=lambda i: (luminance(pal[i]), i),
    )
    return PageColours(paper, rule, ink, tuple(background))


@dataclass
class PageMeasure:
    """What one page's pixels say about the panel, for `measure` to compare with `PANEL`."""

    page: str
    top_edge_row: int
    """Where the drawn top edge of the ruled page begins on this page."""
    background_fraction: dict[int, float]
    """For the rows either side of the panel's top edge: how much of the row is already the
    background a blanking would restore. This is what makes `Panel.top` falsifiable."""
    crayon_rows: tuple[int, ...]
    """Rows of the repaintable rectangle that still hold a saturated (crayon) colour."""
    rule_pairs: tuple[tuple[int, int], ...]
    day_slot_clear: bool
    date_ink_rows: tuple[int, ...]
    colours: PageColours
    notes: list[str] = field(default_factory=list)


def measure_page(texture: Texture, panel: Panel = PANEL) -> PageMeasure:
    """Re-derive the panel geometry from one page, knowing only that it is a diary page."""
    tim = texture.tim
    idx = tim.indices()
    pal = tim.palette_rgba(0)

    def lum(x: int, y: int) -> int:
        return luminance(pal[idx[y * PAGE_W + x]])

    def median(values: list[int]) -> int:
        s = sorted(values)
        return s[len(s) // 2]

    def saturated(x: int, y: int) -> bool:
        """Crayon, as against paper: the panel's own colours are all near-neutral."""
        r, g, b, _ = pal[idx[y * PAGE_W + x]]
        return max(r, g, b) - min(r, g, b) > CRAYON_SPREAD

    # The top edge, found by following a rule column up: a rule is a pale non-paper tone all
    # the way to the drawn edge of the page, and the crayon above it is not. Scanning down
    # from the top of the image instead finds a pale patch of sky.
    def edge_above(x: int) -> int:
        y = panel.bottom
        while y > 0 and 150 <= lum(x, y) <= 244:
            y -= 1
        return y + 1

    edges = [
        edge_above(x)
        for pair in panel.rule_pairs[:3] + panel.rule_pairs[-3:]
        for x in panel.rule_window(pair)
    ]
    top_edge = median([e for e in edges if e <= panel.top] or edges)

    rows = list(range(panel.top, panel.bottom + 1))
    paper_lum = median([lum(x, y) for y in rows for x in range(20, 100)])

    # What a repaint would rub out: the drawing's V-notch at the book's fold dips a few
    # rows past the first paper row, which is why `repaint_top` sits below it.
    crayon = tuple(
        y
        for y in range(panel.top, panel.bottom + 1)
        if any(saturated(x, y) for x in range(panel.left, panel.right + 1))
    )

    # A rule column: one that is a *pale* non-paper tone for most of the panel's height.
    # Text ink is dark and covers only part of a column, so it never qualifies; the cream
    # of the book's centre fold is too pale to, which is also correct. A rule is drawn 1 or
    # 2 px wide depending on the page (it is artwork, not a generated grid), so a rule is
    # looked for at *either* column of its declared pair.
    def rule_like(x: int) -> bool:
        pale = sum(1 for y in rows if paper_lum - 80 <= lum(x, y) <= paper_lum - 3)
        return pale >= 0.7 * len(rows)

    declared = {x for pair in panel.rule_pairs for x in panel.rule_window(pair)}
    pairs = tuple(
        pair for pair in panel.rule_pairs if any(rule_like(x) for x in panel.rule_window(pair))
    )
    extras = tuple(
        x
        for x in range(1, PAGE_W - 1)
        if x not in declared and not CREASE[0] <= x <= CREASE[1] and rule_like(x)
    )
    # `extras` cannot see a rule declaration that has been *deleted* inside the fold, where
    # it does not look: `pairs` is derived from `panel.rule_pairs` and so can never name a
    # rule that is not declared. The columns are evenly spaced, so the step between
    # consecutive declarations is what catches that — a deleted rule leaves a double step.
    wide_steps = [step for step in panel.rule_steps() if step > MAX_RULE_STEP]

    # Where the paper starts and stops, tested directly rather than searched for. A panel row
    # is mostly *already* the background a blanking would restore — text ink covers only part
    # of it — and the drawn edge above it is none of it. Measured over all 94 pages: rows
    # 110-112 never reach 0.39 and rows 113+ never fall below 0.44, so `Panel.top` off by one
    # either way fails this. The bottom is sharper still in plain luminance: row 185 is paper
    # in the median on every page and row 187 is the desk under the book.
    colours = page_colours(texture, panel)

    def background_fraction(y: int) -> float:
        same = sum(
            1
            for x in range(panel.left, panel.right + 1)
            if idx[y * PAGE_W + x] == colours.background[x]
        )
        return same / panel.width

    fractions = {y: background_fraction(y) for y in range(panel.top - 3, panel.top + 2)}

    dx, dy, dw, dh = panel.day_slot
    slot_clear = all(lum(x, y) >= 160 for y in range(dy, dy + dh) for x in range(dx, dx + dw))
    # The date column holds exactly three things: 8, 月 and 日, in three bands with the
    # day-numeral slot between the last two. Counting the bands catches a `date_left` set
    # too LOW, where the last text column's Japanese joins in as extra bands. It does not
    # catch one set too high: the bands are rows, and shaving columns off the left of 月 and
    # 日 does not change how many rows of the column carry ink. Nothing here catches that;
    # looking at a rendered page does, which is what `compare` is for.
    date_ink = tuple(
        y
        for y in range(panel.top, panel.bottom + 1)
        if any(lum(x, y) < 160 for x in range(panel.date_left, PAGE_W - 1))
    )
    date_bands = sum(1 for a, b in zip((-9, *date_ink[:-1]), date_ink, strict=True) if b - a > 1)
    m = PageMeasure(
        page=texture.id,
        top_edge_row=top_edge,
        background_fraction=fractions,
        crayon_rows=crayon,
        rule_pairs=pairs,
        day_slot_clear=slot_clear,
        date_ink_rows=date_ink,
        colours=colours,
    )
    if fractions[panel.top] < PAPER_FRACTION:
        m.notes.append(
            f"row {panel.top} is only {fractions[panel.top]:.2f} background: the paper does "
            f"not start where Panel.top says it does"
        )
    if fractions[panel.top - 1] >= PAPER_FRACTION:
        m.notes.append(
            f"row {panel.top - 1} is already {fractions[panel.top - 1]:.2f} background: the "
            f"paper starts above Panel.top"
        )
    if not 1 <= panel.left < panel.right:
        m.notes.append(f"Panel.left {panel.left} is not a column inside the page")
    elif median([lum(panel.left - 1, y) for y in rows]) > 230:
        m.notes.append(
            f"column {panel.left - 1} is paper, not the page's darker left edge: the blank "
            f"starts further right than it could"
        )
    elif median([lum(panel.left, y) for y in rows]) < 240:
        m.notes.append(
            f"column {panel.left} is not paper: the blank would paint over the page's own "
            f"left edge"
        )
    if median([lum(x, panel.bottom) for x in range(PAGE_W)]) <= 240:
        m.notes.append(f"row {panel.bottom} is not paper: Panel.bottom is past the page")
    if median([lum(x, panel.bottom + 2) for x in range(PAGE_W)]) >= 200:
        m.notes.append(f"row {panel.bottom + 2} is not the desk: Panel.bottom is short")
    if top_edge >= panel.top:
        m.notes.append(f"the ruled page starts at row {top_edge}, at or below the paper row "
                       f"{panel.top} every other page has")
    late = [y for y in crayon if y >= panel.repaint_top]
    if late:
        m.notes.append(f"crayon inside the repainted rectangle, rows {late}")
    if pairs != panel.rule_pairs:
        m.notes.append(f"vertical rules missing: {sorted(set(panel.rule_pairs) - set(pairs))}")
    if extras:
        m.notes.append(f"rule-like columns outside the 13 and the fold: {extras}")
    if wide_steps:
        m.notes.append(
            f"the declared rules step by {wide_steps} px, more than the {MAX_RULE_STEP} a "
            f"column is wide: a rule declaration is missing"
        )
    if not slot_clear:
        m.notes.append("the day-numeral slot is not blank on this page")
    if date_bands != DATE_BANDS:
        m.notes.append(
            f"the date column holds {date_bands} bands of ink, not the {DATE_BANDS} that are "
            f"8, 月 and 日: rows {date_ink}"
        )
    return m


# --- the two 1-bit faces -----------------------------------------------------------------


@dataclass(frozen=True)
class Glyph:
    """A 1-bit glyph as rows of set-pixel x offsets, already left-aligned."""

    width: int
    """Ink width. The advance is this plus one column of air."""
    rows: tuple[tuple[int, ...], ...]
    """`INK_ROWS` rows, top of the ink band first; each a tuple of x offsets."""


class Face:
    """A 1-bit typeface this script can set into a 12-row line box."""

    name = "?"
    space = 4

    def glyph(self, ch: str) -> Glyph | None:
        raise NotImplementedError

    def advance(self, ch: str) -> int:
        if ch == " ":
            return self.space
        g = self.glyph(ch)
        return (g.width + 1) if g else 0

    def missing(self, text: str) -> list[str]:
        return sorted({c for c in text if not c.isspace() and self.glyph(c) is None})


FULLWIDTH_OFFSET = 0xFEE0
"""ASCII to its full-width twin, which is how Unicode lays the two ranges out and how the
game's glyph table is keyed (`research/font.md`): U+0021..U+007E -> U+FF01..U+FF5E. Derived
rather than typed out, so the table cannot drift from the range it claims to be."""

FULLWIDTH = {
    **{chr(c): chr(c + FULLWIDTH_OFFSET) for c in range(0x21, 0x7F)},
    # One the offset gets wrong, because the sheet draws the typographic character rather
    # than the full-width ASCII one: the apostrophe is U+2019.
    #
    # `-` is deliberately NOT mapped. The sheet's only dash is id 30, a full-width minus
    # (U+2212), and `research/font-candidates.md` § 1 lists the hyphen among the cells that
    # have to be drawn for English: "none of those can be reused". Leaving `-` unmapped makes
    # `Face.missing` report it instead of setting a wide, centred, raised minus in its place.
    # There is no straight or double quote on the sheet at all, and `(` `)` are its
    # vertical-writing forms, which `research/font.md` warns are wrong in a horizontal line.
    "'": "\u2019",
}


class GameFace(Face):
    """The game's own 12x12 dialogue glyphs, decoded from `ONMEM.BIN`'s sheet.

    The sheet is four interleaved 1bpp planes, not a 16-colour image: bit *k* of a 4-bit
    pixel is plane *k*, and `id -> (col, plane, row)` is `research/font.md`'s formula. The
    cells are proportional drawings with 1-5 px of left bearing, so a glyph is re-aligned to
    its own ink here and given `ink + 1` of advance — which is the "re-aligned" variant
    `research/font-candidates.md` measured, not the engine's fixed 14 px pitch.
    """

    name = "game"
    space = 4

    def __init__(self, sheet: Tim, table: dict[str, int]) -> None:
        self._idx = sheet.indices()
        self._w = sheet.width
        self._table = table
        self._cache: dict[str, Glyph | None] = {}

    @classmethod
    def load(cls, inv) -> GameFace:
        sheet = inv.get(FONT_SHEET_ID).tim
        table = {}
        for line in GLYPH_TSV.read_text(encoding="utf-8").splitlines()[1:]:
            cells = line.split("\t")
            if len(cells) >= 2 and cells[1]:
                table.setdefault(cells[1], int(cells[0]))
        return cls(sheet, table)

    def _cell(self, glyph_id: int) -> list[list[int]]:
        col, plane, row = glyph_id % 21, (glyph_id // 21) % 4, glyph_id // 84
        x0, y0 = col * 12, row * 12
        return [
            [(self._idx[(y0 + r) * self._w + x0 + c] >> plane) & 1 for c in range(12)]
            for r in range(12)
        ]

    def glyph(self, ch: str) -> Glyph | None:
        if ch in self._cache:
            return self._cache[ch]
        glyph_id = self._table.get(FULLWIDTH.get(ch, ch))
        found = None
        if glyph_id is not None:
            bits = self._cell(glyph_id)
            inked = [c for r in range(12) for c in range(12) if bits[r][c]]
            if inked:
                left, right = min(inked), max(inked)
                found = Glyph(
                    width=right - left + 1,
                    rows=tuple(
                        tuple(c - left for c in range(left, right + 1) if bits[r][c])
                        for r in range(12)
                    ),
                )
        self._cache[ch] = found
        return found


@dataclass(frozen=True)
class BdfChar:
    """One BDF character: its bounding box, its advance and its rows of hex."""

    width: int
    height: int
    off_x: int
    """Left bearing. It cancels here, because every glyph is re-aligned to its own ink."""
    off_y: int
    advance: int
    """The BDF's own `DWIDTH`. Only the space uses it; see `Face.advance`."""
    hex_rows: tuple[str, ...]


class BdfFace(Face):
    """A BDF bitmap font, read at its own pixels — no rasteriser, no hinting.

    Galmuri9 ships a BDF beside its TTFs, so the prototype compares the game's glyphs with
    the *designed* pixels of the candidate rather than with one rasteriser's opinion of them.
    """

    def __init__(self, path: Path, name: str) -> None:
        self.name = name
        self._chars, self._ascent = self._parse(path)
        self._cache: dict[str, Glyph | None] = {}
        space = self._chars.get(32)
        self.space = space.advance if space else 4

    @staticmethod
    def _parse(path: Path) -> tuple[dict[int, BdfChar], int]:
        """The characters, and the font's own `FONT_ASCENT`.

        The ascent is read out of the file rather than typed beside it. Taking the *cap*
        height for it instead silently deletes the top row of every accented capital, and
        `Face.missing` cannot see that, because the glyph is present — it is just short.
        """
        chars: dict[int, BdfChar] = {}
        ascent = None
        code = advance = None
        bbx: tuple[int, int, int, int] | None = None
        rows: list[str] | None = None
        for raw in path.read_text(encoding="latin-1").splitlines():
            line = raw.strip()
            if line.startswith("FONT_ASCENT"):
                ascent = int(line.split()[1])
            elif line.startswith("ENCODING"):
                code = int(line.split()[1])
            elif line.startswith("DWIDTH"):
                advance = int(line.split()[1])
            elif line.startswith("BBX"):
                w, h, ox, oy = (int(v) for v in line.split()[1:5])
                bbx = (w, h, ox, oy)
            elif line == "BITMAP":
                rows = []
            elif line == "ENDCHAR":
                if code is not None and bbx is not None and rows is not None:
                    chars[code] = BdfChar(*bbx, advance if advance is not None else bbx[0],
                                          tuple(rows))  # fmt: skip
                code = advance = None
                bbx = rows = None
            elif rows is not None:
                rows.append(line)
        if ascent is None:
            raise SystemExit(f"{path} declares no FONT_ASCENT, so a baseline cannot be placed")
        return chars, ascent

    def glyph(self, ch: str) -> Glyph | None:
        if ch in self._cache:
            return self._cache[ch]
        entry = self._chars.get(ord(ch))
        found = None
        if entry is not None and entry.width and entry.height:
            rows: list[tuple[int, ...]] = [() for _ in range(INK_ROWS)]
            for i, hex_row in enumerate(entry.hex_rows[: entry.height]):
                # BDF rows run top-down; the top one sits `off_y + height - 1` above the
                # baseline, and the baseline is `ascent` rows down the line's ink band.
                y = self._ascent - (entry.off_y + entry.height - 1 - i) - 1
                if not hex_row:
                    continue
                if not 0 <= y < INK_ROWS:
                    raise SystemExit(
                        f"{self.name}: U+{ord(ch):04X} has ink on row {y} of a {INK_ROWS}-row "
                        f"band. Dropping it would shorten the glyph silently."
                    )
                bits = int(hex_row, 16)
                span = len(hex_row) * 4
                rows[y] = tuple(
                    entry.off_x + c
                    for c in range(entry.width)
                    if (bits >> (span - 1 - c)) & 1
                )
            inked = [c for r in rows for c in r]
            if inked:
                left = min(inked)
                found = Glyph(
                    width=max(inked) - left + 1,
                    rows=tuple(tuple(c - left for c in r) for r in rows),
                )
        self._cache[ch] = found
        return found


def galmuri_face() -> BdfFace:
    """Galmuri9 at its native size: cap 9, x-height 6, 12 rows of ink
    (`research/font-candidates.md` § 4), which is `INK_ROWS` with nothing to spare. The
    ascent comes from the file's own `FONT_ASCENT`, 11, not from the cap height."""
    if not GALMURI_BDF.is_file():
        raise SystemExit(
            f"{GALMURI_BDF} is not there. `reference/fonts/` is gitignored; refetch it as "
            f"`reference/fonts/SOURCES.md` records."
        )
    return BdfFace(GALMURI_BDF, name="galmuri9")


# --- typesetting -------------------------------------------------------------------------


def wrap(text: str, face: Face, width: int) -> list[str]:
    """Greedy word wrap at `width` pixels, in `face`'s own advances."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            trial = f"{current} {word}" if current else word
            if current and measure_text(trial, face) > width:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return lines


def measure_text(text: str, face: Face) -> int:
    total = sum(face.advance(c) for c in text)
    return max(0, total - 1)


# --- the redraw --------------------------------------------------------------------------


@dataclass(frozen=True)
class Redraw:
    tim: Tim
    lines: list[str]
    overflow: list[str]
    """Lines that did not fit the panel — nothing is cut to fit silently (README)."""
    missing: list[str]
    face: str


def redraw_page(texture: Texture, text: str, face: Face, panel: Panel = PANEL) -> Redraw:
    """Blank the panel, rule it horizontally and typeset `text`, in palette indices only."""
    tim = texture.tim
    colours = page_colours(texture, panel)
    pal = tim.palette_rgba(0)
    pixels = bytearray(tim.indices())

    def put(x: int, y: int, index: int) -> None:
        if panel.left <= x <= panel.right and panel.repaint_top <= y <= panel.bottom:
            pixels[y * PAGE_W + x] = index

    # 1. Blank the panel back to the page's own background, rules and all — but never over
    # a crayon pixel. The Japanese columns start at row 114, four rows above where the
    # English may go, and the only thing that reaches down there from the drawing is the
    # V-notch of the book's fold, which is coloured where paper and ink are not.
    for y in range(panel.top, panel.bottom + 1):
        for x in range(panel.left, panel.right + 1):
            r, g, b, _ = pal[pixels[y * PAGE_W + x]]
            if max(r, g, b) - min(r, g, b) > CRAYON_SPREAD:
                continue
            pixels[y * PAGE_W + x] = colours.background[x]

    # 2. horizontal rules, one under each line.
    tops = line_tops(panel)
    for top in tops:
        rule_y = top + INK_ROWS
        for x in range(panel.left, panel.right + 1):
            put(x, rule_y, colours.rule)

    # 3. the English.
    usable = panel.width - 2 * TEXT_MARGIN
    lines = wrap(text, face, usable)
    drawn, overflow = lines[: len(tops)], lines[len(tops) :]
    for top, line in zip(tops, drawn, strict=False):
        x = panel.left + TEXT_MARGIN
        for ch in line:
            glyph = face.glyph(ch)
            if glyph is not None:
                for row, bits in enumerate(glyph.rows):
                    for dx in bits:
                        put(x + dx, top + row, colours.ink)
            x += face.advance(ch)
    return Redraw(
        tim=tim.with_indices(bytes(pixels)),
        lines=drawn,
        overflow=[line for line in overflow if line],
        missing=face.missing(text),
        face=face.name,
    )


# --- entry text ----------------------------------------------------------------------------

PLACEHOLDER = (
    "Mom is having a baby soon, so things at home are hectic! "
    "I am going to stay at my uncle's house out in the country. "
    "I wonder if there will be lots of fun things to do?"
)
"""PLACEHOLDER, not a translation. It paraphrases `NIKKI_001`'s own columns so that the
prototype sets a real sentence's worth of English, and it is the default because **the
diary's prose has no home in `translation/` yet**: `translation/days/dayNN.txt` is the day's
*event* script, a different surface, and reading it here would typeset the wrong text.
Giving the entries a keyed home is `GFX-03`'s, not this prototype's."""


def entry_text(page: str, given: Path | None) -> tuple[str, bool]:
    """The English to set, and whether it is the placeholder."""
    if given is not None:
        return given.read_text(encoding="utf-8").strip(), False
    return PLACEHOLDER, True


# --- verbs ------------------------------------------------------------------------------------


def diary_pages(inv) -> dict[str, Texture]:
    out = {}
    for texture in inv.textures:
        if "NIKKI.BIN_NIKKI_" in texture.id:
            out[texture.id.split("NIKKI_")[-1][:3]] = texture
    return out


def load(disc: Path):
    return inventory(Archive(disc))


def verb_measure(args) -> int:
    inv = load(args.disc)
    pages = diary_pages(inv)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    report = []
    disagree = []
    for key in sorted(pages):
        m = measure_page(pages[key])
        report.append(
            {
                "page": key,
                "top_edge_row": m.top_edge_row,
                "crayon_rows": list(m.crayon_rows),
                "background_fraction": {
                    str(k): round(v, 3) for k, v in m.background_fraction.items()
                },
                "rule_pairs": [list(p) for p in m.rule_pairs],
                "day_slot_clear": m.day_slot_clear,
                "date_ink_rows": list(m.date_ink_rows),
                "paper_rgb": pages[key].tim.palette_rgba(0)[m.colours.paper][:3],
                "rule_rgb": pages[key].tim.palette_rgba(0)[m.colours.rule][:3],
                "ink_rgb": pages[key].tim.palette_rgba(0)[m.colours.ink][:3],
                "notes": m.notes,
            }
        )
        if m.notes:
            disagree.append((key, m.notes))
    (WORK_DIR / "geometry.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"{len(pages)} diary pages measured -> {WORK_DIR / 'geometry.json'}")
    print(
        f"panel: x {PANEL.left}..{PANEL.right} (date column {PANEL.date_left}..239), paper "
        f"y {PANEL.top}..{PANEL.bottom}, repainted from y {PANEL.repaint_top}; "
        f"{len(PANEL.rule_pairs)} vertical rules, steps {sorted(set(PANEL.rule_steps()))}"
    )
    print(f"English lines that fit: {len(line_tops())} at pitch {LINE_PITCH}, tops {line_tops()}")
    edges = Counter(r["top_edge_row"] for r in report)
    print(f"drawn top edge of the ruled page, per page: {sorted(edges.items())}")
    same = len(pages) - len(disagree)
    print(f"pages whose panel matches the measured geometry exactly: {same}/{len(pages)}")
    for key, notes in disagree:
        print(f"  {key}: {'; '.join(notes)}")
    papers = Counter(tuple(r["paper_rgb"]) for r in report)
    inks = Counter(tuple(r["ink_rgb"]) for r in report)
    rules = Counter(tuple(r["rule_rgb"]) for r in report)
    print(f"paper colours: {papers.most_common(4)}")
    print(f"rule colours:  {rules.most_common(4)}")
    print(f"ink colours:   {inks.most_common(4)}")
    print(f"day-numeral slot blank on all pages: {all(r['day_slot_clear'] for r in report)}")
    return 0


def faces(inv) -> dict[str, Face]:
    return {"game": GameFace.load(inv), "galmuri": galmuri_face()}


def render_one(texture: Texture, text: str, face: Face) -> Redraw:
    result = redraw_page(texture, text, face)
    if result.missing:
        print(f"  {face.name}: no glyph for {result.missing} — those characters are dropped")
    if result.overflow:
        print(
            f"  {face.name}: {len(result.overflow)} line(s) did not fit, first "
            f"{result.overflow[:2]} — nothing is cut to fit (README); give the entry less text"
        )
    return result


def verb_render(args) -> int:
    inv = load(args.disc)
    pages = diary_pages(inv)
    texture = pages[args.page]
    text, placeholder = entry_text(args.page, args.text)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    print(f"page {args.page} ({texture.id}), {texture.copies} occurrence(s)")
    if placeholder:
        print("  entry text: PLACEHOLDER — the diary's prose has no home in translation/ yet")
    (WORK_DIR / f"original-{args.page}.png").write_bytes(to_png(texture.tim))
    for name, face in faces(inv).items():
        result = render_one(texture, text, face)
        out = WORK_DIR / f"redraw-{args.page}-{name}.png"
        out.write_bytes(to_png(result.tim))
        print(f"  {name}: {len(result.lines)} lines -> {out}")
    return 0


def _scaled(png_bytes: bytes, scale: int):
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def verb_compare(args) -> int:
    from PIL import Image, ImageDraw

    inv = load(args.disc)
    texture = diary_pages(inv)[args.page]
    text, placeholder = entry_text(args.page, args.text)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    panels = [("original", to_png(texture.tim))]
    for name, face in faces(inv).items():
        panels.append((name, to_png(render_one(texture, text, face).tim)))

    pad, label = 8, 16
    ones = [_scaled(b, 1) for _, b in panels]
    threes = [_scaled(b, 3) for _, b in panels]
    w1, h1 = ones[0].size
    w3, h3 = threes[0].size
    width = pad + max(len(ones) * (w1 + pad), len(threes) * (w3 + pad))
    height = pad + label + h1 + pad + label + h3 + pad
    sheet = Image.new("RGB", (width, height), (32, 32, 36))
    draw = ImageDraw.Draw(sheet)
    y = pad
    for scale, images, cell_w, cell_h in ((1, ones, w1, h1), (3, threes, w3, h3)):
        x = pad
        for (name, _), img in zip(panels, images, strict=True):
            draw.text((x, y), f"{name} {scale}x", fill=(230, 230, 230))
            sheet.paste(img, (x, y + label))
            x += cell_w + pad
        y += label + cell_h + pad
    out = WORK_DIR / "COMPARE.png"
    sheet.save(out)
    print(f"{out}  ({'placeholder entry' if placeholder else 'entry from translation/'})")

    # The same three panels again, cropped to the ruled page and magnified. COMPARE.png at 3x
    # shows whether a redraw reads; only this shows whether a vertical rule survived the blank
    # or a glyph landed a row off, which is the pair of mistakes `measure` cannot see.
    zoom, top = 6, PANEL.top - 5
    crops = [
        _scaled(b, 1).crop((0, top, PAGE_W, PAGE_H)).resize(
            (PAGE_W * zoom, (PAGE_H - top) * zoom), Image.NEAREST
        )
        for _, b in panels
    ]
    cw, ch = crops[0].size
    strip = Image.new("RGB", (cw, len(crops) * (ch + label) + pad), (32, 32, 36))
    draw = ImageDraw.Draw(strip)
    for i, ((name, _), img) in enumerate(zip(panels, crops, strict=True)):
        y = i * (ch + label) + pad
        draw.text((pad, y - label // 2), f"{name} {zoom}x", fill=(230, 230, 230))
        strip.paste(img, (0, y + label // 2))
    zoom_out = WORK_DIR / "panel-zoom.png"
    strip.save(zoom_out)
    print(f"{zoom_out}  (the ruled page alone, rows {top}..{PAGE_H - 1} at {zoom}x)")
    return 0


def verb_build(args) -> int:
    from boku.build import build, verify_written_sectors

    inv = load(args.disc)
    texture = diary_pages(inv)[args.page]
    text, placeholder = entry_text(args.page, args.text)
    face = faces(inv)[args.face]
    result = render_one(texture, text, face)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    (WORK_DIR / f"redraw-{args.page}-{args.face}.png").write_bytes(to_png(result.tim))
    edits = patches_for(texture, result.tim)
    print(
        f"{len(edits)} byte edit(s), {sum(len(e.new) for e in edits)} bytes, "
        f"over {texture.copies} occurrence(s)"
        + ("  [placeholder entry]" if placeholder else "")
    )
    out = build(
        source=args.image,
        out_dir=BUILD_DIR,
        disc_dir=args.disc,
        translation=None,
        binary_patches=edits,
        name="diary",
    )
    if not out.written:
        print("no image was written")
        return 1
    print(f"image -> {out.written.image} ({len(out.written.sectors)} sectors rewritten)")
    # `build()` verifies every `old` before the first write; only `boku build`'s CLI re-reads
    # the *written* sectors afterwards. This is the prototype's own copy of that check, so a
    # sector written with a stale EDC/ECC cannot be reported as a clean build.
    bad = verify_written_sectors(out.written.image, out.written.sectors)
    if bad:
        print(f"{len(bad)} written sector(s) fail their own EDC/ECC: {bad[:8]}")
        return 1
    print(f"all {len(out.written.sectors)} written sectors pass their own EDC/ECC")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--disc", type=Path, default=DISC_DIR)
    sub = parser.add_subparsers(dest="verb", required=True)

    m = sub.add_parser("measure", help="re-derive the panel geometry from all 94 pages")
    m.set_defaults(run=verb_measure)

    for name, run, extra in (
        ("render", verb_render, False),
        ("compare", verb_compare, False),
        ("build", verb_build, True),
    ):
        p = sub.add_parser(name)
        p.add_argument("--page", default="001", help="diary page, e.g. 001")
        p.add_argument("--text", type=Path, default=None, help="file holding the English entry")
        if extra:
            p.add_argument("--face", choices=("game", "galmuri"), default="game")
            p.add_argument("--image", type=Path, default=REPO_ROOT / "disc/image.img")
        p.set_defaults(run=run)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
