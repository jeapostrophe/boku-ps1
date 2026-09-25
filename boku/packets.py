"""`PLAN TRN-08` -- the translator packet: a system part once, then one part per event.

A unit of translation is a day (or `shared.txt`, or any day file, or -- `PLAN TRN-09` --
the menus, books and screens outside every event, or -- the v3 packet, Jay 2026-09-23 --
the whole game in play order), and the translator is one agent directed through it by a
parent (Jay, 2026-09-21: agent shape (b)). So a packet is a directory:

* `system.md` -- given **once**: the day-file format (`translation/days/README.md`
  § Format), then the story bible, the style guide, the glossary and
  `translation/checklist.md`, each **whole** and verbatim but for PLAN citations (Jay,
  2026-09-23: the translator gets "everything"; 2026-09-22: a glossary narrowed to the
  rows a matcher found dropped rows and caused errors).
* one part per event (`E0121.md`) or surface (`exe@8003D2E0.md`; `part_file` turns a
  key's `:` into `_`), given **one at a time** in `order.txt`'s order: where, when and who
  (or what the surface is), the branches if the scene has any, the neighbouring scenes'
  English as it stands, and the lines **in the day-file shape** with the Japanese in the
  English column and only the page breaks marked. No voice-clip ids (Jay, 2026-09-23); a
  line that replays another's recording names that line. The translator's answer is the
  block with the Japanese replaced, and `boku save-event` writes it into the day file --
  the parent does the saving, placing a new block by `order.txt` (`--order`).
* `order.txt` -- one row per part, in the order the parts are given: the event id or
  surface key, a tab, and the translation file its answer is saved into (`target_file`).

    ./make.sh packet --day 8
    ./make.sh packet --like translation/days/day01.txt
    ./make.sh packet --arrays
    ./make.sh packet --game
    ./make.sh save-event E0121 --answer answer.txt --order work/packets/day01/order.txt

`--game` (`unit_of_game`) is every event of all 31 days in play order -- a day file's own
order where one exists, each day-independent event at the day `first_day` gives it --
then every surface; each day's first part says the day begins. `translation/README.md`
§ "Translating the whole game" is how a session is driven through it.

What a translator is **not** handed (Jay's list, `TRN-08`): capacities, byte and copy
counts, pixel widths, frame timers, column splits, lint output, PLAN citations. A
translator asked not to let constraints bend the translation should not be given the
constraints; `boku lint` holds them, and `./make.sh mockup` draws the pages.

**A packet is the Japanese script, so it is written under the gitignored `work/` and can
never be tracked** (CLAUDE.md § "This repo is public"). `--out` refuses anywhere else
inside the repo.

Everything in a packet is *derived*: the scene graph from `disc/script/scenes/`, the lines
from `disc/script/lines.jsonl`, the policy from `translation/*.md` as they stand. Nothing
here restates a fact those files own (`DOC-3`). Two runs over one store write
byte-identical files: no timestamp, no absolute path, no set iteration in the output.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cached_property
from itertools import dropwhile, groupby
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import DEFAULT_DISC_DIR
from boku.events import CHARACTERS, LABEL_NAMES
from boku.extract import SCRIPT_DIR_NAME
from boku.glyphs import GlyphTable
from boku.layout import Marks, menu_lines, original_marks, speaker_label
from boku.lint import Row, load_rows, parse_file, parse_text, translation_paths
from boku.script_store import (
    PLACED_BY_CODE,
    Japanese,
    Store,
    StoreMissing,
    is_array,
    is_array_select,
    iter_play_order,
    load_store,
    ordered_scenes,
    original_bytes,
    scene_dated_day,
    scene_day,
    scene_hour,
    scene_plays_on,
    scenes_named,
    scenes_of_day,
    select_shape,
)
from boku.translation import SampleScenes

DEFAULT_OUT_DIR = REPO_ROOT / "work" / "packets"
TRANSLATION_DIR = REPO_ROOT / "translation"
DAYS_DIR = TRANSLATION_DIR / "days"
FORMAT_SECTION = "Format"
"""The section of `translation/days/README.md` a packet quotes as the day-file format."""

SYSTEM_NAME = "system.md"
ORDER_NAME = "order.txt"
ARRAYS_NAME = "arrays.txt"
"""The day file the surfaces' English lives in (`translation/days/README.md`)."""

CHECKLIST_NAME = "checklist.md"
"""`translation/checklist.md`: the settled renderings the re-translation of days 1-7 got
wrong most often, each citing its home."""

POLICY_DOCUMENTS = (
    ("The story bible (translation/bible.md, whole)", "bible.md"),
    ("The style guide (translation/style-guide.md, whole)", "style-guide.md"),
    ("The glossary (translation/glossary.md, whole)", "glossary.md"),
    ("Before you answer: the renderings most often got wrong", CHECKLIST_NAME),
)
"""What `system.md` carries after the format, whole and in this order, the checklist last
so it is the last thing read before the first part (Jay, 2026-09-23)."""

MONTH = range(1, 32)
"""The in-game days, August 1-31."""
GAME_NAME = "game"
"""`--game`'s directory under `work/packets/`."""

SURFACE_KINDS = {
    "array-E": "one entry of a list the code picks by number",
    "array-L": "one line of a list the code draws line by line",
    "array-R": "a fixed row of characters the code draws cell by cell",
    "array-S": "a choice menu held in the program: the question first, then the choices",
    "array-S1": "one word of a menu",
    "code-label": "a label the program spells out in its own code; ` / ` separates pieces "
    "drawn in different places",
    "sjis-title": "the title of the save on the memory card, as the console's card screen shows it",
    "XAMSG": "a spoken message the program holds itself, outside every event",
}
"""What each kind of non-event line is, in the translator's terms (the extract's kinds,
`research/text-outside-events.md`)."""

_DRAW_FUNCTION = re.compile(r"^\w+_draw: ")
_CAPACITY = re.compile(
    r",?\s*\d+\s*(?:(?!digit)[a-z]+\s+)?(?:[x+]\s*\d+\s*)*(?:glyphs|cells)(?:\s*\([^)]*\))?"
)
"""A glyph or cell count in an extract's purpose note: the lint's to hold, not the
translator's to see (`TRN-08`)."""

EVENT_HEADER = "# --- "
"""What opens an event's block in a day file (`translation/days/README.md` § Format)."""
IDEOGRAPHIC_SPACE = "\u3000"
"""The authoring tool's indent at the head of every continuation column, and the space
Japanese punctuates with; the packet joins a page's columns with one."""


VOICE_ONLY_TSV = REPO_ROOT / "research" / "data" / "voice-only.tsv"


class PacketRefused(Exception):
    """A destination this tool must not write to, a scene it cannot assemble, or an answer
    it will not save."""


def voice_only_gists(path: Path = VOICE_ONLY_TSV) -> dict[str, str]:
    """`research/data/voice-only.tsv`'s gist of each voice-only line: its `said` column (an
    English gist, or `wordless`) and its `notes`, which say what the sound is."""
    if not path.is_file():
        raise PacketRefused(f"{path} is missing; it is tracked, so this checkout is incomplete")
    rows = (
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
    )
    out: dict[str, str] = {}
    for row in csv.DictReader(rows, delimiter="\t"):
        said, notes = (row.get("said") or "").strip(), (row.get("notes") or "").strip()
        out[row["line_id"]] = f"{said}: {notes}" if said and notes else said or notes
    return out


# --- where a packet may be written ------------------------------------------------------------


def check_destination(out: Path, what: str = "A packet") -> Path:
    """Refuse a destination inside the repo that is not under `work/`.

    A packet, or the reader's page (`what`), holds the Japanese script. Outside the checkout
    (a scratch directory, a translator's own machine) is the caller's business; inside it,
    `work/` is the only place the `.gitignore` keeps out of a commit.
    """
    out = Path(out).resolve()
    try:
        inside = out.relative_to(REPO_ROOT)
    except ValueError:
        return out
    if inside.parts[:1] != ("work",):
        raise PacketRefused(
            f"{out} is inside the repo and not under work/. {what} is the game's own "
            f"text and is never tracked (CLAUDE.md § 'This repo is public')."
        )
    return out


# --- the policy documents, narrowed to one scene -------------------------------------------------

_HEADING = re.compile(r"^(#{2,3})\s+(.*)$")
_TABLE_ROW = re.compile(r"^\|(.*)\|\s*$")
_SLOT = re.compile(r"\bslots?\s+((?:\d+)(?:\s*,\s*\d+)*)")
_BASE = re.compile(r"^([A-Z])(\d+)$")


def markdown_sections(text: str, level: int) -> list[tuple[str, list[str]]]:
    """`(heading, body lines)` for every heading of exactly `level` hashes, in order."""
    out: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) <= level:
            if len(match.group(1)) == level:
                current = []
                out.append((match.group(2).strip(), current))
            else:
                current = None
            continue
        if current is not None:
            current.append(line)
    return out


