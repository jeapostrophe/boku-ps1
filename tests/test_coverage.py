"""`boku coverage` -- per day, which lines the player meets are English and why not.

Each test builds a store and a translation that agree, changes **one** thing, and asserts
the report says the thing that changed -- the state *and* the reason, because the whole
value of this tool is the reason. The fixtures are `tests.synth_script`'s, so nothing here
holds the game's text, and the manifest fixtures are written in the shape
`boku.build.manifest_json` emits rather than a shape retyped here: the two keys this tool
reads are taken off that function's own document (`~/.claude/CLAUDE.md` ENG-1).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.coverage import (
    ANY_DAY,
    BUILD_FIELD,
    BUILD_ID_NAME,
    DAY,
    MEMBER_FIELD,
    MISSING,
    NOT_EVENT,
    REFUSED,
    REFUSED_FIELD,
    RELOCATIONS_FIELD,
    RESULT_SHA1_FIELD,
    SURFACE,
    TRANSLATED,
    WRITTEN_FIELD,
    CoverageError,
    Manifest,
    coverage,
    format_moved,
    format_report,
    main_coverage,
    moved_lines,
    summarise,
)
from boku.lint import load_rows, translation_paths
from boku.script_store import (
    day_allows,
    load_store,
    ordered_scenes,
    scene_dated_day,
    scene_day,
    scenes_of_day,
)
from tests.synth_script import SynthStore, write_translation

DAY_EVENT = "E0199"
"""Id 199: `id // 100 == 1`, the day files' own rule."""
DATED_EVENT = "E5199"
"""Id 5199, so `id // 100` is 51 -- but the data dates it to day 1."""
FREE_EVENT = "E8199"
"""No day in the data: a `shared.txt` event."""
LATE_EVENT = "E8299"
"""No day in the data either, but its condition cannot be true on day 1."""
BRANCH_EVENT = "E8399"
"""No day in the data, and its condition's one `day==N` sits in a branch of an `|`."""
BRANCH_CONDITION = "((hour<18 & day!=15) | (day==11 & hour>19))"
"""`script_store.scene_day` derives day 11 from this; the left branch plays on day 1."""
BRANCH_DAY = 11
ARRAY = "exe@80000000.0"

A, B, C = f"{DAY_EVENT}.0", f"{DAY_EVENT}.1", f"{DAY_EVENT}.2"
DATED = f"{DATED_EVENT}.0"
FREE = f"{FREE_EVENT}.0"
LATE = f"{LATE_EVENT}.0"
BRANCH = f"{BRANCH_EVENT}.0"


@pytest.fixture
def store(tmp_path: Path):
    """Three day-1 lines, one dated elsewhere, three day-independent, one array item."""
    synth = SynthStore.new(tmp_path)
    for line_id in (A, B, C, DATED, FREE, LATE, BRANCH):
        synth.message(line_id, [[4]], voiced=True)
    synth.array_item(ARRAY, cells=4)
    synth.scene(DAY_EVENT, [A, B, C], day=1)
    synth.scene(DATED_EVENT, [DATED], day=1)
    free = synth.scene(FREE_EVENT, [FREE], day=None)
    free["when"]["condition"] = None
    free["when"]["meal_hour"] = None
    late = synth.scene(LATE_EVENT, [LATE], day=None)
    late["when"]["condition"] = "(hour<18 & day>7)"
    late["when"]["meal_hour"] = None
    branch = synth.scene(BRANCH_EVENT, [BRANCH], day=None)
    branch["when"]["condition"] = BRANCH_CONDITION
    branch["when"]["meal_hour"] = None
    return load_store(synth.write())


ENGLISH = [
    (A, "Uncle", "One."),
    (B, "Uncle", "Two."),
    (C, "Boku", "Three."),
    (DATED, "Uncle", "Four."),
    (FREE, "Aunt", "Five."),
    (LATE, "Aunt", "Six."),
]

WROTE = [line_id for line_id, *_ in ENGLISH if line_id != LATE]
"""What a build that fitted all of it lists under `lines_written` -- read off `ENGLISH`
rather than retyped, less `LATE`, which day 1 does not reach."""
WITHOUT_B = [line_id for line_id in WROTE if line_id != B]
"""The same build with `B` left out, for the tests that make one line the odd one."""


