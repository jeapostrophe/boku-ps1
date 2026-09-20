"""Text sites and the glyph sheet, checked without a disc.

The two fixtures that matter here are read out of `research/text-renderer.md` § 7 rather
than typed into this file. That note is the source of truth for the trial: it is where
the three immediates and the thirteen glyph words of "Hello, Boku!" were measured. A
hand-written copy of them here would pass exactly when the code and the copy were wrong
together, which is the failure this project has measured before; parsing the note means
the gate breaks the moment the code and the research disagree.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from boku.text import (
    END_WORD,
    PAD_WORD,
    GlyphTable,
    SiteIndex,
    TextError,
    TextSite,
    check_placement,
    line_key_of,
    load_member_offsets,
    load_sites,
)
from boku.trial import RENDERER_PATCH, TRIAL_TEXT

RECIPE = Path(__file__).resolve().parents[1] / "research/text-renderer.md"
RECIPE_SECTION = "## 7. The `TXT-04` trial"


def recipe_section() -> str:
    text = RECIPE.read_text(encoding="utf-8")
    start = text.index(RECIPE_SECTION)
    return text[start : text.index("\n## ", start + 1)]


# --- the recipe, read back out of the research note ------------------------------------


def test_the_renderer_patch_is_the_table_in_the_research_note():
    """Step A: file offset, the bytes that must be there, the bytes to write."""
    rows = re.findall(
        r"^\|\s*`0x([0-9A-Fa-f]+)`\s*\|\s*`([0-9A-Fa-f ]+)`\s*\|\s*`([0-9A-Fa-f ]+)`\s*\|",
        recipe_section(),
        re.M,
    )
    assert len(rows) == 3, f"{RECIPE} § 7 Step A no longer holds three rows: {rows}"
    assert [
        (f"{item.file_offset:X}", item.old.hex(" ").upper(), item.new.hex(" ").upper())
        for item in RENDERER_PATCH
    ] == [(offset.upper(), old.upper(), new.upper()) for offset, old, new in rows]


def test_english_encodes_to_the_words_the_research_note_measured():
    """Step B: the glyph table and the note have to agree about "Hello, Boku!".

    `GlyphTable` derives its map from `research/data/glyph-table.tsv` by normalising the
    full-width characters it records; the note lists the resulting words. Neither was
    copied from the other, so their agreeing is evidence that the derivation is right.
    """
    listed = re.findall(r"^`((?:[0-9A-F]{4} )+8000)`$", recipe_section(), re.M)
    assert len(listed) == 1, f"{RECIPE} § 7 no longer holds exactly one glyph-word line"
    expected = b"".join(int(word, 16).to_bytes(2, "little") for word in listed[0].split())
    encoded = GlyphTable.load().encode(TRIAL_TEXT) + END_WORD.to_bytes(2, "little")
    assert encoded == expected
    assert len(expected) == 26, "the note says the site must be at least 26 bytes"


# --- the glyph sheet --------------------------------------------------------------------


@pytest.fixture(scope="module")
def glyphs() -> GlyphTable:
    return GlyphTable.load()


def test_the_sheet_draws_letters_digits_and_the_space(glyphs: GlyphTable):
    for character in "ABZabz09 .,!?":
        assert character in glyphs.to_glyph, character
    assert glyphs.to_glyph[" "] == 0, "glyph 0 is the blank cell"


def test_a_character_the_sheet_cannot_draw_is_named_rather_than_substituted(glyphs: GlyphTable):
    assert glyphs.unencodable("don't") == ["'"]
    with pytest.raises(TextError, match="no cell"):
        glyphs.encode("don't")


def test_a_message_is_terminated_and_then_padded_to_the_original_length(glyphs: GlyphTable):
    body = glyphs.message("Hi", 12)
    assert len(body) == 12
    assert body[:4] == glyphs.encode("Hi")
    assert body[4:6] == END_WORD.to_bytes(2, "little")
    assert body[6:] == PAD_WORD.to_bytes(2, "little") * 3


def test_a_message_that_does_not_fit_is_refused_rather_than_cut(glyphs: GlyphTable):
    assert len(glyphs.message("abcd", 10)) == 10
    with pytest.raises(TextError, match="nothing is cut to fit"):
        glyphs.message("abcde", 10)


def test_a_newline_is_the_control_word_not_a_glyph(glyphs: GlyphTable):
    assert glyphs.encode("a\nb")[2:4] == (0x8001).to_bytes(2, "little")


# --- sites ------------------------------------------------------------------------------


def site(**overrides) -> TextSite:
    fields = {
        "member": "EV0112.BIN",
        "container": "ev",
        "table": 0,
        "block_id": 112,
        "index": 0,
        "offset": 0x100,
        "size": 32,
        "slack": 0,
        "kind": "MSG+XA",
        "line_key": "a" * 12,
    }
    fields.update(overrides)
    return TextSite(**fields)


def test_a_site_id_names_an_event_and_a_message_index():
    assert site().site_id == "E0112.0"
    assert site(block_id=6, index=3).site_id == "E0006.3"


def test_two_sites_that_differ_only_by_their_table_are_not_the_same_site():
    """The `c1` containers restart their indices per table, so the table is part of the name."""
    first = site(member="M_A01000.BIN", container="c1", table=0, index=0)
    second = site(
        member="M_A01000.BIN", container="c1", table=1, index=0, offset=0x200, line_key="b" * 12
    )
    assert first.site_id != second.site_id
    index = SiteIndex([first, second], {"M_A01000.BIN": 0x1000})
    assert [entry.file_offset for entry in index.copies_of(second.site_id)] == [0x1200]


def test_two_sites_with_one_name_are_refused_rather_than_resolved_to_the_first():
    """`--line <id>` must write where the id says, or it writes somewhere else entirely."""
    twin = site(member="M_A01000.BIN", container="c1", table=0, index=0)
    with pytest.raises(TextError, match="two text sites are both called"):
        SiteIndex([twin, replace(twin, offset=0x200)], {"M_A01000.BIN": 0x1000})


def test_every_copy_of_a_line_is_found_by_key_and_by_any_of_its_site_ids():
    """`--line E0112.0` has to reach the copy in another event, or the trial proves less."""
    here = site()
    elsewhere = site(member="EV0700.BIN", block_id=700, index=4, offset=0x900)
    unrelated = site(member="EV0700.BIN", block_id=700, index=5, line_key="b" * 12)
    index = SiteIndex([here, elsewhere, unrelated], {"EV0112.BIN": 0x1000, "EV0700.BIN": 0x2000})
    assert [entry.site.site_id for entry in index.copies_of("a" * 12)] == ["E0112.0", "E0700.4"]
    assert index.copies_of("E0700.4") == index.copies_of("E0112.0")
    with pytest.raises(TextError, match="no text site"):
        index.copies_of("E9999.0")


def test_a_site_is_placed_at_its_member_offset_plus_its_own():
    index = SiteIndex([site()], {"EV0112.BIN": 0x1000})
    placed = index.copies_of("a" * 12)[0]
    assert (placed.file_name, placed.file_offset, placed.end) == ("BOKU.BIN", 0x1100, 0x1120)


def test_an_exe_site_is_placed_at_its_own_offset():
    index = SiteIndex([site(member="SCPS_100.88", container="array@0x1a2fc", kind="ARR-E")], {})
    placed = index.copies_of("a" * 12)[0]
    assert (placed.file_name, placed.file_offset) == ("SCPS_100.88", 0x100)


def test_a_site_whose_member_is_unknown_is_refused_rather_than_guessed():
    with pytest.raises(TextError, match=re.escape("not in boku-bin-members.tsv")):
        SiteIndex([site()], {})


def test_the_bytes_on_the_disc_have_to_hash_to_what_the_table_recorded():
    """The gate that makes a committed table safe to write from."""
    content = b"\x45\x00\x00\x80" + bytes(28)
    index = SiteIndex([site(line_key=line_key_of(content))], {"EV0112.BIN": 0x1000})
    placed = index.copies_of(line_key_of(content))[0]
    check_placement(placed, content)
    with pytest.raises(TextError, match="table and this image disagree"):
        check_placement(placed, bytes(32))
    with pytest.raises(TextError, match="the site is 32"):
        check_placement(placed, content[:30])


# --- the committed tables ------------------------------------------------------------------


def test_the_committed_tables_load_and_line_up():
    """`text-sites.tsv` names only members `boku-bin-members.tsv` knows, so every site places."""
    sites = load_sites()
    index = SiteIndex(sites, load_member_offsets())
    assert len(index) == len(sites) > 6000
    assert len(index.line_keys) < len(sites), "the disc repeats lines; the grouping must see it"
    assert {entry.file_name for entry in index.placed} == {"BOKU.BIN", "SCPS_100.88"}
    events = list(index.event_messages())
    assert len(events) > 1000
    assert all(entry.site.container == "ev" and entry.file_name == "BOKU.BIN" for entry in events)


def test_every_site_in_the_committed_table_is_reachable_by_its_own_id():
    """The round trip the whole `--line` switch rests on, over the real 6,183 rows.

    Nothing is typed in here: the table is the source of truth, and the property asked of
    it is that resolving a row's own id lands on that row and no other. It fails on any
    id scheme that two rows can share -- under `member:container:index` the disc had 750
    such names and the second row of each was unreachable, so `--line` would have
    rewritten the first one's bytes and reported success.
    """
    index = SiteIndex()
    by_place = {(entry.file_name, entry.file_offset): entry for entry in index.placed}
    assert len(by_place) == len(index.placed), "two rows place at one byte range"
    for entry in index.placed:
        found = index.copies_of(entry.site.site_id)
        assert (entry.file_name, entry.file_offset) in {
            (copy.file_name, copy.file_offset) for copy in found
        }, f"{entry.site.site_id} resolves somewhere else"