def _table_cells(line: str) -> list[str] | None:
    """A Markdown table row's cells, or `None` if this is not a row (or is the rule)."""
    match = _TABLE_ROW.match(line.strip())
    if match is None:
        return None
    cells = [cell.strip() for cell in match.group(1).split("|")]
    if all(set(cell) <= set("-: ") and cell for cell in cells):
        return None
    return cells


@dataclass(frozen=True)
class CastEntry:
    """One `### ` entry of the bible's § 3, and the slots its heading names."""

    heading: str
    slots: tuple[int, ...]


@dataclass(frozen=True)
class Policy:
    """`translation/` as a packet needs it -- parsed once, narrowed per scene."""

    places: tuple[tuple[str, str], ...] = ()
    """The bible's § 7 map base -> place table, one row per base."""
    cast: tuple[CastEntry, ...] = ()
    flags: Mapping[int, str] = field(default_factory=dict)
    """The bible's § 8 story flags by number: what a `flag[n]` test is about."""

    @classmethod
    def load(cls, directory: Path = TRANSLATION_DIR) -> Policy:
        directory = Path(directory)
        bible = _read(directory / "bible.md")
        return cls(
            places=parse_places(bible),
            cast=parse_cast(bible),
            flags=parse_flags(bible),
        )

    def place(self, base: str) -> str:
        return dict(self.places).get(base, "")

    def cast_for(self, slots: Iterable[int]) -> list[CastEntry]:
        wanted = set(slots)
        return [entry for entry in self.cast if wanted.intersection(entry.slots)]


def _required(path: Path) -> str:
    """A policy document the packet hands over whole: a missing one is a refusal, never an
    empty section."""
    if not path.is_file():
        raise PacketRefused(f"{path} is missing; the translator's packet carries it whole")
    return path.read_text(encoding="utf-8")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


_FLAG_ITEM = re.compile(r"^(\d+(?:\s*[/,\u2013-]\s*\d+)*)\s+(.+)$", re.S)


def parse_flags(bible: str) -> dict[int, str]:
    """The bible's § 8 "Flags evident from the script" list: `n name` items joined by ` · `,
    `37/38` naming two flags, `57-60` a run of them, `131-145, 147-153` two runs."""
    body = next(
        (lines for heading, lines in markdown_sections(bible, 2) if heading.startswith("8.")), []
    )
    text = " ".join(body)
    start = text.find("**Flags evident")
    if start < 0:
        return {}
    paragraph = text[start:].split("**For whoever", 1)[0]
    paragraph = paragraph.split("): ", 1)[-1]
    out: dict[int, str] = {}
    for item in paragraph.split(" · "):
        match = _FLAG_ITEM.match(item.strip())
        if match is None:
            continue
        name = re.sub(r"\s+", " ", match.group(2)).strip().rstrip(".")
        for part in re.split(r"[/,]", match.group(1)):
            ends = [int(n) for n in re.split(r"\s*[\u2013-]\s*", part.strip())]
            for number in range(ends[0], ends[-1] + 1):
                out.setdefault(number, name)
    return out


def parse_places(bible: str) -> tuple[tuple[str, str], ...]:
    """The bible's § 7 base -> place table, with `G04 / G05` and `H01-H03` expanded."""
    body = next(
        (lines for heading, lines in markdown_sections(bible, 2) if heading.startswith("7.")), []
    )
    out: list[tuple[str, str]] = []
    for line in body:
        cells = _table_cells(line)
        if cells is None or len(cells) < 2:
            continue
        for base in _expand_bases(cells[0]):
            out.append((base, cells[1]))
    return tuple(out)


def _expand_bases(cell: str) -> list[str]:
    """`G04 / G05`, `H04, H09, H10`, `H01-H03` -> the bases they name."""
    out: list[str] = []
    for piece in re.split(r"[/,]", cell):
        piece = piece.strip()
        if not piece:
            continue
        ends = [part.strip() for part in re.split(r"[-\u2013\u2014]", piece)]
        if len(ends) == 2:
            first, last = (_BASE.match(end) for end in ends)
            if first and last and first.group(1) == last.group(1):
                width = len(first.group(2))
                out.extend(
                    f"{first.group(1)}{number:0{width}d}"
                    for number in range(int(first.group(2)), int(last.group(2)) + 1)
                )
                continue
        if _BASE.match(piece):
            out.append(piece)
    return out


def parse_cast(bible: str) -> tuple[CastEntry, ...]:
    """The `### ` headings of the bible's § 3, with the slot numbers they name."""
    out: list[CastEntry] = []
    inside = False
    for line in bible.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 2:
            inside = match.group(2).strip().startswith("3.")
        elif match and len(match.group(1)) == 3 and inside:
            heading = match.group(2).strip()
            slot = _SLOT.search(heading)
            slots = tuple(int(part) for part in slot.group(1).split(",")) if slot else ()
            out.append(CastEntry(heading, slots))
    return tuple(out)


# --- the flow graph, in words -------------------------------------------------------------------

_CONDITION = re.compile(
    r"opt(\d+)|cancel|lflag(==|>=|<=|!=)(\d+)|flag\[(\d+)\](==|>=|<=|!=)(\d+)"
    r"|map(==|!=)([A-Z]\d+)|day'?([<>=]+)(\d+)|hour'?([<>=]+)(\d+)|R(==|>=)(\d+)"
)
_COMPARISON = {"==": "is", ">=": "is at least", "<=": "is at most", "!=": "is not"}


def condition_in_words(condition: str, flags: Mapping[int, str]) -> str:
    """One edge condition as a sentence. The symbolic form is always shown beside it."""
    return _in_words(condition, flags, " -- or -- ") if condition else ""


def _split_top(text: str, separator: str) -> list[str]:
    """`text` split on `separator` wherever it stands outside every parenthesis."""
    parts, depth, start = [], 0, 0
    for index, character in enumerate(text):
        depth += {"(": 1, ")": -1}.get(character, 0)
        if character == separator and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    return [*parts, text[start:]]


def _unwrap(text: str) -> str:
    """`text` without the parentheses that enclose all of it, however many pairs."""
    text = text.strip()
    while text.startswith("(") and _closing(text) == len(text) - 1:
        text = text[1:-1].strip()
    return text


def _closing(text: str) -> int:
    """Where the parenthesis that opens `text` closes, or -1."""
    depth = 0
    for index, character in enumerate(text):
        depth += {"(": 1, ")": -1}.get(character, 0)
        if depth == 0:
            return index
    return -1


def _in_words(expression: str, flags: Mapping[int, str], either: str = " or ") -> str:
    """`|` over `&` over terms, each split only at its own depth: a group inside a clause
    reads as a parenthesised group, `a and (b or c)`, never as a third clause."""
    expression = _unwrap(expression)
    clauses = _split_top(expression, "|")
    if len(clauses) > 1:
        return either.join(_in_words(clause, flags) for clause in clauses)
    terms = _split_top(expression, "&")
    if len(terms) == 1:
        return _term_in_words(expression, flags)
    words: list[str] = []
    matched = ((term, _OFF_MAP.fullmatch(_unwrap(term))) for term in terms)
    for off_map, group in groupby(matched, key=lambda pair: pair[1] is not None):
        run = list(group)
        if off_map and len(run) > 1:
            maps = ", ".join(match.group(1) for _, match in run)
            words.append(f"the player is on none of maps {maps}")
            continue
        for term, _ in run:
            several = len(_split_top(_unwrap(term), "|")) > 1
            words.append(f"({_in_words(term, flags)})" if several else _in_words(term, flags))
    return " and ".join(words)


_OFF_MAP = re.compile(r"map!=([A-Z]\d+)")
"""One `map!=` test: a run of them in a conjunction reads as one phrase (`E0710` named
eight maps the player is not on in each of twenty conditions)."""


def _term_in_words(term: str, flags: Mapping[int, str]) -> str:
    match = _CONDITION.fullmatch(term)
    if match is None:
        return term
    if match.group(1) is not None:
        return f"the player chose option {int(match.group(1)) + 1}"
    if term == "cancel":
        return "the player cancelled"
    if match.group(2):
        return f"this event's own progress counter {_COMPARISON[match.group(2)]} {match.group(3)}"
    if match.group(4):
        number = int(match.group(4))
        name = f" ({flags[number]})" if number in flags else ""
        return f"story flag {number}{name} {_COMPARISON[match.group(5)]} {match.group(6)}"
    if match.group(7):
        # The place is in the event's map legend, not here: `E0710` tests eight maps in
        # three hundred conditions, and naming each place in each was 45 KB of packet.
        return f"the player is{'' if match.group(7) == '==' else ' not'} on map {match.group(8)}"
    if match.group(9):
        return f"the day {_COMPARISON.get(match.group(9), match.group(9))} {match.group(10)}"
    if match.group(11):
        return f"the hour {_COMPARISON.get(match.group(11), match.group(11))} {match.group(12)}"
    if match.group(13):
        return f"a random draw {_COMPARISON[match.group(13)]} {match.group(14)}"
    return term


