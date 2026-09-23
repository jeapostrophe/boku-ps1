"""`GFX-07` on Beetle PSX: the title menu the player sees is the English the build typeset.

An image carrying only the texture edits (`boku.texture_text.build_edits`) is booted to the
title menu on the core Mode One runs (`tools/libretro/run_core.py`), and the screenshot is
compared texel for texel with the rebuilt atlas: every opaque texel of the three lines the
cursor is not on must show its CLUT-0 colour exactly (Beetle draws the 5-bit channels
shifted left by three). A stock image, or an image whose sprites were not widened, fails it
-- the Japanese or the clipped English is on screen where the English atlas says otherwise.
The cursor's line pulses, so it is not compared.

Skips without the import, without the core and BIOS, and unless `BOKU_EMU_TESTS=1`.
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku import texture_text as tt
from boku.build import build
from boku.png import read as read_png
from boku.tim import parse_exact

RUNNER = REPO_ROOT / "tools/libretro/run_core.py"
START_AT, SHOOT_AT = 3300, 3650
"""`tools/libretro/boot-to-dialogue.press`: START at 3300 fades the menu in by ~3600."""
CURSOR_LINE = 0


@pytest.fixture(scope="module")
def beetle() -> tuple[str, str]:
    if os.environ.get("BOKU_EMU_TESTS") != "1":
        pytest.skip("set BOKU_EMU_TESTS=1: an image build and a Beetle boot")
    core, system = os.environ.get("BOKU_LIBRETRO_CORE"), os.environ.get("BOKU_LIBRETRO_SYSTEM")
    if not core or not system or not Path(core).is_file():
        pytest.skip("set BOKU_LIBRETRO_CORE and BOKU_LIBRETRO_SYSTEM (research/tooling-setup.md)")
    return core, system


def test_the_title_menu_on_beetle_is_the_typeset_english(
    beetle, archive, texture_inventory, real_image, disc_dir, tmp_path
):
    core, system = beetle
    inv = texture_inventory
    edits = tt.build_edits(archive, inv=inv).edits
    out = build(
        source=real_image, out_dir=tmp_path / "image", disc_dir=disc_dir,
        binary_patches=edits, name="gfx07",
    )  # fmt: skip
    assert out.written is not None
    subprocess.run(
        [
            sys.executable, str(RUNNER), str(out.written.image.with_suffix(".cue")),
            "--core", core, "--system", system, "--work", str(tmp_path / "beetle"),
            "--frames", str(SHOOT_AT), "--press", f"{START_AT}:START",
            "--shot", f"{SHOOT_AT}:menu",
        ],
        check=True, capture_output=True, timeout=600,
    )  # fmt: skip
    shot = read_png((tmp_path / "beetle" / "menu.png").read_bytes())
    rgba = shot.rgba

    texture = inv.get(tt.TITLE_ATLAS)
    blob = bytearray(archive.boku)
    for edit in edits:
        blob[edit.offset : edit.offset + len(edit.new)] = edit.new
    atlas = parse_exact(bytes(blob), texture.occurrences[0].file_offset)
    indices, palette, width = atlas.indices(), atlas.palette_rgba(0), atlas.width

    # Where each line lands on screen is the record's own x and y, read from the import.
    origin = [
        struct.unpack_from("<HH", archive.boku, archive.overlay_offset(tt.TITLE_OVERLAY, r) + 2)
        for r in tt.TITLE_MENU_RECORDS
    ]

    compared, wrong = 0, []
    for line in range(tt.MENU_LINES):
        if line == CURSOR_LINE:
            continue
        for y in range(tt.MENU_BAND):
            for x in range(tt.MENU_WIDTH):
                colour = palette[indices[(tt.MENU_BAND * line + y) * width + x]]
                if colour[3] == 0:
                    continue
                sx, sy = origin[line][0] + x, origin[line][1] + y
                at = (sy * shot.width + sx) * 4
                seen = tuple(rgba[at : at + 3])
                want = tuple(c >> 3 << 3 for c in colour[:3])
                compared += 1
                if seen != want:
                    wrong.append((line, x, y, seen, want))
    assert compared > 500, "the English lines were not where the check looked"
    assert wrong == [], f"{len(wrong)} of {compared} texels differ, first {wrong[:5]}"