@pytest.fixture
def rows(tmp_path: Path):
    return read_rows(write_translation(tmp_path / "day01.txt", ENGLISH))


@pytest.fixture
def written(tmp_path: Path):
    """`main_coverage`'s two file inputs: a translation, and a build that wrote all of it."""
    path = write_translation(tmp_path / "day01.txt", ENGLISH)
    manifest = tmp_path / "m.json"
    write_manifest(manifest, WROTE)
    return path, manifest


def read_rows(*paths: Path):
    parsed, _ = load_rows(translation_paths(list(paths)))
    return parsed


def write_manifest(path: Path, written, refused=None, relocated=()) -> Manifest:
    """A manifest holding only the fields this tool reads, in the build's own shape."""
    path.write_text(
        json.dumps(
            {
                "format": 1,
                "build": "days",
                "result_sha1": "0123456789abcdef0123456789abcdef01234567",
                "lines_written": sorted(written),
                "lines_refused": {k: list(v) for k, v in (refused or {}).items()},
                "relocations": [
                    {"member": member, "from_lba": 10, "to_lba": 20} for member in relocated
                ],
            }
        ),
        encoding="utf-8",
    )
    return Manifest.load(path)


def member_of(store, line_id: str) -> str:
    """The member a line's bytes live in, read off the store rather than retyped."""
    return store.lines[line_id]["sites"][0]["member"]


UNCHECKED = Manifest.unchecked()
"""No manifest at all -- English existing is all the report can say."""


def by_id(results):
    return {result.line_id: result for result in results}


def states(results):
    return {result.line_id: result.state for result in results}


# --- the four states -------------------------------------------------------------------------


def test_a_line_the_build_wrote_is_translated(store, rows, tmp_path):
    manifest = write_manifest(tmp_path / "m.json", WROTE)
    result = by_id(coverage(store, rows, 1, manifest))[A]
    assert result.state == TRANSLATED
    assert result.origin.startswith("day01.txt:")


def test_a_line_the_build_refused_is_refused_and_carries_the_builds_own_reason(
    store, rows, tmp_path
):
    """The shape of the day-1 evening bug: English exists, the image still holds Japanese."""
    excuse = "E0199.1 page 2: 4 lines in the dialogue band, which holds 3"
    manifest = write_manifest(tmp_path / "m.json", WITHOUT_B, {B: [excuse]})
    result = by_id(coverage(store, rows, 1, manifest))[B]
    assert result.state == REFUSED
    assert excuse in result.reason


def test_a_line_with_no_row_is_missing(store, tmp_path):
    """The narrowest case: one line of a translated event was never given to a translator."""
    rows = read_rows(write_translation(tmp_path / "day01.txt", [r for r in ENGLISH if r[0] != B]))
    manifest = write_manifest(tmp_path / "m.json", WITHOUT_B)
    result = by_id(coverage(store, rows, 1, manifest))[B]
    assert result.state == MISSING
    assert "no row" in result.reason


def test_a_voice_only_row_is_not_a_translation(store, tmp_path):
    """`(voice only)` says the disc has no text -- and here the disc does have text."""
    listed = [(r[0], "(voice only)", "") if r[0] == B else r for r in ENGLISH]
    rows = read_rows(write_translation(tmp_path / "day01.txt", listed))
    result = by_id(coverage(store, rows, 1, write_manifest(tmp_path / "m.json", [A, C])))[B]
    assert result.state == MISSING
    assert "voice only" in result.reason


def test_a_row_the_build_neither_wrote_nor_refused_is_refused_and_says_so(store, rows, tmp_path):
    """English exists and the image has neither it nor a refusal -- not a silent pass."""
    manifest = write_manifest(tmp_path / "m.json", WITHOUT_B)
    result = by_id(coverage(store, rows, 1, manifest))[B]
    assert result.state == REFUSED
    assert "neither" in result.reason and manifest.name in result.reason


