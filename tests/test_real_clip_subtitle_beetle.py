"""`VO-07` on Beetle PSX: the native-clip subtitles on the paths real play takes to them.

`tests/test_real_clip_subtitle.py` proves `VO-03`'s hooks on Redux by re-entering movie mode
or entering `ENDOTI` where the opening movie hands over -- a moment no event is running.
Real play reaches both clips from an event, whose `END` leaves the event runner's "event" bit
set through the modes that follow; the hooks trusted it, so in play neither subtitle opened
(research/event-scripts.md § Native clips, "Reached as play reaches them").

The same fixture image as the Redux gate, booted on Beetle down two routes:

* **bedtime** -- a new game to the first dialogue, the diary mode entered there
  (`DIARY_MODE`, the pokes `test_real_texture_text_beetle.py` measured), then the game's own
  good-night: the day-end code, the sleep movie and `XCH.34`;
* **ending** -- a generated day-31 card with no stars, `g_flags[251]` poked to 12 so that
  `E3182` fires on the walk (`research/movies.md` § 9), then `M28`, `ENDOTI` and `XCH.45`.

`run_core.py --peek` samples the mode, the event flags, the XA status, the text page and
`ENDOTI`'s own state and counter every `STEP` frames; each gate says what it reads. The
ending is also `VO-09`'s gate: the fixture's epilogue row times its last page to go just
before the production card (`tests.test_real_clip_subtitle.epilogue_times`), and it must.

Skips without the import, armips, `BOKU_LIBRETRO_CORE`/`_SYSTEM`, the new-game base
(`./make.sh saves`), and unless `BOKU_EMU_TESTS=1`: one build and two boots are minutes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from boku import REPO_ROOT, clip_preview, clip_subs, epilogue
from boku.build import load_edit_set
from boku.lint import make_encoder
from boku.movie_block import BLOCK_RAM
from boku.png import read as read_png
from boku.save import G_FLAGS, epilogue_for, star_mask
from boku.voice import xch_nodes
from tests.test_real_clip_subtitle import (
    BEDTIME,
    EPILOGUES,
    FIXTURE,
    PLAYING,
    SLACK,
    VSYNCS_PER_TICK,
    build_fixture_image,
)
from tests.test_real_save_boot import BASE
from tests.test_real_texture_text_beetle import DIARY_MODE, DIARY_PRESSES, RUNNER

WORK = REPO_ROOT / "work" / "vo07"
DIALOGUE_PRESSES = REPO_ROOT / "tools" / "libretro" / "boot-to-dialogue.press"
SAVE_PRESSES = REPO_ROOT / "tools" / "libretro" / "boot-to-save.press"
STEP = VSYNCS_PER_TICK
"""Frames between samples: one page-timer tick."""
MOVIE_MODE, ENDOTI_MODE, DIARY = 0x0E, 0x10, 0x0B
EVENT_RUNNING = 1
"""Bit 0 of the event runner's flags (research/event-scripts.md § Native clips)."""
PEEKS = {
    "mode": (0x800237E0, 1),
    "prev": (0x800237E5, 1),
    "events": (0x8003637C, 4),
    "busy": (0x800359D8, 4),
    "page": (0x800359EC, 4),
    "flags": (0x800359E4, 4),
    "panel": (0x8002911E, 1),
    "state": (epilogue.STATE, 1),
    "count": (epilogue.COUNTER, 4),
}
"""The game mode, the mode before it, the event runner's flags, the XA status word,
`g_text_page` / `g_text_flags` and `g_dlgbox_visible` (research/event-scripts.md § Native
clips; the same words `tools/redux/clip-sub.lua` prints); and, meaningful in `ENDOTI` only,
its state and its counter (§ The epilogue's clock)."""

BEDTIME_ROUTE = {
    "press_file": DIALOGUE_PRESSES,
    "frames": 9600,
    "peek_from": 7400,
    "extra": [
        *[arg for poke in DIARY_MODE for arg in ("--poke", poke)],
        # tonight's page, then close it: the day ends
        *[f"--press={f}:{b}" for f, b in [*DIARY_PRESSES, (8000, "CIRCLE")]],
    ],
}
ENDING_STARS = star_mask(0)
ENDING_CLIP = EPILOGUES[0] + epilogue_for(ENDING_STARS)
FLAG_251 = f"11450:{G_FLAGS + 251:#x}=0c"
"""`E3182`'s condition, poked after the day-31 morning has reset it (research/movies.md § 9)."""
SHOT_EVERY, SHOTS_FROM = 40, 29000
"""The ending is shot this often from a little before `ENDOTI` (measured: its subtitle opens
at 29614), for the gate on the reader's pictures."""
ENDING_ROUTE = {
    "press_file": SAVE_PRESSES,
    "frames": 34000,
    "peek_from": 26000,
    "extra": ["--poke", FLAG_251, "--shot-every", str(SHOT_EVERY), "--shot-from", str(SHOTS_FROM)],
}

