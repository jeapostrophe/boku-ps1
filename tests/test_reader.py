"""`PLAN TRN-14` -- the reader: one linear walkthrough of every translated thing.

The gates here are derived from the translation files through the parsers the build and the
lint read them with, never from a retyped list of ids: "every id appears exactly once" is
only worth something if the id set comes from the source of truth.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from boku import REPO_ROOT, reader
from boku.lint import EM_DASH, load_rows, translation_paths
from boku.packets import DAYS_DIR
from boku.script_store import load_store
from tests.synth_script import SynthStore, write_translation

SURFACE = "exe@80001000"


@pytest.fixture
def walked(tmp_path: Path):
    """Day 1 held by `day01.txt` against its id order, an untranslated day-2 event, a
    day-independent event in `shared.txt`, one surface in `arrays.txt` and a voice-only line.
    The disc directory has no archive: textures and clips are not walked."""
    synth = SynthStore.new(tmp_path / "disc")
    synth.message("E9101.0", [[4]], voiced=True)
    synth.message("E9101.1", [[4]], voiced=False)
    synth.message("E9102.0", [[4]], voiced=False)
    synth.message("E9201.0", [[4]], voiced=False)
    synth.message("E9801.0", [[4]], voiced=False)
    synth.array_item(f"{SURFACE}.0")
    synth.array_item(f"{SURFACE}.1")
    synth.scene("E9101", ["E9101.0", "E9101.1"], day=1, voice_only=["E9101.2"])
    synth.scene("E9102", ["E9102.0"], day=1)
    synth.scene("E9201", ["E9201.0"], day=2)
    synth.scene("E9801", ["E9801.0"], day=None)["when"]["condition"] = "day>=1"
    synth.write()
    days = tmp_path / "days"
    days.mkdir()
    write_translation(
        days / "day01.txt",
        [
            ("E9102.0", "Uncle", "Two."),
            ("E9101.0", "Uncle", "One."),
            ("E9101.1", "Uncle", f"One {EM_DASH} and a half."),
            ("E9101.2", "(voice only)", ""),
        ],
    )
    write_translation(days / "shared.txt", [("E9801.0", "Boku", "Any day.")])
    write_translation(days / "arrays.txt", [(f"{SURFACE}.0", "(unlabelled)", "Item")])
    return tmp_path / "disc", days


def walk(walked, **kwargs) -> reader.Walkthrough:
    disc, days = walked
    sources = reader.Sources(
        disc_dir=disc, days=days, clips=None, movies=None, textures=None, **kwargs
    )
    return reader.build_walkthrough(sources)


def item_ids(walkthrough: reader.Walkthrough) -> list[str]:
    return [i for section in walkthrough.sections for item in section.items for i in item.ids]


def test_every_translated_id_is_walked_exactly_once(walked):
    """The id set is what the lint's loader reads out of the files, not a list typed here."""
    _, days = walked
    rows, _ = load_rows(translation_paths([days]))
    counts = Counter(item_ids(walk(walked)))
    assert {row.line_id for row in rows} <= set(counts)
    assert [i for i, n in counts.items() if n != 1] == []


def test_the_days_come_in_play_order_then_any_day_then_the_screens(walked):
    """A day file's order is the day as played; a day with no file still walks its events
    (untranslated, visibly); `shared.txt`'s events and then the surfaces follow the month."""
    walkthrough = walk(walked)
    assert [s.unit for s in walkthrough.sections] == ["day01", "day02", "shared", "arrays"]
    day1 = walkthrough.sections[0]
    assert [block.key for block in day1.blocks] == ["E9102", "E9101"]
    assert [i.id for i in day1.items] == ["E9102.0", "E9101.0", "E9101.1", "E9101.2"]
    untranslated = walkthrough.sections[1].items[0]
    assert (untranslated.id, untranslated.english) == ("E9201.0", ())
    surface = walkthrough.sections[-1]
    assert [i.id for i in surface.items] == [f"{SURFACE}.0", f"{SURFACE}.1"]


