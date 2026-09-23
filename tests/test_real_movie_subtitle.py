"""`FMV-04` on headless PCSX-Redux: cues keyed by movie, carried by `boku build`, to the pixel.

The image under test is built here the way `./make.sh build-days` builds one --
`tools/vwf/build_prototype.py --edits-only`, then `boku build --vwf` -- from `FIXTURE_CUES`,
placeholder English on two movies over the same frames. So what is proved is the carrier
as well as the hook: the block reaches the reserved sectors through the edit set, and the
loader picks each movie's own cues out of it.

Each movie is booted twice, on the stock dump and on the build, by `tools/redux/movie-sub.lua`,
which copies the same decoded frames of each out of RAM -- the twenty slice buffers at the
`LoadImage` call design E2 hooks, the only place the result can be read exactly (the
emulator's screenshot is black in this display mode). The opening is what the boot plays;
`M60` is played in its place by the probe rewriting the table entry the player is handed
(`BOKU_PLAY_NAME`), since nothing in a headless boot reaches the fireworks. What each gate
asks is on the gate; between them they cover the pixels inside a cue, the frame number they
are predicted from, the frames outside it, and the other movie's cue not being there.

Skips without the import, without armips, PCSX-Redux and the BIOS, and unless
`BOKU_EMU_TESTS=1`: four emulator boots are minutes, not a unit test. The stock dumps are
cached under `work/fmv04/stock-<movie>/` (the run is deterministic), keyed on the probe
that wrote them, so a change to `movie-sub.lua`'s dump format re-runs the stock image
instead of comparing fresh frames against stale ones; the build and its runs are redone
every time. `BOKU_MOVIE_BUILD` names an already-built directory (its `edits.json` and
`image/image.cue`) instead -- how a build without the hooks, or with another loader, is made
this test's red.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.build import main_build
from boku.movie_block import (
    DARK,
    FRAME_HEIGHT,
    SCREEN_WIDTH,
    SLICE_WIDTH,
    SLICES,
    WHITE,
    movie_names,
    render,
    select,
    slice_columns,
)
from boku.movie_cues import read_movie_lengths

WORK = REPO_ROOT / "work" / "fmv04"
PREBUILT = os.environ.get("BOKU_MOVIE_BUILD")
BUILD = Path(PREBUILT) if PREBUILT else WORK / "m2"
RUNNER = REPO_ROOT / "tools" / "redux" / "run-on-image.sh"
SCRIPT = REPO_ROOT / "tools" / "redux" / "movie-sub.lua"
PROTOTYPE = REPO_ROOT / "tools" / "vwf" / "build_prototype.py"
ARMIPS = Path.home() / "Dev/dist/armips/build/armips"
REDUX = Path(os.environ.get("REDUX_APP", Path.home() / "Dev/dist/pcsx-redux/PCSX-Redux.app"))
BIOS = Path(
    os.environ.get("REDUX_BIOS", Path.home() / "Dev/retro-trainer/config/system/scph5500.bin")
)
EXE = REPO_ROOT / "disc" / "files" / "SCPS_100.88"

FIXTURE_CUES = (
    "# FIXTURE: tests/test_real_movie_subtitle.py's placeholder cues. Not a translation.\n"
    "M27\t120\t300\tFIXTURE: the opening, M27 frames 120-300 | keyed to M27 and nothing else\n"
    "M60\t120\t300\tFIXTURE: the fireworks, M60 frames 120-300\n"
)
"""Two movies' cues over the same frames: the one frame index inside both is where a
loader that ignored the movie would draw the wrong one, and every pixel of it is checked."""

BYTES_PER_PIXEL = 3
"""The slice buffers are 24-bit: the movie's display mode, and what the blit writes."""
SLICE_ROW = SLICE_WIDTH * BYTES_PER_PIXEL
"""One row of one slice buffer -- the stride the routine steps by."""
SLICE_BYTES = SLICE_ROW * FRAME_HEIGHT
INSIDE = 199
"""A decoded-frame index (STR header number minus one, as the run records it) inside
both cues' 120-300."""
OUTSIDE = {"M27": (59, 399), "M60": (59, 330)}
"""One index clear of the cues on either side; `M60` stops at 362."""
MOVIES = tuple(OUTSIDE)


def indices(movie: str) -> tuple[int, ...]:
    return (OUTSIDE[movie][0], INSIDE, OUTSIDE[movie][1])


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


STAMP = "probe.sha1"
"""Beside a stock run's dumps: what produced them, so a changed probe re-runs the stock
image rather than comparing its fresh frames with an old probe's."""


