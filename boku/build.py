"""The one image builder: a copy of your import, a list of byte edits, fresh EDC/ECC.

`PIPE-04`'s general build, and the machinery `boku trial` now runs on too. There is one
place that copies the image, one place that checks a byte range is what it is supposed to
be before writing it, and one place that turns sector writes into a manifest — because two
of them meant two answers to "what does this build refuse?", and the trial's answer was
the only one that had been tested.

What a build is
---------------
1. **A source image and an import.** The image is copied and patched in place: every LBA
   stays where it is, because 226,000 sectors of XA and STR sit behind `BOKU.BIN` at
   positions the executable addresses directly and PPF cannot grow an image (`PIPE-04`).
   The *import* under `disc/` is what the text sites are walked out of; the two are
   separate artifacts and every edit carries the bytes it expects, so a disagreement is a
   refusal before the first write.
2. **A translation**, read through `boku.translation.TranslationSource` — the seam that
   keeps `PIPE-02`'s committed format out of the build.
3. **An encoder and a box**, from `boku.layout`: what draws a character and how wide it
   is. The stock full-width cells and a `TXT-05` cell map are interchangeable here.
4. **Binary patches** — `(file, offset, old, new)` with the old bytes verified. The
   trial's renderer and band words are exactly this, and so is anything `TXT-05`'s
   assembler emits.

Nothing half-built escapes: the image is patched inside a staging directory beside `--out`
(`boku.staging`) and moved into place only once every write and the manifest have
succeeded.

Determinism: the same import, translation and encoder give the same image. Every mapping
written to the manifest is sorted, and the edits are applied in `(file, offset)` order.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from boku import __version__, edc
from boku.archive import ARCHIVE_NAME, DEFAULT_DISC_DIR, EXE_NAME, Archive, ArchiveError
from boku.arrays import ArrayError, SelectTables
from boku.disc import DirEntry, DiscError, DiscImage, DiscWriter, SectorWrite
from boku.edc import FORM1_DATA_SIZE
from boku.events import EventError
from boku.glyphs import TextError
from boku.importer import ImportRefused, check_out_dir, sha1_of
from boku.layout import (
    DIALOGUE_BAND,
    BoxSpec,
    CellMapEncoder,
    Encoder,
    LaidOut,
    LayoutError,
    StockEncoder,
    lay_out_array,
    lay_out_message,
    lay_out_select,
)
from boku.reinsert import ByteEdit, Plan, ReinsertRefused, check_disjoint, plan
from boku.sites import SiteError, Walk, load
from boku.staging import StagingRefused, staged
from boku.translation import SampleScenes, TranslationError, TranslationSource

DEFAULT_IMAGE = Path("disc/image.img")
BUILD_ROOT = Path("build")
DEFAULT_BUILD_NAME = "image"
DEFAULT_OUT_DIR = BUILD_ROOT / DEFAULT_BUILD_NAME
"""`build/<name>/`; `main_build` names the directory after the build unless told otherwise."""
IMAGE_NAME = "image.img"
CUE_NAME = "image.cue"
MANIFEST_NAME = "manifest.json"
MANIFEST_FORMAT = 1

EXE_PATH = f"/{EXE_NAME}"
ARCHIVE_PATH = f"/{ARCHIVE_NAME}"

CUE_TEXT = f'FILE "{IMAGE_NAME}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
"""One data track, raw 2352-byte sectors. The emulators want a cue beside the image."""


class BuildRefused(Exception):
    """The build will not proceed, and nothing was written."""


# --- what a build wrote -------------------------------------------------------------------


@dataclass
class SectorRecord:
    """A sector the build changed. `offset` is where it starts inside `file`."""

    lba: int
    file: str
    offset: int
    old_sha1: str
    new_sha1: str


class Ledger:
    """Collects sector writes so the manifest shows each LBA once, as it was and as it is.

    Two edits can share a sector, so the same LBA can be written twice; the manifest must
    still say what that sector looked like before the build touched it and after it
    finished. A sector whose bytes come back to where they started is dropped, so the
    manifest is exactly the set of sectors an image diff can see.
    """

    def __init__(self) -> None:
        self._first: dict[int, str] = {}
        self._last: dict[int, str] = {}
        self._where: dict[int, tuple[str, int]] = {}

    def add(self, writes: Sequence[SectorWrite], file_name: str, file_lba: int) -> None:
        for write in writes:
            self._first.setdefault(write.lba, write.old_sha1)
            self._last[write.lba] = write.new_sha1
            self._where[write.lba] = (file_name, (write.lba - file_lba) * FORM1_DATA_SIZE)

    def records(self) -> list[SectorRecord]:
        out = []
        for lba in sorted(self._first):
            if self._first[lba] == self._last[lba]:
                continue
            file_name, offset = self._where[lba]
            out.append(
                SectorRecord(
                    lba=lba,
                    file=file_name,
                    offset=offset,
                    old_sha1=self._first[lba],
                    new_sha1=self._last[lba],
                )
            )
        return out


@dataclass
class WrittenImage:
    """One finished build: where it is, what it came from, and every sector it moved."""

    image: Path
    cue: Path
    manifest: Path
    source_sha1: str
    result_sha1: str
    sectors: list[SectorRecord] = field(default_factory=list)

    @property
    def unchanged(self) -> bool:
        return not self.sectors


# --- writing an image -------------------------------------------------------------------------


def file_entries(image: DiscImage, refused: type[Exception] = BuildRefused) -> dict[str, DirEntry]:
    """The two files a patch writes into, looked up in the image's own filesystem."""
    found = {entry.path: entry for entry in image.walk()}
    out = {}
    for path in (EXE_PATH, ARCHIVE_PATH):
        if path not in found:
            raise refused(f"{image.path} has no {path}; this is not SCPS-10088")
        out[found[path].name] = found[path]
    return out


