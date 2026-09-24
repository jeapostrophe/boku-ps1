"""`boku.movie_timing`: each timing rule at its boundary, and what `retime` may and may not move."""

from __future__ import annotations

from fractions import Fraction

from boku import movie_timing as mt
from boku.movie_cues import CueRow

FPS = mt.FPS


def cue(start: int, end: int, chars: int, line: int = 1) -> CueRow:
    """A narrated cue (a `Segment`'s default kind) reading `chars` characters."""
    opening, closing = mt.NARRATION_MARKS
    return CueRow("M60", start, end, opening + "a" * chars + closing, line)


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


def test_retime_holds_a_fast_cue_past_its_speech_into_the_silence_after():
    """Jay, 2026-09-24: a cue may stay on screen longer than its speech to be read. A cue whose
    speech is 100-130 needs 75 frames for its text, 7 more than the onset window and `LINGER`
    give: it holds past `LINGER` without leaving its onset window, and `problems` accepts it."""
    seg = mt.Segment(100, 130)
    fast = cue(100, 130, at_rate(75, mt.MAX_CPS), 1)
    in_sync = seg.end + mt.LINGER - (seg.start - mt.ONSET) + 1
    assert in_sync == 75 - 7, "the fixture needs 7 frames more than sync gives"
    moved = mt.retime([fast], [seg], 400)
    start, end = moved[0].start, moved[0].end
    assert end - start + 1 == 75
    assert start >= seg.start - mt.ONSET and end > seg.end + mt.LINGER
    assert mt.problems(moved, [seg]) == []


def test_retime_never_holds_a_cue_into_the_next_one_or_past_its_drift():
    """Held as long as the gap allows, never into the next cue; with no next cue, never past
    `LINGER` + `DRIFT` after its speech. `problems` still names the rate."""
    seg, later = mt.Segment(100, 130), mt.Segment(170, 200)
    hopeless = cue(100, 130, 200, 1)
    following = cue(170, 200, 5, 2)
    moved = mt.retime([hopeless, following], [seg, later], 400)
    assert moved[0].end == 169 and moved[1] == following
    assert checks(mt.problems(moved, [seg, later])) == ["cue-fast"]
    alone = mt.retime([hopeless], [seg], 400)[0]
    assert alone.end == 130 + mt.LINGER + mt.DRIFT
    assert alone.start >= 100 - mt.ONSET - mt.DRIFT


def test_in_continuous_speech_a_fast_cue_borrows_frames_across_a_segment_boundary():
    """The M27 shape: speech with no pause, one cue per segment, the middle one too fast for
    its segment. Its boundaries leave the speech -- the cue before ends early, the one after
    starts late -- by no more than reading needs, and `problems` accepts both."""
    segments = [mt.Segment(100, 160), mt.Segment(160, 220), mt.Segment(220, 280)]
    cues = [cue(100, 159, 20, 1), cue(160, 219, at_rate(90, mt.MAX_CPS), 2), cue(220, 280, 20, 3)]
    assert checks(mt.problems(cues, segments)) == ["cue-fast"]
    moved = mt.retime(cues, segments, 400)
    assert mt.problems(moved, segments) == [], [(c.start, c.end) for c in moved]
    assert moved[1].end - moved[1].start + 1 == 90, "exactly the frames its text needs"
    assert moved[0].start == 100 and moved[2].end == 280, "the outer edges had no reason to move"


def test_a_start_off_its_speech_passes_only_when_the_cue_before_needs_the_frames():
    """The checker's side of the hold: a late start is accepted when moving it back into the
    onset window would leave the abutting cue before it too fast -- and not otherwise."""
    segments = [mt.Segment(100, 160), mt.Segment(160, 220)]
    late = 160 + mt.ONSET + 10
    needy = [cue(100, late - 1, at_rate(75, mt.MAX_CPS), 1), cue(late, 220, 10, 2)]
    assert mt.problems(needy, segments) == []
    idle = [cue(100, late - 1, 10, 1), cue(late, 220, 10, 2)]
    assert checks(mt.problems(idle, segments)) == ["cue-onset"]
    latest = 160 + mt.ONSET + mt.DRIFT
    edge = [cue(100, latest - 1, 200, 1), cue(latest, 240, 10, 2)]
    assert "cue-onset" not in checks(mt.problems(edge, segments))
    far = [cue(100, latest, 200, 1), cue(latest + 1, 240, 10, 2)]
    assert "cue-onset" in checks(mt.problems(far, segments))


def test_an_early_end_passes_only_when_the_cue_after_needs_the_frames():
    """The same for a segment's last cue ending before its speech does: accepted when ending
    on time would leave the abutting cue after it too fast, flagged when it would not."""
    segments = [mt.Segment(100, 160), mt.Segment(160, 220)]
    early = 160 - mt.END_SLACK - 10
    needy = [cue(100, early, 20, 1), cue(early + 1, 220, at_rate(75, mt.MAX_CPS), 2)]
    assert "cue-early-end" not in checks(mt.problems(needy, segments))
    idle = [cue(100, early, 20, 1), cue(early + 1, 220, 10, 2)]
    assert "cue-early-end" in checks(mt.problems(idle, segments))


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


