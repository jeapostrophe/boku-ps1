"""`GFX-07` on Beetle PSX: what the player sees is the English the build typeset.

One image carrying only the texture edits (`boku.texture_text.build_edits`; the session's
`texture_image`, `tests/conftest.py`) is booted on the core Mode One runs
(`tools/libretro/run_core.py`). Each test drives it to a screen and compares the screenshot
with the rebuilt texture: every texel the build changed that is still opaque -- the English and
the ground painted in round it -- must show its CLUT colour exactly (Beetle draws the 5-bit
channels shifted left by three), and there must be enough of them that the English was really
drawn. Texels the build did not change are not compared, and neither are texels it made
transparent. A stock image fails: the Japanese is on screen where the English texture says
otherwise.

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
def shots(beetle, texture_image, tmp_path_factory) -> dict:
    """Build an image carrying only the texture edits, boot it once, shoot every screen."""
    core, system = beetle
    work = tmp_path_factory.mktemp("beetle")
    args = [
        sys.executable, str(RUNNER), str(texture_image),
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


BEACH_WARP = "5300:0x80036588=43313500"
"""After a new game's opening movie the game enters the map named at `g_movie_return_map`
(`0x80036588`, `research/movies.md`); poking the base `C15` into it during the movie lands day 1
on the path to the beach (`C15000`). Shot at 6390, after the map has faded in."""
BEACH_SHOT = 6390
BEACH_BOARD = (330, 20, 159, 62)
"""The board's part of the atlas that reaches the screen -- its last column, x 489, falls
just past the screen's right edge -- and where it lands: measured on the
stock image by matching every CLUT at every screen offset (`research/texture-recipes.md`
§ `M_C15`)."""
BEACH_ON_SCREEN = (161, 178)


def test_the_beach_notice_on_beetle_is_the_painted_english(
    beetle, texture_image, texture_inventory, texture_patched, disc_dir, tmp_path_factory,
):  # fmt: skip
    core, system = beetle
    work = tmp_path_factory.mktemp("beach-beetle")
    args = [
        sys.executable, str(RUNNER), str(texture_image),
        "--core", core, "--system", system, "--work", str(work),
        "--frames", str(BEACH_SHOT), "--shot", f"{BEACH_SHOT}:beach",
        "--press-file", str(REPO_ROOT / "tools/libretro/boot-to-dialogue.press"),
        "--poke", BEACH_WARP,
    ]  # fmt: skip
    subprocess.run(args, check=True, capture_output=True, timeout=600)
    shot = read_png((work / "beach.png").read_bytes())
    n, wrong = compare(
        shot, texture_inventory, texture_patched, tt.BEACH_BACKGROUNDS[0], tt.BEACH_CLUT,
        BEACH_BOARD, BEACH_ON_SCREEN,
    )  # fmt: skip
    assert n > 500, "the build changed too few texels where the check looked"
    assert wrong == [], f"{len(wrong)} of {n} texels differ, first {wrong[:5]}"


DIARY_MODE = [
    "6500:0x800237E5=05", "6500:0x800237E0=0b", "6500:0x800237E4=0b",
    "6500:0x80024728=01000000", "6500:0x800258E0=f4791180",
]  # fmt: skip
"""After the first dialogue, `mode_set(11)` done by hand (`tools/redux/book-pokes.lua`
documents the five words): the desk with the diary open, the cursor on its good-night
button. Level A's arena base is `0x801179F4` (`research/loading-and-memory.md`)."""
DIARY_PAGE_ID = 0x8004612C
"""`g_diary_today`: the page tonight opens (`research/text-outside-events.md`)."""
DIARY_PAGE = "072"
DIARY_PRESSES = [(7020, "CIRCLE"), (7320, "CIRCLE")]
"""Good night -> "write the diary and sleep?" -> yes: tonight's page opens."""
DIARY_SHOT = 7590
DIARY_ON_SCREEN = (53, 16)
"""Where the page lands (measured on this screen by matching the page's texels)."""
DIARY_TOLERANCE = 24
"""The book is lit: the page is drawn colour-modulated, a few levels off its CLUT. Every
changed texel is required within this much luminance; a texel of the wrong kind (ink where
paper is, or paper where ink is) is ~200 off."""


