"""`boku.movie_timing`: each timing rule at its boundary, and what `retime` may and may not move."""

from __future__ import annotations

from fractions import Fraction

from boku import movie_timing as mt
from boku.movie_cues import CueRow

FPS = mt.FPS


def cue(start: int, end: int, chars: int, line: int = 1) -> CueRow:
    return CueRow("M60", start, end, "a" * chars, line)


def checks(found) -> list[str]:
    return [p.check for p in found]


def at_rate(frames: int, cps: int) -> int:
    """Characters that read at exactly `cps` over `frames` frames."""
    chars = Fraction(cps * frames, FPS)
    assert chars.denominator == 1, "pick frames the rate divides"
    return int(chars)


SEG = mt.Segment(100, 190)


def test_a_cue_that_matches_its_segment_passes():
    assert mt.problems([cue(100, 190, 20)], [SEG]) == []


def test_the_onset_rule_holds_at_its_boundary_either_side():
    for delta in (-mt.ONSET, mt.ONSET):
        assert mt.problems([cue(100 + delta, 190, 20)], [SEG]) == []
    for delta in (-mt.ONSET - 1, mt.ONSET + 1):
        assert checks(mt.problems([cue(100 + delta, 190, 20)], [SEG])) == ["cue-onset"]


def test_the_end_rule_allows_one_frame_early_and_no_more():
    assert mt.problems([cue(100, 190 - mt.END_SLACK, 20)], [SEG]) == []
    found = mt.problems([cue(100, 190 - mt.END_SLACK - 1, 20)], [SEG])
    assert checks(found) == ["cue-early-end"]


def test_the_shortest_cue_allowed_and_one_frame_shorter():
    seg = mt.Segment(100, 100 + mt.MIN_FRAMES - 1)
    assert mt.problems([cue(100, 100 + mt.MIN_FRAMES - 1, 5)], [seg]) == []
    seg = mt.Segment(100, 100 + mt.MIN_FRAMES - 2)
    assert checks(mt.problems([cue(100, 100 + mt.MIN_FRAMES - 2, 5)], [seg])) == ["cue-short"]


def test_the_reading_rate_counts_a_line_break_as_one_space_and_holds_at_the_limit():
    assert mt.characters("abc | def") == len("abc def")
    frames = 45  # 3 s
    exact = at_rate(frames, mt.MAX_CPS)
    seg = mt.Segment(100, 100 + frames - 1)
    assert mt.problems([cue(100, 100 + frames - 1, exact)], [seg]) == []
    assert checks(mt.problems([cue(100, 100 + frames - 1, exact + 1)], [seg])) == ["cue-fast"]


def test_speech_no_cue_covers_and_a_cue_over_no_speech_are_both_named():
    found = mt.problems([cue(500, 540, 5)], [SEG])
    assert sorted(checks(found)) == ["cue-unspoken", "speech-uncued"]


def test_the_first_and_last_cue_of_one_segment_carry_its_onset_and_end():
    """Two cues split one sentence: the rules bind the outer edges, not the split."""
    split = [cue(100, 140, 10, 1), cue(141, 190, 10, 2)]
    assert mt.problems(split, [SEG]) == []
    late = [cue(100, 140, 10, 1), cue(141, 180, 10, 2)]
    assert checks(mt.problems(late, [SEG])) == ["cue-early-end"]


def test_retime_moves_the_shared_boundary_to_fix_a_fast_cue_and_keeps_the_text():
    """One segment, two abutting cues, the first too fast for its frames: the split moves."""
    first = cue(100, 129, at_rate(30, 17) + 10, 1)  # over the limit by 10 characters
    second = cue(130, 190, 5, 2)
    assert checks(mt.problems([first, second], [SEG])) == ["cue-fast"]
    moved = mt.retime([first, second], [SEG], 400)
    assert mt.problems(moved, [SEG]) == []
    assert [c.text for c in moved] == [first.text, second.text]
    assert moved[0].start == 100 and moved[1].end == 190, "the outer edges had no reason to move"
    assert moved[0].end + 1 == moved[1].start, "abutting cues stay abutting"


def test_retime_never_breaks_a_rule_to_help_the_rate():
    """A cue too fast even at the latest end its segment allows keeps its onset and does not
    run past `LINGER` or into the next cue; `problems` still names the rate."""
    seg = mt.Segment(100, 130)
    hopeless = cue(100, 130, 200, 1)
    following = cue(170, 200, 5, 2)
    moved = mt.retime([hopeless, following], [seg, mt.Segment(170, 200)], 400)
    assert moved[0].start >= 100 - mt.ONSET
    assert moved[0].end <= min(130 + mt.LINGER, 169)
    assert moved[1] == following
    assert checks(mt.problems(moved, [seg, mt.Segment(170, 200)])) == ["cue-fast"]


def test_retime_leaves_cues_that_pass_where_they_are():
    good = [cue(100, 150, 10, 1), cue(151, 190, 10, 2)]
    assert mt.retime(good, [SEG], 400) == good


def test_a_retimed_file_changes_the_frames_of_the_moved_rows_and_nothing_else():
    text = "# note\nM60\t100\t129\tfirst | line\nM60\t130\t190\tsecond\n"
    moved = {("M60", 2): CueRow("M60", 100, 125, "first | line", 2)}
    assert (
        mt.retimed_file(text, moved)
        == "# note\nM60\t100\t125\tfirst | line\nM60\t130\t190\tsecond\n"
    )


def test_two_chains_moved_toward_each_other_never_overlap():
    """Each chain used to be bounded by where its neighbours *were*: the first one's end moved
    up to the second's old start while the second's start moved back to the first's old end."""
    segments = [mt.Segment(100, 150), mt.Segment(145, 200)]
    moved = mt.retime([cue(100, 140, 10, 1), cue(152, 200, 60, 2)], segments, 400)
    assert moved[0].end < moved[1].start, [(c.start, c.end) for c in moved]


def test_overlapping_cues_are_a_problem():
    found = mt.problems([cue(100, 149, 10, 1), cue(148, 200, 10, 2)], [mt.Segment(100, 200)])
    assert "cue-overlap" in checks(found)


def test_a_chain_whose_onset_window_is_taken_by_the_cue_before_keeps_its_start():
    """The previous cue already runs past this speech's onset window: no start is legal, and
    the chain keeps the one it had instead of raising."""
    segments = [mt.Segment(100, 180), mt.Segment(170, 250)]
    cues = [cue(100, 180, 10, 1), cue(190, 250, 10, 2)]
    assert mt.retime(cues, segments, 400)[1].start == 190
