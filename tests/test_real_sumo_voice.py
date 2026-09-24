"""`VO-06`: the boys' bug-sumo voices get their subtitle (research/sumo.md § Subtitles is
the design), and leaving bug sumo does not hang (research/loading-and-memory.md § Leaving a
mode). The routines run on the patched executable in `tests.mips`; the words compared are the
block's own (`boku.movie_block.clip_words` over the block the build wrote). Needs the import
and armips. The last two tests boot the emulators (`BOKU_EMU_TESTS=1`).
"""

from __future__ import annotations

import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.archive import EXE_NAME, read_exe_dir
from boku.asm_source import asm_equate
from boku.build import main_build
from boku.clip_subs import OUTSIDE_SUMO
from boku.glyphs import END_WORD
from boku.movie_block import MAGIC, clip_words
from tests.mips import Machine
from tests.test_real_movie_subtitle import BIOS, REDUX, REDUX_TIMEOUT, RUNNER
from tests.test_vwf_prototype import (
    NEEDS_ARMIPS,
    NEEDS_IMPORT,
    build_without_a_disc,
    vwf_prototype,
)

pytestmark = [NEEDS_IMPORT, NEEDS_ARMIPS]

G_MODES, MODE_RECORD, SUMO = 0x800236BC, 16, 7
"""`g_modes`: `{update, init, vsync, arena_base}` per mode (research/loading-and-memory.md)."""
MODE_ASKED, MODE_VSYNCS = 0x800237E0, 0x800237EC
EVENT_FLAGS = 0x8003637C
EVENT_IN_SUMO = 5
"""The runner's flags read on Beetle all through a bout: bit 0 set by `E4025`, suspended."""
LEVEL_C = asm_equate("LEVEL_C_BASE", "voice.asm")
HOME = 0x801F7650
"""Level C's base under the build's map-area raise, read on Beetle in a bout."""
TEXT_PAGE, XA_STATUS = 0x800359EC, 0x800359D8
CD_INT_TO_POS, CD_READ, CD_READ_SYNC, XA_PLAY, TEXT_RESET, TEXT_SET_LIGHT = (
    asm_equate(name, "voice.asm")
    for name in (
        "CD_INT_TO_POS",
        "CD_READ",
        "CD_READ_SYNC",
        "XA_PLAY",
        "TEXT_RESET",
        "TEXT_SET_LIGHT",
    )
)
DIALOG_OPEN, DIALOG_DRAW, DIALOG_PANEL_SHOW, DIALOG_PANEL_DRAW = (
    asm_equate(name, "voice.asm")
    for name in ("DIALOG_OPEN", "DIALOG_DRAW", "DIALOG_PANEL_SHOW", "DIALOG_PANEL_DRAW")
)
MAIN_LOOP_CALL = 0x80014C18
"""What the main loop calls where `clip_sub_frame` now sits."""
BASE = REPO_ROOT / "work" / "saves" / "newgame.ram"
BOUT = REPO_ROOT / "tools" / "libretro" / "sumo_bout.py"
PROTOTYPE = REPO_ROOT / "tools" / "vwf" / "build_prototype.py"
WORK = REPO_ROOT / "work" / "vo06"


SUMO_HOME_BYTES = asm_equate("SUMO_HOME_BYTES", "voice.asm")
"""The room the block may take from level C's base."""
SUMO_CLIPS = [n for n in range(41) if n not in OUTSIDE_SUMO]
"""`XCH.00`-`.40` but those known to play elsewhere: bug sumo's."""


@pytest.fixture(scope="module")
def built(tmp_path_factory, archive):
    """`(patched executable, stock executable, armips symbols, the movie-subtitle block)`."""
    tool = vwf_prototype()
    captured: dict[str, object] = {}
    assemble = tool.assemble

    def capture(*arguments, **keywords):
        captured["it"] = assemble(*arguments, **keywords)
        return captured["it"]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tool, "assemble", capture)
        patch.setattr(
            tool, "write_movie_block", lambda w, block, ledger: captured.update(block=block)
        )
        build_without_a_disc(tool, tmp_path_factory.mktemp("sumo-voice"), patch)
    images, symbols = captured["it"]
    return images[EXE_NAME], archive.exe, symbols, captured["block"]


def word(exe: bytes, address: int) -> int:
    return struct.unpack_from("<I", exe, address - vwf_prototype().EXE_LOAD_BIAS)[0]


