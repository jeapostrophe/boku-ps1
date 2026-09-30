"""`PLAN TRN-14` -- the reader: every translated thing in one linear walkthrough.

    ./make.sh reader                 # writes work/reader/index.html

One page to click through the whole translation in order, for reading it for issues: the 31
days' events in play order (each with its setting, every line with its speaker, the
Japanese and the English, voice-only lines with their subtitle), then the day-independent
events of `shared.txt`, the menus, books and screens of `arrays.txt`, the clips native code
plays (`clips.txt`; each epilogue with every page drawn over the picture it meets and a
timeline of pages against pictures, `epilogue_previews`), the movie subtitles (`movies.txt`,
with their timing, the transcript they translate and stills from `./make.sh movie-review`
where there are any), and every
texture the build typesets (`translation/textures/`), the rebuilt image beside the original
-- the screens and signs, the picture diary and the two encyclopedias. Each item's id is
one click (or `c`) to copy, for a comment. The lint's findings (`boku.lint`, every check
`./make.sh lint-translation` makes) sit on the items they are about -- one about no item
(a row the loader cannot read) heads the page -- and a texture group the build would
refuse carries the refusal. The translators' notes are on their lines (`notes_by_id`).
Each section shows its unit's `TRN-04` state from `translation/status.tsv` (`read_status`).

It is **read-only** over the translation: edits go to the files; rebuild and reload.

**The page is the Japanese script and the game's pixels, so it is written under the
gitignored `work/` and never anywhere the repo would track** (CLAUDE.md § "This repo is
public"). It is one static HTML file plus the texture images beside it; the walkthrough is
embedded as JSON and drawn a section at a time, so it opens from `file://` with no server.

It never goes stale unseen (Jay, 2026-09-25): `./make.sh build-days` ends by rewriting it,
its header, on every section, names the commit and the days build it was made from
(`provenance`) and says when that build lacks what the page shows (`stale_build`).
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import html
import json
import os
import re
import struct
import subprocess
import sys
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from boku import REPO_ROOT, clip_preview, clip_subs, epilogue, exchange_notebook, movie_cues
from boku.archive import ARCHIVE_NAME, DEFAULT_DISC_DIR, Archive, ArchiveError
from boku.build import BuildRefused, load_edit_set
from boku.clip_subs import CLIP_FILE
from boku.extract import SCRIPT_DIR_NAME
from boku.layout import UNLABELLED_SPEAKERS, LayoutError
from boku.lint import (
    DEFAULT_CELLS,
    Finding,
    Options,
    Row,
    lint_everything,
    load_rows,
    parse_file,
    renderer_for,
    translation_paths,
)
from boku.movie_timing import DEFAULT_SEGMENTS as VOICE_DIR
from boku.movies import FPS
from boku.packets import (
    DAYS_DIR,
    PacketBuilder,
    PacketRefused,
    Policy,
    check_destination,
    has_text,
    scene_line_ids,
    surfaces_of,
)
from boku.png import SIGNATURE as PNG_SIGNATURE
from boku.png import write_rgba
from boku.reinsert import ByteEdit
from boku.script_store import (
    Store,
    StoreMissing,
    load_store,
    ordered_scenes,
    scene_dated_day,
    select_shape,
)
from boku.texture_kite import VIEWS as KITE_VIEWS
from boku.texture_paint import Canvas, View
from boku.texture_sumo import VIEWS as SUMO_VIEWS
from boku.texture_text import FAMILIES, TEXTURE_TEXT_DIR, TextureTextError, patched_archive
from boku.texture_text import read_entries as read_texture_entries
from boku.textures import Texture, TextureError, inventory, to_png
from boku.tim import TimError, parse_exact
from boku.translation import SampleScenes
from boku.typeset import FONT_SHEET_ID, GameFace, TypesetError
from boku.voice import VSYNC_HZ, xch_nodes

DEFAULT_OUT_DIR = REPO_ROOT / "work" / "reader"
DEFAULT_BUILD_DIR = REPO_ROOT / "build" / "days"
BUILD_ID_NAME = "BUILD-ID.txt"
"""What `./make.sh build-days` writes beside the image: `<UTC time>-<git describe>`."""
STATUS_FILE = REPO_ROOT / "translation" / "status.tsv"
MOVIE_REVIEW_DIR = REPO_ROOT / "work" / "movie-review"
"""`./make.sh movie-review`'s stills: `<movie>/shots/<first frame>-{first,middle,last}.png`."""

STATES = ("undrafted", "drafted", "reviewed", "checked", "rendered", "finalized")
"""`PLAN TRN-04`'s ladder, in order."""

SHARED_UNIT = "shared"
ARRAYS_UNIT = "arrays"
CLIPS_UNIT = "clips"
MOVIES_UNIT = "movies"
TEXTURE_UNITS = {
    "ui.txt": "screens",
    "signs.txt": "screens",
    "buttons.txt": "screens",
    "records.txt": "screens",
    "sumo.txt": "sumo",
    "kite.txt": "kite",
    "diary.txt": "diary",
    "books.txt": "books",
}
"""The unit each texture file's strings are walked and given a state under; a file not
named here is a unit of its own, by its stem (and `read_status` must then give it a row)."""

VIEWS = {**SUMO_VIEWS, **KITE_VIEWS}
"""The groups shown as the game draws them, not as whole atlases (`view_pictures`)."""

UNIT_NAMES = {
    SHARED_UNIT: ("Any day", "Any day"),
    ARRAYS_UNIT: ("Menus, books and screens", "Menus and screens"),
    CLIPS_UNIT: ("Voice clips from code", "Clips"),
    MOVIES_UNIT: ("Movie subtitles", "Movies"),
    "screens": ("Screens and signs", "Screens and signs"),
    "sumo": ("Bug sumo's bout", "Bug sumo"),
    "kite": ("Kite flying's HUD", "Kite flying"),
    "diary": ("The picture diary", "Diary"),
    "books": ("The encyclopedias", "Encyclopedias"),
}
"""Each unit's section title and its name in the contents."""


def unit_section(unit: str, group: str, blocks: Sequence[Block]) -> Section:
    title, short = UNIT_NAMES.get(unit, (unit, unit))
    return Section(unit, title, group, tuple(blocks), short=short)


LINE, SELECT, VOICE, CLIP, CUE, TEXTURE, ROW = (
    "line", "select", "voice", "clip", "cue", "texture", "row",
)  # fmt: skip
"""What an item is. `ROW` is a translated row no screen shows (an unknown id)."""

_DAY_FILE = re.compile(r"day(\d+)$")


