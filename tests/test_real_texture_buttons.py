"""The buttons (`boku.texture_buttons`) against the contributor's own import, and on Beetle PSX.

Texture level: every tracked button's rebuilt box carries exactly its English -- a stone's
ink-dark pixels are the English set bold in the disc's glyphs, a balloon's type is the English
lines -- and nothing of the Japanese; a widened balloon's atlas entry is grown. The expected
pixels are derived from the translation file and the glyph sheet.

On Beetle (`BOKU_EMU_TESTS=1`): an image carrying only the texture edits is driven to the
settings screen, the load screen (a generated card, `./make.sh saves`) and the diary desk, and
every opaque texel of each button's box must show its rebuilt colour exactly. The stock image
fails it: the Japanese is on screen where the English is expected. Where each box lands was
measured by matching its texels against a screenshot (`research/texture-recipes.md` §
"Buttons").
"""

from __future__ import annotations

import dataclasses
import os
import struct
import subprocess
import sys

import pytest

from boku import REPO_ROOT
from boku import texture_buttons as tb
from boku import texture_paint as paint
from boku.png import read as read_png
from boku.texture_text import TextureTextError, ink_of, lines_of, read_entries
from boku.textures import Texture
from boku.tim import luminance, parse_exact
from boku.typeset import FONT_SHEET_ID, GameFace, face_named

ENTRIES = {e.id.removeprefix(tb.FAMILY): e for e in read_entries().values()
           if e.family == tb.FAMILY}  # fmt: skip


def rebuilt(inv, patched: bytes, source) -> paint.Canvas:
    """The texture of `source` (a button, a record: anything with `.texture` and `.drawn_4bpp`)
    as the build left it (its `stock` view is the rebuilt pixels)."""
    stock = inv.get(source.texture)
    tim = parse_exact(patched, stock.occurrences[0].file_offset)
    return paint.Canvas(Texture(stock.id, "0" * 40, tim, ()), drawn_4bpp=source.drawn_4bpp)


def box_of(button: tb.Button) -> paint.Box:
    return button.placed


@pytest.fixture(scope="module")
def game(texture_inventory) -> GameFace:
    return GameFace.from_sheet(texture_inventory.get(FONT_SHEET_ID).tim)


def test_every_measured_button_has_its_english_tracked():
    assert set(ENTRIES) == set(tb.BUTTONS)


FACE = (6, 0, 34, 15)
"""Where the Japanese could be on a stone, from its top-left corner: the face above the lip,
right of the wing's shading (measured on `TZICON`'s stone, atlas rows 72-86; the glyphs'
bottoms reach row 86, where they meet the lip)."""


@pytest.mark.parametrize("key", sorted(k for k, b in tb.BUTTONS.items() if b.kind == "stone"))
def test_a_stone_carries_its_english_bold_and_no_japanese(
    key, texture_inventory, texture_patched, game
):  # fmt: skip
    button = tb.BUTTONS[key]
    canvas = rebuilt(texture_inventory, texture_patched, button)
    palette = canvas.palette(button.clut, button.chunk)
    stock = paint.Canvas(texture_inventory.get(button.texture), drawn_4bpp=button.drawn_4bpp)
    dx, dy, _, _ = tb.STONE_TEXT
    fx, fy, fw, fh = FACE
    around = (button.box[0] - dx + fx, button.box[1] - dy + fy, fw, fh)
    box = paint.points(around)
    dark = {p for p in box if luminance(palette[canvas.at(p)]) < tb.INK_DARK}
    outline = set(box) - tb.inside_stone(stock, button, around)
    english = paint.normalised(paint.bold(ink_of(game, ENTRIES[key])))
    shifts = [(x, y) for x, y in paint.points(around)]
    placed = [
        moved for dx, dy in shifts
        if (moved := {(x + dx, y + dy) for x, y in english}) <= dark
    ]  # fmt: skip
    assert len(placed) == 1, "the English, bold in the disc's glyphs, is not in the box once"
    left = {p for p in dark - placed[0] if not (p in outline and canvas.at(p) == stock.at(p))}
    assert left == set(), (
        f"dark pixels that are neither the English nor the stone's outline: {left}"
    )