def test_an_item_carries_the_japanese_beside_the_english(walked):
    walkthrough = walk(walked)
    store = load_store(walked[0] / "script")
    item = next(i for i in walkthrough.sections[0].items if i.id == "E9101.0")
    assert item.english == ("One.",)
    assert item.speaker == "Uncle"
    # The label is split off as the Japanese speaker and the marks dropped, as the
    # translator's packet gives the line; every other glyph is on the item.
    glyphs = {c for c in store.japanese["E9101.0"].plain() if not c.isspace()} - set("「」『』")
    assert glyphs and glyphs <= set(item.japanese_speaker + "".join(item.japanese))
    assert item.japanese_speaker
    voice = next(i for i in walkthrough.sections[0].items if i.id == "E9101.2")
    assert voice.kind == reader.VOICE


def test_a_lint_finding_is_an_inline_mark_on_its_item(walked):
    """The lint's em-dash warning, carried to the one item it is about -- and to no other."""
    walkthrough = walk(walked)
    marked = {i.id: [m.check for m in i.marks] for i in walkthrough.sections[0].items}
    assert "em-dash" in marked["E9101.1"]
    assert "em-dash" not in marked["E9101.0"]


def test_a_row_for_no_line_in_the_script_is_walked_where_it_can_be_seen(walked):
    """An unknown id is on no screen; it gets a section of its own with the lint's error on
    it, rather than vanishing from the one place Jay reads everything."""
    _, days = walked
    with (days / "day01.txt").open("a", encoding="utf-8") as out:
        out.write("E9999.0\tUncle\tNobody says this.\n")
    walkthrough = walk(walked)
    last = walkthrough.sections[-1]
    assert last.unit is None
    assert [(i.id, [m.check for m in i.marks]) for i in last.items] == [("E9999.0", ["unknown-id"])]


def test_an_empty_row_for_no_line_reads_as_untranslated_not_as_a_blank(walked):
    _, days = walked
    with (days / "day01.txt").open("a", encoding="utf-8") as out:
        out.write("E9999.0\tUncle\t\n")
    assert walk(walked).sections[-1].items[0].english == ()


def test_a_finding_about_no_walked_item_is_a_notice(walked):
    """A row the loader cannot read has no id to hang a mark on; it must still be said."""
    _, days = walked
    with (days / "day01.txt").open("a", encoding="utf-8") as out:
        out.write("E9102.0 with no tab at all\n")
    assert any("malformed" in notice for notice in walk(walked).notices)


# --- the translator's notes ----------------------------------------------------------------------


def notes_of(walkthrough: reader.Walkthrough, line_id: str) -> tuple[str, ...]:
    return next(i.notes for s in walkthrough.sections for i in s.items if i.id == line_id)


def add_notes(days: Path, text: str) -> None:
    with (days / "day01.txt").open("a", encoding="utf-8") as out:
        out.write(text)


def test_a_note_below_its_line_is_shown_on_the_line_it_names(walked):
    """The committed convention puts `# NOTE <id>:` under the block, wrapped on `#   ` lines;
    attached to the row above it instead, it lands on the wrong line or on none."""
    _, days = walked
    add_notes(days, "# NOTE E9101.0: said at the gate\n#   and wrapped\n\n")
    walkthrough = walk(walked)
    assert notes_of(walkthrough, "E9101.0") == ("NOTE E9101.0: said at the gate and wrapped",)
    assert notes_of(walkthrough, "E9101.2") == ()


def test_a_note_naming_a_range_or_a_list_is_shown_on_its_first_line(walked):
    _, days = walked
    add_notes(days, "# NOTE E9101.1-.2: a range\n# NOTE E9102.0, .1: a list\n\n")
    walkthrough = walk(walked)
    assert notes_of(walkthrough, "E9101.1") == ("NOTE E9101.1-.2: a range",)
    assert notes_of(walkthrough, "E9102.0") == ("NOTE E9102.0, .1: a list",)


