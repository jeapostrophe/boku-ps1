"""`PLAN TRN-08` -- the translator packet: a system part once, then one part per event.

The packet is a document, so most of what could go wrong is a part that quietly carries
the wrong thing: a constraint Jay asked to keep out of the translator's view, a template
whose ids are not the event's, an answer saved over the wrong block. These tests assert
each part carries the fact it exists for, that nothing on Jay's drop list survives, that an
answer round-trips into a day file the lint reads, and that two runs are byte-identical.

The policy parsers are checked against the committed `translation/*.md` themselves: a
parser that silently matched nothing would leave every packet quietly context-free.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.layout import Marks
from boku.lint import load_rows, parse_file, translation_paths
from boku.packets import (
    ARRAYS_NAME,
    CHECKLIST_NAME,
    DAYS_DIR,
    EVENT_HEADER,
    ORDER_NAME,
    SYSTEM_NAME,
    DayFile,
    PacketBuilder,
    PacketRefused,
    Policy,
    Unit,
    answer_lines,
    check_destination,
    condition_in_words,
    default_day_file,
    format_section,
    japanese_text,
    main_packet,
    parse_day_rows,
    parse_places,
    part_file,
    save_event,
    scene_line_ids,
    unit_like,
    unit_of_day,
    unit_of_surfaces,
    untranslated_reachable,
    without_line_citations,
    write_unit,
)
from boku.script_store import Japanese, load_store, scene_day
from boku.translation import SampleScenes
from tests.synth_script import SynthStore, write_translation

VOICED = "E9001.0"
CHOICE = "E9001.1"
VOICE_ONLY = "E9001.2"
NEXT = "E9002.0"

GATED_EVENT = "E9011"
GATED = f"{GATED_EVENT}.0"
GATED_CONDITION = "((hour<18 & day!=15) | (day==11 & hour>19))"
"""`E1006`'s shape, and the same string `tests.test_coverage.BRANCH_CONDITION` uses:
`script_store.scene_day` derives day 11 from it, and its left branch plays on day 1. The
day the fixture asserts against is the one `scene_day` derives, never a retyped 11."""


@pytest.fixture
def store(tmp_path: Path):
    synth = SynthStore.new(tmp_path)
    synth.message(VOICED, [[6], [4]], voiced=True)
    synth.select(CHOICE, options=2, prompts=1)
    synth.scene(
        "E9001",
        [VOICED, CHOICE],
        voice_only=[VOICE_ONLY],
        quiz={"routines": [15], "quiz": [{"day": 1, "message": 0, "answer": 2}]},
    )
    synth.message(NEXT, [[3]], voiced=False, speaker="BOKU", slot=0)
    synth.scene("E9002", [NEXT])
    return load_store(synth.write())


@pytest.fixture
def gated(tmp_path: Path):
    """`(store, derived day)` for one scene the data gives no day and a condition does."""
    synth = SynthStore.new(tmp_path)
    synth.message(GATED, [[4]], voiced=False)
    scene = synth.scene(GATED_EVENT, [GATED], day=None)
    scene["when"]["condition"] = GATED_CONDITION
    scene["when"]["meal_hour"] = None
    day, derived = scene_day(scene)
    assert derived and day is not None, "the fixture no longer derives a day from its condition"
    scene["dinner_quiz"] = {"routines": [15], "quiz": [{"day": day, "message": 0, "answer": 2}]}
    return load_store(synth.write()), day


@pytest.fixture
def builder(store):
    return PacketBuilder.build(store, Policy.load(), [], False)


def event(store, name: str) -> dict:
    return store.scenes_by_event[name]


def template_rows(part: str) -> list[str]:
    """The rows of an event part's answer block."""
    fenced = part.split("## Your answer", 1)[1].split("```text\n", 1)[1].split("\n```", 1)[0]
    return fenced.splitlines()


# --- the system part -----------------------------------------------------------------------------


def test_the_system_part_carries_the_format_and_the_day(store, builder):
    """Jay's four (`TRN-08`), each checked by a fact read out of its own home."""
    system = builder.system_part(Unit("day01", "day 1", 1, tuple(store.scenes)))
    readme = (DAYS_DIR / "README.md").read_text(encoding="utf-8")
    first_bullet = format_section(readme).splitlines()[0]
    assert first_bullet in system, "the day-file format is not the README's § Format"
    what = Policy.load().day_row(1)
    assert without_line_citations(what) in system


@pytest.mark.parametrize("name", ["glossary.md", "style-guide.md"])
def test_the_system_part_carries_the_whole_glossary_and_the_whole_style_guide(store, builder, name):
    """Jay, 2026-09-22: the glossary and the style guide go in whole. A glossary narrowed to
    rows whose Japanese a matcher found dropped rows with alternatives, brackets and
    running text, and five translation errors traced to it."""
    system = builder.system_part(Unit("day01", "day 1", 1, tuple(store.scenes)))
    body = (REPO_ROOT / "translation" / name).read_text(encoding="utf-8").split("\n", 1)[1]
    assert body.strip() in system


