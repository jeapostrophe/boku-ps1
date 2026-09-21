"""The provisional reader for the draft samples, and the seam it sits behind.

`PIPE-02` — the committed translation format — is Jay's decision and is not made here, so
what is tested is only that the loader reads what `translation/days/` *already
contains*, and that the seam (`TranslationSource`) is what the build depends on rather
than any particular file format. The day files are tracked, so the fixtures here are the real
ones: the loader is checked against the translation it exists to read.
"""

from __future__ import annotations

from boku import REPO_ROOT
from boku.translation import PreEncoded, SampleScenes, TranslationEntry, select_fields

SAMPLES = REPO_ROOT / "translation" / "days"


def write(tmp_path, text: str):
    path = tmp_path / "scene.txt"
    path.write_text(text, encoding="utf-8")
    return SampleScenes.from_paths([path])


def test_it_reads_the_tracked_drafts_without_a_problem():
    source = SampleScenes.from_directory(SAMPLES)
    assert source.problems == (), source.problems
    ids = [entry.line_id for entry in source]
    assert len(ids) == len(set(ids)), "an id read twice would be written twice"
    assert all(i.startswith("E") for i in ids)
    assert any(entry.options for entry in source), "no [SEL] row; the drafts have some"
    assert any(len(entry.pages) > 1 for entry in source), "no ` // ` row; the drafts have some"


def test_a_page_break_splits_the_pages_in_the_originals_own_positions(tmp_path):
    source = write(tmp_path, "E0406.2\tAunt\tone // two // three\n")
    (entry,) = list(source)
    assert entry.pages == ("one", "two", "three")
    assert entry.speaker == "Aunt"


def test_a_select_row_is_its_options(tmp_path):
    source = write(tmp_path, "E0404.6\t[SEL]\tMelon | Strawberry | Lemon | Mizore\n")
    (entry,) = list(source)
    assert entry.options == ("Melon", "Strawberry", "Lemon", "Mizore")
    assert entry.pages == ()
    assert entry.is_select


def test_comments_blank_lines_and_voice_only_rows_are_not_script(tmp_path):
    source = write(
        tmp_path,
        "# a note\n\nE0650.3\t(voice only)\nE0650.4\tGuts\tThis is Boku-chan.\n",
    )
    assert [entry.line_id for entry in source] == ["E0650.4"]


def test_an_id_given_twice_is_reported_rather_than_silently_overwritten(tmp_path):
    source = write(tmp_path, "E1.0\tA\tone\nE1.0\tA\ttwo\n")
    assert [entry.line_id for entry in source] == ["E1.0"]
    assert any("already given" in problem for problem in source.problems)


def test_a_row_with_no_tab_is_reported(tmp_path):
    source = write(tmp_path, "E1.0 A one\n")
    assert list(source) == []
    assert any("no tab" in problem for problem in source.problems)


def test_a_selects_prompt_lines_are_read_off_the_front_and_are_not_options(tmp_path):
    """The committed convention lists the box's question first (style guide § 13).

    The row is parsed by the loader rather than built by hand, so what is split is the
    same tuple the build and the lint split: counted as an option instead, every
    prompt-bearing select in the game is one option short and the reader and the lint
    disagree about the one check they share.
    """
    source = write(tmp_path, "E0404.6\t[SEL]\tWhat will you read? | Insects | Kites\n")
    (entry,) = list(source)

    assert select_fields(entry, 1) == (("What will you read?",), ("Insects", "Kites"))
    assert select_fields(entry, 0) == ((), entry.options)
    # A shape with more prompt lines than fields takes what is there rather than raising:
    # the count mismatch is the lint's finding to report, not this function's.
    assert select_fields(entry, 9) == (entry.options, ())
    assert select_fields(TranslationEntry(line_id="E1.0"), 1) == ((), ())


def test_pre_encoded_words_are_a_source_like_any_other():
    """The round-trip gate is this: every line, its own words, through the same seam."""
    source = PreEncoded({"E0001.0": (1, 2, 0x8000), "E0002.0": (3, 0x8000)})
    entries = list(source)
    assert [e.line_id for e in entries] == ["E0001.0", "E0002.0"]
    assert entries[0].words == (1, 2, 0x8000)
    assert entries[0].pages == ()