@pytest.mark.parametrize("key", sorted(k for k, b in tb.BUTTONS.items() if b.kind == "label"))
def test_a_card_label_carries_its_english_and_no_japanese(
    key, texture_inventory, texture_patched, game
):  # fmt: skip
    """The attendance card: the only printed (saturated) pixels in the label's box are the
    English lines in their face, once."""
    button = tb.BUTTONS[key]
    canvas = rebuilt(texture_inventory, texture_patched, button)
    palette = canvas.palette(button.clut, button.chunk)
    x0, y0, w, h = button.box
    near = [(x, y) for x, y in paint.points((x0 - 2, y0 - 2, w + 4, h + 4))
            if 0 <= x < canvas.width and 0 <= y < canvas.height]  # fmt: skip
    # the tinted fringe of the hole punched in the card's corner stays as it was
    hole = paint.grown({p for p in near if not palette[canvas.at(p)][3]}, 2, 2, 2, 2)
    printed = {
        p for p in paint.points(button.box)
        if tb.saturation(palette[canvas.at(p)]) > tb.INK_SATURATION and p not in hole
    }  # fmt: skip
    block = tb.lines_block(face_named(button.face, game), lines_of(ENTRIES[key]), ENTRIES[key])
    placed = [
        moved for dx, dy in paint.points(button.box)
        if (moved := {(x + dx, y + dy) for x, y in block}) <= printed
    ]  # fmt: skip
    assert len(placed) == 1, "the English lines, in their face, are not on the card once"
    assert printed - placed[0] == set(), (
        f"printed besides the English: {sorted(printed - placed[0])}"
    )


@pytest.mark.parametrize(
    "key", sorted(k for k, b in tb.BUTTONS.items() if b.kind in ("plank", "plate"))
)
def test_a_board_carries_its_english_and_no_japanese(
    key, texture_inventory, texture_patched, game
):  # fmt: skip
    """The Close board (bold, its punched-through Japanese transparent) and the swap plate:
    every dark or transparent pixel of the room is the English, once."""
    button = tb.BUTTONS[key]
    canvas = rebuilt(texture_inventory, texture_patched, button)
    room = tb.text_area(button, box_of(button)) if button.kind == "plate" else button.box
    palette = canvas.palette(button.clut, button.chunk)
    colours = {p: palette[canvas.at(p)] for p in paint.points(room)}
    dark = {p for p, c in colours.items() if not c[3] or luminance(c) < tb.INK_DARK}
    ink = ink_of(game, ENTRIES[key])
    english = paint.normalised(paint.bold(ink) if button.kind == "plank" else ink)
    assert paint.normalised(dark) == english


STROKE = 8
"""Dark pixels in one group that make a stroke of type, not a speck of the tail's shading
(the largest measured is 4)."""


@pytest.mark.parametrize("key", sorted(k for k, b in tb.BUTTONS.items() if b.kind == "balloon"))
def test_a_balloon_carries_its_english_lines_and_no_japanese(
    key, archive, texture_inventory, texture_patched, game
):  # fmt: skip
    button = tb.BUTTONS[key]
    canvas = rebuilt(texture_inventory, texture_patched, button)
    x0, y0, w, h = box_of(button)
    palette = canvas.palette(button.clut, button.chunk)
    pale = [p for p in paint.points((x0, y0, w, h)) if luminance(palette[canvas.at(p)]) > 200]
    paper = paint.most_used(canvas.stock, canvas.width, pale)
    interior = set()
    for y in range(y0, y0 + h):
        xs = [x for x in range(x0, x0 + w) if canvas.at((x, y)) == paper]
        if xs:
            interior |= {(x, y) for x in range(min(xs), max(xs) + 1)}
    face = face_named(button.face, game)
    expected = tb.lines_block(face, lines_of(ENTRIES[key]), ENTRIES[key])
    ink = {p for p in interior if canvas.at(p) != paper}
    placed = [
        moved for dx, dy in paint.points((x0, y0, w, h))
        if (moved := {(x + dx, y + dy) for x, y in expected}) <= ink
    ]  # fmt: skip
    assert len(placed) == 1, "the English lines, in their face, are not in the balloon once"
    dark = {p for p in ink - placed[0] if luminance(palette[canvas.at(p)]) < tb.SOFT}
    left = [g for g in tb.groups(dark) if len(g) >= STROKE]
    assert left == [], f"marks of type left beside the English: {[sorted(g)[:3] for g in left]}"
    if button.widen:
        assert_sizes_follow(archive, texture_inventory, texture_patched, button)


