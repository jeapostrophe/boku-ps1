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

import csv
import re
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.layout import Marks
from boku.lint import load_rows, parse_file, translation_paths
from boku.locked import HEADER, locks_by_id
from boku.locked import parse as parse_locks
from boku.locked import read as read_locks
from boku.packets import (
    ARRAYS_NAME,
    CHECKLIST_NAME,
    DAYS_DIR,
    DINING_ROOM,
    EVENT_HEADER,
    LABEL_OF,
    ORDER_NAME,
    POLICY_DOCUMENTS,
    SYSTEM_NAME,
    VOICE_ONLY_TSV,
    DayFile,
    PacketBuilder,
    PacketRefused,
    Policy,
    Unit,
    answer_lines,
    check_destination,
    condition_in_words,
    default_day_file,
    estimate_tokens,
    format_section,
    japanese_text,
    main_packet,
    main_save_event,
    order_keys,
    parse_flags,
    parse_places,
    part_file,
    save_event,
    scene_line_ids,
    unit_like,
    unit_of_day,
    unit_of_game,
    unit_of_surfaces,
    untranslated_reachable,
    without_plan_citations,
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


def test_the_system_part_carries_the_format(store, builder):
    system = builder.system_part(Unit("day01", "day 1", 1, tuple(store.scenes)))
    readme = (DAYS_DIR / "README.md").read_text(encoding="utf-8")
    first_bullet = format_section(readme).splitlines()[0]
    assert first_bullet in system, "the day-file format is not the README's § Format"


@pytest.mark.parametrize("name", ["bible.md", "style-guide.md", "glossary.md", CHECKLIST_NAME])
def test_the_system_part_carries_every_policy_document_whole(store, builder, name):
    """Jay, 2026-09-23 (the v3 packet): the ENTIRE story bible, glossary, style guide and
    checklist, verbatim but for PLAN citations. Every line of each file after its title is
    looked for, so a document cut short, narrowed to a day (the v2 packet gave the bible's
    one-day summary) or left out fails here by name. A glossary narrowed to rows a matcher
    found caused five translation errors (2026-09-22)."""
    system = builder.system_part(Unit("day01", "day 1", 1, tuple(store.scenes)))
    lines = (REPO_ROOT / "translation" / name).read_text(encoding="utf-8").splitlines()[1:]
    missing = [line for line in lines if without_plan_citations(line) not in system]
    assert not missing, f"{name}: {len(missing)} line(s) missing, first {missing[0]!r}"
    assert lines, f"{name} is empty"


def test_the_policy_documents_are_the_bible_the_style_guide_the_glossary_the_checklist():
    names = [name for _, name in POLICY_DOCUMENTS]
    assert names == ["bible.md", "style-guide.md", "glossary.md", CHECKLIST_NAME]


def test_a_plan_citation_is_all_that_comes_out():
    text = "# Glossary (PLAN `TRN-01`)\nFat (PLAN `PIPE-07`) is `E0650.10`; see PLAN `TRN-08`."
    assert without_plan_citations(text) == "# Glossary\nFat is `E0650.10`; see."


def test_the_checklist_closes_the_system_part(store, builder):
    system = builder.system_part(Unit("day01", "day 1", 1, tuple(store.scenes)))
    checklist = (REPO_ROOT / "translation" / CHECKLIST_NAME).read_text(encoding="utf-8")
    last = [line for line in checklist.splitlines() if line.strip()][-1]
    assert system.rstrip().endswith(last)


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
        "Voice clips",
        store.lines[VOICED]["voice"]["clip"],
    ):
        assert dropped not in text, f"{dropped!r} reached the packet"
    assert re.search(r"`[A-Z]{2,5}-\d{2}`", text) is None, "a plan row id reached the packet"
    assert "boku lint" not in text


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
    assert record["voice"]["clip"] not in part, "Jay, 2026-09-23: no voice-clip references"


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
    order = order_keys((tmp_path / "day01" / ORDER_NAME).read_text(encoding="utf-8"))
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


