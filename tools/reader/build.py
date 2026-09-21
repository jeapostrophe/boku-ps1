#!/usr/bin/env python3
"""`PLAN TRN-06` — the scene reader: a static HTML site for reading the script in play order.

    uv run --no-project python tools/reader/build.py [--out work/reader/]

It reads the local import's script store (`disc/script/`, written by `boku extract`) and the
committed translation files, and writes one HTML page per event plus an index and a page per
speaker. It is **read-only over both**: nothing here writes a translation, and there is no
second editable representation of the script to keep in sync (README principle 3). Edits go
to the translation files; rebuild and reload.

**Its output is Japanese script, so it lands under the gitignored `work/` and can never be
tracked or published** (README principle 2). `--out` refuses any destination inside the repo
that is not under `work/` or `build/`.

What a scene page shows, in the order the game plays it: every node of the event's flow
graph, with the line id, the speaker label the script gives, the Japanese rendered both as
the game lays it out (vertical columns, right to left, one block per page) and as plain
text, and beside it the English from the translation files if there is any — never filled
in, never guessed, left visibly empty when it is missing. Alternatives for an id, the
translator's `#` notes, SELECT options linked to their branch targets, edge conditions in
the symbolic form the scene JSON gives, and hand-overs linked to the next event.

`--check` reports what the reader notices while loading the translation files — unknown line
ids, ids translated twice, SELECT option-count mismatches, page-count mismatches on voiced
lines. Those checks live in `checks.py` next to this file, so `PLAN PIPE-06`'s lint can hold
its own findings against exactly what the reader reports; the reader only reports them. It
does not measure pixels: that needs the encoder and the font, and lives in `boku/layout.py`,
so a line is OVERFLOW-flagged only when the translator wrote `# OVERFLOW` above it.

`--selftest` builds a site from a synthetic two-scene store held in a temporary directory and
checks the result, so the tool has a gate that needs neither a disc nor `tests/`.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for directory in (ROOT, HERE):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from checks import SHAPE_KINDS, Problem, check, select_fields, select_shape  # noqa: E402

from boku.script_store import scene_dated_day  # noqa: E402
from boku.translation import SampleScenes, TranslationEntry  # noqa: E402

DEFAULT_SCRIPT_DIR = ROOT / "disc" / "script"
DEFAULT_TRANSLATION_DIRS = (ROOT / "translation" / "samples", ROOT / "translation" / "days")
DEFAULT_OUT_DIR = ROOT / "work" / "reader"

WRITABLE_ROOTS = ("work", "build")
"""The only directories inside the repo this tool may write to — both gitignored."""

SLOT_HOUR = {"0": 0, "1": 16, "2": 19}
"""A map name's 4th character is the time slot: `0` below hour 16, `1` until 18, `2` from 19
(research/event-scripts.md § "Map names and `EVVER.BIN`"). Used only to order scenes whose
condition names no hour, and shown as the slot digit, never as a clock time."""


# --- the script store -------------------------------------------------------------------------


class ReaderRefused(Exception):
    """The reader will not run — a missing import, or a destination it must not write to."""


_TOKEN = re.compile(r"\{(NL|END|PAGE:(\d+)|G:\d+)\}")


@dataclass(frozen=True)
class Japanese:
    """One decoded line as the game lays it out: pages of columns of single glyphs.

    `{NL}` opens a column — the renderer steps `x -= 14`, so a later column is drawn to the
    *left* of an earlier one (research/text-format.md, control word `0x8001`). `{PAGE:p}`
    ends a page and carries the frame countdown that turns it in time with the voice clip.
    """

    pages: tuple[tuple[tuple[str, ...], ...], ...] = ()
    waits: tuple[int, ...] = ()

    @property
    def column_counts(self) -> tuple[tuple[int, ...], ...]:
        """Glyphs per column, per page — the shape `disc/script/lines.jsonl` records."""
        return tuple(tuple(len(column) for column in page) for page in self.pages)

    def plain(self) -> str:
        """The same text linearly: ` / ` between columns, ` // ` between pages."""
        return " // ".join(" / ".join("".join(c) for c in page) for page in self.pages)


def parse_japanese(text: str) -> Japanese:
    """Split a decoded line into pages and columns. One cell per glyph, `{G:n}` included."""
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
        if token.startswith("G:"):
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


@dataclass(frozen=True)
class Store:
    """`disc/script/`, as the reader needs it."""

    index: dict
    lines: dict[str, dict]
    scenes: tuple[dict, ...]
    japanese: dict[str, Japanese]


def load_store(script_dir: Path) -> Store:
    script_dir = Path(script_dir)
    index_path = script_dir / "index.json"
    lines_path = script_dir / "lines.jsonl"
    # Every file this reads is refused by name: a half-written or foreign store must say
    # which import step to run, not raise a FileNotFoundError or a KeyError at the page
    # that first touches the missing part.
    for needed in (index_path, lines_path):
        if not needed.is_file():
            raise ReaderRefused(
                f"{needed} is missing — run `./make.sh import` then `./make.sh extract` "
                f"against your own dump (README § 'The import step')."
            )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if "counts" not in index:
        raise ReaderRefused(
            f"{index_path} has no `counts` — it is not a script store this reader can read. "
            f"Re-run `./make.sh extract` against your own dump."
        )
    lines: dict[str, dict] = {}
    for raw in lines_path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            record = json.loads(raw)
            lines[record["id"]] = record
    scenes = tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((script_dir / "scenes").glob("E*.json"))
    )
    japanese = {line_id: parse_japanese(record["text"]) for line_id, record in lines.items()}
    return Store(index=index, lines=lines, scenes=scenes, japanese=japanese)


# --- play order -------------------------------------------------------------------------------

_HOUR = re.compile(r"\bhour(==|>=|<=|>|<)(\d+)\b")

ANY_DAY_TEXT = "any day"
"""What a scene not fixed to a day reads as, wherever this site prints a day."""

ANY_DAY_ANCHOR = "day-none"
"""The calendar section those scenes are listed under."""


def day_text(scene: dict) -> str:
    """How this scene's day reads in a heading, a fact list or a table cell.

    Every day this site prints, groups by or sorts on is
    `boku.script_store.scene_dated_day`'s, which is `None` for a day only derived from
    the entry condition.
    """
    day = scene_dated_day(scene)
    return ANY_DAY_TEXT if day is None else f"day {day}"


HOUR_TEXT = {
    "==": "{hour}:00",
    ">=": "from {hour}:00",
    ">": "after {hour}:00",
    "<": "before {hour}:00",
    "<=": "by {hour}:00",
}
"""How each comparator in an `hour` condition reads. An upper bound is not a clock time:
`hour<14` is every hour of the day up to 14:00, so it is shown as "before 14:00" and
ordered by the map's time slot — printing it as "14:00" put 205 of the 677 scenes at a
time they can never play."""


@dataclass(frozen=True)
class SceneHour:
    """The one hour an event's condition names, with the comparator that names it."""

    comparator: str
    hour: int

    @property
    def ordering(self) -> int | None:
        """The hour to sort the scene under, or `None` when the condition only bounds the
        hour from above and so says nothing about when the scene actually plays."""
        return None if self.comparator in ("<", "<=") else self.hour

    def text(self) -> str:
        return HOUR_TEXT[self.comparator].format(hour=self.hour)


def scene_hour(scene: dict) -> SceneHour | None:
    """The hour the condition names, with its comparator, if it names exactly one."""
    if scene["when"]["meal_hour"] is not None:
        return SceneHour("==", int(scene["when"]["meal_hour"]))
    found = {
        (comparator, int(value))
        for comparator, value in _HOUR.findall(scene["when"].get("condition") or "")
    }
    return SceneHour(*found.pop()) if len(found) == 1 else None


def scene_sort_key(scene: dict) -> tuple:
    """The day the data dates the scene to, then the hour or the time slot where the
    script says one, then the event id. A derived day is not one (`scene_dated_day`), so
    those scenes order by hour among the tail the calendar lists under "any day"."""
    day = scene_dated_day(scene)
    hour = scene_hour(scene)
    ordering = hour.ordering if hour is not None else None
    slots = scene["where"]["time_slots"] or ""
    slot_hour = min((SLOT_HOUR.get(c, 99) for c in slots), default=99)
    return (day is None, day or 0, slot_hour if ordering is None else ordering, scene["id"])


def ordered_scenes(store: Store) -> list[dict]:
    return sorted(store.scenes, key=scene_sort_key)


# --- the translation files --------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One row of a translation file, with the `#` notes written immediately above it."""

    line_id: str
    speaker: str
    text: str
    origin: str
    """`<basename>:<line>` — deliberately the same string `boku.translation` builds for this
    row, because `checks._loader_agreement` matches the reader's rows to the loader's
    entries by it."""
    source: str = ""
    """The file this row came from, keyed so two files cannot collide (`file_label`)."""
    notes: tuple[str, ...] = ()

    @property
    def voice_only(self) -> bool:
        return self.speaker == SampleScenes.VOICE_ONLY or not self.text

    @property
    def entry(self) -> TranslationEntry:
        """The same `TranslationEntry` the build's loader would make of this row."""
        if self.speaker == SampleScenes.SELECT:
            return TranslationEntry(
                line_id=self.line_id,
                speaker=self.speaker,
                options=tuple(o.strip() for o in self.text.split(SampleScenes.OPTION)),
                origin=self.origin,
            )
        return TranslationEntry(
            line_id=self.line_id,
            speaker=self.speaker,
            pages=tuple(p.strip() for p in self.text.split(SampleScenes.PAGE_BREAK)),
            origin=self.origin,
        )


