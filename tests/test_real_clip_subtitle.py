"""`VO-03` on headless PCSX-Redux: subtitles on the clips native code plays (`g_xa_clips`).

A fixture `translation/clips.txt` gives English to `XCH.34` (the day-1 bedtime clip) and
`XCH.41`-`.45` (the epilogues); `tools/vwf/build_prototype.py --edits-only --clip-subs`
carries it in the movie-subtitle block and `boku build --vwf` writes the image. Then
`tools/redux/clip-sub.lua` boots it twice, down the two routes it documents, and prints the
subtitle's state from the clip on. What each gate asks is on the gate; the pixel gate is the
one harm a state line cannot show -- a last page left on the screen after the clip.

Skips without the import, armips, PCSX-Redux and the BIOS, and unless `BOKU_EMU_TESTS=1`:
two builds and two boots are minutes.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.build import main_build
from boku.movie_block import BLOCK_RAM, MAGIC
from boku.translation import SampleScenes
from boku.voice import TICK_HZ, sector_ticks, subtitle_waits, xch_nodes
from tests.test_real_movie_subtitle import ARMIPS, BIOS, PROTOTYPE, REDUX, REDUX_TIMEOUT, RUNNER
from tests.test_vwf_prototype import vwf_layout

WORK = REPO_ROOT / "work" / "vo03"
FIXTURE = REPO_ROOT / "work" / "clip-fixture"
"""The fixture build, shared with `tests/test_real_clip_subtitle_beetle.py`."""
SCRIPT = REPO_ROOT / "tools" / "redux" / "clip-sub.lua"
BEDTIME = 34
EPILOGUES = range(41, 46)
PAGES = {
    BEDTIME: ("VO-03 fixture: bedtime, page one of the first night.", "Page two, over black."),
    **{n: (f"VO-03 fixture: epilogue XCH.{n}, page one.", "Page two.") for n in EPILOGUES},
}
ENDING = 0
VSYNCS_PER_TICK = 60 // TICK_HZ
SLACK = 4
"""Vsyncs a transition may land either side of its prediction."""
READ_BUDGET = 30
"""Vsyncs the block's re-read may hold the epilogue back: half a second (measured: 16)."""
_LAYOUT = vwf_layout()
BAND_ROWS = range(_LAYOUT.band_y, _LAYOUT.band_y + _LAYOUT.band_h)
"""The band's rows, from the geometry the build assembles the renderer with."""

pytestmark = pytest.mark.skipif(
    os.environ.get("BOKU_EMU_TESTS") != "1", reason="emulator boots: set BOKU_EMU_TESTS=1"
)


