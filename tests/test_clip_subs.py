"""`VO-03`: `translation/clips.txt` rows become subtitles for native `g_xa_clips` plays.

The keys are built by `tests/synth_archive.py`; the words come out of the same
`lay_out_subtitle` a `(voice only)` event row goes through, so the timing is checked
against `boku.voice`, never retyped.
"""

from __future__ import annotations

import struct

import pytest

from boku import clip_subs
from boku.glyphs import END_WORD, NEWLINE_WORD, PAGE_WORD
from boku.layout import DIALOGUE_BAND, StockEncoder, lay_out_subtitle
from boku.voice import clip_ticks, parse_xch, subtitle_waits
from tests import synth_archive as synth

KEYS = [synth.voice_key(start=16 * k, end=16 * k + 16 * 50) for k in range(3)]
CLIPS = parse_xch(struct.pack("<I", len(KEYS)) + b"".join(KEYS))
"""A three-clip table, read by the parser `boku.voice.xch_nodes` uses on the disc's."""


def rows(tmp_path, text: str):
    path = tmp_path / "clips.txt"
    path.write_text(text, encoding="utf-8")
    return clip_subs.read(path)


def test_the_committed_file_reads_cleanly():
    entries, problems = clip_subs.read()
    assert problems == []
    assert entries, "clips.txt carries the bedtime, epilogue and bug-sumo English (PLAN VO-04)"


def test_a_missing_file_is_no_rows(tmp_path):
    assert clip_subs.read(tmp_path / "absent.txt") == ([], [])


def test_a_row_is_paged_against_its_own_clip(tmp_path):
    entries, problems = rows(tmp_path, "XCH.02\tNarrator\tone // two\nXCH.01\tNarrator\n")
    assert problems == []
    words, found = clip_subs.lay_out_clips(entries, CLIPS, StockEncoder.load())
    assert found == []
    assert list(words) == [2], "a row without English is not a subtitle"
    laid = words[2]
    assert laid[-1] == END_WORD
    at = laid.index(PAGE_WORD)
    assert laid[at + 1] == subtitle_waits(["one", "two"], clip_ticks(KEYS[2]))[0]


def test_an_id_that_names_no_clip_is_a_problem(tmp_path):
    entries, _ = rows(tmp_path, "XCH.03\tNarrator\tx\nE0184.2\t(voice only)\ty\nXCH.1\tA\tz\n")
    words, found = clip_subs.lay_out_clips(entries, CLIPS, StockEncoder.load())
    assert words == {}
    assert sorted(p.line_id for p in found) == ["E0184.2", "XCH.03", "XCH.1"]


def test_the_band_limits_apply(tmp_path):
    entries, _ = rows(tmp_path, "XCH.00\tNarrator\t" + " ".join(["wide"] * 60) + "\n")
    words, found = clip_subs.lay_out_clips(entries, CLIPS, StockEncoder.load())
    assert words == {} and any("lines in" in p.message for p in found)


def test_the_lint_reports_a_clip_row_by_file_line_and_id(tmp_path, disc_dir):
    """`boku lint` over `translation/clips.txt`: the same layout as the build, keyed to the
    disc's own `BOKU_XA.XCH`, so an id past its records and a page too long are both errors."""
    from boku.lint import Options, lint_clip_file

    path = tmp_path / "clips.txt"
    path.write_text(
        "XCH.34\tNarrator\t" + " ".join(["wide"] * 60) + "\nXCH.99\tNarrator\tx\n",
        encoding="utf-8",
    )
    found = lint_clip_file(path, Options(encoder=StockEncoder.load()), disc_dir)
    assert [(f.number, f.line_id, f.check) for f in found] == [
        (1, "XCH.34", "clip-subtitle"),
        (2, "XCH.99", "clip-subtitle"),
    ]


def test_the_committed_clips_fit_the_band_in_the_builds_own_font(disc_dir):
    """The committed English measured the way the build lays it out: in the VWF cell map
    (`./make.sh build-days` writes it), not the stock full-width sheet, which no English fits."""
    from boku.lint import DEFAULT_CELLS, Options, lint_clip_file, make_encoder

    if not DEFAULT_CELLS.is_file():
        pytest.skip(f"{DEFAULT_CELLS} is not built; run ./make.sh build-days")
    encoder = make_encoder("cellmap", None)
    assert lint_clip_file(clip_subs.CLIP_FILE, Options(encoder=encoder), disc_dir) == []


def test_a_bug_sumo_clip_wraps_clear_of_boku_s_portrait(tmp_path):
    """`VO-06`: bug sumo draws the subtitle `SUMO_PEN_INDENT` px right of the band's pen, so
    a line the band holds whole at its own pen wraps there -- the longest one-line text of
    the band's width is the fixture, found against the band itself."""
    encoder = StockEncoder.load()
    ticks = clip_ticks(KEYS[0])
    text = "go"
    while NEWLINE_WORD not in lay_out_subtitle("x", [text + " go"], ticks, encoder).words:
        text += " go"
    assert clip_subs.clip_box(34) == DIALOGUE_BAND, "the bedtime clip keeps the band's width"
    entries, _ = rows(tmp_path, f"XCH.00\tBoy\t{text}\n")
    words, found = clip_subs.lay_out_clips(entries, CLIPS, encoder)
    assert found == []
    assert NEWLINE_WORD in words[0], "a bug-sumo clip was laid out at the band's full width"