def test_the_checklist_closes_the_system_part(store, builder):
    system = builder.system_part(Unit("day01", "day 1", 1, tuple(store.scenes)))
    checklist = (REPO_ROOT / "translation" / CHECKLIST_NAME).read_text(encoding="utf-8")
    last = [line for line in checklist.splitlines() if line.strip()][-1]
    assert system.rstrip().endswith(last)


def test_a_unit_with_no_day_says_it_has_no_day_summary(store, builder):
    """A shared unit was promised the day's story and got none."""
    system = builder.system_part(Unit("shared", "the shared events", None, tuple(store.scenes)))
    assert "no day summary" in system


def test_the_format_section_stops_at_its_own_section():
    """The README's text after § Format -- the unit states, the file table -- is about the
    project, not the format; a parser that ran on would hand the translator both."""
    readme = (DAYS_DIR / "README.md").read_text(encoding="utf-8")
    section = format_section(readme)
    assert section, "translation/days/README.md has no § Format for the packet to quote"
    assert "day01.txt" not in section
    assert "undrafted" not in section


def test_nothing_on_jay_s_drop_list_reaches_the_translator(store, builder):
    """Capacities, pixels, frame timers, column splits, lint and PLAN citations stay out."""
    parts = [builder.system_part(Unit("day01", "day 1", 1, tuple(store.scenes)))]
    parts += [builder.event_part(scene, 1, 1) for scene in store.scenes]
    text = "\n".join(parts)
    for dropped in (
        " px",
        "bytes per copy",
        "copies on the disc",
        "turns after",
        "col 1 (",
        "PLAN",
    ):
        assert dropped not in text, f"{dropped!r} reached the packet"
    assert re.search(r"`[A-Z]{2,5}-\d{2}`", text) is None, "a plan row id reached the packet"
    assert "boku lint" not in text


def test_the_day_summary_carries_no_line_citations():
    assert without_line_citations("the relay `E0171`\u2013`E0186`, then the kit (`E0107`)") == (
        "the relay, then the kit"
    )


# --- one event -----------------------------------------------------------------------------------


def test_the_template_is_the_event_s_ids_in_the_day_file_shape(store, builder):
    """Every id the event carries, voice-only included, once, in message order, as a row."""
    scene = event(store, "E9001")
    rows = template_rows(builder.event_part(scene, 1, 2))
    assert rows[0].startswith(f"{EVENT_HEADER}E9001")
    ids = [row.split("\t", 1)[0] for row in rows if not row.startswith("#")]
    assert ids == scene_line_ids(scene)
    assert f"{VOICE_ONLY}\t{SampleScenes.VOICE_ONLY}" in rows


def test_a_line_keeps_its_page_breaks_and_loses_its_columns_and_marks(store, builder):
    record = store.lines[VOICED]
    japanese = store.japanese[VOICED]
    _, speaker, text = builder.row(VOICED).split("\t")
    assert text.count(SampleScenes.PAGE_BREAK) == len(japanese.pages) - 1
    assert "「" not in text and "{NL}" not in text
    label = "".join(japanese.pages[0][0]).split("「", 1)[0]
    assert speaker == label, "the speaker column is the label the Japanese draws"
    assert not text.startswith(label)
    part = builder.event_part(event(store, "E9001"), 1, 1)
    assert f"`{VOICED}` {record['voice']['clip']}" in part.split("## Your answer")[0]


def test_columns_join_on_one_space_and_the_indent_and_marks_come_off():
    """The authoring indent opens every continuation column; the marks are the renderer's."""
    space = "\u3000"
    japanese = Japanese(
        pages=((("L", "「", "a", "b"), (space, "c")), ((space, "d", "」"),)), waits=(90,)
    )
    text = japanese_text(japanese, Marks("「", "」", labelled=True))
    assert text == f"ab{space}c{SampleScenes.PAGE_BREAK}d"


def test_a_select_is_a_sel_row_with_the_question_first(store, builder):
    shape = store.lines[CHOICE]["select"]
    _, speaker, text = builder.row(CHOICE).split("\t")
    assert speaker == SampleScenes.SELECT
    assert len(text.split(SampleScenes.OPTION)) == shape["lines"]


def test_a_linear_scene_gets_no_branch_section(store, builder):
    """Jay: no "in the order the game plays it" framing for a linear scene."""
    part = builder.event_part(event(store, "E9002"), 2, 2)
    assert "## Where the scene branches" not in part
    assert "order the game plays" not in part


