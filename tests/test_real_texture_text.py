"""The tracked texture English against the contributor's own import (PLAN `GFX-07`).

What the synthetic tests cannot show: that the recipe's addresses are the title menu's on
the real `TITLE.OVL`, that every edit's `old` bytes are the import's (so the image build
accepts them), and that the rebuilt atlas carries exactly the English in
`translation/textures/` set in the game's own glyphs and nothing of the Japanese. The
expected pixels are derived from the translation file and the disc's glyph sheet; the only
number typed here is the screen geometry `research/texture-recipes.md` § "`T_TITLE`" measured.

Skips without the import. Nothing read here is written anywhere.
"""

from __future__ import annotations

import struct
from collections import Counter

import pytest

from boku import texture_paint as paint
from boku import texture_text as tt
from boku.textures import Inventory
from boku.tim import parse_exact
from boku.typeset import FONT_SHEET_ID, GameFace


@pytest.fixture(scope="module")
def inv(texture_inventory: Inventory) -> Inventory:
    return texture_inventory


@pytest.fixture(scope="module")
def built(texture_edits) -> tt.TextureEdits:
    return texture_edits


@pytest.fixture(scope="module")
def patched(texture_patched) -> bytes:
    return texture_patched


def test_every_edit_replaces_exactly_the_bytes_the_import_holds(archive, built):
    assert "tex@T_TITLE" in built.families
    for edit in built.edits:
        assert edit.file == "BOKU.BIN"
        assert archive.boku[edit.offset : edit.offset + len(edit.old)] == edit.old, edit.reason


def test_the_widened_records_are_the_four_menu_lines_in_order(archive, patched):
    """Each record's v is its band and its h the band's height -- which is what ties
    `TITLE_MENU_RECORDS` to lines 0-3 -- and each is 128 wide after the build."""
    for line, record in enumerate(tt.TITLE_MENU_RECORDS):
        at = archive.overlay_offset(tt.TITLE_OVERLAY, record)
        _, x, _, u, v, w, h = struct.unpack_from("<HHHBBHH", archive.boku, at)
        assert (x, u, v, w, h) == (0x77, 0, tt.MENU_BAND * line, tt.RETAIL_MENU_WIDTH, 16)
        assert struct.unpack_from("<H", patched, at + tt.TITLE_RECORD_WIDTH)[0] == tt.MENU_WIDTH


