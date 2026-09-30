"""The encyclopedia spreads (`boku.texture_books`) against the contributor's import, and on
Beetle PSX.

Texture level: on every rebuilt page, in both lightings of the insect book, the inked pixels of
each text area are exactly as many as its English lines ink (every line there; nothing else
inked in the area); outside the areas only strokes of the Japanese change, never the
photograph or a rule, and none is left across an area's edge; the grey curl under the name and
header stays. The lines are the tracked English wrapped in the page's faces.

On Beetle (`BOKU_EMU_TESTS=1`): an image carrying only the texture edits opens each book at
its first page (the book modes forced by hand, as `test_real_texture_text_beetle` does the
diary's), and every texel of the text areas shows its rebuilt colour within the page's dither
(each texel its colour or 8 less on every channel, measured). The stock image fails it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter

import pytest

from boku import REPO_ROOT
from boku import texture_books as books
from boku import texture_paint as paint
from boku.png import read as read_png
from boku.texture_text import read_entries
from boku.textures import Texture
from boku.tim import luminance, parse_exact
from boku.typeset import FONT_SHEET_ID, GameFace, pixel_face, wrap
from tests.test_real_texture_text_beetle import FIELD, mode_set_pokes

ENTRIES = read_entries()


def page_fields(namespace: str, n: int) -> dict[str, str]:
    prefix = f"{namespace}{n}."
    return {k.removeprefix(prefix): e.text for k, e in ENTRIES.items() if k.startswith(prefix)}


@pytest.fixture(scope="module")
def game(texture_inventory) -> GameFace:
    return GameFace.from_sheet(texture_inventory.get(FONT_SHEET_ID).tim)


def rebuilt(inv, patched: bytes, texture) -> paint.Canvas:
    tim = parse_exact(patched, texture.occurrences[0].file_offset)
    return paint.Canvas(Texture(texture.id, "0" * 40, tim, ()))


def inked(canvas: paint.Canvas, box: paint.Box) -> set:
    palette = canvas.palette(0)
    return {p for p in paint.points(box) if luminance(palette[canvas.at(p)]) < books.INK}


def ink_count(face, lines) -> int:
    return sum(len(face.ink(line)) for line in lines if line)


INSECT_PAGES, KITE_PAGES = 9, 8
"""The spreads each pack stores (the test below reads them off the import)."""


def test_every_page_of_both_books_is_translated(texture_inventory):
    for namespace, packs, count, names in (
        (books.INSECT, books.INSECT_PACKS, INSECT_PAGES, books.INSECT_FIELDS),
        (books.KITE, (books.KITE_PACK,), KITE_PAGES, books.KITE_FIELDS),
    ):
        assert all(len(books.pages(texture_inventory, pack)) == count for pack in packs)
        for n in range(count):
            assert set(page_fields(namespace, n)) == set(names), f"{namespace}{n}"


@pytest.mark.parametrize("n", range(INSECT_PAGES))
@pytest.mark.parametrize("pack", books.INSECT_PACKS)
def test_an_insect_page_carries_its_english_and_no_japanese(
    n, pack, texture_inventory, texture_patched, game
):  # fmt: skip
    text = page_fields(books.INSECT, n)
    canvas = rebuilt(texture_inventory, texture_patched, books.pages(texture_inventory, pack)[n])
    bean = pixel_face(books.BODY_FACE)
    name_face = game if game.measure(text["name"]) <= books.INSECT_NAME.box[2] else bean
    assert len(inked(canvas, books.INSECT_NAME.box)) == ink_count(name_face, [text["name"]])
    header = [line for k in books.INSECT_HEADER_FIELDS
              for line in wrap(text[k], bean, books.INSECT_HEADER.box[2])]  # fmt: skip
    assert len(inked(canvas, books.INSECT_HEADER.box)) == ink_count(bean, header)
    width = min(a.box[2] for a in books.INSECT_BODY) - 2 * books.INSET
    body = inked(canvas, books.INSECT_BODY[0].box) | inked(canvas, books.INSECT_BODY[1].box)
    assert len(body) == ink_count(bean, wrap(text["body"], bean, width))


@pytest.mark.parametrize("n", range(KITE_PAGES))
def test_a_kite_page_carries_its_english_and_no_japanese(
    n, texture_inventory, texture_patched, game
):  # fmt: skip
    text = page_fields(books.KITE, n)
    canvas = rebuilt(
        texture_inventory, texture_patched, books.pages(texture_inventory, books.KITE_PACK)[n]
    )
    bean = pixel_face(books.BODY_FACE)
    width = books.KITE_SET[2]
    expected = (
        ink_count(game, wrap(text["name"], game, width))
        + ink_count(bean, [f"[{text['level']}]"])
        + ink_count(bean, wrap(text["body"], bean, width - 2 * books.INSET))
    )
    assert len(inked(canvas, books.KITE_TEXT.box)) == expected


def book_pages():
    yield from ((pack, n) for pack in books.INSECT_PACKS for n in range(INSECT_PAGES))
    yield from ((books.KITE_PACK, n) for n in range(KITE_PAGES))


def areas(pack: str) -> list:
    if pack == books.KITE_PACK:
        return [books.KITE_TEXT]
    return [books.INSECT_NAME, books.INSECT_HEADER, *books.INSECT_BODY]


COLOURFUL = 40
"""Saturation over which a pixel is certainly the photograph's or a rule's: stricter than the
recipe's own `FURNITURE`, so the check sees the photograph's duller edge too."""


def colourful(canvas: paint.Canvas) -> set:
    palette = canvas.palette(0)
    return {p for p in paint.points((0, 0, canvas.width, canvas.height))
            if books.saturation(palette[canvas.at(p)]) > COLOURFUL}  # fmt: skip


@pytest.mark.parametrize(("pack", "n"), list(book_pages()))
def test_outside_its_text_areas_a_page_loses_only_japanese(
    pack, n, texture_inventory, texture_patched
):  # fmt: skip
    """What the build changes outside the text areas is strokes of the Japanese running out of
    them: never a pixel of the photograph or a rule, and nothing is left of a stroke crossing
    a body's edge."""
    texture = books.pages(texture_inventory, pack)[n]
    stock, canvas = paint.Canvas(texture), rebuilt(texture_inventory, texture_patched, texture)
    inside = set().union(*(paint.points(a.box) for a in areas(pack)))
    changed = {p for p in paint.points((0, 0, stock.width, stock.height))
               if p not in inside and stock.at(p) != canvas.at(p)}  # fmt: skip
    touching = paint.grown(changed, 1, 1, 1, 1) & colourful(stock)
    assert touching == set(), f"the photograph or a rule was changed next to {sorted(touching)[:3]}"
    palette = canvas.palette(0)
    for area in areas(pack)[-2:] if pack != books.KITE_PACK else areas(pack):  # the bodies
        x0, y0, w, h = area.box
        for row in (y0 - 1, y0 + h):
            left = [(x, row) for x in range(x0, x0 + w)
                    if luminance(palette[canvas.at((x, row))]) < books.INK
                    and not paint.grown({(x, row)}, 1, 1, 1, 1) & colourful(canvas)]  # fmt: skip
            assert left == [], f"a stroke of the Japanese left across {area.box}'s edge: {left[:3]}"