class ReaderRefused(Exception):
    """The reader will not run: a missing import, a bad status file, a tracked destination."""


# --- TRN-04's table -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Status:
    """One unit's row of `translation/status.tsv`."""

    unit: str
    state: str
    date: str
    note: str = ""


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


STATUS_COLUMNS = ("unit", "state", "date", "note")


def read_status(path: Path = STATUS_FILE) -> dict[str, Status]:
    """`unit <TAB> state <TAB> date <TAB> note`, a header row first; `#` lines are notes.
    Split on tabs alone -- a quote in a note is a quote. A state off `STATES`, a malformed
    date or a unit given twice is refused, naming the file's line."""
    path = Path(path)
    if not path.is_file():
        raise ReaderRefused(f"{path} is missing; it is tracked, so this checkout is incomplete")
    out: dict[str, Status] = {}
    header = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = [field.strip() for field in line.split("\t")]
        if not header:
            if tuple(fields) != STATUS_COLUMNS:
                raise ReaderRefused(f"{path.name}:{number}: the header is {STATUS_COLUMNS}")
            header = True
            continue
        unit, state, date, *rest = [*fields, "", "", ""]
        note = "\t".join(rest).strip()
        where = f"{path.name}:{number}"
        if state not in STATES:
            raise ReaderRefused(f"{where}: {unit} is {state!r}; a state is one of {STATES}")
        if not _DATE.fullmatch(date):
            raise ReaderRefused(f"{where}: {unit}'s date {date!r} is not YYYY-MM-DD")
        if unit in out:
            raise ReaderRefused(f"{where}: {unit} is given a state twice")
        out[unit] = Status(unit, state, date, note)
    return out


def day_unit(day: int) -> str:
    return f"day{day:02d}"


def walk_units(
    days: Path = DAYS_DIR,
    clips: Path | None = CLIP_FILE,
    movies: Path | None = movie_cues.CUE_FILE,
    textures: Path | None = TEXTURE_TEXT_DIR,
) -> set[str]:
    """The units the reader walks, named from the translation files alone -- what
    `translation/status.tsv` must give a state to, checked without an import."""
    units = {path.stem for path in translation_paths([days])}
    if there(clips):
        units.add(CLIPS_UNIT)
    if there(movies):
        units.add(MOVIES_UNIT)
    if textures is not None and Path(textures).is_dir():
        units |= {TEXTURE_UNITS.get(p.name, p.stem) for p in Path(textures).glob("*.txt")}
    return units


# --- the walkthrough ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Mark:
    """Something the lint, or the texture build, says about an item."""

    severity: str
    check: str
    message: str


@dataclass(frozen=True)
class Timeline:
    """When an item's pages are on the screen against what the screen shows, in seconds
    after the subtitle opens; the page draws both as bars of one length."""

    total: float
    phases: tuple[tuple[str, float, float], ...]
    """`(what is on screen, from, to)`."""
    pages: tuple[tuple[float, float, bool], ...]
    """`(from, to, whether it is up with a picture it should not meet)`."""


@dataclass(frozen=True)
class Item:
    """One stop of the walkthrough: a line, a clip, a cue, or a texture group."""

    id: str
    """What the copy button copies."""
    kind: str
    speaker: str = ""
    japanese_speaker: str = ""
    japanese: tuple[str, ...] = ()
    """Pages (a message), fields (a select) or transcript segments (a voice or a cue)."""
    english: tuple[str, ...] = ()
    """Pages, a select's fields, or a cue's lines. Empty is untranslated (or no subtitle)."""
    prompts: int = 0
    """How many of a select's fields are its question rather than an option."""
    origin: str = ""
    """`file:line` of the English."""
    notes: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    marks: tuple[Mark, ...] = ()
    images: tuple[tuple[str, str], ...] = ()
    """`(caption, source)`: a key of `Walkthrough.files`, or an absolute path (a still)."""
    strings: tuple[tuple[str, str], ...] = ()
    """A texture group's `(string id, English)`, each with its own copy button."""
    timeline: Timeline | None = None
    whole_screens: bool = False
    """Its images are pictures of the whole screen, shown at their own size so that several
    sit in a row; a texture narrower than `SMALL_TEXTURE` is shown doubled."""

    @property
    def ids(self) -> tuple[str, ...]:
        """The translation ids this item shows: its strings', else its own."""
        return tuple(string_id for string_id, _ in self.strings) or (self.id,)


@dataclass(frozen=True)
class Block:
    """An event, a surface, a movie or the like: a heading, its setting, its items."""

    key: str
    title: str
    items: tuple[Item, ...]
    setting: tuple[str, ...] = ()
    """Markdown lines (`PacketBuilder.setting`) or plain notes."""


@dataclass(frozen=True)
class Section:
    """One unit of `TRN-04` (`None` for the rows no screen shows), drawn as one page."""

    unit: str | None
    title: str
    group: str
    blocks: tuple[Block, ...]
    status: Status | None = None
    short: str = ""
    """The contents' name for it, where the title is too long (`Day 1`)."""

    @property
    def items(self) -> list[Item]:
        return [item for block in self.blocks for item in block.items]


@dataclass
class Walkthrough:
    sections: list[Section]
    files: dict[str, bytes] = field(default_factory=dict)
    """Texture images, by the relative path the page loads them from."""
    notices: list[str] = field(default_factory=list)
    """What the walk could not do, said once at the top of the page."""
    texture_edits: list[ByteEdit] = field(default_factory=list)
    """Every edit the texture groups made, which the English images are drawn from."""
    made: dict[str, str] = field(default_factory=dict)
    """What the page was made from (`provenance`), shown at its top."""


@dataclass(frozen=True)
class Sources:
    """Where everything the walk reads lives; `None` skips that part."""

    disc_dir: Path = DEFAULT_DISC_DIR
    days: Path = DAYS_DIR
    clips: Path | None = CLIP_FILE
    movies: Path | None = movie_cues.CUE_FILE
    textures: Path | None = TEXTURE_TEXT_DIR
    status: Path = STATUS_FILE
    voice: Path = VOICE_DIR
    movie_review: Path = MOVIE_REVIEW_DIR
    cells: Path = DEFAULT_CELLS
    build: Path = DEFAULT_BUILD_DIR
    """The days build the page is read against: its id is shown, and a translation file
    newer than it is said (`stale_build`)."""


