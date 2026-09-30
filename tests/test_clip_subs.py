"""`VO-03`: `translation/clips.txt` rows become subtitles for native `g_xa_clips` plays.

The keys are built by `tests/synth_archive.py`; the words come out of the same
`lay_out_subtitle` a `(voice only)` event row goes through, so the timing is checked
against `boku.voice`, never retyped.
"""

from __future__ import annotations

import struct
from fractions import Fraction
from pathlib import Path

import pytest

from boku import clip_subs, epilogue
from boku.glyphs import END_WORD, NEWLINE_WORD, PAGE_WORD
from boku.layout import DIALOGUE_BAND, StockEncoder, lay_out_subtitle
from boku.voice import (
    SEEK_TICKS,
    VSYNC_HZ,
    VSYNCS_PER_TICK,
    clip_ticks,
    parse_xch,
    subtitle_waits,
    timed_waits,
)
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
    words, found = clip_subs.lay_out_clips(entries, CLIPS, StockEncoder.load(), {})
    assert found == []
    assert list(words) == [2], "a row without English is not a subtitle"
    laid = words[2]
    assert laid[-1] == END_WORD
    at = laid.index(PAGE_WORD)
    assert laid[at + 1] == subtitle_waits(["one", "two"], clip_ticks(KEYS[2]))[0]


def test_an_id_that_names_no_clip_is_a_problem(tmp_path):
    entries, _ = rows(tmp_path, "XCH.03\tNarrator\tx\nE0184.2\t(voice only)\ty\nXCH.1\tA\tz\n")
    words, found = clip_subs.lay_out_clips(entries, CLIPS, StockEncoder.load(), {})
    assert words == {}
    assert sorted(p.line_id for p in found) == ["E0184.2", "XCH.03", "XCH.1"]


def test_the_band_limits_apply(tmp_path):
    entries, _ = rows(tmp_path, "XCH.00\tNarrator\t" + " ".join(["wide"] * 60) + "\n")
    words, found = clip_subs.lay_out_clips(entries, CLIPS, StockEncoder.load(), {})
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
    words, found = clip_subs.lay_out_clips(entries, CLIPS, encoder, {})
    assert found == []
    assert NEWLINE_WORD in words[0], "a bug-sumo clip was laid out at the band's full width"


# --- a row's own page times, and what is on the screen when (PLAN VO-09) ----------------------

SHOUT = parse_xch(struct.pack("<I", 1) + synth.voice_key(start=0, end=0))
"""A one-sector clip: a tenth of a second."""
CARD = 200
PICTURE = {0: epilogue.Picture(ending=0, first_out=60, second_in=90, card=CARD, card_out=205)}
"""Clip 0 as an epilogue whose still gives way 200 vsyncs after its subtitle opens."""


def lines_of(tmp_path, text: str, clips=CLIPS, pictures=None):
    """The rows the build would take, and every problem."""
    entries, problems = rows(tmp_path, text)
    assert problems == []
    lines, found = clip_subs.lay_out_lines(entries, clips, StockEncoder.load(), pictures or {})
    return [line for line in lines if not line.problems], found


def messages(found) -> list[str]:
    return [problem.message for problem in found]


def test_timed_waits_count_each_page_in_ticks_from_the_second_the_one_before_gave_way():
    """30 Hz ticks of the console's 59.826 vsyncs a second, the lead counted once."""
    assert timed_waits([Fraction(1), Fraction(2), Fraction(7, 2)], 0) == [30, 30, 45]
    assert timed_waits([Fraction(1), Fraction(2)], 22) == [41, 30]
    assert timed_waits([], 22) == []
    assert min(timed_waits([Fraction(2), Fraction(1)], 0)) < 1, "times that fall are the caller's"