pytestmark = pytest.mark.skipif(
    os.environ.get("BOKU_EMU_TESTS") != "1", reason="emulator boots: set BOKU_EMU_TESTS=1"
)


@pytest.fixture(scope="module")
def image(real_image: Path, disc_dir: Path) -> Path:
    for var in ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM"):
        if not os.environ.get(var):
            pytest.skip(f"{var} is not set (research/tooling-setup.md § Beetle PSX, headless)")
    return build_fixture_image(real_image, disc_dir)


@pytest.fixture(scope="module")
def block_range(image: Path) -> range:
    edits = json.loads((FIXTURE / "vwf" / "edits.json").read_text(encoding="utf-8"))
    return range(BLOCK_RAM, BLOCK_RAM + edits["movie_subtitles"]["bytes"])


def boot(image: Path, name: str, route: dict, *extra: str) -> list[dict[str, int]]:
    work = WORK / name
    peeks = [f"--peek={addr:08X}:{n}" for addr, n in PEEKS.values()]
    done = subprocess.run(
        [sys.executable, str(RUNNER), str(image), "--work", str(work), "--quiet",
         "--frames", str(route["frames"]), "--press-file", str(route["press_file"]),
         *peeks, "--peek-every", str(STEP), "--peek-from", str(route["peek_from"]),
         *route["extra"], *extra],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=1800,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    rows = []
    for line in (work / "peek.tsv").read_text(encoding="ascii").splitlines():
        frame, *cols = line.split("\t")
        row = {
            k: int.from_bytes(bytes.fromhex(c), "little") for k, c in zip(PEEKS, cols, strict=True)
        }
        rows.append({"frame": int(frame), **row})
    return rows


@pytest.fixture(scope="module")
def bedtime(image: Path) -> list[dict[str, int]]:
    return boot(image, "bedtime", BEDTIME_ROUTE)


@pytest.fixture(scope="module")
def ending(image: Path, disc_dir: Path) -> list[dict[str, int]]:
    if not BASE.is_file():
        pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")
    card = WORK / "ending.mcd"
    made = subprocess.run(
        [sys.executable, "-m", "boku", "save", "--base", str(BASE), "--day", "31",
         "--stars-mask", str(ENDING_STARS), "--out", str(card), "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )  # fmt: skip
    assert made.returncode == 0, made.stdout + made.stderr
    return boot(image, "ending", ENDING_ROUTE, "--memcard", str(card))


@pytest.fixture(scope="module")
def lines(image: Path, archive) -> dict[int, clip_subs.ClipLine]:
    """The fixture's rows as the build laid them out: when each page is up."""
    entries, problems = clip_subs.read(FIXTURE / "clips.txt")
    encoder = make_encoder("cellmap", FIXTURE / "vwf" / "edits.json")
    laid, found = clip_subs.lay_out_lines(
        entries, xch_nodes(archive), encoder, epilogue.pictures(archive)
    )
    assert problems == [] and found == []
    return {line.index: line for line in laid}


def clip_rows(rows, mode: int) -> list[dict[str, int]]:
    """The samples in `mode` while the XA status says a clip plays."""
    return [r for r in rows if r["mode"] == mode and r["busy"] & PLAYING]


def check_subtitle(rows, mode: int, line: clip_subs.ClipLine, block: range) -> None:
    clip = line.index
    playing = clip_rows(rows, mode)
    assert playing, f"no clip played in mode {mode:#x}: the route went elsewhere"
    assert all(r["events"] & EVENT_RUNNING for r in playing), (
        "the event flag was clear: this route no longer reaches the clip the way play does"
    )
    opened = [r for r in playing if r["page"] in block]
    assert opened, (
        f"XCH.{clip} played for {len(playing) * STEP} frames with no subtitle "
        f"(g_text_page {playing[0]['page']:#x} throughout)"
    )
    first = opened[0]["frame"]
    turned = next((r["frame"] for r in opened if r["page"] != opened[0]["page"]), None)
    assert turned is not None, f"XCH.{clip}'s subtitle opened at {first} and never turned a page"
    want = first + line.pages[0].end
    assert abs(turned - want) <= STEP + SLACK, (
        f"page 2 at frame {turned}, predicted {want} from the page's 30 Hz timer"
    )
    after = next((r for r in rows if r["frame"] > playing[-1]["frame"] and r["mode"] != mode), None)
    assert after is not None, f"the run ended still in mode {mode:#x}: lengthen the route"
    assert after["page"] == 0, "the subtitle outlived its clip's mode"


def test_the_bedtime_subtitle_opens_after_the_diary_in_play(bedtime, block_range, lines):
    came = [r for r in clip_rows(bedtime, MOVIE_MODE) if r["prev"] == DIARY]
    assert came, "movie mode was not entered from the diary"
    check_subtitle(bedtime, MOVIE_MODE, lines[BEDTIME], block_range)


def test_the_epilogue_subtitle_opens_after_the_ending_in_play(ending, block_range, lines):
    check_subtitle(ending, ENDOTI_MODE, lines[ENDING_CLIP], block_range)


def test_the_epilogue_subtitle_is_gone_before_the_still_gives_way(ending, block_range, lines):
    """`VO-09`: the last page has a time of its own, a little before the production card.
    The card comes when `ENDOTI`'s counter reaches the threshold the layout read from the
    disc, the counter reads `OPENS_AT` as the subtitle opens, and text and band are both
    gone -- on the vsync the layout says -- while the second still is up."""
    line = lines[ENDING_CLIP]
    rows = [r for r in ending if r["mode"] == ENDOTI_MODE]
    up = [r for r in rows if r["page"] in block_range]
    first = up[0]
    assert 0 <= first["count"] - epilogue.OPENS_AT < STEP, first
    shown = epilogue.SHOWN_IN_STATE
    card = next(r for r in rows if shown.get(r["state"]) == epilogue.CARD)
    assert 0 <= card["count"] - (line.picture.card + epilogue.OPENS_AT) < STEP, card
    down = next(r for r in rows if r["frame"] > first["frame"] and r["page"] not in block_range)
    want = first["frame"] + line.pages[-1].end
    assert abs(down["frame"] - want) <= STEP + SLACK, (
        f"the subtitle came down at frame {down['frame']}, predicted {want}"
    )
    assert line.pages[-1].end < line.picture.card, "the fixture's row is not timed before the card"
    assert shown[down["state"]] == epilogue.SECOND_STILL and down["frame"] < card["frame"]
    assert down["panel"] == 0, "the band stayed up over the still with no text in it"
    assert all(r["page"] not in block_range for r in rows if r["frame"] >= down["frame"])
    assert any(r["busy"] & PLAYING for r in rows if r["frame"] > card["frame"]), (
        "the clip had stopped by the card: the subtitle may have gone with it, not on its time"
    )


def five_bits(rgb: bytes) -> bytes:
    """The console's 15-bit colour of each pixel: the emulator and `boku.tim` both widen a
    channel's 5 bits to 8, not the same way."""
    return bytes(value >> 3 for value in rgb)


def test_the_readers_picture_of_an_epilogue_page_is_the_frame_beetle_drew(
    ending, block_range, lines, archive
):
    """`VO-09`: the reader draws each page of an epilogue over its still without an emulator
    (`boku.clip_preview`). Every shot of the run that falls inside a page, clear of a fade,
    is the same picture drawn from the import, the fixture's edit set and the page's lines:
    every pixel, in the console's 15 bits -- over both stills, and both pages."""
    edit_set = load_edit_set(FIXTURE / "vwf" / "edits.json")
    font, band = clip_preview.built_font(archive, edit_set), clip_preview.Band.of(edit_set)
    line = lines[ENDING_CLIP]
    first = next(r for r in ending if r["mode"] == ENDOTI_MODE and r["page"] in block_range)
    settle = epilogue.FADE + SLACK
    seen = set()
    for shot in sorted((WORK / "ending").glob("frame-*.png")):
        at = int(shot.stem.split("-")[1]) - first["frame"]
        page = next((p for p in line.pages if p.start + SLACK <= at < p.end - SLACK), None)
        phase = next(
            (
                name
                for name, start, end in line.picture.phases
                if start + settle <= at < end - settle
            ),
            None,
        )
        if page is None or phase not in (epilogue.FIRST_STILL, epilogue.SECOND_STILL):
            continue
        canvas = clip_preview.backdrop(archive, line.picture, at, None)
        clip_preview.draw_subtitle(canvas, page.lines, edit_set.encoder, font, band)
        drawn = read_png(shot.read_bytes()).rgba
        rgb = bytes(b for at4 in range(0, len(drawn), 4) for b in drawn[at4 : at4 + 3])
        got, want = five_bits(rgb), five_bits(bytes(canvas))
        differing = sum(1 for a, b in zip(got, want, strict=True) if a != b)
        assert differing == 0, f"{shot.name}: {differing} channel values differ over {phase}"
        seen.add((line.pages.index(page), phase))
    assert {page for page, _ in seen} == set(range(len(line.pages))), seen
    assert {phase for _, phase in seen} == {epilogue.FIRST_STILL, epilogue.SECOND_STILL}, seen