def build_walkthrough(
    sources: Sources | None = None, *, archive: Archive | None = None, inv=None
) -> Walkthrough:
    """The whole walk. `archive` and `inv` may be passed in when they are already open."""
    sources = sources if sources is not None else Sources()
    try:
        store = load_store(Path(sources.disc_dir) / SCRIPT_DIR_NAME)
        builder = PacketBuilder.build(store, Policy.load(), [sources.days], False)
    except (StoreMissing, PacketRefused) as error:
        raise ReaderRefused(str(error)) from error
    statuses = read_status(sources.status)
    clips = there(sources.clips)
    movies = there(sources.movies)
    walkthrough = Walkthrough([])
    paths = translation_paths([sources.days])
    rows, findings = load_rows(paths)
    findings += _lint(store, rows, sources, walkthrough.notices)
    english: dict[str, list[Row]] = {}
    for row in rows:
        english.setdefault(row.line_id, []).append(row)
    walk = _Walk(
        store=store,
        builder=builder,
        english=english,
        marks=marks_by_id(findings),
        heard=voice_transcript(Path(sources.voice)),
        notes=notes_by_id([*paths, *([clips] if clips else [])]),
    )

    sections = [*event_sections(walk), surface_section(walk)]
    # The textures first: an epilogue's production card is drawn as they typeset it.
    textures = []
    if sources.textures is not None and Path(sources.textures).is_dir():
        textures = texture_sections(sources, walkthrough, archive, inv)
    if clips is not None:
        previews = epilogue_previews(clips, sources, walkthrough, archive)
        sections.append(clip_section(clips, walk, previews))
    if movies is not None:
        sections.append(movie_section(movies, walk, Path(sources.voice), sources.movie_review))
    sections += textures
    walked = {i for section in sections for item in section.items for i in item.ids}
    unplaced = [row for row in rows if row.line_id not in walked]
    if unplaced:
        sections.append(unplaced_section(unplaced, walk))
        walked.update(row.line_id for row in unplaced)
    walkthrough.notices += [
        f"{f.severity} {f.file}:{f.number} {f.check}: {f.message}"
        for f in findings
        if f.line_id not in walked
    ]
    walkthrough.sections = [
        replace(section, status=statuses.get(section.unit or "")) for section in sections
    ]
    walkthrough.made = provenance(Path(sources.build))
    stale = stale_build(sources)
    if stale:
        walkthrough.made["stale"] = stale
        walkthrough.notices.insert(0, stale)
    return walkthrough


def git(*arguments: str) -> str:
    """`git -C <repo> ...`'s output, or `""` where there is no git or no repository."""
    try:
        done = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *arguments], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return done.stdout.strip()


def build_id(build: Path) -> str:
    path = build / BUILD_ID_NAME
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def build_revision(built_id: str) -> tuple[str, bool]:
    """The commit a build id names, and whether its tree had uncommitted edits.

    `./make.sh build-days` writes `<UTC stamp>-<git describe --always --dirty>`; `("", False)`
    for an id that names no commit."""
    if "-" not in built_id:
        return "", False
    described = built_id.split("-", 1)[1]
    return described.removesuffix("-dirty"), described.endswith("-dirty")


BUILD_INPUTS = ("boku", "tools", "asm", "translation")
"""What a days build is made from, as far as git sees it: a change here since the build's
commit is a change the image does not have."""


def provenance(build: Path) -> dict[str, str]:
    """When the page was made, from which commit (and whether the build inputs had edits not
    yet committed), and the id of the days build beside it."""
    return {
        "at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": git("rev-parse", "--short=8", "HEAD"),
        "uncommitted": "yes" if git("status", "--porcelain", "--", *BUILD_INPUTS) else "",
        "build": build_id(build),
    }


def stale_build(sources: Sources) -> str | None:
    """What to say when the days build is missing, or older than what the page shows: a
    translation file modified after the build began, or a build input committed since the
    build's commit (`BUILD_INPUTS`; the id's `git describe` names that commit)."""
    stamp = Path(sources.build) / BUILD_ID_NAME
    if not stamp.is_file():
        return (
            f"No days build at {sources.build}: run ./make.sh build-days to play what this shows."
        )
    built_id = build_id(Path(sources.build))
    files = [
        *translation_paths([sources.days]),
        *(p for p in (there(sources.clips), there(sources.movies)) if p is not None),
        *(sorted(Path(sources.textures).glob("*.txt")) if sources.textures is not None else []),
    ]
    said = []
    newer = [p.name for p in files if p.stat().st_mtime > stamp.stat().st_mtime]
    if newer:
        said.append(f"{', '.join(newer)} changed after the days build {built_id} began")
    commit, _ = build_revision(built_id)
    moved = git("diff", "--name-only", commit, "HEAD", "--", *BUILD_INPUTS) if commit else ""
    if moved:
        dirs = sorted({f"{name.split('/', 1)[0]}/" for name in moved.splitlines()})
        said.append(f"the build is of {commit}, and {', '.join(dirs)} changed since")
    if not said:
        return None
    return "; ".join(said) + ": the game image does not have that yet (./make.sh build-days)."


def there(path: Path | None) -> Path | None:
    """`path` if it names a file, else `None`: an optional source that is absent is skipped."""
    return Path(path) if path is not None and Path(path).is_file() else None


def _lint(store: Store, rows: Sequence[Row], sources: Sources, notices: list[str]):
    """The lint's findings in the font the build installs; the stock cells, said so, when
    no build has written one; none, said so, when the lint cannot run."""
    kind = "cellmap" if Path(sources.cells).is_file() else "stock"
    if kind == "stock":
        notices.append(
            f"No cell map at {sources.cells}: pages are measured in the stock 14-px cells and "
            f"the movie cues not at all. Run ./make.sh build-days for the build's own font."
        )
    clips = sources.clips
    if clips is not None and not (Path(sources.disc_dir) / "files" / ARCHIVE_NAME).is_file():
        notices.append(f"No {ARCHIVE_NAME} in the import: the clip subtitles are not linted.")
        clips = None
    try:
        encoder, select_row = renderer_for(kind, Path(sources.cells))
        options = Options(encoder=encoder, select_row=select_row)
        return lint_everything(
            store, rows, options, Path(sources.disc_dir), kind, Path(sources.cells),
            sources.movies, clips,
        )  # fmt: skip
    except (OSError, LayoutError, ArchiveError) as error:
        notices.append(f"The lint could not run, so no item carries its marks: {error}")
        return []


def marks_by_id(findings: Iterable[Finding]) -> dict[str, list[Mark]]:
    out: dict[str, list[Mark]] = {}
    for finding in findings:
        out.setdefault(finding.line_id, []).append(
            Mark(finding.severity, finding.check, finding.message)
        )
    return out


