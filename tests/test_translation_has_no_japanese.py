"""The line-keyed translation files carry no Japanese, notes included (translation/days/README.md
§ The files): they are public, and a quoted source line in a note is the original's text."""

import re
from pathlib import Path

TRANSLATION = Path(__file__).resolve().parent.parent / "translation"
KANA_OR_KANJI = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")


def line_keyed_files() -> list[Path]:
    days = sorted((TRANSLATION / "days").glob("*.txt"))
    return [*days, TRANSLATION / "clips.txt", TRANSLATION / "movies.txt"]


def test_no_line_keyed_translation_file_holds_japanese():
    files = line_keyed_files()
    assert all(f.is_file() for f in files) and len(files) > 30, "the file set is out of date"
    found = [
        f"{f.relative_to(TRANSLATION)}:{n}"
        for f in files
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
        if KANA_OR_KANJI.search(line)
    ]
    assert not found, f"Japanese in {len(found)} line(s): {found[:10]}"