# --- the policy text a translator is handed -------------------------------------------------------

_PLAN_IDS = r"`[A-Z]+-\d+`(?:\s*(?:,|/|and|\u2013)\s*`[A-Z]+-\d+`)*"
_PLAN_CITATION = re.compile(rf"\s*\(PLAN {_PLAN_IDS}\)|\s*PLAN {_PLAN_IDS}")


def without_plan_citations(text: str) -> str:
    """`text` less its `(PLAN `TRN-01`)` and `PLAN `TRN-08``: the one thing taken out of a
    policy document handed over whole (Jay's drop list, `TRN-08`)."""
    return _PLAN_CITATION.sub("", text)


def document_body(text: str) -> str:
    """A policy document as the translator is handed it: whole, less its own title line."""
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def format_section(readme: str) -> str:
    """`translation/days/README.md` § Format, the day-file format as the translator reads it."""
    body = next(
        (lines for heading, lines in markdown_sections(readme, 2) if heading == FORMAT_SECTION), []
    )
    return "\n".join(body).strip()


# --- one line of the script, in the day-file shape ------------------------------------------------

LABEL_OF = {name: label for label, name in LABEL_NAMES.items() if label}
"""Store speaker name -> the Japanese label the sheet draws (`boku.events.LABEL_NAMES`,
inverted), for a chorus: its members are named on no screen, so the packet spells them as
the labels they would have had."""


def scene_line_ids(scene: dict) -> list[str]:
    """Every line id the scene carries, voice-only ones included, in message order.

    Message order, not the extract's `play_order`: that walks one visit's flow graph, and a
    scene the game re-enters after a map change (`E0107`: `.0`, a move, then `.1` on the
    new map and `.2` on a later visit) comes out `.0, .2, .1`. The branch section says
    which way the flow goes. One list for the packet's template and for the check on a
    translator's answer, so the two cannot disagree about which ids an event is.
    """
    named = (node["line"] for node in scene["nodes"] if node.get("line"))
    ids = dict.fromkeys([*scene["lines"], *named])
    return sorted(ids, key=lambda line_id: int(line_id.rsplit(".", 1)[1]))


def _unindent(column: Sequence[str]) -> list[str]:
    """A column without the authoring tool's one-cell indent."""
    cells = list(column)
    return cells[1:] if cells[:1] == [IDEOGRAPHIC_SPACE] else cells


def _split_label(column: Sequence[str], opening: str) -> tuple[list[str], list[str]]:
    """Page 1's first column as `(the label, the text after the opening mark)`."""
    cells = list(column)
    if opening not in cells:
        return [], cells
    at = cells.index(opening)
    return cells[:at], cells[at + 1 :]


def japanese_speaker(record: dict, japanese: Japanese, marks: Marks) -> str:
    """What goes in the speaker column before translation: the label as the Japanese draws it.

    A labelled message gives its own label (`おば`), which the translator turns into the
    English label with the glossary. A chorus is drawn unlabelled and named here by its
    members' labels. Narration and a message nobody speaks carry the day-file conventions
    `Narrator` and `(unlabelled)` (`translation/days/README.md` § Format), which are
    already English.
    """
    if marks.labelled and japanese.pages and japanese.pages[0]:
        return "".join(_split_label(japanese.pages[0][0], marks.opening)[0])
    label = (record.get("speaker") or {}).get("label") or ""
    if "+" in label:
        return ", ".join(LABEL_OF.get(member, member) for member in label.split("+"))
    if marks.opening == "『":
        return "Narrator"
    return "(unlabelled)"


_GLYPH_TOKEN = re.compile(r"\{G:(\d+)\}")


def japanese_text(japanese: Japanese, marks: Marks) -> str:
    """The line with only its page breaks marked: ` // ` between pages, as the day file.

    The label and the opening mark come off page 1, the closing mark off the last page, and
    each continuation column loses its authoring indent. A page's columns are joined with
    one ideographic space -- Japanese punctuates with spaces and line ends, so a column end
    is not nothing -- and the column structure itself is not shown (Jay, `TRN-08`).
    """
    pages: list[str] = []
    for number, page in enumerate(japanese.pages):
        columns: list[str] = []
        for index, column in enumerate(page):
            if number == 0 and index == 0 and marks.opening:
                cells = _split_label(column, marks.opening)[1]
            else:
                cells = _unindent(column)
            columns.append("".join(cells))
        pages.append(IDEOGRAPHIC_SPACE.join(column for column in columns if column))
    if marks.closing and pages and pages[-1].endswith(marks.closing):
        pages[-1] = pages[-1][: -len(marks.closing)]
    return SampleScenes.PAGE_BREAK.join(pages)


def select_text(japanese: Japanese, shape: tuple[int, int]) -> str:
    """A choice menu's fields, ` | `-separated: the question first when the box has one."""
    options, prompts = shape
    fields = ["".join(_unindent(column)) for page in japanese.pages for column in page]
    fields = [text for text in fields if text][: options + prompts]
    return SampleScenes.OPTION.join(fields)


_CAST_TAIL = re.compile(r"(?:\s—\s|;\s*)slots?\s.*$")
"""A bible cast heading's `— slot 0, label ボク, 742 lines` / `; slot 1, …` tail: the
bible, whole in `system.md`, carries it; a part names who is there."""

DINING_ROOM = "G02"
"""The base meals are eaten at (bible § 7)."""
BREAKFAST_ENDS = 12
"""Breakfast is at 7 and dinner at 18 (bible § 2): a meal hour before noon is breakfast."""

_MAP_NAMED = re.compile(r"(?:map[=!]=|MAP:)([A-Z]\d+)")


def _step(node: dict) -> str:
    """One node of the flow as the translator can place it: the line it shows, or what it
    does -- a move to another map, or another step with no text."""
    if node.get("line"):
        return f"`{node['line']}`"
    move = re.search(r"MAP:([A-Z]\d+)", node["node"])
    if move:
        return f"the move to map {move.group(1)}"
    return f"a {node.get('opcode', 'silent')} step with no text"


def _day_text(scene: dict) -> str:
    """The day the data fixes the scene to, or that none does.

    The data dates an event by its id, and that day is the only day it fires on. A
    `day==N` inside the entry condition is not that -- it is one test among the rest,
    routinely one branch of an `|` whose sibling covers the other days -- so the day is
    left open and the test is named (`script_store.scene_day`, `scene_dated_day`).
    """
    day, derived = scene_day(scene)
    if day is None:
        return "any day (day-independent)"
    if not derived:
        return f"day {day}"
    return f"any day the condition allows -- its `day=={day}` is one test among the rest"


# --- the packet builder --------------------------------------------------------------------------


