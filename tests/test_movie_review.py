"""`tools/libretro/movie_review.py`'s arithmetic: where to aim a shot, and the table pokes."""

from __future__ import annotations

import importlib.util
import struct
import sys
from functools import cache

import pytest

from boku import REPO_ROOT
from boku.movie_block import MOVIE_ENTRY_FRAMES, MOVIE_ENTRY_SIZE, MOVIE_TABLE


@cache
def tool():
    path = REPO_ROOT / "tools" / "libretro" / "movie_review.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("movie_review", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SAMPLES = [(1200, 20), (1300, 45), (1400, 70)]
"""What `review_movie` hands `aim`: samples while the movie plays, 25 STR frames per 100
vsyncs (it drops those before the first frame and at the stop frame, which have no rate)."""


def test_a_frame_between_two_samples_is_interpolated():
    assert tool().aim(SAMPLES, 45) == 1300
    assert tool().aim(SAMPLES, 50) == 1320


def test_a_frame_outside_the_samples_extrapolates_at_the_nearest_pairs_rate():
    """A cue in a movie's first `SAMPLE` vsyncs is before the first sample; one past the last
    sample is after it."""
    assert tool().aim(SAMPLES, 10) == 1160
    assert tool().aim(SAMPLES, 80) == 1440


def test_samples_with_no_movie_are_refused():
    with pytest.raises(ValueError, match="no movie playing"):
        tool().aim([(1000, 30), (1100, 30)], 5)


def test_the_pokes_rewrite_the_openings_entry_name_and_stop_frame():
    entry = MOVIE_TABLE + MOVIE_ENTRY_SIZE * tool().OPENING
    pokes = tool().entry_pokes(0x8002A19C, 362, at=7)
    assert pokes == [
        f"7:{entry:08X}={struct.pack('<I', 0x8002A19C).hex()}",
        f"7:{entry + MOVIE_ENTRY_FRAMES:08X}={struct.pack('<I', 362).hex()}",
    ]