def verify_edits(
    image: DiscImage,
    entries: dict[str, DirEntry],
    edits: Sequence[ByteEdit],
    refused: type[Exception] = BuildRefused,
) -> None:
    """Refuse unless every edit's byte range still holds exactly what the edit expects.

    This is the gate that makes a write safe, and it is the one check every kind of edit
    shares: an EXE word the recipe measured, a text site the walk hashed, a whole rebuilt
    map pack. It fails on a mis-resolved offset, on an image that is not this dump, on an
    import whose files have drifted from the image they came from, and on an image that is
    already patched — all before a single sector is written.
    """
    for edit in edits:
        entry = entries.get(edit.file)
        if entry is None:
            raise refused(f"{edit.reason}: {edit.file} is not a file this build may write")
        if edit.end > entry.size:
            # `read_file_bytes` knows nothing about ISO 9660 and would happily read on
            # into whatever file follows this one, so only `write_file_bytes` would catch
            # this -- after the 660 MB copy and after earlier edits had been written.
            raise refused(
                f"{edit.reason}: writing {len(edit.new)} bytes at {edit.file}"
                f"+0x{edit.offset:x} would end at 0x{edit.end:x}, past the file's own "
                f"{entry.size}-byte extent. Nothing was written."
            )
        found = image.read_file_bytes(entry.lba, edit.offset, len(edit.old))
        if found != edit.old:
            at = next(i for i in range(len(edit.old)) if found[i] != edit.old[i])
            raise refused(
                f"{edit.file}+0x{edit.offset + at:x} holds {found[at : at + 8].hex(' ')} and "
                f"the build expects {edit.old[at : at + 8].hex(' ')} ({edit.reason}). Either "
                f"this image is already patched, or it is not the dump these offsets were "
                f"read from, or the import under disc/ has drifted from it; nothing was "
                f"written."
            )


def apply_edit(
    writer: DiscWriter, entries: dict[str, DirEntry], edit: ByteEdit, ledger: Ledger
) -> None:
    """Write one edit into the copy, recording every sector it moved."""
    entry = entries[edit.file]
    ledger.add(
        writer.write_file_bytes(entry.lba, edit.offset, edit.new, file_size=entry.size),
        edit.file,
        entry.lba,
    )