def jal_targets(exe: bytes, start: int, end: int) -> list[int]:
    words = (word(exe, a) for a in range(start, end, 4))
    return [0x80000000 | (w & 0x3FFFFFF) << 2 for w in words if w >> 26 == 3]


_RETURNS = {CD_READ: 1, CD_READ_SYNC: 0}
"""A read that is accepted, then complete: what `clip_sub_read` loops on."""


def machine(exe: bytes, *stubbed: int) -> Machine:
    """The executable in RAM with each address in `stubbed` recorded, not run."""
    m = Machine(
        stubs={a: [] for a in stubbed},
        returns={a: v for a, v in _RETURNS.items() if a in stubbed},
    )
    m.load(vwf_prototype().EXE_LOAD_BIAS, exe)
    return m


def in_sumo(m: Machine, block: bytes) -> None:
    """RAM as a bout leaves it: mode 7, the event bit set, the block at level C and not at
    `MOVIE_SUB_BLOCK` (bug sumo's memory there holds anything)."""
    m.write(MODE_ASKED, 1, SUMO)
    m.write(EVENT_FLAGS, 4, EVENT_IN_SUMO)
    m.write(LEVEL_C, 4, HOME)
    m.load(HOME, block)


def test_entering_bug_sumo_reads_the_block_to_level_c_after_musi_s_own_init(built):
    patched, stock, _, block = built
    init = word(stock, G_MODES + SUMO * MODE_RECORD + 4)
    file_load, musi_init = jal_targets(stock, init, init + 0x30)
    m = machine(patched, file_load, musi_init, CD_INT_TO_POS, CD_READ, CD_READ_SYNC)
    m.write(LEVEL_C, 4, HOME)
    m.call(word(patched, G_MODES + SUMO * MODE_RECORD + 4))
    assert m.order == [file_load, musi_init, CD_INT_TO_POS, CD_READ, CD_READ_SYNC], (
        "bug sumo's init must load MUSI, run its init, then read the block -- once"
    )
    (read,) = m.stubs[CD_READ]
    assert read[2] == HOME, f"the block was read to 0x{read[2]:08X}, not level C's base"
    assert read[1] * 2048 >= len(block), "the read is shorter than the block"


@pytest.mark.parametrize("clip", [n for n in SUMO_CLIPS if n in (0, 4, 40)])
def test_a_clip_in_bug_sumo_opens_its_words_from_level_c(built, clip):
    patched, _, symbols, block = built
    words = clip_words(block, clip)
    assert words, f"XCH.{clip:02d} has no English in the block: pick a clip clips.txt gives"
    m = machine(patched, XA_PLAY, DIALOG_OPEN, DIALOG_PANEL_SHOW, TEXT_RESET, CD_READ)
    in_sumo(m, block)
    m.call(symbols["clip_sub_play"], 0x80100000, registers={3: 12 * clip})
    assert not m.stubs[CD_READ], "a clip in a bout must not read the disc"
    (opened,) = m.stubs[DIALOG_OPEN]
    text = opened[3]
    assert HOME <= text < HOME + len(block), f"the words at 0x{text:08X} are not level C's"
    assert words[-1] == END_WORD
    drawn = tuple(m.read(text + 2 * i, 2) for i in range(len(words)))
    assert drawn == words, f"XCH.{clip:02d} opened other words than its own"


def subtitle_up(built, mode: int) -> Machine:
    """A sumo clip's subtitle open and its clip playing, then the game in `mode`."""
    patched, _, symbols, block = built
    m = machine(
        patched,
        XA_PLAY,
        DIALOG_OPEN,
        DIALOG_PANEL_SHOW,
        TEXT_RESET,
        MAIN_LOOP_CALL,
        TEXT_SET_LIGHT,
        DIALOG_DRAW,
        DIALOG_PANEL_DRAW,
    )
    in_sumo(m, block)
    m.call(symbols["clip_sub_play"], 0x80100000, registers={3: 12 * SUMO_CLIPS[0]})
    (opened,) = m.stubs[DIALOG_OPEN]
    m.write(TEXT_PAGE, 4, opened[3])  # what dialog_open sets
    m.write(XA_STATUS, 4, 1)
    m.write(MODE_VSYNCS, 4, 0)  # MUSI's init runs its mode at 60 Hz
    m.write(MODE_ASKED, 1, mode)
    return m