def test_a_fork_names_the_line_each_way_opens(store, builder):
    scene = event(store, "E9001")
    choice = next(node["node"] for node in scene["nodes"] if node.get("line") == CHOICE)
    after = next(node["node"] for node in scene["nodes"] if node.get("line") == VOICE_ONLY)
    scene["edges"] = [edge for edge in scene["edges"] if edge["from"] != choice] + [
        {"from": choice, "to": after, "condition": "opt0"},
        {"from": choice, "to": "END", "condition": "opt1"},
    ]
    part = builder.event_part(scene, 1, 1)
    assert "## Where the scene branches" in part
    assert f"After `{CHOICE}`" in part
    assert f"`{VOICE_ONLY}` comes next when the player chose option 1" in part
    assert "the event ends when the player chose option 2" in part


def test_the_quiz_says_which_day_each_question_belongs_to(store, builder):
    part = builder.event_part(event(store, "E9001"), 1, 2)
    row = event(store, "E9001")["dinner_quiz"]["quiz"][0]
    assert "day d's" in part
    assert f"On day {row['day']} this event asks `E9001.{row['message']}`" in part


def test_a_derived_day_is_not_printed_as_the_scene_s_day(gated):
    store, day = gated
    part = PacketBuilder.build(store, Policy.load(), [], False).event_part(store.scenes[0], 1, 1)
    line = next(row for row in part.splitlines() if row.startswith("* **When**"))
    assert f"day {day};" not in line
    assert f"day=={day}" in line, "the header must name the test the day was read off"
    assert f"On day {day} this event asks" not in part


def test_a_neighbour_outside_the_unit_shows_its_english_one_inside_does_not(store, tmp_path):
    """The translator already has the unit's own events in view; showing their English
    as it stands would show a re-translation the draft it is replacing."""
    write_translation(tmp_path / "day01.txt", [(NEXT, "Boku", "Three.")])
    builder = PacketBuilder.build(store, Policy.load(), [tmp_path / "day01.txt"], False)
    first = event(store, "E9001")
    alone = builder.event_part(first, 1, 1, unit_events=frozenset({"E9001"}))
    assert f"{NEXT}\tBoku\tThree." in alone
    together = builder.event_part(first, 1, 2, unit_events=frozenset({"E9001", "E9002"}))
    assert "Three." not in together


def test_for_review_puts_the_current_english_under_the_template(store, tmp_path):
    written = "One. // Two."
    write_translation(tmp_path / "day01.txt", [(VOICED, "Uncle", written)])
    plain = PacketBuilder.build(store, Policy.load(), [tmp_path / "day01.txt"], False)
    review = PacketBuilder.build(store, Policy.load(), [tmp_path / "day01.txt"], True)
    scene = event(store, "E9001")
    unit = frozenset({"E9001"})
    assert written not in plain.event_part(scene, 1, 1, unit_events=unit)
    assert written in review.event_part(scene, 1, 1, unit_events=unit)


# --- the unit, written out ------------------------------------------------------------------------


def test_a_unit_is_a_system_part_one_part_per_event_and_the_order(store, builder, tmp_path):
    unit = unit_of_day(store, 1)
    written = write_unit(builder, unit, tmp_path / "day01")
    names = [path.name for path in written]
    assert names[0] == SYSTEM_NAME and names[-1] == ORDER_NAME
    order = (tmp_path / "day01" / ORDER_NAME).read_text(encoding="utf-8").split()
    assert order == [scene["event"] for scene in unit.scenes]
    assert [f"{name}.md" for name in order] == names[1:-1]


def test_two_runs_are_byte_identical(store, builder, tmp_path):
    unit = unit_of_day(store, 1)
    first = write_unit(builder, unit, tmp_path / "a")
    second = write_unit(builder, unit, tmp_path / "b")
    for left, right in zip(first, second, strict=True):
        assert left.read_bytes() == right.read_bytes(), f"{left.name} differs between runs"


def test_a_rerun_leaves_no_stale_event_part(store, builder, tmp_path):
    out = tmp_path / "day01"
    write_unit(builder, unit_of_day(store, 1), out)
    one = Unit("day01", "day 1", 1, (event(store, "E9002"),))
    write_unit(builder, one, out)
    assert sorted(path.name for path in out.glob("*.md")) == ["E9002.md", SYSTEM_NAME]


def test_a_blank_draft_row_is_not_english_for_the_reachable_report(store, tmp_path):
    """A day-independent event whose only row is still blank has no English, and `--day`
    must go on naming it."""
    event(store, "E9002")["when"]["day"] = None
    blank = write_translation(tmp_path / "shared.txt", [(NEXT, "Boku", "")])
    builder = PacketBuilder.build(store, Policy.load(), [blank], False)
    assert "E9002" in untranslated_reachable(builder, 1)


def test_like_takes_a_file_s_events_in_the_file_s_order(store, tmp_path):
    path = write_translation(
        tmp_path / "day01.txt", [(NEXT, "Boku", "Three."), (VOICED, "Uncle", "One. // Two.")]
    )
    unit = unit_like(store, path)
    assert [scene["event"] for scene in unit.scenes] == ["E9002", "E9001"]
    assert unit.day == 1


