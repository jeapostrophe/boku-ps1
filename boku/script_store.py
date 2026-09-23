"""Reading `disc/script/` back — the store `boku extract` writes, as its consumers need it.

`boku.extract` writes the store; nothing read it back until now, and two things need to:
the translator packets (`boku.packets`, `PLAN TRN-02`) and the translation lints
(`boku.lint`, `PLAN PIPE-06`). Both need the same handful of derived facts — which ids a
translation may legally name, what shape the executable fixes for a select, how many pages
the voice timing fixes, and the Japanese as pages of columns — so they live here once.

The store is **disc content**: it is written under the gitignored `disc/` from the
contributor's own dump, and nothing read through this module may be written into a tracked
file (CLAUDE.md § "This repo is public").
"""

from __future__ import annotations

import json
import operator
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from boku.glyphs import GlyphTable

INDEX_NAME = "index.json"
LINES_NAME = "lines.jsonl"
SCENES_DIR_NAME = "scenes"


class StoreMissing(Exception):
    """No script store here — the contributor has not run the import and the extract."""


# --- the Japanese, as the game lays it out ---------------------------------------------------

_TOKEN = re.compile(r"\{(NL|END|PAGE:(\d+)|G:\d+|C:[0-9A-F]{4})\}")


@dataclass(frozen=True)
class Japanese:
    """One decoded line as pages of columns of single cells.

    `{NL}` opens a column and `{PAGE:p}` ends a page carrying the frame countdown that
    turns it (`research/text-format.md`). A `{G:n}` or `{C:nnnn}` token is one cell and is
    kept whole, so a column's length here is the cell count the capacity facts quote.
    """

    pages: tuple[tuple[tuple[str, ...], ...], ...] = ()
    waits: tuple[int, ...] = ()

    @property
    def column_counts(self) -> tuple[tuple[int, ...], ...]:
        return tuple(tuple(len(column) for column in page) for page in self.pages)

    @property
    def cells(self) -> int:
        return sum(len(column) for page in self.pages for column in page)

    def plain(self) -> str:
        """The same text linearly: ` / ` between columns, ` // ` between pages."""
        return " // ".join(" / ".join("".join(c) for c in page) for page in self.pages)


def parse_japanese(text: str) -> Japanese:
    """Split a decoded line into pages and columns, one entry per drawn cell."""
    pages: list[tuple[tuple[str, ...], ...]] = []
    page: list[tuple[str, ...]] = []
    column: list[str] = []
    waits: list[int] = []
    ended = False
    at = 0
    for match in _TOKEN.finditer(text):
        column.extend(text[at : match.start()])
        at = match.end()
        token = match.group(1)
        if token.startswith(("G:", "C:")):
            column.append(match.group(0))
            continue
        page.append(tuple(column))
        column = []
        if token == "NL":
            continue
        pages.append(tuple(page))
        page = []
        if token == "END":
            ended = True
        else:
            waits.append(int(match.group(2)))
    column.extend(text[at:])
    if not ended and (column or page):
        page.append(tuple(column))
        pages.append(tuple(page))
    return Japanese(tuple(pages), tuple(waits))


# --- the store ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Store:
    """`disc/script/`, read back."""

    index: dict
    lines: dict[str, dict]
    scenes: tuple[dict, ...]
    root: Path

    @cached_property
    def scenes_by_event(self) -> dict[str, dict]:
        return {scene["event"]: scene for scene in self.scenes}

    @cached_property
    def japanese(self) -> dict[str, Japanese]:
        return {line_id: parse_japanese(record["text"]) for line_id, record in self.lines.items()}

    @cached_property
    def known_ids(self) -> frozenset[str]:
        """Every id a translation may legally address.

        `lines.jsonl` holds the ids with text on the disc; a voice-only line has none and
        is named only by a node of its event's flow graph, and the sample format lists it
        so the ids line up (`translation/samples/README.md`).
        """
        ids = set(self.lines)
        for scene in self.scenes:
            ids.update(node["line"] for node in scene["nodes"] if "line" in node)
        return frozenset(ids)

    @cached_property
    def event_of_line(self) -> dict[str, str]:
        """Which event owns each id, for a finding that wants to name the scene."""
        owner: dict[str, str] = {}
        for scene in self.scenes:
            for line_id in scene["lines"]:
                owner.setdefault(line_id, scene["event"])
            for node in scene["nodes"]:
                if "line" in node:
                    owner.setdefault(node["line"], scene["event"])
        return owner

    @cached_property
    def surfaces(self) -> dict[str, tuple[str, ...]]:
        """Every `<file>@<offset>` line no event claims, by the surface it sits on (the
        array's own id, or the line's for a one-line surface), in the store's order."""
        grouped: dict[str, list[str]] = {}
        for line_id, record in self.lines.items():
            if "@" in line_id and line_id not in self.event_of_line:
                key = record.get("array") or re.sub(r"\.\d+$", "", line_id)
                grouped.setdefault(key, []).append(line_id)
        return {key: tuple(ids) for key, ids in grouped.items()}


