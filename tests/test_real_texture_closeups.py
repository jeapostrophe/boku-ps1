"""The close-ups' tracked English against the contributor's own import (PLAN `GFX-08`).

Saori's note: the rebuilt page, read back upright through the page's plane, is the English of
`translation/textures/signs.txt` in the game's glyphs and nothing else, every line standing on
its rule alike; the ruled lines run on through where the Japanese was; and nothing outside
the page's text area changed. The English is read out of the translation file and the disc's
glyph sheet; where each line sits is found by searching the page, not recomputed.

Skips without the import. Nothing read here is written anywhere.
"""

from __future__ import annotations

import pytest

from boku import texture_closeups as tc
from boku import texture_paint as paint
from boku import texture_text as tt
from boku.tim import luminance, parse_exact
from boku.typeset import FONT_SHEET_ID, GameFace

READ_DARK = 130
"""A pixel of writing when the page is read back: darker than this (the paper is ~200-250)."""


def upright_dark(tim, plane: tc.Plane, box: paint.Box) -> paint.Ink:
    """The page read back upright: each upright pixel of `box` whose picture pixel is dark."""
    palette, indices = tim.palette_rgba(0), tim.indices()
    out = set()
    for v in range(box[1], box[1] + box[3]):
        for u in range(box[0], box[0] + box[2]):
            x, y = (int(c) for c in plane.picture((u + 0.5, v + 0.5)))
            if luminance(palette[indices[y * tim.width + x]]) < READ_DARK:
                out.add((u, v))
    return out


def best_match(ink: paint.Ink, page: paint.Ink, box: paint.Box) -> tuple[float, tuple[int, int]]:
    """Where in `box` `ink` lands on `page`'s dark pixels best, and the share of its pixels
    with a dark pixel on or beside them -- a one-pixel stroke turned into the picture and read
    back can come back a pixel off."""
    page = paint.grown(page, 1, 1, 1, 1)
    x0, y0, w, h = paint.extent(ink)
    best = (0.0, (0, 0))
    for dy in range(box[1] - 1 - y0, box[1] + box[3] - h + 1 - y0):
        for dx in range(box[0] - 1 - x0, box[0] + box[2] - w + 1 - x0):
            misses, allowed = 0, len(ink) * (1 - best[0])
            for x, y in ink:
                misses += (x + dx, y + dy) not in page
                if misses > allowed:
                    break
            else:
                best = max(best, (1 - misses / len(ink), (dx, dy)))
    return best


def off_page(u: float, v: float) -> bool:
    """What reaches into the text area's right side and is not paper: measured on the stock
    page read upright, the curled corner's edge runs from (74, 3) through (84, 10) to (94, 19),
    and below it the page's dark right edge stands at x 94-97; this keeps two pixels inside."""
    return u >= min(72 + 1.2 * (v - 3), 92)


@pytest.fixture(scope="module")
def note(texture_inventory, texture_patched):
    stock = texture_inventory.get(tc.NOTE_TEXTURE)
    return stock.tim, parse_exact(texture_patched, stock.occurrences[0].file_offset)


@pytest.fixture(scope="module")
def face(texture_inventory):
    return GameFace.from_sheet(texture_inventory.get(FONT_SHEET_ID).tim)


@pytest.fixture(scope="module")
def english(face):
    """Each line of the tracked English, top first, as the game's glyphs in their cell rows."""
    entries = tt.read_entries()
    lines = [*tt.lines_of(entries["tex@M_I14000.note"]), entries["tex@M_I14000.signature"].text]
    return [face.ink(line) for line in lines]


def read_back(tim, english) -> tuple[list[tuple[float, tuple[int, int]]], paint.Ink]:
    """Each line's best match on the page read back (longest first, since a short line could
    hide inside a long one, then in `english`'s order), and the dark pixels no line explains
    -- a line explains what is within two pixels of it -- on the paper."""
    page = upright_dark(tim, tc.NOTE, tc.NOTE_TEXT)
    left, matches = set(page), {}
    for i in sorted(range(len(english)), key=lambda i: -len(english[i])):
        _, (dx, dy) = matches[i] = best_match(english[i], left, tc.NOTE_TEXT)
        left -= paint.grown({(x + dx, y + dy) for x, y in english[i]}, 2, 2, 2, 2)
    return [matches[i] for i in range(len(english))], {p for p in left if not off_page(*p)}


MATCH = 0.95
"""The share of a line's glyph pixels that must read dark, on or beside them, on the page."""


@pytest.mark.parametrize("which", ["rebuilt", "stock"])
def test_the_note_reads_back_as_the_tracked_english_and_nothing_else(note, english, which):
    matches, left = read_back(note[1] if which == "rebuilt" else note[0], english)
    shares = [round(share, 2) for share, _ in matches]
    if which == "stock":
        assert min(shares) < MATCH and len(left) > 100, "the stock page should fail this check"
        return
    assert min(shares) >= MATCH, f"a line of the English does not read on the page: {shares}"
    assert not left, f"{len(left)} dark pixels are not the English, first {sorted(left)[:5]}"