def write_image(
    source: Path,
    out_dir: Path,
    edits: Sequence[ByteEdit],
    *,
    manifest: Callable[[WrittenImage], str],
    what: str = "build",
    suffix: str = "building",
    refused: type[Exception] = BuildRefused,
) -> WrittenImage:
    """Copy `source` to `out_dir/image.img` and apply `edits` to the copy, in place.

    With no edits the copy is byte-identical to its source, which is `PIPE-05`'s round
    trip: `DiscWriter` does not write a sector whose bytes do not change, so an unchanged
    run leaves the image exactly as it found it.
    """
    source = Path(source)
    out_dir = Path(out_dir).resolve()
    entries = check_before_writing(source, out_dir, edits, what=what, refused=refused)
    with staged(out_dir, suffix=suffix) as stage:
        image = stage / IMAGE_NAME
        shutil.copyfile(source, image)
        (stage / CUE_NAME).write_text(CUE_TEXT, encoding="ascii")
        ledger = Ledger()
        with DiscWriter(image) as writer:
            verify_edits(writer, entries, edits, refused)
            for edit in edits:
                apply_edit(writer, entries, edit, ledger)
            writer.flush()
        written = WrittenImage(
            image=out_dir / IMAGE_NAME,
            cue=out_dir / CUE_NAME,
            manifest=out_dir / MANIFEST_NAME,
            source_sha1=sha1_of(source),
            result_sha1=sha1_of(image),
            sectors=ledger.records(),
        )
        (stage / MANIFEST_NAME).write_text(manifest(written), encoding="utf-8")
    return written


def check_before_writing(
    source: Path,
    out_dir: Path,
    edits: Sequence[ByteEdit],
    *,
    what: str = "build",
    refused: type[Exception] = BuildRefused,
) -> dict[str, DirEntry]:
    """Everything that can be refused *before* the 660 MB copy, in one place.

    A dry run makes the same checks and writes nothing, so `--dry-run` cannot report a
    clean build that the real one would refuse -- an already-patched image, a dump these
    offsets were not read from, or an `--out` that would eat the import.
    """
    source = Path(source)
    if not source.is_file():
        raise refused(f"{source} is not there: run `./make.sh import` first")
    check_output_directory(Path(out_dir).resolve(), source, what=what, refused=refused)
    with DiscImage(source) as reader:
        entries = file_entries(reader, refused)
        verify_edits(reader, entries, edits, refused)
    return entries


def check_output_directory(
    out_dir: Path,
    source: Path,
    *,
    what: str = "build",
    refused: type[Exception] = BuildRefused,
) -> None:
    """Refuse an output directory that would damage the import, or someone else's files."""
    try:
        check_out_dir(out_dir, manifest_name=MANIFEST_NAME, what=what, source=source, doing="build")
    except ImportRefused as error:
        raise refused(str(error)) from error


def verify_written_sectors(image: Path, records: Sequence[SectorRecord]) -> list[int]:
    """LBAs among `records` whose stored EDC/ECC do not match their own bytes (want: none)."""
    bad = []
    with DiscImage(image) as opened:
        for record in records:
            if not edc.check_sector(opened.read_raw(record.lba), record.lba).ok:
                bad.append(record.lba)
    return bad


# --- a translation, laid out -------------------------------------------------------------------


@dataclass
class LineResult:
    """What became of one translated line: its words, or why it was left alone."""

    line_id: str
    laid_out: LaidOut | None
    problems: tuple[str, ...]

    @property
    def written(self) -> bool:
        return self.laid_out is not None and not self.problems