@dataclass
class Translation:
    """Every row of every translation file, keyed by line id, in file order."""

    rows: dict[str, list[Row]] = field(default_factory=dict)
    file_notes: dict[str, tuple[tuple[str, ...], ...]] = field(default_factory=dict)
    ids_by_file: dict[str, set[str]] = field(default_factory=dict)
    paths: tuple[Path, ...] = ()
    problems: tuple[Problem, ...] = ()
    built: dict[str, TranslationEntry] = field(default_factory=dict)
    """What `boku.translation` — the loader the build reads English through — makes of these
    same files. An id given English twice has several rows here but one entry there, and the
    page says which row the build ignores."""

    def of(self, line_id: str) -> list[Row]:
        return self.rows.get(line_id, [])

    def built_origin(self, line_id: str) -> str | None:
        """Where the row the *build* uses for this id was written, if there is one."""
        entry = self.built.get(line_id)
        return entry.origin if entry is not None else None

    def english_rows(self, line_id: str) -> list[Row]:
        return [row for row in self.of(line_id) if not row.voice_only]

    def notes_for(self, event: str) -> list[tuple[str, tuple[str, ...]]]:
        """File-level note blocks from every file that translates part of this event."""
        out: list[tuple[str, tuple[str, ...]]] = []
        for name, ids in sorted(self.ids_by_file.items()):
            if any(i.split(".", 1)[0] == event for i in ids):
                out.extend((name, block) for block in self.file_notes.get(name, ()))
        return out


def file_label(path: Path) -> str:
    """The name a translation file is keyed and listed under — its path inside the repo.

    Not `path.name`: `translation/days` and `translation/samples` may each hold a file of
    the same basename, and keying note blocks and id lists by the basename alone merges the
    two files into one and drops one of their notes.
    """
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_translation_file(path: Path) -> tuple[list[Row], list[tuple[str, ...]], list[Problem]]:
    """Rows, free-standing note blocks, and the problems the format itself shows."""
    rows: list[Row] = []
    loose: list[tuple[str, ...]] = []
    problems: list[Problem] = []
    block: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.rstrip()
        if not line:
            if block:
                loose.append(tuple(block))
                block = []
            continue
        if line.lstrip().startswith("#"):
            block.append(line.lstrip().lstrip("#").strip())
            continue
        where = f"{path.name}:{number}"
        fields = line.split("\t")
        if len(fields) < 2:
            problems.append(
                Problem("malformed", where, "no tab; a row is `id <TAB> speaker <TAB> English`")
            )
            block = []
            continue
        rows.append(
            Row(
                line_id=fields[0].strip(),
                speaker=fields[1].strip(),
                text=fields[2].strip() if len(fields) > 2 else "",
                origin=where,
                source=file_label(path),
                notes=tuple(block),
            )
        )
        block = []
    if block:
        loose.append(tuple(block))
    return rows, loose, problems


def load_translation(paths: Sequence[Path]) -> Translation:
    translation = Translation(paths=tuple(sorted(paths)))
    problems: list[Problem] = []
    for path in translation.paths:
        rows, loose, file_problems = parse_translation_file(path)
        problems.extend(file_problems)
        label = file_label(path)
        translation.file_notes[label] = tuple(loose)
        seen = translation.ids_by_file.setdefault(label, set())
        for row in rows:
            translation.rows.setdefault(row.line_id, []).append(row)
            seen.add(row.line_id)
    translation.problems = tuple(problems)
    translation.built = {
        entry.line_id: entry for entry in SampleScenes.from_paths(translation.paths)
    }
    return translation


def translation_paths(sources: Sequence[Path]) -> list[Path]:
    """Every `*.txt` under the given files and directories; missing directories are fine."""
    found: list[Path] = []
    for source in sources:
        source = Path(source)
        if source.is_dir():
            found.extend(sorted(source.glob("*.txt")))
        elif source.is_file():
            found.append(source)
    return found


# --- what the reader notices, as marks on a page --------------------------------------------------
# The findings themselves are `checks.py`; what is left here is how a page shows them.


@dataclass(frozen=True)
class Flags:
    """Per-line marks a page shows beside the line id."""

    overflow: frozenset[str] = frozenset()
    """Lines the *translator* marked `# OVERFLOW` — a page that does not fit the dialogue
    band, translated in full anyway (translation/days/README.md; nothing is shortened to
    fit, README § "Who this is for"). The reader does not measure pixels: that needs the
    encoder and the font, and is `PIPE-06`'s lint over `boku/layout.py`."""

    shape: frozenset[str] = frozenset()
    """Lines the reader itself found cannot take the original's shape (`SHAPE_KINDS`)."""

    def marks(self, line_id: str) -> list[str]:
        out = []
        if line_id in self.overflow:
            out.append("OVERFLOW")
        if line_id in self.shape:
            out.append("shape")
        return out


OVERFLOW_NOTE = "OVERFLOW"
"""The marker a translator's note line starts with to flag a page that overruns the band."""


def flags_of(translation: Translation, problems: Iterable[Problem]) -> Flags:
    overflow = {
        line_id
        for line_id, rows in translation.rows.items()
        if any(note.startswith(OVERFLOW_NOTE) for row in rows for note in row.notes)
    }
    shape = {
        problem.message.split(" ", 1)[0] for problem in problems if problem.kind in SHAPE_KINDS
    }
    return Flags(frozenset(overflow), frozenset(shape))


# --- HTML ---------------------------------------------------------------------------------------


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def scene_href(event: str) -> str:
    return f"scene-{slug(event)}.html"


def speaker_href(label: str) -> str:
    return f"speaker-{slug(label)}.html"


STYLE = """\
/* The scene reader's whole stylesheet. Plain on purpose: no framework, no script. */
:root {
  --bg: #fbfaf7; --fg: #1d1b17; --dim: #6a655b; --rule: #ded8cc;
  --card: #ffffff; --en: #123a63; --missing: #8d2f2f; --accent: #2c6b45;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #15140f; --fg: #e9e5db; --dim: #9c968a; --rule: #34312a;
    --card: #1d1b16; --en: #9ec7f0; --missing: #ef9a9a; --accent: #8fd0a5;
  }
}
* { box-sizing: border-box; }
body { margin: 0 auto; padding: 1rem 1rem 4rem; max-width: 62rem; background: var(--bg);
  color: var(--fg); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: var(--en); }
a:focus-visible, summary:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
h1 { font-size: 1.5rem; margin: .2rem 0; }
h2 { font-size: 1.15rem; margin: 2rem 0 .5rem; border-bottom: 1px solid var(--rule); }
h3 { font-size: 1rem; margin: 1.2rem 0 .4rem; }
nav.bar { display: flex; flex-wrap: wrap; gap: .75rem; padding: .5rem 0;
  border-bottom: 1px solid var(--rule); font-size: .9rem; }
.sub, .dim { color: var(--dim); }
.skip { position: absolute; left: -9999px; }
.skip:focus { position: static; }
dl.facts { display: grid; grid-template-columns: max-content 1fr; gap: .15rem .8rem;
  margin: .6rem 0; font-size: .9rem; }
dl.facts dt { color: var(--dim); }
dl.facts dd { margin: 0; }
ol.nodes { list-style: none; margin: 0; padding: 0; }
li.node { border: 1px solid var(--rule); border-radius: 6px; background: var(--card);
  margin: .9rem 0; padding: .6rem .8rem; }
li.node.chain { border-style: dashed; }
.meta { display: flex; flex-wrap: wrap; gap: .5rem; align-items: baseline;
  font-size: .85rem; color: var(--dim); }
.lineid { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--fg); }
.speaker { font-weight: 600; color: var(--fg); }
.badge { border: 1px solid var(--rule); border-radius: 999px; padding: 0 .5rem; }
.badge.flag { border-color: var(--missing); color: var(--missing); }
.pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1rem;
  margin-top: .5rem; }
@media (max-width: 720px) { .pair { grid-template-columns: 1fr; } }
.jp, .en { min-width: 0; }
.cols { display: flex; flex-wrap: wrap; gap: .8rem; overflow-x: auto; padding-bottom: .2rem; }
.page { border-left: 2px solid var(--rule); padding-left: .5rem; }
.vert { writing-mode: vertical-rl; text-orientation: upright; line-height: 1.15;
  font-size: 1.2rem; white-space: pre; }
.plain { font-size: .9rem; color: var(--dim); margin: .3rem 0 0; word-break: break-all; }
.en p { margin: .1rem 0; color: var(--en); }
.en p.prompt { font-weight: 600; }
.en .pageno { color: var(--dim); font-size: .8rem; }
.empty { color: var(--missing); font-style: italic; }
.alt { border-left: 3px solid var(--rule); padding-left: .5rem; margin-top: .4rem; }
ul.notes { margin: .5rem 0 0; padding-left: 1.1rem; font-size: .88rem; color: var(--dim); }
ul.flow { margin: .5rem 0 0; padding-left: 1.1rem; font-size: .85rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85em; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { text-align: left; padding: .25rem .5rem; border-bottom: 1px solid var(--rule);
  vertical-align: top; }
th { color: var(--dim); font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.untranslated { color: var(--missing); }
.legend { font-size: .85rem; color: var(--dim); }
"""


