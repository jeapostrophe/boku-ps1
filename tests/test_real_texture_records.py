"""The labels beside run-time numbers (`boku.texture_records`) against the contributor's import,
and on Beetle PSX.

Texture level: at every place a record is drawn, each label's box holds exactly its English
(in its face, once; a shadowed record's shadow one pixel down and right) and nothing of the
Japanese; a mark the English has no word for (the 日 after the day) is cleared.

On Beetle (`BOKU_EMU_TESTS=1`, `./make.sh saves` for the base): a card that owns the rod and has
caught fish opens the desk's fishing record; a card with an offer in the bug-trading notebook
opens it at the bug-sumo desk, as a single card and as the offered and held pair. Every texel
of every label shows its rebuilt colour exactly (the stock image fails). Routes and where each
sprite lands were measured (`research/texture-recipes.md` § "Records").
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku import texture_paint as paint
from boku import texture_records as tr
from boku import texture_text as tt
from boku.png import read as read_png
from boku.texture_text import family_entries, ink_of
from boku.tim import luminance
from boku.typeset import face_named
from tests.test_real_texture_buttons import check_on_screen, check_texels, rebuilt

ENTRIES = family_entries(tr.FAMILY)


CASES = [(m, c) for m, r in tr.RECORDS.items() for c in r.copies]


@pytest.mark.parametrize(("member", "copy"), CASES, ids=[f"{m}-{c}" for m, c in CASES])
def test_each_label_holds_its_english_and_no_japanese(
    member, copy, texture_inventory, texture_patched, game
):  # fmt: skip
    record = tr.RECORDS[member]
    dx, dy, chunk = copy
    canvas = rebuilt(texture_inventory, texture_patched, record)
    palette = canvas.palette(record.clut, chunk)
    for label in record.labels:
        box, room = label.clear_at(dx, dy), label.room_at(dx, dy)
        area = set(paint.points(box)) | set(paint.points(room))
        dark = {p for p in area if luminance(palette[canvas.at(p)]) < tr.INK}
        if label.key is None:
            assert dark == set(), f"{member} {label.clear}: Japanese left where no word goes"
            continue
        face = face_named(label.face, game)
        ink = paint.normalised(ink_of(face, ENTRIES[f"{member}.{label.key}"]))
        placed = [
            moved for x, y in paint.points(room)
            if (moved := {(a + x, b + y) for a, b in ink}) <= dark
        ]  # fmt: skip
        assert len(placed) == 1, f"{member}.{label.key}: the English is not in its room once"
        assert dark == placed[0], f"{member}.{label.key}: ink besides the English"
        if record.shadow:
            shadow = {(x + 1, y + 1) for x, y in placed[0]} - placed[0]
            shades = {luminance(palette[canvas.at(p)]) for p in shadow}
            paper = max(luminance(palette[canvas.at(p)]) for p in area)
            assert len(shades) == 1 and tr.INK <= shades.pop() < paper, (
                f"{member}.{label.key}: the English has no drop shadow of one grey"
            )


@pytest.mark.parametrize(("member", "copy"), CASES, ids=[f"{m}-{c}" for m, c in CASES])
def test_no_label_leaves_japanese_outside_its_box(member, copy, texture_inventory):
    """The boxes are measured by hand; the stock image is the judge. From each box's ink, walk
    the stock's connected marks (ink, shadow and antialias, `tr.MARK` darker than the paper;
    never the undrawn, transparent texels round a sprite) a few pixels out: every one reached
    must lie in some label's box, or it is Japanese left showing beside the English."""
    record = tr.RECORDS[member]
    dx, dy, chunk = copy
    stock = paint.Canvas(texture_inventory.get(record.texture), drawn_4bpp=record.drawn_4bpp)
    palette = stock.palette(record.clut, chunk)

    def lum(p):
        return luminance(palette[stock.at(p)])

    boxes = [label.clear_at(dx, dy) for label in record.labels]
    inside = {p for box in boxes for p in paint.points(box)}
    for box in boxes:
        x0, y0, w, h = box
        ground = max(lum(p) for p in paint.points(box))
        marks = {
            p for p in paint.points((x0 - 4, y0 - 4, w + 8, h + 8))
            if lum(p) < ground - tr.MARK and palette[stock.at(p)][3]
        }  # fmt: skip
        ink = {p for p in paint.points(box) if lum(p) < tr.INK}
        for group in paint.groups(marks):
            outside = sorted(group - inside) if group & ink else []
            assert not outside, f"{member} {box}: marks outside, {outside[:5]}"


BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"
ROD_CARD = ["--day", "10", "--flag", "10=1", "--flag", "53=1",
            "--poke", "0x8003E0B0=0003E1002C010005F900F40000125B01C201"]  # fmt: skip
"""The rod (`g_flags[10]`), the four-row tackle list (`g_flags[53]`) and three fish caught (the
catch record at `0x8003E0B0`: `u8 picture, count; s16 average, largest` per fish)."""
NOTEBOOK_CARD = [
    "--day", "10", "--flag", "25=2", "--flag", "30=1", "--bug", "saw:68", "--bug", "giant:70",
    "--poke", "0x80045A14=070C0E03", "--poke", "0x80045A20=02050109",
    "--poke", "0x8003DE18=1D3C000004100502",
]  # fmt: skip
"""Bug sumo open, two bugs in the cage and an offer in the notebook (`0x8003DE18`)."""
FISH_ROUTE = ["TRIANGLE:400", "RIGHT:60", "CIRCLE:400", "LEFT:60", "DOWN:40", "DOWN:40",
              "DOWN:40", "DOWN:40", "r60"]  # fmt: skip
"""△ opens the desk on the belongings; RIGHT to the tackle box and ○; LEFT into the tackle
list, DOWN x4 to the summer's catch: the record shows."""
TWO_CARDS = ["r1100", "CIRCLE:900", "CIRCLE:50", "LEFT:40", "CIRCLE:400", "LEFT:90", "LEFT:90",
             "CIRCLE:400"]  # fmt: skip
"""A bug taken in hand first, then the notebook: the offered card over the held one."""
NOTEBOOK = ["r1100", "LEFT:90"]
"""At the bug-sumo desk, one LEFT puts the hand on the notebook, whose balloon (虫を交かん) names
the trade."""
ONE_CARD = [*NOTEBOOK, "LEFT:90", "CIRCLE:400"]
"""A second LEFT along the notebook, ○: the offered bug's card alone."""
SCREENS = {
    # screen: (card, the sumo desk?, route, the buttons on it (boku.texture_buttons) with where
    # each texture's (0, 0) lands, the records on it: (member, copy, the sprite's texture box
    # or None for all its labels, where the texture's (0, 0) lands for that sprite))
    "fishing": (ROD_CARD, False, FISH_ROUTE,
                [("FS_WAL.tackle", (16, -180)), ("FS_WAL.back", (204, -10))],
                [("FS_WAL", (0, 0, 0), (72, 64, 112, 48), (104, 60)),  # the field labels' plate
                 ("FS_WAL", (0, 0, 0), (48, 154, 88, 64), (0, -58))]),  # the four-row list
    "one_card": (NOTEBOOK_CARD, True, ONE_CARD, [],
                 [("M_S01100", (256, 1, 5), None, (-388, 48))]),
    "two_cards": (NOTEBOOK_CARD, True, TWO_CARDS, [("M_S01100.trade_plate", (-48, -112))],
                  [("M_S01100", (0, 0, 4), None, (-132, 18)),
                   ("M_S01100", (0, 106, 4), None, (-132, 18))]),
    "notebook": (NOTEBOOK_CARD, True, NOTEBOOK, [("M_S01100.swap", (-392, 104))], []),
}  # fmt: skip
MARKER_SIGNS_ON = {"one_card": [("M_S01000", (-264, 90))]}
"""The marker signs (`boku.texture_text.MARKER_SIGNS`) a screen shows, and where each texture's
(0, 0) lands: the bug-trading notebook's cover lies on the bug-sumo desk (measured by matching
every changed texel on the English image)."""