@functools.cache
def build_fixture_image(real_image: Path, disc_dir: Path) -> Path:
    """`PAGES` as a fixture `clips.txt`, carried by the font build into `FIXTURE/vwf` and
    written by `boku build --vwf` into `FIXTURE/image`; the `.cue` it wrote. Built once per
    session, whichever emulator's gate asks first."""
    work = FIXTURE
    if not ARMIPS.exists():
        pytest.skip(f"no {ARMIPS}: the font build assembles with armips")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    clips = work / "clips.txt"
    clips.write_text(
        "".join(
            f"XCH.{n:02d}\tNarrator\t{SampleScenes.PAGE_BREAK.join(p)}\n" for n, p in PAGES.items()
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            str(PROTOTYPE),
            "--edits-only",
            "--clip-subs",
            str(clips),
            "--out",
            str(work / "vwf"),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        timeout=600,
    )
    status = main_build(
        str(real_image),
        work / "image",
        None,
        None,
        disc_dir,
        "clip-fixture",
        False,
        False,
        vwf=work / "vwf" / "edits.json",
    )
    assert status == 0, "boku build --vwf refused the fixture's edit set"
    return work / "image" / "image.cue"


@pytest.fixture(scope="module")
def image(real_image: Path, disc_dir: Path) -> Path:
    for path, what in [
        (REDUX / "Contents" / "MacOS" / "PCSX-Redux", "set REDUX_APP"),
        (BIOS, "set REDUX_BIOS"),
    ]:
        if not path.exists():
            pytest.skip(f"no {path}: {what}")
    return build_fixture_image(real_image, disc_dir)


def boot(cue: Path, route: str, **env: str) -> str:
    edits = json.loads((FIXTURE / "vwf" / "edits.json").read_text(encoding="utf-8"))
    (sector,) = edits["sectors"]
    env = {
        "BOKU_BLOCK_BYTES": str(len(bytes.fromhex(sector["new"]))),
        "BOKU_BLOCK_RAM": str(BLOCK_RAM),
    } | env
    done = subprocess.run(
        [str(RUNNER), str(cue), str(SCRIPT)],
        env=os.environ
        | {"BOKU_WORK": str(WORK / route), "BOKU_ROUTE": route, "REDUX_TIMEOUT": REDUX_TIMEOUT}
        | env,
        capture_output=True,
        text=True,
        timeout=1200,
    )
    (WORK / f"{route}.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    assert "EXIT 0" in done.stdout, f"the probe did not finish; see {WORK / route}.log"
    return done.stdout


def block_changes(log: str) -> list[int]:
    """The vsyncs at which the block's bytes changed (the first is the first look) while
    the clip's game mode lasted."""
    return [int(m[1]) for m in re.finditer(r"^BLOCK f=(\d+)", log, re.M)]


def parse(log: str) -> tuple[int, int, int, list[tuple[int, dict[str, int]]]]:
    """(vsync, clip index, block magic at the clip, [(vsync, state)])."""
    clip = re.search(r"^CLIP f=(\d+) clip=(\d+) magic=([0-9a-f]+)", log, re.M)
    states = [
        (int(m[1]), {k: int(v, 16) for k, v in re.findall(r"(\w+)=([0-9a-f]+)", m[2])})
        for m in re.finditer(r"^STATE f=(\d+) (.*)$", log, re.M)
    ]
    return int(clip[1]), int(clip[2]), int(clip[3], 16), states


def band_ink(raw: bytes) -> int:
    """Non-black pixels in the band's rows of a `lib.lua` shot (16-bit)."""
    width, height, bpp, _ = struct.unpack_from("<HHHH", raw, 8)
    assert bpp == 16, "the bedtime screen is 16-bit"
    words = struct.unpack_from(f"<{width * height}H", raw, 16)
    return sum(1 for y in BAND_ROWS for x in range(width) if words[y * width + x] & 0x7FFF)


# --- bedtime: movie mode's wait loop ---------------------------------------------------------


@pytest.fixture(scope="module")
def bedtime_log(image: Path) -> str:
    return boot(image, "bedtime", BOKU_SHOTS="2")


@pytest.fixture(scope="module")
def bedtime(bedtime_log: str) -> tuple[int, int, int, list]:
    return parse(bedtime_log)


def test_bedtime_plays_xch34_with_the_block_the_sleep_movie_left_in_memory(bedtime):
    _, clip, magic, _ = bedtime
    assert clip == BEDTIME
    assert magic == MAGIC, f"no block at 0x{BLOCK_RAM:08X} when the clip started"


def test_bedtime_opens_the_subtitle_in_the_band_and_turns_it_on_the_clips_timer(bedtime, archive):
    started, _, _, states = bedtime
    at, first = states[0]
    assert at - started <= SLACK
    assert first["page"] and first["panel"] == 1 and first["flags"] & 3 == 1
    turned = next(f for f, s in states if s["page"] and s["flags"] & 3 == 2)
    wait = subtitle_waits(PAGES[BEDTIME], sector_ticks(xch_nodes(archive)[BEDTIME].sectors))[0]
    assert abs(turned - (started + VSYNCS_PER_TICK * (wait + 1))) <= SLACK


def test_bedtime_leaves_no_last_page_on_the_screen_after_the_clip(bedtime):
    """The wait loop ends with its clip; the next mode takes a second to draw anything, and
    until `clip_sub_done` flipped an empty frame the last page stayed up through it."""
    _, _, _, states = bedtime
    stopped = next(f for f, s in states if not s["busy"] & 5)
    shots = sorted((WORK / "bedtime" / "shots").glob("bedtime-*.raw"))
    during = [s for s in shots if stopped - 40 <= int(s.stem.split("-")[1]) <= stopped - 10]
    after = [s for s in shots if stopped + 6 <= int(s.stem.split("-")[1]) <= stopped + 30]
    assert during and band_ink(during[0].read_bytes()) > 0, "no subtitle to see go"
    down = next(s for f, s in states if f >= stopped)
    assert down["level"] == 0, "the next panel draw would fade a band out of nothing"
    assert after and all(band_ink(s.read_bytes()) == 0 for s in after)


# --- the ending: ENDOTI -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def ending_log(image: Path) -> str:
    return boot(image, "ending", BOKU_ENDING=str(ENDING))


@pytest.fixture(scope="module")
def ending(ending_log: str) -> tuple[int, int, int, list]:
    return parse(ending_log)


@pytest.mark.parametrize("route", ["bedtime", "ending"])
def test_the_whole_block_stays_as_read_while_its_subtitle_reads_from_it(route, request):
    """The subtitle's words are read from the block every frame it is up, and the block is
    only checked by its first word: every byte of it is compared each frame of the clip's
    mode, and from the frame the subtitle opens it must not change."""
    log = request.getfixturevalue(f"{route}_log")
    changes = block_changes(log)
    assert changes, "the probe compared nothing: BOKU_BLOCK_BYTES did not reach it"
    opened = next(f for f, s in parse(log)[3] if s["page"])
    assert [f for f in changes if f > opened] == [], changes


def test_endoti_writes_over_the_block_and_the_clip_reads_it_again(ending):
    started, clip, magic, states = ending
    assert clip == EPILOGUES[0] + ENDING
    assert magic != MAGIC, "ENDOTI did not write over the block: the re-read is untested"
    # The read comes before xa_play, so the voice waits for it too: text and voice start on
    # the same frame, a fraction of a second after ENDOTI asked for the clip.
    at, first = next((f, s) for f, s in states if s["busy"] & 5)
    assert first["page"] and first["panel"] == 1, "the voice started without its subtitle"
    assert at - started <= READ_BUDGET


def test_the_epilogue_subtitle_comes_down_when_endoti_hands_over(ending):
    """The save prompt reuses the block's memory: a subtitle left up would draw garbage."""
    _, _, _, states = ending
    assert any(s["flags"] & 3 == 2 and s["page"] for _, s in states), "page 2 never came"
    handed = next(s for _, s in states if s["mode"] != 0x10)
    assert handed["page"] == 0 and handed["panel"] == 0
    assert handed["level"] == 0, "the next panel draw would fade a band out of nothing"
