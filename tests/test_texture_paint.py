"""`boku.texture_paint`: the pixel operations the texture recipes are built from."""

from __future__ import annotations

from boku import texture_paint as paint


def test_a_quarter_turn_clockwise_reads_top_to_bottom():
    # A bar along row 1 (the baseline) with a stroke rising from its left end: an "L".
    ink = {(0, 0), (0, 1), (1, 1), (2, 1)}
    # Turned clockwise the baseline runs down column 0, first letter at the top, and the
    # rising stroke now points right from that top end.
    assert paint.rotated_cw(ink) == {(0, 0), (0, 1), (0, 2), (1, 0)}


def test_bold_doubles_each_stroke_rightwards_and_scaled_is_blocky():
    assert paint.bold({(0, 0)}) == {(0, 0), (1, 0)}
    assert paint.scaled({(1, 0)}, 2) == {(2, 0), (3, 0), (2, 1), (3, 1)}


def test_grown_dilates_by_a_rectangle():
    assert paint.grown({(5, 5)}, 1, 0, 2, 1) == {(x, y) for x in range(4, 8) for y in range(5, 7)}


def test_paint_out_takes_a_donor_an_even_distance_away_in_the_same_row():
    """A two-colour ordered dither (a b a b ...) keeps its phase through a painted-out run."""
    width = 12
    row = bytearray([1, 2] * 6)
    mask = {(4, 0), (5, 0), (6, 0)}
    for x, _ in mask:
        row[x] = 9
    paint.paint_out(row, width, (0, 0, width, 1), mask)
    assert row == bytearray([1, 2] * 6)


def test_paint_out_never_takes_a_donor_from_an_avoided_pixel():
    width = 7
    row = bytearray([3, 3, 7, 9, 7, 3, 3])
    left = paint.paint_out(row, width, (0, 0, width, 1), {(3, 0)}, avoid={(1, 0), (5, 0)})
    # The pixels two away (x 1 and x 5) are a rule; the next even donors are x -1 (outside)
    # and x 7 (outside), and a one-row box has no column: the pixel is left and reported.
    assert row[3] == 9 and left == [(3, 0)]


def test_paint_out_falls_back_to_the_column_when_a_row_has_no_donor():
    width = 3
    pixels = bytearray([5, 5, 5, 9, 9, 9, 5, 5, 5])
    mask = {(0, 1), (1, 1), (2, 1)}
    paint.paint_out(pixels, width, (0, 0, 3, 3), mask)
    assert pixels == bytearray([5] * 9)


def test_extent_and_normalised():
    ink = {(3, 4), (5, 7)}
    assert paint.extent(ink) == (3, 4, 3, 4)
    assert paint.normalised(ink) == {(0, 0), (2, 3)}
