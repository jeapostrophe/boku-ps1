"""The provisional reader for the draft samples, and the seam it sits behind.

`PIPE-02` — the committed translation format — is Jay's decision and is not made here, so
what is tested is only that the loader reads what `translation/days/` *already
contains*, and that the seam (`TranslationSource`) is what the build depends on rather
than any particular file format. The day files are tracked, so the fixtures here are the real
ones: the loader is checked against the translation it exists to read.
"""

from __future__ import annotations

from boku import REPO_ROOT
from boku.translation import PreEncoded, SampleScenes

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


def test_pre_encoded_words_are_a_source_like_any_other():
    """The round-trip gate is this: every line, its own words, through the same seam."""
    source = PreEncoded({"E0001.0": (1, 2, 0x8000), "E0002.0": (3, 0x8000)})
    entries = list(source)
    assert [e.line_id for e in entries] == ["E0001.0", "E0002.0"]
    assert entries[0].words == (1, 2, 0x8000)
    assert entries[0].pages == ()
