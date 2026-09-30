"""The kite-flying HUD's labels (`boku.texture_kite`) against the contributor's import, and on
Beetle PSX.

Texture level, on both sheets: each label's cell holds its English in the game's glyphs,
white with a dark edge all round, and nothing else; nothing is left where the Japanese was;
the digits and the units are as they were; and each label's record in `TAKO.OVL` draws its
cell, as wide as it is, about the point retail drew the Japanese about.

On Beetle (`BOKU_EMU_TESTS=1`): a new game is switched to kite flying after its first
dialogue, once for each pack, and every opaque texel of the three cells is on screen where
its record puts it. The stock image fails it: the Japanese is there.
"""

from __future__ import annotations

import dataclasses
import os
import struct
import subprocess
import sys

import pytest

from boku import REPO_ROOT
from boku import texture_kite as tk
from boku import texture_paint as paint
from boku.png import read as read_png
from boku.texture_text import Entry, TextureTextError, family_entries, ink_of
from tests.test_real_texture_buttons import assert_edged, check_texels, mode, rebuilt
from tests.test_real_texture_text_beetle import FIELD

ENTRIES = family_entries(tk.FAMILY)
VIEWS = dict(zip(tk.LABELS, tk.VIEWS[f"{tk.FAMILY}hud"], strict=True))


def sheet(inv, patched: bytes, atlas: str) -> paint.Canvas:
    return rebuilt(inv, patched, dataclasses.replace(VIEWS["direction"], texture=atlas))


def lit(canvas: paint.Canvas, box: paint.Box) -> paint.Ink:
    """The texels of `box` a sprite would draw: those not transparent."""
    palette = canvas.palette(tk.CLUT, tk.CHUNK)
    return {p for p in paint.points(box) if palette[canvas.at(p)][3]}


@pytest.mark.parametrize("atlas", tk.ATLASES)
@pytest.mark.parametrize("key", sorted(tk.LABELS))
def test_a_cell_is_its_label_in_english_edged_and_centred(
    key, atlas, texture_inventory, texture_patched, game
):  # fmt: skip
    canvas = sheet(texture_inventory, texture_patched, atlas)
    palette = canvas.palette(tk.CLUT, tk.CHUNK)
    cell = tk.LABELS[key].cell
    ink = paint.normalised(ink_of(game, ENTRIES[f"hud.{key}"]))
    assert_edged(canvas, palette, lit(canvas, cell), cell, ink, f"the {key} label")


@pytest.mark.parametrize("atlas", tk.ATLASES)
def test_the_sheet_shows_no_japanese_and_is_otherwise_as_it_was(
    atlas, texture_inventory, texture_patched
):  # fmt: skip
    """Outside the cells nothing of the retail strip is left, and no other texel of the sheet
    changed -- the digits, the units, the compass and the reels."""
    canvas = sheet(texture_inventory, texture_patched, atlas)
    stock = paint.Canvas(texture_inventory.get(atlas), drawn_4bpp=True)
    cells = {p for label in tk.LABELS.values() for p in paint.points(label.cell)}
    strip = set(paint.points(tk.STRIP))
    assert len(lit(stock, tk.STRIP)) > 200, "the stock strip's lettering is not where measured"
    assert lit(canvas, tk.STRIP) - cells == set(), "lettering left outside the cells"
    every = paint.points((0, 0, canvas.width, canvas.height))
    changed = {p for p in every if canvas.at(p) != stock.at(p)}
    assert changed <= cells | strip, f"changed elsewhere: {sorted(changed - cells - strip)[:5]}"


def test_each_record_draws_its_cell_about_the_point_retail_drew_the_japanese(
    archive, texture_patched
):  # fmt: skip
    for key, label in tk.LABELS.items():
        at = archive.overlay_offset(tk.OVERLAY, label.record)
        flag, x, y, u, v, w, h = struct.unpack_from(tk.RECORD, texture_patched, at)
        was_flag, was_x, was_y, _, _, was_w, _ = struct.unpack_from(tk.RECORD, archive.boku, at)
        cx, cy, cw, ch = label.cell
        assert (u, v, w, h) == (cx - tk.PAGE_X, cy, cw, ch), f"{key}: not its cell"
        assert (flag, y) == (was_flag, was_y), f"{key}: moved off its row"
        assert 2 * x + w == 2 * was_x + was_w, f"{key}: not centred where the Japanese was"