PAIRED = {"MZ02.next_page": "MZ02.prev_page"}
"""Set in the face of a partner shown beside it, which the game's glyphs cannot hold: the insect
box's two page pencils sit side by side, and a pair in two faces is the mix Jay ruled out."""
SMALL = sorted(k for k, b in tb.BUTTONS.items() if b.face != "game" and k not in PAIRED)


@pytest.mark.parametrize(("key", "partner"), sorted(PAIRED.items()))
def test_a_paired_button_shares_its_partners_small_face(key, partner):
    assert tb.BUTTONS[key].face == tb.BUTTONS[partner].face != "game"
    assert partner in SMALL, "the partner must itself be one the game's glyphs cannot hold"


@pytest.mark.parametrize("key", SMALL)
def test_a_button_is_set_small_only_where_the_games_glyphs_do_not_fit(
    key, archive, texture_inventory, game, monkeypatch
):  # fmt: skip
    """Jay, 2026-09-24: mixing faces in one place looks bad -- the game's glyphs wherever they
    fit. So a button in Bean or Sprout is one the recipe refuses for size in the game's glyphs."""
    monkeypatch.setitem(tb.BUTTONS, key, dataclasses.replace(tb.BUTTONS[key], face="game"))
    with pytest.raises(TextureTextError, match="nothing is cut to fit"):
        tb.buttons(archive, texture_inventory, game, [ENTRIES[key]])


def assert_sizes_follow(archive, inv, patched: bytes, button: tb.Button) -> None:
    """Every stored size of a widened sprite spans its new art: width grown by `extra`, and an
    atlas entry's position moved with the art."""
    x, y, _, _ = box_of(button)
    moved = (x - button.box[0], y - button.box[1])
    for size in button.widen.sizes:
        if isinstance(size, tb.AtlasEntry):
            first = inv.get(button.texture).occurrences[0].file_offset
            x_words, v, w_words, *_ = struct.unpack_from("<6H", patched, first + size.at)
            per = size.per_word
            assert (x_words * per, v, w_words * per) == (
                size.entry[0] * per + moved[0], size.entry[1] + moved[1],
                size.entry[2] * per + button.widen.extra,
            )  # fmt: skip
        else:
            at = archive.overlay_offset(size.overlay, size.ram + 8)
            assert struct.unpack_from("<H", patched, at)[0] == size.width + button.widen.extra


BOOT = ["--press-file", str(REPO_ROOT / "tools/libretro/boot-to-dialogue.press")]
FREE = 24000
"""A new game, left alone after its first dialogue, is free to roam by this frame; the desk's
atlas is loaded at boot (`SUB.BIN` is resident), so the desk is only seen in English from a
boot of the English image, not from a state saved on another."""


def mode(n: int, arena: str) -> list[str]:
    """`mode_set(n)` by hand after the first dialogue (`test_real_texture_text_beetle`)."""
    pokes = ["0x800237E5=05", f"0x800237E0={n:02x}", f"0x800237E4={n:02x}",
             "0x80024728=01000000", f"0x800258E0={arena}"]  # fmt: skip
    return [*BOOT, *(a for poke in pokes for a in ("--poke", f"6500:{poke}"))]


