"""`VO-02`: English on a voice-only `XA` entry, from the day file to the rebuilt block.

A voice-only entry has a voice key and a **null** text offset (`research/text-format.md`);
`asm/voice.asm` makes the `XA` handler open whatever text the entry has. What is tested
here is the pipeline half: that a `(voice only)` row carrying English reaches that null
slot in every copy of the block, laid out as a page-timed subtitle, and that nothing a
text line relies on moves. The archives are built by `tests/synth_archive.py` and read
back by the package's own parsers, as in `tests/test_reinsert.py`.
"""

from __future__ import annotations

import pytest

from boku import REPO_ROOT, clip_subs
from boku.archive import Archive, parse_pack
from boku.build import lay_out
from boku.events import OP_XA, OP_XAMSG, Block, parse_block_table
from boku.glyphs import END_WORD, PAGE_WORD, words_to_bytes
from boku.layout import DIALOGUE_BAND, StockEncoder, lay_out_subtitle
from boku.reinsert import ReinsertRefused, plan
from boku.translation import VOICE_ONLY, SampleScenes, TranslationEntry
from boku.voice import SEEK_TICKS, VOICE_TSV, clip_ticks, read_hand_columns, subtitle_waits
from tests import synth_archive as synth
from tests.test_reinsert import map_pack, synthetic_disc, text_bytes, walk

END_OP = 0x15
KEY = synth.voice_key(start=0x100, end=0x100 + 16 * 100, channel=0)
"""A clip of 101 sectors of its own channel."""


def a_scene_with_a_voice_only_clip() -> bytes:
    """Message 0 is voiced text; message 1 is voice only -- a key and a null text entry."""
    code = (
        synth.instruction(OP_XAMSG, 4, bytes([1, 0x71, 0, 0, 0]))
        + synth.instruction(OP_XA, 4, bytes([0, 0, 1, 0, 0xFF]))
        + synth.instruction(END_OP, 1)
    )
    return synth.block(
        [
            synth.cast([(0, 1)]),
            synth.condition(),
            code,
            synth.voice_key(),
            text_bytes((0x100, 0x101, END_WORD)),
            KEY,
            None,
        ]
    )


def two_maps():
    block = a_scene_with_a_voice_only_clip()
    return synthetic_disc(
        maps=[("A01000", map_pack([(171, block)])), ("A01100", map_pack([(171, block)]))]
    )


# --- the day file ------------------------------------------------------------------------------


def test_a_voice_only_row_with_english_is_a_subtitle_and_one_without_is_not_script(tmp_path):
    path = tmp_path / "scene.txt"
    path.write_text(
        "E0171.1\t(voice only)\tI thought so. // And then I went home.\nE0171.2\t(voice only)\n",
        encoding="utf-8",
    )
    source = SampleScenes.from_paths([path])
    assert source.problems == ()
    (entry,) = list(source)
    assert entry.line_id == "E0171.1"
    assert entry.voice_only
    assert entry.pages == ("I thought so.", "And then I went home.")


# --- the walk ----------------------------------------------------------------------------------


def test_the_walk_lists_every_copy_of_a_voice_only_entry_apart_from_the_text_sites():
    archive = two_maps()
    result = walk(archive)
    assert result.problems == []
    copies = result.voice_only["E0171.1"]
    assert sorted(site.member for site in copies) == ["M_A01000.BIN", "M_A01100.BIN"]
    assert all(site.kind == "MSG+XA" and site.size == 0 for site in copies)
    # The site points at the clip's key, which is how the layout times the pages.
    assert {archive.boku[s.absolute : s.absolute + len(KEY)] for s in copies} == {KEY}
    # A voice-only entry is not a text site: the text tables and the round trip never see it.
    assert "E0171.1" not in result.by_line
    assert set(result.voice_only) == {"E0171.1"}


# --- timing ------------------------------------------------------------------------------------


def test_a_clip_is_timed_in_the_game_ticks_its_sector_count_lasts():
    """One sector of the clip's own channel is 3.2 event ticks (`boku.voice`)."""
    assert clip_ticks(synth.voice_key(start=0, end=16 * 100)) == round(101 * 3.2)
    assert clip_ticks(synth.voice_key(start=0, end=0)) == 3, "a key with end == start plays"


def test_page_waits_share_the_clip_by_length_and_the_first_page_covers_the_seek():
    even = subtitle_waits(["one two", "six ten"], 200)
    assert even == [SEEK_TICKS + 100]
    lopsided = subtitle_waits(["a", "a much longer second page", "c"], 300)
    assert len(lopsided) == 2
    assert lopsided[0] < lopsided[1]
    assert sum(lopsided) < SEEK_TICKS + 300, "the last page is closed by the clip, not a timer"
    assert subtitle_waits(["only page"], 300) == []


def test_no_page_is_given_a_zero_wait_which_would_never_turn():
    """`dialog_draw` counts `g_text_wait` down only while it is non-zero."""
    waits = subtitle_waits(["x", "y", "z", "w"], 0)
    assert all(wait >= 1 for wait in waits)


