"""`translation/clips.txt`: subtitles for the clips native code plays (`g_xa_clips`, `XCH.nn`).

The format is `translation/README.md` § "clips.txt" -- a day file's rows keyed `XCH.nn`, read
by the day files' own loader (`boku.translation.SampleScenes`), with one field of their own:
the times a row gives its pages. This module is the one place that turns those rows into
what the executable draws: dialogue words, paged against the clip's length exactly as a
`(voice only)` event row is (`boku.layout.lay_out_subtitle`) or at the row's own times, for
`boku.movie_block`'s clip section -- and into when each page is on the screen (`Page`), read
back from those same words. The image build (`tools/vwf/build_prototype.py`), the lint
(`boku lint`) and the reader all come through `lay_out_lines`, so a row the lint passes is
one the build writes as measured and the reader shows as built.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from fractions import Fraction
from itertools import accumulate, pairwise
from pathlib import Path

from boku import REPO_ROOT, epilogue
from boku.glyphs import END_WORD, PAGE_WORD
from boku.layout import DIALOGUE_BAND, BoxSpec, Encoder, LaidOut, lay_out_subtitle
from boku.movie_timing import MAX_CPS, characters
from boku.translation import SampleScenes, TranslationEntry
from boku.voice import (
    SAMPLES_PER_SECTOR,
    SEEK_TICKS,
    VSYNC_HZ,
    VSYNCS_PER_TICK,
    XA_RATE,
    VoiceNode,
    sector_ticks,
    timed_waits,
)

CLIP_FILE = REPO_ROOT / "translation" / "clips.txt"
CLIP_ID = re.compile(r"XCH\.(\d{2})")
OUTSIDE_SUMO = frozenset({34, *range(41, 46)})
"""The clips known to play outside bug sumo: the bedtime clip in movie mode and the five
epilogues in `ENDOTI` (research/event-scripts.md § Native clips). Every other clip is laid
out for bug sumo's pen, which is the safe side: a clip laid out narrower than its mode needs
is only shorter lines."""
SUMO_PEN_INDENT = 42
"""Pixels bug sumo's subtitle pen starts right of the dialogue pen (`asm/voice.asm`,
`voice_sub_show`): clear of Boku's 44 x 44 portrait at (18, 161), which a bout draws in
front of the band's first line (research/sumo.md § Subtitles)."""
TIMES_FIELD = 3
"""The tab field after the English: the row's page times."""
MIN_SECONDS = Fraction(3, 2)
"""What a page of several stays up for at least: the movie cues' 1.5 s (`boku.movie_timing`
counts it in whole movie frames); `MAX_CPS`, the fastest a page may ask to be read, is
theirs too."""


def clip_box(index: int, box: BoxSpec = DIALOGUE_BAND) -> BoxSpec:
    """The box clip `index` is laid out in: `box`, or in bug sumo `box` less the indent."""
    if index in OUTSIDE_SUMO:
        return box
    return replace(
        box,
        width=box.width - SUMO_PEN_INDENT,
        guarded_width=max(box.guarded_width - SUMO_PEN_INDENT, 0),
        name=f"{box.name} in bug sumo",
    )


@dataclass(frozen=True)
class ClipProblem:
    line_id: str
    origin: str
    message: str


@dataclass(frozen=True)
class ClipEntry(TranslationEntry):
    """A row of `clips.txt`: a day file's row, and the times it gives its pages."""

    ends: tuple[Fraction, ...] = ()
    """The second of the clip's audio at which each page gives way: to the next page, or
    the last to nothing. Empty: the pages share the clip by length and the last stays up
    until the clip ends."""


@dataclass(frozen=True)
class Page:
    """One page of a clip's subtitle as it is on the screen."""

    text: str
    """The page as the row gives it."""
    lines: tuple[str, ...]
    """As the band breaks it."""
    start: int
    end: int
    """Vsyncs after the subtitle opens: up from `start`, gone at `end`."""

    @property
    def seconds(self) -> Fraction:
        return (self.end - self.start) / VSYNC_HZ

    def meets_card(self, picture: epilogue.Picture | None) -> bool:
        """Whether the page is still up when `picture`'s still gives way to the production
        card -- on that very vsync too: the band outlives its last page by a frame."""
        return picture is not None and self.end >= picture.card


