"""`GFX-07` on Beetle PSX: what the player sees is the English the build typeset.

One image carrying only the texture edits (`boku.texture_text.build_edits`) is built per
module and booted on the core Mode One runs (`tools/libretro/run_core.py`). Each test drives
it to a screen and compares the screenshot with the rebuilt texture: every texel the build
changed that is still opaque -- the English and the ground painted in round it -- must show
its CLUT colour exactly (Beetle draws the 5-bit channels shifted left by three), and there
must be enough of them that the English was really drawn. Texels the build did not change
are not compared, and neither are texels it made transparent. A stock image fails: the
Japanese is on screen where the English texture says otherwise.

Where a sprite lands on screen and through which CLUT it is drawn were measured on the stock
image (`research/texture-recipes.md`); the screen x, y of each sprite is read from its record
in `TITLE.OVL`, not typed here.

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
SETTINGS = [
    (3300, "START"), (3700, "DOWN"), (3760, "DOWN"), (3820, "DOWN"), (3900, "CIRCLE"),
    (4200, "CIRCLE"), (4300, "DOWN"),
]  # fmt: skip
"""START at 3300 fades the title menu in by ~3600 (`tools/libretro/boot-to-dialogue.press`);
DOWN x3 and CIRCLE open Settings, then CIRCLE flips the message mode to voice only and
DOWN moves to the sound row (stereo selected). Measured on the stock image."""
MESSAGE_PLATE_RECORD = 0x800819D0
"""The message plate's sprite record: u, v (0, 16) is child 1's (0, 0)."""
SOUND_PLATE_RECORD = 0x800819BA
VALUE_RECORDS = {"voice_only": 0x80081A12, "stereo": 0x80081A28}


@pytest.fixture(scope="module")
def beetle() -> tuple[str, str]:
    if os.environ.get("BOKU_EMU_TESTS") != "1":
        pytest.skip("set BOKU_EMU_TESTS=1: an image build and a Beetle boot")
    core, system = os.environ.get("BOKU_LIBRETRO_CORE"), os.environ.get("BOKU_LIBRETRO_SYSTEM")
    if not core or not system or not Path(core).is_file():
        pytest.skip("set BOKU_LIBRETRO_CORE and BOKU_LIBRETRO_SYSTEM (research/tooling-setup.md)")
    return core, system


SHOTS = {"title": 3650, "message": 4250, "sound": 4400}
"""One boot, three screens: the title menu is shot before the first settings press."""


@pytest.fixture(scope="module")
def shots(beetle, texture_edits, real_image, disc_dir, tmp_path_factory) -> dict:
    """Build an image carrying only the texture edits, boot it once, shoot every screen."""
    out = build(
        source=real_image, out_dir=tmp_path_factory.mktemp("image"), disc_dir=disc_dir,
        binary_patches=texture_edits.edits, name="gfx07",
    )  # fmt: skip
    assert out.written is not None
    core, system = beetle
    work = tmp_path_factory.mktemp("beetle")
    args = [
        sys.executable, str(RUNNER), str(out.written.image.with_suffix(".cue")),
        "--core", core, "--system", system, "--work", str(work),
        "--frames", str(max(SHOTS.values())),
    ]  # fmt: skip
    for at, button in SETTINGS:
        args += ["--press", f"{at}:{button}"]
    for name, frame in SHOTS.items():
        args += ["--shot", f"{frame}:{name}"]
    subprocess.run(args, check=True, capture_output=True, timeout=600)
    return {name: read_png((work / f"{name}.png").read_bytes()) for name in SHOTS}


def compare(shot, inv, blob: bytes, texture_id: str, clut: int, box, at, *, skip=()):
    """Texels of `box` drawn at screen `at` through `clut`, against the screenshot, counting
    only the texels the build changed from `stock` -- so an image the English never reached
    compares nothing and fails the caller's count, rather than matching itself. `skip` is
    screen rectangles another sprite is drawn over."""
    stock = inv.get(texture_id)
    tim = parse_exact(blob, stock.occurrences[0].file_offset)
    indices, palette = tim.indices(), tim.palette_rgba(clut)
    original = stock.tim.indices()
    rgba = shot.rgba
    compared, wrong = 0, []
    for y in range(box[3]):
        for x in range(box[2]):
            at_texel = (box[1] + y) * tim.width + box[0] + x
            colour = palette[indices[at_texel]]
            sx, sy = at[0] + x, at[1] + y
            if indices[at_texel] == original[at_texel] or any(
                r[0] <= sx < r[0] + r[2] and r[1] <= sy < r[1] + r[3] for r in skip
            ):
                continue
            if not colour[3]:
                continue  # erased to transparent: what shows there is another sprite
            seen = tuple(rgba[(sy * shot.width + sx) * 4 : (sy * shot.width + sx) * 4 + 3])
            compared += 1
            if seen != tuple(c >> 3 << 3 for c in colour[:3]):
                wrong.append((x, y, seen))
    return compared, wrong


def record(archive, ram: int) -> tuple[int, int, int, int]:
    """x, y, w, h of a `TITLE.OVL` sprite record."""
    x, y, _, _, w, h = struct.unpack_from(
        "<HHBBHH", archive.boku, archive.overlay_offset(tt.TITLE_OVERLAY, ram) + 2
    )
    return x, y, w, h


def test_the_title_menu_on_beetle_is_the_typeset_english(
    shots, archive, texture_inventory, texture_patched
):
    total, wrong = 0, []
    for line, ram in enumerate(tt.TITLE_MENU_RECORDS):
        if line == 0:
            continue  # the cursor's line pulses
        box = (0, tt.MENU_BAND * line, tt.MENU_WIDTH, tt.MENU_BAND)
        n, bad = compare(
            shots["title"], texture_inventory, texture_patched, tt.TITLE_ATLAS, 0, box,
            record(archive, ram)[:2],
        )  # fmt: skip
        total, wrong = total + n, wrong + bad
    assert total > 300, "the build changed too few texels where the check looked"
    assert wrong == [], f"{len(wrong)} of {total} texels differ, first {wrong[:5]}"


@pytest.mark.parametrize(
    ("screen", "plate", "plate_record", "texture", "clut", "value"),
    [
        ("message", tt.MESSAGE_PLATE, MESSAGE_PLATE_RECORD, tt.CONFIG_PLATES, tt.MESSAGE_CLUT,
         "voice_only"),
        ("sound", tt.SOUND_PLATE, SOUND_PLATE_RECORD, tt.CONFIG_FRAME, tt.SOUND_CLUT, "stereo"),
    ],
    ids=["message", "sound"],
)  # fmt: skip
def test_the_settings_screen_on_beetle_is_the_typeset_english(
    shots, archive, texture_inventory, texture_patched, screen, plate, plate_record, texture,
    clut, value,
):  # fmt: skip
    shot = shots[screen]
    label = record(archive, VALUE_RECORDS[value])
    n, wrong = compare(
        shot, texture_inventory, texture_patched, texture, clut, plate,
        record(archive, plate_record)[:2], skip=[label],
    )  # fmt: skip
    m, wrong_label = compare(
        shot, texture_inventory, texture_patched, tt.CONFIG_PLATES, tt.VALUE_CLUT,
        tt.VALUE_LABELS[value], label[:2],
    )  # fmt: skip
    assert n > 100 and m > 100, "the build changed too few texels where the check looked"
    assert wrong == [], f"plate: {len(wrong)} of {n} texels differ, first {wrong[:5]}"
    assert wrong_label == [], f"label: {len(wrong_label)} of {m} differ, first {wrong_label[:5]}"
