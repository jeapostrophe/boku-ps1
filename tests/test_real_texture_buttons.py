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
    x, y, w, h = button.box
    return x, y, w + (button.widen.extra if button.widen else 0), h


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
    marks = {p for p in interior if canvas.at(p) != paper}
    face = tb._face(button, game)
    expected = tb.lines_block(face, lines_of(ENTRIES[key]), ENTRIES[key])
    assert paint.normalised(tb.islands(marks, interior)) == expected
    if button.widen:
        first = texture_inventory.get(button.texture).occurrences[0].file_offset
        at = first + button.widen.entry_at
        _, _, w_words, *_ = struct.unpack_from("<6H", texture_patched, at)
        assert w_words * 4 == button.widen.entry[2] * 4 + button.widen.extra


SCREENS = {
    # screen: (press schedule and pokes, shot frame, needs a card, [(button, texture origin)])
    "settings": (
        ["--press", "3300:START", "--press", "3700:DOWN", "--press", "3760:DOWN",
         "--press", "3820:DOWN", "--press", "3900:CIRCLE"],
        4250, False, [("T_CONFIG.back", (176, 150))],
    ),
    "load": (
        ["--press", "3300:START", "--press", "3610:DOWN", "--press", "3680:CIRCLE"],
        4160, True, [("M_S01001.back", (8, 0))],
    ),
    "diary": (
        ["--press-file", str(REPO_ROOT / "tools/libretro/boot-to-dialogue.press"),
         "--poke", "6500:0x800237E5=05", "--poke", "6500:0x800237E0=0b",
         "--poke", "6500:0x800237E4=0b", "--poke", "6500:0x80024728=01000000",
         "--poke", "6500:0x800258E0=f4791180"],
        7000, False, [("NIKKI_W.back", (256, 100)), ("NIKKI_W.good_night", (40, -48))],
    ),
}  # fmt: skip
"""The diary desk is `mode_set(11)` by hand (`test_real_texture_text_beetle.DIARY_MODE`); the
good-night balloon is its idle hint, drawn after 61 frames with no input. A texture origin is
where the texture's (0, 0) lands on screen; negative where only part of it is drawn."""
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
    args, frame, card, buttons = SCREENS[screen]
    command = [
        sys.executable, str(REPO_ROOT / "tools/libretro/run_core.py"), str(image),
        "--core", os.environ["BOKU_LIBRETRO_CORE"], "--system", os.environ["BOKU_LIBRETRO_SYSTEM"],
        "--work", str(tmp_path), "--frames", str(frame + 10), "--shot", f"{frame}:{screen}", *args,
    ]  # fmt: skip
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
    shot = read_png((tmp_path / f"{screen}.png").read_bytes())
    for key, (ox, oy) in buttons:
        button = tb.BUTTONS[key]
        canvas = rebuilt(texture_inventory, texture_patched, button)
        stock = paint.Canvas(texture_inventory.get(button.texture), drawn_4bpp=button.drawn_4bpp)
        palette = canvas.palette(button.clut, button.chunk)
        compared, changed, wrong = 0, 0, []
        for x, y in paint.points(box_of(button)):
            colour = palette[canvas.at((x, y))]
            if not colour[3]:
                continue
            at = ((oy + y) * shot.width + ox + x) * 4
            seen = tuple(shot.rgba[at : at + 3])
            compared += 1
            changed += canvas.at((x, y)) != stock.at((x, y))
            if seen != tuple(c >> 3 << 3 for c in colour[:3]):
                wrong.append((x, y, seen))
        assert changed > 60, f"{key}: the build changed too few texels where the check looked"
        assert wrong == [], f"{key}: {len(wrong)} of {compared} texels differ, first {wrong[:5]}"
