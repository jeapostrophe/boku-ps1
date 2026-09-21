"""`PLAN PIPE-06` -- the translation lints, run over the committed translation files.

Every check answers one question about a *committed* file against the *local* script
store, and answers it in the store's own numbers. The fix for an overflow is another page
or a wider box, never a shorter translation (README § "Who this is for"), so a finding
reports what is over and by how much and stops there; nothing here rewrites English.

    ./make.sh lint-translation                  # translation/days + translation/samples
    ./make.sh lint-translation --encoder cellmap    # in the VWF prototype's own pixels

What it checks, and where each rule comes from
----------------------------------------------
* **`unknown-id`** -- the id is not a line in the script. Voice-only ids count: they have
  no text on the disc and are listed so the ids line up
  (`translation/samples/README.md`).
* **`translated-twice`** -- one id given English in two places. Whichever the build's
  loader picked, the other was written for nothing.
* **`select-options` / `select-shape`** -- the option count is `g_select_lines` in the
  executable, not data, so options map 1:1 (`boku/layout.py`). A box that opens with a
  question spends its first lines on it and the row lists the question first (style guide
  § 13), so those fields are counted against the prompt count, not the option count.
* **`page-count`** -- a voiced message's page turns are a frame countdown matched to the
  clip (`research/text-format.md`, `0x8002`), so the count is fixed. An unvoiced line's
  is not, and a difference there is a `page-count-unvoiced` warning, not an error.
* **`unencodable`** -- a character the chosen encoder draws no cell for.
* **`page-lines` / `page-width`** -- the page measured in pixels through
  `boku.layout`, in the box `TXT-07` measured on the running prototype. The engine has no
  wrap logic and clips at the screen edge silently, so this is the real gate
  (`research/vwf-prototype.md`).
* **`select-width`** -- a select line cannot wrap; a second line would be a second option.
* **`array-bytes`** -- a code-file array item has no slack: the next symbol starts where
  it ends, so growth is refused by the reinserter (`boku/layout.py`, `PLAN PIPE-03`).
* **`additive-word`** -- *a heuristic, and a warning only.* The pilot's recurring defect
  was English the Japanese does not have -- adverbs and intensifiers added for rhythm
  (`translation/days/README.md` § "Lessons from the pilot"). It fires when an English
  intensifier is present and the source line carries none of a matching set. It is
  word-list matching, it has no idea what the sentence means, and it is right often
  enough to be worth a look and wrong often enough that it may never fail a build.
* **`reader-vs-loader`** -- this module's parse against `boku.translation.SampleScenes`,
  the loader the image build reads English through. Two parsers of one provisional format
  is a real risk (`tools/reader/build.py` carries a third and checks it the same way), so
  they are compared rather than trusted.

The label on line 1
-------------------
The renderer draws labelled dialogue in the original's style, label and marks (style guide
§ 9, settled as an early default). The build does not prepend it -- the label is a parsed
field, and *which* marks and whether the label sits inside the box is the dialogue band's
decision -- so the lint charges page 1's first line for the label's own cells plus
`--label-marks`, and `--no-label` measures the bare English. A character the encoder has
no cell for is charged at its fallback advance, which is deliberately the pessimistic way
round for a limit nobody has settled.
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
from boku.glyphs import GlyphTable
from boku.layout import (
    DIALOGUE_BAND,
    BoxSpec,
    CellMapEncoder,
    Encoder,
    LayoutError,
    StockEncoder,
    lay_out_array,
    measure,
    unencodable,
    wrap,
)
from boku.script_store import (
    Store,
    StoreMissing,
    is_array,
    load_store,
    original_bytes,
    page_count,
    pages_fixed_by_voice,
    select_shape,
)
from boku.translation import SampleScenes, TranslationEntry

DEFAULT_SOURCES = (REPO_ROOT / "translation" / "days", REPO_ROOT / "translation" / "samples")
"""What `./make.sh lint-translation` lints when it is given nothing."""

DEFAULT_CELLS = REPO_ROOT / "build" / "vwf" / "manifest.json"
"""Where `tools/vwf/build_prototype.py` leaves the cell map, when it has been run."""

LABEL_MARKS = "\u300c"
"""The opening mark the original draws after a speaker label. Style guide § 9 leaves the
choice between this and an English quotation mark to the dialogue band; both are one
cell, so which one is charged does not change the verdict."""


# --- the additive-word heuristic ------------------------------------------------------------

ADDITIVE_WORDS = (
    "absolutely",
    "actually",
    "awfully",
    "completely",
    "definitely",
    "extremely",
    "incredibly",
    "just",
    "quite",
    "rather",
    "really",
    "terribly",
    "totally",
    "truly",
    "utterly",
    "very",
)
"""English intensifiers the pilot's reviewer kept striking out. Override with
`--additive-words FILE`, one word per line."""

SOURCE_INTENSIFIERS = (
    "\u3068\u3066\u3082",
    "\u3068\u3063\u3066\u3082",
    "\u3059\u3054\u304f",
    "\u3059\u3063\u3054\u304f",
    "\u3059\u3054\u3044",
    "\u672c\u5f53\u306b",
    "\u307b\u3093\u3068",
    "\u307e\u3063\u305f\u304f",
    "\u3061\u3087\u3063\u3068",
    "\u305a\u3044\u3076\u3093",
    "\u304b\u306a\u308a",
    "\u975e\u5e38\u306b",
    "\u5b9f\u306b",
    "\u5927\u5909",
    "\u305f\u3044\u3078\u3093",
    "\u3081\u3061\u3083",
    "\u5168\u7136",
    "\u305c\u3093\u305c\u3093",
    "\u7d76\u5bfe",
    "\u3082\u306e\u3059\u3054",
)
"""Source-side intensifiers that make an English one a translation rather than an
addition. Written as escapes because this file is tracked and the repo holds no Japanese
(CLAUDE.md § "This repo is public"); they are dictionary words, not the game's text."""


