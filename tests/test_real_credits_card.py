"""The epilogue's closing card (`boku.texture_text.credits_strip`, PLAN `GFX-10`) against the
contributor's import, and on Beetle PSX.

Texture level: the rebuilt card's opaque texels are exactly its two English lines in the
game's glyphs, each once, centred where its Japanese line was and in one grey as pale as the
Japanese's -- nothing of the Japanese left.

On Beetle (`BOKU_EMU_TESTS=1`, `./make.sh saves` for the base): a generated day-31 card with no
stars, `g_flags[251]` poked to 12 so the last walk ends the summer (the clip-subtitle gate's
route), plays through `MOVIE 24`'s scrolling credits (video, left as they are) to `ENDOTI`,
whose last still is this card on black; every texel of it must show on screen exactly. The
stock image fails it.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from boku import REPO_ROOT
from boku import texture_paint as paint
from boku import texture_text as tt
from boku.build import build
from boku.png import read as read_png
from boku.save import G_FLAGS
from boku.textures import Texture
from boku.tim import luminance, parse_exact
from boku.typeset import FONT_SHEET_ID, GameFace

ENTRIES = {e.id.removeprefix("tex@OTI."): e for e in tt.read_entries().values()
           if e.family == "tex@OTI"}  # fmt: skip


def rebuilt(inv, patched: bytes) -> paint.Canvas:
    stock = inv.get(tt.CREDITS_STRIP)
    tim = parse_exact(patched, stock.occurrences[0].file_offset)
    return paint.Canvas(Texture(stock.id, "0" * 40, tim, ()))


def test_every_copy_of_the_card_is_patched(texture_inventory, texture_edits):
    places = {o.file_offset for o in texture_inventory.get(tt.CREDITS_STRIP).occurrences}
    assert len(places) == 5, "one card in each of OTI00-OTI04"
    edited = {e.offset for e in texture_edits.edits}
    for place in places:
        tim_bytes = texture_inventory.get(tt.CREDITS_STRIP).tim.length
        assert any(place <= at < place + tim_bytes for at in edited), f"copy at {place:#x}"


def test_the_card_carries_its_two_english_lines_and_nothing_else(
    texture_inventory, texture_patched
):  # fmt: skip
    game = GameFace.from_sheet(texture_inventory.get(FONT_SHEET_ID).tim)
    canvas = rebuilt(texture_inventory, texture_patched)
    palette = canvas.palette(0)
    opaque = {p for p in paint.points((0, 0, canvas.width, canvas.height))
              if palette[canvas.at(p)][3]}  # fmt: skip
    stock = paint.Canvas(texture_inventory.get(tt.CREDITS_STRIP))
    found = set()
    for key, (_, y0, _, h) in tt.CREDITS_LINES:
        ink = paint.normalised(tt.ink_of(game, ENTRIES[key]))
        rows = {p for p in opaque if y0 <= p[1] < y0 + h}
        assert paint.normalised(rows) == ink, f"the {key} line is not the English"
        japanese = {
            p for p in paint.points((0, y0, canvas.width, h)) if palette[stock.at(p, stock=True)][3]
        }
        left, right = min(x for x, _ in japanese), max(x for x, _ in japanese)
        mine = (min(x for x, _ in rows), max(x for x, _ in rows))
        assert abs((mine[0] + mine[1]) - (left + right)) <= 1, f"the {key} line is off centre"
        pale = max(luminance(palette[stock.at(p, stock=True)]) for p in japanese)
        entries = {canvas.at(p) for p in rows}
        assert len(entries) == 1 and luminance(palette[entries.pop()]) >= pale - 40, (
            f"the {key} line is not in one grey as pale as the Japanese's"
        )
        found |= rows
    assert opaque == found, "the card keeps texels outside its two lines"


ENDING_CARD = ["--day", "31", "--stars-mask", "0"]
FLAG_251 = f"11450:{G_FLAGS + 251:#x}=0c"
SHOT = 32300
"""The card is up from ~32200 to ~32450 on this route (measured; it then fades)."""
ON_SCREEN = (23, 94)
"""Where the card's (0, 0) lands (measured by matching its texels)."""
BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"


def test_the_closing_card_on_beetle_is_the_english(
    texture_edits, texture_inventory, texture_patched, real_image, disc_dir, tmp_path_factory
):  # fmt: skip
    if os.environ.get("BOKU_EMU_TESTS") != "1":
        pytest.skip("set BOKU_EMU_TESTS=1: an image build and a Beetle boot to the ending")
    for var in ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM"):
        if not os.environ.get(var):
            pytest.skip(f"{var} is not set (research/tooling-setup.md)")
    if not BASE.is_file():
        pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
    work = tmp_path_factory.mktemp("credits")
    out = build(
        source=real_image, out_dir=work / "image", disc_dir=disc_dir,
        binary_patches=texture_edits.edits, name="credits",
    )  # fmt: skip
    card = work / "ending.mcd"
    subprocess.run(
        [sys.executable, "-m", "boku", "save", "--base", str(BASE), *ENDING_CARD,
         "--out", str(card), "--disc", str(disc_dir)],
        cwd=REPO_ROOT, check=True, capture_output=True,
    )  # fmt: skip
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/libretro/run_core.py"),
         str(out.written.image.with_suffix(".cue")),
         "--core", os.environ["BOKU_LIBRETRO_CORE"], "--system", os.environ["BOKU_LIBRETRO_SYSTEM"],
         "--work", str(work), "--memcard", str(card), "--frames", str(SHOT + 10),
         "--press-file", str(REPO_ROOT / "tools/libretro/boot-to-save.press"),
         "--poke", FLAG_251, "--shot", f"{SHOT}:card"],
        cwd=REPO_ROOT, check=True, capture_output=True, timeout=900,
    )  # fmt: skip
    shot = read_png((work / "card.png").read_bytes())
    canvas = rebuilt(texture_inventory, texture_patched)
    palette = canvas.palette(0)
    ox, oy = ON_SCREEN
    wrong, lit = [], 0
    for x, y in paint.points((0, 0, canvas.width, canvas.height)):
        colour = palette[canvas.at((x, y))]
        want = tuple(c >> 3 << 3 for c in colour[:3]) if colour[3] else (0, 0, 0)
        at = ((oy + y) * shot.width + ox + x) * 4
        seen = tuple(shot.rgba[at : at + 3])
        lit += bool(colour[3])
        if seen != want:
            wrong.append((x, y, seen))
    assert lit > 300, "the English was not drawn into the card"
    assert wrong == [], f"{len(wrong)} texels differ, first {wrong[:5]}"