@dataclass
class PacketBuilder:
    """Everything a run needs, so a part is one call and two runs are identical."""

    store: Store
    policy: Policy
    english: dict[str, list[Row]] = field(default_factory=dict)
    for_review: bool = False
    format_text: str = ""
    documents: tuple[tuple[str, str], ...] = ()
    """`(heading, text)` of each policy document handed over whole, in order."""
    file_order: dict[str, list[str]] = field(default_factory=dict)
    """Each translation file's events, in its order: where a scene's neighbours are."""
    held: dict[str, str] = field(default_factory=dict)
    """Line id -> the name of the translation file that holds its row."""
    sequence: Mapping[str, int] = field(default_factory=dict)
    """Event -> its place in a play-order unit (`--game`); empty for any other unit."""
    table: GlyphTable = field(default_factory=GlyphTable.load)
    voice_only: Mapping[str, str] = field(default_factory=voice_only_gists)

    @classmethod
    def build(
        cls, store: Store, policy: Policy, translations: Sequence[Path], for_review: bool
    ) -> PacketBuilder:
        rows, _ = load_rows(translation_paths(translations))
        english: dict[str, list[Row]] = {}
        file_order: dict[str, list[str]] = {}
        held: dict[str, str] = {}
        for row in rows:
            if row.has_english:
                english.setdefault(row.line_id, []).append(row)
            held.setdefault(row.line_id, row.file)
            event = store.event_of_line.get(row.line_id)
            events = file_order.setdefault(row.file, [])
            if event and event not in events:
                events.append(event)
        return cls(
            store=store,
            policy=policy,
            english=english,
            for_review=for_review,
            format_text=format_section(_read(DAYS_DIR / "README.md")),
            documents=tuple(
                (heading, without_plan_citations(document_body(_required(TRANSLATION_DIR / name))))
                for heading, name in POLICY_DOCUMENTS
            ),
            file_order=file_order,
            held=held,
        )

    def target_file(self, key: str) -> str:
        """The translation file a part's answer is saved into -- `default_day_file`'s
        answer, from the rows this builder read rather than a re-read per part."""
        names = sorted({self.held[i] for i in part_line_ids(self.store, key) if i in self.held})
        return names[0] if names else conventional_file(self.store, key)

    # --- the template: what the translator returns ------------------------------------------

    def row(self, line_id: str) -> str:
        """One line as a day-file row, the Japanese standing where the English will go."""
        record = self.store.lines.get(line_id)
        if record is None:
            return f"{line_id}\t{SampleScenes.VOICE_ONLY}"
        japanese = self.store.japanese[line_id]
        shape = select_shape(record)
        if shape is None and is_array_select(record):
            shape = (menu_lines(original_bytes(record, self.table)), 0)
        if shape is not None:
            return f"{line_id}\t{SampleScenes.SELECT}\t{select_text(japanese, shape)}"
        if is_array(record) or record["kind"] in PLACED_BY_CODE:
            text = japanese_text(japanese, Marks("", "", labelled=False))
            return f"{line_id}\t(unlabelled)\t{text}"
        marks = original_marks(original_bytes(record, self.table), self.table)
        speaker = japanese_speaker(record, japanese, marks)
        return f"{line_id}\t{speaker}\t{japanese_text(japanese, marks)}"

    def places(self, scene: dict) -> str:
        """`G03 -- kitchen (...)`: each base the scene is placed on, and what the bible calls
        it -- once for the bases that share it (`I36, I37 -- single-purpose close-ups`)."""
        by_place: dict[str, list[str]] = {}
        for base in scene["where"]["bases"]:
            by_place.setdefault(self.policy.place(base), []).append(base)
        return "; ".join(
            f"{', '.join(bases)} -- {place}" if place else ", ".join(bases)
            for place, bases in by_place.items()
        )

    def header(self, scene: dict) -> str:
        """`# --- E0121: G03 -- kitchen (...)`, the line that opens the event's block."""
        return f"{EVENT_HEADER}{scene['event']}: {self.places(scene) or 'place unknown'}"

    def block(self, header: str, line_ids: Iterable[str]) -> list[str]:
        """A part's answer block: its header, then one row per line."""
        return [header, *(self.row(line_id) for line_id in line_ids)]

    def template(self, scene: dict) -> list[str]:
        return self.block(self.header(scene), scene_line_ids(scene))

    def surface_header(self, surface: Surface) -> str:
        """`# --- exe@8003D2E0: insect names`, the line that opens a surface's block."""
        return f"{EVENT_HEADER}{surface.key}: {self.describe(surface)}"

    def describe(self, surface: Surface) -> str:
        """What the surface is, in the extract's words less its glyph and cell counts."""
        record = self.store.lines[surface.line_ids[0]]
        purpose = record.get("purpose") or SURFACE_KINDS.get(record["kind"], "")
        purpose = _CAPACITY.sub("", _DRAW_FUNCTION.sub("", purpose))
        return re.sub(r"\s+([,;])", r"\1", purpose).strip(" ,") or surface.key

    def surface_part(self, surface: Surface, position: int, total: int, heading: str = "") -> str:
        """One surface as the translator is handed it: what it is, then its block."""
        kind = self.store.lines[surface.line_ids[0]]["kind"]
        block = self.block(self.surface_header(surface), surface.line_ids)
        out = [
            heading or f"# {surface.key} -- surface {position} of {total}",
            "",
            f"* **What it is**: {self.describe(surface)}",
            f"* **How it is drawn**: {SURFACE_KINDS.get(kind, kind)}",
        ]
        if any(mark in row for row in block[1:] for mark in "「」『』"):
            out.append(
                "* The brackets in these lines are part of the text, not speech marks the "
                "program adds: keep them."
            )
        out += [
            "",
            "## Your answer",
            "",
            "```text",
            *block,
            "```",
            "",
            *self.glyph_notes(block),
        ]
        if self.for_review:
            out += self._current(surface.line_ids)
        return "\n".join(out).rstrip() + "\n"

    def glyph_notes(self, rows: Iterable[str]) -> list[str]:
        """What each `{G:n}` in these rows draws, from the glyph table. The token names the
        exact cell -- two cells can draw one character (`{G:22}` and `{G:1456}` are both a
        closing parenthesis), and a button is a picture -- so it is explained, not replaced."""
        cells = sorted({int(n) for row in rows for n in _GLYPH_TOKEN.findall(row)})
        return [
            f"* `{{G:{n}}}` is one cell of the game's font that draws "
            f"{self.table.characters.get(n) or 'something undescribed'} "
            f"(`research/data/glyph-table.tsv`): punctuation becomes the English mark; a "
            f"button or a picture stays as the token."
            for n in cells
        ]

    @cached_property
    def _by_clip(self) -> dict[str, list[str]]:
        """Clip -> every line that plays it. Two events that play one recording are one line
        seen twice (`E0173.0` / `E0174.0`, a camera cut), so their English is one."""
        clips: dict[str, list[str]] = {}
        for line_id, record in self.store.lines.items():
            clip = (record.get("voice") or {}).get("clip")
            if clip:
                clips.setdefault(clip, []).append(line_id)
        return clips

    def _played_at(self, line_id: str) -> tuple[int, int] | None:
        """Where a line is given in a play-order unit: its event's place, then its index."""
        place = self.sequence.get(self.store.event_of_line.get(line_id, ""))
        return None if place is None else (place, int(line_id.rsplit(".", 1)[1]))

    def same_recording(self, scene: dict) -> list[str]:
        """For each line that replays a recording another line plays, those other lines --
        never the clip id (Jay, 2026-09-23: no voice-clip references). In a play-order unit
        only the first playing given earlier is named: the translator has answered it, and
        the breakfast chorus alone replays one recording seventeen times."""
        by_clip = self._by_clip
        out = []
        for line_id in scene_line_ids(scene):
            clip = ((self.store.lines.get(line_id) or {}).get("voice") or {}).get("clip")
            others = [other for other in by_clip.get(clip, ()) if other != line_id]
            mine = self._played_at(line_id)
            if mine is not None:
                earlier = [(at, o) for o in others if (at := self._played_at(o)) and at < mine]
                others = [min(earlier)[1]] if earlier else []
            if others:
                named = ", ".join(f"`{other}`" for other in others)
                out.append(f"`{line_id}` is the same recording as {named}")
        return out

    # --- the system part ------------------------------------------------------------------

    def system_part(self, unit: Unit) -> str:
        title = unit.title
        noun = "part" if unit.scenes and unit.surfaces else "event" if unit.scenes else "surface"
        order = (
            " in the order the game plays them, each day's first part saying that the day "
            "begins, and after the last day the menus, books and screens"
            if unit.placed
            else ""
        )
        out = [
            f"# Translating {title}",
            "",
            f"You are translating {title} of *Boku no Natsuyasumi* (PlayStation, 2000) from "
            f"Japanese into English, one {noun} at a time: {len(unit.keys)} {noun}s{order}. "
            f"This part is the policy, given once; each {noun} then comes as its own message. "
            f"For each, answer with its block -- the lines under **Your answer** -- with the "
            f"Japanese replaced by English and the speaker column in English, in the "
            f"day-file format below, and nothing else. The Japanese speaker labels become "
            f"the English labels of the glossary and style guide § 9. Your earlier answers "
            f"stay in view: keep a voice, a recurring phrase and a name the same across "
            f"them. You may later be asked to revise an earlier {noun} in the light of what "
            f"came after it; answer with its whole block again. The documents below are the "
            f"project's own, whole: the story bible is what is known about the game, and the "
            f"style guide and the glossary are settled and binding.",
            "",
            "# The day-file format",
            "",
            self.format_text,
            "",
        ]
        for heading, text in self.documents:
            out += [f"# {heading}", "", text, ""]
        return "\n".join(out).rstrip() + "\n"

    # --- one event --------------------------------------------------------------------------

    def event_part(
        self,
        scene: dict,
        position: int,
        total: int,
        unit_events: frozenset[str] = frozenset(),
        heading: str = "",
    ) -> str:
        """One event as the translator is handed it. `unit_events` are the events of the
        same run: the translator has their answers in view already, so a neighbour among
        them is not shown -- and in a re-translation its English as it stands is the draft
        being replaced. `heading` replaces the default title (`Unit.headings`)."""
        event = scene["event"]
        template = self.template(scene)
        out = [heading or f"# {event} -- event {position} of {total}", ""]
        out += self.setting(scene)
        out += self._neighbours(scene, unit_events)
        out += [
            "## Your answer",
            "",
            "```text",
            *template,
            "```",
            "",
            *self.glyph_notes(template),
        ]
        if self.for_review:
            out += self._current(scene_line_ids(scene))
        return "\n".join(out).rstrip() + "\n"

    def setting(self, scene: dict) -> list[str]:
        """Where, when and who, the branches, the maps named and the per-day table: what the
        translator is told about a scene before its lines, as Markdown -- and what the
        reader (`boku.reader`) shows above them."""
        return [
            *self._where(scene),
            *self._branches(scene),
            *self._maps(scene),
            *self._quiz(scene, scene_dated_day(scene)),
        ]

    def _where(self, scene: dict) -> list[str]:
        hour = scene_hour(scene)
        slots = scene["where"]["time_slots"]
        when = [_day_text(scene)]
        if hour is not None:
            when.append(f"from {hour}:00")
            meal = scene["when"]["meal_hour"]
            if meal is not None and DINING_ROOM in scene["where"]["bases"]:
                when.append("breakfast" if meal < BREAKFAST_ENDS else "dinner")
        elif slots:
            when.append(f"time slot(s) {slots}")
        condition = scene["when"]["condition"]
        if condition:
            when.append(f"when {condition_in_words(condition, self.policy.flags)}")
        places = self.places(scene)
        slots = {member["slot"] for member in scene["cast"]} | {
            speaker["slot"]
            for line_id in scene_line_ids(scene)
            if (speaker := (self.store.lines.get(line_id) or {}).get("speaker") or {}).get("slot")
            is not None
        }
        who = [
            _CAST_TAIL.sub("", entry.heading)
            + (
                " (here: "
                + ", ".join(
                    LABEL_OF.get(CHARACTERS[slot], CHARACTERS[slot])
                    for slot in entry.slots
                    if slot in slots
                )
                + ")"
                if len(entry.slots) > 1 and all(slot in CHARACTERS for slot in entry.slots)
                else ""
            )
            for entry in self.policy.cast_for(slots)
        ]
        out = [
            f"* **Where**: {places or 'unknown'}",
            f"* **When**: {'; '.join(when)}",
        ]
        if who:
            out.append(f"* **Who is here**: {'; '.join(who)}")
        replayed = self.same_recording(scene)
        if replayed:
            out.append(
                f"* **One recording, two lines**: {'; '.join(replayed)}: keep the English identical"
            )
        heard = [
            f"`{line_id}` {self.voice_only[line_id]}"
            for line_id in scene_line_ids(scene)
            if line_id in self.voice_only
        ]
        if heard:
            out.append(
                f"* **Heard with no text** (the `(voice only)` rows; our gist, in English): "
                f"{'; '.join(heard)}"
            )
        onward = dict.fromkeys(
            handover["event"]
            for handover in scene.get("handovers") or []
            if handover.get("event") not in (None, scene["event"])
            and handover.get("reachable", True)
        )
        if onward:
            out.append(f"* **Then**: the game moves on to {', '.join(f'`{e}`' for e in onward)}")
        out.append("")
        return out

    def _branches(self, scene: dict) -> list[str]:
        """The scene's forks, in words. A linear scene has none and gets no section.

        A fork is a node with more than one way on -- a choice menu's options, or edges
        that test a condition. Each target is named by the line it opens, which is how
        the translator sees the scene in the block below.
        """
        nodes = {node["node"]: node for node in scene["nodes"]}
        edges: dict[str, list[dict]] = {}
        for edge in scene["edges"]:
            edges.setdefault(edge["from"], []).append(edge)
        forks: list[str] = []
        for source in ["ENTRY", *(node["node"] for node in iter_play_order(scene))]:
            outgoing = edges.get(source, [])
            if len(outgoing) < 2:
                continue
            where = "At the start" if source == "ENTRY" else f"After {_step(nodes[source])}"
            forks.append(f"* {where}:")
            for edge in outgoing:
                target = edge["to"]
                goes = (
                    "the event ends"
                    if target == "END"
                    else f"{_step(nodes[target])} comes next"
                    if target in nodes
                    else f"`{target}` comes next"
                )
                words = condition_in_words(edge["condition"], self.policy.flags)
                forks.append(f"  * {goes}" + (f" when {words}" if words else ""))
        if not forks:
            return []
        return ["## Where the scene branches", "", *forks, ""]

    def _maps(self, scene: dict) -> list[str]:
        """The places behind every map a condition or a move in this event names, less
        the ones **Where** already describes."""
        text = " ".join(
            [scene["when"]["condition"] or "", *(e["condition"] or "" for e in scene["edges"])]
            + [node["node"] for node in scene["nodes"]]
        )
        bases = sorted(set(_MAP_NAMED.findall(text)) - set(scene["where"]["bases"]))
        legend = [f"* {base} -- {place}" for base in bases if (place := self.policy.place(base))]
        return ["## The maps named above", "", *legend, ""] if legend else []

    def _quiz(self, scene: dict, day: int | None) -> list[str]:
        quiz = scene.get("dinner_quiz")
        if not quiz:
            return []
        name, rows = next(
            (
                (key, value)
                for key, value in quiz.items()
                if isinstance(value, list) and value and isinstance(value[0], dict)
            ),
            ("", []),
        )
        if not rows:
            return []
        event = scene["event"]
        out = [
            f"## The per-day {name}",
            "",
            "The game picks one of this event's messages by day, so a line here is **day d's "
            "question** and not a general one -- translate it knowing which day it is asked on.",
            "",
            "| " + " | ".join(rows[0]) + " | line |",
            "|" + "---|" * (len(rows[0]) + 1),
        ]
        for row in rows:
            cells = " | ".join(str(row.get(column, "")) for column in rows[0])
            out.append(f"| {cells} | `{event}.{row.get('message')}` |")
        asked = {row.get("message") for row in rows}
        unasked = [
            line_id
            for line_id in scene_line_ids(scene)
            if int(line_id.rsplit(".", 1)[1]) not in asked
            and select_shape(self.store.lines.get(line_id) or {"kind": ""}) is not None
        ]
        if unasked:
            out += [
                "",
                f"No day's row names {', '.join(f'`{u}`' for u in unasked)}: the table in the "
                f"program never asks it, so it is translated for completeness only.",
            ]
        if day is not None:
            mine = [row for row in rows if row.get("day") == day]
            if mine:
                out += [
                    "",
                    f"On day {day} this event asks `{event}.{mine[0].get('message')}`"
                    + (
                        f", answer index {mine[0]['answer']}"
                        if mine[0].get("answer") is not None
                        else ""
                    )
                    + ".",
                ]
        out.append("")
        return out

    @cached_property
    def _dated(self) -> dict[int, list[str]]:
        """Day -> the events the data dates to it, in the project's order."""
        out: dict[int, list[str]] = {}
        for scene in ordered_scenes(self.store):
            day = scene_dated_day(scene)
            if day is not None:
                out.setdefault(day, []).append(scene["event"])
        return out

    def neighbours(self, scene: dict) -> tuple[dict | None, dict | None]:
        """The events either side of this one: in the day file that already holds it, in
        that file's order (a day file is in the order its day plays); else, for an event the
        data dates, the events dated to that day in the project's order. Anything else has
        none: the project's order sorts undated events by hour alone, which put a breakfast
        chorus beside the watermelon thief (`E0405`), and `shared.txt` is ordered by place."""
        event, by_event = scene["event"], self.store.scenes_by_event
        held = [
            events
            for name, events in sorted(self.file_order.items())
            if _DAY_FILE.fullmatch(Path(name).stem) and event in events
        ]
        if held:
            events = held[0]
        elif (day := scene_dated_day(scene)) is not None:
            events = self._dated[day]
        else:
            return None, None
        others = [e for e in events if e == event or has_text(by_event[e])]
        index = others.index(event)
        before = by_event[others[index - 1]] if index else None
        after = by_event[others[index + 1]] if index + 1 < len(others) else None
        return before, after

    def settled(self, scene: dict) -> list[str]:
        """A scene's English as it stands, as day-file rows."""
        return [
            f"{line_id}\t{row.speaker}\t{row.text}"
            for line_id in scene_line_ids(scene)
            for row in self.english.get(line_id, [])
        ]

    def _neighbours(self, scene: dict, unit_events: frozenset[str]) -> list[str]:
        out: list[str] = []
        previous, following = self.neighbours(scene)
        for title, other in (("before", previous), ("after", following)):
            if other is None or other["event"] in unit_events:
                continue
            settled = self.settled(other)
            out += [f"## The scene {title} this one: `{other['event']}`", ""]
            if settled:
                out += [
                    "Its English as it stands; match the voices and keep a recurring phrase "
                    "identical.",
                    "",
                    "```text",
                    *settled,
                    "```",
                    "",
                ]
            else:
                out += ["Not translated yet.", ""]
        return out

    def _current(self, line_ids: Iterable[str]) -> list[str]:
        """`--for-review`: the English as it stands, with its notes, for the reviewer."""
        rows = [row for line_id in line_ids for row in self.english.get(line_id, [])]
        if not rows:
            return ["## The English as it stands", "", "None written yet.", ""]
        out = ["## The English as it stands", "", "```text"]
        for row in rows:
            out += [f"# {note}" for note in row.notes]
            out.append("\t".join(part for part in (row.line_id, row.speaker, row.text) if part))
        return [*out, "```", ""]


