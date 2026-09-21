"""`PLAN TRN-02` -- scene assembly: one Markdown packet per scene for a translator agent.

A unit of translation work is a whole scene (README § "How the translation is made"), and
a packet is everything an agent needs to translate that scene and nothing it does not: the
scene as the game plays it, every line with its Japanese and its capacity, and the policy
documents narrowed to this scene -- the day's entry in the bible, the glossary rows whose
source term actually occurs here, the settled style rulings, and the neighbouring scenes'
English where it is already written. Err toward too much context; the model has the window.

    ./make.sh packet --day 1
    ./make.sh packet --events E0650 E0651 --for-review

**A packet is the Japanese script, so it is written under the gitignored `work/` and can
never be tracked** (CLAUDE.md § "This repo is public"). `--out` refuses anywhere else
inside the repo.

Everything in a packet is *derived*: the scene graph from `disc/script/scenes/`, the lines
from `disc/script/lines.jsonl`, the policy from `translation/*.md` as they stand. Nothing
here restates a fact those files own (`DOC-3`), so a ruling changed in the style guide is
changed in the next packet without anyone remembering to edit this module. Two runs over
one store write byte-identical files: there is no timestamp, no absolute path and no set
iteration in the output.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import DEFAULT_DISC_DIR
from boku.extract import SCRIPT_DIR_NAME
from boku.layout import DIALOGUE_BAND
from boku.lint import Row, load_rows, translation_paths
from boku.script_store import (
    Japanese,
    Store,
    StoreMissing,
    is_array,
    iter_play_order,
    load_store,
    ordered_scenes,
    page_count,
    pages_fixed_by_voice,
    scene_dated_day,
    scene_day,
    scene_hour,
    scenes_named,
    scenes_of_day,
    select_shape,
)

DEFAULT_OUT_DIR = REPO_ROOT / "work" / "packets"
TRANSLATION_DIR = REPO_ROOT / "translation"
DAYS_DIR = TRANSLATION_DIR / "days"

AVERAGE_PX_PER_CHARACTER = 5.85
"""Measured over the prototype's sample lines (`research/vwf-prototype.md` § "Measurements
for TXT-07"). Only ever used to turn the band's pixel width into the "about N characters"
a translator can hold in their head; the lint measures the real thing."""


class PacketRefused(Exception):
    """A destination this tool must not write to, or a scene it cannot assemble."""


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
    body: str


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
    """`(style guide section, the settled ruling)` -- every bullet that says SETTLED."""

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

    def day_row(self, day: int) -> tuple[str, str] | None:
        for days, what, ids in self.day_rows:
            if day in days:
                return what, ids
        return None

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
    """The `### ` entries of the bible's § 3, with the slot numbers their headings name."""
    out: list[CastEntry] = []
    inside = False
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        if heading is None:
            return
        match = _SLOT.search(heading)
        slots = tuple(int(part) for part in match.group(1).split(",")) if match else ()
        out.append(CastEntry(heading, slots, "\n".join(body).strip()))

    for line in bible.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 2:
            flush()
            heading, body = None, []
            inside = match.group(2).strip().startswith("3.")
            continue
        if match and len(match.group(1)) == 3:
            flush()
            heading = match.group(2).strip() if inside else None
            body = []
            continue
        if heading is not None:
            body.append(line)
    flush()
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
    """Every settled ruling, as `(section heading, the bullet or heading that says so)`.

    The style guide is long and most of it is argument; what a translator has to obey is
    the sentences marked SETTLED. The full file is cited beside them, never copied.
    """
    out: list[tuple[str, str]] = []
    for heading, body in _sections(style_guide, 2):
        if "SETTLED" in heading:
            out.append((heading, ""))
        for paragraph in _bullets(body):
            if "SETTLED" in paragraph:
                out.append((heading, paragraph))
    return tuple(out)


def _bullets(lines: Sequence[str]) -> list[str]:
    """Top-level `* ` bullets, each with its continuation lines folded into one string."""
    out: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("* "):
            current = [line[2:].strip()]
            out.append(current)
        elif current is not None and line.startswith(("  ", "\t")) and line.strip():
            current.append(line.strip())
        elif not line.strip():
            current = None
    return [" ".join(bullet) for bullet in out]


# --- the flow graph, in words -------------------------------------------------------------------