# --- saving an answer -----------------------------------------------------------------------------


def answer_for(builder: PacketBuilder, scene: dict) -> str:
    """The template with every Japanese field replaced, the way a translator returns it."""
    out = []
    for line in builder.template(scene):
        fields = line.split("\t")
        if line.startswith("#") or len(fields) < 3:
            out.append(line)
        elif fields[1] == SampleScenes.SELECT:
            count = len(fields[2].split(SampleScenes.OPTION))
            options = SampleScenes.OPTION.join(["Yes"] * count)
            out.append(f"{fields[0]}\t{SampleScenes.SELECT}\t{options}")
        else:
            pages = fields[2].count(SampleScenes.PAGE_BREAK) + 1
            out.append(f"{fields[0]}\tUncle\t" + SampleScenes.PAGE_BREAK.join(["Words."] * pages))
    return "Here it is:\n\n```text\n" + "\n".join(out) + "\n```\n"


def test_an_answer_saves_as_the_event_s_block_and_the_lint_reads_it(store, builder, tmp_path):
    into = tmp_path / "day01.txt"
    scene = event(store, "E9001")
    save_event(store, "E9001", answer_for(builder, scene), into)
    text = into.read_text(encoding="utf-8")
    assert "Here it is" not in text
    rows, findings = load_rows(translation_paths([into]))
    assert findings == []
    assert [row.line_id for row in rows] == scene_line_ids(scene)


def test_an_event_saved_late_goes_in_at_its_place_in_the_order(store, builder, tmp_path):
    """The day-3 run: an event refused, then saved after the ones behind it, was appended
    at the end and the file had to be rebuilt by hand. It goes in where the order puts it
    -- the unit's `order.txt` when given, else the project's play order -- and a re-save
    stays where it is."""
    into = tmp_path / "day01.txt"
    first, second = event(store, "E9001"), event(store, "E9002")
    save_event(store, "E9002", answer_for(builder, second), into)
    save_event(store, "E9001", answer_for(builder, first), into)
    save_event(store, "E9002", answer_for(builder, second).replace("Words.", "Again."), into)
    blocks = DayFile.read(into).blocks
    assert [DayFile.events_of(block) for block in blocks] == [["E9001"], ["E9002"]]
    rows, _ = parse_file(into)
    assert [row.line_id for row in rows].count(NEXT) == 1
    assert "Again." in into.read_text(encoding="utf-8")


def test_the_unit_s_order_wins_over_the_project_s(store, builder, tmp_path):
    """`--like` keeps a hand-ordered day file's order, which no sort key reproduces."""
    into = tmp_path / "day01.txt"
    order = ["E9002", "E9001"]
    save_event(store, "E9001", answer_for(builder, event(store, "E9001")), into, order=order)
    save_event(store, "E9002", answer_for(builder, event(store, "E9002")), into, order=order)
    blocks = DayFile.read(into).blocks
    assert [DayFile.events_of(block) for block in blocks] == [["E9002"], ["E9001"]]


def test_the_format_says_notes_hold_no_japanese_either():
    """save-event refuses a note with Japanese in it; the translator is told before, not
    after (the day-3 run)."""
    section = format_section((DAYS_DIR / "README.md").read_text(encoding="utf-8"))
    note = next(line for line in section.split("* ") if "Japanese" in line and "note" in line)
    assert "romanis" in note


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda text: text.replace(f"{VOICED}\t", "E9001.9\t"), "not a line of E9001"),
        (
            lambda text: text.replace(f"{VOICE_ONLY}\t(voice only)\n", ""),
            f"no row for {VOICE_ONLY}",
        ),
        (lambda text: text.replace("Words.", "\u3042", 1), "still holds Japanese"),
        (lambda text: text.replace("\tUncle\t", "\tUncel\t", 1), "not a speaker label"),
    ],
)
def test_an_answer_that_is_not_the_event_is_refused_and_nothing_written(
    store, builder, tmp_path, change, reason
):
    into = tmp_path / "day01.txt"
    answer = change(answer_for(builder, event(store, "E9001")))
    with pytest.raises(PacketRefused) as refusal:
        save_event(store, "E9001", answer, into)
    assert reason in str(refusal.value)
    assert not into.exists()


@pytest.mark.parametrize(
    "header",
    [f"{EVENT_HEADER}E9001 / E9002: both", f"{EVENT_HEADER}E9001: the header names one"],
)
def test_a_block_holding_another_event_s_rows_is_refused(store, builder, tmp_path, header):
    """A hand-merged block -- `# --- E0441: ... --- E0446:` in day04.txt holds E0446.0 under
    a header whose id part names only E0441. Replacing it for E0441 deleted E0446's English
    in silence; now it is refused with the file untouched."""
    into = tmp_path / "day01.txt"
    into.write_text(f"{header}\n{VOICED}\tUncle\tOne. // Two.\n{NEXT}\tBoku\tThree.\n")
    before = into.read_text(encoding="utf-8")
    with pytest.raises(PacketRefused, match="also holds"):
        save_event(store, "E9001", answer_for(builder, event(store, "E9001")), into)
    assert into.read_text(encoding="utf-8") == before