# --- a unit: what one directed translator is given ------------------------------------------------


@dataclass(frozen=True)
class Surface:
    """One screen or list outside the events (`PLAN TRN-09`): an array, a menu held in a code
    file, a label assembled in code -- every line the store holds under one key."""

    key: str
    """The array's own id (`exe@8003D2E0`), or the line's for a one-line surface."""
    line_ids: tuple[str, ...]


@dataclass(frozen=True)
class Unit:
    """What one run of the translator covers, and what to call it."""

    name: str
    """The directory under `work/packets/`: `day08`, `shared`, `events`, `arrays`."""
    title: str
    day: int | None
    scenes: tuple[dict, ...]
    surfaces: tuple[Surface, ...] = ()
    placed: Mapping[str, int] = field(default_factory=dict)
    """A play-order unit's (`unit_of_game`): event -> the day it is given under. Empty for
    every other unit, whose parts carry no day marker."""

    @property
    def keys(self) -> list[str]:
        """The parts in the order they are given: events, then surfaces."""
        return [scene["event"] for scene in self.scenes] + [s.key for s in self.surfaces]

    def headings(self) -> list[str]:
        """Each part's title in a play-order unit -- its day and place in the whole -- with
        a marker on the first part of each day and on the first part with no day; `""` (the part's
        default title) for every part of any other unit."""
        keys = self.keys
        if not self.placed:
            return [""] * len(keys)
        out, previous = [], object()
        for position, key in enumerate(keys, start=1):
            day = self.placed.get(key)
            where = f"day {day}" if day is not None else "outside every day"
            title = f"# {key} -- {where}; part {position} of {len(keys)}"
            if day != previous:
                began = (
                    f"**Day {day} begins.**"
                    if day is not None
                    else "**What follows belongs to no day: the part of the game outside the "
                    "story begins here.**"
                )
                title += f"\n\n{began}"
            out.append(title)
            previous = day
        return out

    @property
    def line_ids(self) -> list[str]:
        return [i for scene in self.scenes for i in scene_line_ids(scene)] + [
            i for surface in self.surfaces for i in surface.line_ids
        ]