WORDS = "I'm your Uncle Yusaku."
LOCKED = locks_by_id(parse_locks("\t".join(HEADER) + f"\n{VOICED}\tphrase\t{WORDS}\tJay\n"))
"""Jay's words for one line of the synthetic store, read as `translation/locked.tsv` is."""


def test_a_part_names_jay_s_words_for_its_locked_lines_and_no_others(store, builder):
    """A part names each locked line's words; an event with none carries no such section."""
    builder.locked = LOCKED
    locked_part = builder.event_part(event(store, "E9001"), 1, 2)
    after_answer = locked_part.split("## Your answer", 1)[1]
    assert f"`{VOICED}`: {LOCKED[VOICED][0].says} `{WORDS}`" in after_answer
    assert "## Words that stay" not in builder.event_part(event(store, "E9002"), 2, 2)


def test_an_answer_that_drops_jay_s_words_is_refused_and_nothing_written(store, builder, tmp_path):
    into = tmp_path / "day01.txt"
    answer = answer_for(builder, event(store, "E9001"))
    with pytest.raises(PacketRefused, match=f"{VOICED} drops Jay's words") as refusal:
        save_event(store, "E9001", answer, into, locked=LOCKED)
    assert WORDS in str(refusal.value)
    assert not into.exists()
    kept = answer.replace("Words. //", f"{WORDS} //", 1)
    save_event(store, "E9001", kept, into, locked=LOCKED)
    assert WORDS in into.read_text(encoding="utf-8")


def test_the_packet_and_save_event_read_translation_locked_tsv_by_default(
    store, builder, tmp_path, monkeypatch
):
    """`./make.sh packet` and `./make.sh save-event` pass no locks: the defaults are what hold
    Jay's words in a real run, so they are tested, not only the injected mapping."""
    assert builder.locked == locks_by_id(read_locks()), "the builder's locks are not the file's"
    assert builder.locked, "translation/locked.tsv read as empty"
    monkeypatch.setattr("boku.packets.read_locks", lambda: list(LOCKED[VOICED]))
    with pytest.raises(PacketRefused, match="drops Jay's words"):
        save_event(store, "E9001", answer_for(builder, event(store, "E9001")), tmp_path / "d.txt")


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
    assert LABEL in order_keys((tmp_path / "arrays" / ORDER_NAME).read_text(encoding="utf-8"))
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
    assert len(boys.slots) > 1
    assert f"(here: {LABEL_OF['FAT']})" in who, "the boy present is named by his label"
    assert LABEL_OF["GUTS"] not in who, "a boy not in the scene is not named"
    assert aunt.heading.split(";")[0] in who


def test_who_is_here_carries_no_slot_numbers_or_line_counts(store, builder):
    """20k tokens of the whole-game packet were the bible's cast headings repeated whole --
    slot numbers, labels and line counts -- in every part; the bible is in system.md."""
    part = builder.event_part(event(store, "E9001"), 1, 1)
    who = next(line for line in part.splitlines() if line.startswith("* **Who is here**"))
    assert "slot" not in who and " lines" not in who
    assert "Boku (" in who


def test_bases_that_share_a_place_name_it_once(store):
    """`E0710`'s header named "single-purpose close-ups (...)" once per base, eight times."""
    policy = Policy.load()
    by_place: dict[str, list[str]] = {}
    for base, place in policy.places:
        by_place.setdefault(place, []).append(base)
    place, bases = next((p, b) for p, b in by_place.items() if len(b) > 2)
    scene = event(store, "E9001")
    scene["where"]["bases"] = bases[:3]
    builder = PacketBuilder.build(store, policy, [], False)
    assert builder.places(scene) == f"{', '.join(bases[:3])} -- {place}"


def test_a_run_of_maps_the_player_is_not_on_is_one_phrase():
    words = condition_in_words("flag[34]>=1 & map!=H26 & map!=I36 & map!=I37 & lflag==0", {})
    assert words == (
        "story flag 34 is at least 1 and the player is on none of maps H26, I36, I37 and "
        "this event's own progress counter is 0"
    )