@dataclass(frozen=True)
class Play:
    """What one run is told: which movie in the opening's place, and the island address."""

    movie: str
    name: int
    frames: int
    sub_frame_no: str

    def env(self) -> dict[str, str]:
        return {
            "BOKU_DUMP_INDEX": ",".join(str(n) for n in indices(self.movie)),
            # The island's address has one home, the build's edit set; the probe keeps no
            # copy (`asm/movie.asm` `MOVIE_SUB_ISLAND` is where it is decided).
            "BOKU_SUB_FRAME_NO": self.sub_frame_no,
            "BOKU_PLAY_NAME": f"0x{self.name:08X}",
            "BOKU_PLAY_FRAMES": str(self.frames),
        }

    def stamp(self) -> str:
        return hashlib.sha1(
            SCRIPT.read_bytes() + repr(sorted(self.env().items())).encode()
        ).hexdigest()


def run_redux(image: Path, work: Path, play: Play) -> dict[int, Frame]:
    work.mkdir(parents=True, exist_ok=True)
    env = os.environ | play.env() | {"BOKU_WORK": str(work), "REDUX_BIOS": str(BIOS)}
    done = subprocess.run(
        [str(RUNNER), str(image), str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    (work / "redux.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    assert done.returncode == 0, f"redux exited {done.returncode}; see {work / 'redux.log'}"
    return {n: read_dump(work, n) for n in indices(play.movie)}


# --- the build --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def build() -> Path:
    """`BUILD/edits.json` and `BUILD/image/image.cue`, from `FIXTURE_CUES`."""
    if os.environ.get("BOKU_EMU_TESTS") != "1":
        pytest.skip("set BOKU_EMU_TESTS=1: four headless PCSX-Redux boots, several minutes")
    for path, what in [
        (EXE, "run `./make.sh import` first"),
        (ARMIPS, "the font build assembles with armips"),
        (REDUX / "Contents" / "MacOS" / "PCSX-Redux", "set REDUX_APP"),
        (BIOS, "set REDUX_BIOS (research/tooling-setup.md § The BIOS question)"),
    ]:
        if not path.exists():
            pytest.skip(f"no {path}: {what}")
    if PREBUILT:
        return BUILD
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)
    cues = BUILD / "cues.txt"
    cues.write_text(FIXTURE_CUES, encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(PROTOTYPE),
            "--edits-only",
            "--movie-cues",
            str(cues),
            "--out",
            str(BUILD),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        timeout=600,
    )
    status = main_build(
        source=None,
        out_dir=BUILD / "image",
        translation_dir=None,
        cell_map=None,
        disc_dir=REPO_ROOT / "disc",
        name="fmv04-fixture",
        skip_unfitted=False,
        dry_run=False,
        vwf=BUILD / "edits.json",
    )
    assert status == 0, "boku build --vwf refused the fixture's edit set"
    return BUILD


@pytest.fixture(scope="module")
def edits(build: Path) -> dict:
    return json.loads((build / "edits.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def block(edits: dict) -> bytes:
    """The block as written: the edit set's one sector write, trimmed to its size."""
    (sector,) = edits["sectors"]
    return bytes.fromhex(sector["new"])[: edits["movie_subtitles"]["bytes"]]


@pytest.fixture(scope="module")
def names() -> dict[str, int]:
    return movie_names(EXE.read_bytes())


@pytest.fixture(scope="module")
def plays(edits: dict, names: dict[str, int]) -> dict[str, Play]:
    lengths = read_movie_lengths()
    island = edits["movie_subtitles"]["islands"][0]["symbols"]["movie_sub_frame_no"]
    return {movie: Play(movie, names[movie], lengths[movie], island) for movie in MOVIES}


@pytest.fixture(scope="module")
def stock(real_image: Path, plays: dict[str, Play]) -> dict[str, dict[int, Frame]]:
    out = {}
    for movie, play in plays.items():
        work = WORK / f"stock-{movie}"
        stamp = work / STAMP
        cached = stamp.is_file() and stamp.read_text(encoding="ascii") == play.stamp()
        if cached and all((work / "dumps" / f"k{n}.bin").is_file() for n in indices(movie)):
            out[movie] = {n: read_dump(work, n) for n in indices(movie)}
            continue
        out[movie] = run_redux(real_image.with_suffix(".cue"), work, play)
        stamp.write_text(play.stamp(), encoding="ascii")
    return out


@pytest.fixture(scope="module")
def patched(build: Path, plays: dict[str, Play]) -> dict[str, dict[int, Frame]]:
    return {
        movie: run_redux(build / "image" / "image.cue", WORK / f"patched-{movie}", play)
        for movie, play in plays.items()
    }


# --- the gates -------------------------------------------------------------------------------

Pixels = dict[tuple[int, int], tuple[int, int, int]]


def predicted(block: bytes, name: int, frame: Frame) -> Pixels:
    """What the routine should have drawn for the movie `name`: the block as the loader
    selects it, each slice for the frame number it saw."""
    loaded = select(block, name)
    out: Pixels = {}
    for k in range(SLICES):
        out.update(render(loaded, frame.sub_frame[k], slice_columns(k)))
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


def other(movie: str) -> str:
    (found,) = [m for m in MOVIES if m != movie]
    return found


@pytest.mark.parametrize("movie", MOVIES)
def test_the_stock_frames_are_pictures_and_the_same_decoded_frame_in_both_runs(
    movie, stock, patched
):
    """The gates below compare frames; this says the frames are worth comparing: the frame
    under the text is a picture, no frame is flat black, and each index is the same STR
    frame in both runs -- of the movie asked for, not the opening."""
    for n in indices(movie):
        colours = {pixel(row, x) for row in stock[movie][n].rows for x in range(0, SCREEN_WIDTH, 4)}
        least = 100 if n == INSIDE else 1
        assert len(colours) > least, f"stock {movie} frame k{n} has {len(colours)} colours"
        assert stock[movie][n].header == patched[movie][n].header, (
            f"{movie} k{n} is not the same STR frame in both runs"
        )
    assert stock["M27"][INSIDE].rows != stock["M60"][INSIDE].rows, "both runs played one movie"


@pytest.mark.parametrize("movie", MOVIES)
def test_the_frame_number_the_hook_kept_is_the_one_the_player_saw(movie, patched, plays):
    """What the pixel gate cannot ask. It predicts each slice from `movie_sub_frame_no`
    itself, so a hook that stored a frame number the player never saw -- a stale word, a
    store the wrong side of the jump, a probe reading the wrong address -- is predicted
    wrongly and matches wrongly, pixel for pixel."""
    for n in indices(movie):
        frame = patched[movie][n]
        assert frame.sub_frame == frame.header, (
            f"{movie} k{n}: the hook kept {frame.sub_frame} and movie_frame_volume was passed "
            f"{frame.header}; the probe read movie_sub_frame_no at {plays[movie].sub_frame_no}"
        )


@pytest.mark.parametrize("movie", MOVIES)
def test_inside_its_cue_the_frame_is_the_stock_decode_plus_exactly_its_own_text(
    movie, block, names, stock, patched
):
    frame = patched[movie][INSIDE]
    pixels = predicted(block, names[movie], frame)
    assert pixels, (
        f"nothing predicted for {movie} at k{INSIDE} (the hook saw frames "
        f"{sorted(set(frame.sub_frame))}); the cue is not where the test thinks"
    )
    assert WHITE in pixels.values() and DARK in pixels.values()
    expected = painted(stock[movie][INSIDE].rows, pixels)
    assert expected != stock[movie][INSIDE].rows, "painting the prediction changed nothing"
    wrong = differences(expected, frame.rows)
    assert not wrong, (
        f"{len(wrong)} pixels of {movie} k{INSIDE} differ from the stock frame plus its own "
        f"predicted text ({len(pixels)} predicted); first: {wrong[:8]}"
    )


@pytest.mark.parametrize("movie", MOVIES)
def test_the_other_movies_cue_is_not_drawn(movie, block, names, stock, patched):
    """The per-movie key. The other movie's cue covers this frame too, so a loader that
    ignored the movie -- milestone 1's, which had no key -- would draw it here. Every pixel
    it would have changed that this movie's own text does not cover shows the stock
    decode."""
    frame = patched[movie][INSIDE]
    own = predicted(block, names[movie], frame)
    theirs = predicted(block, names[other(movie)], frame)
    base = stock[movie][INSIDE].rows
    telling = {
        (x, y): colour
        for (x, y), colour in theirs.items()
        if (x, y) not in own and pixel(base[y], x) != bytes(colour)
    }
    assert len(telling) > 100, f"{other(movie)}'s cue would barely show over {movie}; vacuous"
    drawn = [
        (x, y) for (x, y), colour in telling.items() if pixel(frame.rows[y], x) == bytes(colour)
    ]
    assert not drawn, f"{len(drawn)} of {other(movie)}'s pixels are drawn over {movie}: {drawn[:8]}"


@pytest.mark.parametrize("movie", MOVIES)
def test_outside_the_cue_the_frame_is_byte_identical_to_the_stock_decode(
    movie, block, names, stock, patched
):
    for n in OUTSIDE[movie]:
        frame = patched[movie][n]
        assert predicted(block, names[movie], frame) == {}, f"{movie} k{n} is inside a cue"
        wrong = differences(stock[movie][n].rows, frame.rows)
        assert not wrong, f"{len(wrong)} pixels of {movie} k{n} changed; first {wrong[:8]}"