@pytest.mark.parametrize(
    ("pack", "n"), [(p, n) for p in books.INSECT_PACKS for n in range(INSECT_PAGES)]
)
def test_the_grey_curl_under_the_name_and_header_stays(
    pack, n, texture_inventory, texture_patched
):  # fmt: skip
    """The name and header straddle the diagonal edge of the grey curl at the page's top: the
    paper there, white and grey, is kept wherever the English is not inked."""
    texture = books.pages(texture_inventory, pack)[n]
    stock, canvas = paint.Canvas(texture), rebuilt(texture_inventory, texture_patched, texture)
    palette = canvas.palette(0)
    for area in (books.INSECT_NAME, books.INSECT_HEADER):
        points = paint.points(area.box)
        papers = [i for i, _ in Counter(stock.at(p) for p in points).most_common(2)]
        moved = [p for p in points if stock.at(p) in papers and canvas.at(p) != stock.at(p)
                 and luminance(palette[canvas.at(p)]) >= books.INK]  # fmt: skip
        assert moved == [], f"the page's paper was changed in {area.box}: {moved[:3]}"


BOOK_SHOT = FIELD.MODE_SET_AT + FIELD.BOOK_OPEN
"""`mode_set(n)` by hand after the first dialogue (`mode_set_pokes`) opens a book at its first
page (before 19:00, so the insect book is `MZKAN1`, the day pack)."""
BOOKS_ON_SCREEN = {
    # mode: (texture of page 0, where the texture's (0, 0) lands, the text areas)
    FIELD.KITE_MODE: (books.KITE_PACK, (38, 23), [books.KITE_TEXT.box]),
    FIELD.INSECT_MODE: (books.INSECT_PACKS[0], (45, 23),
           [books.INSECT_NAME.box, books.INSECT_HEADER.box, *(a.box for a in books.INSECT_BODY)]),
}  # fmt: skip
"""Measured on the English image by matching the page's texels (`research/texture-recipes.md`
§ "The books")."""
DITHER = 8


@pytest.mark.parametrize("mode", sorted(BOOKS_ON_SCREEN), ids=["kite", "insect"])
def test_a_book_on_beetle_shows_its_english(
    mode, texture_image, texture_inventory, texture_patched, tmp_path
):  # fmt: skip
    pack, (ox, oy), boxes = BOOKS_ON_SCREEN[mode]
    command = [
        sys.executable, str(REPO_ROOT / "tools/libretro/run_core.py"), str(texture_image),
        "--core", os.environ["BOKU_LIBRETRO_CORE"], "--system", os.environ["BOKU_LIBRETRO_SYSTEM"],
        "--work", str(tmp_path), "--frames", str(BOOK_SHOT + 10), "--shot", f"{BOOK_SHOT}:book",
        "--press-file", str(REPO_ROOT / "tools/libretro/boot-to-dialogue.press"),
        *[arg for poke in mode_set_pokes(mode) for arg in ("--poke", poke)],
    ]  # fmt: skip
    subprocess.run(command, check=True, capture_output=True, timeout=600, cwd=REPO_ROOT)
    shot = read_png((tmp_path / "book.png").read_bytes())
    texture = books.pages(texture_inventory, pack)[0]
    canvas = rebuilt(texture_inventory, texture_patched, texture)
    stock = paint.Canvas(texture)
    palette = canvas.palette(0)
    changed, wrong = 0, []
    for x, y in (p for box in boxes for p in paint.points(box)):
        want = [c >> 3 << 3 for c in palette[canvas.at((x, y))][:3]]
        at = ((oy + y) * shot.width + ox + x) * 4
        seen = shot.rgba[at : at + 3]
        changed += canvas.at((x, y)) != stock.at((x, y))
        if not all(0 <= w - s <= DITHER for s, w in zip(seen, want, strict=True)):
            wrong.append((x, y, tuple(seen)))
    assert changed > 500, "the build changed too few texels where the check looked"
    assert wrong == [], f"{len(wrong)} texels differ, first {wrong[:5]}"
