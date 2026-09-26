"""`translation/locked.tsv` -- Jay's own words, held against the committed translation.

The fixture is the lock file itself and the translation files as committed: every row is
checked, so a lock added is a lock enforced, and no list of ids is retyped here.
"""

from __future__ import annotations

import pytest

from boku.locked import (
    HEADER,
    LockError,
    broken,
    committed_english,
    locks_by_id,
    missing,
    parse,
    read,
)

HEAD = "\t".join(HEADER) + "\n"


def one(row: str):
    (lock,) = parse(HEAD + row + "\n")
    return lock


def test_the_translation_holds_every_one_of_jay_s_words():
    assert broken(read(), committed_english()) == []


def test_every_lock_fails_when_its_line_loses_the_words():
    """No row is vacuous: each is broken by its own line losing its words, and only the
    locks on that line are -- a lock that no change can break protects nothing."""
    locks = read()
    english = committed_english()
    for lock in locks:
        copies = len(english.get(lock.line_id) or [""])
        found = broken(locks, {**english, lock.line_id: ["something else"] * copies})
        named = {message.split(": ", 1)[0] for message in found}
        assert lock.where in named, f"{lock.where} {lock.line_id} holds whatever its line says"
        assert named == {other.where for other in locks if other.line_id == lock.line_id}


def test_a_changed_line_is_named_with_the_words_it_lost_and_whose_they_are():
    lock = one("E0175.0\tphrase\tI'm your Uncle Yusaku.\tJay, 2026-09-21")
    (message,) = broken([lock], {"E0175.0": ["The name of this house is Sorano. // Rest."]})
    assert "E0175.0" in message and "I'm your Uncle Yusaku." in message
    assert "Jay, 2026-09-21" in message and "The name of this house" in message


def test_a_phrase_is_not_held_inside_a_longer_word_and_a_line_lock_is_the_whole_line():
    """The locks on one-word buttons (`Take`, `W`, `fish`): a sweep that writes "Takeout",
    "Wins" or "fishing" keeps the letters and loses the word Jay chose."""
    take = one("btn@MITIM.take_out\tphrase\tTake\tJay")
    assert take.held_by("Take") and take.held_by("Take it // now")
    assert not take.held_by("Takeout")
    whole = one("btn@MITIM.take_out\tline\tTake\tJay")
    assert whole.held_by("Take")
    assert not whole.held_by("Take // Out")
    slashes = one("E2515.0\tphrase\t / \tJay")
    assert slashes.words == " / "
    assert slashes.held_by("a / b") and not slashes.held_by("a b")


def test_an_id_with_no_english_is_a_broken_lock():
    (message,) = broken([one("E9999.0\tphrase\tWords\tJay")], {})
    assert "no English" in message


def test_a_line_translated_twice_holds_the_words_only_if_both_copies_do():
    lock = one("E0001.0\tphrase\tWords\tJay")
    assert broken([lock], {"E0001.0": ["Words.", "Words, too."]}) == []
    assert broken([lock], {"E0001.0": ["Words.", "Other."]})


def test_a_movie_is_its_cues_and_a_phrase_is_held_by_one_cue_not_across_two():
    movie = committed_english()["M27"]
    assert len(movie) == 1 and "\n" in movie[0], "M27 is not its cues joined"
    joined = {"M27": ["as if specks\nof light"]}
    assert broken([one("M27\tphrase\tspecks of light\tJay")], joined)
    assert broken([one("M27\tphrase\tof light\tJay")], joined) == []


def test_missing_names_the_locks_an_answer_drops():
    locked = locks_by_id(parse(HEAD + "E1.0\tphrase\tone\tJay\nE1.0\tphrase\ttwo\tJay\n"))
    assert [lock.words for lock in locked["E1.0"]] == ["one", "two"]
    assert [lock.words for lock in missing("E1.0", "one and three", locked)] == ["two"]
    assert missing("E2.0", "anything", locked) == []


def test_a_translation_file_that_does_not_parse_is_refused_not_read_as_lost_words(tmp_path):
    days = tmp_path / "translation" / "days"
    days.mkdir(parents=True)
    (days / "day01.txt").write_text("E0175.0 Uncle no tabs\n", encoding="utf-8")
    (tmp_path / "translation" / "textures").mkdir()
    (tmp_path / "translation" / "movies.txt").write_text("", encoding="utf-8")
    with pytest.raises(LockError, match="do not parse"):
        committed_english(tmp_path)


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("E1.0\tphrase\tone\tJay\n", "header"),
        (HEAD + "E1.0\tphrase\tone\n", "a row is"),
        (HEAD + "E1.0\tphrase\t\tJay\n", "a row is"),
        (HEAD + "E1.0\texact\tone\tJay\n", "match is"),
        (HEAD + "E1.0\tphrase\tone\tJay\nE1.0\tline\tone\tJay again\n", "twice"),
        (HEAD + "# 一 a note in Japanese\n", "Japanese"),
    ],
)
def test_a_malformed_lock_file_is_refused(text, complaint):
    with pytest.raises(LockError, match=complaint):
        parse(text)


def test_an_indented_note_is_a_note():
    assert parse("  # a note\n" + HEAD + "    # another\n") == []