def test_every_line_stands_on_its_rule_alike(note, english):
    """Each line's glyph cell, found on the page, sits the same height above the rule it is
    written on -- a line with no capital ("guy.") no higher than one with capitals -- within
    the read-back's slack: a whole-pixel match against rules at half pixels, and a pixel of
    tolerance in the match."""
    matches, _ = read_back(note[1], english)
    rules = [*tc.NOTE_LINE_RULES[: len(english) - 1], tc.NOTE_SIGNATURE_RULE]
    above = [tc.NOTE_RULES[rule] - dy for (_, (_, dy)), rule in zip(matches, rules, strict=True)]
    assert max(above) - min(above) <= 1.5, f"cell tops above their rules: {above}"


def blueness(c) -> int:
    return c[2] - c[0]


def test_the_ruled_lines_run_on_where_the_japanese_was(note):
    """Where a stroke of the Japanese was and no English is, the refilled paper is bluer on
    a rule than between the rules -- as the untouched paper is. A refill that ignored the
    rules (one paper colour) leaves the two alike."""
    stock, rebuilt = note
    palette, before, after = stock.palette_rgba(0), stock.indices(), rebuilt.indices()
    area = tc.NOTE.pixels(tc.NOTE_TEXT)

    def at(indices, p):
        return palette[indices[p[1] * stock.width + p[0]]]

    def contrast(pixels, indices) -> float:
        on = [blueness(at(indices, p)) for p in pixels
              if min(abs(area[p][1] - r) for r in tc.NOTE_RULES) <= 0.5]  # fmt: skip
        off = [blueness(at(indices, p)) for p in pixels
               if min(abs(area[p][1] - r) for r in tc.NOTE_RULES) >= 1.5]  # fmt: skip
        assert len(on) > 30 and len(off) > 30
        return sum(on) / len(on) - sum(off) / len(off)

    strokes = {p for p in area if luminance(at(before, p)) < tc.NOTE_DARK}
    near = paint.grown(strokes, 3, 3, 3, 3)
    clean = [p for p in area if p not in near]
    refilled = [p for p in strokes if luminance(at(after, p)) >= READ_DARK]
    paper = contrast(clean, before)
    assert paper > 4, "the rules are not where NOTE_RULES says on the stock page"
    assert contrast(refilled, after) > paper / 2


def test_only_the_note_page_changed(note):
    stock, rebuilt = note
    before, after = stock.indices(), rebuilt.indices()
    changed = [(i % stock.width, i // stock.width) for i in range(len(before))
               if before[i] != after[i]]  # fmt: skip
    x0, y0, w, h = tc.NOTE_TEXT
    outside = [p for p in changed
               if not (x0 - 1 <= (uv := tc.NOTE.upright((p[0] + 0.5, p[1] + 0.5)))[0] < x0 + w + 1
                       and y0 - 1 <= uv[1] < y0 + h + 1)]  # fmt: skip
    assert len(changed) > 1000
    assert outside == []


def note_entries(note: str, signature: str = "From Saori") -> list[tt.Entry]:
    return [tt.Entry("tex@M_I14000.note", note, "t:1"), tt.Entry("tex@M_I14000.signature",
            signature, "t:2")]  # fmt: skip


@pytest.mark.parametrize(
    ("note", "signature", "refusal"),
    [(" // ".join(["Bye."] * 6), "Saori", "the note is 6 lines and the page holds 5"),
     ("Goodbye, goodbye!", "Saori", r"is \d+ px and a line of the note holds 83"),
     ("Goodbye.", "With love, your friend Saori",
      r"is \d+ px and a line of the note holds 86"),
     ("Goodbye. //  // guy.", "Saori", "the note has an empty line")],
    ids=["six lines", "too wide", "signature too wide", "empty line"],
)  # fmt: skip
def test_a_note_that_does_not_fit_the_page_is_refused(
    archive, texture_inventory, face, note, signature, refusal
):
    with pytest.raises(tt.TextureTextError, match=refusal):
        tc.note(archive, texture_inventory, face, note_entries(note, signature))


def test_a_line_written_onto_the_curled_corner_is_refused(
    archive, texture_inventory, face, monkeypatch
):
    """The curl reaches into the text area's top right; a first line set a few rules higher
    than the recipe sets it, and wide, would be written across it."""
    monkeypatch.setattr(tc, "NOTE_LINE_RULES", (1, *tc.NOTE_LINE_RULES[1:]))
    with pytest.raises(tt.TextureTextError, match="off the paper"):
        tc.note(archive, texture_inventory, face, note_entries("MMMMMMMM"))


def test_the_pen_is_a_stroke_pixel_even_when_there_are_fewer_than_four(texture_inventory):
    canvas = paint.Canvas(texture_inventory.get(tc.NOTE_TEXTURE))
    one = next(iter(tc.note_japanese(canvas, tc.NOTE.pixels(tc.NOTE_TEXT))[0]))
    assert tc.pen(canvas, {one}) == canvas.at(one)
