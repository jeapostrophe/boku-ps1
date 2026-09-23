"""Per day, every line the player can meet and why it is not English yet.

    ./make.sh coverage --day 1
    ./make.sh coverage --day 1 --manifest build/days/manifest.json --only missing refused

`./make.sh lint-translation` answers "is what we wrote correct?"; this answers the other
question, the one a player asks after a session with the build: *that line was still in
Japanese -- why?* Every line in a day's reach gets one of four states:

* **`translated`** -- a row in `translation/days/` gives it English and the build's
  manifest lists it under `lines_written`. It means exactly *this manifest's build laid
  the line out*: not that the line is in the image you played, and not that the game
  reads the copy the build wrote. The header names the build, the image sha1 and the
  build id the emulator's window title shows, so a reader can check the report is about
  their image, and `format_moved` says where to look when such a line is Japanese anyway.
* **`refused`** -- English exists and the image did not get it: the manifest lists the id
  under `lines_refused` (`boku build --skip-unfitted` leaves such a line in Japanese and
  records why), or lists it under neither, which is the same outcome and says so.
* **`missing`** -- no row for the id, or a row that says `(voice only)` while the disc
  holds text for it. Nobody was ever asked to translate it.
* **`not-event`** -- an `<file>@<offset>.<item>` id with no English yet: the menus, the
  insect and kite books, the title screen. These belong to no event and are translated in
  `translation/days/arrays.txt` (`PLAN TRN-09`); the report names the surface each one
  sits on. Once a row gives one English it is `translated` or `refused` like any other
  line -- and most are refused until the menu and overlay surfaces are built
  (`PLAN TXT-05`), since an array item has no bytes to grow into.

Which days reach which events is `boku.script_store.scene_plays_on`'s answer, the same one
`scenes_of_day` gives `boku.packets`, so a day's coverage and a day's translator packets
cover the same scenes by construction; `scene_scope` turns it into the report's sentence.

This reads the gitignored `disc/script/` store and the committed translation. It writes
nothing, and the only thing it prints from the store is a line's id and its speaker label
(CLAUDE.md § "This repo is public").
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import DEFAULT_DISC_DIR
from boku.extract import SCRIPT_DIR_NAME
from boku.lint import Row, load_rows, translation_paths
from boku.script_store import (
    Store,
    StoreMissing,
    load_store,
    node_line,
    scene_day,
    scene_plays_on,
)

DAYS_DIR = REPO_ROOT / "translation" / "days"
"""Where the English is, and this tool's default source."""

DEFAULT_MANIFEST = REPO_ROOT / "build" / "days" / "manifest.json"
"""`./make.sh build-days` writes this. Used when `--manifest` names nothing and it exists."""

TRANSLATED = "translated"
REFUSED = "refused"
MISSING = "missing"
NOT_EVENT = "not-event"
STATES = (TRANSLATED, REFUSED, MISSING, NOT_EVENT)

DEFAULT_DETAIL = (REFUSED, MISSING)
"""The states `--only` defaults to listing line by line: the two a reader acts on. The
table counts every state either way."""

DAY = "day"
ANY_DAY = "any-day"
SURFACE = "surface"
SCOPES = (DAY, ANY_DAY, SURFACE)

WRITTEN_FIELD = "lines_written"
REFUSED_FIELD = "lines_refused"
RELOCATIONS_FIELD = "relocations"
MEMBER_FIELD = "member"
BUILD_FIELD = "build"
RESULT_SHA1_FIELD = "result_sha1"
"""The fields of the build's manifest this tool reads (`boku.build.manifest_json`). The
first two are required; a build that moved no member may carry no `relocations`, whose
entries this reads by `member`; the last two only name the image in the header."""

BUILD_ID_NAME = "BUILD-ID.txt"
"""`make.sh`'s `cmd_build_days` writes the emulator-visible build id here, beside the
manifest. Read when present, so the report can be matched to the image that was played."""

DAYS = tuple(range(1, 8))
"""The days `translation/days/` covers, and what a bare `boku coverage` reports."""


class CoverageError(Exception):
    """A manifest this tool cannot read."""


# --- the build's manifest -------------------------------------------------------------------