def load_store(script_dir: Path) -> Store:
    """Read the whole store. Raises `StoreMissing` when the import has not been run."""
    script_dir = Path(script_dir)
    index_path = script_dir / INDEX_NAME
    if not index_path.is_file():
        raise StoreMissing(
            f"{index_path} is missing -- run `./make.sh import` then `./make.sh extract` "
            f"against your own dump (README § 'The import step'). This repo ships none of "
            f"the game."
        )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    lines: dict[str, dict] = {}
    for raw in (script_dir / LINES_NAME).read_text(encoding="utf-8").splitlines():
        if raw.strip():
            record = json.loads(raw)
            lines[record["id"]] = record
    scenes = tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((script_dir / SCENES_DIR_NAME).glob("E*.json"))
    )
    return Store(index=index, lines=lines, scenes=scenes, root=script_dir)


# --- the facts both consumers derive ------------------------------------------------------------


def select_shape(record: dict) -> tuple[int, int] | None:
    """`(options, prompt lines)` the executable fixes for this select, or `None`.

    `g_select_lines` is read out of the executable, not the data, so the options map 1:1
    (`boku/layout.py` § "Select boxes never change their line count").
    """
    shape = record.get("select")
    if shape is None:
        return None
    return shape["lines"] - shape["prompt_lines"], shape["prompt_lines"]


def page_count(record: dict) -> int:
    """Pages the original draws. `pages_fixed_by_voice` says whether it may move."""
    return len(record.get("layout", {}).get("pages", ()))


def pages_fixed_by_voice(record: dict) -> bool:
    return bool(record.get("capacity", {}).get("pages_fixed_by_voice"))


def is_array(record: dict) -> bool:
    return record["kind"].startswith("array-")


def is_array_select(record: dict) -> bool:
    """A menu held in a code file (an **S** array), which `select_open_ptr` opens like an
    event select (`research/text-outside-events.md`)."""
    return record["kind"] == "array-S"


PLACED_BY_CODE = frozenset({"code-label", "sjis-title"})
"""Kinds with no text site: a label assembled from instruction immediates, and the
memory-card title in Shift-JIS. Translating one is a code patch, not a data rewrite."""


def original_bytes(record: dict, table: GlyphTable) -> bytes:
    """The site's own bytes, back from the token text `decode` wrote.

    `GlyphTable.encode` is the exact inverse of `decode` for every site on the disc
    (`boku/glyphs.py`, and the extract's own round-trip gate), so this reconstructs the
    bytes without going back to the image -- which is what lets a lint run against the
    store alone.
    """
    return table.encode(record["text"])


# --- play order ----------------------------------------------------------------------------------

_DAY_EQ = re.compile(r"\bday==(\d+)\b")
_HOUR = re.compile(r"\bhour(?:==|>=|<=|>|<)(\d+)\b")

SLOT_HOUR = {"0": 0, "1": 16, "2": 19}
"""A map name's 4th character is its time slot (`research/event-scripts.md`). Used only to
order scenes whose condition names no hour."""

_DAY_TEST = re.compile(r"^day(==|!=|>=|<=|>|<)(-?\d+)$")
_BREAK = "()&|"
_TOKENS = re.compile(r"[()&|]|[^()&|]+")
_COMPARE = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}


class _Unreadable(Exception):
    """A condition this module cannot parse. Always resolved in the scene's favour."""


def _tokens(condition: str) -> list[str]:
    """One token per bracket and operator, one per everything between them."""
    return [token.strip() for token in _TOKENS.findall(condition) if token.strip()]


def day_allows(condition: str | None, day: int) -> bool:
    """Could an event with this entry condition fire on `day`?

    Every `day` comparison is evaluated and **every other atom is taken as true**, so the
    answer is False only when no state of the flags, the clock or the map could let the
    event fire on that day. A condition this cannot parse is True, for the same reason:
    the cost of a false "reachable" is one extra row in a report, and the cost of a false
    "unreachable" is a line the player meets in Japanese that nothing ever mentions.
    """
    if not condition:
        return True

    def atom(token: str) -> bool:
        match = _DAY_TEST.match(token.replace(" ", ""))
        if match is None:
            return True
        return _COMPARE[match.group(1)](day, int(match.group(2)))

    def factor(tokens: list[str], at: int) -> tuple[bool, int]:
        if at >= len(tokens):
            raise _Unreadable
        token = tokens[at]
        if token == "(":
            value, at = alternatives(tokens, at + 1)
            if at >= len(tokens) or tokens[at] != ")":
                raise _Unreadable
            return value, at + 1
        if token in _BREAK:
            raise _Unreadable
        return atom(token), at + 1

    def conjunction(tokens: list[str], at: int) -> tuple[bool, int]:
        value, at = factor(tokens, at)
        while at < len(tokens) and tokens[at] == "&":
            right, at = factor(tokens, at + 1)
            value = value and right
        return value, at

    def alternatives(tokens: list[str], at: int) -> tuple[bool, int]:
        value, at = conjunction(tokens, at)
        while at < len(tokens) and tokens[at] == "|":
            right, at = conjunction(tokens, at + 1)
            value = value or right
        return value, at

    tokens = _tokens(condition)
    try:
        value, at = alternatives(tokens, 0)
    except _Unreadable:
        return True
    return value if at == len(tokens) else True