def test_a_part_does_not_repeat_the_answer_instruction_system_md_gives(store, builder):
    """ "This block, with the Japanese replaced..." in each of 599 parts was 23k tokens."""
    system = builder.system_part(Unit("day01", "day 1", 1, tuple(store.scenes)))
    part = builder.event_part(event(store, "E9001"), 1, 1)
    assert "the lines under **Your answer**" in system
    assert "Japanese replaced" not in part


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


def test_a_voice_only_line_carries_the_gist_the_voice_only_table_gives(store, builder):
    """`E0504.0`'s row said nothing of the car coming and going. The gist is the TSV's own
    `said` and `notes`, read here with `csv` rather than through the loader under test."""
    lines = [
        line
        for line in VOICE_ONLY_TSV.read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")
    ]
    row = next(r for r in csv.DictReader(lines, delimiter="\t") if r["said"] and r["notes"])
    scene = event(store, "E9001")
    scene["nodes"][2]["line"] = row["line_id"]
    scene["lines"].append(row["line_id"])
    context = builder.event_part(scene, 1, 1).split("## Your answer")[0]
    assert row["said"] in context and row["notes"] in context


def test_every_flag_the_bible_lists_is_named_in_a_condition(store):
    """Bible § 8 names the flags; a condition printed "story flag 21 is 1" and no more. The
    numbers are read off the bible's own paragraph, each item's leading numbers."""
    bible = (REPO_ROOT / "translation" / "bible.md").read_text(encoding="utf-8")
    paragraph = bible.split("**Flags evident", 1)[1].split("**For whoever", 1)[0]
    leading = {int(m) for m in re.findall(r"(?:^|\u00b7)\s*(\d+)", paragraph.split("): ", 1)[1])}
    flags = Policy.load().flags
    assert leading <= set(flags), (
        f"flags the bible names and the packet does not: {leading - set(flags)}"
    )
    assert 23 in flags, "the dinner game's flag is in bible § 8"
    number = min(leading)
    words = condition_in_words(f"flag[{number}]==1", flags)
    assert words == f"story flag {number} ({flags[number]}) is 1"


def test_the_flag_list_s_runs_and_pairs_each_name_every_flag_they_cover():
    """§ 8 writes `37/38`, `57\u201360` and `131\u2013145, 147\u2013153`; the comma form was read
    as no flag at all."""
    flags = parse_flags(
        "## 8. Flags\n\n**Flags evident from the script** (`g_flags[n]`): 5 duty \u00b7 "
        "37/38 flowers \u00b7 57\u201360 stations \u00b7 131\u2013145, 147\u2013153 corn ears, "
        "flowers\n\n**For whoever builds** it\n"
    )
    assert flags[5] == "duty" and flags[38] == "flowers" and flags[58] == "stations"
    assert flags[131] == flags[153] == "corn ears, flowers" and 146 not in flags


@pytest.mark.parametrize(("hour", "meal"), [(7, "breakfast"), (8, "breakfast"), (18, "dinner")])
def test_a_scene_at_the_dining_room_names_the_meal(store, builder, hour, meal):
    """`E0502` at 8:00 read to its translator as dinner."""
    scene = event(store, "E9001")
    scene["where"]["bases"] = [DINING_ROOM]
    scene["when"]["meal_hour"] = hour
    when = next(line for line in builder.event_part(scene, 1, 1).splitlines() if "**When**" in line)
    assert meal in when


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
    assert condition_in_words(condition, {}) == expected


def test_a_parenthesised_conjunction_is_read_term_by_term():
    """`E0121`'s entry condition: the group's parentheses sit on its first and last terms,
    and a term that kept one was printed in its symbols -- `(hour>=14` -- not in words."""
    words = condition_in_words("(hour>=14 & hour<=17 & lflag==0)", {})
    assert words == (
        "the hour is at least 14 and the hour is at most 17 and "
        "this event's own progress counter is 0"
    )


