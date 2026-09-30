"""`boku.clip_preview`: an epilogue's pages as the screen shows them (PLAN `VO-09`).

Whether what it draws is what the game draws is `tests/test_real_clip_subtitle_beetle.py`'s:
a frame drawn here against the same frame on Beetle PSX, pixel for pixel. Here: the band
and the text by their rules, and the pictures read from the import's own packs.
"""

from __future__ import annotations

import pytest

from boku import clip_preview, epilogue
from boku.clip_preview import HEIGHT, INK, SHADOW, WHITE, WIDTH, Band
from boku.typeset import CELL

BAND = Band(pen_x=24, pen_y=193, line_pitch=11, band_y=191, band_h=37, band_brightness=168)


class OneDot:
    """A font whose every cell is one pixel, at column 2 of row 3; an encoder of advance 5
    for which `?` has no cell."""

    def cell_bits(self, glyph_id: int) -> list[list[int]]:
        return [[int((row, column) == (3, 2)) for column in range(CELL)] for row in range(CELL)]

    def glyph(self, character: str) -> int | None:
        return None if character == "?" else ord(character)

    def advance(self, character: str) -> int:
        return 5


def pixel(canvas: bytearray, x: int, y: int) -> tuple[int, ...]:
    return tuple(canvas[3 * (y * WIDTH + x) : 3 * (y * WIDTH + x) + 3])


def drawn(lines, grey: int = 100) -> bytearray:
    canvas = bytearray([grey]) * (WIDTH * HEIGHT * 3)
    font = OneDot()
    clip_preview.draw_subtitle(canvas, lines, font, font, BAND)
    return canvas


def test_the_band_adds_its_brightness_to_its_own_rows_and_stops_at_white():
    canvas = drawn([])
    assert pixel(canvas, 0, BAND.band_y - 1) == (100, 100, 100)
    assert (
        pixel(canvas, 0, BAND.band_y) == pixel(canvas, WIDTH - 1, BAND.band_y + 36) == (WHITE,) * 3
    )
    assert pixel(canvas, 0, BAND.band_y + BAND.band_h) == (100, 100, 100)
    assert pixel(drawn([], grey=8), 5, BAND.band_y + 1) == (8 + BAND.band_brightness,) * 3


def test_a_glyph_is_ink_over_its_shadow_one_right_and_one_down():
    canvas = drawn(["a"])
    x, y = BAND.pen_x + 2, BAND.pen_y + 3
    assert pixel(canvas, x, y) == INK
    assert pixel(canvas, x + 1, y) == pixel(canvas, x, y + 1) == SHADOW
    assert pixel(canvas, x + 1, y + 1) == pixel(canvas, x - 1, y) == (WHITE,) * 3


def test_the_pen_steps_by_the_encoders_advance_and_a_line_by_the_pitch():
    canvas = drawn(["ab", "c"])
    assert pixel(canvas, BAND.pen_x + 2 + 5, BAND.pen_y + 3) == INK
    assert pixel(canvas, BAND.pen_x + 2, BAND.pen_y + BAND.line_pitch + 3) == INK


def test_a_character_without_a_cell_draws_nothing_and_still_moves_the_pen():
    canvas = drawn(["?a"])
    assert pixel(canvas, BAND.pen_x + 2, BAND.pen_y + 3) == (WHITE,) * 3
    assert pixel(canvas, BAND.pen_x + 2 + 5, BAND.pen_y + 3) == INK


def test_a_preview_is_a_png_of_the_screen():
    from boku.png import read

    picture = read(clip_preview.png(drawn(["a"])))
    assert (picture.width, picture.height) == (WIDTH, HEIGHT)


# --- the import's own pictures --------------------------------------------------------------


def lit(canvas: bytearray) -> int:
    return sum(1 for at in range(0, len(canvas), 3) if any(canvas[at : at + 3]))


@pytest.mark.parametrize("ending", range(epilogue.ENDINGS))
def test_each_endings_stills_fill_the_screen_and_differ(archive, ending):
    """A still is pieces of an atlas placed on the screen: placed wrongly they leave holes
    (black) or land off it."""
    first, second = (clip_preview.still(archive, ending, which) for which in (0, 1))
    assert len(first) == len(second) == WIDTH * HEIGHT * 3
    assert lit(first) > 0.9 * WIDTH * HEIGHT and lit(second) > 0.9 * WIDTH * HEIGHT
    assert first != second


def test_the_production_card_is_a_few_lines_of_type_on_black_where_endoti_draws_it(archive):
    canvas = clip_preview.card(archive, 0)
    _, y = clip_preview.CARD_AT
    rows = {at // 3 // WIDTH for at in range(0, len(canvas), 3) if any(canvas[at : at + 3])}
    assert rows and min(rows) >= y and max(rows) < y + 33
    assert 0 < lit(canvas) < 0.1 * WIDTH * HEIGHT
    assert all(clip_preview.card(archive, n) == canvas for n in range(1, epilogue.ENDINGS))


def test_the_backdrop_is_the_picture_up_at_that_vsync(archive):
    picture = epilogue.pictures(archive)[epilogue.FIRST_CLIP]
    show = {name: (start + end) // 2 for name, start, end in picture.phases}
    backdrop = {
        name: clip_preview.backdrop(archive, picture, at, None) for name, at in show.items()
    }
    assert backdrop[epilogue.FIRST_STILL] == clip_preview.still(archive, 0, 0)
    assert backdrop[epilogue.SECOND_STILL] == clip_preview.still(archive, 0, 1)
    assert backdrop[epilogue.CARD] == clip_preview.card(archive, 0)
    assert lit(backdrop[epilogue.BLACK]) == 0