def test_the_title_atlas_holds_the_tracked_english_and_none_of_the_japanese(inv, patched):
    texture = inv.get(tt.TITLE_ATLAS)
    before = texture.tim.indices()
    after = parse_exact(patched, texture.occurrences[0].file_offset).indices()
    width = texture.tim.width
    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    english = tt.read_entries()
    menu_rows = tt.MENU_BAND * tt.MENU_LINES

    # The atlas's own outline and fill: the two entries the Japanese menu is drawn in most.
    transparent = before[0]
    counts = Counter(
        before[y * width + x] for y in range(menu_rows) for x in range(tt.RETAIL_MENU_WIDTH)
    )
    outline, fill = [i for i, _ in counts.most_common() if i != transparent][:2]
    palette = texture.tim.palette_rgba(0)
    assert tt.luminance(palette[outline]) > 200 and tt.luminance(palette[fill]) < 100, (
        "the Japanese menu is pale-outlined dark type; the roles read from counts must agree"
    )

    for line in range(tt.MENU_LINES):
        text = english[f"tex@T_TITLE.{line}"].text
        ink = {(x + 1, y + tt.MENU_INK_TOP) for x, y in face.ink(text)}
        ring = {(x + a, y + b) for x, y in ink for a in (-1, 0, 1) for b in (-1, 0, 1)} - ink
        want = {**dict.fromkeys(ring, outline), **dict.fromkeys(ink, fill)}
        got = {
            (x, y): after[(tt.MENU_BAND * line + y) * width + x]
            for y in range(tt.MENU_BAND)
            for x in range(tt.MENU_WIDTH)
            if after[(tt.MENU_BAND * line + y) * width + x] != transparent
        }
        assert got == want, f"line {line}: {text!r}"

    outside = [
        i
        for i in range(len(before))
        if not (i // width < menu_rows and i % width < tt.MENU_WIDTH) and before[i] != after[i]
    ]
    assert outside == [], "the logo, PRESS START, the copyright line and the (TM) are untouched"


# --- T_CONFIG ---------------------------------------------------------------------------------


def placements(ink: set, marks: set) -> list[tuple[int, int]]:
    """Every offset at which all of `ink` (normalised) lands on `marks`."""
    ink = paint.normalised(ink)
    first = min(ink)
    return [
        (mx - first[0], my - first[1])
        for mx, my in marks
        if all((x + mx - first[0], y + my - first[1]) in marks for x, y in ink)
    ]


def config_slots(english):
    """(texture, CLUT, box, which marks, expected strings and how each may be drawn). The
    strings come from the tracked file and the boxes from the recipe's measured geometry
    (`research/texture-recipes.md` § "`T_CONFIG`"); the drawing variants are the only thing
    a slot says about style."""
    t = {k: english[f"tex@T_CONFIG.{k}"].text for k in tt.CONFIG_KEYS}
    plain = [lambda i: i]
    large = [lambda i: paint.scaled(i, 2), paint.bold]
    return [
        (tt.CONFIG_FRAME, tt.HEADING_CLUT, tt.CONFIG_HEADING, "dark", [(t["heading"], plain)]),
        (tt.CONFIG_PLATES, tt.MESSAGE_CLUT, tt.MESSAGE_PLATE, "pale", [
            (t["voice_text"], plain), (t["voice_text_note"], plain),
            (t["voice_only"], plain), (t["voice_only_note"], plain)]),
        (tt.CONFIG_FRAME, tt.SOUND_CLUT, tt.SOUND_PLATE, "pale",
         [(t["stereo"], plain), (t["mono"], plain)]),
        *[
            (tt.CONFIG_PLATES, tt.VALUE_CLUT, tt.VALUE_LABELS[k], "pale",
             [(t[k], large)] + ([(t[f"{k}_note"], plain)] if f"{k}_note" in t else []))
            for k in tt.VALUE_LABELS
        ],
    ]  # fmt: skip


def test_the_settings_screen_carries_exactly_the_tracked_english(inv, patched):
    """In every slot the type-coloured pixels after the build are the English strings, each
    found exactly once as the game's glyphs, and nothing else: no Japanese is left."""
    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    english = tt.read_entries()
    for texture_id, clut, box, kind, expected in config_slots(english):
        texture = inv.get(texture_id)
        after = parse_exact(patched, texture.occurrences[0].file_offset)
        marks = (paint.pale_type if kind == "pale" else paint.dark_type)(after, clut, box)
        covered: set = set()
        for text, variants in expected:
            found = [
                (variant, spot)
                for variant in variants
                for spot in placements(variant(face.ink(text)), marks)
            ]
            assert len(found) == 1, f"{texture_id} {box}: {text!r} found {len(found)} times"
            variant, (dx, dy) = found[0]
            covered |= {(x + dx, y + dy) for x, y in paint.normalised(variant(face.ink(text)))}
        assert marks == covered, f"{texture_id} {box}: {len(marks - covered)} stray type pixels"


def test_the_controller_chart_headings_are_the_tracked_english_turned(inv, patched):
    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    english = tt.read_entries()
    texture = inv.get(tt.CONFIG_PLATES)
    after = parse_exact(patched, texture.occurrences[0].file_offset)
    marks = paint.pale_type(after, tt.CHART_CLUT, tt.CHART_HEAD)
    rules = tt.chart_rules(marks)
    covered: set = set()
    for key in tt.CHART_KEYS:
        for n, line in enumerate(tt.lines_of(english[f"tex@T_CONFIG.{key}"])):
            ink = paint.rotated_cw(face.ink(line))
            spots = placements(ink, marks - rules)
            assert len(spots) == 1, f"{key} line {n}: {line!r} found {len(spots)} times"
            dx, dy = spots[0]
            covered |= {(x + dx, y + dy) for x, y in paint.normalised(ink)}
    assert marks - rules == covered


def test_the_album_heading_is_the_tracked_english_on_its_lines(inv, patched):
    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    entry = tt.read_entries()["tex@T_MEMORY.heading"]
    after = parse_exact(patched, inv.get(tt.MEMORY_ALBUM).occurrences[0].file_offset)
    marks = paint.dark_type(after, tt.MEMORY_CLUT, tt.MEMORY_HEADING)
    covered: set = set()
    tops = []
    for line in tt.lines_of(entry):
        spots = placements(face.ink(line), marks)
        assert len(spots) == 1, f"{line!r} found {len(spots)} times"
        tops.append(spots[0][1])
        covered |= {(x + spots[0][0], y + spots[0][1]) for x, y in paint.normalised(face.ink(line))}
    assert marks == covered, "type on the plaque other than the heading"
    assert tops == sorted(tops) and len(set(tops)) == len(tops), "the lines are not in order"


@pytest.mark.parametrize(
    ("texture_id", "clut", "box"),
    [
        (tt.MEMORY_ALBUM, tt.MEMORY_CLUT, tt.MEMORY_HEADING),
        (tt.CONFIG_FRAME, tt.HEADING_CLUT, tt.CONFIG_HEADING),
    ],
    ids=["album", "settings"],
)
def test_no_antialiasing_of_the_japanese_is_left_on_a_plaque(inv, patched, texture_id, clut, box):
    """The dark mask cannot see the Japanese's grey antialiasing; this can. Where the Japanese
    was (its extent, grown by the width of its fringe), every pixel after the build is either
    the plaque's ground or the English's ink -- both entries read from the stock image."""
    stock = inv.get(texture_id)
    before = stock.tim.indices()
    after = parse_exact(patched, stock.occurrences[0].file_offset).indices()
    width = stock.tim.width
    japanese = paint.dark_type(stock.tim, clut, box)
    ground = Counter(before[y * width + x] for x, y in paint.points(box)).most_common(1)[0][0]
    ink = Counter(before[y * width + x] for x, y in japanese).most_common(1)[0][0]
    jx, jy, jw, jh = paint.extent(japanese)
    fringe = paint.points((jx - 1, jy - 1, jw + 2, jh + 2))
    left = {(x, y): after[y * width + x] for x, y in fringe}
    stray = {p: i for p, i in left.items() if i not in (ground, ink)}
    assert stray == {}, f"{len(stray)} pixels of neither ground nor ink, e.g. {list(stray)[:3]}"


@pytest.mark.parametrize("texture_id", tt.BEACH_BACKGROUNDS)
def test_the_beach_notice_is_the_tracked_english_painted_on_both_variants(inv, patched, texture_id):
    """Each line's English, at the recipe's scale and cut at the atlas's edge as the board is
    cut by the screen's, is found once in its line, and no other pale type is left there."""
    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    english = tt.read_entries()
    after = parse_exact(patched, inv.get(texture_id).occurrences[0].file_offset)
    for n, box in enumerate(tt.BEACH_LINES):
        marks = paint.pale_type(after, tt.BEACH_CLUT, box)
        text = english[f"tex@M_C15.{n}"].text
        ink = paint.normalised(paint.scaled(face.ink(text), tt.BEACH_SCALE))
        right = box[0] + box[2]
        # The line runs off the board, so it is located by its first letters, which are on it.
        head = {p for p in ink if p[0] < box[2] // 2}
        hx, hy, _, _ = paint.extent(head)
        spots = placements(head, marks)
        assert len(spots) == 1, f"line {n}: {text!r} found {len(spots)} times"
        dx, dy = spots[0][0] - hx, spots[0][1] - hy
        drawn = {(x + dx, y + dy) for x, y in ink if x + dx < right}
        assert marks == drawn, f"line {n}: {len(marks ^ drawn)} pixels differ from the English"