def test_bug_sumo_s_frame_draws_the_subtitle_although_its_event_bit_is_set(built):
    m = subtitle_up(built, SUMO)
    m.call(built[2]["clip_sub_frame"])
    assert len(m.stubs[DIALOG_DRAW]) == 1, "bug sumo's frame did not draw the subtitle"


PORTRAIT = (18, 161, 44, 44)
"""Boku's portrait in a bout: x, y, w, h of the sprite a bout adds to ordering-table slot 0,
in front of the band (read from the table on Beetle; research/sumo.md § Subtitles)."""


def pen_x(built, mode: int) -> int:
    """The x `dialog_open` is given for a sumo clip in `mode`, the block where it looks."""
    patched, _, symbols, block = built
    m = machine(patched, XA_PLAY, DIALOG_OPEN, DIALOG_PANEL_SHOW, TEXT_RESET)
    in_sumo(m, block)
    m.load(vwf_prototype().BLOCK_RAM, block)
    m.write(MODE_ASKED, 1, mode)
    m.write(EVENT_FLAGS, 4, 0)  # outside bug sumo the bit means an event owns the text
    m.call(symbols["clip_sub_play"], 0x80100000, registers={3: 12 * SUMO_CLIPS[0]})
    ((x, *_),) = m.stubs[DIALOG_OPEN]
    return x


def test_bug_sumo_s_pen_starts_right_of_boku_s_portrait(built):
    x, right = pen_x(built, SUMO), PORTRAIT[0] + PORTRAIT[2]
    assert x >= right, f"the pen at x {x} starts under the portrait, which ends at {right}"


def test_movie_mode_keeps_the_band_s_own_pen(built):
    assert pen_x(built, 0x0E) == vwf_prototype().Layout().pen_x


# --- leaving bug sumo: SUB.TIM's reload must stay under the stack -----------------------------

SUB_TIM = asm_equate("SUB_TIM", "arena.asm")
SUB_TIM_RELOAD = 0x80014E60
"""Loads `SUB.TIM` (`g_cd_dir` `SUB_TIM`) at its argument and uploads it: every overlay's exit
calls it with `g_arena_cur` (research/loading-and-memory.md § Leaving a mode)."""
FILE_LOAD, TIM_UPLOAD = 0x800129E0, 0x80014C98
STACK_REACH = asm_equate("STACK_TOP", "arena.asm") - asm_equate("STACK_DEPTH", "arena.asm")
"""The stack's measured low-water mark, which `sub_tim_floor` keeps SUB.TIM under."""
MUSI_CUR_AT_EXIT = 0x801E7AC0
"""`g_arena_cur` all through bug sumo under the build's raises (Beetle, a bout)."""


@pytest.mark.parametrize("cur", [MUSI_CUR_AT_EXIT, 0x801B5A50])
def test_sub_tim_s_reload_ends_under_the_stack_and_moves_only_when_it_must(built, cur):
    """From bug sumo's `g_arena_cur` SUB.TIM's sectors ran over the stack (a black screen);
    a reload that fits -- a menu's, from level B's base -- keeps its address."""
    patched, _, _, _ = built
    entry = read_exe_dir(patched)[SUB_TIM]
    assert "SUB.TIM" in entry.name
    loaded = entry.sectors * 2048
    m = machine(patched, FILE_LOAD, TIM_UPLOAD)
    m.call(SUB_TIM_RELOAD, cur)
    ((index, dest, *_),) = m.stubs[FILE_LOAD]
    assert index == SUB_TIM
    if cur + loaded <= STACK_REACH:
        assert dest == cur, "a reload that fits was moved"
    else:
        assert dest + loaded <= STACK_REACH, (
            f"SUB.TIM loads at 0x{dest:08X} and its sectors run to 0x{dest + loaded:08X}, "
            f"into the stack (reach 0x{STACK_REACH:08X})"
        )
    assert m.stubs[TIM_UPLOAD][0][0] == dest, "the upload reads another address than the load"


# --- on the emulators: the committed clips.txt built into an image -------------------------

EMU = pytest.mark.skipif(os.environ.get("BOKU_EMU_TESTS") != "1", reason="set BOKU_EMU_TESTS=1")


