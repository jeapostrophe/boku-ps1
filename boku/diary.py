"""The picture diary's pages, rebuilt with English entries (PLAN `GFX-04`).

Each of the 94 `NIKKI.BIN` pages is a 240x192 8bpp TIM whose lower part is a ruled panel of
vertical Japanese columns under a crayon drawing. `redraw_page` blanks that panel back to the
page's own background, rules it horizontally and sets the English entry in the game's own
glyphs, all in the page's own palette indices; `measure_page` re-derives the panel's
geometry from a page's pixels so a page that differs from the measured one is caught before
it is drawn over. Every number here is `research/diary-redraw.md`'s, measured over all 94
pages; the English itself is `translation/textures/diary.txt`, keyed by page id.

The prototype that found all this, and still draws comparison sheets, is
`tools/diary/redraw.py`; it imports from here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise

from boku.textures import Inventory, Texture
from boku.tim import Tim, luminance
from boku.typeset import Face, wrap

DIARY_PREFIX = "_DATA_NIKKI.BIN_NIKKI_"
DUMMY_PAGE = "000"
"""The unused page: `g_diary_pages` never names it (`research/diary-redraw.md`)."""
SHADED_PAGES = {"047": (2, 15, 157, 158, 159, 160, 161, 162, 163)}
"""The one page with pale shading columns that `measure_page` reads as extra rules, and
exactly which: the redraw keeps each column's own background, so they survive. Any other
extra column, on this page or another, is a panel the recipe was not measured on."""


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

    @property
    def text_width(self) -> int:
        """What one line of English may be: the panel less `TEXT_MARGIN` either side."""
        return self.width - 2 * TEXT_MARGIN


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
    shade = [luminance(c) for c in tim.palette_rgba(0)]

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
        chosen = next((i for i, _ in common if shade[i] >= 180), paper)
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
    paper_lum = shade[paper]
    rule_candidates: Counter[int] = Counter()
    for y in rows:
        for x in rule_x:
            if x > panel.right:
                continue
            entry = at(x, y)
            if paper_lum - 80 <= shade[entry] <= paper_lum - 8:
                rule_candidates[entry] += 1
    rule = rule_candidates.most_common(1)[0][0] if rule_candidates else paper

    # The ink is the darkest entry the page's own text already uses. The date column is
    # included so that a page with empty columns (NIKKI_000) still finds its ink.
    ink = min(
        (at(x, y) for y in rows for x in range(panel.left, PAGE_W)),
        key=lambda i: (shade[i], i),
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
    shade = [luminance(c) for c in pal]

    def lum(x: int, y: int) -> int:
        return shade[idx[y * PAGE_W + x]]

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
            f"column {panel.left} is not paper: the blank would paint over the page's own left edge"
        )
    if median([lum(x, panel.bottom) for x in range(PAGE_W)]) <= 240:
        m.notes.append(f"row {panel.bottom} is not paper: Panel.bottom is past the page")
    if median([lum(x, panel.bottom + 2) for x in range(PAGE_W)]) >= 200:
        m.notes.append(f"row {panel.bottom + 2} is not the desk: Panel.bottom is short")
    if top_edge >= panel.top:
        m.notes.append(
            f"the ruled page starts at row {top_edge}, at or below the paper row "
            f"{panel.top} every other page has"
        )
    late = [y for y in crayon if y >= panel.repaint_top]
    if late:
        m.notes.append(f"crayon inside the repainted rectangle, rows {late}")
    if pairs != panel.rule_pairs:
        m.notes.append(f"vertical rules missing: {sorted(set(panel.rule_pairs) - set(pairs))}")
    if extras and extras != SHADED_PAGES.get(page_number(texture.id)):
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


@dataclass(frozen=True)
class Redraw:
    tim: Tim
    lines: list[str]
    overflow: list[str]
    """Lines that did not fit the panel — nothing is cut to fit silently (README)."""
    missing: list[str]
    face: str


def redraw_page(
    texture: Texture,
    text: str,
    face: Face,
    panel: Panel = PANEL,
    colours: PageColours | None = None,
) -> Redraw:
    """Blank the panel, rule it horizontally and typeset `text`, in palette indices only.
    `colours` is the page's `page_colours`, when the caller has already read them."""
    tim = texture.tim
    colours = colours or page_colours(texture, panel)
    crayon = [max(c[:3]) - min(c[:3]) > CRAYON_SPREAD for c in tim.palette_rgba(0)]
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
            if crayon[pixels[y * PAGE_W + x]]:
                continue
            pixels[y * PAGE_W + x] = colours.background[x]

    # 2. horizontal rules, one under each line.
    tops = line_tops(panel)
    for top in tops:
        rule_y = top + INK_ROWS
        for x in range(panel.left, panel.right + 1):
            put(x, rule_y, colours.rule)

    # 3. the English.
    lines = wrap(text, face, panel.text_width)
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


def page_number(texture_id: str) -> str:
    """`"072"` for `_DATA_NIKKI.BIN_NIKKI_072__000000`."""
    return texture_id.removeprefix(DIARY_PREFIX)[:3]


def diary_pages(inv: Inventory) -> dict[str, Texture]:
    """Every diary page by its three-digit number (`"001"`)."""
    return {page_number(t.id): t for t in inv.textures if t.id.startswith(DIARY_PREFIX)}