def test_a_diary_page_on_beetle_is_the_english_entry(
    beetle, texture_image, texture_inventory, texture_patched, disc_dir, tmp_path_factory,
):  # fmt: skip
    from boku import diary
    from boku.tim import luminance

    core, system = beetle
    work = tmp_path_factory.mktemp("diary-beetle")
    args = [
        sys.executable, str(RUNNER), str(texture_image),
        "--core", core, "--system", system, "--work", str(work),
        "--frames", str(DIARY_SHOT), "--shot", f"{DIARY_SHOT}:diary",
        "--press-file", str(REPO_ROOT / "tools/libretro/boot-to-dialogue.press"),
        "--poke", f"7000:{DIARY_PAGE_ID:#x}={int(DIARY_PAGE):02x}",
    ]  # fmt: skip
    for poke in DIARY_MODE:
        args += ["--poke", poke]
    for at, button in DIARY_PRESSES:
        args += ["--press", f"{at}:{button}"]
    subprocess.run(args, check=True, capture_output=True, timeout=600)
    shot = read_png((work / "diary.png").read_bytes())

    stock = diary.diary_pages(texture_inventory)[DIARY_PAGE]
    after = parse_exact(texture_patched, stock.occurrences[0].file_offset)
    before, now, palette = stock.tim.indices(), after.indices(), after.palette_rgba(0)
    ox, oy = DIARY_ON_SCREEN
    far = []
    changed = [i for i in range(len(now)) if now[i] != before[i]]
    for i in changed:
        x, y = i % after.width, i // after.width
        at = ((oy + y) * shot.width + ox + x) * 4
        seen = luminance(tuple(shot.rgba[at : at + 3]))
        if abs(seen - luminance(palette[now[i]])) > DIARY_TOLERANCE:
            far.append((x, y))
    assert len(changed) > 1000, "the page was not rebuilt"
    assert far == [], f"{len(far)} of {len(changed)} changed texels are off, first {far[:5]}"


ALBUM_PRESSES = [(3300, "START"), (3700, "DOWN"), (3760, "DOWN"), (3900, "CIRCLE"),
                 (4400, "CIRCLE"), (4900, "CIRCLE")]  # fmt: skip
"""Title -> Summer Memories -> the card's finished file -> "is this file all right?" -> yes:
the album opens by ~5900 (measured on Beetle with a generated finished card)."""
ALBUM_SHOT = 6200
ALBUM_HEADING_ON_SCREEN = (36, 24)
"""Where the heading plaque's box lands (measured by matching its texels; drawn exactly)."""
BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"


def test_the_album_heading_on_beetle_is_the_typeset_english(
    beetle, texture_image, texture_inventory, texture_patched, disc_dir, tmp_path_factory,
):  # fmt: skip
    """`T_MEMORY` is reached only with a finished game on the card; `boku save --finished`
    makes one (PLAN `ENV-08`)."""
    if not BASE.is_file():
        pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
    work = tmp_path_factory.mktemp("album")
    card = work / "finished.mcd"
    subprocess.run(
        [sys.executable, "-m", "boku", "save", "--base", str(BASE), "--finished",
         "--out", str(card), "--disc", str(disc_dir)],
        cwd=REPO_ROOT, check=True, capture_output=True,
    )  # fmt: skip
    core, system = beetle
    args = [
        sys.executable, str(RUNNER), str(texture_image),
        "--core", core, "--system", system, "--work", str(work), "--memcard", str(card),
        "--frames", str(ALBUM_SHOT + 10), "--shot", f"{ALBUM_SHOT}:album",
    ]  # fmt: skip
    for at, button in ALBUM_PRESSES:
        args += ["--press", f"{at}:{button}"]
    subprocess.run(args, check=True, capture_output=True, timeout=600)
    shot = read_png((work / "album.png").read_bytes())
    n, wrong = compare(
        shot, texture_inventory, texture_patched, tt.MEMORY_ALBUM, tt.MEMORY_CLUT,
        tt.MEMORY_HEADING, ALBUM_HEADING_ON_SCREEN,
    )  # fmt: skip
    assert n > 200, "the build changed too few texels where the check looked"
    assert wrong == [], f"{len(wrong)} of {n} texels differ, first {wrong[:5]}"