def scene_day(scene: dict) -> tuple[int | None, bool]:
    """`(day, derived)` — the extractor's day, else one read off a `day==N` condition.

    A **derived** day is the day of one `day==N` comparison somewhere in the condition,
    which is not the same as the only day the scene fires on: the comparison routinely
    sits in one branch of an `|` whose other branch is open (`E0710`'s
    `((day>6 & day!=30 & hour<16) | (day==30 & hour<11))` derives day 30 and plays every
    day after the 6th). Ask `scene_plays_on` which days reach a scene; a derived day is a
    label for the packet, never a filter.
    """
    day = scene["when"]["day"]
    if day is not None:
        return day, False
    found = _DAY_EQ.findall(scene["when"].get("condition") or "")
    if len(set(found)) == 1:
        return int(found[0]), True
    return None, False


def scene_dated_day(scene: dict) -> int | None:
    """The day the *data* fixes this scene to, or `None` when nothing does.

    The companion to `scene_day` for everything that **labels or groups by** a day. A
    derived day is one `day==N` inside the entry condition, routinely one branch of an
    `|` whose sibling covers the other days, so printing it as the scene's day states a
    falsehood: `E1006` derives day 11 from
    `… & day!=30 & ((day==11 & hour!=19) | (day!=11 & hour>6)) & …`, whose second branch
    is every day but 11, so `day_allows` puts the event on every day of the month but 30.
    `scene_plays_on` answers the other question, "can this day reach the scene".
    """
    day, derived = scene_day(scene)
    return None if derived else day


def scene_plays_on(scene: dict, day: int) -> bool:
    """Can `day` reach this scene? The one predicate every per-day view asks.

    A day the *extractor* dated is exclusive — it came off the event id, which fixes the
    day the engine fires the scene on. Anything else asks the entry condition, because a
    derived day (`scene_day`) and a missing day are both compatible with the scene firing
    on other days, and dropping a scene the player meets is the failure that matters.
    """
    dated = scene_dated_day(scene)
    if dated is not None:
        return dated == day
    return day_allows(scene["when"].get("condition"), day)


def scene_hour(scene: dict) -> int | None:
    """The hour the condition names, if it names exactly one."""
    if scene["when"]["meal_hour"] is not None:
        return int(scene["when"]["meal_hour"])
    hours = {int(value) for value in _HOUR.findall(scene["when"].get("condition") or "")}
    return min(hours) if len(hours) == 1 else None


def scene_sort_key(scene: dict) -> tuple:
    """The day the data dates the scene to, then the hour or time slot the script names,
    then the event id. A day only derived from the condition is not a day to sort under
    (`scene_dated_day`): those scenes order by hour with the rest of the undated tail."""
    day = scene_dated_day(scene)
    hour = scene_hour(scene)
    slots = scene["where"]["time_slots"] or ""
    slot_hour = min((SLOT_HOUR.get(c, 99) for c in slots), default=99)
    return (day is None, day or 0, hour if hour is not None else slot_hour, scene["id"])


def ordered_scenes(store: Store) -> list[dict]:
    """Every scene in the order this project reads them -- the reader's order too."""
    return sorted(store.scenes, key=scene_sort_key)


def scenes_of_day(store: Store, day: int) -> list[dict]:
    """The scenes a given in-game day can reach, in order (`scene_plays_on`).

    A scene the extractor dated belongs to that day alone. Every other scene is here when
    its entry condition's `day` tests can be true on this day, so a scene with no day and
    a scene whose `day==N` sits in one branch of an `|` both appear on every day that can
    reach them — which is how the game plays them, and why a packet for day 7 carries
    `E0710`. Whether the flags and the map also line up is a judgement this cannot make;
    `translation/days/README.md` makes it by hand.
    """
    return [scene for scene in ordered_scenes(store) if scene_plays_on(scene, day)]


def scenes_named(store: Store, events: Sequence[str]) -> list[dict]:
    """The named scenes, in play order. Raises on one the store does not hold."""
    by_event = store.scenes_by_event
    missing = [event for event in events if event not in by_event]
    if missing:
        raise StoreMissing(f"no scene in the store for {', '.join(sorted(missing))}")
    return sorted((by_event[event] for event in dict.fromkeys(events)), key=scene_sort_key)


def node_line(node: dict) -> str | None:
    return node.get("line")


def iter_play_order(scene: dict) -> Iterator[dict]:
    """The scene's nodes in the order `play_order` lists them, nodes first-class.

    `play_order` is ids; the packets want the node records, and a node id that is not in
    `nodes` (never seen, but the store is data) is skipped rather than crashing a packet.
    """
    by_id = {node["node"]: node for node in scene["nodes"]}
    for node_id in scene["play_order"]:
        node = by_id.get(node_id)
        if node is not None:
            yield node