def test_an_array_id_is_not_event_and_names_its_surface(store, rows, tmp_path):
    result = by_id(coverage(store, rows, 1, write_manifest(tmp_path / "m.json", [])))[ARRAY]
    assert result.state == NOT_EVENT
    assert result.scope == SURFACE
    assert result.group == "exe"
    assert "exe" in result.reason


def test_an_array_line_with_english_is_classified_like_any_other(store, tmp_path):
    """`translation/days/arrays.txt` gives the surfaces English (`TRN-09`); a line with a
    row is then translated or refused by the manifest, not `not-event` for ever."""
    rows = read_rows(write_translation(tmp_path / "arrays.txt", [(ARRAY, "(unlabelled)", "Kite")]))
    result = by_id(coverage(store, rows, 1, UNCHECKED))[ARRAY]
    assert result.scope == SURFACE
    assert result.state == TRANSLATED


def test_an_array_line_written_voice_only_is_missing_not_waiting(store, tmp_path):
    """Every surface line has text on the disc; `(voice only)` for one is a mistake, and
    it is named as one rather than hidden behind "no English yet"."""
    rows = read_rows(write_translation(tmp_path / "arrays.txt", [(ARRAY, "(voice only)", "")]))
    result = by_id(coverage(store, rows, 1, UNCHECKED))[ARRAY]
    assert result.state == MISSING
    assert "voice only" in result.reason


def test_a_line_an_event_reaches_but_does_not_list_is_reported_under_that_event(tmp_path):
    """A scene's `lines` and its nodes' `line`s are not the same set. A node can name an
    id with text that `lines` leaves out; reading only `lines` drops it, and a line the
    player meets that the report never mentions is exactly this tool's one fatal bug."""
    listed, reached = "E0188.0", "E0188.1"
    synth = SynthStore.new(tmp_path / "reached")
    synth.message(listed, [[4]], voiced=True)
    synth.message(reached, [[4]], voiced=True)
    synth.scene("E0188", [listed], voice_only=[reached], day=1)
    unlisted = load_store(synth.write())
    result = by_id(coverage(unlisted, [], 1, UNCHECKED))[reached]
    assert result.scope == DAY
    assert result.group == "E0188"
    assert result.state == MISSING


def test_a_record_no_scene_claims_is_reported_rather_than_lost(rows, tmp_path):
    """The report walks events; a line the extract wrote that no event lists must still
    appear, or the one line nothing accounts for is the one line nothing accounts for."""
    orphan = "E7777.0"
    synth = SynthStore.new(tmp_path / "orphan")
    synth.message(orphan, [[4]], voiced=False)
    unclaimed = load_store(synth.write())
    result = by_id(coverage(unclaimed, rows, 1, UNCHECKED))[orphan]
    assert result.scope == SURFACE
    assert result.state == NOT_EVENT


def test_without_a_manifest_the_report_says_the_image_was_not_checked(store, rows):
    result = by_id(coverage(store, rows, 1, UNCHECKED))[A]
    assert result.state == TRANSLATED
    assert "no manifest" in result.reason


# --- written, but into a member the build moved ---------------------------------------------


def test_a_line_written_into_a_member_this_build_relocated_is_flagged(store, rows, tmp_path):
    """`translated` says the build wrote the English; it does not say the game reads that
    copy. A member this build moved to a new LBA is the one place those two come apart, so
    a line sitting in one is named -- otherwise a relocation bug reads as a clean report."""
    member = member_of(store, A)
    manifest = write_manifest(tmp_path / "m.json", WROTE, relocated=[member])
    results = coverage(store, rows, 1, manifest)
    result = by_id(results)[A]
    assert result.state == TRANSLATED
    assert result.moved == (member,)
    report = "\n".join(format_report(results))
    assert member in report and DAY_EVENT in report


def test_a_line_whose_member_did_not_move_is_not_flagged(store, rows, tmp_path):
    manifest = write_manifest(tmp_path / "m.json", WROTE, relocated=["OTHER.BIN"])
    assert by_id(coverage(store, rows, 1, manifest))[A].moved == ()


def test_without_a_manifest_no_line_is_flagged_as_moved(store, rows):
    assert by_id(coverage(store, rows, 1, UNCHECKED))[A].moved == ()