def test_a_note_naming_no_line_stays_on_the_line_above_it(walked):
    _, days = walked
    add_notes(days, "E9101.3\tUncle\tThree.\n# NOTE E9101.9: nobody\n")
    assert notes_of(walk(walked), "E9101.3") == ("NOTE E9101.9: nobody",)


# --- the TRN-04 state of each unit --------------------------------------------------------------


def test_every_unit_the_translation_files_make_has_a_state_and_every_state_a_unit():
    """`translation/status.tsv` is the one home of TRN-04's table. The units are what the
    reader walks, named from the committed files -- so a new day file, or a texture file no
    unit maps, fails here until it is given a state."""
    states = reader.read_status()
    assert set(states) == reader.walk_units()


def test_a_state_outside_trn_04_s_ladder_is_refused(tmp_path):
    path = tmp_path / "status.tsv"
    path.write_text("unit\tstate\tdate\tnote\nday01\tdone\t2026-09-24\t\n", encoding="utf-8")
    with pytest.raises(reader.ReaderRefused, match="done"):
        reader.read_status(path)


def test_a_unit_given_two_states_is_refused(tmp_path):
    path = tmp_path / "status.tsv"
    path.write_text(
        "unit\tstate\tdate\tnote\nday01\treviewed\t2026-09-23\t\nday01\tchecked\t2026-09-24\t\n",
        encoding="utf-8",
    )
    with pytest.raises(reader.ReaderRefused, match="day01"):
        reader.read_status(path)


def test_a_quote_in_a_note_does_not_swallow_the_next_row(tmp_path):
    path = tmp_path / "status.tsv"
    path.write_text(
        "unit\tstate\tdate\tnote\n"
        'day01\treviewed\t2026-09-23\t"reads well, Jay said\n'
        "day02\tchecked\t2026-09-24\t\n",
        encoding="utf-8",
    )
    states = reader.read_status(path)
    assert states["day01"].note == '"reads well, Jay said'
    assert states["day02"].state == "checked"


def test_each_section_shows_its_unit_s_state(walked, tmp_path):
    path = tmp_path / "status.tsv"
    path.write_text(
        "unit\tstate\tdate\tnote\nday01\tchecked\t2026-09-24\tread in the reader\n",
        encoding="utf-8",
    )
    walkthrough = walk(walked, status=path)
    assert walkthrough.sections[0].status == reader.Status(
        "day01", "checked", "2026-09-24", "read in the reader"
    )
    assert walkthrough.sections[1].status is None


# --- the page ------------------------------------------------------------------------------------


def page_data(index: Path) -> dict:
    """The walkthrough the page embeds, read back out of the HTML."""
    text = index.read_text(encoding="utf-8")
    found = re.search(r'<script id="walk" type="application/json">(.*?)</script>', text, re.S)
    assert found, "the page carries no walkthrough"
    return json.loads(found.group(1))


def test_the_page_embeds_every_item_once(walked, tmp_path):
    out = tmp_path / "work" / "reader"
    walkthrough = walk(walked)
    index = reader.write_site(walkthrough, out)
    data = page_data(index)
    ids = [
        i
        for section in data["sections"]
        for block in section["blocks"]
        for item in block["items"]
        for i in ([s["id"] for s in item.get("strings", [])] or [item["id"]])
    ]
    assert ids == item_ids(walkthrough)


def test_a_line_that_closes_a_script_tag_cannot_end_the_embedded_data(walked, tmp_path):
    _, days = walked
    write_translation(days / "shared.txt", [("E9801.0", "Boku", "</script><b>x</b>")])
    index = reader.write_site(walk(walked), tmp_path / "work" / "reader")
    english = [
        item["en"]
        for section in page_data(index)["sections"]
        for block in section["blocks"]
        for item in block["items"]
        if item["id"] == "E9801.0"
    ]
    assert english == [["</script><b>x</b>"]]


def test_a_rebuild_removes_only_the_images_the_reader_wrote(walked, tmp_path):
    out = tmp_path / "work" / "reader"
    (out / "img").mkdir(parents=True)
    (out / "img" / "stale.en.png").write_bytes(b"old")
    (out / "img" / "keep.txt").write_text("not the reader's", encoding="utf-8")
    reader.write_site(walk(walked), out)
    assert sorted(p.name for p in (out / "img").iterdir()) == ["keep.txt"]