SCREENS = {
    # screen: (presses and pokes, needs a card, {shot frame: [(button, texture origin, skip)]})
    "settings": (
        ["--press", "3300:START", "--press", "3700:DOWN", "--press", "3760:DOWN",
         "--press", "3820:DOWN", "--press", "3900:CIRCLE"],
        False, {4250: [("T_CONFIG.back", (176, 150), None)]},
    ),
    "load": (
        ["--press", "3300:START", "--press", "3610:DOWN", "--press", "3680:CIRCLE"],
        True, {4160: [("M_S01001.back", (8, 0), None)]},
    ),
    "diary": (
        mode(0x0B, "f4791180"), False,
        {7000: [("NIKKI_W.back", (256, 100), None), ("NIKKI_W.good_night", (40, -48), None)]},
    ),
    "desk": (
        [*BOOT, "--press", f"{FREE + 30}:TRIANGLE", "--press", f"{FREE + 320}:RIGHT"], False,
        {FREE + 300: [("SUB.belongings", (-664, -56), None)],
         FREE + 520: [("SUB.tackle", (-260, -82), (102, 136, 6, 10))]},
    ),
    "bag": (
        [*BOOT, "--press", f"{FREE + 30}:TRIANGLE", "--press", f"{FREE + 330}:CIRCLE"], False,
        {FREE + 790: [("PK_WAL.belongings", (16, -180), None),
                      ("PK_WAL.back", (176, 110), None),
                      ("PK_ITM.title", (176, 26), "drawn"), ("PK_ITM.footer", (176, 26), "drawn")]},
    ),
    "kite_record": (
        [*BOOT, "--poke", f"{FREE}:0x80047EC0=0101", "--press", f"{FREE + 30}:TRIANGLE",
         "--press", f"{FREE + 330}:UP", "--press", f"{FREE + 460}:CIRCLE"], False,
        {FREE + 1150: [("TK_WAL.kite", (16, -180), None),
                       ("TK_WAL.back", (204, -10), (276, 193, 3, 1))]},
    ),
    "kite_book": (
        [*mode(0x0C, "f4791180"), "--poke", "7010:0x800459DC=08000000"], False,
        {7200: [("TZICON.make_this_kite", (16, 160), None), ("TZICON.back", (256, 130), None)]},
    ),
    "insect_book": (
        [*mode(0x0D, "f4791180")], False, {7290: [("MZKAN.back", (256, 202), None)]},
    ),
    "bug_sumo": (
        [*BOOT, "--poke", "5300:0x80036588=41313800", "--poke", "5300:0x80036359=01",
         "--poke", "5300:0x8003635A=b90f", "--poke", "5300:0x80035E61=02",
         "--poke", "5300:0x80035E66=01"], False,
        {7000: [("M_S01100.cage", (-296, -40), None)]},
    ),
    "insect_box": (
        [*mode(0x0A, "f43d1b80"), "--press", "7250:DOWN", "--press", "7700:DOWN"], False,
        {7200: [("MZ02.cage", (-540, 40), None)],
         7690: [("MZ02.collecting_box", (-520, 8), None), ("SAMP.back", (-80, 177), None)],
         7800: [("MZ02.remove_specimen", (-476, 48), (162, 178, 9, 20))]},
    ),
}  # fmt: skip
"""Measured on the English image by matching each box's texels near where the recon put it
(`research/texture-recipes.md` § "Buttons"). A texture origin is where the texture's (0, 0)
lands on screen; `skip` is a screen rectangle the hand cursor is drawn over, or "drawn" for
a picture the game draws dithered (`check_drawn`). The diary's and
the kite book's balloons are idle hints; the kite record needs kite 0 owned (the poke);
bug sumo and the insect box are forced by the recon's pokes. Not compared, though seen: the
bug-sumo desk's stone, drawn through a CLUT that is not in its TIM."""
BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"