@dataclass(frozen=True)
class Manifest:
    """What one built image did with each line, as `boku build` recorded it."""

    written: frozenset[str]
    refused: Mapping[str, tuple[str, ...]]
    name: str
    relocated: frozenset[str] = frozenset()
    """Members this build moved to a new LBA (`PLAN PIPE-03`). A place to look, not a
    diagnosis -- `format_moved` says what would make one of them a suspect."""
    build: str = ""
    """The manifest's own `build` name -- which build this is (`days`, `trial`, ...)."""
    result_sha1: str = ""
    """SHA-1 of the image the build wrote, as the manifest recorded it."""
    build_id: str = ""
    """`BUILD-ID.txt` beside the manifest, when `make.sh build-days` left one: the id the
    emulator's window title carries, so a report can be matched to a play session."""
    checked: bool = True
    """False for `unchecked()`: no image was consulted, so no line can be called refused."""

    @classmethod
    def unchecked(cls) -> Manifest:
        """No manifest given -- English existing is all that can be said."""
        return cls(written=frozenset(), refused={}, name="(no manifest)", checked=False)

    def describe(self) -> str:
        """The manifest, named the way a reader can check it against what they played."""
        if not self.checked:
            return f"{self.name} (nothing was checked against an image)"
        parts = [f"build {self.build!r}" if self.build else "no build name"]
        if self.result_sha1:
            parts.append(f"image sha1 {self.result_sha1[:8]}")
        parts.append(f"build id {self.build_id}" if self.build_id else f"no {BUILD_ID_NAME}")
        return f"{self.name} ({', '.join(parts)})"

    @classmethod
    def load(cls, path: Path) -> Manifest:
        path = Path(path)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise CoverageError(f"{path}: {error.strerror or error}") from None
        except ValueError as error:
            raise CoverageError(f"{path} is not JSON: {error}") from None
        absent = [field for field in (WRITTEN_FIELD, REFUSED_FIELD) if field not in document]
        if absent:
            raise CoverageError(
                f"{path} carries no {' and no '.join(absent)}, so it is not a build manifest "
                f"-- `./make.sh build-days` writes one beside the image it builds"
            )
        refused = document[REFUSED_FIELD]
        build_id = path.parent / BUILD_ID_NAME
        return cls(
            written=frozenset(document[WRITTEN_FIELD]),
            refused={line_id: tuple(problems) for line_id, problems in refused.items()},
            name=str(path),
            relocated=frozenset(
                placement[MEMBER_FIELD] for placement in document.get(RELOCATIONS_FIELD, ())
            ),
            build=str(document.get(BUILD_FIELD, "")),
            result_sha1=str(document.get(RESULT_SHA1_FIELD, "")),
            build_id=build_id.read_text(encoding="utf-8").strip() if build_id.is_file() else "",
        )


# --- which events a day reaches ---------------------------------------------------------------


def scene_scope(scene: dict, day: int) -> tuple[str, str] | None:
    """`(scope, why)` for this event on this day, or `None` when the day never reaches it.

    `boku.script_store.scene_plays_on` decides reach; everything here is the sentence the
    report prints about *why* the event is in front of the reader.
    """
    if not scene_plays_on(scene, day):
        return None
    dated, derived = scene_day(scene)
    id_day = scene["id"] // 100
    by_id = "; its id says so too" if id_day == day else ""
    if dated is not None and not derived:
        return DAY, f"day {day}: the data dates it here{by_id}"
    condition = scene["when"].get("condition")
    if derived and dated == day:
        return DAY, f"day {day}: its condition tests `day=={day}`{by_id}"
    if id_day == day:
        return DAY, (
            f"day {day} by its id ({scene['id']} // 100); the data gives it no day of its "
            f"own, so it can fire on other days too"
        )
    if derived:
        return ANY_DAY, (
            f"no day in the data: `day=={dated}` is read off its condition, which day "
            f"{day} can satisfy all the same, so this day reaches it too "
            f"(condition `{condition}`)"
        )
    return ANY_DAY, (
        "no day in the data: a day-independent event, so whether day "
        f"{day} reaches it turns on flags and place, which the data does not decide"
        + (f" (condition `{condition}`)" if condition else " (no entry condition)")
    )


# --- one line's verdict --------------------------------------------------------------------


@dataclass(frozen=True)
class LineCoverage:
    """One line the player can meet on one day, and what the build did with it."""

    scope: str
    group: str
    """The event it belongs to, or, for a `not-event` line, the surface it sits on."""
    line_id: str
    state: str
    reason: str
    scope_reason: str = ""
    speaker: str = ""
    place: str = ""
    """The map bases the event sits on -- what a reader needs to judge whether a
    day-independent event is somewhere this day can walk to."""
    origin: str = ""
    """`file:line` of the row that translates it, empty when there is none."""
    moved: tuple[str, ...] = ()
    """Members holding this line's bytes that the build relocated (`Manifest.relocated`)."""


