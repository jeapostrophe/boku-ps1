"""The close-ups' tracked English against the contributor's own import (PLAN `GFX-08`).

Saori's note: the rebuilt page, read back upright through the page's plane, is the English of
`translation/textures/signs.txt` in the game's glyphs and nothing else, every line standing on
its rule alike; the ruled lines run on through where the Japanese was; and nothing outside
the page's text area changed. The English is read out of the translation file and the disc's
glyph sheet; where each line sits is found by searching the page, not recomputed.

Skips without the import. Nothing read here is written anywhere.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Callable
from functools import cache

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


def test_the_pen_is_a_stroke_pixel_even_when_there_are_fewer_than_ten(texture_inventory):
    canvas = paint.Canvas(texture_inventory.get(tc.NOTE_TEXTURE))
    one = next(iter(tc.note_japanese(canvas, tc.NOTE.pixels(tc.NOTE_TEXT))[0]))
    assert tc.pen(canvas, {one}) == canvas.at(one)


# --- M_I23000: the hunting association's board ---------------------------------------------------


@pytest.fixture(scope="module")
def board(texture_inventory, texture_patched):
    stock = texture_inventory.get(tc.BOARD_TEXTURE)
    return stock.tim, parse_exact(texture_patched, stock.occurrences[0].file_offset)


@cache
def _pixels(tim) -> tuple[list, bytes]:
    return tim.palette_rgba(0), tim.indices()


def rgb(tim, p):
    palette, indices = _pixels(tim)
    return palette[indices[p[1] * tim.width + p[0]]]


def black(c) -> bool:
    return luminance(c) < 100 and max(c[:3]) - min(c[:3]) < 40


def red(c) -> bool:
    return c[0] > 120 and c[0] - c[1] > 50 and c[0] - c[2] > 30


def yellow(c) -> bool:
    return c[0] > 120 and c[1] > 100 and c[2] < c[1] - 40


def pale(c) -> bool:
    return luminance(c) > 200 and max(c[:3]) - min(c[:3]) < 40


PAINT = {"black": black, "red": red}


@pytest.fixture(scope="module")
def board_english(face):
    """Each sign's English as the build sets it, from the tracked strings and the disc's
    glyphs (`emboldened` is checked on its own in `tests/test_texture_closeups.py`)."""
    entries = tt.read_entries()
    return {
        sign.key: tc.board_ink(face, entries[f"tex@M_I23000.{sign.key}"], sign)
        for sign in tc.BOARD_SIGNS
    }  # fmt: skip


def placed(ink: paint.Ink, painted: paint.Ink, room: paint.Box) -> list[tuple[int, int]]:
    """Every shift in `room` at which all of `ink` is painted."""
    _, _, w, h = paint.extent(ink)
    return [
        (dx, dy)
        for dy in range(room[1], room[1] + room[3] - h + 1)
        for dx in range(room[0], room[0] + room[2] - w + 1)
        if all((x + dx, y + dy) in painted for x, y in ink)
    ]


STROKE = 10
"""A group of this many painted pixels or more in a sign's box is writing, not weathering."""


def english_on(tim, board_english) -> tuple[dict[str, paint.Ink], list[str]]:
    """Each sign's English where it is painted -- whole, once, in its room, in its paint --
    and what is wrong."""
    found, problems = {}, []
    for sign in tc.BOARD_SIGNS:
        painted = {p for p in paint.points(sign.room) if PAINT[sign.colour](rgb(tim, p))}
        at = placed(board_english[sign.key], painted, sign.room)
        if len(at) != 1:
            problems.append(f"{sign.key}: the English is painted at {len(at)} places")
        else:
            found[sign.key] = {(x + at[0][0], y + at[0][1]) for x, y in board_english[sign.key]}
    return found, problems


@pytest.fixture(scope="module")
def trail(board) -> Callable[[tuple[int, int]], bool]:
    """The bullet's trail, measured here and not taken from the recipe: its two thin lines
    fitted on the stock board where they cross open board between the two black lines (x
    172-188, y 105-126: nothing else is drawn there), each extended across the boxes; a pixel
    of the trail is within a pixel of one of them, from the gun's muzzle (x 140) on. (Where the
    Japanese touches the trail, its strokes a pixel further out are the Japanese's.)"""
    stock = board[0]
    dark = [(x, y) for y in range(105, 127) for x in range(172, 189) if black(rgb(stock, (x, y)))]
    best = (0, 0.0)
    for k in range(400, 800):
        slope = k / 1000
        counts = Counter(round(y + slope * x) for x, y in dark)
        best = max(best, (sum(n * n for n in counts.values()), slope))
    slope = best[1]
    near = [c for c, _ in Counter(round(y + slope * x) for x, y in dark).most_common(2)]
    lines = []
    for c in near:  # each line's own offset: the mean over its pixels, not the rounded bin
        on = [y + slope * x for x, y in dark if abs(y + slope * x - c) <= 1]
        lines.append(sum(on) / len(on))
    assert len(dark) > 20 and len(lines) == 2 and 2 <= abs(lines[0] - lines[1]) <= 4, lines
    return lambda p: p[0] >= 140 and min(abs(p[1] + slope * p[0] - c) for c in lines) <= 1.0


