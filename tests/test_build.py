"""The build's own refusals, the ones that do not need a disc.

`tests/test_trial.py` exercises the image writer against the real dump; what is left here
is the part of `boku.build` that decides *before* it ever opens an image — and one thing
that used to be decided nowhere at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boku.archive import ARCHIVE_NAME, EXE_NAME
from boku.build import (
    BuildRefused,
    EditSet,
    build,
    check_no_sector_clash,
    load_edit_set,
    original_draws_label,
)
from boku.glyphs import END_WORD, NEWLINE_WORD, PAGE_WORD, words_to_bytes
from boku.layout import DIALOGUE_BAND, CellMapEncoder, lay_out_message
from boku.lint import LABEL_MARKS, fit_page, label_allowance
from boku.reinsert import ByteEdit
from boku.relocate import SectorEdit
from boku.translation import SampleScenes


def test_a_translation_file_the_loader_could_not_read_stops_the_build(tmp_path):
    """The harm: a row typed with spaces instead of a tab is a line silently left Japanese.

    The loader has always collected these; nothing read them, so a malformed scene file
    produced a green build and no mention of the lines it had dropped.
    """
    scene = tmp_path / "scene.txt"
    scene.write_text("E0404.0 Uncle Gochisosama deshita.\n", encoding="utf-8")
    source = SampleScenes.from_paths([scene])
    assert source.problems, "the fixture is not malformed; this test would prove nothing"
    with pytest.raises(BuildRefused, match="reading the translation"):
        build(source=Path("no-such-image.img"), out_dir=tmp_path / "out", translation=source)
    assert not (tmp_path / "out").exists()


def test_the_same_translation_is_reported_rather_than_refused_when_skipping_is_asked_for(
    tmp_path,
):
    """`--skip-unfitted` carries on, but the problem still has to reach the report."""
    scene = tmp_path / "scene.txt"
    scene.write_text("E1.0\tA\tone\nE1.0\tA\ttwo\n", encoding="utf-8")
    source = SampleScenes.from_paths([scene])
    with pytest.raises(BuildRefused) as raised:
        build(
            source=Path("no-such-image.img"),
            out_dir=tmp_path / "out",
            translation=source,
            skip_unfitted=True,
            dry_run=True,
        )
    # It gets past the translation check and fails on the missing import instead, which is
    # what says the loader's problems no longer abort a skipping build.
    assert "no-such-image.img" in str(raised.value) or "disc" in str(raised.value)


# --- the renderer edit set, as `boku build --vwf` reads it --------------------------------------


def write_edit_set(path: Path, edits, **extra) -> Path:
    """An `edits.json` in the shape `tools/vwf/build_prototype.py --edits-only` writes."""
    path.write_text(
        json.dumps(
            {"format": 1, "cells": {"A": {"id": 292, "advance": 9}}, "edits": edits, **extra}
        ),
        encoding="utf-8",
    )
    return path


def test_an_edit_set_becomes_byte_edits_that_carry_what_they_expect_to_find(tmp_path):
    """The whole point of the file: the patch arrives as `ByteEdit`s and is verified.

    A renderer patch read from a file has no special standing — it goes through the same
    `verify_edits` gate a reinserted line does, so a stale edit set over a different dump
    is a refusal and not a corrupted executable.
    """
    path = write_edit_set(
        tmp_path / "edits.json",
        [
            {"file": "BOKU.BIN", "offset": 16, "old": "0000", "new": "0102", "reason": "sheet"},
            {
                "file": "SCPS_100.88",
                "offset": 4,
                "old": "deadbeef",
                "new": "00000000",
                "reason": "word",
            },
        ],
    )
    edit_set = load_edit_set(path)
    assert isinstance(edit_set, EditSet)
    assert [(e.file, e.offset, e.old, e.new) for e in edit_set.edits] == [
        ("BOKU.BIN", 16, b"\x00\x00", b"\x01\x02"),
        ("SCPS_100.88", 4, b"\xde\xad\xbe\xef", bytes(4)),
    ], "the edits are not sorted by (file, offset), which is the order the build applies"
    # The same file carries the font those bytes install, ready to measure English with.
    assert edit_set.encoder.cells == {"A": (292, 9)}


@pytest.mark.parametrize(
    ("edits", "extra", "message"),
    [
        (
            [{"file": "SCPS_100.88", "offset": 0, "old": "00", "new": "01"}],
            {"format": 2},
            "format 1",
        ),
        ([], {}, "no `edits`"),
        ([{"file": "OTHER.BIN", "offset": 0, "old": "00", "new": "01"}], {}, "may only write"),
        ([{"file": "SCPS_100.88", "offset": 0, "old": "0000", "new": "01"}], {}, "never changes"),
        ([{"file": "SCPS_100.88", "offset": 0, "old": "zz", "new": "01"}], {}, "non-hexadecimal"),
        ([{"file": "SCPS_100.88", "offset": -1, "old": "00", "new": "01"}], {}, "negative"),
        ([{"file": "SCPS_100.88", "offset": 0}], {}, r"not a \(file, offset, old, new\)"),
        (
            [
                {"file": "SCPS_100.88", "offset": 0, "old": "0000", "new": "0101"},
                {"file": "SCPS_100.88", "offset": 1, "old": "00", "new": "02"},
            ],
            {},
            "one of them would be lost",
        ),
    ],
)
def test_an_edit_set_this_build_could_not_apply_safely_is_refused(tmp_path, edits, extra, message):
    """Each row is a way a hand-edited or stale file could quietly corrupt an image."""
    path = write_edit_set(tmp_path / "edits.json", edits, **extra)
    with pytest.raises(Exception, match=message):
        load_edit_set(path)


def test_an_edit_set_that_is_not_json_names_the_file(tmp_path):
    path = tmp_path / "edits.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(BuildRefused, match=r"edits\.json"):
        load_edit_set(path)


# --- the speaker label's pixels ------------------------------------------------------------------

CELLS = CellMapEncoder(
    # Narrow enough that a label really costs a word, which is what makes the test bite.
    {
        c: (100 + i, 6)
        for i, c in enumerate("abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ.")
    },
    name="test cell map",
)

LABELLED = "Uncle"
PAGE = "the cicadas are loud enough to drown the radio out here on the veranda today"


def one_page_original(pages: int = 1) -> bytes:
    """Words for a `pages`-page unvoiced message: no `0x8002`, so the page count is free."""
    words = [200, END_WORD] if pages == 1 else [200, PAGE_WORD, 0, 200, END_WORD]
    return words_to_bytes(words)


def test_the_label_narrows_line_1_of_page_1_and_no_other_line():
    """The build reserves exactly what the lint charges, and in the same place.

    Derived from `boku.lint.fit_page`, the other implementation of the rule, rather than
    from a transcribed expectation: if the two ever disagree a line the lint passes would
    be inserted over the label, or one it fails would be refused by nobody.
    """
    reserve = label_allowance(CELLS, LABELLED, LABEL_MARKS)
    assert reserve > 0, "the fixture reserves nothing; this test would prove nothing"
    laid = lay_out_message(
        "E1.0", (PAGE,), one_page_original(), CELLS, DIALOGUE_BAND, reserve=reserve
    )
    broken, widths = fit_page(CELLS, PAGE, DIALOGUE_BAND, reserve)
    assert list(laid.pages[0]) == broken
    assert list(laid.widths[0]) == widths


def test_the_reserve_changes_the_break_at_all_which_is_what_makes_the_gate_above_bite():
    """The narrowest red: without the reserve the same page breaks somewhere else."""
    reserve = label_allowance(CELLS, LABELLED, LABEL_MARKS)
    with_label = lay_out_message(
        "E1.0", (PAGE,), one_page_original(), CELLS, DIALOGUE_BAND, reserve=reserve
    )
    without = lay_out_message("E1.0", (PAGE,), one_page_original(), CELLS, DIALOGUE_BAND)
    assert with_label.pages != without.pages


def test_the_label_is_charged_to_page_1_only():
    """Page 2 opens under no label, so it gets the whole box."""
    reserve = label_allowance(CELLS, LABELLED, LABEL_MARKS)
    laid = lay_out_message(
        "E1.0", (PAGE, PAGE), one_page_original(pages=2), CELLS, DIALOGUE_BAND, reserve=reserve
    )
    plain = lay_out_message("E1.0", (PAGE,), one_page_original(), CELLS, DIALOGUE_BAND)
    assert list(laid.pages[1]) == list(plain.pages[0])
    assert laid.pages[0] != laid.pages[1]


def words_bytes(*words: int) -> bytes:
    """`boku.glyphs.words_to_bytes`, spelled variadically for readability in a fixture."""
    return words_to_bytes(words)


def test_a_message_the_japanese_opened_with_a_speaker_is_the_one_that_reserves(tmp_path):
    """`「` after the first cell means a label; at the first cell it is an examine line."""
    mark = 999
    assert original_draws_label(words_bytes(5, 6, mark, 7, END_WORD), mark)
    assert not original_draws_label(words_bytes(mark, 5, 6, END_WORD), mark)
    # The mark on line 2 is quoted speech inside the body, not this line's speaker.
    assert not original_draws_label(words_bytes(5, NEWLINE_WORD, 6, mark, END_WORD), mark)
    assert not original_draws_label(words_bytes(5, 6, mark, END_WORD), None)


# --- a patch a relocation would also write ---------------------------------------------------
#
# The arithmetic is asserted against a real member of the real archive in
# `tests/test_real_vwf_build.py`, because what makes this check real is that
# `Archive.base_lba` and a `SectorEdit`'s `lba` are the same frame -- something no
# hand-chosen pair of numbers can say. What is left here is the two branches that need no
# disc: the near miss, and the file that is never written by LBA at all.


class ArchiveAt1000:
    """Only what `check_no_sector_clash` reads of an `Archive`: where `BOKU.BIN` starts."""

    base_lba = 1000


def test_a_patch_in_a_file_no_relocation_writes_is_never_compared():
    """`SCPS_100.88` is written only through its own extent, so it is out of scope."""
    exe = ByteEdit(file=EXE_NAME, offset=0x1000, old=b"\0" * 4, new=b"\1" * 4, reason="word")
    moved = SectorEdit(lba=1002, old=bytes(2048), new=b"\2" * 2048, reason="a member moved")
    check_no_sector_clash([exe], [moved], ArchiveAt1000())


def test_no_relocation_at_all_compares_nothing():
    """A build with no growth writes no sector by LBA, so there is nothing to clash with."""
    patch = ByteEdit(file=ARCHIVE_NAME, offset=0, old=b"\0" * 4, new=b"\1" * 4, reason="sheet")
    check_no_sector_clash([patch], [], ArchiveAt1000())