def page(title: str, body: str, *, heading_nav: str = "") -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n"
        '<link rel="stylesheet" href="style.css">\n'
        "</head>\n<body>\n"
        '<a class="skip" href="#main">Skip to content</a>\n'
        f"{heading_nav}"
        f'<main id="main">\n{body}\n</main>\n'
        "</body>\n</html>\n"
    )


def bar(items: Sequence[str]) -> str:
    return '<nav class="bar">' + " ".join(items) + "</nav>\n"


def facts(pairs: Sequence[tuple[str, str]]) -> str:
    rows = "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs if v)
    return f'<dl class="facts">{rows}</dl>\n' if rows else ""


def japanese_html(japanese: Japanese) -> str:
    if not japanese.pages:
        return '<p class="empty">(no text on the disc)</p>'
    blocks = []
    for number, columns in enumerate(japanese.pages):
        longest = max((len(c) for c in columns), default=0)
        text = "\n".join("".join(column) for column in columns)
        wait = ""
        if number < len(japanese.waits):
            wait = f'<span class="pageno"> wait {japanese.waits[number]}</span>'
        label = ""
        if len(japanese.pages) > 1:
            label = f'<div class="pageno dim">page {number + 1}{wait}</div>'
        blocks.append(
            f'<div class="page">{label}'
            f'<div class="vert" style="height: {longest + 1}em">{esc(text)}</div></div>'
        )
    return (
        '<div class="cols">'
        + "".join(blocks)
        + f'</div><p class="plain">{esc(japanese.plain())}</p>'
    )


def target_html(target: str) -> str:
    """A branch target, linked to its node — except `END`, which is not a node and has no
    anchor on any page."""
    return esc(target) if target == "END" else f'<a href="#{esc(target)}">{esc(target)}</a>'


def english_html(
    rows: Sequence[Row],
    *,
    targets: Sequence[str] = (),
    prompt_lines: int = 0,
    built_origin: str | None = None,
) -> str:
    if not rows:
        return '<p class="empty">(not translated yet)</p>'
    out = []
    for number, row in enumerate(rows):
        entry = row.entry
        if entry.is_select:
            prompts, options = select_fields(entry, prompt_lines)
            items = []
            for index, option in enumerate(options):
                link = targets[index] if index < len(targets) else ""
                arrow = f" &rarr; {target_html(link)}" if link else ""
                items.append(f"<li>{esc(option)}{arrow}</li>")
            body = (
                "".join(f'<p class="prompt">{esc(prompt)}</p>' for prompt in prompts)
                + "<ol>"
                + "".join(items)
                + "</ol>"
            )
        else:
            body = "".join(
                f'<p><span class="pageno">{index + 1}.</span> {esc(text)}</p>'
                if len(entry.pages) > 1
                else f"<p>{esc(text)}</p>"
                for index, text in enumerate(entry.pages)
            )
        origin = f'<div class="pageno dim">{esc(row.speaker)} &middot; {esc(row.origin)}</div>'
        ignored = built_origin is not None and row.origin != built_origin
        if number == 0 and not ignored:
            out.append(body + origin)
        else:
            label = "the build ignores this row" if ignored else "alternative"
            mark = f'<div class="pageno dim">{label}</div>'
            out.append(f'<div class="alt">{mark}{body}{origin}</div>')
    return "".join(out)


def english_cell(store: Store, translation: Translation, line_id: str, rows: Sequence[Row]) -> str:
    """One table cell of English — the row the build would use, or the empty-slot marker."""
    if not rows:
        return '<span class="empty">(not translated yet)</span>'
    return english_html(
        rows[:1],
        prompt_lines=select_prompt_lines(store, line_id),
        built_origin=translation.built_origin(line_id),
    )


def notes_html(notes: Sequence[str]) -> str:
    if not notes:
        return ""
    return '<ul class="notes">' + "".join(f"<li>{esc(n)}</li>" for n in notes) + "</ul>"


# --- the scene page -------------------------------------------------------------------------------


def select_prompt_lines(store: Store, line_id: str) -> int:
    """How many of a `[SEL]` row's fields are the question rather than an option."""
    shape = select_shape(store, line_id)
    return shape[1] if shape is not None else 0


def select_targets(scene: dict, node_id: str, options: int) -> list[str]:
    """The branch target of each `optN` edge leaving this select node, in option order."""
    targets = [""] * options
    for edge in scene["edges"]:
        if edge["from"] != node_id:
            continue
        match = re.fullmatch(r"opt(\d+)", edge["condition"] or "")
        if match and int(match.group(1)) < options:
            targets[int(match.group(1))] = edge["to"]
    return targets


def flow_html(scene: dict, node_id: str) -> str:
    items = []
    for edge in scene["edges"]:
        if edge["from"] != node_id:
            continue
        condition = f" when <code>{esc(edge['condition'])}</code>" if edge["condition"] else ""
        items.append(f"<li>&rarr; {target_html(edge['to'])}{condition}</li>")
    return '<ul class="flow">' + "".join(items) + "</ul>" if items else ""


@dataclass(frozen=True)
class SceneCounts:
    lines: int = 0
    translated: int = 0
    overflow: int = 0
    shape: int = 0

    @property
    def untranslated(self) -> int:
        return self.lines - self.translated

    def html(self) -> str:
        parts = [
            f"{self.lines} line(s)",
            f"{self.translated} translated",
            f'<span class="untranslated">{self.untranslated} untranslated</span>',
        ]
        if self.overflow:
            parts.append(f'<span class="untranslated">{self.overflow} OVERFLOW</span>')
        if self.shape:
            parts.append(f'<a class="untranslated" href="checks.html">{self.shape} shape</a>')
        return " &middot; ".join(parts)


def scene_counts(scene: dict, translation: Translation, flags: Flags) -> SceneCounts:
    ids = scene["lines"]
    return SceneCounts(
        lines=len(ids),
        translated=sum(1 for i in ids if translation.english_rows(i)),
        overflow=sum(1 for i in ids if i in flags.overflow),
        shape=sum(1 for i in ids if i in flags.shape),
    )


def reached_lines(scene: dict) -> set[str]:
    return {node["line"] for node in scene["nodes"] if "line" in node}


def scene_owned_lines(scenes: Iterable[dict]) -> set[str]:
    """Every id that appears on some scene page, reached by a node or not."""
    owned: set[str] = set()
    for scene in scenes:
        owned.update(scene["lines"])
        owned.update(reached_lines(scene))
    return owned


def event_link(event: str | None) -> str:
    return f'<a href="{scene_href(event)}">{esc(event)}</a>' if event else "&mdash;"


def handover_link(token: str) -> str:
    """`MAP:I16` or `MOVIE22:A01>E0004` — link the event half when there is one."""
    if ">" in token:
        head, event = token.rsplit(">", 1)
        return f'{esc(head)}&gt;<a href="{scene_href(event)}">{esc(event)}</a>'
    return esc(token)


def line_anchors(scene: dict) -> dict[str, str]:
    """Where each of this event's lines is anchored on its own scene page: the first node
    that names it, or the line's own id where the flow graph reaches it from nowhere and it
    is rendered under "Lines no node reaches". An id absent from this map is on no page."""
    anchors: dict[str, str] = {}
    for node in scene["nodes"]:
        if "line" in node:
            anchors.setdefault(node["line"], node["node"])
    for line_id in scene["lines"]:
        anchors.setdefault(line_id, line_id)
    return anchors


def day_table_html(quiz: dict, scene: dict) -> str:
    """The per-day message table a native routine picks from — the dinner quiz's questions
    (`quiz`, with the right answer) or the dinner menu (`menu`). The reader shows whichever
    the extract recorded, with its own columns, rather than assuming one shape.

    Each `message` is resolved against the page it would land on rather than linked blind:
    the tables the executable reads are longer than some of the events they are attached to,
    and a fabricated anchor reads as "day 1 uses line E1502.2" where no such line exists.
    """
    name, rows = next(
        ((k, v) for k, v in quiz.items() if isinstance(v, list) and v and isinstance(v[0], dict)),
        ("", []),
    )
    if not rows:
        return ""
    event = scene["event"]
    anchors = line_anchors(scene)
    columns = list(rows[0])
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    missing = 0

    def cell(row: dict, column: str) -> str:
        nonlocal missing
        value = row.get(column, "")
        if column != "message":
            return esc(value)
        line_id = f"{event}.{value}"
        anchor = anchors.get(line_id)
        if anchor is None:
            missing += 1
            return f'{esc(line_id)} <span class="badge flag">no such line</span>'
        return f'<a href="#{esc(anchor)}">{esc(line_id)}</a>'

    cells = "".join(
        "<tr>" + "".join(f'<td class="num">{cell(row, c)}</td>' for c in columns) + "</tr>"
        for row in rows
    )
    note = (
        f" {missing} row(s) name a message this event has no line for — the table in the "
        f"executable is longer than the event's text."
        if missing
        else ""
    )
    return (
        f'<h2>Per-day {esc(name)}</h2><p class="legend">Which message this event uses on which '
        f"day, chosen by native routine(s) {esc(quiz.get('routines', ''))}.{note}</p>"
        f"<table><tr>{head}</tr>{cells}</table>"
    )


