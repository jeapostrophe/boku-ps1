"""`translation/movies.txt`: the movies' subtitles, keyed by movie file and STR frame.

The format is `translation/README.md` § "movies.txt"; this module is its one parser and
the one statement of its rules (`check`). The image build (`tools/vwf/build_prototype.py`,
which encodes the rows into `boku.movie_block`) and the lint (`boku lint`) both read the
file through it, so a row the lint passes is a row the build draws exactly as measured.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from boku import REPO_ROOT
from boku.layout import BoxSpec, Encoder, measure, unencodable, wrap
from boku.movie_block import LINE_WIDTH, POSITIONS, Cue
from boku.movies import MOVIES_TSV

CUE_FILE = REPO_ROOT / "translation" / "movies.txt"
LINE_BREAK = "|"
FIELDS = 4
"""A row's fields; a fifth, the options, is optional: space-separated, at most one position
(`POSITIONS`, default `DEFAULT_POSITION`) and any of `FLAGS`."""
CAPTION = "caption"
FLAGS = frozenset({CAPTION})
"""`caption`: the cue translates writing in the picture, not speech (FMV-08), so
`boku.movie_timing` holds it to no transcript segment."""
DEFAULT_POSITION = "bottom"
MOVIE_BAND = BoxSpec(
    width=LINE_WIDTH, lines=min(map(len, POSITIONS.values())), name="the movie band"
)
"""What one cue can hold wherever it sits: `boku.movie_block`'s line width, and the fewest
lines any position has."""


@dataclass(frozen=True)
class CueRow:
    movie: str
    start: int
    end: int
    text: str
    line: int
    """The row's line number in its file, for a finding to point at."""
    position: str = DEFAULT_POSITION
    """Where the cue sits: a key of `boku.movie_block.POSITIONS`."""
    caption: bool = False
    """Whether the cue translates writing in the picture (`CAPTION`) rather than speech."""

    @property
    def key(self) -> str:
        """How a finding names the cue: `M27@120`."""
        return f"{self.movie}@{self.start}"


@dataclass(frozen=True)
class Problem:
    line: int
    key: str
    check: str
    message: str


def parse(text: str) -> tuple[list[CueRow], list[Problem]]:
    """The rows of a cue file and what is malformed about its lines, in file order.
    Blank lines and `#` lines are notes."""
    rows: list[CueRow] = []
    problems: list[Problem] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) not in (FIELDS, FIELDS + 1):
            problems.append(
                Problem(
                    number,
                    "-",
                    "cue-malformed",
                    f"{len(fields)} tab-separated fields; a row is "
                    f"`movie <TAB> first frame <TAB> last frame <TAB> English [<TAB> options]`",
                )
            )
            continue
        movie, start, end, english, *rest = (field.strip() for field in fields)
        options = rest[0].split() if rest else []
        positions = [word for word in options if word in POSITIONS]
        unknown = [word for word in options if word not in POSITIONS and word not in FLAGS]
        if unknown or len(positions) > 1:
            problems.append(
                Problem(
                    number,
                    movie,
                    "cue-malformed",
                    f"options {' '.join(options)!r}: at most one position of "
                    f"{', '.join(sorted(POSITIONS))}, and flags of {', '.join(sorted(FLAGS))}",
                )
            )
            continue
        position = positions[0] if positions else DEFAULT_POSITION
        try:
            first, last = int(start), int(end)
        except ValueError:
            problems.append(
                Problem(number, movie, "cue-malformed", f"frames {start!r}, {end!r} are not whole")
            )
            continue
        rows.append(CueRow(movie, first, last, english, number, position, CAPTION in options))
    return rows, problems


def read(path: Path = CUE_FILE) -> tuple[list[CueRow], list[Problem]]:
    return parse(Path(path).read_text(encoding="utf-8"))


def movie_lengths(tsv: str) -> dict[str, int]:
    """Each movie file -> the last STR frame any id playing it shows: the largest
    `stop_frame` among its rows of `research/data/movies.tsv`."""
    body = [line for line in tsv.splitlines() if line and not line.startswith("#")]
    lengths: dict[str, int] = {}
    for row in csv.DictReader(body, delimiter="\t"):
        lengths[row["file"]] = max(lengths.get(row["file"], 0), int(row["stop_frame"]))
    return lengths