def test_a_label_too_wide_for_its_cell_is_refused_not_cut(archive, texture_inventory, game):
    text = dict(ENTRIES)
    text["hud.direction"] = Entry("kite@hud.direction", "Wind direction", "t:1")
    with pytest.raises(TextureTextError, match="nothing is cut to fit"):
        tk.kite(archive, texture_inventory, game, list(text.values()))


def test_a_hud_missing_a_label_is_refused(archive, texture_inventory, game):
    given = [e for key, e in ENTRIES.items() if key != "hud.speed"]
    with pytest.raises(TextureTextError, match="kite@hud takes exactly"):
        tk.kite(archive, texture_inventory, game, given)


# --- on Beetle -----------------------------------------------------------------------------

KITE_FLYING = 6
"""`TAKO`'s mode (`research/loading-and-memory.md` § "Modes and the three arena levels")."""
LEVEL_B = "f43d1b80"
"""Its arena's base on an image with no code of ours, as `run_core.py --poke` takes it."""
SHOT = FIELD.MODE_SET_AT + 350
"""The kite is up and the HUD drawn (measured: by 300 frames after the mode is set)."""
HOUR, AFTERNOON = 0x80028FC1, 15
"""The hour `TAKO.OVL` picks its pack by, and from which it loads the second, `tk.ATLASES[1]`
(`research/texture-recipes.md` § "The kite-flying HUD"); a new game's first dialogue is at 14."""
PANEL, PANEL_CLUT = (10, 20, 80, 160), 1
"""Part of the panel Boku stands in, left of the sky: the pack's own picture, the left of its
sheet read at 8bpp, drawn at the screen's corner. Boku and the line cover about a tenth."""


def panel_shown(shot, inv, atlas: str) -> float:
    """How much of `PANEL` on screen is `atlas`'s picture: which pack the flight loaded."""
    tim = inv.get(atlas).tim
    indices, palette = tim.indices(), tim.palette_rgba(PANEL_CLUT)
    same = 0
    for x, y in paint.points(PANEL):
        at = (y * shot.width + x) * 4
        want = tuple(c >> 3 << 3 for c in palette[indices[y * tim.width + x]][:3])
        same += tuple(shot.rgba[at : at + 3]) == want
    return same / (PANEL[2] * PANEL[3])


@pytest.mark.skipif(os.environ.get("BOKU_EMU_TESTS") != "1", reason="set BOKU_EMU_TESTS=1")
@pytest.mark.parametrize("hour", [AFTERNOON - 1, AFTERNOON], ids=["day", "afternoon"])
def test_kite_flying_on_beetle_shows_the_three_labels_in_english(
    hour, texture_image, texture_inventory, texture_patched, tmp_path
):  # fmt: skip
    """Once over each pack, the day's and the afternoon's: the hour is set as the mode is, and
    the panel on screen must be that pack's."""
    command = [
        sys.executable, str(REPO_ROOT / "tools/libretro/run_core.py"), str(texture_image),
        "--core", os.environ["BOKU_LIBRETRO_CORE"], "--system", os.environ["BOKU_LIBRETRO_SYSTEM"],
        "--work", str(tmp_path), "--frames", str(SHOT + 10), "--shot", f"{SHOT}:kite",
        *mode(KITE_FLYING, LEVEL_B), "--poke", f"{FIELD.MODE_SET_AT}:{HOUR:#x}={hour:02x}",
    ]  # fmt: skip
    subprocess.run(command, check=True, capture_output=True, timeout=600, cwd=REPO_ROOT)
    shot = read_png((tmp_path / "kite.png").read_bytes())
    loaded, other = (tk.ATLASES[hour >= AFTERNOON], tk.ATLASES[hour < AFTERNOON])
    shown = {atlas: panel_shown(shot, texture_inventory, atlas) for atlas in tk.ATLASES}
    assert shown[loaded] > 0.8 > 0.2 > shown[other], f"hour {hour} did not load {loaded}: {shown}"
    for key, label in tk.LABELS.items():
        view = dataclasses.replace(VIEWS[key], texture=loaded)
        origin = (label.x - label.cell[0], tk.LABEL_Y - label.cell[1])
        check_texels(shot, texture_inventory, texture_patched, view, view.clut, view.chunk,
                     paint.points(label.cell), origin, f"the {key} label", at_least=40)  # fmt: skip
