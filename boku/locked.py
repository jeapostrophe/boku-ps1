"""Jay's own words: `translation/locked.tsv`, and whether the translation still holds them.

A lock is a line id and words Jay wrote, dictated, heard or picked for that line
(`translation/README.md` § locked.tsv): either the line's whole English (`line`) or words that
must appear in it (`phrase`). Who reads the file and what each holds it to is § locked.tsv.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from boku import REPO_ROOT

LOCK_FILE = REPO_ROOT / "translation" / "locked.tsv"
HEADER = ("id", "match", "words", "source")
LINE, PHRASE = "line", "phrase"
JAPANESE = re.compile("[\\u3000-\\u30ff\\u3400-\\u9fff\\uff00-\\uffef]")
"""A character of Japanese text: none may stand in a tracked translation file."""


class LockError(Exception):
    """A `locked.tsv` row, or a translation file, this reader cannot hold to its locks."""


@dataclass(frozen=True)
class Lock:
    line_id: str
    match: str
    """`LINE`: the English is exactly `words`. `PHRASE`: `words` appear in it, not as part of
    a longer word -- "Take" is not held by "Takeout"."""
    words: str
    source: str
    where: str
    """`locked.tsv:N`, for a failure to point at."""

    @property
    def says(self) -> str:
        """How a packet part and a refusal say what the lock asks of the line."""
        return "the whole line is" if self.match == LINE else "the line holds"

    def held_by(self, english: str) -> bool:
        if self.match == LINE:
            return english == self.words
        before = r"(?<!\w)" if re.match(r"\w", self.words) else ""
        after = r"(?!\w)" if re.search(r"\w$", self.words) else ""
        return re.search(before + re.escape(self.words) + after, english) is not None


def parse(text: str, name: str = LOCK_FILE.name) -> list[Lock]:
    """Every row after the header; `#` lines and blank lines are notes. Refused: a row
    without four fields or with an unknown match, a repeated id and words, and Japanese
    anywhere (the file is tracked, and English only, as the translation files are)."""
    locks: list[Lock] = []
    seen: set[tuple[str, str]] = set()
    header_seen = False
    for number, line in enumerate(text.splitlines(), start=1):
        where = f"{name}:{number}"
        if JAPANESE.search(line):
            raise LockError(f"{where}: holds Japanese; the file is English only")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        fields = tuple(cell.strip() for cell in cells)
        if not header_seen:
            if fields != HEADER:
                raise LockError(f"{where}: the first row is the header {' / '.join(HEADER)}")
            header_seen = True
            continue
        if len(fields) != len(HEADER) or not all(fields):
            raise LockError(f"{where}: a row is `id <TAB> match <TAB> words <TAB> source`")
        line_id, match, words, source = fields
        if match not in (LINE, PHRASE):
            raise LockError(f"{where}: match is `{LINE}` or `{PHRASE}`, not {match!r}")
        if (line_id, words) in seen:
            raise LockError(f"{where}: {line_id} {words!r} is given twice")
        seen.add((line_id, words))
        if match == PHRASE:
            words = cells[2]  # a phrase keeps its edge spaces: the tanka's " / "
        locks.append(Lock(line_id, match, words, source, where))
    return locks


def read(path: Path = LOCK_FILE) -> list[Lock]:
    path = Path(path)
    return parse(path.read_text(encoding="utf-8"), path.name)


def locks_by_id(locks: Iterable[Lock]) -> dict[str, tuple[Lock, ...]]:
    """Each locked id -> its locks, in the file's order."""
    out: dict[str, list[Lock]] = {}
    for lock in locks:
        out.setdefault(lock.line_id, []).append(lock)
    return {line_id: tuple(found) for line_id, found in out.items()}


def missing(line_id: str, english: str, locked: Mapping[str, Sequence[Lock]]) -> list[Lock]:
    """The locks on `line_id` that `english` does not hold."""
    return [lock for lock in locked.get(line_id, ()) if not lock.held_by(english)]


def committed_english(root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """Every id's English as its tracked file writes it: the day files and `clips.txt`
    (a row's third field), the texture strings, and each movie (`M27`) as its cues joined by
    newlines, so a phrase is held by one cue and never across two.
    A file its reader cannot parse is refused, not read as missing lines."""
    from boku.lint import load_rows, translation_paths
    from boku.movie_cues import read as read_cues
    from boku.texture_text import read_entries

    translation = root / "translation"
    english: dict[str, list[str]] = {}
    rows, findings = load_rows(translation_paths([translation / "days", translation / "clips.txt"]))
    cues, problems = read_cues(translation / "movies.txt")
    unread = [f"{f.file}:{f.number} {f.message}" for f in findings]
    unread += [f"movies.txt:{p.line} {p.message}" for p in problems]
    if unread:
        raise LockError("the translation files do not parse: " + "; ".join(unread))
    for row in rows:
        english.setdefault(row.line_id, []).append(row.text)
    for entry in read_entries(translation / "textures").values():
        english.setdefault(entry.id, []).append(entry.text)
    by_movie: dict[str, list[str]] = {}
    for cue in cues:
        by_movie.setdefault(cue.movie, []).append(cue.text)
    for movie, texts in by_movie.items():
        english[movie] = ["\n".join(texts)]
    return english


def broken(locks: Iterable[Lock], english: Mapping[str, Sequence[str]]) -> list[str]:
    """Each lock the translation does not hold, said so its reader knows what to do."""
    out: list[str] = []
    for lock in locks:
        texts = english.get(lock.line_id)
        if not texts:
            out.append(f"{lock.where}: {lock.line_id} has no English in any translation file")
            continue
        if not all(lock.held_by(text) for text in texts):
            now = " / ".join(repr(text) for text in texts)
            out.append(
                f"{lock.where}: {lock.line_id} no longer says {lock.words!r} ({lock.match}; "
                f"{lock.source}); it says {now}. These are Jay's words: put them back, or ask "
                f"Jay and change the lock with his ruling"
            )
    return out