def test_an_event_another_file_beside_it_translates_is_refused(store, builder, tmp_path):
    """Saving into `shared.txt` what `day01.txt` already holds is one id translated twice."""
    write_translation(tmp_path / "day01.txt", [(NEXT, "Boku", "Three.")])
    into = tmp_path / "shared.txt"
    with pytest.raises(PacketRefused, match="already translates"):
        save_event(store, "E9002", answer_for(builder, event(store, "E9002")), into)
    assert not into.exists()


def test_the_default_file_is_the_one_that_already_holds_the_event(store, tmp_path):
    """E0001 is day-independent and lives in day01.txt: the convention alone says shared."""
    event(store, "E9002")["when"]["day"] = None
    assert default_day_file(store, "E9002", tmp_path) == tmp_path / "shared.txt"
    write_translation(tmp_path / "day01.txt", [(NEXT, "Boku", "Three.")])
    assert default_day_file(store, "E9002", tmp_path) == tmp_path / "day01.txt"


def test_a_save_changes_its_own_block_and_nothing_else(store, builder, tmp_path):
    """The rest of the file keeps its bytes -- blank lines and the notes above their rows."""
    into = tmp_path / "day01.txt"
    kept = (
        f"# a preamble\n\n\n{EVENT_HEADER}E9002: kept\n# NOTE {NEXT}: a note\n"
        f"{NEXT}\tBoku\tThree.\n\n\n"
    )
    into.write_text(kept + f"{EVENT_HEADER}E9001: old\n{VOICED}\tUncle\tOld. // Old.\n")
    save_event(store, "E9001", answer_for(builder, event(store, "E9001")), into)
    assert into.read_text(encoding="utf-8").startswith(kept)


@pytest.mark.parametrize("name", ["day01.txt", "day03.txt", "shared.txt"])
def test_a_committed_day_file_reads_and_writes_back_byte_for_byte(name):
    path = DAYS_DIR / name
    assert DayFile.read(path).text() == path.read_text(encoding="utf-8")


def test_a_note_in_japanese_is_refused(store, builder, tmp_path):
    """The day files are tracked and hold no Japanese; a note quoting the source would be
    the way it came in."""
    answer = answer_for(builder, event(store, "E9001")).replace(
        "```text\n", f"```text\n# NOTE {VOICED}: \u3042 -> a\n", 1
    )
    with pytest.raises(PacketRefused, match="a note still holds Japanese"):
        save_event(store, "E9001", answer, tmp_path / "day01.txt")


def test_answer_lines_takes_the_fenced_block():
    answer = "prose\n```text\n\nE1.0\tBoku\tHi.\n```\nmore prose\n"
    assert answer_lines(answer) == ["E1.0\tBoku\tHi."]


# --- the arrays, menus and overlays: TRN-09 ---------------------------------------------------

ITEM = "exe@80000000"
MENU = "exe@80001000"
LABEL = "exe@code:80002000"


@pytest.fixture
def surfaces(tmp_path: Path):
    """Two items of one array, a code-file menu, a code-immediate label -- and one event,
    which the array unit must leave out."""
    synth = SynthStore.new(tmp_path)
    synth.array_item(f"{ITEM}.0")["purpose"] = "kite names, 4 x 3 glyphs, drawn vertically"
    synth.array_item(f"{ITEM}.1")
    synth.select_array(MENU, lines=3)
    synth.code_label(LABEL)
    synth.message(VOICED, [[4]], voiced=False)
    synth.scene("E9001", [VOICED])
    return load_store(synth.write())


def test_the_array_unit_is_every_non_event_line_by_surface(surfaces):
    unit = unit_of_surfaces(surfaces)
    assert [surface.key for surface in unit.surfaces] == [ITEM, MENU, LABEL]
    assert unit.surfaces[0].line_ids == (f"{ITEM}.0", f"{ITEM}.1")
    assert unit.scenes == ()


def test_a_surface_part_is_its_lines_in_the_day_file_shape(surfaces):
    builder = PacketBuilder.build(surfaces, Policy.load(), [], False)
    unit = unit_of_surfaces(surfaces)
    item, menu, _ = unit.surfaces
    rows = template_rows(builder.surface_part(item, 1, 3))
    assert rows[0].startswith(f"{EVENT_HEADER}{ITEM}")
    assert [row.split("\t")[:2] for row in rows[1:]] == [
        [f"{ITEM}.0", "(unlabelled)"],
        [f"{ITEM}.1", "(unlabelled)"],
    ]
    _, speaker, text = template_rows(builder.surface_part(menu, 2, 3))[1].split("\t")
    assert speaker == SampleScenes.SELECT
    assert len(text.split(SampleScenes.OPTION)) == 3