def test_a_chain_whose_onset_window_is_taken_by_the_cue_before_starts_as_near_as_it_can():
    """The previous cue already runs past this speech's onset window: no start is in sync, and
    the chain starts right after that cue, the nearest frame to its speech, instead of raising."""
    segments = [mt.Segment(100, 180), mt.Segment(170, 250)]
    cues = [cue(100, 180, 10, 1), cue(190, 250, 10, 2)]
    assert mt.retime(cues, segments, 400)[1].start == 181


def test_sung_lines_are_timed_like_narration_and_music_is_not(tmp_path):
    """The theme song is subtitled (FMV-02), so its segments bind cues as narration does."""
    path = tmp_path / "M28.ja.tsv"
    path.write_text(
        "start_s\tend_s\tstart_frame\tend_frame\tkind\tconf\tja\tnote\n"
        "0\t1\t1\t961\tmusic\tok\t\t\n"
        "1\t2\t961\t1044\tnarration\tok\t\t\n"
        "2\t3\t1044\t1159\tsong\tok\t\t\n"
        "3\t4\t1159\t1200\tvoice\tok\t\t\n",
        encoding="utf-8",
    )
    assert mt.read_segments(path) == [
        mt.Segment(961, 1044, "narration"),
        mt.Segment(1044, 1159, "song"),
    ]


def test_a_cue_starting_before_its_onset_window_is_pulled_back_into_it():
    """Nothing needs the early frames, so `retime` must not keep any of them."""
    seg = mt.Segment(100, 160)
    moved = mt.retime([cue(80, 160, 10)], [seg], 400)
    assert mt.problems(moved, [seg]) == [], [(c.start, c.end) for c in moved]


def test_abutting_cues_across_a_long_silence_keep_the_next_cue_on_its_onset():
    """The first cue holds through the silence to the next cue, which starts on its speech:
    both pass, and the end-of-speech `LINGER` cap must not drag the second one off it."""
    segments = [mt.Segment(100, 130), mt.Segment(200, 230)]
    cues = [cue(100, 199, 10, 1), cue(200, 230, 10, 2)]
    assert mt.problems(cues, segments) == []
    assert mt.problems(mt.retime(cues, segments, 400), segments) == []


def test_the_narration_marks_are_not_read_so_they_do_not_count_toward_the_rate():
    assert mt.characters("『abc | def』") == len("abc def")


def test_a_narrated_cue_takes_the_narration_marks_and_a_sung_one_does_not():
    """FMV-07: the adult Boku's narration is marked 『 』 as the dialogue's narration is; the
    theme song is not narration. The transcript's `kind` says which a cue is."""
    spoken = mt.Segment(100, 190, "narration")
    sung = mt.Segment(100, 190, "song")
    marked = CueRow("M60", 100, 190, "『aaaa | aaaa』", 1)
    bare = CueRow("M60", 100, 190, "aaaa | aaaa", 1)
    assert mt.problems([marked], [spoken]) == []
    assert checks(mt.problems([bare], [spoken])) == ["cue-marks"]
    assert mt.problems([bare], [sung]) == []
    assert checks(mt.problems([marked], [sung])) == ["cue-marks"]
    for wrong in ("『aaaa | aaaa", "『aaaa』 | aaaa"):
        stray = CueRow("M60", 100, 190, wrong, 1)
        assert checks(mt.problems([stray], [spoken])) == ["cue-marks"], wrong


def test_a_caption_of_writing_on_screen_is_held_to_no_speech():
    """FMV-08: a caption over silence is not `cue-unspoken`, carries no marks, and does not
    take a segment it overlaps from the cue that subtitles it; its reading rate still counts."""
    caption = CueRow("M27", 300, 374, "a" * 60, 1, caption=True)
    assert mt.problems([caption], []) == []
    over = CueRow("M27", 151, 171, "a" * 60, 2, caption=True)
    found = mt.problems([cue(100, 149, 10, 1), over], [SEG])
    assert sorted(checks(found)) == ["cue-early-end", "cue-fast", "cue-short"]


def test_a_captions_frames_are_the_pictures_and_no_neighbour_borrows_them():
    """A caption's frames are fixed by the writing on screen: `retime` never moves them, and
    a narrated cue ending early before one is not excused by the caption's rate."""
    narrated = cue(100, 160, 10, 1)
    caption = CueRow("M27", 161, 200, "a" * 60, 2, caption=True)
    moved = mt.retime([narrated, caption], [SEG], 400)
    assert moved[1] == caption, [(c.start, c.end) for c in moved]
    found = mt.problems([narrated, caption], [SEG])
    assert "cue-early-end" in checks(found)
    before = CueRow("M27", 40, 99, "a" * 60, 1, caption=True)
    late = cue(100 + mt.ONSET + 1, 190, 10, 2)
    assert mt.retime([before, late], [SEG], 400)[0] == before
