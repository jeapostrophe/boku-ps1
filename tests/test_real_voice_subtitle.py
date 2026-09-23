"""`VO-02` on headless PCSX-Redux: a subtitle on a voice-only clip opens, turns, and closes.

A one-row translation puts a two-page English fixture on `E0184.2` -- the voice-only clip
in Boku's room that day 1's arrival sequence reaches with no input -- and is built through
the renderer's edit set (`build/vwf/edits.json`, or `BOKU_VWF_BUILD`), which carries
`asm/voice.asm`. `tools/redux/voice-sub.lua` boots it and prints the dialogue state from the
tick the `XA` opcode runs. The gates are what the hooks promise: the text opens that tick
with the band up, the first page turns on the timer the build derived from the clip, and
the subtitle and band come down when the clip's status word clears.

The red is the stock executable: its `XA` handler opens no text, so the page stays 0
(`research/event-scripts.md` § Voice-only entries says where that was run).

Skips without the import, the edit set, PCSX-Redux and the BIOS, and unless
`BOKU_EMU_TESTS=1`: a boot to day 1's room is minutes.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.archive import Archive
from boku.build import main_build
from boku.events import VOICE_KEY_SIZE
from boku.sites import Walk
from boku.translation import SampleScenes
from boku.voice import TICK_HZ, clip_ticks, subtitle_waits
from tests.test_real_movie_subtitle import BIOS, REDUX, RUNNER

BUILD = Path(os.environ.get("BOKU_VWF_BUILD", REPO_ROOT / "build" / "vwf"))
WORK = REPO_ROOT / "work" / "vo02"
SCRIPT = REPO_ROOT / "tools" / "redux" / "voice-sub.lua"

LINE = "E0184.2"
PAGES = (
    "VO-02 fixture: page one of a subtitle on a voice-only clip.",
    "Page two, turned by the clip's own timer.",
)
VSYNCS_PER_TICK = 60 // TICK_HZ
SLACK = 4
"""Vsyncs a transition may land either side of its prediction: the probe samples once a
vsync and a tick is two."""

pytestmark = pytest.mark.skipif(
    os.environ.get("BOKU_EMU_TESTS") != "1", reason="emulator boots: set BOKU_EMU_TESTS=1"
)


def states(log: str) -> list[tuple[int, dict[str, int]]]:
    out = []
    for match in re.finditer(r"^TEXT f=(\d+) (.*)$", log, re.M):
        fields = {k: int(v, 16) for k, v in re.findall(r"(\w+)=([0-9a-f]+)", match[2])}
        out.append((int(match[1]), fields))
    return out


@pytest.fixture(scope="module")
def run(
    real_image: Path, disc_dir: Path, archive: Archive, walk_reader: Walk, tmp_path_factory
) -> tuple[int, list, int]:
    """(vsync the XA ran, the state changes after it, the clip's length in ticks)."""
    edits = BUILD / "edits.json"
    for needed, how in (
        (edits, "run `./make.sh build-days` or tools/vwf/build_prototype.py --edits-only"),
        (REDUX, "install PCSX-Redux or set REDUX_APP"),
        (BIOS, "set REDUX_BIOS"),
    ):
        if not needed.exists():
            pytest.skip(f"no {needed}: {how}")
    rows = tmp_path_factory.mktemp("vo02") / "fixture.txt"
    rows.write_text(f"{LINE}\t{SampleScenes.VOICE_ONLY}\t{' // '.join(PAGES)}\n", encoding="utf-8")
    out = WORK / "image"
    status = main_build(
        str(real_image), out, rows.parent, None, disc_dir, "vo02", False, False, vwf=edits
    )
    assert status == 0, "the fixture build failed"
    slot = walk_reader.voice_only[LINE][0]
    ticks = clip_ticks(archive.boku[slot.absolute : slot.absolute + VOICE_KEY_SIZE])
    log = probe(out / "image.cue", "boot", BOKU_SAVE="1")
    started = int(re.search(r"^XA f=(\d+) ev=184 msg=2 ", log, re.M)[1])
    return started, states(log), ticks


def probe(cue: Path, name: str, **env: str) -> str:
    """Run `voice-sub.lua` on `cue`; its stdout, also kept as `work/vo02/<name>.log`."""
    done = subprocess.run(
        [str(RUNNER), str(cue), str(SCRIPT)],
        env=os.environ | {"BOKU_WORK": str(WORK / "redux"), "BOKU_AFTER": "400"} | env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    (WORK / f"{name}.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    assert "EXIT 0" in done.stdout, f"the probe did not finish; see {WORK / name}.log"
    return done.stdout


@pytest.fixture(scope="module")
def cleared(run) -> tuple[int, list]:
    """The same clip from the state saved as it started, with the page cleared under it
    60 vsyncs in -- what `text_reset` does when an event ends (`BOKU_CLEAR_AT`)."""
    log = probe(
        WORK / "image" / "image.cue", "cleared", BOKU_LOAD="voice-start", BOKU_CLEAR_AT="60"
    )
    return int(re.search(r"^CLEARED f=(\d+)", log, re.M)[1]), states(log)


def test_the_subtitle_opens_the_tick_the_clip_starts_with_the_band_up(run):
    started, changes, _ = run
    first_at, first = changes[0]
    assert first_at - started <= SLACK
    assert first["page"] != 0, "the XA handler opened no text: is asm/voice.asm in the build?"
    assert first["panel"] == 1, "the text is up with no band behind it"
    assert first["flags"] & 3 == 1, "page 1 should end on a page break"


def test_the_first_page_turns_on_the_timer_the_build_derived_from_the_clip(run):
    started, changes, ticks = run
    turned = [(f, s) for f, s in changes if s["flags"] & 3 == 2 and s["page"]]
    assert turned, "the subtitle never reached its last page"
    # The countdown is loaded the tick the page is first drawn and counts from the next.
    predicted = started + VSYNCS_PER_TICK * (subtitle_waits(PAGES, ticks)[0] + 1)
    assert abs(turned[0][0] - predicted) <= SLACK, (turned[0][0], predicted)


def test_the_subtitle_and_its_band_come_down_when_the_clip_stops(run):
    _, changes, _ = run
    stopped = next(f for f, s in changes if s["busy"] & 5 == 0)
    closed = [(f, s) for f, s in changes if s["page"] == 0]
    assert closed, "the subtitle stayed up after the clip"
    assert abs(closed[0][0] - stopped) <= SLACK
    assert closed[0][1]["panel"] == 0, "the band stayed up with nothing in it"


def test_a_subtitle_cleared_under_it_takes_its_band_down_while_the_clip_plays(cleared):
    at, changes = cleared
    after = [(f, s) for f, s in changes if f >= at]
    assert after and after[0][1]["busy"] & 5, "the clip had stopped; this is not the case asked"
    down = [f for f, s in after if s["panel"] == 0]
    assert down, "the band stayed up with nothing in it"
    assert down[0] - at <= SLACK