_DAY_FILE = re.compile(r"day(\d+)$")


def has_text(scene: dict) -> bool:
    """Does the scene carry any line id at all? One with none has nothing to translate."""
    return bool(scene_line_ids(scene))


def part_of(store: Store, line_id: str) -> str:
    """The event a line belongs to, or the surface a non-event line sits on."""
    if line_id in store.event_of_line:
        return store.event_of_line[line_id]
    key = next((key for key, ids in store.surfaces.items() if line_id in ids), None)
    return key or line_id.split(".", 1)[0]


def surfaces_of(store: Store) -> list[Surface]:
    """Every line no event claims, grouped by surface (`Store.surfaces`)."""
    return [Surface(key, ids) for key, ids in store.surfaces.items()]


def unit_of_surfaces(store: Store) -> Unit:
    """`TRN-09`: the menus, books, labels and screens -- `translation/days/arrays.txt`."""
    return Unit("arrays", "the menus, books and screens", None, (), tuple(surfaces_of(store)))


def unit_of_day(store: Store, day: int) -> Unit:
    """The events the data dates to `day`, in play order: a new day file's scope.

    A day-independent event the day can reach belongs in `shared.txt`, so that each event is
    translated once (`translation/days/README.md` § shared.txt); `main_packet` names the
    ones no file has English for yet, and `--events` builds them a packet of their own. A
    day file already written may hold some too (`day01.txt` holds `E0001`, the narration
    its day hands over to), which is why a re-translation uses `unit_like`, not this.
    """
    scenes = [s for s in scenes_of_day(store, day) if scene_dated_day(s) == day and has_text(s)]
    return Unit(f"day{day:02d}", f"day {day}", day, tuple(scenes))


def unit_like(store: Store, path: Path) -> Unit:
    """Exactly the events (or surfaces) a translation file holds, in that file's order.

    What a re-translation needs: `--like translation/days/day01.txt` is day 1 as the held
    draft scoped it, `E0001` and all, so the new draft and the old compare line for line.
    """
    path = Path(path)
    rows, _ = parse_file(path)
    keys = dict.fromkeys(part_of(store, row.line_id) for row in rows)
    by_event = store.scenes_by_event
    match = _DAY_FILE.fullmatch(path.stem)
    day = int(match.group(1)) if match else None
    title = f"day {day}" if day is not None else f"the lines of {path.name}"
    return Unit(
        path.stem,
        title,
        day,
        tuple(by_event[key] for key in keys if key in by_event and has_text(by_event[key])),
        tuple(Surface(key, store.surfaces[key]) for key in keys if key in store.surfaces),
    )


def unit_of_events(store: Store, events: Sequence[str]) -> Unit:
    scenes = tuple(scene for scene in scenes_named(store, events) if has_text(scene))
    days = {scene_dated_day(scene) for scene in scenes}
    day = days.pop() if len(days) == 1 else None
    return Unit("events", f"events {', '.join(s['event'] for s in scenes)}", day, scenes)


def first_day(scene: dict) -> int | None:
    """The day a play-order unit gives the scene under: the day the data dates it to; else
    the day its id names (`E<day><nn>`, `translation/days/README.md`) when its condition
    lets that day play it -- `E1006`, the satellite, tests flags and no day, so the first
    day its condition allows is day 1; else the first day of the month that can reach it
    (`scene_plays_on`), which is right for the ever-present `E4xxx`-`E8xxx`; else `None`."""
    dated = scene_dated_day(scene)
    if dated is not None:
        return dated
    named = scene["id"] // 100
    if named in MONTH and scene_plays_on(scene, named):
        return named
    return next((day for day in MONTH if scene_plays_on(scene, day)), None)


def unit_of_game(store: Store, builder: PacketBuilder) -> Unit:
    """Every event with text, day by day through the month, then every surface.

    Within a day: the events its day file holds, in that file's order (a day file is the
    day as played, hand-ordered and reviewed); then the rest the day owns, in the project's
    order, dated ones first. An event a day file holds is given under that day; any other
    under `first_day`. An event no day reaches (none, 2026-09-23) comes after day 31, under
    the same no-day marker as the surfaces.
    """
    scenes = [scene for scene in ordered_scenes(store) if has_text(scene)]
    placed: dict[str, int | None] = {}
    for name, events in sorted(builder.file_order.items()):
        match = _DAY_FILE.fullmatch(Path(name).stem)
        for event in events if match else ():
            placed.setdefault(event, int(match.group(1)))
    for scene in scenes:
        placed.setdefault(scene["event"], first_day(scene))
    order: list[str] = []
    for day in [*MONTH, None]:
        held = builder.file_order.get(f"day{day:02d}.txt", []) if day is not None else []
        ours = dict.fromkeys(event for event in held if placed.get(event) == day)
        ours.update(dict.fromkeys(s["event"] for s in scenes if placed[s["event"]] == day))
        order += ours
    by_event = store.scenes_by_event
    texted = {scene["event"] for scene in scenes}
    order = [event for event in order if event in texted]
    return Unit(
        GAME_NAME,
        "the whole game",
        None,
        tuple(by_event[event] for event in order),
        tuple(surfaces_of(store)),
        {event: day for event, day in placed.items() if day is not None and event in texted},
    )


def write_unit(builder: PacketBuilder, unit: Unit, out_dir: Path) -> list[Path]:
    """`system.md`, one `<KEY>.md` per event or surface, and `order.txt`. Deterministic.

    The directory is emptied of earlier parts first, so a stale part from another run is
    never mistaken for part of this one.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.md"):
        stale.unlink()
    if unit.placed:
        builder = replace(builder, sequence={key: at for at, key in enumerate(unit.keys)})
    written: list[Path] = []
    system = out_dir / SYSTEM_NAME
    system.write_text(builder.system_part(unit), encoding="utf-8")
    written.append(system)
    total = len(unit.keys)
    events = frozenset(scene["event"] for scene in unit.scenes)
    headings = unit.headings()
    parts = [
        *(
            builder.event_part(scene, position, total, events, headings[position - 1])
            for position, scene in enumerate(unit.scenes, start=1)
        ),
        *(
            builder.surface_part(surface, position, total, headings[position - 1])
            for position, surface in enumerate(unit.surfaces, start=len(unit.scenes) + 1)
        ),
    ]
    for key, part in zip(unit.keys, parts, strict=True):
        path = out_dir / part_file(key)
        path.write_text(part, encoding="utf-8")
        written.append(path)
    order = out_dir / ORDER_NAME
    order.write_text(
        "".join(f"{key}\t{builder.target_file(key)}\n" for key in unit.keys), encoding="utf-8"
    )
    written.append(order)
    return written


def order_keys(text: str) -> list[str]:
    """The part keys of an `order.txt`: the first field of each row."""
    return [line.split("\t", 1)[0].strip() for line in text.splitlines() if line.strip()]


def estimate_tokens(text: str) -> int:
    """A rough token count: one per Japanese character, one per 3.5 of anything else --
    the rule of thumb the packet's size is reported in, not a tokenizer."""
    japanese = len(_JAPANESE.findall(text))
    return round(japanese + (len(text) - japanese) / 3.5)


