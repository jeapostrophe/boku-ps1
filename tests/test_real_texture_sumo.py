"""Bug sumo's bout (`boku.texture_sumo`) against the contributor's import, and on Beetle PSX.

Texture level: the banner's page holds each move's English -- a technique's name over its
gloss -- in the strip the game's own table names for it and nothing else, and the heading is
in the third page's free corner; the two routines that place them, run on the built overlay,
give every way of ending its strip; the stamina plate is set down widened with its word
embossed and its old place is blank; inside each rank mark's ring the only chalk is the rank.

On Beetle (`BOKU_EMU_TESTS=1`, `./make.sh saves` for the base): the card with the mantis
beaten takes a bug to the ring against the King, rings the gong and lets the bout end. The
mark, the plate, the heading and the move's name and gloss show every texel as rebuilt, the
plate opens to its new width, and the two records the banner is drawn from hold the new
places. The stock image fails each: it shows the Japanese there.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from boku import REPO_ROOT
from boku import texture_paint as paint
from boku import texture_sumo as ts
from boku.archive import OVERLAY_LOAD_ADDRESS
from boku.png import read as read_png
from boku.texture_closeups import emboldened
from boku.texture_text import Entry, TextureTextError, family_entries, ink_of
from boku.tim import luminance
from tests.mips import Machine
from tests.test_real_sumo_bout import _card
from tests.test_real_texture_buttons import DARK, WHITE, check_texels, rebuilt

ENTRIES = family_entries(ts.FAMILY)
BANNER, HEADING = ts.VIEWS[f"{ts.FAMILY}move"]
PLATE = ts.VIEWS[f"{ts.FAMILY}plate"][0]
MARKS = dict(zip(ts.RANK_MARKS, ts.VIEWS[f"{ts.FAMILY}rank"], strict=True))
"""Each part's texture as the game draws it: what `rebuilt` opens and `check_texels` reads."""


def bold(game, key: str) -> paint.Ink:
    entry = ENTRIES[key]
    return paint.normalised(emboldened(game, entry, entry.text, False))


def glyph_row(game, key: str) -> int:
    """How far below its glyph cell's top a line's bold ink starts."""
    entry = ENTRIES[key]
    return paint.extent(emboldened(game, entry, entry.text, False))[1]


def lines_of(key: str) -> list[tuple[str, int]]:
    """What the tracked English says a strip holds: `(key, the row its glyph cell starts on)`
    for the name, and the gloss under it when `sumo.txt` gives one."""
    gloss = f"move.gloss-{key}"
    if gloss in ENTRIES:
        return [(f"move.{key}", ts.NAME_TOP), (gloss, ts.GLOSS_TOP)]
    return [(f"move.{key}", ts.ALONE_TOP)]


def assert_lines(canvas, palette, box: paint.Box, lines, game, what: str) -> paint.Ink:
    """`box`'s lettered texels are `lines`, each its English in white, centred across the box
    with its glyph cell's top on its row, the whole ringed in a dark edge; returns them."""
    x0, y0, w, _ = box
    drawn = {p for p in paint.points(box) if canvas.at(p)}
    white = {p for p in drawn if luminance(palette[canvas.at(p)]) > WHITE}
    tops = [top for _, top in lines] + [box[3]]
    for (key, top), below in zip(lines, tops[1:], strict=True):
        line = {(x, y) for x, y in white if top <= y - y0 < below}
        assert paint.normalised(line) == bold(game, key), f"{what}: {key} is not its English"
        left, first, width, _ = paint.extent(line)
        assert first - y0 == top + glyph_row(game, key), f"{what}: {key} not on its line"
        assert abs((left - x0) - (x0 + w - left - width)) <= 1, f"{what}: {key} not centred"
    edge = drawn - white
    assert edge == paint.grown(white, 1, 1, 1, 1) - white, f"{what}: its edge"
    assert all(luminance(palette[canvas.at(p)]) < DARK for p in edge), f"{what}: a pale edge"
    return drawn


def test_each_strip_is_its_moves_english_and_the_page_holds_nothing_else(
    archive, texture_inventory, texture_patched, game
):  # fmt: skip
    """The strip is looked up as the game does: the move's byte of `CELL_TABLE`, read here
    from the import; a real technique's strip is its name over the gloss `sumo.txt` gives."""
    canvas = rebuilt(texture_inventory, texture_patched, BANNER)
    palette = canvas.palette(BANNER.clut, BANNER.chunk)
    expected: paint.Ink = set()
    for key, cell in ts.cells(archive).items():
        box = ts.cell_box(cell)
        expected |= assert_lines(canvas, palette, box, lines_of(key), game, f"strip {cell}")
    page = paint.points((0, 0, ts.PAGE, ts.PAGE))
    assert {p for p in page if canvas.at(p)} == expected, "lettering outside the strips"


