"""The built image's `save_title_build`, run instruction by instruction (`PLAN PIPE-07`).

The memory-card title is what the console's own card screen shows; no emulator run of a
bedtime save is needed to see what the patched game writes there, because the code that
writes it is ours to run: `TITLE.OVL`'s `save_title_build` (`0x8007AEF4`) with the built
executable's `strcpy`/`strcat` under it (`tests/mips.py`). The expectation is the committed
row itself, spelled out the way `boku.code_text` spells it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boku.archive import EXE_LOAD_BIAS, OVERLAY_LOAD_ADDRESS
from boku.arrays import SAVE_TITLE_BYTES, SAVE_TITLE_LINE_ID
from boku.code_text import DAY, SLOT, full_width
from boku.translation import SampleScenes
from tests.mips import Machine
from tests.test_real_reinsert import read_back

REPO_ROOT = Path(__file__).resolve().parent.parent
DAYS = REPO_ROOT / "build" / "days"
ARRAYS = REPO_ROOT / "translation" / "days" / "arrays.txt"
SAVE_TITLE_BUILD = 0x8007AEF4
DESTINATION = 0x80100000


@pytest.fixture(scope="module")
def built():
    manifest = DAYS / "manifest.json"
    if not manifest.is_file():
        pytest.skip("no build/days: run `./make.sh build-days` first")
    if SAVE_TITLE_LINE_ID not in json.loads(manifest.read_text())["lines_written"]:
        pytest.skip("this build did not write the save title")
    return read_back(DAYS / "image.img")[0]


@pytest.mark.parametrize(("slot", "day"), [(1, 5), (15, 31)])
def test_the_patched_game_writes_the_english_title_into_the_card_header(built, slot, day):
    (row,) = [e for e in SampleScenes.from_paths([ARRAYS]) if e.line_id == SAVE_TITLE_LINE_ID]
    text = " ".join(row.pages).replace(SLOT, str(slot)).replace(DAY, str(day))
    machine = Machine()
    machine.load(EXE_LOAD_BIAS, built.exe)
    machine.load(OVERLAY_LOAD_ADDRESS, built.blob(built.member("TITLE.OVL")))
    machine.load(DESTINATION, bytes(0x100))
    machine.call(SAVE_TITLE_BUILD, DESTINATION, slot, day)
    written = bytes(machine.ram[DESTINATION & 0x1FFFFF : (DESTINATION & 0x1FFFFF) + 0x100])
    title = written[: written.index(b"\0")]
    assert title.decode("shift_jis") == full_width(text)
    assert len(title) < SAVE_TITLE_BYTES, "the field's 64 bytes, terminator included"