def part_file(key: str) -> str:
    """A part's file name: its key, with the `:` of `exe@code:80037544` made `_` -- a colon
    is an alternate data stream on NTFS and a `/` in the macOS Finder."""
    return f"{key.replace(':', '_')}.md"


def untranslated_reachable(builder: PacketBuilder, day: int) -> list[str]:
    """Day-independent events `day` can reach that no translation file gives English to."""
    out = []
    for scene in scenes_of_day(builder.store, day):
        if scene_dated_day(scene) is not None:
            continue
        texts = [line_id for line_id in scene_line_ids(scene) if line_id in builder.store.lines]
        if texts and not any(builder.english.get(line_id) for line_id in texts):
            out.append(scene["event"])
    return out


# --- saving a translator's answer -----------------------------------------------------------------

_FENCE = re.compile(r"^```[\w-]*\s*$")
_PART_ID = re.compile(r"\bE\d{4}\b|\b[a-z]+@[\w:]+")
_JAPANESE = re.compile("[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")
"""Kana, kanji, CJK punctuation and the full-width forms: a row still holding any is a
row the translator did not finish."""


def answer_lines(answer: str) -> list[str]:
    """The translator's block: the first fenced block if there is one, else the whole text,
    without surrounding blank lines."""
    lines = answer.splitlines()
    fences = [index for index, line in enumerate(lines) if _FENCE.match(line.strip())]
    if len(fences) >= 2:
        lines = lines[fences[0] + 1 : fences[1]]
    lines = [line.rstrip() for line in lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def part_line_ids(store: Store, key: str) -> list[str]:
    """The line ids an event or a surface is, in the order its packet part lists them."""
    scene = store.scenes_by_event.get(key)
    if scene is not None:
        return scene_line_ids(scene)
    if key not in store.surfaces:
        raise PacketRefused(f"no event or surface in the store is called {key}")
    return list(store.surfaces[key])


def check_answer(key: str, expected: Sequence[str], lines: Sequence[str], where: Path) -> list[str]:
    """Why this answer cannot be saved as the part's block, or nothing.

    Only what the file itself cannot hold is refused here: an id missing, extra or given
    twice, a row or note still in Japanese, a speaker that is not a label. Fit, page counts
    and menus are `boku lint`'s, run over the file afterwards.
    """
    rows, findings = parse_text("\n".join(lines), where)
    problems = [finding.message for finding in findings]
    problems += [
        f"a note still holds Japanese, and the day files hold none: {line!r}"
        for line in lines
        if line.lstrip().startswith("#") and _JAPANESE.search(line)
    ]
    given = Counter(row.line_id for row in rows)
    missing = [line_id for line_id in expected if line_id not in given]
    extra = [line_id for line_id in given if line_id not in expected]
    twice = sorted(line_id for line_id, count in given.items() if count > 1)
    if missing:
        problems.append(f"no row for {', '.join(missing)}")
    if extra:
        problems.append(f"{', '.join(extra)} is not a line of {key}")
    if twice:
        problems.append(f"{', '.join(twice)} given more than once")
    special = {SampleScenes.SELECT, SampleScenes.VOICE_ONLY}
    for row in rows:
        if _JAPANESE.search(row.speaker) or _JAPANESE.search(row.text):
            problems.append(f"{row.line_id} still holds Japanese: {row.speaker!r} {row.text!r}")
            continue
        if row.speaker not in special:
            _, unknown = speaker_label(row.speaker)
            if unknown:
                problems.append(
                    f"{row.line_id}: {', '.join(unknown)} is not a speaker label of the "
                    f"style guide § 9"
                )
    return problems


@dataclass(frozen=True)
class DayFile:
    """A day file cut at its part headers: the preamble, then one block per `# --- ` line.

    Every line is kept as it was, blank ones included, so `text()` of a file read and not
    changed is the file byte for byte: a save rewrites its own block and nothing else, and
    a `#` note keeps the row it sits above (the lint attaches notes by adjacency).
    """

    preamble: tuple[str, ...]
    blocks: tuple[tuple[str, ...], ...]

    @classmethod
    def read(cls, path: Path) -> DayFile:
        path = Path(path)
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        preamble: list[str] = []
        blocks: list[list[str]] = []
        for line in lines:
            if line.startswith(EVENT_HEADER):
                blocks.append([line])
            elif blocks:
                blocks[-1].append(line)
            else:
                preamble.append(line)
        return cls(tuple(preamble), tuple(tuple(block) for block in blocks))

    @staticmethod
    def events_of(block: Sequence[str]) -> list[str]:
        """The events or surfaces a block's header names (`# --- E0173 / E0174: ...` names
        two; `# --- exe@code:80037544: ...` one)."""
        return _PART_ID.findall(block[0][len(EVENT_HEADER) :].split(": ", 1)[0])

    def text(self) -> str:
        lines = [*self.preamble, *(line for block in self.blocks for line in block)]
        return "\n".join(lines) + "\n" if lines else ""


def _trailing_blanks(block: Sequence[str]) -> int:
    return len(block) - len(tuple(dropwhile(lambda line: not line.strip(), reversed(block))))


def _event_rows(text: str, where: Path, ids: set[str]) -> list[str]:
    rows, _ = parse_text(text, where)
    return sorted({row.line_id for row in rows if row.line_id in ids})


def play_order(store: Store) -> list[str]:
    """Every event in the project's order, then every surface: where a part goes in a file
    when no unit order is given."""
    return [scene["event"] for scene in ordered_scenes(store)] + list(store.surfaces)


def _insert_at(blocks: Sequence[Sequence[str]], key: str, order: Sequence[str]) -> int:
    """Where a new block for `key` goes: after the last block of a part `order` puts before
    it, else before the first block of a part it puts after, else at the end. A block of a
    part `order` does not name keeps its place and decides nothing."""
    rank = {part: index for index, part in enumerate(order)}
    mine = rank.get(key)
    if mine is None:
        return len(blocks)
    ranks = [next((rank[e] for e in DayFile.events_of(b) if e in rank), None) for b in blocks]
    before = [i for i, r in enumerate(ranks) if r is not None and r < mine]
    if before:
        return before[-1] + 1
    after = [i for i, r in enumerate(ranks) if r is not None and r > mine]
    return after[0] if after else len(blocks)


def save_event(
    store: Store,
    event: str,
    answer: str,
    into: Path,
    title: str = "",
    order: Sequence[str] | None = None,
) -> str:
    """Write a translator's answer for an event or surface into a day file, as its block.

    The block replaces the one whose header names this part, or goes in at the part's place
    in `order` -- the unit's `order.txt`, else `play_order` -- so a part refused and saved
    later lands where it belongs, and blocks of parts the order does not know keep theirs.
    Nothing else in the file changes.

    Refused, with the file untouched: an answer `check_answer` rejects; a block whose
    header names this part beside others, or that holds another part's rows (both are
    hand-merged blocks, and replacing one would delete the other's English -- split it
    first); rows of this part outside a block of its own; and rows of this part in
    another translation file beside this one, which would translate it twice.
    """
    expected = part_line_ids(store, event)
    into = Path(into)
    lines = answer_lines(answer)
    problems = check_answer(event, expected, lines, into)
    if problems:
        raise PacketRefused(f"{event}: not saved -- " + "; ".join(problems))
    if not lines or not lines[0].startswith(EVENT_HEADER) or event not in DayFile.events_of(lines):
        lines = [f"{EVENT_HEADER}{event}", *lines]
    ids = set(expected)
    for sibling in sorted(into.parent.glob("*.txt")):
        if sibling.resolve() == into.resolve():
            continue
        held = _event_rows(sibling.read_text(encoding="utf-8"), sibling, ids)
        if held:
            raise PacketRefused(
                f"{sibling.name} already translates {', '.join(held)}; saving {event} into "
                f"{into.name} would give it English twice"
            )
    day_file = DayFile.read(into)
    blocks = list(day_file.blocks)
    mine = [i for i, block in enumerate(blocks) if event in DayFile.events_of(block)]
    for index in mine:
        rows, _ = parse_text("\n".join(blocks[index]), into)
        others = sorted({part_of(store, row.line_id) for row in rows} - {event})
        if DayFile.events_of(blocks[index]) != [event] or others:
            raise PacketRefused(
                f"{into.name}: the block of {event} also holds "
                f"{', '.join(others) or 'another part in its header'}; split it so each "
                f"has its own `{EVENT_HEADER}` header, then save again"
            )
    if mine:
        keep = _trailing_blanks(blocks[mine[0]])
        blocks[mine[0]] = (*lines, *([""] * keep))
        for index in reversed(mine[1:]):
            del blocks[index]
    else:
        rest = "\n".join(line for block in blocks for line in block)
        stray = _event_rows(rest, into, ids)
        if stray:
            raise PacketRefused(
                f"{into.name} already holds {', '.join(stray)} outside a block of {event}'s "
                f"own; move them under a `{EVENT_HEADER}{event}` header first"
            )
        at = _insert_at(blocks, event, order if order is not None else play_order(store))
        above = blocks[at - 1] if at else day_file.preamble
        if above and above[-1].strip():
            lines = ["", *lines]
        if at < len(blocks):
            lines = [*lines, ""]
        blocks.insert(at, tuple(lines))
    preamble = day_file.preamble or (f"# {title or into.stem} (translation/days/README.md)",)
    into.parent.mkdir(parents=True, exist_ok=True)
    into.write_text(DayFile(preamble, tuple(blocks)).text(), encoding="utf-8")
    verb = "replaced" if mine else "added"
    return f"save-event: {event} {verb} in {into} ({len(ids)} line(s))"


def default_day_file(store: Store, key: str, directory: Path = DAYS_DIR) -> Path:
    """Where a part's English goes when no `--into` is given: the file that already holds
    it; else an event's dated day's file, `shared.txt` for one with no day, and
    `arrays.txt` for a surface. A day file may hold a day-independent event its day hands
    over to (`day01.txt` holds `E0001`), so the convention alone would send a re-save of
    one to `shared.txt` and translate it twice."""
    directory = Path(directory)
    ids = set(part_line_ids(store, key))
    for path in sorted(directory.glob("*.txt")):
        if _event_rows(path.read_text(encoding="utf-8"), path, ids):
            return path
    return directory / conventional_file(store, key)


def conventional_file(store: Store, key: str) -> str:
    """The file a part no translation file holds yet belongs in: an event's dated day's
    file, `shared.txt` for one with no day, `arrays.txt` for a surface."""
    scene = store.scenes_by_event.get(key)
    if scene is None:
        return ARRAYS_NAME
    day = scene_dated_day(scene)
    return f"day{day:02d}.txt" if day is not None else "shared.txt"


# --- the command line -----------------------------------------------------------------------------


def main_packet(
    day: int | None,
    events: Sequence[str],
    disc_dir: Path,
    out: Path,
    for_review: bool,
    translations: Sequence[Path],
    like: Path | None = None,
    arrays: bool = False,
    game: bool = False,
) -> int:
    if sum((day is not None, bool(events), like is not None, arrays, game)) != 1:
        print(
            "packet: give exactly one of --day N, --events E0103 [E0104 ...], --like FILE, "
            "--arrays or --game",
            file=sys.stderr,
        )
        return 2
    try:
        out_dir = check_destination(out)
        store = load_store(Path(disc_dir) / SCRIPT_DIR_NAME)
        builder = PacketBuilder.build(store, Policy.load(), translations or [DAYS_DIR], for_review)
        if day is not None:
            unit = unit_of_day(store, day)
        elif like is not None:
            unit = unit_like(store, like)
        elif arrays:
            unit = unit_of_surfaces(store)
        elif game:
            unit = unit_of_game(store, builder)
        else:
            unit = unit_of_events(store, events)
    except (PacketRefused, StoreMissing, OSError) as error:
        print(f"packet: {error}", file=sys.stderr)
        return 2
    if not unit.keys:
        print(f"packet: {unit.title} has nothing with text in the store", file=sys.stderr)
        return 2
    where = out_dir / (unit.name + ("-review" if for_review else ""))
    written = write_unit(builder, unit, where)
    texts = {path.name: path.read_text(encoding="utf-8") for path in written}
    system = texts.pop(SYSTEM_NAME)
    parts = "".join(text for name, text in texts.items() if name != ORDER_NAME)
    print(
        f"packet: {len(unit.keys)} part(s) of {unit.title}, {len(written)} file(s), in {where}"
        + (" (for review)" if for_review else "")
    )
    print(
        f"packet: system.md {len(system):,} chars, ~{estimate_tokens(system):,} tokens; the "
        f"parts {len(parts):,} chars, ~{estimate_tokens(parts):,} tokens (a Japanese "
        f"character ~1 token, anything else ~3.5 characters a token)"
    )
    if day is not None:
        missing = untranslated_reachable(builder, day)
        if missing:
            print(
                f"packet: day {day} also reaches {len(missing)} day-independent event(s) no "
                f"translation file has English for; they belong in shared.txt -- "
                f"`--events {' '.join(missing)}`"
            )
    return 0


def main_save_event(
    event: str,
    answer: Path | None,
    into: Path | None,
    disc_dir: Path,
    title: str,
    order: Path | None = None,
) -> int:
    try:
        store = load_store(Path(disc_dir) / SCRIPT_DIR_NAME)
        text = Path(answer).read_text(encoding="utf-8") if answer else sys.stdin.read()
        target = into or default_day_file(store, event)
        keys = order_keys(Path(order).read_text(encoding="utf-8")) if order else None
        print(save_event(store, event, text, target, title, keys))
    except (PacketRefused, StoreMissing, OSError) as error:
        print(f"save-event: {error}", file=sys.stderr)
        return 1
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    select = parser.add_argument_group("which events (exactly one)")
    select.add_argument(
        "--day",
        type=int,
        metavar="N",
        help=(
            "every event the data dates to in-game day N -- a new day file's scope; to "
            "re-translate a day file as it was scoped, use --like"
        ),
    )
    select.add_argument(
        "--events",
        nargs="+",
        default=(),
        metavar="EVENT",
        help="these events instead, in play order, e.g. E0650 E0651",
    )
    select.add_argument(
        "--arrays",
        action="store_true",
        help=(
            "every line outside the events -- menus, books, labels, screens -- one part "
            "per surface, for translation/days/arrays.txt (PLAN TRN-09)"
        ),
    )
    select.add_argument(
        "--like",
        type=Path,
        metavar="FILE",
        help=(
            "exactly the events a translation file holds, in its order -- for re-translating "
            "a day file or shared.txt"
        ),
    )
    select.add_argument(
        "--game",
        action="store_true",
        help=(
            "the whole game for one session: every event of all 31 days in play order, each "
            "day-independent event at the first day that reaches it, then every surface; "
            "order.txt names the file each part saves into (translation/README.md)"
        ),
    )
    parser.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        metavar="DIR",
        help=f"the import whose script store is read (default: {DEFAULT_DISC_DIR}/)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        metavar="DIR",
        help=(
            f"where the packet directories go (default: {DEFAULT_OUT_DIR}/). A packet is the "
            f"game's own text, so inside the repo only work/ is allowed"
        ),
    )
    parser.add_argument(
        "--for-review",
        action="store_true",
        help="also print each event's English as it stands, for the reviewer agent",
    )
    parser.add_argument(
        "--translation",
        dest="translations",
        nargs="+",
        default=(),
        type=Path,
        metavar="PATH",
        help=(
            f"translation files to read the neighbouring English from (default: {DAYS_DIR}/). "
            f"Point it away from a draft being re-translated, so the new one is not shown "
            f"the old"
        ),
    )
    parser.set_defaults(
        run=lambda args: main_packet(
            args.day,
            args.events,
            args.disc,
            args.out,
            args.for_review,
            args.translations,
            args.like,
            args.arrays,
            args.game,
        )
    )
    return parser


def add_save_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "event",
        metavar="PART",
        help="the event or surface the answer is for, e.g. E0121 or exe@8003D2E0",
    )
    parser.add_argument(
        "--order",
        type=Path,
        metavar="FILE",
        help=(
            "the packet's order.txt: a new part goes in at its place in it (default: the "
            "project's play order, events then surfaces)"
        ),
    )
    parser.add_argument(
        "--answer",
        type=Path,
        metavar="FILE",
        help="the translator's answer (default: standard input)",
    )
    parser.add_argument(
        "--into",
        type=Path,
        metavar="FILE",
        help=(
            "the day file to write it into (default: the file that already holds it, else "
            "translation/days/dayNN.txt for an event the data dates, shared.txt for one it "
            "does not, arrays.txt for a surface)"
        ),
    )
    parser.add_argument(
        "--title",
        default="",
        help="the first line of a day file this call creates (default: its file name)",
    )
    parser.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        metavar="DIR",
        help=f"the import whose script store is read (default: {DEFAULT_DISC_DIR}/)",
    )
    parser.set_defaults(
        run=lambda args: main_save_event(
            args.event, args.answer, args.into, args.disc, args.title, args.order
        )
    )
    return parser
