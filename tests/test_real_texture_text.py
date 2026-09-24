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
from boku.typeset import FONT_SHEET_ID, GameFace, wrap


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
    """Each line's English, whole at the recipe's scale, is found once in its line -- whose box
    ends at the last column on screen -- and no other pale type is left there."""
    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    english = tt.read_entries()
    after = parse_exact(patched, inv.get(texture_id).occurrences[0].file_offset)
    for n, box in enumerate(tt.BEACH_LINES):
        marks = paint.pale_type(after, tt.BEACH_CLUT, box)
        text = english[f"tex@M_C15.{n}"].text
        ink = paint.normalised(paint.scaled(face.ink(text), tt.BEACH_SCALE))
        spots = placements(ink, marks)
        assert len(spots) == 1, f"line {n}: {text!r} found {len(spots)} times"
        drawn = {(x + spots[0][0], y + spots[0][1]) for x, y in ink}
        assert marks == drawn, f"line {n}: {len(marks ^ drawn)} pixels differ from the English"


@pytest.mark.parametrize("texture_id", tt.BEACH_BACKGROUNDS)
def test_the_beach_notice_on_screen_is_painted_only_in_the_boards_own_colours(
    inv, patched, texture_id
):  # fmt: skip
    """Where a line was painted out, the part on screen takes only entries the stock board
    shows on screen there: the atlas column past the screen's edge is another region's
    (transparent through the board's CLUT: on Beetle what is behind shows, red, and the Beetle
    comparison skips it), and a refill that reached it would paint it in."""
    texture = inv.get(texture_id)
    stock = texture.tim
    after = parse_exact(patched, texture.occurrences[0].file_offset)
    for n, (x0, y0, _, h) in enumerate(tt.BEACH_LINES):
        seen = set(paint.points((x0, y0, tt.BEACH_VISIBLE - x0, h)))
        before = {stock.indices()[y * stock.width + x] for x, y in seen}
        new = {after.indices()[y * after.width + x] for x, y in seen} - before
        assert new == set(), f"line {n}: entries {sorted(new)} are not the board's on screen"


# --- the picture diary (GFX-04) -------------------------------------------------------------------


def diary_entries():
    return {k: e for k, e in tt.read_entries().items() if k.startswith("nikki@")}


@pytest.mark.parametrize("key", sorted(diary_entries()))
def test_each_diary_page_carries_its_entry_and_no_japanese(inv, patched, key):
    """Every line the entry wraps to (in the page's width, the game's glyphs) is found once
    on the rebuilt panel, and the panel's dark type is exactly those lines."""
    from boku import diary

    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    entry = diary_entries()[key]
    texture = diary.diary_pages(inv)[key.removeprefix("nikki@NIKKI_")]
    after = parse_exact(patched, texture.occurrences[0].file_offset)
    panel = diary.PANEL
    box = (panel.left, panel.repaint_top, panel.width, panel.bottom - panel.repaint_top + 1)
    marks = paint.dark_type(after, 0, box, spread=40)
    covered: set = set()
    for line in wrap(entry.text, face, panel.text_width):
        ink = face.ink(line)
        spots = placements(ink, marks)
        assert len(spots) == 1, f"{key}: {line!r} found {len(spots)} times"
        covered |= {(x + spots[0][0], y + spots[0][1]) for x, y in paint.normalised(ink)}
    assert marks == covered, f"{key}: {len(marks - covered)} dark pixels are not the English"


def diary_check(archive, inv, tmp_path, rows: str):
    (tmp_path / "diary.txt").write_text(rows, encoding="utf-8")
    return tt.build_edits(archive, tmp_path, inv=inv)


def test_the_dummy_page_and_an_unknown_page_are_refused_together(archive, inv, tmp_path):
    with pytest.raises(tt.TextureTextError) as raised:
        diary_check(
            archive, inv, tmp_path,
            "nikki@NIKKI_000\tHello.\nnikki@NIKKI_999\tHello.\nnikki@NIKKI_001\tHello.\n",
        )  # fmt: skip
    message = str(raised.value)
    assert message.startswith("2 diary page(s) refused")
    assert "NIKKI_000 is the unused dummy page" in message
    assert "there is no diary page NIKKI_999" in message