def scene_page(
    scene: dict,
    store: Store,
    translation: Translation,
    flags: Flags,
    neighbours: tuple[dict | None, dict | None],
) -> str:
    event = scene["event"]
    day = scene_dated_day(scene)
    hour = scene_hour(scene)
    when_text = day_text(scene)
    previous, following = neighbours
    anchor = ANY_DAY_ANCHOR if day is None else f"day-{day}"
    links = [
        '<a href="index.html">index</a>',
        f'<a href="index.html#{anchor}">{esc(when_text)}</a>',
    ]
    if previous is not None:
        links.append(
            f'<a href="{scene_href(previous["event"])}">&larr; {esc(previous["event"])}</a>'
        )
    if following is not None:
        links.append(
            f'<a href="{scene_href(following["event"])}">{esc(following["event"])} &rarr;</a>'
        )
    links.append('<a href="checks.html">checks</a>')

    counts = scene_counts(scene, translation, flags)
    triggers = ", ".join(f"{esc(k)} &times;{esc(v)}" for k, v in scene["where"]["triggers"].items())
    actors = ", ".join(
        f"slot {k}: {', '.join(str(m) for m in v)}" for k, v in scene["actors"].items()
    )
    body = [
        f'<h1>{esc(event)} <span class="sub">{esc(when_text)}</span></h1>',
        facts(
            [
                ("when", esc(when_text) + (f", {esc(hour.text())}" if hour is not None else "")),
                (
                    "condition",
                    f"<code>{esc(scene['when']['condition'])}</code>"
                    if scene["when"]["condition"]
                    else "",
                ),
                ("maps", esc(", ".join(scene["where"]["maps"]))),
                ("time slots", esc(scene["where"]["time_slots"])),
                ("triggers", triggers),
                ("actors", esc(actors)),
                (
                    "copies",
                    f"{scene['copies']} member(s)" + (", also in EV.BIN" if scene["in_ev"] else ""),
                ),
                ("lines", counts.html()),
                (
                    "conditions",
                    "summarised — the graph simplifies a complex condition tree"
                    if scene["conditions_summarised"]
                    else "",
                ),
            ]
        ),
    ]
    entry = [e for e in scene["edges"] if e["from"] == "ENTRY"]
    if entry:
        starts = ", ".join(
            target_html(e["to"])
            + (f" when <code>{esc(e['condition'])}</code>" if e["condition"] else "")
            for e in entry
        )
        body.append(f'<p class="legend">Entry: {starts}</p>')

    body.append('<ol class="nodes">')
    for node in scene["nodes"]:
        body.append(node_html(node, scene, store, translation, flags))
    body.append("</ol>")

    unreached = [i for i in scene["lines"] if i not in reached_lines(scene)]
    if unreached:
        body.append(
            '<h2>Lines no node reaches</h2><p class="legend">Text of this event that the flow '
            "graph never names: a native routine in the executable picks it (the per-day table "
            "below, where there is one). It counts in this scene's totals.</p>"
            '<ol class="nodes">'
            + "".join(loose_line_html(line_id, store, translation, flags) for line_id in unreached)
            + "</ol>"
        )

    if scene["handovers"]:
        rows = "".join(
            f"<tr><td>{esc(h['kind'])}</td><td>{esc(h['map'])}</td>"
            f"<td>{event_link(h['event'])}</td>"
            f"<td>{'reachable' if h['reachable'] else 'unreachable'}</td></tr>"
            for h in scene["handovers"]
        )
        body.append(
            "<h2>Hands over to</h2><table><tr><th>kind</th><th>map</th><th>event</th>"
            f"<th></th></tr>{rows}</table>"
        )
    if scene.get("dinner_quiz"):
        body.append(day_table_html(scene["dinner_quiz"], scene))
    if scene["speaker_mismatches"]:
        rows = "".join(
            f"<tr><td><code>{esc(m['node'])}</code></td><td>{esc(m['inline_label'])}</td>"
            f"<td>{esc(m['slot_name'])}</td></tr>"
            for m in scene["speaker_mismatches"]
        )
        body.append(
            '<h2>Speaker mismatches</h2><p class="legend">The label inside the line disagrees '
            "with the actor slot the opcode names.</p>"
            f"<table><tr><th>node</th><th>in the line</th><th>slot</th></tr>{rows}</table>"
        )
    file_notes = translation.notes_for(event)
    if file_notes:
        blocks = "".join(f"<h3>{esc(name)}</h3>{notes_html(block)}" for name, block in file_notes)
        body.append(f"<h2>Notes from the translation files</h2>{blocks}")

    return page(
        f"{event} — {when_text} — scene reader",
        "\n".join(body),
        heading_nav=bar(links),
    )


def node_html(node: dict, scene: dict, store: Store, translation: Translation, flags: Flags) -> str:
    node_id = node["node"]
    meta = [
        f'<span class="lineid">{esc(node_id)}</span>',
        f'<span class="badge">{esc(node["opcode"])}</span>',
    ]
    if "hands_over_to" in node:
        meta.append('<span class="speaker">chain</span>')
        body = f"<p>Hands over to {handover_link(node['hands_over_to'])}</p>"
        return (
            f'<li class="node chain" id="{esc(node_id)}"><div class="meta">'
            + "".join(meta)
            + f"</div>{body}{flow_html(scene, node_id)}</li>"
        )
    if "native" in node:
        meta.append('<span class="speaker">native routine</span>')
        body = f"<p>Handled by the executable: <code>{esc(node['native'])}</code></p>"
        return (
            f'<li class="node chain" id="{esc(node_id)}"><div class="meta">'
            + "".join(meta)
            + f"</div>{body}{flow_html(scene, node_id)}</li>"
        )

    line_id = node["line"]
    record = store.lines.get(line_id)
    meta.insert(1, f'<span class="speaker">{esc(node["speaker"])}</span>')
    meta.insert(2, f'<span class="lineid">{esc(line_id)}</span>')
    if "slot" in node:
        meta.append(f'<span class="badge">slot {node["slot"]}</span>')
    if record is not None:
        if record.get("voiced"):
            clip = (record.get("voice") or {}).get("clip", "")
            meta.append(f'<span class="badge">voice {esc(clip)}</span>')
        pages = record.get("layout", {}).get("pages", [])
        meta.append(f'<span class="badge">{len(pages)} page(s), {record["glyphs"]} glyphs</span>')
        meta.append(
            f'<span class="badge">{record["capacity"]["bytes"]} bytes &times; '
            f"{record['capacity']['copies']}</span>"
        )
    meta.extend(f'<span class="badge flag">{mark}</span>' for mark in flags.marks(line_id))

    japanese = store.japanese.get(line_id)
    if record is None:
        jp = '<p class="empty">(voice only — no text on the disc)</p>'
    else:
        jp = japanese_html(japanese or Japanese())

    rows = translation.english_rows(line_id)
    targets: list[str] = []
    if "select" in node:
        # The option count is the executable's, never the translation's: a row with the
        # wrong number of fields is a finding, not a different set of branches.
        targets = select_targets(scene, node_id, node["select"]["options"])
    en = english_html(
        rows,
        targets=targets,
        prompt_lines=select_prompt_lines(store, line_id),
        built_origin=translation.built_origin(line_id),
    )

    select_note = ""
    if "select" in node:
        shape = node["select"]
        select_note = (
            f'<p class="legend">SELECT type {shape["type"]}.{shape["variant"]}: '
            f"{shape['options']} option(s), {shape['prompt_lines']} prompt line(s), "
            f"{'cancellable' if shape['cancellable'] else 'not cancellable'}.</p>"
        )
    notes = [n for row in translation.of(line_id) for n in row.notes]
    return (
        f'<li class="node" id="{esc(node_id)}"><div class="meta">'
        + "".join(meta)
        + f"</div>{select_note}"
        f'<div class="pair"><section class="jp">{jp}</section>'
        f'<section class="en">{en}</section></div>'
        f"{notes_html(notes)}{flow_html(scene, node_id)}</li>"
    )