@dataclass(frozen=True)
class ClipLine:
    """One row laid out: the words the block carries and when each page is up."""

    index: int
    entry: ClipEntry
    laid: LaidOut
    pages: tuple[Page, ...]
    until: int
    """Vsyncs after the subtitle opens at which it comes down whatever its pages say: the
    clip has ended, or the game has left the epilogue."""
    picture: epilogue.Picture | None = None
    """What `ENDOTI` shows meanwhile, for an epilogue."""
    problems: tuple[str, ...] = ()
    """What the band cannot draw, and `timing_problems`. The build takes no such row."""

    @property
    def ok(self) -> bool:
        return not self.problems


def read(path: Path = CLIP_FILE) -> tuple[list[ClipEntry], list[str]]:
    """The rows that carry English, and what the loader could not read. A missing file is
    no rows: a checkout that has not started on the clips builds as before."""
    path = Path(path)
    if not path.is_file():
        return [], []
    source = SampleScenes.from_paths([path])
    problems = list(source.problems)
    times: dict[str, tuple[Fraction, ...]] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        columns = raw.rstrip().split("\t")
        if raw.lstrip().startswith("#") or len(columns) <= TIMES_FIELD:
            continue
        try:
            times[columns[0].strip()] = tuple(Fraction(t) for t in columns[TIMES_FIELD].split())
        except ValueError:
            problems.append(
                f"{path.name}:{number}: the times {columns[TIMES_FIELD]!r} are not seconds "
                f"separated by spaces"
            )
    entries = [
        ClipEntry(
            **{f.name: getattr(entry, f.name) for f in fields(TranslationEntry)},
            ends=times.get(entry.line_id, ()),
        )
        for entry in source
    ]
    return entries, problems


def lead(index: int, pictures: Mapping[int, epilogue.Picture]) -> int:
    """Vsyncs from a clip's subtitle opening to its audio's first sample: an epilogue's
    measured one, else the seek every other clip waits out (`boku.voice.SEEK_TICKS`)."""
    return epilogue.LEAD if index in pictures else SEEK_TICKS * VSYNCS_PER_TICK


def page_times(words: Sequence[int], until: int) -> list[tuple[int, int]]:
    """When each page of `words` is up, in vsyncs after the subtitle opens, from the page
    timers in the words themselves: a page turns when its timer has counted down at two
    vsyncs a tick, a last page with a timer comes down with it (`asm/voice.asm`,
    `voice_sub_service`), one without stays to `until`, and nothing is up past `until`."""
    waits = [words[at + 1] for at, word in enumerate(words[:-1]) if word == PAGE_WORD]
    turns = [VSYNCS_PER_TICK * ticks for ticks in accumulate(waits)]
    timed_last = len(words) >= 3 and words[-3] == PAGE_WORD and words[-1] == END_WORD
    if not timed_last:
        turns.append(until)
    return [(min(start, until), min(end, until)) for start, end in pairwise([0, *turns])]


def timing_problems(
    pages: Sequence[Page], timed: bool, picture: epilogue.Picture | None
) -> list[str]:
    """What a viewer cannot read or should not see: a page of several up for less than
    `MIN_SECONDS` or asking more than `MAX_CPS`, and an epilogue's page that
    `Page.meets_card`. A row of one page without times (`timed`) is up for as long as its
    clip plays, which no row can change, and is not judged."""
    found = []
    judged = len(pages) > 1 or timed
    for number, page in enumerate(pages, start=1):
        seconds = page.seconds
        if judged and seconds < MIN_SECONDS:
            found.append(
                f"page {number} is up for {float(seconds):.2f} s; at least "
                f"{float(MIN_SECONDS):.1f} s"
            )
        elif judged and characters(page.text) > MAX_CPS * seconds:
            found.append(
                f"page {number} is up for {float(seconds):.2f} s: "
                f"{float(characters(page.text) / seconds):.1f} characters a second; at most "
                f"{MAX_CPS}"
            )
        if page.meets_card(picture):
            found.append(
                f"page {number} is up from {float(page.start / VSYNC_HZ):.1f} s to "
                f"{float(page.end / VSYNC_HZ):.2f} s, and the still gives way to the "
                f"production card at {float(picture.card / VSYNC_HZ):.2f} s; give the row "
                f"times that end before it (translation/README.md § clips.txt)"
            )
    return found


