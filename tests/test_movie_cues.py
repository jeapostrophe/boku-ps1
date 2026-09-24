"""`boku.movie_cues`: the cue file's rows, and every rule the lint and the build hold them to."""

from __future__ import annotations

import pytest

from boku import movie_cues as mc
from boku.layout import CellMapEncoder
from boku.movie_block import LINE_WIDTH, POSITIONS, Cue

ADVANCE = 6
"""Every character of `FONT` steps 6 px, so a width is `6 * len(text)`; `LINE_WIDTH` (318)
is 53 of them."""
FONT = CellMapEncoder(
    {c: (i, ADVANCE) for i, c in enumerate("abcdefghijklmnopqrstuvwxyz ,.")}, name="test"
)
FULL = LINE_WIDTH // ADVANCE
LENGTHS = {"M27": 4239, "M60": 362}

TSV = """# a comment line, as the generated file carries
id\tfile\tframes\tseconds\tstop_frame\tskippable
0\tM27\t4244\t3.9\t58\tyes
23\tM27\t4244\t282.6\t4239\tyes
21\tM60\t367\t24.1\t362\tyes
"""


def rows(*specs: tuple[str, int, int, str]) -> list[mc.CueRow]:
    return [mc.CueRow(movie, s, e, text, n) for n, (movie, s, e, text) in enumerate(specs, 1)]


def checks(found: list[mc.Problem]) -> list[str]:
    return [problem.check for problem in found]


def test_a_row_is_four_or_five_tab_separated_fields_and_notes_are_skipped():
    text = "# the opening\n\nM27\t120\t300\tfar away\nM27\t1\t2\n  # indented note\nM60\tx\t3\ta\n"
    found, problems = mc.parse(text)
    assert found == [mc.CueRow("M27", 120, 300, "far away", 3)]
    assert [(p.line, p.check) for p in problems] == [(4, "cue-malformed"), (6, "cue-malformed")]


def test_a_fifth_field_places_the_cue_and_anything_but_a_position_is_malformed():
    text = "M28\t1\t2\ta\ttop\nM28\t3\t4\tb\tbottom\nM28\t5\t6\tc\tmiddle\nM28\t7\t8\td\t\n"
    found, problems = mc.parse(text)
    assert found == [
        mc.CueRow("M28", 1, 2, "a", 1, "top"),
        mc.CueRow("M28", 3, 4, "b", 2),
        mc.CueRow("M28", 7, 8, "d", 4),  # an empty position field is the default
    ]
    assert [(p.line, p.check) for p in problems] == [(3, "cue-malformed")]
    assert "top" in problems[0].message and "bottom" in problems[0].message


def test_a_files_length_is_the_last_frame_any_id_playing_it_shows():
    """The opening's file is played by an id stopping at 58 and one at 4,239."""
    assert mc.movie_lengths(TSV) == {"M27": 4239, "M60": 362}


def test_the_committed_movie_list_names_every_file_once():
    lengths = mc.read_movie_lengths()
    assert "M27" in lengths and "M28" in lengths and all(n > 0 for n in lengths.values())


def test_a_clean_file_has_no_problems():
    assert mc.check(rows(("M27", 1, 4239, "a b"), ("M60", 1, 362, "c")), LENGTHS, FONT) == []


@pytest.mark.parametrize(
    ("spec", "check"),
    [
        (("M99", 1, 2, "a"), "cue-movie"),
        (("M60", 0, 2, "a"), "cue-frames"),
        (("M60", 5, 4, "a"), "cue-frames"),
        (("M60", 1, 363, "a"), "cue-frames"),
        (("M60", 1, 2, ""), "cue-empty"),
        (("M60", 1, 2, "a | "), "cue-empty"),
        (("M60", 1, 2, "a!"), "cue-unencodable"),
        (("M60", 1, 2, "a" * (FULL + 1)), "cue-width"),
        (("M60", 1, 2, "a | b | c"), "cue-lines"),
    ],
)
def test_each_rule_names_its_row(spec, check):
    (problem,) = mc.check(rows(spec), LENGTHS, FONT)
    assert (problem.check, problem.line, problem.key) == (check, 1, f"{spec[0]}@{spec[1]}")


def test_a_cue_may_end_on_the_movies_last_frame_and_fill_the_band_exactly():
    assert mc.check(rows(("M60", 362, 362, "a" * FULL)), LENGTHS, FONT) == []


def test_wrapping_breaks_at_the_band_width_and_a_third_line_is_refused():
    word = "a" * (FULL // 2)
    two = " ".join([word] * 3)
    assert mc.cue_lines(two, FONT) == (f"{word} {word}", word)
    assert mc.check(rows(("M60", 1, 2, two)), LENGTHS, FONT) == []
    assert checks(mc.check(rows(("M60", 1, 2, " ".join([word] * 5))), LENGTHS, FONT)) == [
        "cue-lines"
    ]


def test_a_forced_break_is_kept_even_where_the_wrap_would_have_joined_the_lines():
    assert mc.cue_lines("a | b", FONT) == ("a", "b")


def test_a_forced_line_too_wide_is_not_rewrapped_but_reported():
    found = mc.check(rows(("M60", 1, 2, "a | " + "b" * (FULL + 1))), LENGTHS, FONT)
    assert checks(found) == ["cue-width"]


def test_cues_of_one_movie_may_touch_but_not_overlap():
    assert mc.check(rows(("M60", 1, 10, "a"), ("M60", 11, 20, "b")), LENGTHS, FONT) == []
    found = mc.check(rows(("M60", 11, 20, "b"), ("M60", 1, 11, "a")), LENGTHS, FONT)
    assert [(p.check, p.key) for p in found] == [("cue-overlap", "M60@11")]


def test_cues_of_two_movies_over_the_same_frames_are_not_an_overlap():
    assert mc.check(rows(("M27", 1, 10, "a"), ("M60", 1, 10, "b")), LENGTHS, FONT) == []


def test_without_a_font_the_pixel_rules_are_not_measured():
    spec = ("M60", 1, 2, "!" * (FULL + 1))
    assert mc.check(rows(spec), LENGTHS, None) == []
    assert checks(mc.check(rows(("M60", 0, 2, "a")), LENGTHS, None)) == ["cue-frames"]


def test_the_build_gets_each_movies_cues_in_frame_order_as_laid_out():
    found = mc.cues_by_movie(
        rows(("M60", 20, 30, "b"), ("M27", 5, 6, "a | c"), ("M60", 1, 2, "a")), FONT
    )
    assert found == {
        "M27": [Cue(5, 6, ("a", "c"))],
        "M60": [Cue(1, 2, ("a",)), Cue(20, 30, ("b",))],
    }


def test_a_top_cue_is_laid_out_on_the_top_rows():
    (cue,) = mc.cues_by_movie([mc.CueRow("M28", 1, 2, "a | b", 1, "top")], FONT)["M28"]
    assert cue == Cue(1, 2, ("a", "b"), POSITIONS["top"])


def test_the_committed_cue_file_parses_and_holds_to_the_movie_list():
    """Every row of `translation/movies.txt` against the tracked movie list; the pixel
    rules need the font build and are the lint's (`./make.sh lint-translation`)."""
    found, problems = mc.read()
    assert problems == []
    assert mc.check(found, mc.read_movie_lengths(), None) == []