def lay_out(
    archive: Archive,
    walk: Walk,
    translation: TranslationSource,
    encoder: Encoder,
    box: BoxSpec,
    *,
    indent_continuations: bool = False,
) -> list[LineResult]:
    """Turn every entry of a translation into words, collecting the lints it failed.

    Nothing is shortened and nothing is dropped silently: a line that does not fit comes
    back with its numbers and the caller decides (README § "Who this is for").
    """
    selects = SelectTables(archive)
    out: list[LineResult] = []
    for entry in translation:
        sites = walk.by_line.get(entry.line_id)
        if not sites:
            out.append(
                LineResult(
                    entry.line_id,
                    None,
                    (
                        f"{entry.line_id}: no text site has this id"
                        + (f" ({entry.origin})" if entry.origin else ""),
                    ),
                )
            )
            continue
        original = walk.raw(archive, sites[0])
        if entry.words is not None:
            out.append(
                LineResult(
                    entry.line_id,
                    LaidOut(entry.line_id, tuple(entry.words), (), (), ()),
                    (),
                )
            )
            continue
        kind = sites[0].kind.split("+")[0]
        if kind.startswith("SEL"):
            select_type, variant = (int(part) for part in kind[3:].split("."))
            laid = lay_out_select(
                entry.line_id,
                entry.options,
                original,
                selects.shape(select_type, variant),
                encoder,
                box,
                entry.prompts,
            )
        elif kind == "MSG":
            laid = lay_out_message(
                entry.line_id,
                entry.pages,
                original,
                encoder,
                box,
                indent_continuations=indent_continuations,
            )
        elif kind.startswith("ARR"):
            if entry.is_select:
                out.append(
                    LineResult(
                        entry.line_id,
                        None,
                        (
                            f"{entry.line_id} is a {sites[0].kind} site in a code file, and "
                            f"the translation gives it as a choice menu; the two are drawn "
                            f"by different code and are not interchangeable",
                        ),
                    )
                )
                continue
            laid = lay_out_array(
                entry.line_id, " ".join(entry.pages), original, encoder, sites[0].size
            )
        else:
            out.append(
                LineResult(
                    entry.line_id,
                    None,
                    (f"{entry.line_id} is a {sites[0].kind} site, which nothing lays out",),
                )
            )
            continue
        out.append(LineResult(entry.line_id, laid, laid.problems))
    return out


# --- the whole build ------------------------------------------------------------------------------


@dataclass
class BuildResult:
    """A finished (or dry-run) build: the image, the plan, and every line's verdict."""

    written: WrittenImage | None
    plan: Plan | None
    lines: list[LineResult]
    source_problems: tuple[str, ...]
    """What the translation source itself could not read — a malformed row, a repeated id.

    Collected by the loader and reported here, because a row nobody could parse is a line
    left in Japanese that no lint would otherwise mention (`lay_out`'s "nothing is dropped
    silently" has to be true of the reading as well as of the laying out)."""
    encoder: str
    box: BoxSpec
    translation: str
    binary_patches: tuple[ByteEdit, ...]

    @property
    def refused_lines(self) -> list[LineResult]:
        return [line for line in self.lines if not line.written]

    @property
    def written_lines(self) -> list[LineResult]:
        return [line for line in self.lines if line.written]