def voice_transcript(directory: Path) -> dict[str, str]:
    """`voice-only.ja.tsv`: the Japanese heard in each voice-only line and clip, by id."""
    path = directory / "voice-only.ja.tsv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        return {
            row["line_id"]: row.get("ja") or "" for row in csv.DictReader(handle, delimiter="\t")
        }


# --- the translator's notes -----------------------------------------------------------------------

_NOTE = re.compile(r"(?:NOTE|VOICE)\s+(.+?):\s")
"""`# NOTE <ids>: ...` -- a note that names the line(s) it is about, wherever it sits; and
`# VOICE <id>: ...`, the kept additive words (`boku.lint.VOICE_NOTE`), placed the same way."""


def notes_by_id(paths: Iterable[Path]) -> dict[str, tuple[str, ...]]:
    """Every row's notes in files of the day-file shape (`id <TAB> ...`).

    Two kinds. A comment run directly above a row is that row's. A `# NOTE <ids>:` block --
    the convention, usually under the event's rows -- or a `# VOICE <id>:` belongs to the
    first row its ids name in the same file (`note_target`), or, naming none, to the row
    above it. A comment line whose text is indented (`#   ...`) continues the one before it."""
    out: dict[str, list[str]] = {}
    for path in paths:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        ids = [
            line.split("\t", 1)[0].strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#") and "\t" in line
        ]
        above: list[str] = []
        named: list[tuple[str, list[str], str | None]] = []
        current: list[str] | None = None
        previous: str | None = None
        for raw in lines:
            stripped = raw.strip()
            if not stripped:
                above, current = [], None
                continue
            if stripped.startswith("#"):
                body = stripped[1:]
                text = body.strip()
                if current is not None and body.startswith("  ") and text:
                    current[-1] += " " + text
                    continue
                found = _NOTE.match(text + " ")
                if found:
                    current = [text]
                    named.append((found.group(1), current, previous))
                else:
                    current = above
                    above.append(text)
                continue
            if "\t" not in raw:
                continue
            previous = raw.split("\t", 1)[0].strip()
            out.setdefault(previous, []).extend(above)
            above, current = [], None
        for expression, block, before in named:
            target = note_target(expression, ids) or before
            if target is not None:
                out.setdefault(target, []).extend(block)
    return {line_id: tuple(notes) for line_id, notes in out.items() if notes}


def note_target(expression: str, ids: Sequence[str]) -> str | None:
    """The first of `ids` a note's id expression names: `E0710.2`, a range `E0710.2-.3`, a
    list `E0101.1, .2` (a part opening with `.` keeps the last part's prefix), a pattern
    `exe@8003D2E0.*@exchange`, or a page named without its namespace (`NIKKI_072`)."""
    prefix = ""
    for part in (part.strip() for part in expression.split(",")):
        if part.startswith(".") and prefix:
            part = prefix + part
        first = part.split("-", 1)[0]
        prefix = first.rsplit(".", 1)[0] if "." in first else prefix
        if "*" in part:
            hit = next((i for i in ids if fnmatch.fnmatchcase(i, part)), None)
        else:
            hit = next(
                (
                    i
                    for i in ids
                    if i == first or i.endswith("@" + first) or i.startswith(first + ".")
                ),
                None,
            )
        if hit is not None:
            return hit
    return None


# --- the days -----------------------------------------------------------------------------------


@dataclass
class _Walk:
    """What every section is built from."""

    store: Store
    builder: PacketBuilder
    english: dict[str, list[Row]]
    marks: Mapping[str, list[Mark]]
    heard: Mapping[str, str]
    notes: Mapping[str, tuple[str, ...]]


CONVENTIONS = UNLABELLED_SPEAKERS | {SampleScenes.SELECT, SampleScenes.VOICE_ONLY}
"""The day files' speaker-column conventions: no one is speaking, so no label is shown."""


def label(speaker: str) -> str:
    return "" if speaker in CONVENTIONS else speaker


def english_of(row: Row | None) -> tuple[str, ...]:
    """A row's English as the build reads it: a select's fields, else its pages; `()` when
    the row gives none."""
    if row is None or not row.has_english:
        return ()
    entry = row.entry
    return entry.options if entry.is_select else entry.pages


def event_sections(walk: _Walk) -> list[Section]:
    """Days 1-31, then `shared.txt`'s events, then any other file's.

    An event goes where the file that holds it puts it, in that file's order -- a day file
    is the day as played, and `shared.txt` holds the events no single day owns. An event no
    file holds yet goes to the day the data dates it to, else to the day-independent ones.
    """
    placed: dict[str, list[str]] = {}
    for name, events in walk.builder.file_order.items():
        stem = Path(name).stem
        match = _DAY_FILE.fullmatch(stem)
        unit = day_unit(int(match.group(1))) if match else stem
        placed.setdefault(unit, []).extend(events)
    held = {event for events in placed.values() for event in events}
    for scene in ordered_scenes(walk.store):
        if scene["event"] in held or not has_text(scene):
            continue
        day = scene_dated_day(scene)
        placed.setdefault(day_unit(day) if day is not None else SHARED_UNIT, []).append(
            scene["event"]
        )
    days = sorted(unit for unit in placed if _DAY_FILE.fullmatch(unit))
    others = [SHARED_UNIT] if SHARED_UNIT in placed else []
    others += sorted(u for u in placed if u not in days and u != SHARED_UNIT and placed[u])
    sections = []
    for unit in [*days, *others]:
        blocks = tuple(event_block(walk.store.scenes_by_event[e], walk) for e in placed[unit])
        match = _DAY_FILE.fullmatch(unit)
        if match:
            day = int(match.group(1))
            title, short, group = f"Day {day} (August {day})", f"Day {day}", "Days"
        else:
            sections.append(unit_section(unit, "Any day", blocks))
            continue
        sections.append(Section(unit, title, group, blocks, short=short))
    return sections


def event_block(scene: dict, walk: _Walk) -> Block:
    items = tuple(line_item(line_id, walk) for line_id in scene_line_ids(scene))
    places = walk.builder.places(scene)
    return Block(
        scene["event"],
        scene["event"] + (f": {places}" if places else ""),
        items,
        tuple(walk.builder.setting(scene)),
    )