def _rows_by_id(rows: Sequence[Row]) -> dict[str, Row]:
    """One row per id, preferring a row that carries English (`translated-twice` is the
    lint's finding, not this tool's)."""
    chosen: dict[str, Row] = {}
    for row in rows:
        if row.line_id not in chosen or (not chosen[row.line_id].has_english and row.has_english):
            chosen[row.line_id] = row
    return chosen


def _origin(row: Row | None) -> str:
    return f"{row.file}:{row.number}" if row else ""


def _lines_of(scene: dict) -> list[str]:
    """Every id this event can reach: the `lines` it lists, then any its nodes name.

    A node can name an id with text that `lines` leaves out; reading only `lines` loses it
    silently, which is the one shape of bug a coverage report must not have. (A voice-only
    node names an id with no record at all -- dropped by the caller, which looks it up.)
    """
    named = [line for line in map(node_line, scene["nodes"]) if line is not None]
    return list(dict.fromkeys([*scene["lines"], *named]))


def _speaker(record: dict) -> str:
    return str(record.get("speaker", {}).get("label") or "")


def _moved(record: dict, manifest: Manifest) -> tuple[str, ...]:
    """The members holding this line that this build moved, in the record's own order."""
    members = dict.fromkeys(site["member"] for site in record.get("sites", ()))
    return tuple(member for member in members if member in manifest.relocated)


NO_EVENT = "(no event)"
"""The group for a record whose id names no surface and whose event no scene holds."""


def surface_of(line_id: str) -> str:
    """The file a non-event line sits in: `exe`, `hhon`, `musi`, `title`, `tako`, `zukan`."""
    return line_id.split("@", 1)[0] if "@" in line_id else NO_EVENT


def _classify(line_id: str, row: Row | None, manifest: Manifest) -> tuple[str, str]:
    if row is None:
        return MISSING, "no row in the translation for this id -- nobody was asked for it"
    origin = _origin(row)
    if not row.has_english:
        return MISSING, (
            f"{origin} lists it '(voice only)', but the disc holds text for it, so the "
            f"game draws that text"
        )
    if not manifest.checked:
        return TRANSLATED, f"English at {origin}; no manifest given, so the image was not checked"
    if line_id in manifest.refused:
        return REFUSED, "; ".join(manifest.refused[line_id])
    if line_id in manifest.written:
        return TRANSLATED, f"English at {origin}, written by {manifest.name}"
    return REFUSED, (
        f"English at {origin}, but {manifest.name} lists it under neither {WRITTEN_FIELD} "
        f"nor {REFUSED_FIELD}: the image holds the Japanese and the build said nothing"
    )


def coverage(store: Store, rows: Sequence[Row], day: int, manifest: Manifest) -> list[LineCoverage]:
    """Every line the player can meet on `day`, classified, in report order."""
    by_id = _rows_by_id(rows)
    out: list[LineCoverage] = []
    for scene in store.scenes:
        scoped = scene_scope(scene, day)
        if scoped is None:
            continue
        scope, why = scoped
        for line_id in _lines_of(scene):
            record = store.lines.get(line_id)
            if record is None:
                continue
            row = by_id.get(line_id)
            state, reason = _classify(line_id, row, manifest)
            out.append(
                LineCoverage(
                    scope=scope,
                    group=scene["event"],
                    line_id=line_id,
                    state=state,
                    reason=reason,
                    scope_reason=why,
                    speaker=_speaker(record),
                    place=",".join(scene["where"]["bases"]),
                    origin=_origin(row),
                    moved=_moved(record, manifest),
                )
            )
    # Every record no scene claims, not only the `@` ids: a line the extract wrote and no
    # event lists is exactly the line a report must not lose, whatever its id looks like.
    # `Store.event_of_line`'s keys are the ids `_lines_of` yields over every scene.
    for line_id, record in store.lines.items():
        if line_id in store.event_of_line:
            continue
        surface = surface_of(line_id)
        row = by_id.get(line_id)
        english = f" (English at {_origin(row)})" if row and row.has_english else ""
        state = NOT_EVENT
        if surface == NO_EVENT:
            reason = (
                f"an event id no scene in the store claims: the extract wrote the record "
                f"and no scene lists it, so no day can be shown to reach it and nothing "
                f"asks for its English{english}"
            )
            scope_reason = "claimed by no scene: reported on every day rather than lost"
        else:
            scope_reason = f"`{surface}`: reachable on any day, from a menu or a book"
            if row is not None:
                state, reason = _classify(line_id, row, manifest)
            else:
                reason = (
                    f"an array, overlay or code-immediate line on the `{surface}` surface; "
                    f"it belongs to no event and translation/days/arrays.txt has no English "
                    f"for it"
                )
        out.append(
            LineCoverage(
                scope=SURFACE,
                group=surface,
                line_id=line_id,
                state=state,
                reason=reason,
                scope_reason=scope_reason,
                speaker=_speaker(record),
                origin=_origin(row),
                moved=_moved(record, manifest),
            )
        )
    return sorted(out, key=_order)