def test_an_entry_one_line_too_long_is_refused_with_its_numbers(archive, inv, tmp_path):
    """Built from the page's own capacity: five lines fit, six are refused."""
    from boku import diary

    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    width = diary.PANEL.text_width
    lines = len(diary.line_tops())
    word = "abcde"
    text = word
    while len(wrap(text + " " + word, face, width)) <= lines:
        text += " " + word
    diary_check(archive, inv, tmp_path, f"nikki@NIKKI_001\t{text}\n")
    with pytest.raises(
        tt.TextureTextError, match=rf"wraps to {lines + 1} lines and the page holds {lines}"
    ):
        diary_check(archive, inv, tmp_path, f"nikki@NIKKI_001\t{text} {word}\n")


def test_a_double_quote_in_an_entry_is_refused(archive, inv, tmp_path):
    with pytest.raises(tt.TextureTextError, match="no drawing for '\"'"):
        diary_check(archive, inv, tmp_path, 'nikki@NIKKI_001\tA "bug".\n')


def test_the_hyphen_is_drawn_as_the_crossbar_of_the_sheets_e(archive, inv, tmp_path):
    """The sheet has no hyphen (its only dash is the full-width minus); the face draws a fixed
    4 px one, narrower than `e`, on the row of `e`'s crossbar, so "Moe-neechan" sets as the
    day files write it. The crossbar is found here as the one full-width row strictly between
    `e`'s top and bottom ink, not as the face finds it."""
    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    e = face.glyph("e")
    inked = [r for r, xs in enumerate(e.rows) if xs]
    interior = range(inked[0] + 1, inked[-1])
    full = [r for r in interior if len(e.rows[r]) == e.width]
    assert len(full) == 1, full
    crossbar = full[0]
    hyphen = face.glyph("-")
    assert hyphen is not None
    assert [r for r, xs in enumerate(hyphen.rows) if xs] == [crossbar]
    assert hyphen.width < e.width
    diary_check(archive, inv, tmp_path, "nikki@NIKKI_001\tMoe-neechan read a well-known book.\n")


def test_a_word_wider_than_a_line_is_refused_not_clipped(archive, inv, tmp_path):
    with pytest.raises(tt.TextureTextError, match="wider than a line of the page"):
        diary_check(archive, inv, tmp_path, "nikki@NIKKI_001\t" + "WOW" * 20 + "!\n")


def test_a_line_break_in_a_diary_entry_is_refused(archive, inv, tmp_path):
    with pytest.raises(tt.TextureTextError, match="one paragraph"):
        diary_check(archive, inv, tmp_path, "nikki@NIKKI_001\tThe bugs are fast. // I lost.\n")


def test_the_shaded_page_047_is_measured_and_accepted(archive, inv, tmp_path):
    result = diary_check(archive, inv, tmp_path, "nikki@NIKKI_047\tA quiet day.\n")
    assert result.families == ("nikki@",) and result.edits


def test_a_page_whose_panel_measures_differently_is_refused(archive, inv, tmp_path, monkeypatch):
    """The recipe re-measures every page it draws on; a disagreement (as a contributor's
    different dump would give) stops it before English lands on a drawing. Only NIKKI_047's
    known shading is let through, and only on NIKKI_047."""
    from boku import diary

    known = diary.SHADED_PAGES["047"]
    monkeypatch.setattr(diary, "SHADED_PAGES", {"047": known[:-1]})  # one column fewer
    with pytest.raises(tt.TextureTextError, match="NIKKI_047's panel is not the one"):
        diary_check(archive, inv, tmp_path, "nikki@NIKKI_047\tHello.\n")
    monkeypatch.setattr(diary, "SHADED_PAGES", {"001": known})  # the wrong page
    with pytest.raises(tt.TextureTextError, match="NIKKI_047's panel is not the one"):
        diary_check(archive, inv, tmp_path, "nikki@NIKKI_047\tHello.\n")


def test_textures_check_reports_writes_the_images_and_fails_on_a_refusal(
    disc_dir, tmp_path, capsys
):
    out = tmp_path / "look"
    assert tt.main_check(disc_dir, tt.TEXTURE_TEXT_DIR, out) == 0
    assert (out / "_DATA_NIKKI.BIN_NIKKI_072__000000.png").is_file()
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "diary.txt").write_text("nikki@NIKKI_000\tHello.\n", encoding="utf-8")
    assert tt.main_check(disc_dir, bad, None) == 1
    assert "NIKKI_000 is the unused dummy page" in capsys.readouterr().out
