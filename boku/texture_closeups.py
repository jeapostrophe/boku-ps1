"""The close-up screens with writing drawn into their art (PLAN `GFX-08`;
`research/texture-recipes.md` § "Close-ups", which has the method and the measurements).

A close-up is a whole 320x240 screen the player opens by examining something. Its writing is
part of a painting -- a note lying at an angle on a log -- so the recipe works in the plane of
the thing written on: `Plane` maps an upright rectangle onto the four corners the object
has in the picture, the Japanese is refilled along the object's own rules, and the English is
set upright in the game's glyphs and carried into the picture through the same map, each
covered pixel mixed from the ink and the paper under it and matched back to an entry the
object already uses. Only the Japanese, the pixel round it, and the English change.

The English is `tex@<member>.<key>` in `translation/textures/signs.txt`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from boku import texture_paint as paint
from boku.archive import Archive
from boku.reinsert import ByteEdit
from boku.textures import Inventory
from boku.tim import luminance
from boku.typeset import Face

from boku.texture_text import (  # isort: skip
    Entry, TextureTextError, found, ink_of, keyed, lines_of,
)  # fmt: skip

Point = tuple[float, float]


def _solve(rows: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting: `rows` x = `rhs`."""
    n = len(rhs)
    m = [[*row, rhs[i]] for i, row in enumerate(rows)]
    for c in range(n):
        pivot = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[pivot][c]) < 1e-12:
            raise ValueError("the four corners are degenerate: three of them are in a line")
        m[c], m[pivot] = m[pivot], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def _homography(src: Sequence[Point], dst: Sequence[Point]) -> tuple[float, ...]:
    """The projective map taking each of four `src` points to its `dst` point."""
    rows, rhs = [], []
    for (u, v), (x, y) in zip(src, dst, strict=True):
        rows += [[u, v, 1, 0, 0, 0, -u * x, -v * x], [0, 0, 0, u, v, 1, -u * y, -v * y]]
        rhs += [x, y]
    return (*_solve(rows, rhs), 1.0)