_INDEX = re.compile(r"\.(\d+)$")


def _order(result: LineCoverage) -> tuple:
    """Scope, then event, then the line's own index -- `.10` after `.9`, not before it."""
    index = _INDEX.search(result.line_id)
    return (
        SCOPES.index(result.scope),
        result.group,
        int(index.group(1)) if index else -1,
        result.line_id,
    )


# --- the report --------------------------------------------------------------------------------

SCOPE_HEADINGS = {
    DAY: (
        "events this day reaches by its own day, by its id, or by a `day==N` in its "
        "condition -- each row says which"
    ),
    ANY_DAY: "day-independent events -- no day in the data (translation/days/shared.txt)",
    SURFACE: "non-event surfaces -- menus, books, the title screen (translation/days/arrays.txt)",
}


def counts(results: Iterable[LineCoverage]) -> dict[str, int]:
    tally = dict.fromkeys(STATES, 0)
    for result in results:
        tally[result.state] += 1
    return tally


def _by_group(results: Iterable[LineCoverage]) -> dict[str, list[LineCoverage]]:
    """The results under each event or surface, groups in name order, lines in report order."""
    grouped: dict[str, list[LineCoverage]] = {}
    for result in results:
        grouped.setdefault(result.group, []).append(result)
    return dict(sorted(grouped.items()))


def format_report(
    results: Sequence[LineCoverage], detail: Sequence[str] = DEFAULT_DETAIL
) -> list[str]:
    """The table, grouped by event, with a detail line under each interesting line."""
    out: list[str] = []
    for scope in SCOPES:
        in_scope = [result for result in results if result.scope == scope]
        if not in_scope:
            continue
        out.append("")
        out.append(f"== {scope}: {SCOPE_HEADINGS[scope]} ==")
        out.append(
            f"{'event':<8} {'lines':>5} {'transl':>6} {'refused':>7} {'missing':>7} "
            f"{'not-event':>9}  {'place':<14} where"
        )
        for group, lines in _by_group(in_scope).items():
            tally = counts(lines)
            where = ", ".join(
                sorted({result.origin.split(":")[0] for result in lines if result.origin})
            )
            out.append(
                f"{group:<8} {len(lines):>5} {tally[TRANSLATED]:>6} {tally[REFUSED]:>7} "
                f"{tally[MISSING]:>7} {tally[NOT_EVENT]:>9}  {lines[0].place or '-':<14} "
                f"{where or '-'}"
            )
            if any(result.state in detail for result in lines):
                out.append(f"         {lines[0].scope_reason}")
            for result in lines:
                if result.state in detail:
                    speaker = f" [{result.speaker}]" if result.speaker else ""
                    out.append(f"    {result.line_id}{speaker} {result.state}: {result.reason}")
    return out + format_moved(results)


def moved_lines(results: Sequence[LineCoverage]) -> list[LineCoverage]:
    """The `translated` lines whose bytes live in a member this build relocated.

    Only `translated` ones: a `missing` or `refused` line is Japanese because nobody wrote
    English for it or the build could not fit it, and which member holds its bytes explains
    neither. Listing those made most of this section noise.
    """
    return [result for result in results if result.moved and result.state == TRANSLATED]


