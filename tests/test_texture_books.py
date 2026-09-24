"""`boku.texture_books` without a disc: the page recipe on invented spreads.

The pages are made here (`tests/synth_tim.py`) in the insect book's shape and size: a paper
shaded column by column, "Japanese" in each text area, a photograph (saturated) above the
body with a dark-grey pixel on its edge. The real pages are `tests/test_real_texture_books.py`'s.
"""

from __future__ import annotations

import pytest

from boku import texture_books as books
from boku import texture_paint as paint
from boku.archive import ARCHIVE_NAME
from boku.texture_text import Entry, TextureTextError
from boku.textures import Occurrence, Texture
from boku.tim import parse_exact
from boku.typeset import pixel_face, wrap
from tests import synth_tim as synth

PAPERS = [1, 2, 3]
"""Three near-white greys; each column's paper is one of them (shading toward the spine)."""
INK, PHOTO, DARK_PHOTO = 10, 20, 11
WORDS = [0] * 256
for k, i in enumerate(PAPERS):
    WORDS[i] = (31 - k) * 0x421
WORDS[INK] = 6 * 0x421  # dark grey
WORDS[DARK_PHOTO] = 5 * 0x421  # a dark-grey pixel of the photograph, at its edge
WORDS[PHOTO] = 2 | 24 << 5 | 4 << 10  # green: saturated
W, H = 252, 188


def paper(x: int) -> int:
    return PAPERS[(x // 30) % len(PAPERS)]


def page():
    """Paper everywhere; the photograph above the left body; Japanese strokes in every area,
    and one stroke of the body that runs up out of its box to the photograph's edge."""
    px = [paper(x) for _ in range(H) for x in range(W)]

    def put(x, y, v):
        px[y * W + x] = v

    for y in range(12, 86):
        for x in range(8, 140):
            put(x, y, PHOTO)
    put(20, 86, DARK_PHOTO)  # on the photograph's edge, a pixel above the stroke
    for area in (books.INSECT_NAME, books.INSECT_HEADER, *books.INSECT_BODY):
        x0, y0, w, h = area.box
        for x in range(x0 + 3, x0 + w - 3, 6):
            for y in range(y0 + 2, y0 + h - 2):
                put(x, y, INK)
    for y in range(88, 97):  # a stroke from under the photograph down into the left body
        put(20, y, INK)
    raw = synth.tim(
        1, synth.pixel_block(W // 2, H, bytes(px)), clut=synth.clut_block(256, 1, WORDS)
    )
    tim = parse_exact(raw)
    place = Occurrence(ARCHIVE_NAME, "\\_DATA\\MZKAN1.BIN", 0, 0x1000, tim.length)
    return paint.Canvas(Texture("p", "0" * 40, tim, (place,)))


def test_an_area_is_blanked_whole_each_column_to_its_own_paper():
    canvas = page()
    box = books.INSECT_BODY[1].box
    books.clear_body(canvas, books.Area(box), "the body")
    assert all(canvas.at(p) == paper(p[0]) for p in paint.points(box))


def test_an_area_that_takes_in_the_photograph_is_refused():
    canvas = page()
    x0, _, w, h = books.INSECT_BODY[0].box
    with pytest.raises(TextureTextError, match=r"takes in .* furniture"):
        books.clear_body(canvas, books.Area((x0, 80, w, h)), "the body")


def test_a_stroke_running_out_of_the_box_goes_but_the_photograph_stays():
    """Under the photograph the Japanese starts above the box the English is set in."""
    canvas = page()
    area = books.INSECT_BODY[0]
    books.clear_body(canvas, area, "the body")
    assert all(canvas.at((20, y)) == paper(20) for y in range(88, 96))
    assert canvas.at((20, 86)) == DARK_PHOTO, "the photograph's own dark pixel was blanked"
    assert all(canvas.at((x, 85)) == PHOTO for x in range(8, 140))


class Game:
    """A stand-in for the game's glyphs: 6-px blocks, 12-row cell."""

    name, cell, pitch = "game", 12, 13

    def measure(self, text):
        return max(0, 7 * len(text) - 1)

    def ink(self, text):
        return {(7 * n + dx, dy) for n, ch in enumerate(text) if ch != " "
                for dx in range(6) for dy in range(2, 10)}  # fmt: skip


def fields(body: str) -> dict[str, Entry]:
    texts = {"name": "Musk", "family": "Swallowtail family", "size": "Wingspan 100 mm",
             "food": "Likes nectar", "body": body}  # fmt: skip
    return {k: Entry(f"mzkan@0.{k}", v, f"books.txt:{n}") for n, (k, v) in enumerate(texts.items())}


def test_an_insect_page_sets_every_field_and_leaves_no_japanese():
    """Every inked pixel of the text areas is the English -- as many as its lines ink -- so no
    stroke of the Japanese is left and no line is missing."""
    canvas = page()
    given = fields("It does not like cold places. " * 8)
    books.insect_page(canvas, given, Game(), "page 0")
    bean = pixel_face("bean")
    inked = {p for a in (books.INSECT_NAME, books.INSECT_HEADER, *books.INSECT_BODY)
             for p in paint.points(a.box) if canvas.at(p) == INK}  # fmt: skip
    header = [line for k in books.INSECT_HEADER_FIELDS
              for line in wrap(given[k].text, bean, books.INSECT_HEADER.box[2])]  # fmt: skip
    width = min(a.box[2] for a in books.INSECT_BODY) - 2 * books.INSET
    body = wrap(given["body"].text, bean, width)
    expected = len(Game().ink(given["name"].text)) + sum(len(bean.ink(t)) for t in header + body)
    assert len(inked) == expected


def test_a_body_longer_than_the_spread_is_refused_not_cut():
    with pytest.raises(TextureTextError, match=r"books.txt:4: the body is \d+ lines .* nothing"):
        books.insect_page(page(), fields("It does not like cold places. " * 40), Game(), "p0")
