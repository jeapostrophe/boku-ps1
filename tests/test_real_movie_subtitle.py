"""`FMV-04` milestone 1 on headless PCSX-Redux: one cue over the opening, pixel for pixel.

The image `tools/vwf/build_prototype.py` wrote and the stock dump are both booted to the
opening movie by `tools/redux/movie-sub.lua`, which copies the same decoded frames of each
out of RAM -- the twenty slice buffers at the `LoadImage` call design E2 hooks, which is
where the routine writes and the only place the result can be read exactly (the emulator's
screenshot is black in this display mode; the script says where that was measured). What
each gate asks is on the gate; between them they cover the pixels inside the cue, the frame
number they are predicted from, and the frames outside it.

Skips without the import, without a built image, its manifest and its block, without
PCSX-Redux and the BIOS, and unless `BOKU_EMU_TESTS=1`: two emulator boots are minutes, not
a unit test. The stock dumps are cached under `work/fmv04/stock/` (the run is
deterministic) and the cache is keyed on the probe that wrote them, so a change to
`movie-sub.lua`'s dump format re-runs the stock image instead of comparing fresh frames
against stale ones; the patched image is rerun every time. `BOKU_VWF_BUILD` names another
build directory than `build/vwf/`; a build without the hooks is this test's red.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.movie_block import (
    DARK,
    FRAME_HEIGHT,
    SCREEN_WIDTH,
    SLICE_WIDTH,
    SLICES,
    WHITE,
    render,
    slice_columns,
)

BUILD = Path(os.environ.get("BOKU_VWF_BUILD", REPO_ROOT / "build" / "vwf"))
WORK = REPO_ROOT / "work" / "fmv04"
RUNNER = REPO_ROOT / "tools" / "redux" / "run-on-image.sh"
SCRIPT = REPO_ROOT / "tools" / "redux" / "movie-sub.lua"
REDUX = Path(os.environ.get("REDUX_APP", Path.home() / "Dev/dist/pcsx-redux/PCSX-Redux.app"))
BIOS = Path(
    os.environ.get("REDUX_BIOS", Path.home() / "Dev/retro-trainer/config/system/scph5500.bin")
)

BYTES_PER_PIXEL = 3
"""The slice buffers are 24-bit: the movie's display mode, and what the blit writes."""
SLICE_ROW = SLICE_WIDTH * BYTES_PER_PIXEL
"""One row of one slice buffer -- the stride the routine steps by."""
SLICE_BYTES = SLICE_ROW * FRAME_HEIGHT
INSIDE = 199
OUTSIDE = (59, 399)
"""Decoded-frame indices (STR header number minus one, as the run records it): one inside
the cue's 120-300 and one well clear on either side."""
INDICES = (OUTSIDE[0], INSIDE, OUTSIDE[1])


@dataclass(frozen=True)
class Frame:
    rows: tuple[bytes, ...]
    """`FRAME_HEIGHT` rows of the whole frame's pixels, the slices laid side by side."""
    sub_frame: tuple[int, ...]
    """Per slice, the word at `movie_sub_frame_no` when it was uploaded: the STR frame the
    hook drew for. Meaningless on the stock image."""
    header: tuple[int, ...]
    """Per slice, the last STR header number `movie_frame_volume` had seen."""


def read_dump(work: Path, index: int) -> Frame:
    blob = (work / "dumps" / f"k{index}.bin").read_bytes()
    assert len(blob) == SLICES * SLICE_BYTES, f"k{index}.bin is {len(blob)} bytes"
    rows = tuple(
        b"".join(
            blob[k * SLICE_BYTES + y * SLICE_ROW : k * SLICE_BYTES + (y + 1) * SLICE_ROW]
            for k in range(SLICES)
        )
        for y in range(FRAME_HEIGHT)
    )
    notes = (work / "dumps" / f"k{index}.txt").read_text(encoding="ascii").splitlines()
    assert len(notes) == SLICES
    parsed = [dict(re.findall(r"(\w+)=(-?\d+)", line)) for line in notes]
    assert [int(n["slice"]) for n in parsed] == list(range(SLICES))
    return Frame(
        rows,
        tuple(int(n["sub_frame"]) for n in parsed),
        tuple(int(n["header"]) for n in parsed),
    )