def test_a_part_s_file_name_holds_no_colon(surfaces, tmp_path):
    """`exe@code:80037544.md` is an alternate data stream on NTFS; order.txt keeps the key."""
    builder = PacketBuilder.build(surfaces, Policy.load(), [], False)
    unit = unit_of_surfaces(surfaces)
    written = write_unit(builder, unit, tmp_path / "arrays")
    assert all(":" not in path.name for path in written)
    assert LABEL in (tmp_path / "arrays" / ORDER_NAME).read_text(encoding="utf-8").split()
    assert (tmp_path / "arrays" / part_file(LABEL)).is_file()


def test_an_event_id_no_scene_claims_is_not_a_surface(tmp_path):
    synth = SynthStore.new(tmp_path)
    synth.message("E7777.0", [[4]], voiced=False)
    synth.array_item(f"{ITEM}.0")
    orphaned = load_store(synth.write())
    assert [surface.key for surface in unit_of_surfaces(orphaned).surfaces] == [ITEM]


def test_a_surface_s_capacity_is_not_in_its_description(surfaces):
    """The purpose column carries glyph and cell counts; those are the lint's, not the
    translator's (`TRN-08`'s rule, kept for the arrays)."""
    builder = PacketBuilder.build(surfaces, Policy.load(), [], False)
    part = builder.surface_part(unit_of_surfaces(surfaces).surfaces[0], 1, 3)
    assert "kite names" in part
    assert re.search(r"\d+\s*(x\s*\d+\s*)?(glyphs|cells)", part) is None


def test_a_surface_answer_saves_into_the_arrays_file(surfaces, tmp_path):
    builder = PacketBuilder.build(surfaces, Policy.load(), [], False)
    surface = unit_of_surfaces(surfaces).surfaces[1]
    answer = "\n".join(builder.block(builder.surface_header(surface), surface.line_ids))
    answer = re.sub(r"\t\[SEL\]\t.*", "\t[SEL]\tRelease it? | Yes | No", answer)
    assert default_day_file(surfaces, MENU, tmp_path) == tmp_path / ARRAYS_NAME
    into = tmp_path / ARRAYS_NAME
    save_event(surfaces, MENU, answer, into)
    rows, _ = parse_file(into)
    assert [(row.line_id, row.text) for row in rows] == [(MENU, "Release it? | Yes | No")]


# --- what the day-1..7 re-translation found in the event parts -----------------------------------


def test_a_scene_s_lines_come_in_message_order_whatever_the_flow_walk_says(store, builder):
    """`E0107`: the extract's walk gives `.0, .2, .1` (the game re-enters after a map change)
    and the packet showed them so; the lines are in message order."""
    scene = event(store, "E9001")
    scene["play_order"] = list(reversed(scene["play_order"]))
    ids = [row.split("\t", 1)[0] for row in builder.template(scene)[1:]]
    assert ids == sorted(ids, key=lambda line_id: int(line_id.rsplit(".", 1)[1]))


def test_the_neighbours_are_the_file_s_not_the_project_s_sort(store, tmp_path):
    """`E0405` was shown a breakfast chorus as the scene before it: undated events sort by
    hour alone. The file that holds a scene is in the order its day plays."""
    write_translation(
        tmp_path / "day01.txt", [(NEXT, "Boku", "Three."), (VOICED, "Uncle", "One. // Two.")]
    )
    builder = PacketBuilder.build(store, Policy.load(), [tmp_path / "day01.txt"], False)
    before, after = builder.neighbours(event(store, "E9001"))
    assert before["event"] == "E9002" and after is None


def test_shared_txt_is_no_order_to_take_neighbours_from(store, tmp_path):
    """`shared.txt` is ordered by place, not play: a neighbour from it is the next room."""
    event(store, "E9002")["when"]["day"] = None
    event(store, "E9001")["when"]["day"] = None
    write_translation(
        tmp_path / "shared.txt", [(NEXT, "Boku", "Three."), (VOICED, "Uncle", "One. // Two.")]
    )
    builder = PacketBuilder.build(store, Policy.load(), [tmp_path / "shared.txt"], False)
    assert builder.neighbours(event(store, "E9001")) == (None, None)


def test_a_dated_event_with_no_text_still_has_a_place_among_its_day(store, builder):
    silent = event(store, "E9002")
    silent["lines"], silent["nodes"] = [], []
    assert builder.neighbours(silent) == (event(store, "E9001"), None)


def test_an_undated_event_no_file_holds_has_no_neighbours(store, builder):
    scene = event(store, "E9002")
    scene["when"]["day"] = None
    assert builder.neighbours(scene) == (None, None)