def line_item(line_id: str, walk: _Walk) -> Item:
    """One line of the script: the Japanese as the translator was given it
    (`PacketBuilder.row`), beside the English the build reads."""
    record = walk.store.lines.get(line_id)
    rows = walk.english.get(line_id, [])
    row = rows[0] if rows else None
    # A `# --- E0121: <place>` heading is the block's title already.
    notes = [note for note in walk.notes.get(line_id, ()) if not note.startswith("--- ")]
    facts = []
    if record is None:
        kind, japanese_speaker = VOICE, ""
        japanese = (walk.heard[line_id],) if walk.heard.get(line_id) else ()
        if line_id in walk.builder.voice_only:
            notes.append(f"Heard: {walk.builder.voice_only[line_id]}")
        facts.append("voice only")
    else:
        _, japanese_speaker, text = walk.builder.row(line_id).split("\t", 2)
        is_select = japanese_speaker == SampleScenes.SELECT
        kind = SELECT if is_select else LINE
        separator = SampleScenes.OPTION if is_select else SampleScenes.PAGE_BREAK
        japanese = tuple(part.strip() for part in text.split(separator))
        if record.get("voiced"):
            facts.append("voiced")
    prompts = 0
    if record is not None and (shape := select_shape(record)) is not None:
        prompts = shape[1]
    if len(rows) > 1:
        facts.append(f"{len(rows)} rows")
    return Item(
        id=line_id,
        kind=kind,
        speaker=label(row.speaker) if row is not None else "",
        japanese_speaker=label(japanese_speaker),
        japanese=japanese,
        english=english_of(row),
        prompts=prompts,
        origin=f"{row.file}:{row.number}" if row is not None else "",
        notes=tuple(notes),
        facts=tuple(facts),
        marks=tuple(walk.marks.get(line_id, ())),
    )


def row_item(row: Row, walk: _Walk, kind: str, facts: tuple[str, ...] = ()) -> Item:
    """A row with no line of the script behind it: English, notes and marks only."""
    return Item(
        id=row.line_id,
        kind=kind,
        speaker=label(row.speaker),
        english=english_of(row),
        origin=f"{row.file}:{row.number}",
        notes=walk.notes.get(row.line_id, ()),
        facts=facts,
        marks=tuple(walk.marks.get(row.line_id, ())),
    )


# --- the screens ----------------------------------------------------------------------------------


def surface_section(walk: _Walk) -> Section:
    """Every line outside the events, one block per screen or list (`Store.surfaces`); a
    notebook variant (`exchange_notebook`) right after the item it varies."""
    variants: dict[str, list[str]] = {}
    for line_id in walk.english:
        if exchange_notebook.is_variant(line_id):
            variants.setdefault(exchange_notebook.base_of(line_id), []).append(line_id)
    blocks = []
    for surface in surfaces_of(walk.store):
        items = []
        for line_id in surface.line_ids:
            items.append(line_item(line_id, walk))
            items += [
                row_item(walk.english[v][0], walk, LINE, ("the notebook's wording of the above",))
                for v in variants.get(line_id, ())
            ]
        title = f"{surface.key}: {walk.builder.describe(surface)}"
        blocks.append(Block(surface.key, title, tuple(items)))
    return unit_section(ARRAYS_UNIT, "Screens", blocks)


def unplaced_section(rows: Sequence[Row], walk: _Walk) -> Section:
    """Translated rows for no line the script has: shown so they cannot hide."""
    items = tuple(row_item(row, walk, ROW) for row in rows)
    block = Block("unplaced", "Rows for no line in the script", items)
    title = "Rows no screen shows"
    return Section(None, title, "Problems", (block,), short=title)


# --- the voices -----------------------------------------------------------------------------------


def clip_section(path: Path, walk: _Walk, previews: Mapping[str, Item] | None = None) -> Section:
    """`clips.txt`, in the file's order: every clip row, worded or not; an epilogue with
    `epilogue_previews`' facts, pictures and timeline."""
    rows, _ = parse_file(path)
    items = []
    for row in rows:
        item = row_item(row, walk, CLIP)
        heard = walk.heard.get(row.line_id)
        gist = walk.builder.voice_only.get(row.line_id)
        drawn = (previews or {}).get(row.line_id)
        items.append(
            replace(
                item,
                japanese=(heard,) if heard else (),
                notes=(*item.notes, *((f"Heard: {gist}",) if gist else ())),
                facts=(*item.facts, *(drawn.facts if drawn else ())),
                images=drawn.images if drawn else item.images,
                timeline=drawn.timeline if drawn else None,
                whole_screens=drawn.whole_screens if drawn else False,
            )
        )
    block = Block("clips", "The clips BOKU_XA.XCH holds", tuple(items))
    return unit_section(CLIPS_UNIT, "Voices", (block,))


def _seconds(vsyncs: int) -> float:
    return round(float(vsyncs / VSYNC_HZ), 2)


PREVIEW_ERRORS = (
    ArchiveError,
    BuildRefused,
    clip_preview.PreviewError,
    epilogue.EpilogueError,
    LayoutError,
    TimError,
    OSError,
    struct.error,
)
"""What an import or an edit set that is not the expected one raises under
`epilogue_previews`: a notice, not the end of the reader."""


def epilogue_previews(
    path: Path, sources: Sources, walkthrough: Walkthrough, archive: Archive | None = None
) -> dict[str, Item]:
    """Per epilogue row of `clips.txt`, what the reader adds to its item: every page drawn
    over the picture `ENDOTI` shows at its middle (`boku.clip_preview`: the stills from the
    import, the production card as the textures typeset it, the band and glyphs of the
    days build), captioned with when it is up and over what, and the timeline of pages
    against pictures -- from `boku.clip_subs.lay_out_lines`, the layout the build writes
    and the lint judges. The images go to `walkthrough.files`. Nothing, said once, without
    the import or the build's edit set."""
    files: dict[str, bytes] = {}
    try:
        archive = archive if archive is not None else Archive(Path(sources.disc_dir))
        out = _epilogue_previews(path, sources, walkthrough.texture_edits, archive, files)
    except PREVIEW_ERRORS as error:
        walkthrough.notices.append(f"The epilogues' pages are not drawn: {error}")
        return {}
    walkthrough.files.update(files)
    return out


