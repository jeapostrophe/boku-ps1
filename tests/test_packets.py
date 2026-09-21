"""`PLAN TRN-02` -- the translator packets: what is in one, and that two runs agree.

The packet is a document, so most of what could go wrong is a section that quietly stops
being written. These tests assert each section is present *and carries the fact it exists
for* -- the capacity numbers out of the store, the branch target beside its option, the
glossary row whose term is actually in the scene -- and that the whole thing is
byte-identical over two runs, which is what lets a translator diff one packet against the
next.

The policy parsers are checked against the committed `translation/*.md` themselves: a
parser that silently matched nothing would leave every packet quietly context-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.packets import (
    DAYS_DIR,
    SOURCE_COLUMN,
    PacketBuilder,
    PacketRefused,
    Policy,
    band_rule,
    check_destination,
    condition_in_words,
    main_packet,
    parse_day_rows,
    parse_glossary,
    parse_places,
    table_rows,
    write_packets,
)
from boku.script_store import load_store, scene_day
from tests.synth_script import SynthStore, write_translation

VOICED = "E9001.0"
CHOICE = "E9001.1"
VOICE_ONLY = "E9001.2"

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
    return load_store(synth.write())


@pytest.fixture
def gated(tmp_path: Path):
    """`(store, derived day)` for one scene the data gives no day and a condition does.

    The quiz row is written for the day `scene_day` derives, so the packet has every
    day-keyed section it could get wrong: the header, the bible's § 4 entry, and the
    "on day d this event asks" line.
    """
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
def builder(store, tmp_path: Path):
    write_translation(
        tmp_path / "day01.txt", [(VOICED, "Uncle", "One. // Two.")], header="a day file"
    )
    return PacketBuilder.build(store, Policy.load(), [tmp_path / "day01.txt"], False)


# --- what a packet holds ------------------------------------------------------------------------


def test_a_packet_holds_every_section_a_translator_needs(store, builder):
    packet = builder.scene_packet(store.scenes[0])
    for heading in (
        "## Where and when",
        "## Cast",
        "## The scene, in the order the game plays it",
        "## The lines",
        "## The per-day quiz",
        "## The settled style rulings",
    ):
        assert heading in packet, f"{heading} is missing from the packet"
    assert f"### `{VOICED}`" in packet
    assert f"### `{VOICE_ONLY}`" in packet
    assert "voice only" in packet


def test_a_line_carries_the_store_s_own_capacity_numbers(store, builder):
    """The numbers a translator plans against come out of the store, not out of prose."""
    packet = builder.scene_packet(store.scenes[0])
    capacity = store.lines[VOICED]["capacity"]
    assert f"{capacity['bytes']} bytes per copy" in packet
    assert f"{capacity['pages']} page(s)" in packet
    assert "fixed by the voice clip" in packet
    columns = store.lines[VOICED]["layout"]["pages"][0]
    assert f"col 1 ({columns[0]:2d})" in packet


def test_the_band_rule_quotes_the_box_the_lint_measures_against(store, builder):
    """One home for the limit: `boku.layout.DIALOGUE_BAND` (`DOC-3`)."""
    from boku.layout import DIALOGUE_BAND

    rule = band_rule()
    assert f"{DIALOGUE_BAND.lines} lines of {DIALOGUE_BAND.width} px" in rule
    assert f"{DIALOGUE_BAND.guarded_width} px" in rule
    assert rule in builder.scene_packet(store.scenes[0])


def test_a_select_lists_its_options_against_their_branch_targets(store, builder):
    packet = builder.scene_packet(store.scenes[0])
    shape = store.lines[CHOICE]["select"]
    assert (
        f"{shape['prompt_lines']} prompt line(s) then "
        f"{shape['lines'] - shape['prompt_lines']} option(s)" in packet
    )
    assert "* prompt:" in packet
    assert "* option 1:" in packet


def test_the_quiz_says_which_day_each_question_belongs_to(store, builder):
    """Which question this event asks on THIS day -- the fact `TRN-02` exists to add."""
    packet = builder.scene_packet(store.scenes[0])
    row = store.scenes[0]["dinner_quiz"]["quiz"][0]
    assert "day d's question" in packet
    assert f"On day {row['day']} this event asks `E9001.{row['message']}`" in packet
    assert f"answer index {row['answer']}" in packet


def test_a_day_derived_from_the_condition_is_not_printed_as_the_scene_s_day(gated):
    """The header a translator reads first must not name a day the scene is not fixed to.

    `scene_day`'s second return says the day was read off one `day==N` *inside* the entry
    condition -- routinely one branch of an `|` whose sibling covers the other days, as in
    `E1006` -- so it is not the day the scene plays on. Printed as "Day N", it is a
    translator writing day-N context into a scene the player meets on other days.
    """
    store, day = gated
    packet = PacketBuilder.build(store, Policy.load(), [], False).scene_packet(store.scenes[0])
    line = next(row for row in packet.splitlines() if row.startswith("* **Day**"))
    assert f"**Day**: {day}" not in line
    assert "any day" in line
    assert f"day=={day}" in line, "the header must name the test the day was read off"


def test_a_derived_day_pulls_in_no_day_keyed_context(gated):
    """The same rule below the header: the bible's day entry and the quiz's day row are
    context for a day this scene is not fixed to, and read as fact once they are in the
    packet. The quiz table itself stays -- it says which day each question belongs to."""
    store, day = gated
    packet = PacketBuilder.build(store, Policy.load(), [], False).scene_packet(store.scenes[0])
    assert "## The day, from the story bible" not in packet
    assert f"On day {day} this event asks" not in packet
    assert "## The per-day quiz" in packet


def test_for_review_puts_the_current_english_beside_the_line(store, tmp_path):
    written = "One. // Two."
    write_translation(tmp_path / "day01.txt", [(VOICED, "Uncle", written)])
    plain = PacketBuilder.build(store, Policy.load(), [tmp_path / "day01.txt"], False)
    review = PacketBuilder.build(store, Policy.load(), [tmp_path / "day01.txt"], True)
    assert written not in plain.scene_packet(store.scenes[0])
    assert written in review.scene_packet(store.scenes[0])
    assert "English as it stands" in review.scene_packet(store.scenes[0])


def test_an_untranslated_neighbour_says_so_rather_than_guessing(store, builder):
    packet = builder.scene_packet(store.scenes[0])
    assert "## The scene before this one" not in packet  # the only scene in this store
    assert "## The scene after this one" not in packet


# --- determinism --------------------------------------------------------------------------------


def test_two_runs_are_byte_identical(store, builder, tmp_path):
    first = write_packets(builder, store.scenes, tmp_path / "a", day=1)
    second = write_packets(builder, store.scenes, tmp_path / "b", day=1)
    assert [path.name for path in first] == [path.name for path in second]
    for left, right in zip(first, second, strict=True):
        assert left.read_bytes() == right.read_bytes(), f"{left.name} differs between runs"


def test_a_day_packet_lists_its_scenes_in_order(store, builder, tmp_path):
    day = builder.day_packet(1, store.scenes)
    assert "| 1 | [`E9001`](E9001.md)" in day
    assert f"| {len(store.scenes[0]['lines'])} |" in day


# --- the destination a packet may never be written to --------------------------------------------


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


# --- conditions in words -------------------------------------------------------------------------


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
    assert condition_in_words(condition, Policy()) == expected


def test_a_compound_condition_keeps_its_structure():
    words = condition_in_words("flag[43]>=1 & lflag==0 | opt1", Policy())
    assert " and " in words
    assert " -- or -- " in words


def test_a_map_condition_names_the_place_when_the_bible_knows_it():
    policy = Policy.load()
    base, place = policy.places[0]
    assert place in condition_in_words(f"map=={base}", policy)
    assert "not" in condition_in_words(f"map!={base}", policy)


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
    """The table writes its ranges with an en dash, and `9-` means "until the next row".

    Read as the single day it starts on, every day inside an open-ended range loses its
    story context: day 10's packets would carry no § 4 entry at all.
    """
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


def test_the_glossary_matches_on_its_own_source_column():
    policy = Policy.load()
    assert policy.glossary, "no glossary rows parsed"
    row = policy.glossary[0]
    assert row in policy.glossary_for(f"...{row.terms[0]}...")
    assert policy.glossary_for("English only, no source term here") == []


def test_no_table_header_is_parsed_as_a_glossary_row():
    """A header read as data is a row whose "source term" is the word *source* itself,
    which then matches any text holding it -- and prints the header twice in the packet."""
    text = (REPO_ROOT / "translation" / "glossary.md").read_text(encoding="utf-8")
    headers = {header for _, header, _ in table_rows(text)}
    assert headers, "no Markdown tables were found in the glossary"
    parsed = parse_glossary(text)
    assert [row.cells for row in parsed if row.cells in headers] == []
    assert all(any(name.lower() == SOURCE_COLUMN for name in header) for header in headers), (
        f"a glossary table has no {SOURCE_COLUMN} column, so its rows are dropped in silence"
    )


def test_a_table_that_does_not_lead_with_source_is_keyed_on_it_anyway():
    """§ 4a leads with the insect's array index. Keyed on the first column instead, every
    one of its 57 rows has a bare number for a term, and a scene whose text holds that
    digit pulls in unrelated insects."""
    text = (REPO_ROOT / "translation" / "glossary.md").read_text(encoding="utf-8")
    insects = [row for row in parse_glossary(text) if row.section.startswith("4a.")]
    assert insects, "the 57 insect names did not parse"
    assert insects[0].header[0].lower() != SOURCE_COLUMN, "4a no longer leads with its index"
    assert [term for row in insects for term in row.terms if term.isdigit()] == []


def test_the_style_rulings_are_the_settled_ones():
    policy = Policy.load()
    assert policy.rulings, "no settled rulings parsed; packets would carry no policy"
    assert all("SETTLED" in heading or "SETTLED" in ruling for heading, ruling in policy.rulings)


def test_the_packet_reads_the_committed_day_files_by_default():
    assert DAYS_DIR.is_dir()
    assert any(DAYS_DIR.glob("*.txt"))