def build(
    source: Path = DEFAULT_IMAGE,
    out_dir: Path = DEFAULT_OUT_DIR,
    *,
    disc_dir: Path = DEFAULT_DISC_DIR,
    translation: TranslationSource | None = None,
    encoder: Encoder | None = None,
    box: BoxSpec | None = None,
    binary_patches: Sequence[ByteEdit] = (),
    in_place: bool = False,
    indent_continuations: bool = False,
    skip_unfitted: bool = False,
    dry_run: bool = False,
    name: str = DEFAULT_BUILD_NAME,
) -> BuildResult:
    """Read an import and a translation, and write a patched image (`PIPE-04`).

    `skip_unfitted` leaves a line that fails a lint in its original Japanese and reports
    it, which is what a work-in-progress translation needs; without it one overflowing
    line refuses the whole build. Either way the English is never shortened.

    `dry_run` does everything up to the copy and writes nothing — the lint report.
    """
    box = box or DIALOGUE_BAND
    encoder = encoder or StockEncoder.load()
    lines: list[LineResult] = []
    the_plan: Plan | None = None
    edits = list(binary_patches)

    source_problems = tuple(getattr(translation, "problems", ()) or ())
    if source_problems and not skip_unfitted:
        raise BuildRefused(
            f"{len(source_problems)} problem(s) reading the translation, first: "
            f"{source_problems[0]}"
        )
    if translation is not None:
        archive, walk = load(disc_dir)
        lines = lay_out(
            archive,
            walk,
            translation,
            encoder,
            box,
            indent_continuations=indent_continuations,
        )
        problems = [p for line in lines for p in line.problems]
        if problems and not skip_unfitted:
            raise BuildRefused(
                f"{len(problems)} translation problem(s), first: {problems[0]}. Nothing is "
                f"cut to fit (README); pass --skip-unfitted to build the lines that do fit "
                f"and leave the rest in Japanese, or give the text more room."
            )
        words = {line.line_id: line.laid_out.words for line in lines if line.written}
        the_plan, refused = _plan_what_fits(archive, walk, words, in_place, skip_unfitted)
        lines = [
            LineResult(line.line_id, line.laid_out, line.problems + refused.get(line.line_id, ()))
            for line in lines
        ]
        edits += list(the_plan.edits)

    edits.sort(key=lambda e: (e.file, e.offset))
    # `plan` checks its own edits are disjoint; the caller's binary patches were not in
    # that set. A rebuilt member's edit covers its whole byte range, so a patch aimed
    # inside one would be applied over the rebuild at an offset the growth has already
    # moved -- and would verify against the *source* first, so nothing would notice.
    check_disjoint(edits)
    result = BuildResult(
        written=None,
        plan=the_plan,
        lines=lines,
        source_problems=source_problems,
        encoder=getattr(encoder, "name", type(encoder).__name__),
        box=box,
        translation=getattr(translation, "name", "none") if translation else "none",
        binary_patches=tuple(binary_patches),
    )
    if dry_run:
        check_before_writing(source, out_dir, edits, what=name)
        return result
    result.written = write_image(
        source,
        out_dir,
        edits,
        manifest=lambda written: manifest_json(written, result, name),
        what=name,
    )
    return result


def _plan_what_fits(
    archive: Archive,
    walk: Walk,
    words: dict[str, tuple[int, ...]],
    in_place: bool,
    skip_unfitted: bool,
) -> tuple[Plan, dict[str, tuple[str, ...]]]:
    """Plan the reinsertion, optionally dropping the lines that do not fit and retrying.

    A refusal names the logical lines it is about, and a dropped line is dropped **at
    every copy**: half-writing a line would leave two map variants of one event disagreeing
    in their text, which is exactly the invariant `boku.sites.Walk.conflicts` exists to
    assert. Each round removes at least one line, so the loop ends.
    """
    refused: dict[str, tuple[str, ...]] = {}
    while True:
        try:
            return plan(archive, walk, words, in_place=in_place), refused
        except ReinsertRefused as error:
            if not skip_unfitted or not error.lines:
                raise
            for line_id in error.lines:
                words.pop(line_id, None)
                refused[line_id] = (str(error),)