DRIVE = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from field import Game, land_in
from sumo_bout import enter_desk
g = Game(Path(sys.argv[2]), Path(sys.argv[3]).read_bytes(), Path(sys.argv[4]))
land_in(g, "A18")
if sys.argv[5] == "1":
    enter_desk(g)
for op in sys.argv[6:]:
    if op.startswith("r"):
        g.run(int(op[1:]))
    else:
        button, _, after = op.partition(":")
        g.press(button, int(after))
g.fe.screenshot(Path(sys.argv[4]) / "shot.png")
"""
"""Land in A18 through the dawn movie (`tools/libretro/field.py`), open the bug-sumo desk if
asked (`sumo_bout.enter_desk`), press the route, shoot."""


@pytest.fixture(scope="module")
def card(disc_dir, tmp_path_factory):
    """A card made from `BASE` by `boku save` with the given arguments, once per arguments."""
    if not BASE.is_file():
        pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
    made: dict[tuple[str, ...], Path] = {}

    def make(args: list[str]) -> Path:
        if tuple(args) not in made:
            out = tmp_path_factory.mktemp("card") / "card.mcd"
            subprocess.run(
                [sys.executable, "-m", "boku", "save", "--base", str(BASE), *args,
                 "--out", str(out), "--disc", str(disc_dir)],
                cwd=REPO_ROOT, check=True, capture_output=True,
            )  # fmt: skip
            made[tuple(args)] = out
        return made[tuple(args)]

    return make


def within(box: paint.Box, outer: paint.Box) -> bool:
    return (outer[0] <= box[0] and box[0] + box[2] <= outer[0] + outer[2]
            and outer[1] <= box[1] and box[1] + box[3] <= outer[1] + outer[3])  # fmt: skip


@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_records_on_beetle_are_the_typeset_english(
    screen, texture_image, card, texture_inventory, texture_patched, tmp_path
):  # fmt: skip
    card_args, desk, route, buttons, records = SCREENS[screen]
    subprocess.run(
        [sys.executable, "-c", DRIVE, str(REPO_ROOT / "tools/libretro"), str(texture_image),
         str(card(card_args)), str(tmp_path), "1" if desk else "0", *route],
        cwd=REPO_ROOT, check=True, capture_output=True, timeout=900,
    )  # fmt: skip
    shot = read_png((tmp_path / "shot.png").read_bytes())
    for key, origin in buttons:
        check_on_screen(shot, texture_inventory, texture_patched, key, origin, None)
    for member, (dx, dy, chunk), sprite, origin in records:
        record = tr.RECORDS[member]
        labels = [label for label in record.labels if sprite is None or within(label.clear, sprite)]
        points = {p for label in labels for p in paint.points(label.room_at(dx, dy))}
        check_texels(shot, texture_inventory, texture_patched, record, record.clut, chunk,
                     sorted(points), origin, f"{member} {dx, dy}", at_least=30)  # fmt: skip
    for name, (ox, oy) in MARKER_SIGNS_ON.get(screen, []):
        from tests.test_real_texture_text_beetle import compare, sign_area

        sign = tt.MARKER_SIGNS[name]
        area = sign_area(sign)
        n, wrong = compare(shot, texture_inventory, texture_patched, sign.texture, sign.clut,
                           area, (area[0] + ox, area[1] + oy))  # fmt: skip
        assert n > 500, f"{name}: the build changed too few texels where the check looked"
        assert wrong == [], f"{name}: {len(wrong)} of {n} texels differ, first {wrong[:5]}"