def test_the_heading_is_set_in_a_corner_that_was_free(texture_inventory, texture_patched, game):
    """(The atlas's other pages carry other families' English, so only the box is checked.)"""
    canvas = rebuilt(texture_inventory, texture_patched, HEADING)
    stock = paint.Canvas(texture_inventory.get(HEADING.texture), drawn_4bpp=True)
    palette = canvas.palette(HEADING.clut, HEADING.chunk)
    box = ts.HEADING_BOX
    assert not any(stock.at(p) for p in paint.points(box)), "the corner was not free"
    assert_lines(canvas, palette, box, [("move.heading", ts.NAME_TOP)], game, "the heading")


def _records(overlay: bytes) -> tuple[tuple[int, ...], dict[int, tuple[int, ...]]]:
    """The heading's record, and each way of ending's move record, as the routines that fill
    them (`0x8008659C`, `0x800865F8`) leave them in `overlay`: each the 12 halfwords to
    +0x18."""
    machine = Machine()
    machine.load(OVERLAY_LOAD_ADDRESS, overlay)

    def record(at: int) -> tuple[int, ...]:
        return tuple(machine.read(at + 2 * i, 2) for i in range(12))

    machine.call(HEADING_ROUTINE)
    heading = record(ts.HEADING_RECORD)
    moves = {}
    for move in range(ts.MOVES):
        machine.call(MOVE_ROUTINE, move)
        moves[move] = record(ts.MOVE_RECORD)
    return heading, moves


HEADING_ROUTINE, MOVE_ROUTINE = 0x8008659C, 0x800865F8
PAGES = (ts.HEADING_PAGE_X, 0, 288, 247), (ts.PAGE_X, 0, 288, 247)
"""The texture page and CLUT the heading and the move are drawn through (VRAM x, y)."""


def test_the_patched_routines_place_the_heading_and_every_moves_strip(archive, texture_patched):
    """The two routines, run as the game runs them on the built `MUSI.OVL`: the heading's
    record is `HEADING_BOX` (its `v` the page's x, whose low byte the GPU takes), and each way
    a bout ends names its strip's box by the table, drawn at the strip's place."""
    member = archive.member(ts.OVERLAY)
    heading, moves = _records(texture_patched[member.offset : member.offset + member.size])
    x, _, w, h = ts.HEADING_BOX
    u = x - (ts.HEADING_PAGE_X - ts.PAGE_X) * 4
    assert heading[:2] == (u, ts.HEADING_PAGE_X)
    assert heading[2:] == (w, h, ts.HEADING_X, ts.HEADING_Y, w, h, *PAGES[0]), heading
    cells = ts.cells(archive)
    for move, record in moves.items():
        box = ts.cell_box(cells[str(move)])
        at = (ts.STRIP_X, ts.ALONE_Y if move == ts.ALONE else ts.MOVE_Y)
        assert record == (*box, *at, *box[2:], *PAGES[1]), f"move {move}: {record}"


def test_the_plate_is_widened_embossed_with_its_word_and_gone_from_its_old_place(
    texture_inventory, texture_patched, game
):  # fmt: skip
    canvas = rebuilt(texture_inventory, texture_patched, PLATE)
    stock = paint.Canvas(texture_inventory.get(PLATE.texture), drawn_4bpp=True)
    palette = canvas.palette(PLATE.clut, PLATE.chunk)
    assert {stock.at(p) for p in paint.points(PLATE.original)} != {0}
    assert {canvas.at(p) for p in paint.points(PLATE.original)} == {0}, "the Japanese plate is left"
    x0, y0, w, h = PLATE.english
    fx, fy, fw, fh = ts.PLATE_FACE
    right = ts.PLATE[2] - fx - fw
    for dy in range(h):  # the frame is the stock plate's, at both ends
        was = [stock.at((ts.PLATE[0] + dx, ts.PLATE[1] + dy)) for dx in range(ts.PLATE[2])]
        now = [canvas.at((x0 + dx, y0 + dy)) for dx in range(w)]
        assert now[:fx] == was[:fx] and now[-right:] == was[-right:], f"the frame, row {dy}"
    face = paint.points((x0 + fx, y0 + fy, w - fx - right, fh))
    ground = canvas.most_used(face)
    level = luminance(palette[ground])
    light = {p for p in face if luminance(palette[canvas.at(p)]) > level}
    dark = {p for p in face if luminance(palette[canvas.at(p)]) < level}
    word = paint.normalised(ink_of(game, ENTRIES["plate.stamina"]))
    assert paint.normalised(light) == word, "the plate's raised type is not the English"
    assert dark == {(x + 1, y + 1) for x, y in light} - light, "its shadow"
    left, _, width, _ = paint.extent(light | dark)
    assert abs((left - x0 - fx) - (x0 + w - right - left - width)) <= 1, "not centred"