_CONDITION = re.compile(
    r"opt(\d+)|cancel|lflag(==|>=|<=|!=)(\d+)|flag\[(\d+)\](==|>=|<=|!=)(\d+)"
    r"|map(==|!=)([A-Z]\d+)|day'?([<>=]+)(\d+)|hour'?([<>=]+)(\d+)|R(==|>=)(\d+)"
)
_COMPARISON = {"==": "is", ">=": "is at least", "<=": "is at most", "!=": "is not"}


def condition_in_words(condition: str, policy: Policy) -> str:
    """One edge condition as a sentence. The symbolic form is always shown beside it."""
    if not condition:
        return ""
    parts: list[str] = []
    for clause in re.split(r"\s*\|\s*", condition):
        terms = [_term_in_words(term.strip(), policy) for term in re.split(r"\s*&\s*", clause)]
        parts.append(" and ".join(term for term in terms if term))
    return " -- or -- ".join(part for part in parts if part)


def _term_in_words(term: str, policy: Policy) -> str:
    while term.startswith("(") and term.endswith(")"):
        term = term[1:-1].strip()
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


# --- rendering ------------------------------------------------------------------------------------


def _fence(japanese: Japanese) -> list[str]:
    """The Japanese as the game lays it out: one block per page, one line per column."""
    out = ["```"]
    for number, page in enumerate(japanese.pages, start=1):
        if number > 1:
            wait = japanese.waits[number - 2] if number - 2 < len(japanese.waits) else None
            out.append(f"-- page {number} (turns after {wait} frames) --")
        for index, column in enumerate(page, start=1):
            out.append(f"col {index} ({len(column):2d}): {''.join(column)}")
    out.append("```")
    return out


def band_rule() -> str:
    """The box limits, in the numbers `boku.layout` holds and `TXT-07` measured."""
    band = DIALOGUE_BAND
    characters = int(band.width / AVERAGE_PX_PER_CHARACTER)
    guarded = int(band.guarded_width / AVERAGE_PX_PER_CHARACTER)
    return (
        f"The dialogue band holds **{band.lines} lines of {band.width} px** -- about "
        f"{characters} characters at the prototype's measured {AVERAGE_PX_PER_CHARACTER} px "
        f"per character. Line {band.guarded_from} and any line below it must end before "
        f"{band.guarded_width} px (~{guarded} characters): the next-page pencil sits there. "
        f"The engine has no wrap logic and clips at the screen edge in silence, so the "
        f"inserter breaks lines and `boku lint` measures them. **Nothing is shortened to "
        f'fit** (README § "Who this is for"): a page that will not fit is translated in '
        f"full and flagged `# OVERFLOW`, and the engineering side widens the box or adds a "
        f"page."
    )


def _capacity(record: dict) -> str:
    capacity = record.get("capacity", {})
    pages = page_count(record)
    fixed = pages_fixed_by_voice(record)
    parts = [
        f"{pages} page(s), "
        + (
            "**fixed by the voice clip** -- the English must have exactly this many, in this "
            "order, and no content may move across a break"
            if fixed
            else "not voice-timed, so the page breaks may be re-placed (each page must still fit)"
        ),
        f"{capacity.get('bytes')} bytes per copy, {capacity.get('copies')} copy/copies on the disc",
    ]
    if capacity.get("select_lines_fixed") is not None:
        parts.append(
            f"the executable fixes {capacity['select_lines_fixed']} select line(s); options map 1:1"
        )
    if is_array(record):
        parts.append(
            "a code-file array item: the next symbol starts where it ends, so it may not "
            "grow past its byte size"
        )
    return "; ".join(parts)


def _day_text(scene: dict) -> str:
    """The `Day` line of the header: the day the data fixes the scene to, or that none does.

    The data dates an event by its id, and that day is the only day it fires on. A
    `day==N` inside the entry condition is not that -- it is one test among the rest,
    routinely one branch of an `|` whose sibling covers the other days -- so the header
    leaves the day open and points at the condition bullet below rather than reprinting
    it (`script_store.scene_day`, `scene_dated_day`).
    """
    day, derived = scene_day(scene)
    if day is None:
        return "any (day-independent)"
    if not derived:
        return str(day)
    return (
        f"any day -- see the entry condition below; its `day=={day}` is one test among "
        f"the rest, not the day this scene plays on"
    )