def have_dumps(work: Path) -> bool:
    return all(
        (work / "dumps" / f"k{n}.{ext}").is_file() for n in INDICES for ext in ("bin", "txt")
    )


STAMP = "probe.sha1"
"""Beside a run's dumps: what produced them. The stock run is cached because it is
deterministic, and it was keyed on the frame indices alone -- so an edit to the probe's
dump format compared fresh patched frames against stock frames written by the old one."""


def probe_stamp(sub_frame_no: str) -> str:
    return hashlib.sha1(
        SCRIPT.read_bytes() + repr((INDICES, sub_frame_no)).encode("ascii")
    ).hexdigest()


def run_redux(image: Path, work: Path, sub_frame_no: str) -> dict[int, Frame]:
    work.mkdir(parents=True, exist_ok=True)
    env = os.environ | {
        "BOKU_WORK": str(work),
        "BOKU_DUMP_INDEX": ",".join(str(n) for n in INDICES),
        # The island's address has one home, the build's manifest; the probe keeps no copy
        # (`asm/movie.asm` `MOVIE_SUB_ISLAND` is where it is decided).
        "BOKU_SUB_FRAME_NO": sub_frame_no,
        "REDUX_BIOS": str(BIOS),
    }
    done = subprocess.run(
        [str(RUNNER), str(image), str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    (work / "redux.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    assert done.returncode == 0, f"redux exited {done.returncode}; see {work / 'redux.log'}"
    return {n: read_dump(work, n) for n in INDICES}


@pytest.fixture(scope="module")
def block() -> bytes:
    if os.environ.get("BOKU_EMU_TESTS") != "1":
        pytest.skip("set BOKU_EMU_TESTS=1: two headless PCSX-Redux boots, about three minutes")
    for path, what in [
        (BUILD / "image.cue", "run `uv run python tools/vwf/build_prototype.py`"),
        (BUILD / "manifest.json", "the full build writes it; `--edits-only` removes it"),
        (BUILD / "files" / "movie-subtitles.bin", "the build writes it beside the image"),
        (REDUX / "Contents" / "MacOS" / "PCSX-Redux", "set REDUX_APP"),
        (BIOS, "set REDUX_BIOS (research/tooling-setup.md § The BIOS question)"),
    ]:
        if not path.exists():
            pytest.skip(f"no {path}: {what}")
    return (BUILD / "files" / "movie-subtitles.bin").read_bytes()


@pytest.fixture(scope="module")
def sub_frame_no(block: bytes) -> str:
    """Where the probe reads the frame number the hook kept: the build's own record of the
    island it assembled, so the address is not restated in the Lua or here. Takes `block`
    for its skips -- this is the first fixture that opens a file of the build, and every
    other one reaches it through this."""
    manifest = json.loads((BUILD / "manifest.json").read_text(encoding="utf-8"))
    return manifest["movie_subtitles"]["island"]["symbols"]["movie_sub_frame_no"]


@pytest.fixture(scope="module")
def stock(real_image: Path, sub_frame_no: str) -> dict[int, Frame]:
    work = WORK / "stock"
    stamp = work / STAMP
    if (
        have_dumps(work)
        and stamp.is_file()
        and stamp.read_text(encoding="ascii") == probe_stamp(sub_frame_no)
    ):
        return {n: read_dump(work, n) for n in INDICES}
    frames = run_redux(real_image.with_suffix(".cue"), work, sub_frame_no)
    stamp.write_text(probe_stamp(sub_frame_no), encoding="ascii")
    return frames


@pytest.fixture(scope="module")
def patched(sub_frame_no: str) -> dict[int, Frame]:
    return run_redux(BUILD / "image.cue", WORK / f"patched-{BUILD.name}", sub_frame_no)


Pixels = dict[tuple[int, int], tuple[int, int, int]]


def predicted(block: bytes, frame: Frame) -> Pixels:
    """What the routine should have drawn: each slice for the frame number it saw."""
    out: Pixels = {}
    for k in range(SLICES):
        out.update(render(block, frame.sub_frame[k], slice_columns(k)))
    return out


def pixel(row: bytes, x: int) -> bytes:
    """Column `x` of one row of a frame."""
    return row[BYTES_PER_PIXEL * x : BYTES_PER_PIXEL * (x + 1)]


def painted(rows: tuple[bytes, ...], pixels: Pixels) -> tuple[bytes, ...]:
    out = [bytearray(row) for row in rows]
    for (x, y), colour in pixels.items():
        assert 0 <= x < SCREEN_WIDTH and 0 <= y < FRAME_HEIGHT, f"({x}, {y}) is off the frame"
        out[y][BYTES_PER_PIXEL * x : BYTES_PER_PIXEL * (x + 1)] = bytes(colour)
    return tuple(bytes(row) for row in out)


def differences(one: tuple[bytes, ...], other: tuple[bytes, ...]) -> list[tuple]:
    out = []
    for y, (a, b) in enumerate(zip(one, other, strict=True)):
        if a == b:
            continue
        out += [
            (x, y, pixel(a, x).hex(), pixel(b, x).hex())
            for x in range(SCREEN_WIDTH)
            if pixel(a, x) != pixel(b, x)
        ]
    return out


def test_the_stock_frames_are_pictures_and_the_same_decoded_frame_in_both_runs(
    stock: dict[int, Frame], patched: dict[int, Frame]
):
    """The two gates below compare frames; this says the frames are worth comparing: the
    frame under the text is a picture, no frame is flat black (k59 is a dark fade-in: 15
    colours), and each index is the same STR frame in both runs."""
    for n in INDICES:
        colours = {pixel(row, x) for row in stock[n].rows for x in range(0, SCREEN_WIDTH, 4)}
        least = 100 if n == INSIDE else 1
        assert len(colours) > least, f"stock frame k{n} has {len(colours)} colours"
        assert stock[n].header == patched[n].header, f"k{n} is not the same STR frame in both runs"


def test_the_frame_number_the_hook_kept_is_the_one_the_player_saw(
    patched: dict[int, Frame], sub_frame_no: str
):
    """What the pixel gate cannot ask. It predicts each slice from `movie_sub_frame_no`
    itself, so a hook that stored a frame number the player never saw -- a stale word, a
    store the wrong side of the jump, a probe reading the wrong address -- is predicted
    wrongly and matches wrongly, pixel for pixel. `movie_sub_frame` stores `a0` and jumps
    to `movie_frame_volume`, and the probe reads both at the same breakpoint, so they are
    the same number on every slice."""
    for n in INDICES:
        assert patched[n].sub_frame == patched[n].header, (
            f"k{n}: the hook kept {patched[n].sub_frame} and movie_frame_volume was passed "
            f"{patched[n].header}; the probe read movie_sub_frame_no at {sub_frame_no}"
        )


def test_inside_the_cue_the_frame_is_the_stock_decode_plus_exactly_the_predicted_text(
    block: bytes, stock: dict[int, Frame], patched: dict[int, Frame]
):
    pixels = predicted(block, patched[INSIDE])
    seen = sorted(set(patched[INSIDE].sub_frame))
    assert pixels, (
        f"nothing predicted at k{INSIDE} (the hook saw frames {seen}); the cue is not where "
        f"the test thinks"
    )
    assert WHITE in pixels.values() and DARK in pixels.values()
    expected = painted(stock[INSIDE].rows, pixels)
    assert expected != stock[INSIDE].rows, "painting the prediction changed nothing; vacuous"
    wrong = differences(expected, patched[INSIDE].rows)
    assert not wrong, (
        f"{len(wrong)} pixels differ from the stock frame plus the predicted text "
        f"({len(pixels)} predicted); first: {wrong[:8]}"
    )


@pytest.mark.parametrize("index", OUTSIDE)
def test_outside_the_cue_the_frame_is_byte_identical_to_the_stock_decode(
    index: int, block: bytes, stock: dict[int, Frame], patched: dict[int, Frame]
):
    assert predicted(block, patched[index]) == {}, f"k{index} is inside a cue; not an outside frame"
    wrong = differences(stock[index].rows, patched[index].rows)
    assert not wrong, f"{len(wrong)} pixels changed on a frame with no cue; first {wrong[:8]}"
