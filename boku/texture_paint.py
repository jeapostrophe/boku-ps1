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


def _where(tim: Tim, clut: int, box: Box, keep) -> Ink:
    idx, palette = tim.indices(), tim.palette_rgba(clut)
    return {(x, y) for x, y in points(box) if keep(palette[idx[y * tim.width + x]])}


def pale_type(tim: Tim, clut: int, box: Box, *, spread: int = 60, lightest: int = 110) -> Ink:
    """The pixels of `box` drawn in a pale, near-neutral colour through CLUT `clut`: white
    type and its grey antialiasing, against a saturated or dark ground."""
    return _where(
        tim, clut, box,
        lambda c: c[3] and max(c[:3]) - min(c[:3]) < spread and luminance(c) > lightest,
    )  # fmt: skip


def dark_type(tim: Tim, clut: int, box: Box, *, darkest: int = 100, spread: int = 256) -> Ink:
    """The pixels of `box` darker than `darkest` through CLUT `clut`: dark type on a pale
    plate. A `spread` keeps only near-grey ones, leaving a dark crayon or photo out."""
    return _where(
        tim, clut, box,
        lambda c: c[3] and luminance(c) < darkest and max(c[:3]) - min(c[:3]) < spread,
    )  # fmt: skip


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


def stamp(pixels: bytearray, width: int, at: tuple[int, int], ink: Ink, index: int) -> None:
    ax, ay = at
    for x, y in ink:
        pixels[(ay + y) * width + ax + x] = index


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

    Detection (`type_mask`) reads the **stock** image, so what a recipe finds is the
    Japanese as shipped even after it has painted elsewhere; everything else reads and
    writes the edited pixels.
    """

    def __init__(self, texture: Texture) -> None:
        self.texture = texture
        self.tim = texture.tim
        self.width = texture.tim.width
        self.pixels = bytearray(texture.tim.indices())
        self._palettes: dict[int, list[tuple[int, int, int, int]]] = {}

    def palette(self, clut: int) -> list[tuple[int, int, int, int]]:
        if clut not in self._palettes:
            self._palettes[clut] = self.tim.palette_rgba(clut)
        return self._palettes[clut]

    def at(self, point: tuple[int, int]) -> int:
        return self.pixels[point[1] * self.width + point[0]]

    def type_mask(self, kind: str, clut: int, box: Box) -> Ink:
        """`pale_type` or `dark_type` of the stock image, by name."""
        return {"pale": pale_type, "dark": dark_type}[kind](self.tim, clut, box)

    def most_used(self, where: Iterable[tuple[int, int]]) -> int:
        return most_used(self.pixels, self.width, where)

    def fill(self, box: Box, index: int) -> None:
        x0, y0, w, h = box
        for y in range(y0, y0 + h):
            self.pixels[y * self.width + x0 : y * self.width + x0 + w] = bytes([index]) * w

    def stamp(self, at: tuple[int, int], ink: Ink, index: int) -> None:
        stamp(self.pixels, self.width, at, ink, index)

    def paint_out(self, box: Box, mask: Ink, *, avoid: Ink = frozenset()):
        return paint_out(self.pixels, self.width, box, mask, avoid=avoid)

    def patches(self) -> list[ByteEdit]:
        """The verified byte edits that turn the stock image into this one, at every copy."""
        return patches_for(self.texture, self.tim.with_indices(bytes(self.pixels)))


__all__ = [
    "Box",
    "Canvas",
    "Ink",
    "bold",
    "dark_type",
    "extent",
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