@pytest.mark.parametrize("name", sorted(ts.RANK_MARKS))
def test_the_only_chalk_inside_a_rank_marks_ring_is_the_rank(
    name, texture_inventory, texture_patched, game
):  # fmt: skip
    mark, view = ts.RANK_MARKS[name], MARKS[name]
    canvas = rebuilt(texture_inventory, texture_patched, view)
    stock = paint.Canvas(texture_inventory.get(mark.texture))
    palette = canvas.palette(mark.clut)
    area = ts.inside(mark)

    def chalk(c: paint.Canvas) -> paint.Ink:
        return {p for p in area if luminance(palette[c.at(p)]) > ts.CHALK}

    word = bold(game, f"rank.{name}")
    assert len(chalk(stock)) > 2 * len(word), "the stock mark's writing is not where measured"
    assert paint.normalised(chalk(canvas)) == word, f"{name}: chalk besides the English"
    dust = {p for p in area - chalk(canvas) if luminance(palette[canvas.at(p)]) > ts.WOOD}
    assert dust == set(), f"{name}: chalk dust left inside the ring"
    outside = set(paint.points(view.original)) - area
    assert all(canvas.at(p) == stock.at(p) for p in outside), f"{name}: the ring or desk changed"


def test_a_rank_too_wide_for_its_ring_is_refused_not_cut(texture_inventory, game):
    mark = ts.RANK_MARKS["king"]
    canvas = paint.Canvas(texture_inventory.get(mark.texture))
    with pytest.raises(TextureTextError, match="does not fit inside"):
        ts.rank_mark(canvas, mark, Entry("sumo@rank.king", "Champion", "t:1"), game, "the mark")


def test_a_gloss_too_wide_for_its_line_is_refused_not_cut(game):
    """utchari's gloss as first worded, 139 px in the game's glyphs made bold, against a line's
    122: it is refused, and Jay's shorter wording is what `sumo.txt` gives."""
    name = ENTRIES["move.3"]
    with pytest.raises(TextureTextError, match="nothing is cut to fit"):
        ts.strip(game, name, Entry("sumo@move.gloss-3", "backward pivot throw", "t:1"))
    ts.strip(game, name, ENTRIES["move.gloss-3"])


def test_a_word_too_wide_for_the_plate_is_refused_not_cut(archive, texture_inventory, game):
    with pytest.raises(TextureTextError, match="nothing is cut to fit"):
        entry = Entry("sumo@plate.stamina", "Stamina left", "t:1")
        ts.plate(archive, texture_inventory, game, {"plate.stamina": entry})


# --- on Beetle -----------------------------------------------------------------------------

MARK_AT, PLATE_Y = (10, 27), 130
"""Where the rank mark and the plate's top are on screen with the desk scrolled to the ring."""