def test_a_texture_group_the_recipe_refuses_carries_the_refusal():
    """`Inventory.get` raises `TextureError` for a texture this import does not have; a group
    is marked with it, and the rest of the walk goes on."""
    from boku.textures import TextureError

    def refuses(*_):
        raise TextureError("no texture _DATA_X.BIN__000000 in this import")

    images, marks, edits = reader.build_group(refuses, None, None, None, [], [], [])
    assert (images, edits) == ([], [])
    assert [m.message for m in marks] == ["no texture _DATA_X.BIN__000000 in this import"]


def test_the_page_is_never_written_where_the_repo_would_track_it(walked):
    with pytest.raises(reader.ReaderRefused, match="work/"):
        reader.write_site(walk(walked), REPO_ROOT / "translation" / "reader")


# --- the real import ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_walkthrough(disc_dir, archive, texture_inventory) -> reader.Walkthrough:
    return reader.build_walkthrough(
        reader.Sources(disc_dir=disc_dir), archive=archive, inv=texture_inventory
    )


def committed_ids() -> list[str]:
    """Every id the committed translation holds, through each file's own parser."""
    from boku import movie_cues
    from boku.texture_text import read_entries

    rows, _ = load_rows(translation_paths([DAYS_DIR, reader.CLIP_FILE]))
    cues, _ = movie_cues.read()
    return [
        *(row.line_id for row in rows),
        *(cue.key for cue in cues),
        *read_entries(),
    ]


def test_every_committed_id_is_walked_exactly_once(real_walkthrough):
    counts = Counter(item_ids(real_walkthrough))
    expected = committed_ids()
    assert len(expected) == len(set(expected)), "the translation itself holds an id twice"
    assert [i for i in expected if counts[i] != 1] == []


_ONE_ID_NOTE = re.compile(r"^#\s*NOTE ([^\s,*:]+?):")


def test_every_committed_note_naming_one_line_is_on_that_line(real_walkthrough):
    """Read off the committed files: a `# NOTE <id>:` that names a single id, where that id
    is walked, shows on that item."""
    items = {i.id: i for s in real_walkthrough.sections for i in s.items}
    missing = []
    for path in [*translation_paths([DAYS_DIR]), reader.CLIP_FILE]:
        for line in path.read_text(encoding="utf-8").splitlines():
            found = _ONE_ID_NOTE.match(line)
            if found and "-" not in found.group(1) and found.group(1) in items:
                note_id = found.group(1)
                if not any(n.startswith(f"NOTE {note_id}:") for n in items[note_id].notes):
                    missing.append(f"{path.name}: {note_id}")
    assert missing == []


def test_every_unit_walked_has_a_state_and_every_state_is_walked(real_walkthrough):
    walked_units = [s.unit for s in real_walkthrough.sections if s.unit is not None]
    assert sorted(walked_units) == sorted(reader.read_status())
    assert all(s.status is not None for s in real_walkthrough.sections if s.unit is not None)


def test_every_texture_item_shows_the_original_and_the_english(real_walkthrough):
    textures = [
        item for section in real_walkthrough.sections for item in section.items
        if item.kind == reader.TEXTURE
    ]  # fmt: skip
    assert textures
    for item in textures:
        captions = [caption for caption, _ in item.images]
        assert captions and captions.count("original") == captions.count("English"), item.id
        for _, name in item.images:
            assert name in real_walkthrough.files, (item.id, name)


def test_the_english_images_are_the_edits_the_build_writes(real_walkthrough, texture_edits):
    """The reader builds each texture group on its own, to know which strings drew which
    image; the images it shows are only the game's if those edits together are the build's."""

    def key(edit):
        return edit.file, edit.offset, edit.old, edit.new

    assert sorted(real_walkthrough.texture_edits, key=key) == sorted(texture_edits.edits, key=key)
