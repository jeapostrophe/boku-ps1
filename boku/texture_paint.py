"""Pixel operations for the programmatic texture path, all in palette indices.

`boku.texture_text`'s recipes are built from these: find the Japanese in a region by the
colour of its pixels, paint it out from the region's own background, and set English ink
(scaled, emboldened, rotated) in entries the texture already uses. No colour is ever chosen
here and nothing is quantised: every index written is one the caller read out of the image.

Coordinates are texture pixels; a *box* is `(x, y, w, h)`; *ink* is a set of `(x, y)`
relative to wherever the caller stamps it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from boku.reinsert import ByteEdit
from boku.textures import Texture, patches_for
from boku.tim import Tim, luminance

Box = tuple[int, int, int, int]
Ink = set[tuple[int, int]]


def points(box: Box) -> list[tuple[int, int]]:
    x0, y0, w, h = box
    return [(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w)]


def where(indices, width: int, palette, box: Box, keep) -> Ink:
    """The pixels of `box` whose colour (through `palette`) `keep` accepts."""
    return {(x, y) for x, y in points(box) if keep(palette[indices[y * width + x]])}


def pale(c, *, spread: int = 60, lightest: int = 110) -> bool:
    """A pale, near-neutral colour: white type and its grey antialiasing."""
    return bool(c[3]) and max(c[:3]) - min(c[:3]) < spread and luminance(c) > lightest


def dark(c, *, darkest: int = 100, spread: int = 256) -> bool:
    """A colour darker than `darkest`; a `spread` keeps only near-grey ones, leaving a dark
    crayon or photo out."""
    return bool(c[3]) and luminance(c) < darkest and max(c[:3]) - min(c[:3]) < spread


def pale_type(tim: Tim, clut: int, box: Box, *, spread: int = 60, lightest: int = 110) -> Ink:
    """The pixels of `box` drawn `pale` through CLUT `clut`: white type against a saturated
    or dark ground."""
    keep = lambda c: pale(c, spread=spread, lightest=lightest)  # noqa: E731
    return where(tim.indices(), tim.width, tim.palette_rgba(clut), box, keep)


def dark_type(tim: Tim, clut: int, box: Box, *, darkest: int = 100, spread: int = 256) -> Ink:
    """The pixels of `box` drawn `dark` through CLUT `clut`: dark type on a pale plate."""
    keep = lambda c: dark(c, darkest=darkest, spread=spread)  # noqa: E731
    return where(tim.indices(), tim.width, tim.palette_rgba(clut), box, keep)


def grown(ink: Iterable[tuple[int, int]], left: int, up: int, right: int, down: int) -> Ink:
    """`ink` dilated by a rectangle: every pixel within `left`..`right`, `up`..`down`."""
    return {
        (x + dx, y + dy)
        for x, y in ink
        for dx in range(-left, right + 1)
        for dy in range(-up, down + 1)
    }


def paint_out(
    pixels: bytearray, width: int, box: Box, mask: Ink, *, avoid: Ink = frozenset()
) -> list[tuple[int, int]]:
    """Replace every masked pixel of `box` with the nearest unmasked pixel of its own row, and
    return the masked pixels that had no donor at all (left as they were).

    The donor is taken an even distance away, so an ordered dither keeps its phase and a
    gradient keeps its slope; `avoid` pixels (a rule, a frame line) are never donors. A
    pixel whose row has no donor takes one from its column, an even distance away if one
    exists, else the nearest.
    """
    x0, y0, w, h = box
    bad = mask | avoid

    def donor(x: int, y: int) -> int | None:
        for d in range(2, w + 1, 2):
            for sx in (x - d, x + d):
                if x0 <= sx < x0 + w and (sx, y) not in bad:
                    return pixels[y * width + sx]
        return None

    todo = sorted(p for p in mask if x0 <= p[0] < x0 + w and y0 <= p[1] < y0 + h)
    left = []
    for x, y in todo:
        found = donor(x, y)
        if found is None:
            left.append((x, y))
        else:
            pixels[y * width + x] = found
    unfilled = []
    for x, y in left:
        for d in [*range(2, h + 1, 2), *range(1, h + 1, 2)]:
            rows = [sy for sy in (y - d, y + d) if y0 <= sy < y0 + h and (x, sy) not in bad]
            if rows:
                pixels[y * width + x] = pixels[rows[0] * width + x]
                break
        else:
            unfilled.append((x, y))
    return unfilled


def fill_from_nearest(
    pixels: bytearray, width: int, mask: Ink, donors: Ink, *, reach: int = 8, parity: bool = False
) -> list[tuple[int, int]]:
    """Replace every masked pixel with the nearest donor's value as it stood before any
    replacement, and return the masked pixels with no donor within `reach` (left as they
    were). Nearest counts a row away as two columns away, so a pixel on a horizontal band
    (a stone's lip, a plank's grain) takes its colour from its own band; and a donor is a
    single nearby pixel, never a run copied from along the row, so a textured ground keeps
    its texture instead of growing streaks. `parity` takes only donors an even number of steps
    away (`dx + dy` even), so a checkerboard dither keeps its phase."""
    source = bytes(pixels)
    order = sorted(
        ((dx, dy) for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1)
         if (dx or dy) and not (parity and (dx + dy) % 2)),
        key=lambda o: (o[0] ** 2 + 4 * o[1] ** 2, abs(o[1]), o),
    )  # fmt: skip
    unfilled = []
    for x, y in sorted(mask):
        for dx, dy in order:
            if (x + dx, y + dy) in donors:
                pixels[y * width + x] = source[(y + dy) * width + x + dx]
                break
        else:
            unfilled.append((x, y))
    return unfilled


def groups(marks: Iterable[tuple[int, int]]) -> list[Ink]:
    """The 8-connected groups of `marks`."""
    out, todo = [], set(marks)
    while todo:
        group, stack = set(), [todo.pop()]
        while stack:
            p = stack.pop()
            group.add(p)
            for q in grown({p}, 1, 1, 1, 1) & todo:
                todo.discard(q)
                stack.append(q)
        out.append(group)
    return out


def stamp(pixels: bytearray, width: int, at: tuple[int, int], ink: Ink, index: int) -> None:
    ax, ay = at
    for x, y in ink:
        pixels[(ay + y) * width + ax + x] = index


def groups(marks: Ink) -> list[Ink]:
    """The 8-connected groups of `marks`."""
    out, todo = [], set(marks)
    while todo:
        group, stack = set(), [todo.pop()]
        while stack:
            p = stack.pop()
            group.add(p)
            for q in grown({p}, 1, 1, 1, 1) & todo:
                todo.discard(q)
                stack.append(q)
        out.append(group)
    return out


def scaled(ink: Ink, n: int) -> Ink:
    return {(x * n + i, y * n + j) for x, y in ink for i in range(n) for j in range(n)}


def bold(ink: Ink) -> Ink:
    """Double every stroke one column to the right: how a 1x face reads as the heavy type
    the original draws its emphasised values in."""
    return ink | {(x + 1, y) for x, y in ink}


def rotated_cw(ink: Ink) -> Ink:
    """A quarter turn clockwise, normalised to the origin: a line reading top to bottom."""
    top = max(y for _, y in ink)
    return {(top - y, x) for x, y in ink}


def extent(ink: Ink) -> Box:
    xs = [x for x, _ in ink]
    ys = [y for _, y in ink]
    return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def normalised(ink: Ink) -> Ink:
    x0, y0, _, _ = extent(ink)
    return {(x - x0, y - y0) for x, y in ink}


def most_used(pixels: bytes | bytearray, width: int, where: Iterable[tuple[int, int]]) -> int:
    return Counter(pixels[y * width + x] for x, y in where).most_common(1)[0][0]


class Canvas:
    """One texture being rebuilt: its stock image, the pixels being edited, and the patches.

    Detection (`type_mask`, `colour(stock=True)`) reads `stock`, the image as shipped, so what
    a recipe finds is the Japanese even after it has painted elsewhere; everything else reads
    and writes the edited pixels. (A recipe that reshapes the art first -- a widened balloon
    -- replaces `stock` with the reshaped art.)

    `drawn_4bpp` is for a TIM whose header says 8bpp but which the game draws as 4bpp
    (`_DATA_NIKKI_W.BIN__005450`, `research/texture-recipes.md`): each byte is two pixels,
    low nibble on the left, the image twice as wide, and a sprite's colours are the 16
    entries of a CLUT row from `16 * chunk` -- the slice the game points it at.
    """

    def __init__(self, texture: Texture, *, drawn_4bpp: bool = False) -> None:
        self.texture = texture
        self.tim = texture.tim
        self.drawn_4bpp = drawn_4bpp
        raw = texture.tim.indices()
        if not drawn_4bpp:
            self.width = texture.tim.width
            self.pixels = bytearray(raw)
        else:
            if texture.tim.bpp != 8:
                raise ValueError(f"{texture.id} is already {texture.tim.bpp}bpp")
            self.width = texture.tim.width * 2
            self.pixels = bytearray(len(raw) * 2)
            self.pixels[0::2] = bytes(v & 0xF for v in raw)
            self.pixels[1::2] = bytes(v >> 4 for v in raw)
        self.height = len(self.pixels) // self.width
        self.stock = bytes(self.pixels)
        self._palettes: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {}

    def palette(self, clut: int, chunk: int = 0) -> list[tuple[int, int, int, int]]:
        """CLUT `clut`; drawn at 4bpp, its 16 entries from `16 * chunk`."""
        if (clut, chunk) not in self._palettes:
            full = self.tim.palette_rgba(clut)
            self._palettes[clut, chunk] = full[16 * chunk :][:16] if self.drawn_4bpp else full
        return self._palettes[clut, chunk]

    def at(self, point: tuple[int, int], *, stock: bool = False) -> int:
        source = self.stock if stock else self.pixels
        return source[point[1] * self.width + point[0]]

    def colour(self, clut: int, point: tuple[int, int], *, stock: bool = False, chunk: int = 0):
        """The colour `point` shows through `clut` (`chunk`), as edited or as shipped."""
        return self.palette(clut, chunk)[self.at(point, stock=stock)]

    def type_mask(self, kind: str, clut: int, box: Box) -> Ink:
        """`pale_type` or `dark_type` of the stock image, by name."""
        keep = {"pale": pale, "dark": dark}[kind]
        return where(self.stock, self.width, self.palette(clut), box, keep)

    def most_used(self, where: Iterable[tuple[int, int]], *, stock: bool = False) -> int:
        return most_used(self.stock if stock else self.pixels, self.width, where)

    def fill(self, box: Box, index: int) -> None:
        x0, y0, w, h = box
        for y in range(y0, y0 + h):
            self.pixels[y * self.width + x0 : y * self.width + x0 + w] = bytes([index]) * w

    def stamp(self, at: tuple[int, int], ink: Ink, index: int) -> None:
        stamp(self.pixels, self.width, at, ink, index)

    def paint_out(self, box: Box, mask: Ink, *, avoid: Ink = frozenset()):
        return paint_out(self.pixels, self.width, box, mask, avoid=avoid)

    def fill_from_nearest(self, mask: Ink, donors: Ink, *, parity: bool = False, reach: int = 8):
        return fill_from_nearest(self.pixels, self.width, mask, donors, parity=parity, reach=reach)

    def patches(self) -> list[ByteEdit]:
        """The verified byte edits that turn the stock image into this one, at every copy."""
        pixels = bytes(self.pixels)
        if self.drawn_4bpp:
            pixels = bytes(lo | hi << 4 for lo, hi in zip(pixels[0::2], pixels[1::2], strict=True))
        return patches_for(self.texture, self.tim.with_indices(pixels))


__all__ = [
    "Box",
    "Canvas",
    "Ink",
    "bold",
    "dark_type",
    "extent",
    "fill_from_nearest",
    "groups",
    "grown",
    "most_used",
    "normalised",
    "paint_out",
    "pale_type",
    "points",
    "rotated_cw",
    "scaled",
    "stamp",
]