def lay_out_lines(
    entries: Sequence[ClipEntry],
    clips: Sequence[VoiceNode],
    encoder: Encoder,
    pictures: Mapping[int, epilogue.Picture],
    box: BoxSpec = DIALOGUE_BAND,
) -> tuple[list[ClipLine], list[ClipProblem]]:
    """Each row laid out, and every problem: an id that is not `XCH.nn` for a clip of `clips`
    (`boku.voice.xch_nodes`), a menu row, times that do not fit the row's pages, what the
    band cannot draw, and `timing_problems`. A row whose pages can be placed at all is in the
    lines with its problems on it, so the reader can show what is wrong with it.
    `pictures` is `boku.epilogue.pictures` of the disc the clips play on: not optional, or a
    caller that left it out would lay the epilogues out against no picture and pass them."""
    lines: list[ClipLine] = []
    problems: list[ClipProblem] = []
    for entry in entries:
        line, found = _lay_out(entry, clips, encoder, pictures, box)
        problems += [ClipProblem(entry.line_id, entry.origin, message) for message in found]
        if line is not None:
            lines.append(line)
    return lines, problems


def _lay_out(
    entry: ClipEntry,
    clips: Sequence[VoiceNode],
    encoder: Encoder,
    pictures: Mapping[int, epilogue.Picture],
    box: BoxSpec,
) -> tuple[ClipLine | None, list[str]]:
    match = CLIP_ID.fullmatch(entry.line_id)
    if not match or int(match[1]) >= len(clips):
        return None, [
            f"not a clip: ids are XCH.00-XCH.{len(clips) - 1:02d}, the records of "
            f"BOKU_XA.XCH (research/data/voice-only.tsv)"
        ]
    if entry.is_select:
        return None, ["a clip is not a menu"]
    index = int(match[1])
    ahead = lead(index, pictures)
    if entry.ends and len(entry.ends) != len(entry.pages):
        return None, [
            f"{len(entry.ends)} time(s) for {len(entry.pages)} page(s): a row gives every "
            f"page the second it gives way, or none"
        ]
    waits = timed_waits(entry.ends, ahead)
    if any(wait < 1 for wait in waits):
        return None, [f"its times {' '.join(str(float(t)) for t in entry.ends)} do not rise from 0"]
    sectors = clips[index].sectors
    laid = lay_out_subtitle(
        entry.line_id, entry.pages, sector_ticks(sectors), encoder, clip_box(index, box), waits
    )
    picture = pictures.get(index)
    until = ahead + round(Fraction(sectors * SAMPLES_PER_SECTOR, XA_RATE) * VSYNC_HZ)
    if picture is not None:
        until = min(until, picture.end)
    pages = tuple(
        Page(text, lines, start, end)
        for text, lines, (start, end) in zip(
            entry.pages, laid.pages, page_times(laid.words, until), strict=True
        )
    )
    found = [*laid.problems, *timing_problems(pages, bool(entry.ends), picture)]
    return ClipLine(index, entry, laid, pages, until, picture, tuple(found)), found


def lay_out_clips(
    entries: Sequence[ClipEntry],
    clips: Sequence[VoiceNode],
    encoder: Encoder,
    pictures: Mapping[int, epilogue.Picture],
    box: BoxSpec = DIALOGUE_BAND,
) -> tuple[dict[int, tuple[int, ...]], list[ClipProblem]]:
    """`lay_out_lines` as the build takes it: the words of each row without a problem, by
    clip index."""
    lines, problems = lay_out_lines(entries, clips, encoder, pictures, box)
    return {line.index: line.laid.words for line in lines if line.ok}, problems
