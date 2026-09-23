"""`PLAN TRN-08` -- the translator packet: a system part once, then one part per event.

A unit of translation is a day (or `shared.txt`, or any day file, or -- `PLAN TRN-09` --
the menus, books and screens outside every event), and the translator is one agent
directed through it by a parent (Jay, 2026-09-21: agent shape (b)). So a packet is a
directory:

* `system.md` -- given **once**: the day-file format (`translation/days/README.md`
  § Format, quoted whole), the style guide's rulings, the glossary rows whose Japanese
  term occurs anywhere in the unit, and the story bible's summary of the day with its line
  citations taken out.
* one part per event (`E0121.md`) or surface (`exe@8003D2E0.md`; `part_file` turns a
  key's `:` into `_`), given **one at a time** in `order.txt`'s order: where and who (or
  what the surface is), the branches if the scene has any, the neighbouring scenes'
  English as it stands, and the lines **in the day-file shape** with the Japanese in the
  English column and only the page breaks marked. The translator's answer is that block
  with the Japanese replaced, and `boku save-event` writes it into the day file -- the
  parent does the saving, placing a new block by `order.txt` (`--order`).
* `order.txt` -- the event ids or surface keys, in the order the parts are to be given.

    ./make.sh packet --day 8
    ./make.sh packet --like translation/days/day01.txt
    ./make.sh packet --arrays
    ./make.sh save-event E0121 --answer answer.txt --order work/packets/day01/order.txt

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
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from itertools import dropwhile
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import DEFAULT_DISC_DIR
from boku.events import LABEL_NAMES
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


class PacketRefused(Exception):
    """A destination this tool must not write to, a scene it cannot assemble, or an answer
    it will not save."""


# --- where a packet may be written ------------------------------------------------------------


def check_destination(out: Path) -> Path:
    """Refuse a destination inside the repo that is not under `work/`.

    A packet holds the Japanese script. Outside the checkout (a scratch directory, a
    translator's own machine) is the caller's business; inside it, `work/` is the only
    place the `.gitignore` keeps out of a commit.
    """
    out = Path(out).resolve()
    try:
        inside = out.relative_to(REPO_ROOT)
    except ValueError:
        return out
    if inside.parts[:1] != ("work",):
        raise PacketRefused(
            f"{out} is inside the repo and not under work/. A packet is the game's own "
            f"text and is never tracked (CLAUDE.md § 'This repo is public')."
        )
    return out


# --- the policy documents, narrowed to one scene -------------------------------------------------

_HEADING = re.compile(r"^(#{2,3})\s+(.*)$")
_TABLE_ROW = re.compile(r"^\|(.*)\|\s*$")
_SLOT = re.compile(r"\bslots?\s+((?:\d+)(?:\s*,\s*\d+)*)")
_DAY_CELL = re.compile(r"^(\d+)\s*(?:[-\u2013\u2014]\s*(\d+)?)?$")
_BASE = re.compile(r"^([A-Z])(\d+)$")


def _sections(text: str, level: int) -> list[tuple[str, list[str]]]:
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
class GlossaryRow:
    """One glossary row, with the source terms its table's `source` column names."""

    section: str
    terms: tuple[str, ...]
    cells: tuple[str, ...]
    header: tuple[str, ...] = ()
    """The column names of the table this row came from, so a packet prints that table's
    own header rather than a copy of it kept here (`DOC-3`)."""

    def markdown(self) -> str:
        return "| " + " | ".join(self.cells) + " |"


@dataclass(frozen=True)
class CastEntry:
    """One `### ` entry of the bible's § 3, and the slots its heading names."""

    heading: str
    slots: tuple[int, ...]


@dataclass(frozen=True)
class Policy:
    """`translation/` as a packet needs it -- parsed once, narrowed per scene."""

    day_rows: tuple[tuple[range, str, str], ...] = ()
    """The bible's § 4 month table: which days, what happens, which ids."""
    places: tuple[tuple[str, str], ...] = ()
    """The bible's § 7 map base -> place table, one row per base."""
    cast: tuple[CastEntry, ...] = ()
    glossary: tuple[GlossaryRow, ...] = ()
    rulings: tuple[tuple[str, str], ...] = ()
    """`(style guide section heading, its text)`, every numbered section (`parse_rulings`)."""

    @classmethod
    def load(cls, directory: Path = TRANSLATION_DIR) -> Policy:
        directory = Path(directory)
        bible = _read(directory / "bible.md")
        return cls(
            day_rows=parse_day_rows(bible),
            places=parse_places(bible),
            cast=parse_cast(bible),
            glossary=parse_glossary(_read(directory / "glossary.md")),
            rulings=parse_rulings(_read(directory / "style-guide.md")),
        )

    def day_row(self, day: int) -> str | None:
        """What happens on `day`, from the bible's § 4."""
        return next((what for days, what, _ in self.day_rows if day in days), None)

    def place(self, base: str) -> str:
        return dict(self.places).get(base, "")

    def cast_for(self, slots: Iterable[int]) -> list[CastEntry]:
        wanted = set(slots)
        return [entry for entry in self.cast if wanted.intersection(entry.slots)]

    def glossary_for(self, source: str) -> list[GlossaryRow]:
        """The rows whose source column occurs in this scene's Japanese, in file order."""
        return [row for row in self.glossary if any(term and term in source for term in row.terms)]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def parse_day_rows(bible: str) -> tuple[tuple[range, str, str], ...]:
    """The month table of the bible's § 4, as `(days, what happens, ids)` per row.

    An open-ended cell ("9-") runs to the day before the next row starts, which is what
    the table means and what the rows around it show.
    """
    body = next((lines for heading, lines in _sections(bible, 2) if heading.startswith("4.")), [])
    starts: list[tuple[int, int | None, str, str]] = []
    for line in body:
        cells = _table_cells(line)
        if cells is None or len(cells) < 3:
            continue
        cell = cells[0].replace("\u2013", "-").replace("\u2014", "-")
        match = _DAY_CELL.match(cell)
        if match is None:
            continue
        first = int(match.group(1))
        # The dash is tested on the *normalised* cell: the table writes "9-11" and "9-" with
        # an en dash, so asking the raw cell for an ASCII "-" reads every open-ended row as
        # the single day it starts on, and the days after it lose their story context.
        last = int(match.group(2)) if match.group(2) else (None if "-" in cell else first)
        starts.append((first, last, cells[1], cells[2]))
    out: list[tuple[range, str, str]] = []
    for index, (first, last, what, ids) in enumerate(starts):
        if last is None:
            following = starts[index + 1][0] if index + 1 < len(starts) else first + 1
            last = max(first, following - 1)
        out.append((range(first, last + 1), what, ids))
    return tuple(out)


def parse_places(bible: str) -> tuple[tuple[str, str], ...]:
    """The bible's § 7 base -> place table, with `G04 / G05` and `H01-H03` expanded."""
    body = next((lines for heading, lines in _sections(bible, 2) if heading.startswith("7.")), [])
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


SOURCE_COLUMN = "source"
"""The glossary column a row is matched on. Every table in `translation/glossary.md` has
one, but not always first: \u00a7 4a's tables lead with the insect's array index."""


def table_rows(text: str) -> Iterator[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """`(section, header cells, body cells)` for every body row of every Markdown table.

    A table is a header row, the `|---|` rule, then its body, so the header is asked which
    column is which rather than the columns being counted. Without that, the header row is
    itself read as data -- a glossary row whose "source term" is the word *source*, which
    matches any text containing it -- and a table that does not lead with its source column
    is keyed on whatever it does lead with (\u00a7 4a's `#`, so on the digits of an index).
    """
    section = ""
    candidate: tuple[str, ...] | None = None
    header: tuple[str, ...] | None = None
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            section, candidate, header = heading.group(2).strip(), None, None
            continue
        match = _TABLE_ROW.match(line.strip())
        if match is None:
            candidate = header = None
            continue
        cells = tuple(cell.strip() for cell in match.group(1).split("|"))
        if all(cell and set(cell) <= set("-: ") for cell in cells):
            header, candidate = candidate, None
            continue
        if header is None:
            candidate = cells
            continue
        yield section, header, cells


def parse_glossary(glossary: str) -> tuple[GlossaryRow, ...]:
    """Every table row of every section, keyed by the terms its `source` column names."""
    out: list[GlossaryRow] = []
    for section, header, cells in table_rows(glossary):
        column = next(
            (index for index, name in enumerate(header) if name.lower() == SOURCE_COLUMN), None
        )
        if column is None or column >= len(cells):
            continue
        terms = tuple(
            term.strip()
            for term in re.split(r"[/\uff0f]", re.sub(r"\(.*?\)", "", cells[column]))
            if term.strip() and term.strip() not in {"-", "\u2014"}
        )
        if terms:
            out.append(GlossaryRow(section, terms, cells, header))
    return tuple(out)


def parse_rulings(style_guide: str) -> tuple[tuple[str, str], ...]:
    """Every numbered section of the style guide, as `(heading, its text)`.

    The guide is in force as a whole (its status line), so a section with no SETTLED mark
    -- § 13, pages -- binds as much as one with it. The preamble is about the document and
    is left out.
    """
    return tuple((heading, "\n".join(body).strip()) for heading, body in _sections(style_guide, 2))


# --- the flow graph, in words -------------------------------------------------------------------

_CONDITION = re.compile(
    r"opt(\d+)|cancel|lflag(==|>=|<=|!=)(\d+)|flag\[(\d+)\](==|>=|<=|!=)(\d+)"
    r"|map(==|!=)([A-Z]\d+)|day'?([<>=]+)(\d+)|hour'?([<>=]+)(\d+)|R(==|>=)(\d+)"
)
_COMPARISON = {"==": "is", ">=": "is at least", "<=": "is at most", "!=": "is not"}


def condition_in_words(condition: str, policy: Policy) -> str:
    """One edge condition as a sentence. The symbolic form is always shown beside it."""
    return _in_words(condition, policy, " -- or -- ") if condition else ""


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


def _in_words(expression: str, policy: Policy, either: str = " or ") -> str:
    """`|` over `&` over terms, each split only at its own depth: a group inside a clause
    reads as a parenthesised group, `a and (b or c)`, never as a third clause."""
    expression = _unwrap(expression)
    clauses = _split_top(expression, "|")
    if len(clauses) > 1:
        return either.join(_in_words(clause, policy) for clause in clauses)
    terms = _split_top(expression, "&")
    if len(terms) == 1:
        return _term_in_words(expression, policy)
    return " and ".join(
        f"({_in_words(term, policy)})"
        if len(_split_top(_unwrap(term), "|")) > 1
        else _in_words(term, policy)
        for term in terms
    )


def _term_in_words(term: str, policy: Policy) -> str:
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
        return f"story flag {match.group(4)} {_COMPARISON[match.group(5)]} {match.group(6)}"
    if match.group(7):
        base = match.group(8)
        place = policy.place(base)
        where = f"{base}{f' ({place})' if place else ''}"
        return f"the player is{'' if match.group(7) == '==' else ' not'} on map {where}"
    if match.group(9):
        return f"the day {_COMPARISON.get(match.group(9), match.group(9))} {match.group(10)}"
    if match.group(11):
        return f"the hour {_COMPARISON.get(match.group(11), match.group(11))} {match.group(12)}"
    if match.group(13):
        return f"a random draw {_COMPARISON[match.group(13)]} {match.group(14)}"
    return term


# --- the policy text a translator is handed -------------------------------------------------------

_PLAN_CITATION = re.compile(r"\s*\([^()]*(?:\bPLAN\b|`[A-Z]{2,5}-\d{2}`)[^()]*\)")
_LINE_CITATION = re.compile(r"\s*\(?`E\d{4}[^`]*`(?:\s*[-\u2013\u2014]\s*`E\d{4}[^`]*`)?\)?")


def without_plan_citations(text: str) -> str:
    """Drop every parenthesis that cites the plan: `(PLAN § ...)`, `(`TRN-08`)`.

    The policy documents are written for the project and cite its rows; a translator has
    no use for them (Jay's list, `TRN-08`), and a row id reads as an instruction to go and
    look something up.
    """
    return _PLAN_CITATION.sub("", text)


def without_line_citations(text: str) -> str:
    """The bible's day summary without the event ids it cites (Jay, `TRN-08`)."""
    return re.sub(r"\s{2,}", " ", _LINE_CITATION.sub("", text)).strip()


def format_section(readme: str) -> str:
    """`translation/days/README.md` § Format, the day-file format as the translator reads it."""
    body = next((lines for heading, lines in _sections(readme, 2) if heading == FORMAT_SECTION), [])
    return "\n".join(body).strip()


# --- one line of the script, in the day-file shape ------------------------------------------------

LABEL_OF = {name: label for label, name in LABEL_NAMES.items() if label}
"""Store speaker name -> the Japanese label the sheet draws (`boku.events.LABEL_NAMES`,
inverted), for a chorus: its members are named on no screen, so the packet spells them as
the labels they would have had."""


def scene_line_ids(scene: dict) -> list[str]:
    """Every line id the scene carries, in play order, then any the flow never reaches.

    One list for the packet's template and for the check on a translator's answer, so the
    two cannot disagree about which ids an event is.
    """
    played = (node["line"] for node in iter_play_order(scene) if node.get("line"))
    return list(dict.fromkeys([*played, *scene["lines"]]))


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
    table: GlyphTable = field(default_factory=GlyphTable.load)

    @classmethod
    def build(
        cls, store: Store, policy: Policy, translations: Sequence[Path], for_review: bool
    ) -> PacketBuilder:
        rows, _ = load_rows(translation_paths(translations))
        english: dict[str, list[Row]] = {}
        for row in rows:
            if row.has_english:
                english.setdefault(row.line_id, []).append(row)
        return cls(
            store=store,
            policy=policy,
            english=english,
            for_review=for_review,
            format_text=format_section(_read(DAYS_DIR / "README.md")),
        )

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
        """`G03 -- kitchen (...)`: each base the scene is placed on, and what the bible calls it."""
        return "; ".join(
            f"{base} -- {self.policy.place(base)}" if self.policy.place(base) else base
            for base in scene["where"]["bases"]
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

    def surface_part(self, surface: Surface, position: int, total: int) -> str:
        """One surface as the translator is handed it: what it is, then its block."""
        kind = self.store.lines[surface.line_ids[0]]["kind"]
        block = self.block(self.surface_header(surface), surface.line_ids)
        out = [
            f"# {surface.key} -- surface {position} of {total}",
            "",
            f"* **What it is**: {self.describe(surface)}",
            f"* **How it is drawn**: {SURFACE_KINDS.get(kind, kind)}",
        ]
        if any(mark in row for row in block[1:] for mark in "「」『』"):
            out.append(
                "* The brackets in these lines are part of the text, not speech marks the "
                "program adds: keep them."
            )
        if any("{G:" in self.store.lines[i]["text"] for i in surface.line_ids):
            out.append(
                "* `{G:n}` is a picture the game draws inside the text (a button, an icon); "
                "keep it where the meaning puts it."
            )
        out += [
            "",
            "## Your answer",
            "",
            "This block, with the Japanese replaced by English.",
            "",
            "```text",
            *block,
            "```",
            "",
        ]
        if self.for_review:
            out += self._current(surface.line_ids)
        return "\n".join(out).rstrip() + "\n"

    def clips(self, scene: dict) -> list[str]:
        """`E0121.0 0121_00` for each voiced line: which recording each line is."""
        return [
            f"`{line_id}` {clip}"
            for line_id in scene_line_ids(scene)
            if (clip := (self.store.lines.get(line_id) or {}).get("voice", {}).get("clip"))
        ]

    # --- the system part ------------------------------------------------------------------

    def system_part(self, unit: Unit) -> str:
        title, day = unit.title, unit.day
        noun = "event" if unit.scenes else "surface"
        out = [
            f"# Translating {title}",
            "",
            f"You are translating {title} of *Boku no Natsuyasumi* (PlayStation, 2000) from "
            f"Japanese into English, one {noun} at a time: {len(unit.keys)} {noun}(s). This "
            f"part is the policy, given once; each {noun} then comes as its own message. For "
            f"each, answer with its block -- the lines under **Your answer** -- with the "
            f"Japanese replaced by English and the speaker column in English, in the "
            f"day-file format below, and nothing else. The Japanese speaker labels become "
            f"the English labels of the glossary and style guide § 9. Your earlier answers "
            f"stay in view: keep a voice, a recurring phrase and a name the same across them.",
            "",
            "## The day-file format",
            "",
            without_plan_citations(self.format_text),
            "",
            "## The style guide",
            "",
            "The whole of `translation/style-guide.md` is in force; these are its sections.",
            "",
        ]
        for heading, text in self.policy.rulings:
            out += [f"### {heading}", "", without_plan_citations(text), ""]
        source = "\n".join(
            self.store.japanese[line_id].plain()
            for line_id in unit.line_ids
            if line_id in self.store.japanese
        )
        rows = self.policy.glossary_for(source)
        if rows:
            out += [
                "## The glossary",
                "",
                f"Every row of `translation/glossary.md` whose Japanese occurs in these "
                f"{noun}s. "
                "These renderings are settled; use them.",
                "",
            ]
            section = ""
            for glossary_row in rows:
                if glossary_row.section != section:
                    section = glossary_row.section
                    header = glossary_row.header or ("source", "English")
                    out += [
                        "",
                        f"**{section}**",
                        "",
                        "| " + " | ".join(header) + " |",
                        "|" + "---|" * len(header),
                    ]
                out.append(glossary_row.markdown())
            out.append("")
        row = self.policy.day_row(day) if day is not None else None
        if row is not None:
            out += [
                "## The day, from the story bible",
                "",
                f"**Day {day}**: {without_line_citations(row)}",
                "",
            ]
        return "\n".join(out).rstrip() + "\n"

    # --- one event --------------------------------------------------------------------------

    def event_part(
        self, scene: dict, position: int, total: int, unit_events: frozenset[str] = frozenset()
    ) -> str:
        """One event as the translator is handed it. `unit_events` are the events of the
        same run: the translator has their answers in view already, so a neighbour among
        them is not shown -- and in a re-translation its English as it stands is the draft
        being replaced."""
        event = scene["event"]
        out = [f"# {event} -- event {position} of {total}", ""]
        out += self._where(scene)
        out += self._branches(scene)
        out += self._quiz(scene, scene_dated_day(scene))
        out += self._neighbours(scene, unit_events)
        out += [
            "## Your answer",
            "",
            "This block, with the Japanese replaced by English and the speaker column in "
            "English. Add `# NOTE` or `# UNSURE` lines where you need them.",
            "",
            "```text",
            *self.template(scene),
            "```",
            "",
        ]
        if self.for_review:
            out += self._current(scene_line_ids(scene))
        return "\n".join(out).rstrip() + "\n"

    def _where(self, scene: dict) -> list[str]:
        hour = scene_hour(scene)
        slots = scene["where"]["time_slots"]
        when = [_day_text(scene)]
        if hour is not None:
            when.append(f"from {hour}:00")
        elif slots:
            when.append(f"time slot(s) {slots}")
        condition = scene["when"]["condition"]
        if condition:
            when.append(f"when {condition_in_words(condition, self.policy)}")
        places = self.places(scene)
        who = [
            re.sub(r",\s*\d[\d,]* lines$", "", entry.heading)
            for entry in self.policy.cast_for(member["slot"] for member in scene["cast"])
        ]
        out = [
            f"* **Where**: {places or 'unknown'}",
            f"* **When**: {'; '.join(when)}",
        ]
        if who:
            out.append(f"* **Who is here**: {'; '.join(who)}")
        clips = self.clips(scene)
        if clips:
            out.append(f"* **Voice clips**: {', '.join(clips)}")
        for handover in scene.get("handovers") or []:
            if handover.get("event") and handover.get("reachable", True):
                out.append(f"* **Then**: the game moves on to `{handover['event']}`")
        out.append("")
        return out

    def _branches(self, scene: dict) -> list[str]:
        """The scene's forks, in words. A linear scene has none and gets no section.

        A fork is a node with more than one way on -- a choice menu's options, or edges
        that test a condition. Each target is named by the line it opens, which is how
        the translator sees the scene in the block below.
        """
        line_of = {node["node"]: node.get("line") for node in scene["nodes"]}
        edges: dict[str, list[dict]] = {}
        for edge in scene["edges"]:
            edges.setdefault(edge["from"], []).append(edge)
        forks: list[str] = []
        for source in ["ENTRY", *(node["node"] for node in iter_play_order(scene))]:
            outgoing = edges.get(source, [])
            if len(outgoing) < 2:
                continue
            where = "At the start" if source == "ENTRY" else f"After `{line_of.get(source)}`"
            forks.append(f"* {where}:")
            for edge in outgoing:
                target = edge["to"]
                goes = (
                    "the event ends"
                    if target == "END"
                    else f"`{line_of.get(target) or target}` comes next"
                )
                words = condition_in_words(edge["condition"], self.policy)
                forks.append(f"  * {goes}" + (f" when {words}" if words else ""))
        if not forks:
            return []
        return ["## Where the scene branches", "", *forks, ""]

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
    def _order(self) -> tuple[list[dict], dict[str, int]]:
        """Every scene with any text in the project's order, and each one's place in it."""
        order = [scene for scene in ordered_scenes(self.store) if has_text(scene)]
        return order, {scene["event"]: index for index, scene in enumerate(order)}

    def neighbours(self, scene: dict) -> tuple[dict | None, dict | None]:
        """The scenes either side of this one with any text, in the project's order."""
        order, index_of = self._order
        index = index_of.get(scene["event"])
        if index is None:
            return None, None
        return (
            order[index - 1] if index else None,
            order[index + 1] if index + 1 < len(order) else None,
        )

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

    @property
    def keys(self) -> list[str]:
        """The parts in the order they are given: events, then surfaces."""
        return [scene["event"] for scene in self.scenes] + [s.key for s in self.surfaces]

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


def write_unit(builder: PacketBuilder, unit: Unit, out_dir: Path) -> list[Path]:
    """`system.md`, one `<KEY>.md` per event or surface, and `order.txt`. Deterministic.

    The directory is emptied of earlier parts first, so a stale part from another run is
    never mistaken for part of this one.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.md"):
        stale.unlink()
    written: list[Path] = []
    system = out_dir / SYSTEM_NAME
    system.write_text(builder.system_part(unit), encoding="utf-8")
    written.append(system)
    total = len(unit.keys)
    events = frozenset(scene["event"] for scene in unit.scenes)
    parts = [
        *(
            builder.event_part(scene, position, total, events)
            for position, scene in enumerate(unit.scenes, start=1)
        ),
        *(
            builder.surface_part(surface, position, total)
            for position, surface in enumerate(unit.surfaces, start=len(unit.scenes) + 1)
        ),
    ]
    for key, part in zip(unit.keys, parts, strict=True):
        path = out_dir / part_file(key)
        path.write_text(part, encoding="utf-8")
        written.append(path)
    order = out_dir / ORDER_NAME
    order.write_text("".join(f"{key}\n" for key in unit.keys), encoding="utf-8")
    written.append(order)
    return written


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
    scene = store.scenes_by_event.get(key)
    if scene is None:
        return directory / ARRAYS_NAME
    day = scene_dated_day(scene)
    return directory / (f"day{day:02d}.txt" if day is not None else "shared.txt")


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
) -> int:
    if sum((day is not None, bool(events), like is not None, arrays)) != 1:
        print(
            "packet: give exactly one of --day N, --events E0103 [E0104 ...], --like FILE "
            "or --arrays",
            file=sys.stderr,
        )
        return 2
    try:
        out_dir = check_destination(out)
        store = load_store(Path(disc_dir) / SCRIPT_DIR_NAME)
        if day is not None:
            unit = unit_of_day(store, day)
        elif like is not None:
            unit = unit_like(store, like)
        elif arrays:
            unit = unit_of_surfaces(store)
        else:
            unit = unit_of_events(store, events)
    except (PacketRefused, StoreMissing, OSError) as error:
        print(f"packet: {error}", file=sys.stderr)
        return 2
    if not unit.keys:
        print(f"packet: {unit.title} has nothing with text in the store", file=sys.stderr)
        return 2
    builder = PacketBuilder.build(store, Policy.load(), translations or [DAYS_DIR], for_review)
    where = out_dir / (unit.name + ("-review" if for_review else ""))
    written = write_unit(builder, unit, where)
    total = sum(path.stat().st_size for path in written)
    print(
        f"packet: {len(unit.keys)} part(s) of {unit.title}, {len(written)} file(s), "
        f"{total / 1024:.0f} KiB, in {where}" + (" (for review)" if for_review else "")
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
        keys = Path(order).read_text(encoding="utf-8").split() if order else None
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