@pytest.mark.parametrize("which", ["rebuilt", "stock"])
def test_each_line_of_the_board_is_its_english_and_nothing_else(board, board_english, trail, which):
    """Each sign's English is painted, whole, once, in its room and in its paint; and no
    group of that paint big enough to be writing is left in any sign's box but English and
    the trail -- which runs through two boxes and is not writing."""
    tim = board[1] if which == "rebuilt" else board[0]
    english, problems = english_on(tim, board_english)
    every = set().union(*english.values())
    for sign in tc.BOARD_SIGNS:
        rest = {p for p in paint.points(sign.box) if PAINT[sign.colour](rgb(tim, p))}
        rest = {p for p in rest if p not in every and not trail(p)}
        left = [g for g in paint.groups(rest) if len(g) >= STROKE]
        if left:
            problems.append(f"{sign.key}: {len(left)} group(s) of writing left, first at "
                            f"{paint.extent(left[0])}")  # fmt: skip
    if which == "stock":
        assert len(english) < len(tc.BOARD_SIGNS) and len(problems) > len(tc.BOARD_SIGNS)
    else:
        assert problems == []


def test_the_board_keeps_its_starburst_trail_and_everything_else(board, board_english, trail):
    """The clean plate changes only the writing's boxes and rooms; the bullet trail's lines
    are the original's, pixel for pixel; and in the starburst, what the red Japanese was
    refilled with is the burst's own colours -- entries its room shows as shipped, none of
    them red -- and every pixel of the red Japanese that the English does not cover is yellow
    again, or board where it ran past the burst's edge (the top of its "!")."""
    stock, rebuilt = board
    before, after = stock.indices(), rebuilt.indices()
    changed = {(i % stock.width, i // stock.width) for i in range(len(before))
               if before[i] != after[i]}  # fmt: skip
    rooms = set().union(*(paint.grown(set(paint.points(s.box)) | set(paint.points(s.room)),
                                      1, 1, 1, 1) for s in tc.BOARD_SIGNS))  # fmt: skip
    assert len(changed) > 2000
    assert sorted(changed - rooms) == []
    lines = {p for p in paint.points((140, 90, 120, 60)) if trail(p) and black(rgb(stock, p))}
    assert len(lines) > 60 and sorted(lines & changed) == []

    english, problems = english_on(rebuilt, board_english)
    assert problems == []
    star = next(s for s in tc.BOARD_SIGNS if s.colour == "red")
    room = set(paint.points(star.room))
    burst = {before[y * stock.width + x] for x, y in room} - {
        e for e in range(256) if red(stock.palette_rgba(0)[e])
    }
    refilled = (set(paint.points(star.box)) & changed) - set().union(*english.values())
    entries = {after[y * stock.width + x] for x, y in refilled}
    assert len(refilled) > 200
    assert sorted(entries - burst) == []
    was_red = {p for p in refilled if red(rgb(stock, p))}
    assert len(was_red) > 150
    back = {p: rgb(rebuilt, p) for p in was_red}
    assert sorted(p for p, c in back.items() if not (yellow(c) or pale(c))) == []
    assert sum(yellow(c) for c in back.values()) > 0.9 * len(back)


def board_entries(**text: str) -> list[tt.Entry]:
    return [tt.Entry(f"tex@M_I23000.{key}", value, f"t:{n}")
            for n, (key, value) in enumerate(text.items())]  # fmt: skip


BOARD_TEXT = {"danger": "DANGER!", "houses": "Homes nearby,", "shoot": "Fire with care!",
              "association": "Prefectural // Hunting Assn."}  # fmt: skip


@pytest.mark.parametrize(
    ("key", "text", "refusal"),
    [("houses", "Houses nearby, beware,", "no place for it clear of the drawing"),
     ("shoot", "Fire // with care!", "shoot line is 1 line"),
     ("association", "Prefectural //  // Hunting Assn.", "is 2 line"),
     ("association", "Prefectural //  ", "has an empty line")],
    ids=["too wide", "two lines where one goes", "three lines", "empty line"],
)  # fmt: skip
def test_a_board_line_that_does_not_fit_is_refused(
    archive, texture_inventory, face, key, text, refusal
):
    with pytest.raises(tt.TextureTextError, match=refusal):
        tc.board(archive, texture_inventory, face, board_entries(**{**BOARD_TEXT, key: text}))


TRAIL_ROOM = (160, 122, 32, 22)
"""A room for the shooting line that the bullet's trail crosses, and nothing else of the drawing
reaches (found by trying rooms along the trail with and without it)."""


@pytest.mark.parametrize("with_trail", [True, False], ids=["the trail", "no trail"])
def test_a_board_line_that_would_cross_the_trail_is_refused(
    archive, texture_inventory, face, monkeypatch, with_trail
):
    """In `TRAIL_ROOM` every place would put the English over the trail, and it is refused;
    with the recipe's trail moved off the board the same line is placed there, so the trail,
    and nothing else in the room, is why."""
    signs = [s if s.key != "shoot" else dataclasses.replace(s, room=TRAIL_ROOM)
             for s in tc.BOARD_SIGNS]  # fmt: skip
    monkeypatch.setattr(tc, "BOARD_SIGNS", tuple(signs))
    if not with_trail:
        monkeypatch.setattr(tc, "BOARD_TRAIL", (*tc.BOARD_TRAIL[:3], 10_000))
    entries = board_entries(**{**BOARD_TEXT, "shoot": "Fire!"})
    if with_trail:
        with pytest.raises(tt.TextureTextError, match=r"shoot space .* no place for it clear"):
            tc.board(archive, texture_inventory, face, entries)
    else:
        assert tc.board(archive, texture_inventory, face, entries)
