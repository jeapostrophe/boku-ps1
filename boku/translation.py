"""Where the English comes from — a seam, not a file format.

**The committed translation format is `PLAN PIPE-02` and it is Jay's to decide**
(`[MINE: contract]`). Nothing here designs one or documents one. What this module defines
is the *interface* the build reads English through, so that settling the format later is
one new `TranslationSource` and no change to the reinserter, the layout or the image
build — which is also what README § "How the translation is made" promises anyone who
wants to drop in a hand translation or another language.

A source yields `TranslationEntry` values. An entry carries either text to lay out (pages
for a message, options for a select) or words that are already encoded, which is how
`PIPE-05`'s round trip feeds every line its own original bytes back through the whole
rebuild path.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

VOICE_ONLY = "(voice only)"
"""The speaker field of a row for a clip with no text on the disc."""


class TranslationError(Exception):
    """A translation file this loader cannot read."""


@dataclass(frozen=True)
class TranslationEntry:
    """One logical line's English, addressed by the id every physical copy shares."""

    line_id: str
    speaker: str = ""
    pages: tuple[str, ...] = ()
    """A message's text, one string per page of the original. Empty for a select."""
    options: tuple[str, ...] = ()
    """A select's options, in the order the box lists them."""
    prompts: tuple[str, ...] = ()
    """A select's leading prompt lines, if its shape has any (`g_select_first`)."""
    words: tuple[int, ...] | None = None
    """Already-encoded words. When present the layout is bypassed entirely."""
    origin: str = ""
    """Where this entry was written, for a message that has to name it."""

    @property
    def is_select(self) -> bool:
        return bool(self.options) or bool(self.prompts)

    @property
    def voice_only(self) -> bool:
        """A subtitle for a clip with no text on the disc (`VO-02`): laid out against the
        clip's length rather than an original's page timers."""
        return self.speaker == VOICE_ONLY


def select_fields(entry: TranslationEntry, prompts: int) -> tuple[tuple[str, ...], ...]:
    """A `[SEL]` row's pipe fields as the box reads them: `(prompt lines, options)`.

    A select whose box opens with a question spends its first `prompts` lines on it, and
    the committed convention lists the question first -- style guide § 13,
    `translation/days/README.md` § shared.txt, and that file's own header. The question is
    not an option: it is neither counted against `g_select_lines` nor given a branch.

    It lives beside `TranslationEntry` because that is what it reads: the lint and the
    image build both split a row this way, and a second copy of the rule is a build and a
    lint disagreeing about which field is the question.
    """
    return entry.options[:prompts], entry.options[prompts:]


class TranslationSource(Protocol):
    """Anything that can list the English, keyed by line id."""

    name: str

    def __iter__(self) -> Iterator[TranslationEntry]: ...


@dataclass(frozen=True)
class PreEncoded:
    """Lines whose words are already known — no text, no layout, no encoder.

    `PIPE-05`'s round-trip gate is this source holding every line's own original words:
    the build then walks the full rebuild path for every text-bearing member and the image
    it produces has to come back byte-identical.
    """

    words: Mapping[str, Sequence[int]]
    name: str = "pre-encoded words"

    def __iter__(self) -> Iterator[TranslationEntry]:
        for line_id in sorted(self.words):
            yield TranslationEntry(line_id=line_id, words=tuple(self.words[line_id]))


# --- the loader for the translation files -------------------------------------------------


@dataclass
class SampleScenes:
    """Reads the committed translation files, in the day-file format
    (`translation/days/README.md` § Format, ruled as `PLAN PIPE-02`). Named for the three
    draft samples it was first written for; the day files, `shared.txt`, `arrays.txt` and
    `clips.txt` are read through it.

    It is deliberately the thinnest possible reader: `#` comments, and
    `line id <TAB> speaker <TAB> English`, where ` // ` is a page break in the same position
    as the original's, ` | ` separates the options of a `[SEL]` row, and a row whose speaker
    is `(voice only)` has no text on the disc and is listed only so the ids line up --
    unless it carries English, which is then a subtitle for the clip (`voice_only`,
    `PLAN VO-02`).
    """

    entries: tuple[TranslationEntry, ...]
    name: str = "translation files"
    problems: tuple[str, ...] = ()

    PAGE_BREAK = " // "
    OPTION = " | "
    SELECT = "[SEL]"
    VOICE_ONLY = VOICE_ONLY

    def __iter__(self) -> Iterator[TranslationEntry]:
        return iter(self.entries)

    @classmethod
    def from_paths(cls, paths: Sequence[Path]) -> SampleScenes:
        entries: list[TranslationEntry] = []
        problems: list[str] = []
        seen: dict[str, str] = {}
        for path in sorted(Path(p) for p in paths):
            for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                line = raw.rstrip()
                if not line or line.lstrip().startswith("#"):
                    continue
                where = f"{path.name}:{number}"
                fields = line.split("\t")
                if len(fields) < 2:
                    problems.append(f"{where}: no tab; a row is `id <TAB> speaker <TAB> English`")
                    continue
                line_id, speaker = fields[0].strip(), fields[1].strip()
                text = fields[2].strip() if len(fields) > 2 else ""
                if not text:
                    continue
                if line_id in seen:
                    problems.append(f"{where}: {line_id} was already given at {seen[line_id]}")
                    continue
                seen[line_id] = where
                if speaker == cls.SELECT:
                    entries.append(
                        TranslationEntry(
                            line_id=line_id,
                            speaker=speaker,
                            options=tuple(o.strip() for o in text.split(cls.OPTION)),
                            origin=where,
                        )
                    )
                else:
                    entries.append(
                        TranslationEntry(
                            line_id=line_id,
                            speaker=speaker,
                            pages=tuple(p.strip() for p in text.split(cls.PAGE_BREAK)),
                            origin=where,
                        )
                    )
        return cls(entries=tuple(entries), problems=tuple(problems))

    @classmethod
    def from_directory(cls, directory: Path) -> SampleScenes:
        paths = sorted(Path(directory).glob("*.txt"))
        if not paths:
            raise TranslationError(f"{directory} holds no *.txt translation files")
        source = cls.from_paths(paths)
        source.name = f"{directory} ({len(paths)} file(s))"
        return source