@pytest.fixture
def beetle() -> None:
    for var in ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM"):
        if not os.environ.get(var):
            pytest.skip(f"{var} is not set (research/tooling-setup.md § Beetle PSX, headless)")
    if not BASE.is_file():
        pytest.skip(f"no {BASE}: `./make.sh saves` dumps it")


@pytest.fixture
def redux() -> None:
    for path, what in [
        (REDUX / "Contents" / "MacOS" / "PCSX-Redux", "set REDUX_APP"),
        (BIOS, "set REDUX_BIOS"),
    ]:
        if not path.exists():
            pytest.skip(f"no {path}: {what}")


@pytest.fixture(scope="module")
def sumo_image(real_image: Path, disc_dir: Path, tmp_path_factory) -> Path:
    """The committed translation built into an image (asked for after the emulator's own
    prerequisites, so a machine without that emulator skips before paying for the build)."""
    out = tmp_path_factory.mktemp("vo06")
    subprocess.run(
        [sys.executable, str(PROTOTYPE), "--edits-only", "--out", str(out / "vwf")],
        cwd=REPO_ROOT, check=True, capture_output=True, timeout=600,
    )  # fmt: skip
    status = main_build(
        str(real_image), out / "image", None, None, disc_dir, "vo06", False, False,
        vwf=out / "vwf" / "edits.json",
    )  # fmt: skip
    assert status == 0, "boku build --vwf refused the committed translation"
    return out / "image" / "image.cue"


@EMU
def test_on_beetle_the_gong_s_clip_is_subtitled_and_bug_sumo_can_be_left(
    beetle, sumo_image: Path, disc_dir: Path, tmp_path: Path
):
    """The corpus's sumo card driven into a bout by `tools/libretro/sumo_bout.py --gong
    --leave`, whose exit code is the assertion: 14, no subtitle while the gong's clip played
    or one left after it; 15, the field never came back after "もどる"."""
    made = subprocess.run(
        [sys.executable, "-m", "boku", "save", "--base", str(BASE), "--corpus",
         "--out", str(tmp_path / "corpus"), "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )  # fmt: skip
    card = tmp_path / "corpus" / "sumo-maxed-cage.mcd"
    assert made.returncode == 0 and card.is_file(), made.stdout + made.stderr
    fought = subprocess.run(
        [sys.executable, str(BOUT), str(card), "--gong", "--leave", "--image", str(sumo_image),
         "--work", str(WORK / "beetle"), "--disc", str(disc_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    assert fought.returncode == 0, fought.stdout + fought.stderr


@EMU
def test_on_redux_a_sumo_clip_opens_its_words_from_level_c_and_closes_with_the_clip(
    redux, sumo_image: Path
):
    """`tools/redux/sumo-clip.lua`: bug sumo's desk from a cold boot, then a clip played by
    the call every sumo clip makes. The block must be at level C's base when it plays, the
    subtitle up from there with the band, and both down once the clip has stopped."""
    done = subprocess.run(
        [str(RUNNER), str(sumo_image), str(REPO_ROOT / "tools" / "redux" / "sumo-clip.lua")],
        env=os.environ | {"BOKU_WORK": str(WORK / "redux"), "REDUX_TIMEOUT": REDUX_TIMEOUT},
        capture_output=True, text=True, timeout=1500,
    )  # fmt: skip
    (WORK / "redux.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    assert "EXIT 0" in done.stdout, f"the probe did not finish; see {WORK / 'redux.log'}"
    clip = re.search(
        r"^CLIP f=(\d+) clip=\d+ home=([0-9a-f]+) magic=([0-9a-f]+)", done.stdout, re.M
    )
    assert clip, "no CLIP line: the forced xa_play_indexed call never returned"
    home, magic = int(clip[2], 16), int(clip[3], 16)
    assert magic == MAGIC, f"no block at level C's base 0x{home:08X} when the clip played"
    states = [
        {k: int(v, 16) for k, v in re.findall(r"(\w+)=([0-9a-f]+)", m[1])}
        for m in re.finditer(r"^STATE f=\d+ (.*)$", done.stdout, re.M)
    ]
    assert states, "the subtitle's state never changed after the clip"
    first = states[0]
    assert home <= first["page"] < home + SUMO_HOME_BYTES and first["panel"] == 1
    stopped = next((s for s in states if not s["busy"] & 5), None)
    assert stopped, "the clip never stopped in the probe's window"
    assert stopped["page"] == 0 and stopped["panel"] == 0, "the subtitle outlived its clip"