def test_a_row_with_times_turns_each_page_at_its_second_and_takes_the_last_down(tmp_path):
    lines, found = lines_of(tmp_path, "XCH.00\tBoy\tone // two\t2 4.5\n")
    assert found == []
    (line,) = lines
    lead = SEEK_TICKS * VSYNCS_PER_TICK
    first, last = timed_waits([Fraction(2), Fraction(9, 2)], lead)
    words = line.laid.words
    assert words[words.index(PAGE_WORD) + 1] == first
    assert words[-3:] == (PAGE_WORD, last, END_WORD), "the last page has no timer of its own"
    turn, down = VSYNCS_PER_TICK * first, VSYNCS_PER_TICK * (first + last)
    assert [(page.start, page.end) for page in line.pages] == [(0, turn), (turn, down)]
    assert abs(down - (lead + Fraction(9, 2) * VSYNC_HZ)) <= VSYNCS_PER_TICK
    assert down < line.until, "the fixture's last page comes down before its clip ends"


def test_a_row_without_times_keeps_its_last_page_until_the_clip_ends(tmp_path):
    lines, found = lines_of(tmp_path, "XCH.00\tBoy\tone // two\n")
    assert found == []
    (line,) = lines
    assert line.laid.words.count(PAGE_WORD) == 1
    assert line.pages[-1].end == line.until
    lead = SEEK_TICKS * VSYNCS_PER_TICK
    assert abs(line.until - lead - VSYNC_HZ * clip_ticks(KEYS[0]) / 30) <= 1


@pytest.mark.parametrize(
    ("times", "problem"),
    [
        ("2", "1 time(s) for 2 page(s)"),
        ("2 3 4", "3 time(s) for 2 page(s)"),
        ("4 2", "do not rise"),
        ("2 2", "do not rise"),
    ],
)
def test_times_that_do_not_fit_the_rows_pages_are_a_problem(tmp_path, times, problem):
    lines, found = lines_of(tmp_path, f"XCH.00\tBoy\tone // two\t{times}\n")
    assert lines == []
    assert [problem in message for message in messages(found)] == [True]


def test_times_that_are_not_numbers_are_a_problem_of_the_file(tmp_path):
    entries, problems = rows(tmp_path, "XCH.00\tBoy\tone // two\t2 soon\n")
    assert [e.ends for e in entries] == [()]
    assert len(problems) == 1 and "clips.txt:1" in problems[0] and "'2 soon'" in problems[0]


def test_a_page_timed_past_its_clips_end_is_a_page_nobody_sees(tmp_path):
    lines, found = lines_of(tmp_path, "XCH.00\tBoy\tone // two\t20 30\n")
    assert lines == []
    assert messages(found) == ["page 2 is up for 0.00 s; at least 1.5 s"]


def test_a_page_of_several_is_readable_from_a_second_and_a_half(tmp_path):
    """The floor is the 1.5 s the message names: 90 vsyncs of 59.826 a second pass, 88 do
    not. (Page 1 is up 22 vsyncs of seek before the clip's second 0.)"""
    assert clip_subs.MIN_SECONDS * VSYNC_HZ < 90
    lines, found = lines_of(tmp_path, "XCH.00\tBoy\tone // two\t1.14 5\n")
    assert found == [] and lines[0].pages[0].end == 90
    lines, found = lines_of(tmp_path, "XCH.00\tBoy\tone // two\t1.1 5\n")
    assert messages(found) == ["page 1 is up for 1.47 s; at least 1.5 s"]


def test_pages_too_many_for_their_clip_are_each_too_short_to_read(tmp_path):
    lines, found = lines_of(tmp_path, "XCH.00\tBoy\t" + " // ".join("abcdefgh") + "\n")
    assert lines == []
    assert len(found) == 8 and all("at least 1.5 s" in m for m in messages(found))


def test_a_page_asking_more_than_the_reading_rate_is_a_problem(tmp_path):
    crowded = "aaaa bbbb cccc dddd eeee ffff gggg hhhh"
    lines, found = lines_of(tmp_path, f"XCH.00\tBoy\t{crowded} // b\t1.6 5\n")
    assert lines == []
    (message,) = messages(found)
    assert message.startswith("page 1 is up for") and "characters a second; at most 17" in message