def read_word_list(path: Path) -> tuple[str, ...]:
    """One word per line; `#` comments and blanks ignored. Lower-cased, deduplicated."""
    words: list[str] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        word = raw.split("#", 1)[0].strip().lower()
        if word and word not in words:
            words.append(word)
    return tuple(words)


# --- findings -------------------------------------------------------------------------------

ERROR = "ERROR"
WARNING = "WARNING"

SHARED_WITH_READER = frozenset(
    {"unknown-id", "translated-twice", "select-options", "select-shape", "page-count"}
)
"""The checks `tools/reader/build.py --check` also reports. Two implementations of one
rule set, over one store and one set of files, must name the same lines -- which is what
`tests/test_lint.py`'s agreement gate compares. The reader reports; this enforces."""


@dataclass(frozen=True, order=True)
class Finding:
    """One thing wrong with one row, in the store's numbers."""

    file: str
    number: int
    line_id: str
    check: str
    severity: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.severity == ERROR

    def format(self) -> str:
        return (
            f"{self.severity} {self.file}:{self.number} {self.line_id} {self.check} {self.message}"
        )


# --- the translation files ---------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One row of a translation file, with the `#` notes written immediately above it."""

    line_id: str
    speaker: str
    text: str
    path: Path
    number: int
    notes: tuple[str, ...] = ()

    @property
    def file(self) -> str:
        return self.path.name

    @property
    def voice_only(self) -> bool:
        return self.speaker == SampleScenes.VOICE_ONLY or not self.text

    @property
    def is_select(self) -> bool:
        return self.speaker == SampleScenes.SELECT

    @property
    def entry(self) -> TranslationEntry:
        """The same `TranslationEntry` the build's loader makes of this row.

        Built from `SampleScenes`' own constants so the two cannot drift silently; that
        they do not drift *at all* is what `reader-vs-loader` below checks.
        """
        if self.is_select:
            return TranslationEntry(
                line_id=self.line_id,
                speaker=self.speaker,
                options=tuple(o.strip() for o in self.text.split(SampleScenes.OPTION)),
                origin=f"{self.file}:{self.number}",
            )
        return TranslationEntry(
            line_id=self.line_id,
            speaker=self.speaker,
            pages=tuple(p.strip() for p in self.text.split(SampleScenes.PAGE_BREAK)),
            origin=f"{self.file}:{self.number}",
        )