@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_buttons_on_beetle_are_the_typeset_english(
    screen, texture_image, disc_dir, texture_inventory, texture_patched, tmp_path
):  # fmt: skip
    args, card, shots = SCREENS[screen]
    command = [
        sys.executable, str(REPO_ROOT / "tools/libretro/run_core.py"), str(texture_image),
        "--core", os.environ["BOKU_LIBRETRO_CORE"], "--system", os.environ["BOKU_LIBRETRO_SYSTEM"],
        "--work", str(tmp_path), "--frames", str(max(shots) + 10), *args,
    ]  # fmt: skip
    for frame in shots:
        command += ["--shot", f"{frame}:{screen}-{frame}"]
    if card:
        if not BASE.is_file():
            pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
        mcd = tmp_path / "day05.mcd"
        subprocess.run(
            [sys.executable, "-m", "boku", "save", "--base", str(BASE), "--day", "5",
             "--out", str(mcd), "--disc", str(disc_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True,
        )  # fmt: skip
        command += ["--memcard", str(mcd)]
    subprocess.run(command, check=True, capture_output=True, timeout=600, cwd=REPO_ROOT)
    for frame, buttons in shots.items():
        shot = read_png((tmp_path / f"{screen}-{frame}.png").read_bytes())
        for key, origin, skip in buttons:
            if skip == "drawn":
                check_drawn(shot, texture_inventory, texture_patched, key, origin)
            else:
                check_on_screen(shot, texture_inventory, texture_patched, key, origin, skip)


DITHER = 8
"""How far Beetle's dither moves each channel of the attendance card: measured, every texel
of it is its colour exactly or 8 less on all three channels."""


def check_drawn(shot, inv, patched: bytes, key: str, origin) -> None:
    """For an item picture the game draws dithered (the attendance card in the bag): every
    opaque texel of the box is on screen within `DITHER` of its rebuilt colour on each channel;
    and enough of them are ones the build changed."""
    button = tb.BUTTONS[key]
    check_texels(shot, inv, patched, button, button.clut, button.chunk,
                 paint.points(button.placed), origin, key, dither=DITHER)  # fmt: skip


def check_on_screen(shot, inv, patched: bytes, key: str, origin, skip) -> None:
    """Every opaque texel of the button's box, as rebuilt, is on screen exactly, but those
    under `skip`; and enough of them are ones the build changed."""
    button = tb.BUTTONS[key]
    check_texels(shot, inv, patched, button, button.clut, button.chunk,
                 paint.points(box_of(button)), origin, key, skip=skip)  # fmt: skip


def check_texels(shot, inv, patched: bytes, source, clut: int, chunk: int, points, origin,
                 what: str, *, skip=None, dither: int = 0, at_least: int = 60) -> None:  # fmt: skip
    """Every opaque texel at `points` of `source`'s texture (anything with `.texture` and
    `.drawn_4bpp`), as rebuilt, is on screen with `origin` at its (0, 0) -- at the colour Beetle
    shows it, or up to `dither` darker on each channel -- but those under screen box `skip`;
    and more than `at_least` of them are ones the build changed."""
    ox, oy = origin
    canvas = rebuilt(inv, patched, source)
    stock = paint.Canvas(inv.get(source.texture), drawn_4bpp=source.drawn_4bpp)
    palette = canvas.palette(clut, chunk)
    compared, changed, wrong = 0, 0, []
    for x, y in points:
        colour = palette[canvas.at((x, y))]
        sx, sy = ox + x, oy + y
        hidden = skip and skip[0] <= sx < skip[0] + skip[2] and skip[1] <= sy < skip[1] + skip[3]
        if not colour[3] or hidden:
            continue
        at = (sy * shot.width + sx) * 4
        seen = tuple(shot.rgba[at : at + 3])
        compared += 1
        changed += canvas.at((x, y)) != stock.at((x, y))
        want = [c >> 3 << 3 for c in colour[:3]]
        if not all(0 <= w - s <= dither for s, w in zip(seen, want, strict=True)):
            wrong.append((x, y, seen))
    assert changed > at_least, f"{what}: the build changed too few texels where the check looked"
    assert wrong == [], f"{what}: {len(wrong)} of {compared} texels differ, first {wrong[:5]}"
