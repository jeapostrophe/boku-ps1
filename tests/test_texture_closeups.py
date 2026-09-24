"""`boku.texture_closeups`: the plane a close-up's writing lies in, the refill along its rules,
and how much of each pixel the English covers -- on synthetic pictures, no disc."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from boku import texture_closeups as tc
from boku import texture_paint as paint
from boku.texture_text import Entry, TextureTextError
from boku.typeset import Glyph, PixelFace

TURNED = tc.Plane(
    size=(60, 40),
    corners=((20.0, 40.0), (20.0 + 60 * math.cos(0.5), 40.0 - 60 * math.sin(0.5)),
             (20.0 + 60 * math.cos(0.5) + 40 * math.sin(0.5),
              40.0 - 60 * math.sin(0.5) + 40 * math.cos(0.5)),
             (20.0 + 40 * math.sin(0.5), 40.0 + 40 * math.cos(0.5))),
)  # fmt: skip
"""A 60x40 page turned half a radian (29 degrees) anticlockwise, its top-left at (20, 40)."""


def test_a_plane_puts_its_corners_where_it_was_told_and_maps_back():
    w, h = TURNED.size
    for upright, picture in zip(((0, 0), (w, 0), (w, h), (0, h)), TURNED.corners, strict=True):
        assert TURNED.picture(upright) == pytest.approx(picture)
        assert TURNED.upright(picture) == pytest.approx(upright)


def test_a_plane_refuses_corners_three_of_which_are_in_a_line():
    with pytest.raises(ValueError, match="in a line"):
        tc.Plane(size=(10, 10), corners=((0, 0), (5, 0), (10, 0), (0, 10)))


@dataclass
class Pixels:
    """The two fields of a `paint.Canvas` the refill uses."""

    pixels: bytearray
    width: int


STRIPE = 5
"""Rows of the synthetic ruled page: an index per 5-row band of the upright page, alternating."""


def ruled(width: int = 100, height: int = 100) -> tuple[bytearray, dict]:
    """A picture of `TURNED` whose every pixel is the index of its upright band (1 or 2), and
    the page's pixels with their upright points."""
    page = TURNED.pixels((0, 0, *TURNED.size))
    pixels = bytearray(width * height)
    for (x, y), (_, v) in page.items():
        pixels[y * width + x] = 1 + int(v // STRIPE) % 2
    return pixels, page


def test_the_refill_keeps_each_pixel_on_its_own_rule():
    """A blot across the bands of a turned page: every blotted pixel comes back as its band's
    index. A refill along the picture's rows (as `paint.paint_out` does for upright plates)
    crosses the turned bands and brings the wrong one into about a third of it."""
    width = 100
    pixels, page = ruled(width)
    blot = {p for p, (u, v) in page.items() if 20 <= u < 32 and 8 <= v < 30}
    for x, y in blot:
        pixels[y * width + x] = 9
    rows = bytearray(pixels)
    paint.paint_out(rows, width, (0, 0, width, 100), blot)
    tc.refill_along_rules(Pixels(pixels, width), TURNED, blot, page, what="the blot")

    def wrong(refilled: bytearray) -> list[tuple[int, int]]:
        out = []
        for x, y in blot:
            v = page[x, y][1]
            inside = abs(v - STRIPE * round(v / STRIPE)) > 0.5  # a band's inside, not its edge
            if inside and refilled[y * width + x] != 1 + int(v // STRIPE) % 2:
                out.append((x, y))
        return out

    assert len(blot) > 150
    assert wrong(pixels) == []
    assert len(wrong(rows)) > len(blot) // 5


def test_the_refill_refuses_a_pixel_whose_rule_has_no_clean_pixel():
    width = 100
    pixels, page = ruled(width)
    rule = {p for p, (_, v) in page.items() if 20 <= v < 21}
    with pytest.raises(TextureTextError, match="no clean pixel on their rule"):
        tc.refill_along_rules(Pixels(pixels, width), TURNED, rule, page, what="a whole rule")


def test_coverage_is_the_ink_itself_on_an_unturned_plane():
    """An upright plane is the identity: each inked pixel is covered wholly, nothing else."""
    flat = tc.Plane(size=(10, 10), corners=((0, 0), (10, 0), (10, 10), (0, 10)))
    ink = {(0, 0), (1, 0), (1, 1), (3, 2)}
    assert tc.coverage(flat, ink, (2.0, 3.0)) == {(x + 2, y + 3): 1.0 for x, y in ink}


def test_coverage_of_turned_ink_adds_up_to_its_area():
    """Turning preserves area: a 6x3 block's coverage, summed over the pixels it touches,
    is 18 pixels to within the 4x4 sampling's error, and no pixel is more than covered."""
    block = {(x, y) for x in range(6) for y in range(3)}
    cover = tc.coverage(TURNED, block, (20.0, 10.0))
    assert sum(cover.values()) == pytest.approx(18, abs=1.5)
    assert max(cover.values()) <= 1.0
    assert len(cover) > 18


def test_coverage_reaches_ink_that_does_not_start_at_the_origin():
    """A line's ink keeps its glyph cell's rows (a lower-case line starts at row 3 and its
    descenders reach row 11), so coverage must look where the ink is, not at its size from
    the origin."""
    flat = tc.Plane(size=(20, 20), corners=((0, 0), (20, 0), (20, 20), (0, 20)))
    ink = {(3, 3), (3, 11)}
    assert tc.coverage(flat, ink, (0.0, 0.0)) == {(3, 3): 1.0, (3, 11): 1.0}


def test_emboldened_letters_keep_a_column_of_air_between_them():
    """Two one-column letters a column apart: `paint.bold` of the line joins them into one
    block; `emboldened` sets each bold letter and moves the next on until a column of air is
    between them -- and, tall, doubles every row."""
    bar = Glyph(1, tuple((0,) for _ in range(4)))
    face = PixelFace("t", 4, 5, 2, {"l": bar})
    entry = Entry("tex@T.x", "ll", "t:1")
    assert {x for x, _ in paint.bold(face.ink("ll"))} == {0, 1, 2, 3}
    for tall, rows in ((False, 4), (True, 8)):
        ink = tc.emboldened(face, entry, "ll", tall)
        assert {x for x, _ in ink} == {0, 1, 3, 4}
        assert {y for _, y in ink} == set(range(rows))