def format_moved(results: Sequence[LineCoverage]) -> list[str]:
    """Where to look *after* a translated line turns out to be Japanese on Beetle.

    Membership is not a diagnosis; the section's own prose carries the refutation and the
    evidence for it, because its reader is the person holding the report.
    """
    moved = moved_lines(results)
    if not moved:
        return []
    translated = sum(1 for result in results if result.state == TRANSLATED)
    members = sorted({member for result in moved for member in result.moved})
    out = [
        "",
        f"== translated lines whose bytes live in a member this build relocated -- "
        f"{len(moved)} of {translated}, {len(members)} member(s) ==",
        "   Membership proves nothing on its own: relocated members draw English on Beetle",
        "   today (E0171.0 in M_H02001, E0220.0 in EV0220.BIN). Relocation (PLAN PIPE-03) is a",
        "   suspect only for a line `translated` here that a run of THIS image shows in",
        "   Japanese -- and then this is the list to check it against.",
    ]
    for group, lines in _by_group(moved).items():
        in_members = sorted({member for result in lines for member in result.moved})
        out.append(f"    {group}: {len(lines)} line(s) in {', '.join(in_members)}")
    return out


def summarise(results: Sequence[LineCoverage], day: int) -> str:
    tally = counts(results)
    events = {result.group for result in results if result.scope != SURFACE}
    surfaces = {result.group for result in results if result.scope == SURFACE}
    parts = ", ".join(f"{state} {tally[state]}" for state in STATES)
    return (
        f"day {day}: {len(results)} line(s) across {len(events)} event(s) and "
        f"{len(surfaces)} non-event surface(s) -- {parts}"
        f"; {len(moved_lines(results))} translated line(s) sit in a member the build moved"
    )


# --- the command line ---------------------------------------------------------------------------


def main_coverage(
    days: Sequence[int] | None,
    disc_dir: Path,
    sources: Sequence[Path] | None,
    manifest_path: Path | None,
    only: Sequence[str] | None,
    scopes: Sequence[str] | None = None,
) -> int:
    paths = translation_paths(list(sources) if sources else [DAYS_DIR])
    if not paths:
        print(f"coverage: no *.txt translation files under {sources or DAYS_DIR}", file=sys.stderr)
        return 2
    try:
        store = load_store(Path(disc_dir) / SCRIPT_DIR_NAME)
    except StoreMissing as error:
        print(f"coverage: {error}", file=sys.stderr)
        return 2
    if manifest_path is None and DEFAULT_MANIFEST.is_file():
        manifest_path = DEFAULT_MANIFEST
    try:
        manifest = Manifest.load(manifest_path) if manifest_path else Manifest.unchecked()
    except CoverageError as error:
        print(f"coverage: {error}", file=sys.stderr)
        return 2
    rows, _ = load_rows(paths)
    print(
        f"read {', '.join(path.name for path in paths)} ({len(rows)} row(s)) against "
        f"{store.root} and {manifest.describe()}"
    )
    detail = tuple(only) if only else DEFAULT_DETAIL
    wanted = tuple(scopes) if scopes else SCOPES
    for day in days or DAYS:
        results = [r for r in coverage(store, rows, day, manifest) if r.scope in wanted]
        for line in format_report(results, detail):
            print(line)
        print("")
        print(summarise(results, day))
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "sources",
        nargs="*",
        type=Path,
        metavar="FILE",
        help=f"translation files or directories of them (default: {DAYS_DIR.name}/)",
    )
    parser.add_argument(
        "--day",
        dest="days",
        type=int,
        action="append",
        metavar="N",
        help=f"an in-game day to report; repeatable (default: {DAYS[0]}-{DAYS[-1]})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        metavar="FILE",
        help=(
            f"the build manifest saying what the image actually got (default: "
            f"{DEFAULT_MANIFEST.relative_to(REPO_ROOT)} when it exists). Without one, a "
            f"line with English is reported as translated and the image is not checked"
        ),
    )
    parser.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        metavar="DIR",
        help=f"the import whose script store the days are read from (default: {DEFAULT_DISC_DIR}/)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=STATES,
        metavar="STATE",
        help=f"which states to list line by line, from {', '.join(STATES)} "
        f"(default: {', '.join(DEFAULT_DETAIL)}); the table counts them all either way",
    )
    parser.add_argument(
        "--scope",
        dest="scopes",
        nargs="+",
        choices=SCOPES,
        metavar="SCOPE",
        help=f"which sections to report, from {', '.join(SCOPES)} (default: all)",
    )
    parser.set_defaults(
        run=lambda args: main_coverage(
            args.days, args.disc, args.sources, args.manifest, args.only, args.scopes
        )
    )
    return parser