def test_only_a_translated_line_is_listed_under_the_member_the_build_moved(store, rows, tmp_path):
    """A `refused` line is Japanese because the build could not fit it, and a `missing`
    one because nobody wrote English -- which member holds their bytes explains neither.
    Listing them made this section mostly noise (27 of 133 day-1 flags were not
    `translated`) and pointed a reader at relocation for a line relocation cannot explain.
    """
    member = member_of(store, B)
    manifest = write_manifest(tmp_path / "m.json", WITHOUT_B, {B: ["too tall"]}, relocated=[member])
    results = coverage(store, rows, 1, manifest)
    refused = by_id(results)[B]
    assert refused.state == REFUSED
    assert refused.moved == (member,), "the line is still in the moved member"
    assert B not in {result.line_id for result in moved_lines(results)}
    section = "\n".join(format_moved(results))
    # The event's three lines are A and C translated, B refused: two, not three.
    assert f"{DAY_EVENT}: 2 line(s) in {member}" in section, section
    # Six of day 1's lines live in that member; B is refused and BRANCH has no row at all.
    assert "4 translated line(s) sit in a member the build moved" in summarise(results, 1)


def test_the_moved_section_does_not_claim_relocation_is_the_cause(store, rows, tmp_path):
    """Both relocated members whose English was checked draw English on Beetle
    (`E0171.0` in `M_H02001`, `E0220.0` in `EV0220.BIN`), so the heading says what the
    list is and the prose says what would make one of its lines a suspect."""
    member = member_of(store, A)
    manifest = write_manifest(tmp_path / "m.json", WROTE, relocated=[member])
    section = "\n".join(format_moved(coverage(store, rows, 1, manifest)))
    heading = next(line for line in section.splitlines() if line.startswith("=="))
    assert "relocated" in heading and "suspect" not in heading, heading
    assert "Membership proves nothing on its own" in section
    assert "E0171.0" in section and "E0220.0" in section, "the refutation lost its evidence"


# --- which events are in a day's scope ----------------------------------------------------------


def test_an_event_in_the_days_id_range_is_in_scope(store, rows):
    assert by_id(coverage(store, rows, 1, UNCHECKED))[A].scope == DAY


def test_an_event_the_data_dates_to_the_day_is_in_scope_though_its_id_is_not(store, rows):
    """`E5199` is not `E01xx`; the store dates it to day 1 and the player still meets it."""
    result = by_id(coverage(store, rows, 1, UNCHECKED))[DATED]
    assert result.scope == DAY
    assert DATED not in states(coverage(store, rows, 2, UNCHECKED))


def test_a_day_independent_event_is_in_scope_and_says_its_day_is_not_in_the_data(store, rows):
    result = by_id(coverage(store, rows, 1, UNCHECKED))[FREE]
    assert result.scope == ANY_DAY
    assert "no day" in result.scope_reason


def test_a_day_read_off_one_branch_of_an_or_does_not_take_the_event_off_other_days(store, rows):
    """The `E0710` shape, and the reason both this report and the packets lost lines.

    `((hour<18 & day!=15) | (day==11 & hour>19))` derives day 11 -- one `day==N` anywhere
    in the condition is all `scene_day` needs -- and its left branch plays on day 1 all
    the same. Taking a *derived* day as exclusive drops the event from every day but 11:
    39 lines of `E0710` were invisible on day 7, and `scenes_of_day` fed the same
    predicate to `boku.packets`, so no translator was ever handed them.
    """
    for day in (1, BRANCH_DAY):
        assert BRANCH in states(coverage(store, rows, day, UNCHECKED)), day
        assert BRANCH_EVENT in [scene["event"] for scene in scenes_of_day(store, day)], day
    assert by_id(coverage(store, rows, BRANCH_DAY, UNCHECKED))[BRANCH].scope == DAY
    day_one = by_id(coverage(store, rows, 1, UNCHECKED))[BRANCH]
    assert day_one.scope == ANY_DAY
    assert f"day=={BRANCH_DAY}" in day_one.scope_reason