def _epilogue_previews(
    path: Path, sources: Sources, texture_edits: Sequence[ByteEdit], archive: Archive, files
) -> dict[str, Item]:
    edit_set = load_edit_set(Path(sources.cells))
    font = clip_preview.built_font(archive, edit_set)
    band = clip_preview.Band.of(edit_set)
    entries, _ = clip_subs.read(path)
    lines, _ = clip_subs.lay_out_lines(
        entries, xch_nodes(archive), edit_set.encoder, epilogue.pictures(archive)
    )
    try:
        english = patched_archive(archive, texture_edits)
    except TextureTextError:
        english = None
    out = {}
    for line in lines:
        picture = line.picture
        if picture is None:
            continue
        line_id = line.entry.line_id
        backdrops = {
            what: clip_preview.backdrop(archive, picture, start, english)
            for what, start, _ in picture.phases
        }
        images, pages = [], []
        for number, page in enumerate(line.pages, start=1):
            pages.append((_seconds(page.start), _seconds(page.end), page.meets_card(picture)))
            if page.end <= page.start:
                continue
            canvas = bytearray(backdrops[picture.showing((page.start + page.end) // 2)])
            clip_preview.draw_subtitle(canvas, page.lines, edit_set.encoder, font, band)
            name = f"img/{line_id}.page{number:02d}.en.png"
            files[name] = clip_preview.png(canvas)
            over = [
                what for what, start, end in picture.phases if start < page.end and page.start < end
            ]
            images.append(
                (
                    f"page {number}: {_seconds(page.start)}-{_seconds(page.end)} s "
                    f"({float(page.seconds):.1f} s) over {', then '.join(over)}",
                    name,
                )
            )
        name = f"img/{line_id}.card.en.png"
        files[name] = clip_preview.png(backdrops[epilogue.CARD])
        images.append((f"{_seconds(picture.card)} s: {epilogue.CARD}", name))
        out[line_id] = Item(
            id=line_id,
            kind=CLIP,
            facts=(f"OTI0{picture.ending}", f"{epilogue.CARD} at {_seconds(picture.card)} s"),
            images=tuple(images),
            timeline=Timeline(
                total=_seconds(picture.end),
                phases=tuple((n, _seconds(a), _seconds(b)) for n, a, b in picture.phases),
                pages=tuple(pages),
            ),
            whole_screens=True,
        )
    return out


def movie_notes(path: Path) -> tuple[dict[int, tuple[str, ...]], dict[int, str]]:
    """`movies.txt`'s notes by the line number of the cue row they belong to -- the comment
    run right under a row (the file's convention), or a run after a blank line and before a
    row (`# SONG`), each run one paragraph -- and its `# ---` headings, with their indented
    continuation lines, by theirs."""
    above: dict[int, str] = {}
    below: dict[int, list[str]] = {}
    headings: dict[int, str] = {}
    run: list[str] = []
    owner: int | None = None
    heading: int | None = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            run, owner, heading = [], None, None
            continue
        if line.startswith("#"):
            body = line[1:]
            text = body.strip()
            if text.startswith("---"):
                headings[number], heading, owner = text.lstrip("- "), number, None
            elif heading is not None and body.startswith("  "):
                headings[heading] += " " + text
            elif owner is not None:
                below.setdefault(owner, []).append(text)
            else:
                heading = None
                run.append(text)
            continue
        heading, owner = None, number
        if run:
            above[number] = " ".join(run)
        run = []
    notes = {
        n: tuple(p for p in (above.get(n), " ".join(below.get(n, ()))) if p)
        for n in {*above, *below}
    }
    return notes, headings


def movie_transcript(directory: Path, movie: str) -> list[tuple[int, int, str]]:
    """`<movie>.ja.tsv`'s worded segments: `(first frame, last frame, Japanese)`."""
    path = directory / f"{movie}.ja.tsv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [
            (int(row["start_frame"]), int(row["end_frame"]), row["ja"])
            for row in csv.DictReader(handle, delimiter="\t")
            if (row.get("ja") or "").strip()
        ]


def seconds(frame: int) -> str:
    """A movie frame as `m:ss.s` (frame 1 is 0 s)."""
    at = (frame - 1) / FPS
    return f"{int(at // 60)}:{at % 60:04.1f}"


def movie_section(path: Path, walk: _Walk, voice: Path, stills: Path) -> Section:
    cues, _ = movie_cues.read(path)
    notes, headings = movie_notes(path)
    blocks = []
    for movie in dict.fromkeys(cue.movie for cue in cues):
        mine = [cue for cue in cues if cue.movie == movie]
        heard = movie_transcript(voice, movie)
        heading = next(
            (
                text
                for number, text in sorted(headings.items(), reverse=True)
                if number < mine[0].line
            ),
            "",
        )
        items = []
        for cue in mine:
            flags = [flag for flag, on in (("caption", cue.caption), ("panel", cue.panel)) if on]
            if cue.position != movie_cues.DEFAULT_POSITION:
                flags.append(cue.position)
            shots = tuple(
                (which, str(shot))
                for which in ("first", "middle", "last")
                if (shot := Path(stills) / movie / "shots" / f"{cue.start}-{which}.png").is_file()
            )
            items.append(
                Item(
                    id=cue.key,
                    kind=CUE,
                    japanese=tuple(
                        ja for start, end, ja in heard if start <= cue.end and end >= cue.start
                    ),
                    english=tuple(line.strip() for line in cue.text.split(movie_cues.LINE_BREAK)),
                    origin=f"{path.name}:{cue.line}",
                    notes=notes.get(cue.line, ()),
                    facts=(
                        f"frames {cue.start}-{cue.end}",
                        f"{seconds(cue.start)}-{seconds(cue.end + 1)}",
                        *flags,
                    ),
                    marks=tuple(walk.marks.get(cue.key, ())),
                    images=shots,
                )
            )
        blocks.append(Block(movie, heading or movie, tuple(items)))
    return unit_section(MOVIES_UNIT, "Voices", blocks)


# --- the textures ---------------------------------------------------------------------------------


def texture_sections(
    sources: Sources, walkthrough: Walkthrough, archive: Archive | None, inv
) -> list[Section]:
    """Every texture group the tracked English builds, the original image beside the
    rebuilt one. A group is a single texture's strings (`tex@T_TITLE`) or one page or member
    of a bulk family (`nikki@NIKKI_072`, `mzkan@3`, `btn@SUB`), built on its own so each image
    is shown with the strings that drew it and a refusal lands on the group it is about."""
    directory = Path(sources.textures)
    try:
        entries = read_texture_entries(directory)
    except TextureTextError as error:
        walkthrough.notices.append(f"The texture strings cannot be read: {error}")
        return []
    groups: dict[str, list] = {}
    for entry in entries.values():
        groups.setdefault(entry.id.rsplit(".", 1)[0], []).append(entry)
    notes = notes_by_id(sorted(directory.glob("*.txt")))
    built: dict[str, tuple[list[str], list[Mark]]] = {}
    viewed: dict[str, tuple[tuple[str, str], ...]] = {}
    try:
        archive = archive if archive is not None else Archive(Path(sources.disc_dir))
        inv = inv if inv is not None else inventory(archive)
        face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    except (ArchiveError, OSError, TextureError) as error:
        walkthrough.notices.append(f"No import to build the textures from, so no images: {error}")
        archive = None
    if archive is not None:
        spans = sorted(
            (o.file_offset, o.file_offset + o.length, texture.id)
            for texture in inv.textures
            for o in texture.occurrences[:1]
            if o.file == ARCHIVE_NAME
        )
        starts = [start for start, _, _ in spans]
        for key, members in groups.items():
            family = FAMILIES.get(members[0].family)
            images, marks, edits = build_group(family, archive, inv, face, members, spans, starts)
            walkthrough.texture_edits += edits
            built[key] = (images, marks)
        try:
            blob = patched_archive(archive, walkthrough.texture_edits)
        except TextureTextError as error:
            walkthrough.notices.append(f"The texture edits do not apply together: {error}")
            blob = None
        by_id = {texture.id: texture for texture in inv.textures}
        for texture_id in sorted({t for images, _ in built.values() for t in images}):
            texture = by_id[texture_id]
            walkthrough.files[f"img/{texture_id}.ja.png"] = to_png(texture.tim)
            if blob is not None:
                after = parse_exact(blob, texture.occurrences[0].file_offset)
                walkthrough.files[f"img/{texture_id}.en.png"] = to_png(after)
        for key in groups.keys() & VIEWS.keys():
            if built[key][0]:  # the group built: its views stand for its whole atlases
                viewed[key] = view_pictures(key, VIEWS[key], by_id, blob, walkthrough.files)

    def place(entry) -> tuple[str, int]:
        name, number = entry.where.rsplit(":", 1)
        return name, int(number)

    rank = {name: index for index, name in enumerate(TEXTURE_UNITS)}
    by_unit: dict[str, list[Item]] = {}
    for key, members in sorted(
        groups.items(), key=lambda kv: (rank.get(place(kv[1][0])[0], len(rank)), place(kv[1][0]))
    ):
        name = place(members[0])[0]
        images, group_marks = built.get(key, ([], []))
        pictures = viewed.get(key) or tuple(
            (caption, path)
            for texture_id in images
            for caption, path in (
                ("original", f"img/{texture_id}.ja.png"),
                ("English", f"img/{texture_id}.en.png"),
            )
            if path in walkthrough.files
        )
        by_unit.setdefault(TEXTURE_UNITS.get(name, Path(name).stem), []).append(
            Item(
                id=key,
                kind=TEXTURE,
                origin=members[0].where,
                notes=tuple(note for m in members for note in notes.get(m.id, ())),
                facts=tuple(images),
                marks=tuple(group_marks),
                images=pictures,
                strings=tuple((m.id, m.text) for m in members),
            )
        )
    return [
        unit_section(unit, "Textures", (Block(unit, "", tuple(items)),))
        for unit, items in by_unit.items()
    ]


VIEW_GROUND = (96, 96, 112, 255)
"""What a view shows where a sprite is transparent: white lettering has to stay readable."""


def view_pictures(
    key: str, views: Sequence[View], by_id, blob: bytes | None, files: dict[str, bytes]
) -> tuple[tuple[str, str], ...]:
    """A group's pictures as the game draws them (a family's `VIEWS`): each view's box of
    the original and, if the edits applied, of the rebuilt image, added to `files`."""
    pictures = []
    for n, view in enumerate(views):
        stock = by_id[view.texture]
        sides = [("original", "ja", stock, view.original)]
        if blob is not None:
            tim = parse_exact(blob, stock.occurrences[0].file_offset)
            sides.append(("English", "en", Texture(stock.id, stock.sha1, tim, ()), view.english))
        for caption, tag, texture, (x0, y0, w, h) in sides:
            canvas = Canvas(texture, drawn_4bpp=view.drawn_4bpp)
            palette = canvas.palette(view.clut, view.chunk)
            colours = (palette[canvas.at((x, y))] for y in range(y0, y0 + h)
                       for x in range(x0, x0 + w))  # fmt: skip
            rgba = b"".join(bytes(c if c[3] else VIEW_GROUND) for c in colours)
            name = f"img/{key.replace('@', '-')}.{n}.{tag}.png"
            files[name] = write_rgba(w, h, rgba)
            pictures.append((caption, name))
    return tuple(pictures)


def build_group(family, archive, inv, face, members, spans, starts):
    """One texture group through its recipe: `(texture ids it drew into, marks, edits)`. A
    refusal -- the recipe's, the typesetter's, or a texture this import lacks -- is a mark on
    the group, never the end of the walk."""
    if family is None:
        return [], [Mark("ERROR", "texture", f"no recipe builds {members[0].family}")], []
    try:
        edits = family(archive, inv, face, members)
    except (TextureTextError, TypesetError, TimError, TextureError) as error:
        return [], [Mark("ERROR", "texture", str(error))], []
    return touched(edits, spans, starts), [], list(edits)


def touched(edits: Sequence[ByteEdit], spans, starts: Sequence[int]) -> list[str]:
    """The textures (by id) whose first `BOKU.BIN` copy any of `edits` writes into."""
    found: dict[str, None] = {}
    for edit in edits:
        if edit.file != ARCHIVE_NAME:
            continue
        for at in range(bisect_right(starts, edit.end - 1) - 1, -1, -1):
            _, end, texture_id = spans[at]
            if end <= edit.offset:
                break
            found[texture_id] = None
    return sorted(found)


# --- the page -------------------------------------------------------------------------------------

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    return _BOLD.sub(r"<strong>\1</strong>", _CODE.sub(r"<code>\1</code>", html.escape(text)))


def setting_html(lines: Sequence[str]) -> str:
    """`PacketBuilder.setting`'s Markdown, as the little of HTML it needs: headings, bullets
    (nested by indent), paragraphs and the per-day table."""
    out: list[str] = []
    table: list[list[str]] = []

    def flush() -> None:
        if table:
            head, *body = table
            out.append(
                "<table><tr>"
                + "".join(f"<th>{_inline(c)}</th>" for c in head)
                + "</tr>"
                + "".join(
                    "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body
                )
                + "</table>"
            )
            table.clear()

    for line in lines:
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not set("".join(cells)) <= set("-: "):
                table.append(cells)
            continue
        flush()
        stripped = line.lstrip()
        if line.startswith("## "):
            out.append(f"<h4>{_inline(line[3:])}</h4>")
        elif stripped.startswith("* "):
            depth = min((len(line) - len(stripped)) // 2, 3)
            out.append(f'<p class="li d{depth}">{_inline(stripped[2:])}</p>')
        elif stripped:
            out.append(f"<p>{_inline(stripped)}</p>")
    flush()
    return "".join(out)


def item_json(item: Item, images: list[list]) -> dict:
    """An item as the page reads it, with its images sized (`walkthrough_json`); empty fields
    left out."""
    data = {
        "id": item.id,
        "kind": item.kind,
        "speaker": item.speaker,
        "jspeaker": item.japanese_speaker,
        "ja": list(item.japanese),
        "en": list(item.english),
        "prompts": item.prompts,
        "origin": item.origin,
        "notes": list(item.notes),
        "facts": list(item.facts),
        "marks": [[m.severity, m.check, m.message] for m in item.marks],
        "images": images,
        "strings": [{"id": i, "en": text} for i, text in item.strings],
        "timeline": item.timeline and asdict(item.timeline),
    }
    return {key: value for key, value in data.items() if value or key in ("id", "kind", "en")}


def png_size(head: bytes) -> tuple[int, int]:
    """A PNG's width and height, from its IHDR chunk; `(0, 0)` for anything else."""
    if head[:8] != PNG_SIGNATURE or len(head) < 24:
        return 0, 0
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


SMALL_TEXTURE = 400
"""A texture narrower than this is shown at twice its size, pixel for pixel."""


def walkthrough_json(walkthrough: Walkthrough, out_dir: Path) -> dict:
    def image(caption: str, path: str, whole_screen: bool) -> list:
        """`[caption, src, width, height]` at the size the page shows it, so the layout does
        not move as images load. A still is linked where `movie-review` left it."""
        if Path(path).is_absolute():
            with open(path, "rb") as handle:
                width, height = png_size(handle.read(24))
            return [caption, os.path.relpath(path, out_dir), width, height]
        width, height = png_size(walkthrough.files[path][:24])
        scale = 2 if width < SMALL_TEXTURE and not whole_screen else 1
        return [caption, path, width * scale, height * scale]

    sections = []
    for section in walkthrough.sections:
        status = section.status
        blocks = []
        for block in section.blocks:
            items = [
                item_json(item, [image(*pair, item.whole_screens) for pair in item.images])
                for item in block.items
            ]
            blocks.append(
                {
                    "key": block.key,
                    "title": block.title,
                    "setting": setting_html(block.setting),
                    "items": items,
                }
            )
        sections.append(
            {
                "unit": section.unit,
                "title": section.title,
                "short": section.short,
                "group": section.group,
                "status": None if status is None else {
                    "state": status.state, "date": status.date, "note": status.note,
                },
                "blocks": blocks,
            }
        )  # fmt: skip
    return {
        "states": list(STATES),
        "made": walkthrough.made,
        "notices": walkthrough.notices,
        "sections": sections,
    }


def write_site(walkthrough: Walkthrough, out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    """`index.html` and `img/` under `out_dir` (refused anywhere the repo tracks); the images
    a previous run wrote (`img/*.ja.png`, `img/*.en.png`) are removed first, nothing else.
    Returns the page."""
    try:
        out_dir = check_destination(out_dir, "The reader")
    except PacketRefused as error:
        raise ReaderRefused(str(error)) from error
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in [*(out_dir / "img").glob("*.ja.png"), *(out_dir / "img").glob("*.en.png")]:
        stale.unlink()
    for name, data in walkthrough.files.items():
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # `<` escaped everywhere, so no line of the script can close the data's <script> element.
    data = json.dumps(walkthrough_json(walkthrough, out_dir), ensure_ascii=False)
    data = data.replace("<", "\\u003c")
    index = out_dir / "index.html"
    index.write_text(PAGE.replace("/*WALK*/", data), encoding="utf-8")
    return index


# --- the command ----------------------------------------------------------------------------------


def summary(walkthrough: Walkthrough) -> list[str]:
    out = []
    for section in walkthrough.sections:
        items = section.items
        untranslated = sum(1 for i in items if i.kind in (LINE, SELECT) and not i.english)
        marked = sum(1 for i in items if i.marks)
        state = section.status.state if section.status else "NO STATE"
        out.append(
            f"  {section.unit or '-':10} {len(items):5} item(s)"
            + (f", {untranslated} untranslated" if untranslated else "")
            + (f", {marked} marked" if marked else "")
            + f"  [{state}]  {section.title}"
        )
    return out


def main_reader(sources: Sources, out: Path) -> int:
    try:
        walkthrough = build_walkthrough(sources)
        index = write_site(walkthrough, out)
    except ReaderRefused as error:
        print(f"reader: {error}", file=sys.stderr)
        return 2
    for notice in walkthrough.notices:
        print(f"reader: {notice}")
    print("\n".join(summary(walkthrough)))
    total = sum(len(section.items) for section in walkthrough.sections)
    print(f"reader: {total} item(s) in {len(walkthrough.sections)} section(s) -> {index}")
    missing = [s.unit for s in walkthrough.sections if s.unit and s.status is None]
    if missing:
        print(f"reader: {sources.status} gives no state to {', '.join(missing)}", file=sys.stderr)
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    defaults = Sources()
    parser.add_argument(
        "--disc", type=Path, default=defaults.disc_dir, metavar="DIR",
        help=f"the import to read the script and the textures from (default: {defaults.disc_dir})",
    )  # fmt: skip
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT_DIR, metavar="DIR",
        help=f"where the page is written, under work/ (default: {DEFAULT_OUT_DIR})",
    )  # fmt: skip
    parser.add_argument(
        "--voice", type=Path, default=defaults.voice, metavar="DIR",
        help=f"the reviewed transcripts: the Japanese of voices and cues (default: {VOICE_DIR})",
    )  # fmt: skip
    parser.add_argument(
        "--movie-review", type=Path, default=defaults.movie_review, metavar="DIR",
        help=f"./make.sh movie-review's stills (default: {MOVIE_REVIEW_DIR})",
    )  # fmt: skip
    parser.add_argument(
        "--build", type=Path, default=defaults.build, metavar="DIR",
        help=f"the days build the page is read against (default: {DEFAULT_BUILD_DIR})",
    )  # fmt: skip
    parser.add_argument(
        "--cells", type=Path, default=defaults.cells, metavar="FILE",
        help=f"the cell map the lint measures in (default: {DEFAULT_CELLS}, which "
        f"./make.sh build-days writes; without it the stock cells)",
    )  # fmt: skip
    parser.set_defaults(
        run=lambda args: main_reader(
            Sources(
                disc_dir=args.disc,
                voice=args.voice,
                movie_review=args.movie_review,
                cells=args.cells,
                build=args.build,
            ),
            args.out,
        )
    )
    return parser


PAGE = (Path(__file__).parent / "reader.html").read_text(encoding="utf-8")
"""The page: its style and script, with `/*WALK*/` where the walkthrough's JSON goes."""