@dataclass
class _Neighbours:
    previous: dict | None = None
    following: dict | None = None


@dataclass
class PacketBuilder:
    """Everything a run needs, so a scene packet is one call and two runs are identical."""

    store: Store
    policy: Policy
    english: dict[str, list[Row]] = field(default_factory=dict)
    for_review: bool = False

    @classmethod
    def build(
        cls, store: Store, policy: Policy, translations: Sequence[Path], for_review: bool
    ) -> PacketBuilder:
        rows, _ = load_rows(translation_paths(translations))
        english: dict[str, list[Row]] = {}
        for row in rows:
            if not row.voice_only:
                english.setdefault(row.line_id, []).append(row)
        return cls(store=store, policy=policy, english=english, for_review=for_review)

    def neighbours(self, scene: dict) -> _Neighbours:
        order = ordered_scenes(self.store)
        index = next((i for i, other in enumerate(order) if other["event"] == scene["event"]), None)
        if index is None:
            return _Neighbours()
        return _Neighbours(
            previous=order[index - 1] if index else None,
            following=order[index + 1] if index + 1 < len(order) else None,
        )

    def settled(self, scene: dict) -> list[str]:
        """A neighbouring scene's English, if it is already written."""
        out: list[str] = []
        for line_id in scene["lines"]:
            for row in self.english.get(line_id, []):
                out.append(f"| `{line_id}` | {row.speaker} | {row.text} |")
        return out

    # --- the scene packet ------------------------------------------------------------------

    def scene_packet(self, scene: dict) -> str:
        event = scene["event"]
        # Only a dated day selects day-keyed context (the bible's § 4 entry, the quiz's
        # row for the day); what the header says about a derived one is `_day_text`.
        dated = scene_dated_day(scene)
        lines: list[str] = []
        add = lines.append

        add(f"# {event} -- translation packet")
        add("")
        add(
            "Everything needed to translate this one scene, assembled by `boku packet` "
            "(`PLAN TRN-02`). Write the English into `translation/days/` in the format of "
            "`translation/days/README.md`; flag anything you are unsure of with a `# UNSURE` "
            "note above the row -- on the day-1 pilot four of six flags drew a reviewer "
            "finding, so a flag is a real signal."
        )
        add("")
        lines += self._where(scene)
        lines += self._cast(scene)
        lines += self._flow(scene)
        lines += self._lines(scene)
        lines += self._quiz(scene, dated)
        lines += self._context(scene, dated)
        lines += self._neighbours(scene)
        return "\n".join(lines).rstrip() + "\n"

    def _where(self, scene: dict) -> list[str]:
        where, when = scene["where"], scene["when"]
        hour = scene_hour(scene)
        bases = ", ".join(
            f"{base}{f' -- {self.policy.place(base)}' if self.policy.place(base) else ''}"
            for base in where["bases"]
        )
        triggers = ", ".join(
            f"{name} x{count}" for name, count in sorted(where["triggers"].items())
        )
        out = [
            "## Where and when",
            "",
            f"* **Day**: {_day_text(scene)}",
            f"* **Hour**: {hour if hour is not None else 'not fixed'}"
            + (f"; time slot(s) {where['time_slots']}" if where["time_slots"] else ""),
            f"* **Place**: {bases or 'unknown'} (maps {', '.join(where['maps']) or 'none'})",
            f"* **Trigger**: {triggers or 'none recorded'}",
            f"* **Entry condition**: `{when['condition'] or '(none)'}`"
            + (
                f" -- {condition_in_words(when['condition'], self.policy)}"
                if when["condition"]
                else ""
            ),
            f"* **Copies of this event on the disc**: {scene['copies']}",
            "",
        ]
        return out

    def _cast(self, scene: dict) -> list[str]:
        out = ["## Cast", "", "| slot | model | who |", "|---|---|---|"]
        for member in scene["cast"]:
            slot = member["slot"]
            who = "; ".join(entry.heading for entry in self.policy.cast_for([slot])) or "?"
            out.append(f"| {slot} | {member['model']} | {who} |")
        labels = sorted(
            {
                node["speaker"]
                for node in scene["nodes"]
                if node.get("speaker") and node["speaker"] not in {"CHAIN", "SELECT"}
            }
        )
        if labels:
            out += [
                "",
                f"Speaker labels the script gives in this scene: "
                f"{', '.join(f'`{label}`' for label in labels)}. A `+` label is a chorus and "
                f"is written as the members, comma-separated, in the speaker column "
                f"(`translation/days/README.md`). The English labels are the style guide's § 9.",
            ]
        out.append("")
        return out

    def _flow(self, scene: dict) -> list[str]:
        out = [
            "## The scene, in the order the game plays it",
            "",
            "Each node is one thing the engine does. An edge is where it can go next; the "
            "symbolic condition is the extract's own and the sentence after it is this tool's "
            "reading of it.",
            "",
        ]
        edges: dict[str, list[dict]] = {}
        for edge in scene["edges"]:
            edges.setdefault(edge["from"], []).append(edge)
        entry = [edge["to"] for edge in edges.get("ENTRY", [])]
        if entry:
            out.append(f"* **ENTRY** -> {', '.join(f'`{target}`' for target in entry)}")
        for node in iter_play_order(scene):
            node_id = node["node"]
            line_id = node.get("line")
            head = f"* **`{node_id}`** -- {node['opcode']}"
            if node.get("speaker"):
                head += f", speaker `{node['speaker']}`"
            if node.get("slot") is not None:
                head += f" (slot {node['slot']})"
            if line_id:
                head += f", line `{line_id}`"
            if node.get("hands_over_to"):
                head += f", hands over to `{node['hands_over_to']}`"
            out.append(head)
            out += self._options(scene, node, edges)
            for edge in edges.get(node_id, []):
                words = condition_in_words(edge["condition"], self.policy)
                condition = f" when `{edge['condition']}` -- {words}" if edge["condition"] else ""
                out.append(f"  * -> `{edge['to']}`{condition}")
        handovers = scene.get("handovers") or []
        if handovers:
            out += ["", "**Hand-overs** (where this scene leaves the player):", ""]
            for handover in handovers:
                out.append(
                    f"* `{handover['kind']}`"
                    + (f" on map `{handover['map']}`" if handover.get("map") else "")
                    + (f" -> event `{handover['event']}`" if handover.get("event") else "")
                    + ("" if handover.get("reachable", True) else " (not reachable)")
                )
        out.append("")
        return out

    def _options(self, scene: dict, node: dict, edges: dict[str, list[dict]]) -> list[str]:
        """A select node's options, each against the node its branch goes to."""
        line_id = node.get("line")
        record = self.store.lines.get(line_id) if line_id else None
        shape = select_shape(record) if record else None
        if shape is None:
            return []
        options, prompts = shape
        japanese = self.store.japanese[line_id]
        rows = [c for page in japanese.pages for c in page]
        targets = {"": ""}
        for edge in edges.get(node["node"], []):
            match = re.fullmatch(r"opt(\d+)", edge["condition"] or "")
            if match:
                targets[match.group(1)] = edge["to"]
        out = [
            f"  * a choice menu: {prompts} prompt line(s) then {options} option(s), fixed by "
            f"`g_select_lines` -- the English maps 1:1"
        ]
        for index, column in enumerate(rows):
            text = "".join(column)
            if not text:
                continue
            if index < prompts:
                out.append(f"    * prompt: {text}")
            else:
                target = targets.get(str(index - prompts), "")
                arrow = f" -> `{target}`" if target else ""
                out.append(f"    * option {index - prompts + 1}: {text}{arrow}")
        return out

    def _lines(self, scene: dict) -> list[str]:
        out = ["## The lines", "", band_rule(), ""]
        reached = {node["line"]: node for node in scene["nodes"] if "line" in node}
        order = [node["line"] for node in iter_play_order(scene) if node.get("line")]
        order += [line_id for line_id in scene["lines"] if line_id not in order]
        for line_id in order:
            record = self.store.lines.get(line_id)
            node = reached.get(line_id)
            out.append(f"### `{line_id}`")
            out.append("")
            if record is None:
                out += [
                    "* **voice only** -- no text on the disc. It is listed so the ids line up; "
                    "write the row as `(voice only)` with no English "
                    "(`translation/samples/README.md`), and see `translation/voice-only.md`.",
                    "",
                ]
                continue
            speaker = record.get("speaker") or {}
            out.append(
                f"* **Speaker**: label `{speaker.get('label')}`"
                + (f", slot {speaker['slot']}" if speaker.get("slot") is not None else "")
                + (
                    f", drawn inline as `{speaker['inline_label']}`"
                    if speaker.get("inline_label")
                    else ""
                )
            )
            if node is not None and node.get("speaker") and node["speaker"] != speaker.get("label"):
                out.append(
                    f"* **The node names a different speaker**: `{node['speaker']}` -- a chorus "
                    f"or a hand-over; translate the label the scene shows."
                )
            voiced = record.get("voiced")
            voice = record.get("voice") or {}
            out.append(
                "* **Voiced**: "
                + (
                    f"yes, clip `{voice.get('clip')}`; the pages turn on its frame countdown"
                    if voiced
                    else "no"
                )
            )
            out.append(f"* **Capacity**: {_capacity(record)}")
            out.append("")
            out += _fence(self.store.japanese[line_id])
            out.append("")
            if self.for_review:
                out += self._current(line_id)
        return out

    def _current(self, line_id: str) -> list[str]:
        """`--for-review`: the English as it stands, for the reviewer agent."""
        rows = self.english.get(line_id, [])
        if not rows:
            return ["* **English as it stands**: none written yet.", ""]
        out = ["* **English as it stands**:", ""]
        for row in rows:
            out.append(f"  * `{row.file}:{row.number}` {row.speaker}: {row.text}")
            for note in row.notes:
                out.append(f"    * note: {note}")
        out.append("")
        return out

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
            f"Native routine(s) {quiz.get('routines')} pick one of this event's messages by "
            f"day, so a line here is **day d's question** and not a general one -- translate it "
            f"knowing which day it is asked on.",
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

    def _context(self, scene: dict, day: int | None) -> list[str]:
        out: list[str] = []
        row = self.policy.day_row(day) if day is not None else None
        if row is not None:
            out += [
                "## The day, from the story bible (§ 4)",
                "",
                f"**Day {day}**: {row[0]}",
                "",
                f"Events the bible names for it: {row[1]}. The whole section is "
                f"`translation/bible.md` § 4; the cast entries are § 3 and the places § 7.",
                "",
            ]
        cast = self.policy.cast_for(member["slot"] for member in scene["cast"])
        if cast:
            out += ["## Who is in this scene, from the bible (§ 3)", ""]
            for entry in cast:
                out += [f"### {entry.heading}", "", entry.body, ""]
        source = "\n".join(
            self.store.japanese[line_id].plain()
            for line_id in scene["lines"]
            if line_id in self.store.japanese
        )
        rows = self.policy.glossary_for(source)
        if rows:
            out += [
                "## Glossary rows whose term occurs in this scene",
                "",
                "Matched on the source column against this scene's own text; these renderings "
                "are settled and are not to be re-decided here (`translation/glossary.md`).",
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
        if self.policy.rulings:
            out += [
                "## The settled style rulings",
                "",
                "Compact; the reasoning and the rejected alternatives are in "
                "`translation/style-guide.md`.",
                "",
            ]
            section = ""
            for heading, ruling in self.policy.rulings:
                if heading != section:
                    section = heading
                    out.append(f"* **{heading}**")
                if ruling:
                    out.append(f"  * {ruling}")
            out.append("")
        return out

    def _neighbours(self, scene: dict) -> list[str]:
        neighbours = self.neighbours(scene)
        out: list[str] = []
        for title, other in (
            ("The scene before this one", neighbours.previous),
            ("The scene after this one", neighbours.following),
        ):
            if other is None:
                continue
            settled = self.settled(other)
            out += [f"## {title}: `{other['event']}`", ""]
            if settled:
                out += [
                    "Its English is settled; match the voices and keep any recurring phrase "
                    "identical.",
                    "",
                    "| line | speaker | English |",
                    "|---|---|---|",
                    *settled,
                    "",
                ]
            else:
                out += ["Not translated yet.", ""]
        return out

    # --- the day packet --------------------------------------------------------------------

    def day_packet(self, day: int, scenes: Sequence[dict]) -> str:
        out = [
            f"# Day {day} -- the scenes, in order",
            "",
            f"{len(scenes)} scene(s) day {day} can reach (`script_store.scene_plays_on`, "
            f"so a scene the data gives no day of its own is here too), in the order this "
            f"project reads them (day, then the hour or time slot the script names, then the "
            f"event id). One packet per scene sits beside this file. Day-independent events "
            f"a day's flow can reach are a judgement the data does not make -- "
            f"`translation/days/README.md` records which ones day 1 needed and why.",
            "",
            "| # | event | hour | place | lines | translated |",
            "|---|---|---|---|---|---|",
        ]
        for number, scene in enumerate(scenes, start=1):
            hour = scene_hour(scene)
            bases = ", ".join(
                f"{base}{f' ({self.policy.place(base)})' if self.policy.place(base) else ''}"
                for base in scene["where"]["bases"]
            )
            translated = sum(1 for line_id in scene["lines"] if self.english.get(line_id))
            out.append(
                f"| {number} | [`{scene['event']}`]({scene['event']}.md) | "
                f"{hour if hour is not None else '-'} | {bases or '-'} | "
                f"{len(scene['lines'])} | {translated} |"
            )
        out.append("")
        row = self.policy.day_row(day)
        if row is not None:
            out += [
                "## The day, from the story bible (§ 4)",
                "",
                f"**Day {day}**: {row[0]}",
                "",
                f"Events the bible names for it: {row[1]}.",
                "",
            ]
        out += ["## The box", "", band_rule(), ""]
        return "\n".join(out).rstrip() + "\n"


# --- writing them out ---------------------------------------------------------------------------


def write_packets(
    builder: PacketBuilder,
    scenes: Sequence[dict],
    out_dir: Path,
    day: int | None,
) -> list[Path]:
    """One file per scene plus, for a day, the day-level packet. Deterministic."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for scene in scenes:
        path = out_dir / f"{scene['event']}.md"
        path.write_text(builder.scene_packet(scene), encoding="utf-8")
        written.append(path)
    if day is not None:
        path = out_dir / f"day{day:02d}.md"
        path.write_text(builder.day_packet(day, scenes), encoding="utf-8")
        written.append(path)
    return written


def main_packet(
    day: int | None,
    events: Sequence[str],
    disc_dir: Path,
    out: Path,
    for_review: bool,
    translations: Sequence[Path],
) -> int:
    if (day is None) == (not events):
        print("packet: give exactly one of --day N or --events E0103 [E0104 ...]", file=sys.stderr)
        return 2
    try:
        out_dir = check_destination(out)
        store = load_store(Path(disc_dir) / SCRIPT_DIR_NAME)
        scenes = scenes_of_day(store, day) if day is not None else scenes_named(store, events)
    except (PacketRefused, StoreMissing) as error:
        print(f"packet: {error}", file=sys.stderr)
        return 2
    if not scenes:
        print(f"packet: no scene in the store plays on day {day}", file=sys.stderr)
        return 2
    sources = translations or [DAYS_DIR]
    builder = PacketBuilder.build(store, Policy.load(), sources, for_review)
    where = out_dir / (f"day{day:02d}" if day is not None else "events")
    if for_review:
        where = where.with_name(where.name + "-review")
    written = write_packets(builder, scenes, where, day)
    total = sum(path.stat().st_size for path in written)
    print(
        f"packet: wrote {len(written)} file(s), {total / 1024:.0f} KiB, to {where}"
        + (" (for review)" if for_review else "")
    )
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--day",
        type=int,
        metavar="N",
        help="assemble every scene the extract dates to in-game day N",
    )
    parser.add_argument(
        "--events",
        nargs="+",
        default=(),
        metavar="EVENT",
        help="assemble these events instead, e.g. E0650 E0651",
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
            f"where the packets go (default: {DEFAULT_OUT_DIR}/). A packet is the game's "
            f"own text, so inside the repo only work/ is allowed"
        ),
    )
    parser.add_argument(
        "--for-review",
        action="store_true",
        help="also print the English as it stands beside each line, for the reviewer agent",
    )
    parser.add_argument(
        "--translation",
        dest="translations",
        nargs="+",
        default=(),
        type=Path,
        metavar="PATH",
        help=f"translation files to read the settled English from (default: {DAYS_DIR}/)",
    )
    parser.set_defaults(
        run=lambda args: main_packet(
            args.day,
            args.events,
            args.disc,
            args.out,
            args.for_review,
            args.translations,
        )
    )
    return parser
