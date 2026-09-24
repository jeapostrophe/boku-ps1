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

import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku import texture_buttons as tb
from boku import texture_paint as paint
from boku.build import build
from boku.png import read as read_png
from boku.texture_text import ink_of, lines_of, read_entries
from boku.textures import Texture
from boku.tim import luminance, parse_exact
from boku.typeset import FONT_SHEET_ID, GameFace

ENTRIES = {e.id.removeprefix(tb.FAMILY): e for e in read_entries().values()
           if e.family == tb.FAMILY}  # fmt: skip


def rebuilt(inv, patched: bytes, button: tb.Button) -> paint.Canvas:
    """The button's texture as the build left it (its `stock` view is the rebuilt pixels)."""
    stock = inv.get(button.texture)
    tim = parse_exact(patched, stock.occurrences[0].file_offset)
    return paint.Canvas(Texture(stock.id, "0" * 40, tim, ()), drawn_4bpp=button.drawn_4bpp)


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
    face = tb._face(button, game)
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
        {FREE + 790: [("PK_WAL.belongings", (-248, -140), None),
                      ("PK_WAL.back", (176, 110), None)]},
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
    "bug_sumo": (
        [*BOOT, "--poke", "5300:0x80036588=41313800", "--poke", "5300:0x80036359=01",
         "--poke", "5300:0x8003635A=b90f", "--poke", "5300:0x80035E61=02",
         "--poke", "5300:0x80035E66=01"], False,
        {7000: [("M_S01100.cage", (-296, -40), None)]},
    ),
    "insect_box": (
        [*mode(0x0A, "f43d1b80"), "--press", "7250:DOWN"], False,
        {7200: [("MZ02.cage", (-540, 40), None)],
         7690: [("MZ02.collecting_box", (-520, 8), None), ("SAMP.back", (-80, 177), None)]},
    ),
}  # fmt: skip
"""Measured on the English image by matching each box's texels near where the recon put it
(`research/texture-recipes.md` § "Buttons"). A texture origin is where the texture's (0, 0)
lands on screen; `skip` is a screen rectangle the hand cursor is drawn over. The diary's and
the kite book's balloons are idle hints; the kite record needs kite 0 owned (the poke);
bug sumo and the insect box are forced by the recon's pokes. Not compared, though seen: the
bug-sumo desk's stone, drawn through a CLUT that is not in its TIM."""
BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"


@pytest.fixture(scope="module")
def image(texture_edits, real_image, disc_dir, tmp_path_factory) -> Path:
    if os.environ.get("BOKU_EMU_TESTS") != "1":
        pytest.skip("set BOKU_EMU_TESTS=1: an image build and Beetle boots")
    for var in ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM"):
        if not os.environ.get(var):
            pytest.skip(f"{var} is not set (research/tooling-setup.md)")
    out = build(
        source=real_image, out_dir=tmp_path_factory.mktemp("image"), disc_dir=disc_dir,
        binary_patches=texture_edits.edits, name="buttons",
    )  # fmt: skip
    return out.written.image.with_suffix(".cue")


@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_buttons_on_beetle_are_the_typeset_english(
    screen, image, disc_dir, texture_inventory, texture_patched, tmp_path
):  # fmt: skip
    args, card, shots = SCREENS[screen]
    command = [
        sys.executable, str(REPO_ROOT / "tools/libretro/run_core.py"), str(image),
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
            check_on_screen(shot, texture_inventory, texture_patched, key, origin, skip)


def check_on_screen(shot, inv, patched: bytes, key: str, origin, skip) -> None:
    """Every opaque texel of the button's box, as rebuilt, is on screen exactly, but those
    under `skip`; and enough of them are ones the build changed."""
    ox, oy = origin
    button = tb.BUTTONS[key]
    canvas = rebuilt(inv, patched, button)
    stock = paint.Canvas(inv.get(button.texture), drawn_4bpp=button.drawn_4bpp)
    palette = canvas.palette(button.clut, button.chunk)
    compared, changed, wrong = 0, 0, []
    for x, y in paint.points(box_of(button)):
        colour = palette[canvas.at((x, y))]
        sx, sy = ox + x, oy + y
        hidden = skip and skip[0] <= sx < skip[0] + skip[2] and skip[1] <= sy < skip[1] + skip[3]
        if not colour[3] or hidden:
            continue
        at = (sy * shot.width + sx) * 4
        seen = tuple(shot.rgba[at : at + 3])
        compared += 1
        changed += canvas.at((x, y)) != stock.at((x, y))
        if seen != tuple(c >> 3 << 3 for c in colour[:3]):
            wrong.append((x, y, seen))
    assert changed > 60, f"{key}: the build changed too few texels where the check looked"
    assert wrong == [], f"{key}: {len(wrong)} of {compared} texels differ, first {wrong[:5]}"