def parse_file(path: Path) -> tuple[list[Row], list[Finding]]:
    """Rows and the problems the format itself shows, in file order."""
    rows: list[Row] = []
    findings: list[Finding] = []
    notes: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.rstrip()
        if not line:
            notes = []
            continue
        if line.lstrip().startswith("#"):
            notes.append(line.lstrip().lstrip("#").strip())
            continue
        fields = line.split("\t")
        if len(fields) < 2:
            findings.append(
                Finding(
                    path.name,
                    number,
                    "-",
                    "malformed",
                    ERROR,
                    "no tab; a row is `id <TAB> speaker <TAB> English`",
                )
            )
            notes = []
            continue
        rows.append(
            Row(
                line_id=fields[0].strip(),
                speaker=fields[1].strip(),
                text=fields[2].strip() if len(fields) > 2 else "",
                path=path,
                number=number,
                notes=tuple(notes),
            )
        )
        notes = []
    return rows, findings


def translation_paths(sources: Sequence[Path]) -> list[Path]:
    """Every `*.txt` under the given files and directories, sorted. Missing ones are fine."""
    found: list[Path] = []
    for source in sources:
        source = Path(source)
        if source.is_dir():
            found.extend(sorted(source.glob("*.txt")))
        elif source.is_file():
            found.append(source)
    return sorted(set(found))


def load_rows(paths: Sequence[Path]) -> tuple[list[Row], list[Finding]]:
    rows: list[Row] = []
    findings: list[Finding] = []
    for path in paths:
        file_rows, file_findings = parse_file(path)
        rows.extend(file_rows)
        findings.extend(file_findings)
    return rows, findings


# --- the box, and the label that sits in it ------------------------------------------------------


def box_from(
    width: int, lines: int, guard_from: int, guard_width: int, name: str = DIALOGUE_BAND.name
) -> BoxSpec:
    """A `BoxSpec` from the command line's four numbers, refusing a box nothing fits in."""
    if width <= 0 or lines <= 0:
        raise LayoutError(f"a box is at least 1 line of 1 px; {lines} x {width} is not")
    if guard_from and not guard_width:
        raise LayoutError("--guard-from without --guard-width leaves the guarded line no room")
    return BoxSpec(
        width=width,
        lines=lines,
        guarded_from=guard_from,
        guarded_width=guard_width,
        name=name,
    )


def original_draws_label(record: dict, store: Store) -> bool:
    """Did the Japanese open this message with `<speaker>\u300c`?

    The label is inline in the source and a parsed field in the translation (style guide
    § 9). Narration opens `\u300e` and an unlabelled examine message opens `\u300c` with nothing
    before it, so the test is a `\u300c` that is *not* the first cell of the line.
    """
    japanese = store.japanese.get(record["id"])
    if japanese is None or not japanese.pages or not japanese.pages[0]:
        return False
    first_column = japanese.pages[0][0]
    return LABEL_MARKS in first_column[1:]


def label_allowance(encoder: Encoder, speaker: str, marks: str) -> int:
    """Pixels the label takes off the head of page 1's first line."""
    return measure(encoder, f"{speaker}{marks}")