def test_one_page_without_times_is_up_as_long_as_its_clip_and_is_not_judged(tmp_path):
    """A bug-sumo shout of half a second: no row can make its clip longer."""
    lines, found = lines_of(tmp_path, "XCH.00\tBoy\tGo!\n", SHOUT)
    assert found == []
    assert lines[0].pages[0].seconds < clip_subs.MIN_SECONDS, "the fixture is not short"
    _, found = lines_of(tmp_path, "XCH.00\tBoy\tGo!\t0.1\n", SHOUT)
    assert ["at least 1.5 s" in m for m in messages(found)] == [True], "times are a claim"


def test_an_epilogue_page_still_up_when_the_still_gives_way_is_a_problem(tmp_path):
    """The harm of PLAN VO-09, at its narrowest: a page that goes on the card's own vsync
    is a problem, one that goes a tick before it is not."""
    lines, found = lines_of(tmp_path, "XCH.00\tBoy\tone // two\n", pictures=PICTURE)
    assert lines == []
    (message,) = messages(found)
    assert message.startswith("page 2 is up from") and "production card at 3.34 s" in message

    def second_page_ends(times: str) -> tuple[int, tuple[str, ...]]:
        entries, _ = rows(tmp_path, f"XCH.00\tBoy\tone // two\t{times}\n")
        (line,), _ = clip_subs.lay_out_lines(entries, CLIPS, StockEncoder.load(), PICTURE)
        return line.pages[-1].end, line.problems

    end, found = second_page_ends("1.6 3.23")
    assert end == CARD - VSYNCS_PER_TICK and found == ()
    end, found = second_page_ends("1.6 3.26")
    assert end == CARD
    assert len(found) == 1 and "production card" in found[0]


def test_an_epilogue_is_timed_from_its_own_lead_and_comes_down_when_the_game_moves_on(tmp_path):
    lines, _ = lines_of(tmp_path, "XCH.00\tBoy\tone // two\t1.6 3.2\n", pictures=PICTURE)
    (line,) = lines
    assert line.pages[0].end == VSYNCS_PER_TICK * timed_waits([Fraction(8, 5)], epilogue.LEAD)[0]
    assert line.until == PICTURE[0].end, "the clip outlasts the fixture's picture"


def without_times(tmp_path) -> Path:
    """The committed `clips.txt` with every row's times cut: PLAN VO-09 as Jay met it."""
    text = clip_subs.CLIP_FILE.read_text(encoding="utf-8")
    bare = tmp_path / "clips.txt"
    rows_ = ("\t".join(row.split("\t")[: clip_subs.TIMES_FIELD]) for row in text.split("\n"))
    bare.write_text("\n".join(rows_), encoding="utf-8")
    return bare


def timing_findings(path, disc_dir) -> list:
    """The lint's findings about when pages are up, whatever font the pages are measured in
    (the stock sheet fits no English; the times do not depend on it)."""
    from boku.lint import Options, lint_clip_file

    found = lint_clip_file(path, Options(encoder=StockEncoder.load()), disc_dir)
    return [f for f in found if " is up " in f.message]


def test_the_committed_epilogues_are_down_before_the_production_card(disc_dir):
    assert timing_findings(clip_subs.CLIP_FILE, disc_dir) == []


def test_the_committed_epilogues_without_their_times_end_under_the_production_card(
    tmp_path, disc_dir, archive
):
    """PLAN VO-09 as Jay met it: shared by length over the whole clip, whose tail is
    silence, every epilogue's last page is up after its still has gone -- `OTI02`'s and
    `OTI03`'s only then."""
    bare = without_times(tmp_path)
    found = timing_findings(bare, disc_dir)
    entries, _ = clip_subs.read(bare)
    pages = {e.line_id: len(e.pages) for e in entries}
    for clip in epilogue.pictures(archive):
        line_id = f"XCH.{clip}"
        mine = [f.message for f in found if f.line_id == line_id and "production card" in f.message]
        assert any(m.startswith(f"page {pages[line_id]} is up") for m in mine), line_id
