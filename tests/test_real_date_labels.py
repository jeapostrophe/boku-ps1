"""The two date labels, redrawn around their English (`asm/labels.asm`, `PLAN PIPE-07`).

The built image's drawers are run instruction by instruction (`tests/mips.py`): each must
now draw its row's English cells, in order, left to right, stepped through the advance
table -- the save date is also seen on Beetle's load screen ("1) August 4"); the caught
label needs a caught insect or fish, so this run is its proof. `number_draw` and the glyph
flush are stubbed to return: they draw sprites, not text, and are the retail routines."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boku.archive import EXE_LOAD_BIAS, OVERLAY_LOAD_ADDRESS
from boku.build import load_edit_set
from boku.code_text import DATE_LABELS, drawer_of, lay_out_date_label
from boku.glyphs import END_WORD
from boku.translation import SampleScenes
from tests.mips import Machine
from tests.test_real_reinsert import read_back

REPO_ROOT = Path(__file__).resolve().parent.parent
DAYS = REPO_ROOT / "build" / "days"
EDITS = REPO_ROOT / "build" / "vwf" / "edits.json"
ARRAYS = REPO_ROOT / "translation" / "days" / "arrays.txt"
NUMBER_DRAW, GLYPH_FLUSH = 0x800400F8, 0x8002B95C
GLYPH_DIGIT, SPRITE_DIGIT, CAUGHT_RIGHT = 0x34, 7, 77  # asm/labels.asm's equates


@pytest.fixture(scope="module")
def built():
    manifest = DAYS / "manifest.json"
    if not manifest.is_file() or not EDITS.is_file():
        pytest.skip("no build/days or build/vwf: run `./make.sh build-days` first")
    written = set(json.loads(manifest.read_text())["lines_written"])
    if not set(DATE_LABELS) <= written:
        pytest.skip("this build did not write the date labels")
    return read_back(DAYS / "image.img")[0]


def _run(built, line_id: str, day: int, colour: int = 0x5A):
    encoder = load_edit_set(EDITS).encoder
    (row,) = [e for e in SampleScenes.from_paths([ARRAYS]) if e.line_id == line_id]
    laid = lay_out_date_label(line_id, " ".join(row.pages), encoder)
    machine = Machine(stubs={NUMBER_DRAW: [], GLYPH_FLUSH: []})
    machine.load(EXE_LOAD_BIAS, built.exe)
    image, ram = drawer_of(line_id)
    if image == "title":
        machine.load(OVERLAY_LOAD_ADDRESS, built.blob(built.member("TITLE.OVL")))
    sp = 0x801FFF00
    machine.load(sp + 16, colour.to_bytes(4, "little"))  # the caller's fifth argument
    machine.call(ram, X, Y, day, 0x1234)
    return laid, machine


X, Y = 40, 100


@pytest.mark.parametrize("line_id", sorted(DATE_LABELS))
@pytest.mark.parametrize("day", [4, 15])
def test_the_drawer_draws_the_row_s_english_left_to_right(built, line_id, day):
    laid, machine = _run(built, line_id, day)
    english = [cell for cell in laid.words if cell != END_WORD]
    ids = [draw[0] for draw in machine.draws]
    xs = [draw[1] for draw in machine.draws]
    assert [i for i in ids if i in english] == english, f"{line_id} drew {ids}"
    assert xs == sorted(xs), f"{line_id} drew right to left somewhere: {xs}"
    assert all(draw[2] == Y for draw in machine.draws)
    assert len(machine.stubs[GLYPH_FLUSH]) == 1, "the glyphs are flushed once, as retail does"


@pytest.mark.parametrize("day", [4, 15])
def test_the_save_date_draws_the_day_s_digits_after_the_english(built, day):
    laid, machine = _run(built, "title@code:8007BB60", day)
    prefix = laid.words.index(END_WORD)  # the cells before the day
    digits = [draw[0] for draw in machine.draws][prefix : prefix + len(str(day))]
    assert digits == [GLYPH_DIGIT + int(d) for d in str(day)]


@pytest.mark.parametrize("day", [4, 15])
def test_the_caught_label_places_its_numbers_after_the_english_and_keeps_its_right_edge(built, day):
    """Month then day through `number_draw`, a row lower, with the caller's own fourth and
    fifth arguments; the label right-aligned where the retail one ended (x + 77), because its
    callers put it against the screen's right edge."""
    _, machine = _run(built, "exe@code:80037544", day, colour=0x5A)
    month, day_call = machine.stubs[NUMBER_DRAW]
    assert (month[0], month[2], month[3], month[4], month[5] & 0xFF) == (8, Y + 1, 0, 0x1234, 0x5A)
    assert (day_call[0], day_call[2]) == (day, Y + 1)
    last_letter = max(draw[1] for draw in machine.draws)
    first_letter = min(draw[1] for draw in machine.draws)
    assert first_letter < month[1] < day_call[1], "the numbers come after the words"
    right = day_call[1] + SPRITE_DIGIT * len(str(day))
    assert right <= X + CAUGHT_RIGHT and last_letter < X + CAUGHT_RIGHT