@dataclass(frozen=True)
class LabelledBox(BoxSpec):
    """`box` with its **first line only** narrowed by the label drawn in front of it.

    `BoxSpec` narrows the tail of a line -- the next-page pencil, which sits on the last
    one. The label narrows the head, and only of page 1's first line, so it cannot be
    subtracted from `width`: that takes the pixels off every line of the page and reports
    a page that fits as one line too many.
    """

    reserve: int = 0

    def width_of_line(self, number: int) -> int:
        width = super().width_of_line(number)
        return max(width - self.reserve, 1) if number == 1 else width


def fit_page(
    encoder: Encoder, text: str, box: BoxSpec, reserve: int = 0
) -> tuple[list[str], list[int]]:
    """Break one page into lines and measure each, with `reserve` px gone from line 1.

    The wrap itself is `boku.layout.wrap` -- the same greedy pixel wrap the build inserts
    with -- run against a box whose first line is narrowed by the label. Its own widths
    are then re-measured against the unnarrowed box so a finding quotes the real limit.
    """
    if reserve:
        narrowed = LabelledBox(
            width=box.width,
            lines=box.lines,
            guarded_from=box.guarded_from,
            guarded_width=box.guarded_width,
            name=box.name,
            reserve=reserve,
        )
        broken = wrap(encoder, text, narrowed)
        widths = [measure(encoder, line) for line in broken]
        if widths:
            widths[0] += reserve
        return broken, widths
    broken = wrap(encoder, text, box)
    return broken, [measure(encoder, line) for line in broken]


# --- the checks ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Options:
    """Everything a run of the lint can be told, so one call site can hold it."""

    encoder: Encoder
    box: BoxSpec = DIALOGUE_BAND
    label: bool = True
    label_marks: str = LABEL_MARKS
    additive_words: tuple[str, ...] = ADDITIVE_WORDS
    additive: bool = True


@dataclass
class _Context:
    """Per-run state the checks share: the store, the options, the growing findings."""

    store: Store
    options: Options
    table: GlyphTable
    findings: list[Finding] = field(default_factory=list)

    def say(self, row: Row, check: str, severity: str, message: str) -> None:
        self.findings.append(Finding(row.file, row.number, row.line_id, check, severity, message))


def lint_rows(store: Store, rows: Sequence[Row], options: Options) -> list[Finding]:
    """Every finding over these rows, sorted by file then row."""
    context = _Context(store=store, options=options, table=GlyphTable.load())
    english = [row for row in rows if not row.voice_only]
    _check_ids(context, rows, english)
    for row in english:
        record = store.lines.get(row.line_id)
        if record is None:
            continue  # unknown, or voice-only: `_check_ids` has already said so
        _check_row(context, row, record)
        if options.additive:
            _check_additive(context, row, record)
    context.findings.extend(_check_loader_agreement(rows))
    return sorted(context.findings)


def _check_ids(context: _Context, rows: Sequence[Row], english: Sequence[Row]) -> None:
    legal = context.store.known_ids
    for row in rows:
        if row.line_id not in legal:
            context.say(
                row,
                "unknown-id",
                ERROR,
                f"{row.line_id} is not a line in the script ({len(legal)} ids known)",
            )
    seen: dict[str, Row] = {}
    for row in english:
        first = seen.get(row.line_id)
        if first is None:
            seen[row.line_id] = row
            continue
        context.say(
            row,
            "translated-twice",
            ERROR,
            f"{row.line_id} is given English twice; first at {first.file}:{first.number}",
        )


def _check_row(context: _Context, row: Row, record: dict) -> None:
    shape = select_shape(record)
    if shape is not None:
        _check_select(context, row, record, shape)
        return
    if row.is_select:
        context.say(
            row,
            "select-shape",
            ERROR,
            f"{row.line_id} is written as a SELECT but the store has it as a message",
        )
        return
    if is_array(record):
        _check_array(context, row, record)
        return
    _check_message(context, row, record)