def test_only_a_day_the_data_dates_is_a_scene_s_own_day(store):
    """The other half of the `E0710`/`E1006` trap, and the one a *reader* falls into.

    `scene_day` answers "is there a day in or behind this scene", which two tools read as
    "this is the scene's day" and printed -- the coverage report's scope and the packets'
    header. Anything that labels or groups by a day asks this instead.
    """
    by_event = store.scenes_by_event
    assert scene_dated_day(by_event[DAY_EVENT]) == 1
    assert scene_day(by_event[BRANCH_EVENT]) == (BRANCH_DAY, True)
    assert scene_dated_day(by_event[BRANCH_EVENT]) is None
    assert scene_dated_day(by_event[FREE_EVENT]) is None


def test_a_derived_day_does_not_sort_a_scene_in_among_the_dated_days(store):
    """Play order asks the same question, and got the same answer wrong.

    Keyed on the derived day, a scene the data gives no day sorts under it: it lands
    between two dated days in every per-day view, and the hour column of the section it
    is actually printed in restarts at it. It belongs with the scenes that have no day of
    their own, ordered by the hour or slot the script names -- so `FREE_EVENT`, same slot
    and a lower id, comes first.
    """
    order = [scene["event"] for scene in ordered_scenes(store)]
    assert order.index(BRANCH_EVENT) > order.index(DATED_EVENT)
    assert order.index(FREE_EVENT) < order.index(BRANCH_EVENT)


def test_a_day_independent_event_whose_condition_excludes_the_day_is_left_out(store, rows):
    """`(hour<18 & day>7)` cannot be true on day 1, and is true on day 8."""
    assert LATE not in states(coverage(store, rows, 1, UNCHECKED))
    assert LATE in states(coverage(store, rows, 8, UNCHECKED))


# --- the day test inside a condition -------------------------------------------------------------


@pytest.mark.parametrize(
    ("condition", "day", "allowed"),
    [
        (None, 1, True),
        ("", 1, True),
        ("(hour==18)", 1, True),
        ("(day>7)", 1, False),
        ("(day>7)", 8, True),
        ("(day>1 & day<5 & flag[9]==0)", 1, False),
        ("(day>1 & day<5 & flag[9]==0)", 2, True),
        ("(day==3 & hour>15)", 3, True),
        ("(day==3 & hour>15)", 4, False),
        ("(hour>=19 & day!=5)", 5, False),
        ("((hour>18 & day!=21) | (hour>19 & day==21))", 21, True),
        ("(day>=2)", 1, False),
        ("(day<=2)", 3, False),
    ],
)
def test_day_allows_reads_the_day_tests_and_nothing_else(condition, day, allowed):
    assert day_allows(condition, day) is allowed


def test_a_condition_the_parser_cannot_read_keeps_the_event_in_scope():
    """Optimistic on purpose: an unreadable condition must never hide a line.

    `(day>7` would exclude day 1 if it parsed, so this is red the moment the tool starts
    guessing at something it cannot read.
    """
    assert day_allows("(day>7 & ", 1) is True


def test_a_flag_the_tool_cannot_evaluate_never_excludes_a_day():
    assert day_allows("(flag[255]==2)", 1) is True


# --- the report ---------------------------------------------------------------------------------


def test_the_report_groups_by_event_and_counts_its_lines(store, rows, tmp_path):
    manifest = write_manifest(tmp_path / "m.json", WITHOUT_B, {B: ["too tall"]})
    report = "\n".join(format_report(coverage(store, rows, 1, manifest)))
    row = next(line for line in report.splitlines() if line.startswith(DAY_EVENT))
    assert re.search(rf"^{DAY_EVENT}\b.*\b3\b", row), row
    assert store.scenes_by_event[DAY_EVENT]["where"]["bases"][0] in row, row
    assert B in report and "too tall" in report


def test_the_summary_names_every_state(store, rows, tmp_path):
    manifest = write_manifest(tmp_path / "m.json", WITHOUT_B, {B: ["too tall"]})
    line = summarise(coverage(store, rows, 1, manifest), 1)
    assert line.startswith("day 1:")
    for state in (TRANSLATED, REFUSED, MISSING, NOT_EVENT):
        assert state in line