def test_a_subtitle_is_laid_out_in_the_band_with_its_waits_after_each_break():
    encoder = StockEncoder.load()
    laid = lay_out_subtitle("E0171.1", ["ab", "cd"], 320, encoder, DIALOGUE_BAND)
    assert laid.problems == ()
    at = laid.words.index(PAGE_WORD)
    assert laid.words[at + 1] == subtitle_waits(["ab", "cd"], 320)[0]
    assert laid.words[-1] == END_WORD


# --- the build's layout ------------------------------------------------------------------------


def test_the_build_lays_a_voice_only_row_out_against_its_own_clip():
    archive = two_maps()
    result = walk(archive)
    entry = TranslationEntry(line_id="E0171.1", speaker=VOICE_ONLY, pages=("ab", "cd"))
    (line,) = lay_out(
        archive, result, [entry], StockEncoder.load(), DIALOGUE_BAND, voice_subtitles=True
    )
    assert line.problems == ()
    words = line.laid_out.words
    assert words[words.index(PAGE_WORD) + 1] == subtitle_waits(["ab", "cd"], clip_ticks(KEY))[0]


@pytest.mark.parametrize(
    ("line_id", "problem"),
    [
        ("E0171.0", "has text on the disc"),
        ("E0171.7", "no voice-only entry"),
    ],
)
def test_a_voice_only_row_must_name_a_voice_only_entry(line_id, problem):
    archive = two_maps()
    entry = TranslationEntry(line_id=line_id, speaker=VOICE_ONLY, pages=("ab",))
    (line,) = lay_out(
        archive, walk(archive), [entry], StockEncoder.load(), DIALOGUE_BAND, voice_subtitles=True
    )
    assert line.laid_out is None
    assert any(problem in p for p in line.problems), line.problems


def test_a_build_that_installs_no_voice_hook_refuses_a_subtitle_rather_than_claim_it():
    """The stock `XA` handler never reads the entry's text; writing it anyway would list the
    line as written in the manifest, and coverage would call it shipped."""
    archive = two_maps()
    entry = TranslationEntry(line_id="E0171.1", speaker=VOICE_ONLY, pages=("ab",))
    (line,) = lay_out(archive, walk(archive), [entry], StockEncoder.load(), DIALOGUE_BAND)
    assert line.laid_out is None
    assert any("asm/voice.asm" in p for p in line.problems), line.problems


# --- the rebuild -------------------------------------------------------------------------------


def blocks_of(archive: Archive) -> list[Block]:
    out = []
    for name in ("M_A01000.BIN", "M_A01100.BIN"):
        pack = parse_pack(archive.blob(archive.member(name)))
        table = parse_block_table(pack.children[1], name)
        out.append(Block(table.blocks[0][1]))
    return out


def test_english_fills_the_null_entry_of_every_copy_and_moves_nothing_else():
    archive = two_maps()
    result = walk(archive)
    words = (0x200, 0x201, 0x202, END_WORD)
    the_plan = plan(archive, result, {"E0171.1": words})
    blob = bytearray(archive.boku)
    for edit in the_plan.edits:
        assert blob[edit.offset : edit.end] == edit.old
        blob[edit.offset : edit.end] = edit.new
    after = Archive.from_bytes(archive.exe, bytes(blob), source="rebuilt")
    after.require_clean()
    for old, new in zip(blocks_of(archive), blocks_of(after), strict=True):
        assert new.message_text(1)[: 2 * len(words)] == words_to_bytes(words)
        assert new.message_key(1) == old.message_key(1)
        assert new.message_text(0) == old.message_text(0)
        assert new.entry(2) == old.entry(2), "the bytecode is not rewritten"
    # Read back as text now: the XA-named entry is a message site of its own.
    again = walk(after)
    assert again.problems == []
    assert "E0171.1" in again.by_line and "E0171.1" not in again.voice_only


def test_a_voice_only_entry_cannot_be_written_in_place_because_it_has_no_bytes():
    archive = two_maps()
    with pytest.raises(ReinsertRefused, match="voice-only"):
        plan(archive, walk(archive), {"E0171.1": (0x200, END_WORD)}, in_place=True)


def test_empty_words_are_refused_by_name_not_by_a_formatting_crash():
    archive = two_maps()
    with pytest.raises(ReinsertRefused, match="end with nothing"):
        plan(archive, walk(archive), {"E0171.1": ()})


# --- the committed translation against the inventory -------------------------------------------


def test_every_clip_the_inventory_hears_words_in_has_english_and_no_wordless_one_does():
    """`PLAN VO-04`: `research/data/voice-only.tsv`'s `said` column is the listening pass's
    verdict on every clip; a worded one left without English plays with nothing on screen."""
    said = {
        line_id: hand["said"]
        for line_id, hand in read_hand_columns(VOICE_TSV.read_text(encoding="utf-8")).items()
    }
    worded = {line_id for line_id, words in said.items() if words != "wordless"}
    days = SampleScenes.from_paths(sorted((REPO_ROOT / "translation" / "days").glob("*.txt")))
    clips, problems = clip_subs.read()
    assert days.problems == () and problems == []
    english = {e.line_id for e in days if e.voice_only and e.pages}
    english |= {e.line_id for e in clips if e.pages}  # a clip row carries its speaker
    assert sorted(worded - english) == [], "worded clips with no English"
    assert sorted((english & said.keys()) - worded) == [], "English on a wordless clip"