def select_fields(entry: TranslationEntry, prompts: int) -> tuple[tuple[str, ...], ...]:
    """A `[SEL]` row's pipe fields as the box reads them: `(prompt lines, options)`.

    A select whose box opens with a question spends its first `prompts` lines on it, and
    the committed convention lists the question first -- style guide § 13,
    `translation/days/README.md` § shared.txt, and that file's own header. The question is
    not an option: it is neither counted against `g_select_lines` nor given a branch. The
    reader reads a row the same way (`tools/reader/checks.py`), which is what lets the two
    be held against each other.
    """
    return entry.options[:prompts], entry.options[prompts:]


def _check_select(context: _Context, row: Row, record: dict, shape: tuple[int, int]) -> None:
    options, prompts = shape
    if not row.is_select:
        context.say(
            row,
            "select-shape",
            ERROR,
            f"{row.line_id} is a SELECT of {options} option(s) but is written as a message",
        )
        return
    question, given = select_fields(row.entry, prompts)
    if len(given) != options or len(question) != prompts:
        context.say(
            row,
            "select-options",
            ERROR,
            f"{len(given)} option(s) given; g_select_lines fixes {options}"
            + (
                f", after {prompts} prompt line(s) the row lists first "
                f"(style guide § 13); {len(question)} given"
                if prompts
                else ""
            ),
        )
    encoder = context.options.encoder
    drawn = (*question, *given)  # the box draws the question too, so it is measured too
    missing = unencodable(encoder, "".join(drawn))
    if missing:
        context.say(
            row, "unencodable", ERROR, f"the {encoder.name} draws no cell for {''.join(missing)!r}"
        )
    width = context.options.box.width
    for index, line in enumerate(drawn, start=1):
        pixels = measure(encoder, line)
        if pixels > width:
            context.say(
                row,
                "select-width",
                ERROR,
                f"line {index}: {pixels} px in {width}, {pixels - width} over; "
                f"a select line cannot wrap",
            )


def _check_array(context: _Context, row: Row, record: dict) -> None:
    """The byte size, through the same `lay_out_array` the build lays arrays out with.

    There is no pixel lint here: the fixed-pitch surfaces these arrays feed have not been
    measured (`PLAN TXT-07`), so the byte length is the only limit that is known.
    """
    encoder = context.options.encoder
    text = " ".join(row.entry.pages)
    size = record["capacity"]["bytes"]
    laid = lay_out_array(row.line_id, text, original_bytes(record, context.table), encoder, size)
    for problem in laid.problems:
        detail = problem.split(": ", 1)[-1]
        check = "array-bytes"
        severity = ERROR
        if "drawn as a group" in problem:
            check, severity = "array-group", WARNING
        elif "draws no cell" in problem:
            check = "unencodable"
        elif "no English was given" in problem:
            check = "array-empty"
        context.say(row, check, severity, detail)


def _check_message(context: _Context, row: Row, record: dict) -> None:
    encoder = context.options.encoder
    box = context.options.box
    pages = row.entry.pages
    original = page_count(record)
    if len(pages) != original:
        voiced = pages_fixed_by_voice(record)
        context.say(
            row,
            "page-count" if voiced else "page-count-unvoiced",
            ERROR if voiced else WARNING,
            f"{len(pages)} page(s) given, the original has {original}"
            + (
                "; the page turns are a frame countdown matched to the voice clip and cannot move"
                if voiced
                else "; these page breaks are not voice-timed, so this may be deliberate"
            ),
        )
    missing = unencodable(encoder, "".join(pages))
    if missing:
        context.say(
            row, "unencodable", ERROR, f"the {encoder.name} draws no cell for {''.join(missing)!r}"
        )
    reserve = 0
    if context.options.label and original_draws_label(record, context.store):
        reserve = label_allowance(encoder, row.speaker, context.options.label_marks)
    for number, text in enumerate(pages, start=1):
        broken, widths = fit_page(encoder, text, box, reserve if number == 1 else 0)
        if len(broken) > box.lines:
            context.say(
                row,
                "page-lines",
                ERROR,
                f"page {number}: {len(broken)} lines in {box.name}, which holds {box.lines}; "
                f"the fix is another page or a wider box, never a shorter line",
            )
        for index, (broken_line, pixels) in enumerate(zip(broken, widths, strict=True), start=1):
            limit = box.width_of_line(index)
            if pixels > limit:
                label = " (label included)" if reserve and number == 1 and index == 1 else ""
                context.say(
                    row,
                    "page-width",
                    ERROR,
                    f"page {number} line {index}: {pixels} px in {limit}, "
                    f"{pixels - limit} over{label} ({broken_line!r} does not break)",
                )