# --- the manifest's real shape ------------------------------------------------------------------


def test_a_manifest_without_the_fields_this_tool_reads_is_refused(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"format": 1, "build": "days"}), encoding="utf-8")
    with pytest.raises(CoverageError) as error:
        Manifest.load(path)
    assert "lines_written" in str(error.value)


def test_the_manifest_fields_are_the_ones_the_build_writes():
    """A gate on the seam, not on a copy of it: every name this tool dereferences out of
    a manifest is grepped for in the function that writes them, so a rename there fails
    here instead of silently reporting every line as never written. `member` belongs in
    this list too -- `Manifest.load` reads it out of each `relocations` entry, and the
    only other place it is written down is this file's own fixture."""
    source = (REPO_ROOT / "boku" / "build.py").read_text(encoding="utf-8")
    for field in (
        WRITTEN_FIELD,
        REFUSED_FIELD,
        RELOCATIONS_FIELD,
        MEMBER_FIELD,
        BUILD_FIELD,
        RESULT_SHA1_FIELD,
    ):
        assert f'"{field}"' in source, f"boku.build no longer writes {field}"


def test_the_build_id_file_is_the_one_make_sh_writes():
    """The other seam: `cmd_build_days` writes the id the emulator's window shows."""
    script = (REPO_ROOT / "make.sh").read_text(encoding="utf-8")
    assert BUILD_ID_NAME in script, f"make.sh no longer writes {BUILD_ID_NAME}"


# --- the command line and the verb ---------------------------------------------------------------


def test_main_coverage_prints_the_day_and_exits_zero(store, written, capsys):
    path, manifest = written
    assert main_coverage([1], store.root.parent, [path], manifest, None) == 0
    out = capsys.readouterr().out
    assert "day 1:" in out and DAY_EVENT in out


def test_the_header_names_the_image_the_report_is_about(store, written, tmp_path, capsys):
    """`translated` means *this* build laid the line out, so a reader has to be able to
    tell whether the report describes the image they played: the manifest's build name,
    the short image sha1 and, when the build left one, the id in the emulator's title."""
    path, manifest = written
    document = json.loads(manifest.read_text(encoding="utf-8"))

    assert main_coverage([1], store.root.parent, [path], manifest, None) == 0
    header = capsys.readouterr().out.splitlines()[0]
    assert document[BUILD_FIELD] in header and document[RESULT_SHA1_FIELD][:8] in header
    assert BUILD_ID_NAME in header, "with no build id the header must say the id is missing"

    (tmp_path / BUILD_ID_NAME).write_text("20260920T1200Z-1234abcd\n", encoding="utf-8")
    assert main_coverage([1], store.root.parent, [path], manifest, None) == 0
    header = capsys.readouterr().out.splitlines()[0]
    assert (tmp_path / BUILD_ID_NAME).read_text(encoding="utf-8").strip() in header


def test_boku_coverage_is_a_command(tmp_path):
    from boku.cli import build_parser

    args = build_parser().parse_args(["coverage", "--day", "1"])
    assert args.days == [1]


def test_make_sh_has_a_coverage_verb():
    """The one place a recurring command line is written down (project CLAUDE.md)."""
    script = (REPO_ROOT / "make.sh").read_text(encoding="utf-8")
    assert re.search(r"^\s*coverage\)", script, re.M), "make.sh has no coverage verb"
    assert "boku coverage" in script


def test_a_line_no_retail_path_draws_is_not_one_the_player_can_meet(tmp_path):
    """`boku.arrays.UNREACHABLE` (bug sumo's move names): the build leaves them retail and
    lists them apart, so the report must not call them refused for want of a listing."""
    synth = SynthStore.new(tmp_path)
    synth.array_item("musi@2C.0", cells=4)
    store = load_store(synth.write())
    rows = read_rows(
        write_translation(tmp_path / "arrays.txt", [("musi@2C.0", "(unlabelled)", "Retreat")])
    )
    report = by_id(coverage(store, rows, 1, write_manifest(tmp_path / "m.json", [])))
    assert "musi@2C.0" not in report