def _apply(h: tuple[float, ...], p: Point) -> Point:
    x, y = p
    w = h[6] * x + h[7] * y + h[8]
    return (h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w


@dataclass(frozen=True)
class Plane:
    """A flat object in a picture: the upright `size` (w, h) rectangle it is, and the four
    picture points its corners land on (top-left, top-right, bottom-right, bottom-left of the
    upright object). `picture` and `upright` map a point between the two; a pixel's point is
    its centre."""

    size: tuple[int, int]
    corners: tuple[Point, Point, Point, Point]
    _forward: tuple[float, ...] = field(init=False, repr=False, compare=False)
    _backward: tuple[float, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        w, h = self.size
        rectangle = ((0, 0), (w, 0), (w, h), (0, h))
        object.__setattr__(self, "_forward", _homography(rectangle, self.corners))
        object.__setattr__(self, "_backward", _homography(self.corners, rectangle))

    def picture(self, p: Point) -> Point:
        return _apply(self._forward, p)

    def upright(self, p: Point) -> Point:
        return _apply(self._backward, p)

    def pixels(self, box: paint.Box) -> dict[tuple[int, int], Point]:
        """Every picture pixel whose centre lies in upright `box`, with its upright point."""
        x0, y0, w, h = box
        ends = [self.picture(p) for p in ((x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h))]
        xs, ys = [c[0] for c in ends], [c[1] for c in ends]
        out = {}
        for y in range(int(min(ys)), int(max(ys)) + 2):
            for x in range(int(min(xs)), int(max(xs)) + 2):
                u, v = self.upright((x + 0.5, y + 0.5))
                if x0 <= u < x0 + w and y0 <= v < y0 + h:
                    out[x, y] = (u, v)
        return out


def refill_along_rules(
    canvas: paint.Canvas, plane: Plane, mask: paint.Ink, donors: dict[tuple[int, int], Point],
    *, what: str,
) -> None:  # fmt: skip
    """Refill each `mask` pixel from the nearest `donors` pixel on its own rule: along the
    object's horizontal, the nearest whose upright height is within half a pixel of its own,
    so a ruled line stays a line and the shading across the rules keeps its bands. Refuses,
    naming `what`, a pixel with no such donor."""
    pixels, width, source = canvas.pixels, canvas.width, bytes(canvas.pixels)
    left = []
    for p in sorted(mask):
        u, v = plane.upright((p[0] + 0.5, p[1] + 0.5))
        for step in range(1, 2 * plane.size[0]):
            hit = next(
                (q for q in (_pixel(plane.picture((u + du, v))) for du in (-step / 2, step / 2))
                 if q in donors and q not in mask and abs(donors[q][1] - v) <= 0.5),
                None,
            )  # fmt: skip
            if hit is not None:
                pixels[p[1] * width + p[0]] = source[hit[1] * width + hit[0]]
                break
        else:
            left.append(p)
    if left:
        raise TextureTextError(
            f"{what}: {len(left)} pixel(s) of Japanese had no clean pixel on their rule, "
            f"first {left[:3]}"
        )


def _pixel(p: Point) -> tuple[int, int]:
    return math.floor(p[0]), math.floor(p[1])


SUBSAMPLES = 4
"""Per side of the grid each picture pixel is sampled on for `coverage`."""


def coverage(plane: Plane, ink: paint.Ink, at: Point) -> dict[tuple[int, int], float]:
    """The fraction of each picture pixel that upright `ink`, stamped at upright `at`, covers."""
    ax, ay = at
    x0, y0, w, h = paint.extent(ink)
    n = SUBSAMPLES
    out = {}
    for x, y in plane.pixels((ax + x0 - 1, ay + y0 - 1, w + 2, h + 2)):
        hits = 0
        for j in range(n):
            for i in range(n):
                u, v = plane.upright((x + (i + 0.5) / n, y + (j + 0.5) / n))
                hits += (math.floor(u - ax), math.floor(v - ay)) in ink
        if hits:
            out[x, y] = hits / (n * n)
    return out


def _nearest(palette, entries: Sequence[int], colour: tuple[float, float, float]) -> int:
    return min(entries, key=lambda e: sum((palette[e][k] - colour[k]) ** 2 for k in range(3)))


def write_in(
    canvas: paint.Canvas, clut: int, cover: dict[tuple[int, int], float], ink_entry: int,
    entries: Sequence[int], *, weight: float = 1.0,
) -> None:  # fmt: skip
    """Mix the ink over the paper by `cover` (times `weight`, at most all ink) and match each
    mix to the nearest of `entries`."""
    palette = canvas.palette(clut)
    ink = palette[ink_entry]
    for (x, y), c in cover.items():
        c = min(1.0, c * weight)
        paper = canvas.colour(clut, (x, y))
        mix = tuple(c * ink[k] + (1 - c) * paper[k] for k in range(3))
        canvas.pixels[y * canvas.width + x] = _nearest(palette, entries, mix)


# --- M_I14000: Saori's farewell note ------------------------------------------------------------


NOTE_TEXTURE = "_DATA_M_FILES.BIN_M_I14000.BIN__000214"
"""320x240 8bpp, one CLUT: the close-up of the spiral notepad left on the log at Saori's camp
(scene `E2860`, from day 28)."""
NOTE = Plane(size=(100, 123), corners=((84.2, 73.7), (179.7, 35.9), (239.3, 140.3), (149.0, 181.7)))
"""The page, upright with its spiral on the left, and where its corners are: the meeting
points of its four edges, each fitted to the page's outline. The top-right corner is curled
over, so its fitted corner lies off the paper."""
NOTE_TEXT = (11, 3, 86, 119)
"""The upright area the Japanese is in and the English may use: right of the spiral's holes.
The curled corner and the log beyond it reach into its top right (`note_japanese` leaves
them; the English may not touch them)."""
NOTE_DARK = 150
"""The Japanese's strokes: darker than this. The ruled lines and the page's shading are paler."""
NOTE_GREY = 215
"""The strokes' antialiasing: a pixel within two of a stroke that is darker than this and no
bluer than grey (`NOTE_BLUE`); the paper round the strokes is paler or bluer."""
NOTE_BLUE = 10
NOTE_RULES = (11.0, 16.0, 20.5, 25.0, 29.5, 34.5, 39.0, 44.5, 49.5, 55.0, 60.5, 65.0, 70.5,
              76.0, 81.5, 87.0, 92.5, 97.5, 103.0, 107.5, 112.5, 117.0)  # fmt: skip
"""The ruled lines' upright heights, as painted (4.5 to 5.5 apart), top first."""
NOTE_LINE_RULES = (4, 7, 10, 13, 16)
"""The rule each line of the note sits on: every third, as the Japanese characters are about
three rules tall."""
NOTE_SIGNATURE_RULE = 20
"""The signature's rule, near the foot of the page as the Japanese's is; it ends at the text
area's right edge."""
NOTE_LEFT = 14.0
"""Where each line of the note starts."""
BASELINE = 10.5
"""From a glyph cell's top to half a pixel under its capitals (rows 1-9): where the rule runs."""
NOTE_WEIGHT = 1.5
"""A one-pixel stroke off the pixel grid covers two pixels by about half each, which reads
grey beside the Japanese's dark strokes; coverage is scaled by this. (The game's glyphs
emboldened, `paint.bold`, clog at this size.)"""


def note_japanese(canvas: paint.Canvas, area) -> tuple[paint.Ink, paint.Ink]:
    """The Japanese's strokes in `area`, and those with their grey antialiasing. A stroke is
    a group of dark pixels the area surrounds: the curled corner and the log beyond it, which
    reach into the area's top right, run out of it."""
    colours = {p: canvas.colour(0, p, stock=True) for p in area}
    dark = {p for p, c in colours.items() if luminance(c) < NOTE_DARK}
    strokes = set().union(
        *(g for g in paint.groups(dark) if paint.grown(g, 1, 1, 1, 1) <= area.keys())
    )
    near = paint.grown(strokes, 2, 2, 2, 2)
    return strokes, strokes | {
        p for p, c in colours.items()
        if p in near and luminance(c) < NOTE_GREY and c[2] - c[0] <= NOTE_BLUE
    }  # fmt: skip


def pen(canvas: paint.Canvas, strokes: paint.Ink) -> int:
    """The pen's entry, not its antialiasing's: what the darkest tenth of `strokes` (at
    least one pixel) uses most."""
    by_darkness = sorted(strokes, key=lambda p: luminance(canvas.colour(0, p, stock=True)))
    return canvas.most_used(by_darkness[: max(1, len(by_darkness) // 10)], stock=True)


def note(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]) -> list[ByteEdit]:
    """Refill the note's Japanese along its rules and write the English on the rules."""
    text = keyed("tex@M_I14000", entries, ["note", "signature"])
    lines = lines_of(text["note"])
    if len(lines) > len(NOTE_LINE_RULES):
        raise TextureTextError(
            f"{text['note'].where}: the note is {len(lines)} lines and the page holds "
            f"{len(NOTE_LINE_RULES)}; nothing is cut to fit (README)"
        )
    if not all(line.strip() for line in lines):
        raise TextureTextError(f"{text['note'].where}: the note has an empty line")
    left_edge, right_edge = NOTE_TEXT[0], NOTE_TEXT[0] + NOTE_TEXT[2]
    rows = [(text["note"], line, rule) for line, rule in zip(lines, NOTE_LINE_RULES, strict=False)]
    rows.append((text["signature"], text["signature"].text, NOTE_SIGNATURE_RULE))
    placed = []
    for entry, line, rule in rows:
        ink = ink_of(face, entry, line)  # x from the first ink, y the glyph cell's rows
        width = paint.extent(ink)[2]
        start = NOTE_LEFT if entry is text["note"] else left_edge
        if width > right_edge - start:
            raise TextureTextError(
                f"{entry.where}: {line!r} is {width} px and a line of the note holds "
                f"{right_edge - start:.0f}; nothing is cut to fit (README)"
            )
        left = start if entry is text["note"] else right_edge - width
        placed.append((entry, line, ink, (left, NOTE_RULES[rule] - BASELINE)))

    canvas = paint.Canvas(inv.get(NOTE_TEXTURE))
    area, page = NOTE.pixels(NOTE_TEXT), NOTE.pixels((0, 0, *NOTE.size))
    strokes, japanese = note_japanese(canvas, area)
    found(strokes, "Saori's note")
    # Not paper: the curl, the log and the spiral's holes. The refill never copies them, the
    # English never touches them, and its mixes are never matched to their colours.
    marks = {p for p in page if luminance(canvas.colour(0, p)) < NOTE_DARK} - japanese
    ink_entry = pen(canvas, strokes)
    shades = sorted({canvas.at(p) for p in page if p not in marks})
    erase = {q for q in paint.grown(japanese, 1, 1, 1, 1) if q in area}
    donors = {p: uv for p, uv in area.items() if p not in marks}
    refill_along_rules(canvas, NOTE, erase, donors, what="Saori's note")
    near_marks = paint.grown(marks, 1, 1, 1, 1)
    for entry, line, ink, at in placed:
        cover = coverage(NOTE, ink, at)
        off_paper = sorted(p for p in cover if p not in page or p in near_marks)
        if off_paper:
            raise TextureTextError(
                f"{entry.where}: {line!r} would be written off the paper (onto the curled "
                f"corner or the log) at {off_paper[:3]}; nothing is cut to fit (README)"
            )
        write_in(canvas, 0, cover, ink_entry, shades, weight=NOTE_WEIGHT)
    return canvas.patches()


__all__ = [
    "NOTE",
    "NOTE_TEXTURE",
    "Plane",
    "coverage",
    "note",
    "note_japanese",
    "pen",
    "refill_along_rules",
    "write_in",
]