def test_a_group_inside_a_clause_stays_a_group():
    """`a & (b | c)` split on every `|` read as two clauses, `a and b -- or -- c`: another
    condition. Split at depth 0 only, the group keeps its parentheses in words."""
    words = condition_in_words("hour>=14 & (opt0 | opt1)", {})
    assert words == (
        "the hour is at least 14 and (the player chose option 1 or the player chose option 2)"
    )


def test_a_compound_condition_keeps_its_structure():
    words = condition_in_words("flag[43]>=1 & lflag==0 | opt1", {})
    assert " and " in words
    assert " -- or -- " in words


# --- the policy documents, as they are committed ------------------------------------------------


def test_the_bible_s_places_parse_to_one_base_each():
    places = parse_places((REPO_ROOT / "translation" / "bible.md").read_text(encoding="utf-8"))
    assert places, "no base -> place rows were parsed; every packet would lose its place names"
    assert all(len(base) >= 3 and base[0].isupper() for base, _ in places)
    assert len({base for base, _ in places}) == len(places), "a base was parsed twice"


def test_the_packet_reads_the_committed_day_files_by_default():
    assert DAYS_DIR.is_dir()
    assert any(DAYS_DIR.glob("*.txt"))


# --- the whole game in one directed session (v3, Jay 2026-09-23) --------------------------------

LATER_DAY = 2
"""The day the game fixture's second-day events are dated to."""


@pytest.fixture
def game(tmp_path: Path):
    """Two day-1 events held by `day01.txt` against their id order, a day-independent event
    day 1 reaches, a day-2 event that replays day 1's recording, a day-independent event
    only day 2 reaches, and one surface. The store is `tmp_path/disc/script`, so the command
    line reads it with `--disc tmp_path/disc`."""
    synth = SynthStore.new(tmp_path / "disc")
    synth.message("E9101.0", [[4]], voiced=True)
    synth.message("E9102.0", [[4]], voiced=False)
    synth.message("E9802.0", [[4]], voiced=False)
    synth.message("E9201.0", [[4]], voiced=True)
    synth.message("E9801.0", [[4]], voiced=False)
    synth.array_item(f"{ITEM}.0")
    synth.scene("E9101", ["E9101.0"], day=1)
    synth.scene("E9102", ["E9102.0"], day=1)
    synth.scene("E9802", ["E9802.0"], day=None)
    synth.scene("E9201", ["E9201.0"], day=LATER_DAY)
    synth.scene("E9801", ["E9801.0"], day=None)["when"]["condition"] = f"day>={LATER_DAY}"
    store = load_store(synth.write())
    days = tmp_path / "days"
    days.mkdir()
    write_translation(
        days / "day01.txt", [("E9102.0", "Uncle", "Two."), ("E9101.0", "Uncle", "One.")]
    )
    return store, days


def game_builder(store, days: Path) -> PacketBuilder:
    return PacketBuilder.build(store, Policy.load(), [days], False)


def written_game(game, tmp_path: Path) -> tuple[Unit, Path]:
    store, days = game
    builder = game_builder(store, days)
    unit = unit_of_game(store, builder)
    write_unit(builder, unit, tmp_path / "game")
    return unit, tmp_path / "game"


def test_the_game_is_every_day_in_turn_then_the_surfaces(game):
    """A day file's own order wins (it is the day as played); a day-independent event goes
    in at the first day that can reach it; the menus and books come after the story."""
    store, days = game
    unit = unit_of_game(store, game_builder(store, days))
    assert unit.keys == ["E9102", "E9101", "E9802", "E9201", "E9801", ITEM]
    assert [unit.placed.get(key) for key in unit.keys] == [1, 1, 1, LATER_DAY, LATER_DAY, None]