def test_a_fork_from_a_step_with_no_text_names_the_step_not_none(store, builder):
    """`E4028` printed "After `None`": the fork's source was a step with no line."""
    scene = event(store, "E9001")
    silent = {"node": "E9001.P16@99", "pc": 99, "opcode": "PROG"}
    scene["nodes"].append(silent)
    scene["edges"] += [
        {"from": silent["node"], "to": "END", "condition": "opt0"},
        {"from": silent["node"], "to": "END", "condition": "opt1"},
    ]
    scene["play_order"].append(silent["node"])
    part = builder.event_part(scene, 1, 1)
    assert "None" not in part
    assert "After a PROG step with no text" in part


def test_a_move_is_named_as_a_move_and_the_map_has_a_legend(store, builder):
    policy = Policy.load()
    base, place = policy.places[0]
    scene = event(store, "E9001")
    move = {"node": f"E9001.MAP:{base}@90", "pc": 144, "opcode": "MAP"}
    first = scene["nodes"][0]["node"]
    scene["nodes"].append(move)
    scene["edges"] += [
        {"from": first, "to": move["node"], "condition": f"map=={base}"},
        {"from": first, "to": "END", "condition": f"map!={base}"},
    ]
    part = PacketBuilder.build(store, policy, [], False).event_part(scene, 1, 1)
    assert f"the move to map {base} comes next when the player is on map {base}" in part
    assert f"* {base} -- {place}" in part
    assert part.count(place) == 1, "the place is named once, in the legend"
    scene["where"]["bases"] = [base]
    part = PacketBuilder.build(store, policy, [], False).event_part(scene, 1, 1)
    context = part.split("## Your answer")[0]
    assert context.count(place) == 1, "a base **Where** describes is not in the legend again"


def test_a_hand_over_to_itself_or_twice_is_one_line_or_none(store, builder):
    scene = event(store, "E9001")
    scene["handovers"] = [
        {"kind": "MAP", "map": "G01", "event": "E9001", "reachable": True},
        {"kind": "MAP", "map": "G02", "event": "E9002", "reachable": True},
        {"kind": "MAP", "map": "G03", "event": "E9002", "reachable": True},
    ]
    part = builder.event_part(scene, 1, 1)
    assert part.count("**Then**") == 1
    assert "`E9002`" in part.split("**Then**")[1].splitlines()[0]
    assert "`E9001`" not in part.split("**Then**")[1].splitlines()[0]


def test_a_glyph_code_is_explained_not_replaced(store, builder):
    """`E0650.11` showed a raw `{G:22}` with no word on it. The token names the exact cell
    -- `{G:22}` and `{G:1456}` both draw a closing parenthesis, `{G:47}` is the triangle
    button -- so it stays, and the part says what the glyph table says it draws."""
    table = builder.table
    cells = sorted(n for n in table.characters if n not in table.unambiguous)[:2]
    record = store.lines[NEXT]
    tokens = "".join(f"{{G:{n}}}" for n in cells)
    record["text"] = record["text"].replace("{END}", f"{tokens}{{END}}")
    store.__dict__.pop("japanese", None)
    part = builder.event_part(event(store, "E9002"), 1, 1)
    for n in cells:
        assert f"{{G:{n}}}" in part.split("## Your answer")[1]
        assert (
            f"`{{G:{n}}}` is one cell of the game's font that draws {table.characters[n]}" in part
        )


def test_a_bible_entry_for_several_slots_says_which_slot_is_who(tmp_path):
    """ "The three boys, slots 6-8" named no one; and a speaker the scene does not place
    (`E0512.1`'s aunt) was missing from "Who is here"."""
    synth = SynthStore.new(tmp_path)
    synth.message("E9003.0", [[3]], voiced=False, speaker="FAT", slot=7)
    synth.message("E9003.1", [[3]], voiced=False, speaker="OBA", slot=2)
    scene = synth.scene("E9003", ["E9003.0", "E9003.1"])
    scene["cast"] = [{"slot": 7, "model": 1}]
    store = load_store(synth.write())
    policy = Policy.load()
    boys = next(entry for entry in policy.cast if 7 in entry.slots)
    aunt = next(entry for entry in policy.cast if entry.slots == (2,))
    part = PacketBuilder.build(store, policy, [], False).event_part(store.scenes[0], 1, 1)
    who = next(line for line in part.splitlines() if line.startswith("* **Who is here**"))
    assert "slot 7 is Fat" in who and len(boys.slots) > 1
    assert aunt.heading.split(",")[0] in who


def test_lines_that_share_a_recording_say_so(tmp_path):
    """`E0173.0` and `E0174.0` are one line with one clip, played in two events. A shared
    Japanese text alone says nothing: a bare "Huh?" is forty different lines."""
    synth = SynthStore.new(tmp_path)
    synth.message("E9003.0", [[3]], voiced=True)
    synth.message("E9004.0", [[3]], voiced=True)
    synth.scene("E9003", ["E9003.0"])
    synth.scene("E9004", ["E9004.0"])
    store = load_store(synth.write())
    part = PacketBuilder.build(store, Policy.load(), [], False).event_part(
        store.scenes_by_event["E9004"], 1, 1
    )
    assert "the same recording as `E9003.0`: keep the English identical" in part
    assert "word for word" not in part, "a shared text alone is no reason to match the English"