_WORD = re.compile(r"[a-z']+")


def _check_additive(context: _Context, row: Row, record: dict) -> None:
    """The pilot's recurring defect, as far as a word list can see it. Warning only."""
    source = context.store.japanese[record["id"]].plain()
    if any(marker in source for marker in SOURCE_INTENSIFIERS):
        return
    words = set(_WORD.findall(row.text.lower()))
    added = [word for word in context.options.additive_words if word in words]
    if added:
        context.say(
            row,
            "additive-word",
            WARNING,
            f"heuristic: {', '.join(added)} in the English, no intensifier in the source "
            f"({len(SOURCE_INTENSIFIERS)} looked for) -- check it is a translation, not an "
            f"addition",
        )


def _check_loader_agreement(rows: Sequence[Row]) -> Iterator[Finding]:
    """This module's parse against the loader the build reads English through.

    A disagreement means the lint passed something other than what would be built, which
    is the one failure a lint can cause on its own.
    """
    paths = sorted({row.path for row in rows})
    if not paths:
        return
    theirs = {entry.line_id: entry for entry in SampleScenes.from_paths(paths)}
    mine: dict[str, tuple[Row, TranslationEntry]] = {}
    for row in rows:
        if not row.voice_only and row.line_id not in mine:
            mine[row.line_id] = (row, row.entry)
    for line_id in sorted(set(mine) | set(theirs)):
        here = mine.get(line_id)
        there = theirs.get(line_id)
        ours = here[1] if here else None
        if ours == there:
            continue
        row = here[0] if here else None
        yield Finding(
            row.file if row else "-",
            row.number if row else 0,
            line_id,
            "reader-vs-loader",
            ERROR,
            f"this lint reads {ours!r}; boku.translation reads {there!r}",
        )


# --- running it -------------------------------------------------------------------------------


def make_encoder(kind: str, cells: Path | None) -> Encoder:
    """`stock` or `cellmap`; a cell map defaults to where the VWF build leaves one."""
    if kind == "stock":
        return StockEncoder.load()
    path = Path(cells) if cells is not None else DEFAULT_CELLS
    if not path.is_file():
        raise LayoutError(
            f"--encoder cellmap needs a character -> cell map and {path} is not there; "
            f"run `uv run python tools/vwf/build_prototype.py`, or give --cells FILE"
        )
    return CellMapEncoder.from_json(path)


def format_report(findings: Iterable[Finding]) -> list[str]:
    return [finding.format() for finding in findings]


def summarise(findings: Sequence[Finding]) -> str:
    errors = sum(1 for f in findings if f.is_error)
    warnings = len(findings) - errors
    by_check = ", ".join(
        f"{check} {sum(1 for f in findings if f.check == check)}"
        for check in sorted({f.check for f in findings})
    )
    return f"{errors} error(s), {warnings} warning(s)" + (f" -- {by_check}" if by_check else "")