def test_an_undated_event_whose_id_names_a_day_it_can_play_goes_to_that_day(tmp_path):
    """`E1006` (the satellite, bible § 4's days 9-10) tests flags, not the day, so the first
    day its condition allows is day 1 -- and the whole-game packet gave it under "Day 1
    begins". An event id is `E<day><nn>` (`translation/days/README.md`); when the condition
    lets that day play it, that day is where it goes. An id outside the month (`E8013`, the
    examine texts) keeps the first day that can reach it."""
    synth = SynthStore.new(tmp_path)
    for name in ("E0101", "E0250", "E8013"):
        synth.message(f"{name}.0", [[4]], voiced=False)
    synth.scene("E0101", ["E0101.0"], day=1)
    synth.scene("E0250", ["E0250.0"], day=None)["when"]["condition"] = "flag[45]>0 & day>=1"
    synth.scene("E8013", ["E8013.0"], day=None)["when"]["condition"] = "day>=1"
    store = load_store(synth.write())
    unit = unit_of_game(store, PacketBuilder.build(store, Policy.load(), [], False))
    assert unit.placed == {"E0101": 1, "E0250": 2, "E8013": 1}
    assert unit.keys == ["E0101", "E8013", "E0250"]


def test_order_txt_names_the_file_each_part_saves_into(game, tmp_path):
    """The mapping is what `save-event` would choose by itself, asked part by part."""
    store, days = game
    _, out = written_game(game, tmp_path)
    rows = [line.split("\t") for line in (out / ORDER_NAME).read_text().splitlines()]
    assert rows == [
        ["E9102", "day01.txt"],
        ["E9101", "day01.txt"],
        ["E9802", "shared.txt"],
        ["E9201", f"day{LATER_DAY:02d}.txt"],
        ["E9801", "shared.txt"],
        [ITEM, ARRAYS_NAME],
    ]
    for key, name in rows:
        assert default_day_file(store, key, days).name == name, f"save-event disagrees on {key}"


def test_the_first_part_of_each_day_says_the_day_begins(game, tmp_path):
    unit, out = written_game(game, tmp_path)
    begins = {key: (out / part_file(key)).read_text().count("begins") for key in unit.keys}
    assert begins == {"E9102": 1, "E9101": 0, "E9802": 0, "E9201": 1, "E9801": 0, ITEM: 1}


def test_a_replayed_recording_names_only_its_first_playing_in_the_game(game, tmp_path):
    """E0502.0's part listed seventeen other lines and their clip ids. In play order the
    translator has already answered the first playing; that one line is all it needs."""
    store, _ = game
    _, out = written_game(game, tmp_path)
    later = (out / "E9201.md").read_text()
    first = (out / "E9101.md").read_text()
    assert "the same recording as `E9101.0`: keep the English identical" in later
    assert "same recording" not in first
    assert store.lines["E9101.0"]["voice"]["clip"] not in later + first


def test_save_event_reads_the_key_column_of_a_two_column_order(game, tmp_path, capsys):
    """order.txt now says which file a part goes to; `--order` must still read the keys,
    and a part saved into an empty file goes in at its place among them."""
    _, days = game
    _, out = written_game(game, tmp_path)
    into = days / "shared.txt"
    for key in ("E9801", "E9802"):
        answer = tmp_path / f"{key}.txt"
        answer.write_text(f"{EVENT_HEADER}{key}\n{key}.0\tUncle\tWords.\n")
        code = main_save_event(key, answer, into, tmp_path / "disc", "", out / ORDER_NAME)
        assert code == 0, capsys.readouterr().err
    assert [row.line_id for row in parse_file(into)[0]] == ["E9802.0", "E9801.0"]


def test_the_cli_writes_the_whole_game_and_its_size(game, tmp_path, capsys):
    _, days = game
    out = tmp_path / "out"
    code = main_packet(None, (), tmp_path / "disc", out, False, (days,), game=True)
    assert code == 0, capsys.readouterr().err
    said = capsys.readouterr().out
    assert (out / "game" / SYSTEM_NAME).read_text().startswith("# Translating the whole game")
    assert "tokens" in said


def test_a_token_estimate_counts_japanese_one_each_and_the_rest_by_three_and_a_half():
    assert estimate_tokens("あい" + "a" * 7) == 4