ADDRESSES = (ts.HEADING_RECORD, ts.MOVE_RECORD, ts.HOW_IT_ENDED, ts.PLATE_WIDTH)
DRIVE = """
import json, struct, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import sumo_bout as sb
from field import Game, land_in
g = Game(Path(sys.argv[2]), Path(sys.argv[3]).read_bytes(), Path(sys.argv[4]))
work = Path(sys.argv[4])
heading, move, how, width = (int(a, 0) for a in sys.argv[5:9])
land_in(g, "A18")
sb.enter_desk(g)
g.run(1100)
for button, then in (("CIRCLE", 900), ("CIRCLE", 50), ("LEFT", 40)):
    g.press(button, then)
g.press("CIRCLE", 0)
g.until("the bug in hand", lambda: g.read(sb.HELD, 1)[0] != sb.EMPTY, 300)
g.run(400)
for button, then in (("DOWN", 40), ("RIGHT", 90), ("RIGHT", 50), ("UP", 55),  # to the ring
                     ("LEFT", 60), ("CIRCLE", 60), ("DOWN", 60), ("DOWN", 60)):  # the board
    g.press(button, then)
if g.read(sb.RANK_CHOICE, 1)[0] != sb.KING:
    raise SystemExit("the rank board is not on King")
g.press("CIRCLE", 1300)
g.press("RIGHT", 60)
g.fe.screenshot(work / "mark.png")
g.press("CIRCLE", 0)
g.until("the bout", lambda: g.read(sb.BOUT, 1)[0] == 1, 900)
g.run(420)
g.press("RIGHT", 60)
g.press("CIRCLE", 60)
g.run(40)
g.fe.screenshot(work / "fight.png")
out = {"plate": struct.unpack("<H", g.read(width, 2))[0]}
for _ in range(600):
    if g.read(sb.RESULT, 1)[0]:
        break
    g.press("TRIANGLE", 6)
faded = lambda: min(g.read(heading + 0x18, 1)[0], g.read(move + 0x18, 1)[0]) >= 0x80
g.until("the banner", faded, 600)
g.run(2)
g.fe.screenshot(work / "banner.png")
out["result"] = g.read(sb.RESULT, 1)[0]
out["move"] = struct.unpack("<h", g.read(how, 2))[0]
out["heading"] = struct.unpack("<8h", g.read(heading, 16))
out["strip"] = struct.unpack("<8h", g.read(move, 16))
(work / "bout.json").write_text(json.dumps(out))
"""
"""The mantis card's route to a King bout (`tools/libretro/sumo_bout.py`'s, by way of the rank
board, which a card with the mantis beaten has to open itself), the gong, △ until the bout
ends, and the banner once both its lines have faded in."""


@pytest.mark.skipif(os.environ.get("BOKU_EMU_TESTS") != "1", reason="set BOKU_EMU_TESTS=1")
def test_a_bout_on_beetle_shows_the_mark_the_plate_and_the_banner_in_english(
    texture_image, archive, disc_dir, texture_inventory, texture_patched, tmp_path
):  # fmt: skip
    card = _card(disc_dir, tmp_path, "shortcut-open", ["--corpus"])
    work = tmp_path / "bout"
    work.mkdir()
    ran = subprocess.run(
        [sys.executable, "-c", DRIVE, str(REPO_ROOT / "tools/libretro"), str(texture_image),
         str(card), str(work), *(hex(a) for a in ADDRESSES)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    assert ran.returncode == 0, ran.stdout + ran.stderr
    bout = json.loads((work / "bout.json").read_text())
    shots = {name: read_png((work / f"{name}.png").read_bytes())
             for name in ("mark", "fight", "banner")}  # fmt: skip

    def on_screen(shot, view, box, at, what):
        origin = (at[0] - box[0], at[1] - box[1])
        check_texels(shots[shot], texture_inventory, texture_patched, view, view.clut, view.chunk,
                     paint.points(box), origin, what)  # fmt: skip

    on_screen("mark", MARKS["king"], MARKS["king"].english, MARK_AT, "the King mark")

    wide = PLATE.english
    assert bout["plate"] == wide[2], "the plate did not open to its new width"
    on_screen("fight", PLATE, wide, (0x88 - ts.HALF, PLATE_Y), "the stamina plate")

    assert bout["move"] != ts.ALONE and bout["result"], bout
    assert f"move.gloss-{bout['move']}" in ENTRIES, f"move {bout['move']} has no gloss to check"
    _, _, w, h = ts.HEADING_BOX
    heading = (w, ts.HEADING_PAGE_X, w, h, ts.HEADING_X, ts.HEADING_Y, w, h)
    strip = ts.cell_box(ts.cells(archive)[str(bout["move"])])
    assert tuple(bout["heading"]) == heading, "the heading's record"
    assert tuple(bout["strip"]) == (*strip, ts.STRIP_X, ts.MOVE_Y, *strip[2:]), "the move's"
    on_screen("banner", HEADING, ts.HEADING_BOX, (ts.HEADING_X, ts.HEADING_Y), "the heading")
    on_screen("banner", BANNER, strip, (ts.STRIP_X, ts.MOVE_Y),
              f"the banner's move {bout['move']}, its name and gloss")  # fmt: skip
