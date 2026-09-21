"""Placing text sites into files, and the `TXT-04` recipe read back out of its note.

The two fixtures that matter here are read out of `research/text-renderer.md` § 7 rather
than typed into this file. That note is the source of truth for the trial: it is where
the three immediates and the thirteen glyph words of "Hello, Boku!" were measured. A
hand-written copy of them here would pass exactly when the code and the copy were wrong
together, which is the failure this project has measured before; parsing the note means
the gate breaks the moment the code and the research disagree.

The site half is about one property: **a line id names every physical copy of that line,
and only those.** Under the earlier per-site scheme a map-resident line could not be asked
for by its event id at all, and grouping by bytes swept up the 246 byte strings that two
different lines happen to share.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from boku.glyphs import END_WORD, PAD_WORD, GlyphTable, TextError
from boku.sites import Site
from boku.text import PlacedSite, SiteIndex
from boku.trial import RENDERER_PATCH, TRIAL_TEXT

RECIPE = Path(__file__).resolve().parents[1] / "research/text-renderer.md"
RECIPE_SECTION = "## 7. The `TXT-04` trial"


def index_of(placed) -> SiteIndex:
    """A `SiteIndex` over hand-built sites, with no import behind it.

    `SiteIndex` needs the archive and the walk it came from — `boku.reinsert` asks for
    both — and these tests build their sites by hand, so they hand in the pair that says
    so: nothing here may ask this index to rebuild a container.
    """
    return SiteIndex(placed, archive=None, walk=None)


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
    encoded = GlyphTable.load().encode_english(TRIAL_TEXT) + END_WORD.to_bytes(2, "little")
    assert encoded == expected
    assert len(expected) == 26, "the note says the site must be at least 26 bytes"


# --- writing English into a site --------------------------------------------------------


@pytest.fixture(scope="module")
def glyphs() -> GlyphTable:
    return GlyphTable.load()


def test_a_character_the_sheet_cannot_draw_is_named_rather_than_substituted(glyphs: GlyphTable):
    assert glyphs.unencodable("don't") == ["'"]
    with pytest.raises(TextError, match="no cell"):
        glyphs.encode_english("don't")


def test_a_message_is_terminated_and_then_padded_to_the_original_length(glyphs: GlyphTable):
    body = glyphs.message("Hi", 12)
    assert len(body) == 12
    assert body[:4] == glyphs.encode_english("Hi")
    assert body[4:6] == END_WORD.to_bytes(2, "little")
    assert body[6:] == PAD_WORD.to_bytes(2, "little") * 3


def test_a_message_that_does_not_fit_is_refused_rather_than_cut(glyphs: GlyphTable):
    assert len(glyphs.message("abcd", 10)) == 10
    with pytest.raises(TextError, match="nothing is cut to fit"):
        glyphs.message("abcde", 10)


def test_a_newline_is_the_control_word_not_a_glyph(glyphs: GlyphTable):
    assert glyphs.encode_english("a\nb")[2:4] == (0x8001).to_bytes(2, "little")


# --- sites, placed --------------------------------------------------------------------------


def site(**overrides) -> Site:
    fields = {
        "file": "BOKU",
        "member": "EV0112.BIN",
        "container": "ev",
        "table": 0,
        "block_id": 112,
        "index": 0,
        "offset": 0x100,
        "size": 32,
        "slack": 0,
        "kind": "MSG+XA",
        "line_id": "E0112.0",
        "absolute": 0x1100,
    }
    fields.update(overrides)
    return Site(**fields)


def placed(site_: Site, key: str = "a" * 12) -> PlacedSite:
    return PlacedSite(site_, "BOKU.BIN", site_.absolute, key)


def test_one_id_names_every_copy_of_a_line_wherever_the_copies_live():
    """`E0112.0` has to reach the map-resident copies, or the trial proves less."""
    in_ev = placed(site())
    in_map = placed(site(member="M_G02001.BIN", container="c1", table=1, absolute=0x9000))
    other = placed(site(index=1, line_id="E0112.1", absolute=0x1200), key="b" * 12)
    index = index_of([in_ev, in_map, other])
    assert [e.file_offset for e in index.copies_of("E0112.0")] == [0x1100, 0x9000]
    assert [e.file_offset for e in index.copies_of("E0112.1")] == [0x1200]


def test_a_line_key_still_groups_by_bytes_which_is_the_coarser_question():
    """246 byte strings on the disc belong to more than one line; the ids keep them apart."""
    here = placed(site())
    twin = placed(site(block_id=700, member="EV0700.BIN", line_id="E0700.4", absolute=0x2100))
    index = index_of([here, twin])
    assert {e.line_id for e in index.copies_of("a" * 12)} == {"E0112.0", "E0700.4"}
    assert index.copies_of("E0112.0") == [here]


def test_an_id_nobody_has_is_refused_rather_than_resolved_to_something_else():
    index = index_of([placed(site())])
    with pytest.raises(TextError, match="no text site is called"):
        index.copies_of("E9999.0")


def test_two_sites_at_one_byte_range_are_refused():
    """A walk that emitted the same range twice would double-write it and count it twice."""
    entry = placed(site())
    with pytest.raises(TextError, match="both start at"):
        index_of([entry, replace(entry, line_key="b" * 12)])


def test_event_messages_are_the_map_resident_copies_as_well_as_the_ev_ones():
    """The bug this model replaced: `container == "ev"` missed 4,000-odd sites."""
    in_map = placed(site(member="M_G02001.BIN", container="c1", absolute=0x9000))
    array = placed(
        site(
            file="EXE",
            member="SCPS_100.88",
            container="array@0x36a14",
            kind="ARR-E",
            line_id="exe@80046214.0",
            absolute=0x36A14,
        ),
        key="c" * 12,
    )
    index = index_of([placed(site()), in_map, array])
    assert {e.line_id for e in index.event_messages()} == {"E0112.0"}
    assert len(list(index.event_messages())) == 2


# --- against the real import -------------------------------------------------------------------


def test_every_site_of_the_real_import_is_reachable_by_its_own_id(site_index: SiteIndex):
    """The round trip the whole `--line` switch rests on, over all 6,193 sites.

    Nothing is typed in: the walk is the source of truth, and the property asked of it is
    that resolving a site's own id lands on that site among others. It fails on any id
    scheme two unrelated sites can share.
    """
    assert len(site_index) > 6000
    assert {e.file_name for e in site_index.placed} == {"BOKU.BIN", "SCPS_100.88"}
    for entry in site_index.placed:
        found = site_index.copies_of(entry.line_id)
        assert (entry.file_name, entry.file_offset) in {
            (copy.file_name, copy.file_offset) for copy in found
        }, f"{entry.line_id} resolves somewhere else"


def test_the_opening_line_of_the_game_is_addressable_by_its_event_id(site_index: SiteIndex):
    """`E0171` is map-resident with no `EV.BIN` copy; the earlier model could not name it."""
    copies = site_index.copies_of("E0171.0")
    assert copies
    assert all(copy.site.container == "c1" for copy in copies)


def test_the_index_walks_the_archive_that_is_already_open(site_index: SiteIndex, archive):
    """One import, opened once -- `from_disc` is handed the `Archive` its caller holds.

    `Archive.__init__` is the only thing that reads `BOKU.BIN`, and it reads all 109 MB
    into memory. A caller that already has one and lets `from_disc` open its own reads the
    file a second time and keeps 218 MB resident for as long as both live, which is what
    the font build's step 1 was doing. Identity is the check: a second read is a second
    object, and there is no cheaper way to tell them apart.
    """
    assert site_index.archive is archive


def test_a_line_with_many_copies_returns_all_of_them_and_they_are_the_same_bytes(
    site_index: SiteIndex,
):
    many = max(site_index.line_ids, key=lambda i: len(site_index.copies_of(i)))
    copies = site_index.copies_of(many)
    assert len(copies) > 5
    assert len({copy.line_key for copy in copies}) == 1