def loose_line_html(line_id: str, store: Store, translation: Translation, flags: Flags) -> str:
    """One of the event's lines that no node names — the same pair, without a flow."""
    record = store.lines.get(line_id)
    meta = [f'<span class="lineid">{esc(line_id)}</span>']
    if record is not None:
        meta.append(f'<span class="badge">{esc(record["kind"])}</span>')
        meta.append(f'<span class="badge">{record["glyphs"]} glyphs</span>')
    meta.extend(f'<span class="badge flag">{mark}</span>' for mark in flags.marks(line_id))
    jp = japanese_html(store.japanese.get(line_id) or Japanese())
    en = english_html(
        translation.english_rows(line_id),
        prompt_lines=select_prompt_lines(store, line_id),
        built_origin=translation.built_origin(line_id),
    )
    notes = [n for row in translation.of(line_id) for n in row.notes]
    return (
        f'<li class="node" id="{esc(line_id)}"><div class="meta">'
        + "".join(meta)
        + f'</div><div class="pair"><section class="jp">{jp}</section>'
        f'<section class="en">{en}</section></div>{notes_html(notes)}</li>'
    )


# --- the index, the speakers, the leftovers -------------------------------------------------------


def index_page(
    store: Store,
    translation: Translation,
    scenes: Sequence[dict],
    flags: Flags,
    problems: Sequence[Problem],
    speakers: dict[str, list],
) -> str:
    by_day: dict[int | None, list[dict]] = {}
    for scene in scenes:
        by_day.setdefault(scene_dated_day(scene), []).append(scene)
    total = SceneCounts(
        lines=sum(scene_counts(s, translation, flags).lines for s in scenes),
        translated=sum(scene_counts(s, translation, flags).translated for s in scenes),
        overflow=sum(scene_counts(s, translation, flags).overflow for s in scenes),
        shape=sum(scene_counts(s, translation, flags).shape for s in scenes),
    )
    files = ", ".join(esc(file_label(p)) for p in translation.paths) or "none found"
    body = [
        "<h1>Boku no Natsuyasumi — scene reader</h1>",
        '<p class="legend">Read-only over the translation files (<code>PLAN TRN-06</code>, '
        "README principle 3). The Japanese comes from your own import and never leaves "
        "<code>work/</code>.</p>",
        facts(
            [
                (
                    "script",
                    f"{store.index['counts']['events']} events, "
                    f"{store.index['counts']['logical_lines']} logical lines",
                ),
                ("translation", files),
                ("lines in scenes", total.html()),
                ("checks", f'<a href="checks.html">{len(problems)} thing(s) noticed</a>'),
                ("other text", '<a href="other.html">arrays, menus and code labels</a>'),
            ]
        ),
        "<h2>Speakers</h2><p>"
        + " &middot; ".join(
            f'<a href="{speaker_href(label)}">{esc(label)}</a> '
            f'<span class="dim">({len(rows)})</span>'
            for label, rows in sorted(speakers.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        )
        + "</p>",
        "<h2>The calendar</h2>",
        '<p class="legend">Scenes in the order the game plays them: day, then the hour or '
        "time slot the script names, then the event id. A scene the data gives no day of "
        "its own is listed under <em>any day</em> with the condition it plays behind — "
        "including one whose condition tests a single <code>day==N</code>, routinely one "
        "branch of an <code>|</code> whose sibling covers the rest of the month. "
        "<strong>over</strong> counts "
        "lines the translator marked <code># OVERFLOW</code> — a page that does not fit the "
        "dialogue band, translated in full anyway; <strong>shape</strong> counts lines whose "
        "English cannot take the original's shape, which is the "
        '<a href="checks.html">checks</a> page.</p>',
    ]
    days = [d for d in sorted(by_day, key=lambda d: (d is None, d or 0))]
    body.append(
        '<p class="legend">'
        + " ".join(
            f'<a href="#day-{d}">{d}</a>'
            if d is not None
            else f'<a href="#{ANY_DAY_ANCHOR}">{ANY_DAY_TEXT}</a>'
            for d in days
        )
        + "</p>"
    )
    for day in days:
        anchor = f"day-{day}" if day is not None else ANY_DAY_ANCHOR
        title = f"Day {day}" if day is not None else ANY_DAY_TEXT.capitalize()
        rows = []
        for scene in by_day[day]:
            counts = scene_counts(scene, translation, flags)
            hour = scene_hour(scene)
            when = hour.text() if hour is not None else f"slot {scene['where']['time_slots']}"
            # In the any-day section the condition is what puts the scene in front of the
            # player at all, so it is shown instead of the day this table has no cell for.
            gate = scene["when"]["condition"] if day is None else ""
            when_cell = esc(when) + (f" <code>{esc(gate)}</code>" if gate else "")
            rows.append(
                f'<tr><td><a href="{scene_href(scene["event"])}">{esc(scene["event"])}</a></td>'
                f"<td>{when_cell}</td>"
                f"<td>{esc(', '.join(scene['where']['bases']))}</td>"
                f"<td>{esc(', '.join(scene['where']['triggers']))}</td>"
                f'<td class="num">{counts.lines}</td>'
                f'<td class="num">{counts.translated}</td>'
                f'<td class="num untranslated">{counts.untranslated or ""}</td>'
                f'<td class="num untranslated">{counts.overflow or ""}</td>'
                f'<td class="num untranslated">{counts.shape or ""}</td></tr>'
            )
        body.append(
            f'<h2 id="{anchor}">{title} <span class="sub">{len(by_day[day])} scene(s)</span></h2>'
            "<table><tr><th>event</th><th>when</th><th>where</th><th>trigger</th>"
            "<th>lines</th><th>done</th><th>todo</th><th>over</th><th>shape</th></tr>"
            + "".join(rows)
            + "</table>"
        )
    return page(
        "Scene reader — index",
        "\n".join(body),
        heading_nav=bar(
            ['<a href="checks.html">checks</a>', '<a href="other.html">other text</a>']
        ),
    )


def speaker_pages(
    store: Store, translation: Translation, scenes: Sequence[dict], flags: Flags
) -> tuple[dict[str, list[tuple[dict, dict]]], dict[str, str]]:
    """Every line each speaker label says, in play order, and the page for each label."""
    collected: dict[str, list[tuple[dict, dict]]] = {}
    for scene in scenes:
        for node in scene["nodes"]:
            if "line" in node:
                collected.setdefault(node["speaker"], []).append((scene, node))
    pages: dict[str, str] = {}
    for label, entries in collected.items():
        rows = []
        for scene, node in entries:
            line_id = node["line"]
            japanese = store.japanese.get(line_id)
            english = translation.english_rows(line_id)
            flag = "".join(f' <span class="badge flag">{m}</span>' for m in flags.marks(line_id))
            rows.append(
                f"<tr>"
                f'<td><a href="{scene_href(scene["event"])}#{esc(node["node"])}">'
                f"{esc(line_id)}</a>{flag}</td>"
                f"<td>{esc(day_text(scene))}</td>"
                f"<td>{esc(japanese.plain() if japanese else '(voice only)')}</td>"
                f"<td>{english_cell(store, translation, line_id, english)}</td>"
                f"</tr>"
            )
        table = (
            "<table><tr><th>line</th><th>when</th><th>Japanese</th><th>English</th></tr>"
            + "".join(rows)
            + "</table>"
        )
        done = sum(1 for scene, node in entries if translation.english_rows(node["line"]))
        pages[label] = page(
            f"{label} — scene reader",
            f'<h1>{esc(label)} <span class="sub">{len(entries)} line(s), {done} translated'
            "</span></h1>" + table,
            heading_nav=bar(['<a href="index.html">index</a>', '<a href="checks.html">checks</a>']),
        )
    return collected, pages


def other_page(store: Store, translation: Translation, scenes: Sequence[dict]) -> str:
    """Text that is not in any event: the code arrays, menus and labels."""
    in_scenes = scene_owned_lines(scenes)
    rows = []
    for line_id, record in sorted(store.lines.items()):
        if line_id in in_scenes:
            continue
        japanese = store.japanese[line_id]
        english = translation.english_rows(line_id)
        purpose = record.get("purpose") or record.get("reader") or record.get("array") or ""
        rows.append(
            f'<tr><td class="lineid">{esc(line_id)}</td><td>{esc(record["kind"])}</td>'
            f"<td>{esc(purpose)}</td><td>{esc(japanese.plain())}</td>"
            f"<td>{english_cell(store, translation, line_id, english)}</td></tr>"
        )
    table = (
        "<table><tr><th>id</th><th>kind</th><th>where it is read</th><th>Japanese</th>"
        "<th>English</th></tr>" + "".join(rows) + "</table>"
    )
    return page(
        "Other text — scene reader",
        f'<h1>Other text <span class="sub">{len(rows)} line(s) outside the events</span></h1>'
        '<p class="legend">Item names, menus, the fortune slips and labels drawn from code '
        "immediates. These belong to no event, so they appear on no scene page.</p>" + table,
        heading_nav=bar(['<a href="index.html">index</a>']),
    )


def by_kind(problems: Iterable[Problem]) -> dict[str, list[Problem]]:
    grouped: dict[str, list[Problem]] = {}
    for problem in problems:
        grouped.setdefault(problem.kind, []).append(problem)
    return grouped


def checks_page(problems: Sequence[Problem]) -> str:
    if not problems:
        body = "<h1>Checks</h1><p>Nothing noticed.</p>"
    else:
        parts = [
            f'<h1>Checks <span class="sub">{len(problems)} thing(s) noticed</span></h1>',
            '<p class="legend">Reported, not enforced — <code>PLAN PIPE-06</code> is the lint '
            "that will refuse a build over these.</p>",
        ]
        for kind, found in sorted(by_kind(problems).items()):
            rows = "".join(
                f"<tr><td><code>{esc(p.where)}</code></td><td>{esc(p.message)}</td></tr>"
                for p in found
            )
            parts.append(
                f'<h2>{esc(kind)} <span class="sub">{len(found)}</span></h2>'
                f"<table><tr><th>where</th><th>what</th></tr>{rows}</table>"
            )
        body = "\n".join(parts)
    return page("Checks — scene reader", body, heading_nav=bar(['<a href="index.html">index</a>']))


# --- writing the site -----------------------------------------------------------------------------


def refuse_tracked(out_dir: Path) -> Path:
    """Refuse a destination this repo would track: the site holds the Japanese script.

    Inside the repo that means one of `WRITABLE_ROOTS`, both gitignored. Outside the repo
    this cannot know what tracks what and does not try — a destination somewhere else is
    the caller's own business.
    """
    out_dir = Path(out_dir).resolve()
    try:
        relative = out_dir.relative_to(ROOT)
    except ValueError:
        return out_dir
    if relative.parts and relative.parts[0] in WRITABLE_ROOTS:
        return out_dir
    raise ReaderRefused(
        f"{out_dir} is inside the repo and not under "
        f"{' or '.join(f'{root}/' for root in WRITABLE_ROOTS)}. The "
        f"reader renders the Japanese script, which this repo never contains (README "
        f"principle 2)."
    )


def _our_pages(out_dir: Path) -> Iterator[Path]:
    """The pages a previous run of *this* tool wrote, so a rebuild clears its own stale
    scenes without touching anything else that happens to live in the destination."""
    for name in ("index.html", "checks.html", "other.html"):
        candidate = out_dir / name
        if candidate.is_file():
            yield candidate
    yield from out_dir.glob("scene-*.html")
    yield from out_dir.glob("speaker-*.html")


def build_site(
    script_dir: Path = DEFAULT_SCRIPT_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
    sources: Sequence[Path] = DEFAULT_TRANSLATION_DIRS,
) -> tuple[Path, list[Problem], int]:
    """Render the whole site. Returns the directory, what was noticed, and the page count."""
    out_dir = refuse_tracked(out_dir)
    store = load_store(script_dir)
    translation = load_translation(translation_paths(sources))
    problems = check(store, translation)
    flags = flags_of(translation, problems)
    scenes = ordered_scenes(store)

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in _our_pages(out_dir):
        stale.unlink()
    (out_dir / "style.css").write_text(STYLE, encoding="utf-8")

    written = 0
    for position, scene in enumerate(scenes):
        neighbours = (
            scenes[position - 1] if position else None,
            scenes[position + 1] if position + 1 < len(scenes) else None,
        )
        (out_dir / scene_href(scene["event"])).write_text(
            scene_page(scene, store, translation, flags, neighbours), encoding="utf-8"
        )
        written += 1
    speakers, pages = speaker_pages(store, translation, scenes, flags)
    for label, text in pages.items():
        (out_dir / speaker_href(label)).write_text(text, encoding="utf-8")
        written += 1
    (out_dir / "other.html").write_text(other_page(store, translation, scenes), encoding="utf-8")
    (out_dir / "checks.html").write_text(checks_page(problems), encoding="utf-8")
    (out_dir / "index.html").write_text(
        index_page(store, translation, scenes, flags, problems, speakers), encoding="utf-8"
    )
    return out_dir, problems, written + 3


def report(problems: Sequence[Problem]) -> str:
    if not problems:
        return "Nothing noticed in the translation files."
    out = [f"{len(problems)} thing(s) noticed (reported, not enforced):"]
    for kind, found in sorted(by_kind(problems).items()):
        out.append(f"\n  {kind} ({len(found)})")
        out.extend(f"    {p.where}: {p.message}" for p in found)
    return "\n".join(out)


# --- the self-check ----------------------------------------------------------------------------

SELFTEST_LINES = [
    {
        "id": "E9001.0",
        "kind": "XAMSG",
        "text": "ボク「あつい{NL}　なつだ{PAGE:96}　ほんとうに{NL}　あついね」{END}",
        "glyphs": 22,
        "voiced": True,
        "layout": {"pages": [[6, 4], [6, 6]], "page_waits": [96], "columns": 4},
        "capacity": {"bytes": 48, "copies": 1, "pages": 2, "pages_fixed_by_voice": True},
        "event": "E9001",
        "index": 0,
        "speaker": {"label": "BOKU", "slot": 0},
        "voice": {"clip": "9001_00"},
    },
    {
        "id": "E9001.1",
        "kind": "SELECT",
        "text": "はい{NL}いいえ{NL}",
        "glyphs": 5,
        "voiced": False,
        "layout": {"pages": [[2, 3, 0]], "page_waits": [], "columns": 3},
        "capacity": {"bytes": 16, "copies": 1, "pages": 1, "pages_fixed_by_voice": False},
        "select": {"type": 3, "variant": 1, "lines": 2, "prompt_lines": 0},
        "event": "E9001",
        "index": 1,
        "speaker": {"label": "SELECT", "slot": None},
    },
    {
        "id": "E9002.1",
        "kind": "SELECT",
        "text": "カレー{NL}やきそば{NL}",
        "glyphs": 7,
        "voiced": False,
        "layout": {"pages": [[3, 4, 0]], "page_waits": [], "columns": 3},
        "capacity": {"bytes": 20, "copies": 1, "pages": 1, "pages_fixed_by_voice": False},
        "select": {"type": 3, "variant": 1, "lines": 2, "prompt_lines": 0},
        "event": "E9002",
        "index": 1,
        "speaker": {"label": "SELECT", "slot": None},
    },
    {
        "id": "E9002.0",
        "kind": "MSG",
        "text": "おじ「おかえり」{END}",
        "glyphs": 8,
        "voiced": False,
        "layout": {"pages": [[8]], "page_waits": [], "columns": 1},
        "capacity": {"bytes": 18, "copies": 1, "pages": 1, "pages_fixed_by_voice": False},
        "event": "E9002",
        "index": 0,
        "speaker": {"label": "OJI", "slot": 1},
    },
    # A select whose shape spends its first line on the question (`prompt_lines`), as
    # `E0020.0` does: the row lists the question first and it is not an option.
    {
        "id": "E9003.0",
        "kind": "SELECT",
        "text": "おふろにはいる？{NL}はい{NL}いいえ{NL}",  # noqa: RUF001 (full-width punctuation)
        "glyphs": 13,
        "voiced": False,
        "layout": {"pages": [[8, 2, 3, 0]], "page_waits": [], "columns": 4},
        "capacity": {"bytes": 40, "copies": 1, "pages": 1, "pages_fixed_by_voice": False},
        "select": {"type": 3, "variant": 3, "lines": 3, "prompt_lines": 1},
        "event": "E9003",
        "index": 0,
        "speaker": {"label": "SELECT", "slot": None},
    },
    {
        "id": "E9003.1",
        "kind": "MSG",
        "text": "おじ「どうぞ」{END}",
        "glyphs": 7,
        "voiced": False,
        "layout": {"pages": [[7]], "page_waits": [], "columns": 1},
        "capacity": {"bytes": 16, "copies": 1, "pages": 1, "pages_fixed_by_voice": False},
        "event": "E9003",
        "index": 1,
        "speaker": {"label": "OJI", "slot": 1},
    },
]

SELFTEST_SCENES = [
    {
        "event": "E9001",
        "id": 9001,
        "copies": 1,
        "in_ev": False,
        # `hour<14` is an upper bound, not a clock time: this scene plays any time before
        # 14:00, so it sorts under its time slot and ahead of E9003's 13:00.
        "when": {"day": 3, "meal_hour": None, "condition": "(hour<14)"},
        "where": {"maps": ["G02000"], "bases": ["G02"], "time_slots": "0", "triggers": {"auto": 1}},
        "cast": [],
        "actors": {"0": [7]},
        "lines": ["E9001.0", "E9001.1"],
        "play_order": ["E9001.0@10", "E9001.1@20", "E9001.MAP:I06@30"],
        "nodes": [
            {
                "node": "E9001.0@10",
                "pc": 16,
                "opcode": "XAMSG",
                "speaker": "BOKU",
                "line": "E9001.0",
                "slot": 0,
            },
            {
                "node": "E9001.1@20",
                "pc": 32,
                "opcode": "SELECT",
                "speaker": "SELECT",
                "line": "E9001.1",
                "select": {
                    "type": 3,
                    "variant": 1,
                    "lines": 2,
                    "prompt_lines": 0,
                    "options": 2,
                    "cancellable": False,
                },
            },
            {
                "node": "E9001.MAP:I06@30",
                "pc": 48,
                "opcode": "MAP",
                "speaker": "CHAIN",
                "hands_over_to": "MAP:I06>E9002",
            },
        ],
        "edges": [
            {"from": "ENTRY", "to": "E9001.0@10", "condition": ""},
            {"from": "E9001.0@10", "to": "E9001.1@20", "condition": ""},
            {"from": "E9001.1@20", "to": "E9001.MAP:I06@30", "condition": "opt0"},
            {"from": "E9001.1@20", "to": "END", "condition": "opt1"},
            {"from": "E9001.MAP:I06@30", "to": "END", "condition": ""},
        ],
        "handovers": [{"kind": "MAP", "map": "I06", "event": "E9002", "reachable": True}],
        "speaker_mismatches": [],
        "conditions_summarised": False,
    },
    {
        "event": "E9002",
        "id": 9002,
        "copies": 1,
        "in_ev": False,
        # `E1006`'s shape: the `day==2` is one branch of an `|` whose sibling covers every
        # other day but 15, so the day derived from it is not the day this scene plays on
        # -- the reader must say "any day", show the gate, and sort it with the scenes the
        # data gives no day rather than ahead of the day-3 scenes.
        "when": {"day": None, "meal_hour": None, "condition": "((day==2 | day!=15) & hour>=19)"},
        "where": {"maps": ["I06002"], "bases": ["I06"], "time_slots": "2", "triggers": {"auto": 1}},
        "cast": [],
        "actors": {"1": [6]},
        # Three shapes of table row: a message no node reaches (its own anchor), one a node
        # reaches (the node's anchor), and one this event has no line for at all.
        "dinner_quiz": {
            "routines": [16],
            "menu": [
                {"day": 1, "message": 1},
                {"day": 2, "message": 0},
                {"day": 3, "message": 9},
            ],
        },
        "lines": ["E9002.0", "E9002.1"],
        "play_order": ["E9002.0@10"],
        "nodes": [
            {
                "node": "E9002.0@10",
                "pc": 16,
                "opcode": "MSG",
                "speaker": "OJI",
                "line": "E9002.0",
                "slot": 1,
            },
        ],
        "edges": [
            {"from": "ENTRY", "to": "E9002.0@10", "condition": ""},
            {"from": "E9002.0@10", "to": "END", "condition": ""},
        ],
        "handovers": [],
        "speaker_mismatches": [],
        "conditions_summarised": False,
    },
    {
        "event": "E9003",
        "id": 9003,
        "copies": 1,
        "in_ev": False,
        "when": {"day": 3, "meal_hour": None, "condition": "(day==3 & hour==13)"},
        # An `&` in a trigger label: the facts list must escape what it interpolates.
        "where": {
            "maps": ["G03001"],
            "bases": ["G03"],
            "time_slots": "1",
            "triggers": {"talk:A&B": 1},
        },
        "cast": [],
        "actors": {"1": [6]},
        "lines": ["E9003.0", "E9003.1"],
        "play_order": ["E9003.0@10", "E9003.1@20"],
        "nodes": [
            {
                "node": "E9003.0@10",
                "pc": 16,
                "opcode": "SELECT",
                "speaker": "SELECT",
                "line": "E9003.0",
                "select": {
                    "type": 3,
                    "variant": 3,
                    "lines": 3,
                    "prompt_lines": 1,
                    "options": 2,
                    "cancellable": False,
                },
            },
            {
                "node": "E9003.1@20",
                "pc": 32,
                "opcode": "MSG",
                "speaker": "OJI",
                "line": "E9003.1",
                "slot": 1,
            },
        ],
        "edges": [
            {"from": "ENTRY", "to": "E9003.0@10", "condition": ""},
            # An entry that ends the event outright, as `E0809` does: the entry legend shows
            # targets too, and `END` has no anchor there either.
            {"from": "ENTRY", "to": "END", "condition": "lflag>=1"},
            {"from": "E9003.0@10", "to": "E9003.1@20", "condition": "opt0"},
            {"from": "E9003.0@10", "to": "END", "condition": "opt1"},
            {"from": "E9003.1@20", "to": "END", "condition": ""},
        ],
        "handovers": [],
        "speaker_mismatches": [],
        "conditions_summarised": False,
    },
]

CLEAN_TRANSLATION = """\
# A synthetic scene, for the reader's own self-check.

# Boku says it twice, one page each.
E9001.0\tBoku\tIt's hot. It's summer. // It really is hot, isn't it.
E9001.1\t[SEL]\tYes | No
E9002.0\tUncle\tWelcome home.
E9002.1\t[SEL]\tCurry | Fried noodles
# The question first, as style guide § 13 and translation/days/shared.txt's header commit to.
E9003.0\t[SEL]\tTake a bath? | Yes | No
E9003.1\tUncle\tGo ahead.
"""

DIRTY_TRANSLATION = """\
E9001.0\tBoku\tIt's hot, it's summer, and it really is hot isn't it.
E9001.1\t[SEL]\tYes | No | Maybe
# OVERFLOW: this page runs past the dialogue band; it is translated in full anyway.
E9002.0\tUncle\tWelcome home.
E9002.0\tUncle\tYou're back.
E9999.0\tNobody\tThis line does not exist.
"""


def _write_store(root: Path) -> Path:
    script = root / "script"
    (script / "scenes").mkdir(parents=True)
    (script / "index.json").write_text(
        json.dumps(
            {
                "format": 1,
                "counts": {"events": len(SELFTEST_SCENES), "logical_lines": len(SELFTEST_LINES)},
            }
        ),
        encoding="utf-8",
    )
    (script / "lines.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in SELFTEST_LINES), encoding="utf-8"
    )
    for scene in SELFTEST_SCENES:
        (script / "scenes" / f"{scene['event']}.json").write_text(
            json.dumps(scene, ensure_ascii=False), encoding="utf-8"
        )
    return script


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _require_refused(action, message: str) -> None:
    """The action must raise `ReaderRefused` — the reader's own "I will not do that"."""
    try:
        action()
    except ReaderRefused:
        return
    raise AssertionError(message)


def selftest() -> int:
    """Build the whole site from a synthetic store and check what comes out."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        script = _write_store(root)
        clean = root / "clean"
        clean.mkdir()
        (clean / "scene.txt").write_text(CLEAN_TRANSLATION, encoding="utf-8")
        dirty = root / "dirty"
        dirty.mkdir()
        (dirty / "scene.txt").write_text(DIRTY_TRANSLATION, encoding="utf-8")

        # The tokeniser against the shape the extract recorded, and a clean file against
        # every check: both must be silent, or a firing check below proves nothing.
        out, problems, pages = build_site(script, root / "out", [clean])
        _require(not problems, f"a clean translation must notice nothing, got {problems}")
        _require(
            pages == 3 + 3 + 3,
            f"expected 3 scenes + 3 speaker labels (BOKU, OJI, SELECT) + index, checks and "
            f"other, got {pages}",
        )

        # An upper-bound hour is not the hour the scene plays at: E9001 is `hour<14`, so it
        # is ordered by its time slot (0) and comes before E9003's 13:00, not after it.
        store = load_store(script)
        _require(
            [s["event"] for s in ordered_scenes(store)] == ["E9001", "E9003", "E9002"],
            f"play order: {[s['event'] for s in ordered_scenes(store)]}",
        )
        # A derived day is not a day to sort under either. E9002 derives day 2, and sorting
        # by that puts it ahead of the day-3 scenes -- between the dated days, where the
        # hour column of the section it is printed in restarts for no visible reason.
        _require(
            [s["event"] for s in ordered_scenes(store)][-1] == "E9002",
            "a scene whose day is only derived sorts with the tail the data gives no day",
        )

        page_text = (out / "scene-E9001.html").read_text(encoding="utf-8")
        _require(
            "before 14:00" in page_text,
            "an `hour<14` scene must say it plays before 14:00, never at 14:00",
        )
        _require("E9001.0" in page_text, "the scene page must name its line ids")
        _require("ボク「あつい" in page_text, "the scene page must carry the Japanese")
        _require(
            "ボク「あつい / 　なつだ // 　ほんとうに / 　あついね」" in page_text,
            "the plain rendering must show columns as ` / ` and pages as ` // `",
        )
        _require("writing-mode" not in page_text, "the vertical layout belongs in style.css")
        _require("vert" in page_text, "the scene page must carry the vertical layout blocks")
        _require("It&#x27;s hot. It&#x27;s summer." in page_text, "the English must be shown")
        _require(
            '<li>Yes &rarr; <a href="#E9001.MAP:I06@30">E9001.MAP:I06@30</a></li>' in page_text,
            "each SELECT option must link to its branch target",
        )
        _require(
            "<li>No &rarr; END</li>" in page_text,
            "an option that ends the scene must say END, as plain text",
        )
        _require(
            'MAP:I06&gt;<a href="scene-E9002.html">E9002</a>' in page_text,
            "a hand-over must link to the next scene",
        )
        _require(
            "<code>opt0</code>" in page_text, "the flow must list each option edge by its condition"
        )
        _require("wait 96" in page_text, "a voiced page break must show its frame countdown")

        # END is not a node and has no anchor on any page, so nothing may link to it.
        for built in sorted(out.glob("*.html")):
            _require(
                'href="#END"' not in built.read_text(encoding="utf-8"),
                f"{built.name} links to #END, which is not an anchor on any page",
            )

        second = (out / "scene-E9002.html").read_text(encoding="utf-8")
        _require(
            "day 2" not in second,
            "a day read off a `day==N` inside the condition is not the day the scene plays "
            "on, and must never be printed as one",
        )
        _require(
            "any day" in second and "day==2" in second,
            "a condition-gated scene must say its day is open and show the gate",
        )
        _require(
            f"<title>E9002 — {ANY_DAY_TEXT} — scene reader</title>" in second,
            "the page title says the same about the day as the heading does",
        )
        _require(
            "Lines no node reaches" in second and "E9002.1" in second,
            "a line the flow graph never names must still appear on its own scene page",
        )
        _require("カレー" in second, "and it must carry its Japanese")
        # The per-day table is resolved against the anchors the page actually has.
        _require(
            '<a href="#E9002.1">E9002.1</a>' in second,
            "a table message no node reaches must link to that line's own anchor",
        )
        _require(
            '<a href="#E9002.0@10">E9002.0</a>' in second,
            "a table message a node reaches must link to that node, its only anchor",
        )
        _require(
            'href="#E9002.9"' not in second
            and 'E9002.9 <span class="badge flag">no such line</span>' in second,
            "a table message this event has no line for must be text with a flag, not a link",
        )

        third = (out / "scene-E9003.html").read_text(encoding="utf-8")
        _require(
            '<p class="prompt">Take a bath?</p>' in third,
            "a SELECT's prompt line is the question, shown above the options",
        )
        _require(
            '<li>Yes &rarr; <a href="#E9003.1@20">E9003.1@20</a></li>' in third,
            "the first option after the prompt line is option 0 and takes the opt0 branch",
        )
        _require("<li>No &rarr; END</li>" in third, "and the second option is option 1")
        _require(
            "Entry: " in third and "END when <code>lflag&gt;=1</code>" in third,
            "an entry edge that ends the event must name END as text, not link it",
        )
        _require(
            "talk:A&amp;B" in third and "talk:A&B" not in third,
            "a trigger label must be escaped like everything else the facts list shows",
        )

        other = (out / "other.html").read_text(encoding="utf-8")
        _require(
            "E9002.1" not in other,
            "a line shown on a scene page must not be listed as text outside the events",
        )

        index = (out / "index.html").read_text(encoding="utf-8")
        _require('id="day-3"' in index, "the calendar must list the days the data dates")
        _require(
            'id="day-2"' not in index and 'id="day-none"' in index,
            "a scene whose only day is a `day==N` inside its condition belongs with the "
            "day-independent scenes, not under that day's heading",
        )
        # `find`, not `index`: an absent string must fail through `_require` with the
        # sentence below, not raise a ValueError from inside the check.
        section = index.find('id="day-none"')
        row = index.find("scene-E9002.html")
        _require(
            0 <= section < row and "day==2" in index,
            "and its row must sit in that section, with the condition it plays behind",
        )
        _require("6 translated" in index, "the index must count what is translated")
        _require("before 14:00" in index, "the calendar must not print a bound as a clock time")
        _require(
            index.index("scene-E9001.html") < index.index("scene-E9003.html"),
            "the calendar must list the `hour<14` scene before the 13:00 scene of the same day",
        )

        speaker = (out / "speaker-BOKU.html").read_text(encoding="utf-8")
        _require("E9001.0" in speaker, "a speaker page must list that speaker's lines")
        oji = (out / "speaker-OJI.html").read_text(encoding="utf-8")
        _require(
            "E9002.0" in oji and "day 2" not in oji and "any day" in oji,
            "a speaker page dates each line by the scene it is in, so it too must not date "
            "one by a day read off a branch of the condition",
        )

        # Now one file with four planted defects, each of which must be named.
        _, dirty_problems, _ = build_site(script, root / "out2", [dirty])
        kinds = {p.kind for p in dirty_problems}
        found = {p.kind: p.message for p in dirty_problems}
        for kind, must_name in (
            ("unknown-id", "E9999.0"),
            ("translated-twice", "E9002.0"),
            ("select-options", "E9001.1"),
            ("page-count", "E9001.0"),
        ):
            _require(kind in kinds, f"{kind} was planted and not reported: {dirty_problems}")
            _require(
                must_name in found[kind], f"the {kind} report must name {must_name}: {found[kind]}"
            )
        _require(
            "reader-vs-loader" not in kinds,
            f"the reader must parse what boku.translation parses: {dirty_problems}",
        )
        dirty_flags = flags_of(load_translation([dirty / "scene.txt"]), dirty_problems)
        _require(
            dirty_flags.shape == {"E9001.1", "E9001.0"},
            f"the shape mark belongs on the select and the voiced page count, got "
            f"{dirty_flags.shape}",
        )
        _require(
            dirty_flags.overflow == {"E9002.0"},
            f"OVERFLOW is the translator's own `# OVERFLOW` note and nothing else, got "
            f"{dirty_flags.overflow}",
        )
        dirty_page = (root / "out2" / "scene-E9001.html").read_text(encoding="utf-8")
        _require(">shape<" in dirty_page, "a shape-marked line must say so on its scene page")
        _require("OVERFLOW" not in dirty_page, "E9001 carries no translator OVERFLOW note")
        second_dirty = (root / "out2" / "scene-E9002.html").read_text(encoding="utf-8")
        _require(">OVERFLOW<" in second_dirty, "the `# OVERFLOW` note must mark its own line")
        _require(
            "the build ignores this row" in second_dirty,
            "a row the loader discards must say so, not read as an equal alternative",
        )

        # The agreement check matches the reader's rows to the loader's entries by where
        # each was written, so it compares the row the loader kept even when that is not
        # the first row the reader shows.
        swapped = load_translation([dirty / "scene.txt"])
        duplicates = swapped.english_rows("E9002.0")
        _require(len(duplicates) == 2, f"E9002.0 is the planted duplicate, got {duplicates}")
        swapped.built["E9002.0"] = duplicates[1].entry
        _require(
            not [p for p in check(store, swapped) if p.kind == "reader-vs-loader"],
            "the agreement check must compare the row the loader kept, whichever row that is",
        )
        _require(
            swapped.built_origin("E9002.0") == duplicates[1].origin,
            "and the page must mark the other row, not the second one by position",
        )

        # Two files of the same basename in different directories are two files.
        both = load_translation([clean / "scene.txt", dirty / "scene.txt"])
        _require(
            len(both.file_notes) == 2 and len(both.ids_by_file) == 2,
            f"same-basename files must not merge: {sorted(both.ids_by_file)}",
        )

        # An untranslated line leaves the slot empty, and never borrows the Japanese.
        _, _, _ = build_site(script, root / "out3", [])
        bare = (root / "out3" / "scene-E9001.html").read_text(encoding="utf-8")
        _require("(not translated yet)" in bare, "a missing English must be an empty slot")
        _require(bare.count("(not translated yet)") == 2, "both lines are untranslated")

        # The site is Japanese script: it may not be written into the tracked tree.
        _require_refused(
            lambda: build_site(script, ROOT / "translation" / "reader", [clean]),
            "writing into the tracked tree must be refused",
        )

        # A half-written or foreign store is refused by name, not by traceback.
        headless = root / "no-lines"
        (headless / "scenes").mkdir(parents=True)
        (headless / "index.json").write_text(
            json.dumps({"format": 1, "counts": {"events": 0, "logical_lines": 0}}),
            encoding="utf-8",
        )
        _require_refused(
            lambda: load_store(headless), "a store with no lines.jsonl must be refused"
        )
        countless = root / "no-counts"
        (countless / "scenes").mkdir(parents=True)
        (countless / "index.json").write_text(json.dumps({"format": 1}), encoding="utf-8")
        (countless / "lines.jsonl").write_text("", encoding="utf-8")
        _require_refused(
            lambda: load_store(countless), "an index.json with no `counts` must be refused"
        )
    print("selftest: ok")
    return 0


# --- CLI ---------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the read-only scene reader (PLAN TRN-06).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"where the site goes (default {DEFAULT_OUT_DIR.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--script-dir", type=Path, default=DEFAULT_SCRIPT_DIR, help="the extracted script store"
    )
    parser.add_argument(
        "--translation",
        type=Path,
        action="append",
        default=None,
        help="a translation file or directory (repeatable)",
    )
    parser.add_argument(
        "--check", action="store_true", help="report what the reader notices, and write nothing"
    )
    parser.add_argument(
        "--selftest", action="store_true", help="build from a synthetic store and check the result"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    sources = args.translation if args.translation is not None else list(DEFAULT_TRANSLATION_DIRS)
    try:
        if args.check:
            store = load_store(args.script_dir)
            translation = load_translation(translation_paths(sources))
            files = (
                ", ".join(file_label(p) for p in translation.paths) or "no translation files found"
            )
            print(f"read {files}")
            print(report(check(store, translation)))
            return 0
        out, problems, pages = build_site(args.script_dir, args.out, sources)
        print(f"wrote {pages} page(s) to {out}")
        print(report(problems))
        print(f"open {out / 'index.html'}")
    except ReaderRefused as refused:
        print(f"reader refused: {refused}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