def manifest_json(written: WrittenImage, result: BuildResult, name: str) -> str:
    """Everything a later reader needs to say what this image is, sorted and reproducible."""
    document = {
        "format": MANIFEST_FORMAT,
        "tool": __version__,
        "build": name,
        "source_sha1": written.source_sha1,
        "result_sha1": written.result_sha1,
        "translation": result.translation,
        "translation_problems": list(result.source_problems),
        "encoder": result.encoder,
        "box": {"name": result.box.name, "width": result.box.width, "lines": result.box.lines},
        "lines_written": sorted(line.line_id for line in result.written_lines),
        "lines_refused": {
            line.line_id: list(line.problems)
            for line in sorted(result.refused_lines, key=lambda line: line.line_id)
        },
        "members_rebuilt": sorted(result.plan.members_rebuilt) if result.plan else [],
        "member_growth": dict(sorted(result.plan.growth.items())) if result.plan else {},
        "binary_patches": [
            {
                "file": patch.file,
                "offset": f"0x{patch.offset:x}",
                "old": patch.old.hex(" "),
                "new": patch.new.hex(" "),
                "meaning": patch.reason,
            }
            for patch in result.binary_patches
        ],
        "sectors": [
            {
                "lba": record.lba,
                "file": record.file,
                "offset": f"0x{record.offset:x}",
                "old_sha1": record.old_sha1,
                "new_sha1": record.new_sha1,
            }
            for record in written.sectors
        ],
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def format_summary(result: BuildResult) -> str:
    """What the command prints: what fits, what does not, and what moved."""
    out: list[str] = []
    if result.written:
        out.append(f"wrote {result.written.image} ({result.written.result_sha1})")
        out.append(f"  from {result.written.source_sha1}")
    else:
        out.append("dry run: nothing was written")
    out.append(f"  translation: {result.translation}; encoder: {result.encoder}")
    for problem in result.source_problems:
        out.append(f"    ! {problem}")
    out.append(
        f"  {len(result.written_lines)} line(s) laid out, {len(result.refused_lines)} refused"
    )
    # One refusal can name a whole scene -- a member out of sector slack drops every line
    # in it at once -- so the report counts distinct problems rather than printing the
    # same sentence fifteen times.
    problems: dict[str, int] = {}
    for line in result.refused_lines:
        for problem in line.problems:
            problems[problem] = problems.get(problem, 0) + 1
    for problem, count in list(problems.items())[:20]:
        out.append(f"    - {problem}" + (f"  [{count} lines]" if count > 1 else ""))
    if len(problems) > 20:
        out.append(f"    ... {len(problems) - 20} more")
    if result.plan:
        out.append(
            f"  {len(result.plan.members_rebuilt)} member(s) rebuilt, "
            f"{len(result.plan.edits)} byte range(s) changed"
        )
        for member, delta in sorted(result.plan.growth.items()):
            out.append(f"    {member}: {delta:+d} bytes")
    if result.written:
        out.append(f"  {len(result.written.sectors)} sectors changed; {result.written.manifest}")
        if result.written.unchanged:
            out.append("  nothing was written: this image is byte-identical to its source")
    return "\n".join(out)


def main_build(
    source: str | None,
    out_dir: Path | None,
    translation_dir: Path | None,
    cell_map: Path | None,
    disc_dir: Path,
    name: str,
    skip_unfitted: bool,
    dry_run: bool,
    binary_patches: Sequence[ByteEdit] = (),
) -> int:
    """`boku build`. Every refusal reaches the contributor as one sentence."""
    out_dir = Path(out_dir) if out_dir else BUILD_ROOT / name
    try:
        translation = (
            SampleScenes.from_directory(Path(translation_dir)) if translation_dir else None
        )
        encoder = CellMapEncoder.from_json(Path(cell_map)) if cell_map else StockEncoder.load()
        result = build(
            source=Path(source) if source else DEFAULT_IMAGE,
            out_dir=out_dir,
            disc_dir=disc_dir,
            translation=translation,
            encoder=encoder,
            binary_patches=binary_patches,
            skip_unfitted=skip_unfitted,
            dry_run=dry_run,
            name=name,
        )
    except (
        ArchiveError,
        ArrayError,
        BuildRefused,
        DiscError,
        EventError,
        LayoutError,
        ReinsertRefused,
        SiteError,
        StagingRefused,
        TextError,
        TranslationError,
        OSError,
    ) as error:
        print(f"boku build: {error}")
        return 1
    print(format_summary(result))
    if result.written:
        bad = verify_written_sectors(result.written.image, result.written.sectors)
        if bad:
            print(f"boku build: {len(bad)} written sectors fail their own EDC/ECC: {bad[:8]}")
            return 1
    return 0


__all__ = [
    "BuildRefused",
    "BuildResult",
    "ByteEdit",
    "Ledger",
    "LineResult",
    "ReinsertRefused",
    "SectorRecord",
    "WrittenImage",
    "apply_edit",
    "build",
    "file_entries",
    "format_summary",
    "lay_out",
    "verify_edits",
    "verify_written_sectors",
    "write_image",
]
