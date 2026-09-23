"""The small faces drawn for this project (`boku/faces/*.txt`, `boku.typeset.PixelFace`).

No disc: the faces are our own pixels, tracked. What is asserted about a glyph's pixels is
read back out of the face file itself, never retyped here.
"""

from __future__ import annotations

import string

import pytest

from boku.typeset import FACES_DIR, PixelFace, TypesetError, pixel_face

FACES = sorted(p.stem for p in FACES_DIR.glob("*.txt"))


def test_the_two_ruled_faces_are_tracked():
    assert {"bean", "sprout"} <= set(FACES)


@pytest.mark.parametrize("slug", FACES)
def test_a_face_draws_every_letter_and_digit_inside_its_cell(slug):
    face = pixel_face(slug)
    assert face.missing(string.ascii_letters + string.digits) == []
    for ch in string.ascii_letters + string.digits:
        g = face.glyph(ch)
        assert len(g.rows) == face.cell
        assert any(g.rows), ch
        assert all(0 <= x < g.width for row in g.rows for x in row), ch


@pytest.mark.parametrize("slug", FACES)
def test_the_hyphen_and_quotes_the_game_sheet_lacks_are_drawn(slug):
    face = pixel_face(slug)
    assert face.missing("-\"'[]") == []
    assert face.glyph("\u2019") == face.glyph("'")


def test_ink_is_the_file_rows_at_their_advances(tmp_path):
    path = tmp_path / "t.txt"
    path.write_text(
        "name T\ncell 3\npitch 4\nspace 2\n\n== a\n#.\n.#\n\n== b\n#\n#\n#\n", encoding="utf-8"
    )
    face = PixelFace.load(path)
    assert (face.cell, face.pitch, face.space) == (3, 4, 2)
    assert face.measure("ab") == 2 + 1 + 1
    assert face.ink("a b") == {(0, 0), (1, 1), (3 + 2, 0), (5, 1), (5, 2)}


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("== a\n#\n#\n#\n#\n", "taller than its cell"),
        ("== a\n#\n\n== a\n#\n", "twice"),
        ("== ab\n#\n", "one character"),
        ("== a\n#x\n", "only '#' and '.'"),
        ("== a\n", "no rows"),
    ],
)
def test_a_malformed_face_file_is_refused_with_its_line(tmp_path, body, why):
    path = tmp_path / "bad.txt"
    path.write_text("name B\ncell 3\npitch 4\nspace 2\n\n" + body, encoding="utf-8")
    with pytest.raises(TypesetError, match=why):
        PixelFace.load(path)


def test_a_face_file_missing_a_header_is_refused(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_text("name B\ncell 3\n\n== a\n#\n", encoding="utf-8")
    with pytest.raises(TypesetError, match="pitch"):
        PixelFace.load(path)
