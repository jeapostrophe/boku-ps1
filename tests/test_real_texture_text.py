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

from boku import texture_text as tt
from boku.archive import Archive
from boku.textures import Inventory
from boku.tim import parse_exact
from boku.typeset import FONT_SHEET_ID, GameFace


@pytest.fixture(scope="module")
def inv(texture_inventory: Inventory) -> Inventory:
    return texture_inventory


@pytest.fixture(scope="module")
def built(archive: Archive, inv: Inventory) -> tt.TextureEdits:
    return tt.build_edits(archive, inv=inv)


@pytest.fixture(scope="module")
def patched(archive: Archive, built: tt.TextureEdits) -> bytes:
    blob = bytearray(archive.boku)
    for edit in built.edits:
        blob[edit.offset : edit.offset + len(edit.new)] = edit.new
    return bytes(blob)


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
