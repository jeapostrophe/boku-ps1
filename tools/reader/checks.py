#!/usr/bin/env python3
"""`PLAN TRN-06` — what the reader notices, as facts rather than as a page.

Split out of `build.py` so that `PLAN PIPE-06`'s lint can hold its own findings against
exactly what the reader reports: this module is the findings, `build.py` is the site. It
reads nothing off disk and writes nothing — every input is already-loaded state, so a lint
that builds the same `Store` and `Translation` gets the same `Problem` list.

A `Problem` is reported, never enforced. The reader shows them on `checks.html`; refusing a
build over one is `PIPE-06`'s job.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from boku.translation import TranslationEntry  # noqa: E402

if TYPE_CHECKING:  # `build` imports this module, so its types are for annotations only.
    from build import Row, Store, Translation


@dataclass(frozen=True)
class Problem:
    """Something the reader noticed. Reported, never enforced."""

    kind: str
    where: str
    message: str


SHAPE_KINDS = frozenset({"select-options", "select-shape", "page-count"})
"""The reader's findings that say the English cannot take the original's shape: a select
whose option count the executable fixes, or a voiced message whose page turns are timed to
its clip."""


def known_ids(store: Store) -> set[str]:
    """Every id a translation may legally address — including voice-only ids, which have no
    text on the disc and so no record in `lines.jsonl`, but are named by a node."""
    ids = set(store.lines)
    for scene in store.scenes:
        ids.update(node["line"] for node in scene["nodes"] if "line" in node)
    return ids


def select_shape(store: Store, line_id: str) -> tuple[int, int] | None:
    """`(options, prompt_lines)` the executable fixes for this select, if it is one."""
    record = store.lines.get(line_id)
    if record is None or "select" not in record:
        return None
    shape = record["select"]
    return shape["lines"] - shape["prompt_lines"], shape["prompt_lines"]


def select_fields(
    entry: TranslationEntry, prompt_lines: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """A `[SEL]` row's pipe fields split the way the box reads them: `(prompts, options)`.

    A select whose shape has `prompt_lines` spends its first rows on the question, and the
    committed convention is that the row lists the question first — style guide § 13 and the
    header of `translation/days/shared.txt` ("Take a bath? | Yes | No"). The question is not
    an option: it is neither counted against the shape's option count nor given a branch.
    """
    return entry.options[:prompt_lines], entry.options[prompt_lines:]


def check(store: Store, translation: Translation) -> list[Problem]:
    """Everything the reader noticed: the translation's problems, then the store's own."""
    problems: list[Problem] = list(translation.problems)
    legal = known_ids(store)
    for line_id, rows in sorted(translation.rows.items()):
        if line_id not in legal:
            problems.append(
                Problem("unknown-id", rows[0].origin, f"{line_id} is not a line in the script")
            )
            continue
        english = [row for row in rows if not row.voice_only]
        if len(english) > 1:
            where = ", ".join(row.origin for row in english[1:])
            problems.append(
                Problem(
                    "translated-twice",
                    english[0].origin,
                    f"{line_id} is given English {len(english)} times; also at {where}",
                )
            )
        for row in english:
            problems.extend(_row_problems(store, row))
    problems.extend(_store_problems(store))
    problems.extend(_loader_agreement(translation))
    return problems


def _row_problems(store: Store, row: Row) -> Iterator[Problem]:
    record = store.lines.get(row.line_id)
    if record is None:
        return
    shape = select_shape(store, row.line_id)
    entry = row.entry
    if shape is not None:
        options, prompts = shape
        if not entry.is_select:
            yield Problem(
                "select-shape",
                row.origin,
                f"{row.line_id} is a SELECT of {options} option(s) but is written as a message",
            )
            return
        written_prompts, written_options = select_fields(entry, prompts)
        if len(written_options) != options or len(written_prompts) != prompts:
            yield Problem(
                "select-options",
                row.origin,
                f"{row.line_id} has {len(written_prompts)} prompt line(s) and "
                f"{len(written_options)} option(s); the executable fixes {prompts} and "
                f"{options}",
            )
        return
    if entry.is_select:
        yield Problem(
            "select-shape", row.origin, f"{row.line_id} is written as a SELECT but is a message"
        )
        return
    original = len(record.get("layout", {}).get("pages", ()))
    if len(entry.pages) == original:
        return
    voiced = bool(record.get("capacity", {}).get("pages_fixed_by_voice"))
    kind = "page-count" if voiced else "page-count-unvoiced"
    fixed = (
        "the page turns are timed to the voice clip and cannot move"
        if voiced
        else "the original's page breaks are not voice-timed, so this may be deliberate"
    )
    yield Problem(
        kind,
        row.origin,
        f"{row.line_id} has {len(entry.pages)} page(s); the original has {original} — {fixed}",
    )


def _store_problems(store: Store) -> Iterator[Problem]:
    """The reader's own decoding, against the shape the extractor recorded. Silent unless
    `build.py`'s tokeniser and `boku.sites.page_structure` disagree about a line."""
    for line_id, record in sorted(store.lines.items()):
        layout = record.get("layout")
        if layout is None:
            continue
        recorded = tuple(tuple(page) for page in layout["pages"])
        mine = store.japanese[line_id].column_counts
        if mine != recorded:
            yield Problem(
                "store-layout",
                line_id,
                f"the reader reads the columns as {mine}, the extract recorded {recorded}",
            )


def _loader_agreement(translation: Translation) -> Iterator[Problem]:
    """The reader's parse, against the loader the build reads English through.

    If these ever disagree, the reader is showing Jay something other than what would be
    built, which is the one failure a read-only reader can still cause.

    An id may carry several rows, and the loader keeps exactly one of them. The rows are
    matched by `origin` — where each was written — rather than by position, so this compares
    the row the loader actually kept even when that is not the first one the reader shows;
    the rows it did not keep are marked as ignored on the page instead.
    """
    if not translation.paths:
        return
    for line_id in sorted(set(translation.rows) | set(translation.built)):
        theirs = translation.built.get(line_id)
        english = translation.english_rows(line_id)
        if theirs is None:
            if english:
                yield Problem(
                    "reader-vs-loader",
                    line_id,
                    f"the reader shows the English at {english[0].origin}; boku.translation "
                    f"reads none",
                )
            continue
        mine = next((row for row in english if row.origin == theirs.origin), None)
        if mine is None:
            yield Problem(
                "reader-vs-loader",
                line_id,
                f"boku.translation builds this from {theirs.origin}; the reader shows no "
                f"English row written there",
            )
            continue
        if mine.entry != theirs:
            yield Problem(
                "reader-vs-loader",
                line_id,
                f"the reader reads {mine.entry!r}; boku.translation reads {theirs!r}",
            )