def read_movie_lengths(path: Path = MOVIES_TSV) -> dict[str, int]:
    return movie_lengths(Path(path).read_text(encoding="utf-8"))


def cue_lines(text: str, encoder: Encoder) -> tuple[str, ...]:
    """The lines a cue's English is drawn as: split at ` | ` if the translator broke it,
    else wrapped greedily at the band's width in `encoder`'s pixels."""
    if LINE_BREAK in text:
        return tuple(part.strip() for part in text.split(LINE_BREAK))
    return tuple(wrap(encoder, text, MOVIE_BAND))


def check(
    rows: Sequence[CueRow], lengths: Mapping[str, int], encoder: Encoder | None
) -> list[Problem]:
    """Every rule a cue must pass for the build to draw it as written. With no `encoder`
    the pixel rules -- `cue-width`, `cue-lines`, `cue-unencodable` -- are not measured."""
    problems: list[Problem] = []

    def say(row: CueRow, check: str, message: str) -> None:
        problems.append(Problem(row.line, row.key, check, message))

    for row in rows:
        length = lengths.get(row.movie)
        if length is None:
            say(row, "cue-movie", f"{row.movie!r} is not a file of research/data/movies.tsv")
        elif not 1 <= row.start <= row.end <= length:
            say(
                row,
                "cue-frames",
                f"frames {row.start}..{row.end} are not 1 <= first <= last <= {length}, "
                f"the last frame {row.movie} shows",
            )
        if not row.text or any(not line.strip() for line in row.text.split(LINE_BREAK)):
            say(row, "cue-empty", "a cue with no English, or an empty line in one")
            continue
        if encoder is None:
            continue
        missing = unencodable(encoder, row.text.replace(LINE_BREAK, ""))
        if missing:
            say(row, "cue-unencodable", f"the font has no glyph for {''.join(missing)!r}")
        lines = cue_lines(row.text, encoder)
        if len(lines) > MOVIE_BAND.lines:
            say(row, "cue-lines", f"{len(lines)} lines; the movie band holds {MOVIE_BAND.lines}")
        for line in lines:
            width = measure(encoder, line)
            if width > MOVIE_BAND.width:
                say(
                    row,
                    "cue-width",
                    f"{line!r} is {width} px; the movie band holds {MOVIE_BAND.width} "
                    f"({width - MOVIE_BAND.width} over)",
                )
    by_movie: dict[str, list[CueRow]] = {}
    for row in rows:
        by_movie.setdefault(row.movie, []).append(row)
    for movie_rows in by_movie.values():
        ordered = sorted(movie_rows, key=lambda row: (row.start, row.end))
        for earlier, later in pairwise(ordered):
            if later.start <= earlier.end:
                say(
                    later,
                    "cue-overlap",
                    f"frames {later.start}..{later.end} overlap {earlier.key}'s "
                    f"{earlier.start}..{earlier.end} (line {earlier.line}); one cue at a time",
                )
    return sorted(problems, key=lambda problem: (problem.line, problem.check))


def cues_by_movie(rows: Iterable[CueRow], encoder: Encoder) -> dict[str, list[Cue]]:
    """The rows as `boku.movie_block.Cue`s, grouped by movie file in frame order."""
    out: dict[str, list[Cue]] = {}
    for row in sorted(rows, key=lambda row: (row.movie, row.start)):
        cue = Cue(row.start, row.end, cue_lines(row.text, encoder), POSITIONS[row.position])
        out.setdefault(row.movie, []).append(cue)
    return out


__all__ = [
    "CAPTION",
    "CUE_FILE",
    "FLAGS",
    "MOVIE_BAND",
    "CueRow",
    "Problem",
    "check",
    "cue_lines",
    "cues_by_movie",
    "movie_lengths",
    "parse",
    "read",
    "read_movie_lengths",
]