def main_lint(
    sources: Sequence[Path],
    disc_dir: Path,
    encoder_kind: str,
    cells: Path | None,
    width: int,
    lines: int,
    guard_from: int,
    guard_width: int,
    label: bool,
    additive: bool,
    additive_words: Path | None,
) -> int:
    paths = translation_paths(sources or DEFAULT_SOURCES)
    if not paths:
        print(f"lint: no *.txt translation files under {', '.join(str(s) for s in sources)}")
        return 2
    try:
        store = load_store(Path(disc_dir) / SCRIPT_DIR_NAME)
        options = Options(
            encoder=make_encoder(encoder_kind, cells),
            box=box_from(width, lines, guard_from, guard_width),
            label=label,
            additive=additive,
            additive_words=(read_word_list(additive_words) if additive_words else ADDITIVE_WORDS),
        )
    except (StoreMissing, LayoutError) as error:
        print(f"lint: {error}", file=sys.stderr)
        return 2
    rows, findings = load_rows(paths)
    findings = sorted([*findings, *lint_rows(store, rows, options)])
    print(
        f"read {', '.join(path.name for path in paths)} "
        f"({len(rows)} row(s)) against {store.root} in {options.encoder.name}, "
        f"{options.box.name} {options.box.lines}x{options.box.width} px"
    )
    for line in format_report(findings):
        print(line)
    print(summarise(findings))
    return 1 if any(finding.is_error for finding in findings) else 0


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The lint's switches, on `boku lint`. Shared with nothing; kept beside the code."""
    parser.add_argument(
        "sources",
        nargs="*",
        type=Path,
        metavar="FILE",
        help=(
            "translation files or directories of them (default: "
            f"{', '.join(str(p.relative_to(REPO_ROOT)) for p in DEFAULT_SOURCES)})"
        ),
    )
    parser.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        metavar="DIR",
        help=f"the import whose script store the ids are checked against (default: "
        f"{DEFAULT_DISC_DIR}/)",
    )
    parser.add_argument(
        "--encoder",
        choices=("stock", "cellmap"),
        default="stock",
        help=(
            "which font's widths to measure in: the game's own full-width Latin cells at a "
            "fixed 14 px, or the variable-width cell map TXT-05's font build emits "
            "(default: stock)"
        ),
    )
    parser.add_argument(
        "--cells",
        type=Path,
        metavar="FILE",
        help=f"the cell map --encoder cellmap reads (default: {DEFAULT_CELLS})",
    )
    parser.add_argument(
        "--box-width",
        type=int,
        default=DIALOGUE_BAND.width,
        metavar="PX",
        help=f"usable pixels per line (default: {DIALOGUE_BAND.width}, the dialogue band)",
    )
    parser.add_argument(
        "--box-lines",
        type=int,
        default=DIALOGUE_BAND.lines,
        metavar="N",
        help=f"lines that draw cleanly on one page (default: {DIALOGUE_BAND.lines})",
    )
    parser.add_argument(
        "--guard-from",
        type=int,
        default=DIALOGUE_BAND.guarded_from,
        metavar="N",
        help=(
            f"first line the next-page pencil sits on, 0 for none "
            f"(default: {DIALOGUE_BAND.guarded_from})"
        ),
    )
    parser.add_argument(
        "--guard-width",
        type=int,
        default=DIALOGUE_BAND.guarded_width,
        metavar="PX",
        help=f"what a guarded line fits in instead (default: {DIALOGUE_BAND.guarded_width})",
    )
    parser.add_argument(
        "--no-label",
        dest="label",
        action="store_false",
        help=(
            "measure the bare English, without charging page 1's first line for the "
            "speaker label the renderer draws in the original's style (style guide § 9)"
        ),
    )
    parser.add_argument(
        "--no-additive",
        dest="additive",
        action="store_false",
        help="skip the additive-word heuristic, which only ever warns",
    )
    parser.add_argument(
        "--additive-words",
        type=Path,
        metavar="FILE",
        help="the English intensifier list to use instead of the built-in one, one per line",
    )
    parser.set_defaults(
        run=lambda args: main_lint(
            args.sources,
            args.disc,
            args.encoder,
            args.cells,
            args.box_width,
            args.box_lines,
            args.guard_from,
            args.guard_width,
            args.label,
            args.additive,
            args.additive_words,
        )
    )
    return parser