def test_a_quiz_message_no_day_asks_is_named(store, builder):
    """`E0221.16`: day 15 opens message 0, so nothing points at `.16` -- the packet says so
    rather than leaving a translator to wonder which day it belongs to."""
    scene = event(store, "E9001")
    scene["dinner_quiz"]["quiz"] = [{"day": 1, "message": 0, "answer": 2}]
    part = builder.event_part(scene, 1, 1)
    assert f"No day's row names `{CHOICE}`" in part


# --- the destination a packet may never be written to ---------------------------------------------


def test_a_packet_refuses_a_tracked_destination():
    with pytest.raises(PacketRefused) as refusal:
        check_destination(REPO_ROOT / "translation" / "packets")
    assert "work/" in str(refusal.value)
    assert check_destination(REPO_ROOT / "work" / "packets").is_relative_to(REPO_ROOT / "work")


def test_the_cli_refuses_a_tracked_destination(tmp_path, capsys):
    code = main_packet(1, (), tmp_path, REPO_ROOT / "research", False, ())
    assert code == 2
    assert "work/" in capsys.readouterr().err


def test_the_cli_refuses_both_or_neither_selector(tmp_path, capsys):
    assert main_packet(None, (), tmp_path, tmp_path / "out", False, ()) == 2
    assert main_packet(1, ("E9001",), tmp_path, tmp_path / "out", False, ()) == 2
    assert "exactly one" in capsys.readouterr().err


# --- conditions in words --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("opt0", "the player chose option 1"),
        ("opt2", "the player chose option 3"),
        ("cancel", "the player cancelled"),
        ("lflag>=1", "this event's own progress counter is at least 1"),
        ("flag[43]==0", "story flag 43 is 0"),
        ("(hour==18)", "the hour is 18"),
    ],
)
def test_a_condition_reads_as_a_sentence(condition, expected):
    assert condition_in_words(condition) == expected


def test_a_parenthesised_conjunction_is_read_term_by_term():
    """`E0121`'s entry condition: the group's parentheses sit on its first and last terms,
    and a term that kept one was printed in its symbols -- `(hour>=14` -- not in words."""
    words = condition_in_words("(hour>=14 & hour<=17 & lflag==0)")
    assert words == (
        "the hour is at least 14 and the hour is at most 17 and "
        "this event's own progress counter is 0"
    )


def test_a_group_inside_a_clause_stays_a_group():
    """`a & (b | c)` split on every `|` read as two clauses, `a and b -- or -- c`: another
    condition. Split at depth 0 only, the group keeps its parentheses in words."""
    words = condition_in_words("hour>=14 & (opt0 | opt1)")
    assert words == (
        "the hour is at least 14 and (the player chose option 1 or the player chose option 2)"
    )


def test_a_compound_condition_keeps_its_structure():
    words = condition_in_words("flag[43]>=1 & lflag==0 | opt1")
    assert " and " in words
    assert " -- or -- " in words


# --- the policy documents, as they are committed ------------------------------------------------


def test_the_bible_s_month_table_covers_every_day():
    """A day with no row would leave that day's packets with no story context at all."""
    rows = parse_day_rows((REPO_ROOT / "translation" / "bible.md").read_text(encoding="utf-8"))
    month = set(range(1, 32))
    covered = {day for days, _, _ in rows for day in days}
    assert covered >= month, f"days missing from the table: {month - covered}"
    policy = Policy(day_rows=rows)
    assert all(policy.day_row(day) is not None for day in range(1, 32))


def test_an_open_ended_day_row_runs_to_the_row_after_it():
    """The table writes its ranges with an en dash, and `9-` means "until the next row"."""
    rows = parse_day_rows(
        "## 4. The month\n\n"
        "| day | what happens | ids |\n|---:|---|---|\n"
        "| 9\u2013 | the giant fish; the satellite | `E0906`, `E1006` |\n"
        "| 11 | Moe posts her letter | `E1101` |\n"
    )
    assert [tuple(days) for days, _, _ in rows] == [(9, 10), (11,)]


def test_the_bible_s_places_parse_to_one_base_each():
    places = parse_places((REPO_ROOT / "translation" / "bible.md").read_text(encoding="utf-8"))
    assert places, "no base -> place rows were parsed; every packet would lose its place names"
    assert all(len(base) >= 3 and base[0].isupper() for base, _ in places)
    assert len({base for base, _ in places}) == len(places), "a base was parsed twice"


def test_the_packet_reads_the_committed_day_files_by_default():
    assert DAYS_DIR.is_dir()
    assert any(DAYS_DIR.glob("*.txt"))
