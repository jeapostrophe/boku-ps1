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

import hashlib
import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from boku import __version__, edc
from boku.archive import (
    ARCHIVE_NAME,
    DEFAULT_DISC_DIR,
    EXE_LOAD_BIAS,
    EXE_NAME,
    OVERLAY_LOAD_ADDRESS,
    Archive,
    ArchiveError,
)
from boku.array_relocate import (
    DEAD_REGIONS,
    PC_HOST_DATA,
    ArrayPlan,
    ArrayRoomRefused,
    Region,
    Scanned,
    plan_arrays,
    scans,
)
from boku.arrays import (
    CODE_LABEL_MARK,
    SAVE_TITLE_LINE_ID,
    ArrayError,
    CodeLabel,
    SelectTables,
    byte_limit,
    read_code_labels,
    unreachable,
)
from boku.boxes import box_for, box_spec_for
from boku.code_text import (
    BANNERS,
    DATE_LABELS,
    banner_of,
    code_label_edits,
    lay_out_banner,
    lay_out_code_label,
    lay_out_date_label,
    lay_out_save_title,
)
from boku.disc import DirEntry, DiscError, DiscImage, DiscWriter, SectorWrite
from boku.edc import FORM1_DATA_SIZE
from boku.events import VOICE_KEY_SIZE, EventError
from boku.glyphs import GlyphTable, TextError
from boku.importer import ImportRefused, check_out_dir, sha1_of
from boku.layout import (
    ANSWER_PAIR,
    DIALOGUE_BAND,
    MENU_IS_SEL,
    SELECT_ROW,
    BoxSpec,
    CellMapEncoder,
    Encoder,
    LaidOut,
    LayoutError,
    StockEncoder,
    answer_pair_code,
    lay_out_answer_pair,
    lay_out_array,
    lay_out_array_select,
    lay_out_message,
    lay_out_select,
    lay_out_subtitle,
    original_marks,
    select_row_of,
    speaker_label,
)
from boku.reinsert import (
    MAP_WORK_AREA_END,
    ByteEdit,
    Plan,
    ReinsertRefused,
    check_disjoint,
    check_no_double_write,
    plan,
)
from boku.relocate import MOVIE_BLOCK_RESERVE, RelocationRefused, Run, SectorEdit
from boku.relocate import check_disjoint as check_sectors_disjoint
from boku.sites import SiteError, Walk, load
from boku.staging import StagingRefused, staged
from boku.texture_text import TextureTextError
from boku.texture_text import build_edits as build_texture_edits
from boku.textures import TextureError
from boku.tim import TimError
from boku.translation import (
    SampleScenes,
    TranslationEntry,
    TranslationError,
    TranslationSource,
    select_fields,
)
from boku.voice import clip_ticks

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


ARENA_FILE = "(no file)"
"""What the manifest calls a sector that belongs to no file: `PIPE-03`'s relocation arena."""


def verify_sectors(
    image: DiscImage, edits: Sequence[SectorEdit], refused: type[Exception] = BuildRefused
) -> None:
    """Refuse unless every sector a relocation writes still holds what it expects.

    The counterpart of `verify_edits` for the sectors outside every file. A Form 2 filler
    sector reads as its 2,048 zero bytes (`DiscImage.read_form1_span`), so an arena that
    has already been written into — a second build over a built image — is a refusal here
    and not a member quietly laid over another one.
    """
    for edit in edits:
        if edit.lba < 0 or edit.end > image.sector_count:
            raise refused(
                f"{edit.reason}: sectors {edit.lba}..{edit.end - 1} fall outside the "
                f"{image.sector_count}-sector image. Nothing was written."
            )
        found = image.read_form1_span(edit.lba, edit.sectors)
        if found != edit.old:
            at = next(i for i in range(len(edit.old)) if found[i] != edit.old[i])
            raise refused(
                f"LBA {edit.lba + at // FORM1_DATA_SIZE}+0x{at % FORM1_DATA_SIZE:x} holds "
                f"{found[at : at + 8].hex(' ')} and the build expects "
                f"{edit.old[at : at + 8].hex(' ')} ({edit.reason}). Either this image is "
                f"already patched, or it is not the dump these offsets were read from; "
                f"nothing was written."
            )


def check_no_sector_clash(
    patches: Sequence[ByteEdit],
    sectors: Sequence[SectorEdit],
    archive: Archive,
) -> None:
    """Refuse a caller's byte patch that a relocation would also write, by LBA.

    The trap: a `TITLE.OVL` array translated into more bytes relocates the overlay, and
    the font build's overlay patch then writes the sectors the overlay abandoned — a
    corrupt image with every other gate green. `check_no_double_write` makes the same
    check over the edits the reinserter produces; a patch handed in from outside
    (`TXT-05`'s renderer edit set) was never in that set.
    """
    check_no_double_write(patches, sectors, archive, refused=BuildRefused)


def check_resident(edits: Sequence[ByteEdit]) -> None:
    """Refuse an executable edit inside the overlay region.

    The executable is loaded once, by the BIOS; from `g_overlay_base` to the end of the file
    every byte is rewritten by some overlay load (a load is whole sectors, and `MUSI.OVL`'s
    reaches past the file's end -- research/text-renderer.md § 6), so a table or hook kept
    there is zeroed and never comes back. A `BOKU.BIN` edit is an overlay's own bytes.
    """
    for edit in edits:
        ram = edit.offset + EXE_LOAD_BIAS
        if edit.file == EXE_NAME and edit.end + EXE_LOAD_BIAS > OVERLAY_LOAD_ADDRESS:
            raise BuildRefused(
                f"{edit.reason}: 0x{ram:08X} is in the overlay region, which every overlay "
                f"load rewrites from 0x{OVERLAY_LOAD_ADDRESS:08X}; a resident patch belongs "
                f"below it (research/text-renderer.md § 6)"
            )


def apply_sector_edit(
    writer: DiscWriter, entries: dict[str, DirEntry], edit: SectorEdit, ledger: Ledger
) -> None:
    """Write whole sectors by LBA, converting Form 2 filler as it goes.

    A relocation writes on both sides of `BOKU.BIN`'s extent: the sectors a member vacates
    are inside it, and its new home is inside it too when it was given a run another moving
    member vacated, or in the arena — which belongs to no file — when it was not
    (`boku.relocate.FreeSpace`). The manifest names the file a sector really belongs to, so
    a diff of the built image can be checked against it row by row (`boku trial`).
    """
    writes = writer.write_data_sectors(edit.lba, edit.new)
    name, origin = _owning_file(entries, edit.lba)
    ledger.add(writes, name, origin)


def _owning_file(entries: Mapping[str, DirEntry], lba: int) -> tuple[str, int]:
    """`(file name, that file's first LBA)` for `lba`, or `ARENA_FILE` and `lba` itself.

    `Ledger.add` reports each sector's offset from the second value, so an arena sector's
    is measured from the start of the run being written rather than from a file it is not
    in.
    """
    for name, entry in entries.items():
        if entry.lba <= lba < entry.lba + (entry.size + FORM1_DATA_SIZE - 1) // FORM1_DATA_SIZE:
            return name, entry.lba
    return ARENA_FILE, lba


def write_image(
    source: Path,
    out_dir: Path,
    edits: Sequence[ByteEdit],
    *,
    manifest: Callable[[WrittenImage], str],
    what: str = "build",
    suffix: str = "building",
    refused: type[Exception] = BuildRefused,
    sectors: Sequence[SectorEdit] = (),
) -> WrittenImage:
    """Copy `source` to `out_dir/image.img` and apply `edits` to the copy, in place.

    With no edits the copy is byte-identical to its source, which is `PIPE-05`'s round
    trip: `DiscWriter` does not write a sector whose bytes do not change, so an unchanged
    run leaves the image exactly as it found it.
    """
    source = Path(source)
    out_dir = Path(out_dir).resolve()
    entries = check_before_writing(
        source, out_dir, edits, what=what, refused=refused, sectors=sectors
    )
    with staged(out_dir, suffix=suffix) as stage:
        image = stage / IMAGE_NAME
        shutil.copyfile(source, image)
        (stage / CUE_NAME).write_text(CUE_TEXT, encoding="ascii")
        ledger = Ledger()
        with DiscWriter(image) as writer:
            verify_edits(writer, entries, edits, refused)
            verify_sectors(writer, sectors, refused)
            for edit in edits:
                apply_edit(writer, entries, edit, ledger)
            for sector_edit in sectors:
                apply_sector_edit(writer, entries, sector_edit, ledger)
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
    sectors: Sequence[SectorEdit] = (),
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
        verify_sectors(reader, sectors, refused)
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


# --- the renderer patch, read as an edit set -----------------------------------------------------

VWF_EDITS_FORMAT = 1
"""The `edits.json` shape `tools/vwf/build_prototype.py --edits-only` writes."""


@dataclass(frozen=True)
class EditSet:
    """A renderer patch read from disk: its byte edits and the font it was built with.

    The font build (`tools/vwf/`) and the image build (this package) share exactly one
    file. It carries the *bytes* of the patch — the executable's words and free-space
    table, the rebuilt overlays, the rebuilt font sheet — and the character -> cell map
    the same build derived them from, so an image cannot be written with one build's
    executable and another build's widths.
    """

    edits: tuple[ByteEdit, ...]
    document: dict
    sectors: tuple[SectorEdit, ...] = ()
    """Whole sectors written by LBA -- the movie-subtitle block, which belongs to no file
    (`tools/vwf/build_prototype.py` `MOVIE_BLOCK_NAME`). Only ever inside
    `MOVIE_BLOCK_RESERVE`, over the filler the retail disc has there."""

    @property
    def encoder(self) -> CellMapEncoder:
        """The font these edits install, ready to measure English in."""
        return CellMapEncoder.from_document(self.document, "the edit set")

    @property
    def array_regions(self) -> tuple[Region, ...]:
        """Where grown arrays may move with this renderer installed: `DEAD_REGIONS`, the
        PC-host module's data (dead only because this patch clears `g_pc_host`), and the
        island's tail from `vwf_free` to `island_end`, both recorded in `gap` by the build
        that assembled the island (research/text-renderer.md § 6). An edit set without
        the island adds nothing."""
        gap = self.document.get("gap")
        if not isinstance(gap, dict) or "island_end" not in gap:
            return DEAD_REGIONS
        free = int(gap["symbols"]["vwf_advance"], 16) + int(gap["bytes"])
        end = int(gap["island_end"], 16)
        if free > end:
            raise BuildRefused(f"the edit set's gap ends at 0x{free:08X}, past its island's end")
        return (*DEAD_REGIONS, PC_HOST_DATA, Region(free, end, "the renderer island's tail"))

    @property
    def label_routines(self) -> dict[str, int]:
        """The routines this renderer assembled for the date labels (`asm/labels.asm`) and
        the banners (`asm/banners.asm`), by symbol, read out of the island's record; empty
        for an edit set without them."""
        gap = self.document.get("gap")
        symbols = gap.get("symbols", {}) if isinstance(gap, dict) else {}
        return {
            symbol: int(symbols[symbol], 16)
            for symbol in (
                *(label.routine for label in DATE_LABELS.values()),
                *(banner.routine for banner in BANNERS.values()),
            )
            if symbol in symbols
        }

    @property
    def select_row(self) -> BoxSpec:
        """The select row the renderer in these edits draws (`boku.layout.select_row_of`)."""
        return select_row_of(self.document)

    @property
    def work_area_end(self) -> int:
        """The map work area the patched engine tests against (`asm/arena.asm`).

        A map pack's children 0-5 must fit below it, and the reinserter must measure
        against the engine the image will run, not the retail one: an edit set that
        raised the constant and a build that still refused at `0x6400` would leave
        `M_H06001`'s lines in Japanese for a limit that no longer exists. An edit set
        that says nothing installs the retail engine.
        """
        value = self.document.get("map_work_area_end", MAP_WORK_AREA_END)
        if not isinstance(value, int) or value < MAP_WORK_AREA_END:
            raise BuildRefused(
                f"the edit set's map_work_area_end is {value!r}; the engine's work area "
                f"is {MAP_WORK_AREA_END:#x} or a patch that raised it"
            )
        return value

    @property
    def voice_subtitles(self) -> bool:
        """Whether the executable carries `asm/voice.asm`, without which nothing draws a
        `(voice only)` row's English (`tools/vwf/build_prototype.py` records it)."""
        return self.document.get("voice_subtitles") is True


def load_edit_set(path: Path) -> EditSet:
    """Read an `edits.json`, refusing anything this build could not apply safely.

    Every entry becomes a `ByteEdit`, so the `old` bytes are verified against the image
    before a sector is written exactly as a reinserted line's are — there is no second
    trust path for a patch that happens to come from a file.
    """
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BuildRefused(f"{path}: {error}") from error
    if not isinstance(document, dict) or document.get("format") != VWF_EDITS_FORMAT:
        raise BuildRefused(
            f"{path} is not a format {VWF_EDITS_FORMAT} edit set; "
            f"`uv run python tools/vwf/build_prototype.py --edits-only` writes one"
        )
    entries = document.get("edits")
    if not isinstance(entries, list) or not entries:
        raise BuildRefused(f"{path} carries no `edits`; an empty patch is not a renderer")
    edits: list[ByteEdit] = []
    for number, entry in enumerate(entries, start=1):
        where = f"{path.name} edit {number}"
        if not isinstance(entry, dict) or {"file", "offset", "old", "new"} - set(entry):
            raise BuildRefused(f"{where} is not a (file, offset, old, new) record")
        if entry["file"] not in (EXE_NAME, ARCHIVE_NAME):
            raise BuildRefused(
                f"{where} writes {entry['file']!r}; a patch may only write "
                f"{EXE_NAME} and {ARCHIVE_NAME}"
            )
        try:
            old, new = bytes.fromhex(entry["old"]), bytes.fromhex(entry["new"])
            offset = int(entry["offset"])
        except (TypeError, ValueError) as error:
            raise BuildRefused(f"{where}: {error}") from error
        if offset < 0:
            raise BuildRefused(f"{where}: offset {offset} is negative")
        if len(old) != len(new):
            raise BuildRefused(
                f"{where}: {len(old)} bytes replaced by {len(new)}; an edit never changes "
                f"a file's length (PIPE-04 keeps every LBA)"
            )
        if not old:
            # An empty edit writes nothing and is invisible to every range check that
            # follows -- `check_disjoint` and `check_no_sector_clash` both measure
            # `offset..end - 1`, which is empty here. It can only be a malformed file.
            raise BuildRefused(f"{where} is zero bytes long; an edit writes something")
        edits.append(
            ByteEdit(
                file=entry["file"],
                offset=offset,
                old=old,
                new=new,
                reason=str(entry.get("reason", where)),
            )
        )
    edits.sort(key=lambda edit: (edit.file, edit.offset))
    check_disjoint(edits)
    edit_set = EditSet(edits=tuple(edits), document=document, sectors=_sector_edits(path, document))
    try:
        # The font's bytes and the widths English is measured with are the two halves of
        # one build, and this file is the only place they are held together. A document
        # carrying edits and no cell map would install a sheet and then be measured in
        # the stock 14-px font; that is refused here, not two calls later in another
        # module's voice.
        _ = edit_set.encoder
    except LayoutError as error:
        raise BuildRefused(f"{path}: {error}") from error
    return edit_set


def _sector_edits(path: Path, document: dict) -> tuple[SectorEdit, ...]:
    """The edit set's `sectors`: each `{lba, new, reason}` a whole number of sectors inside
    `MOVIE_BLOCK_RESERVE` and starting at its first, where the executable reads the block
    (`boku.movie_block.BLOCK_LBA`), expecting filler. Anywhere else by LBA is the arena the
    relocation allocator hands out, or a file's extent -- both written through their own
    gates, never through a file that happens to name an LBA."""
    entries = document.get("sectors", [])
    if not isinstance(entries, list):
        raise BuildRefused(f"{path}: `sectors` is not a list")
    out: list[SectorEdit] = []
    for number, entry in enumerate(entries, start=1):
        where = f"{path.name} sector write {number}"
        if not isinstance(entry, dict) or {"lba", "new"} - set(entry):
            raise BuildRefused(f"{where} is not an (lba, new) record")
        try:
            lba, new = int(entry["lba"]), bytes.fromhex(entry["new"])
            edit = SectorEdit(lba, bytes(len(new)), new, str(entry.get("reason", where)))
        except (TypeError, ValueError, RelocationRefused) as error:
            raise BuildRefused(f"{where}: {error}") from error
        if not MOVIE_BLOCK_RESERVE.contains(Run(edit.lba, edit.sectors)):
            raise BuildRefused(
                f"{where} writes LBA {edit.lba}..{edit.end - 1}, outside the movie block's "
                f"reserve {MOVIE_BLOCK_RESERVE.start}..{MOVIE_BLOCK_RESERVE.end - 1}, the "
                f"only sectors an edit set may write by LBA"
            )
        if edit.lba != MOVIE_BLOCK_RESERVE.start:
            raise BuildRefused(
                f"{where} starts at LBA {edit.lba}; the movie block is read from LBA "
                f"{MOVIE_BLOCK_RESERVE.start}, the reserve's first sector"
            )
        out.append(edit)
    try:
        check_sectors_disjoint(out)
    except RelocationRefused as error:
        raise BuildRefused(f"{path}: {error}") from error
    return tuple(sorted(out, key=lambda edit: edit.lba))


# --- a translation, laid out -------------------------------------------------------------------


@dataclass
class LineResult:
    """What became of one translated line: its words, or why it was left alone."""

    line_id: str
    laid_out: LaidOut | None
    problems: tuple[str, ...]
    unreachable: str | None = None
    """Why nothing is written for it: no retail path draws it (`boku.arrays.UNREACHABLE`)."""

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
    label: bool = True,
    voice_subtitles: bool = False,
    select_row: BoxSpec = SELECT_ROW,
) -> list[LineResult]:
    """Turn every entry of a translation into words, collecting the lints it failed.

    Nothing is shortened and nothing is dropped silently: a line that does not fit comes
    back with its numbers and the caller decides (README § "Who this is for").

    `voice_subtitles` says the executable this build installs carries `asm/voice.asm`;
    without it a `(voice only)` row's English is refused, because nothing would draw it.
    """
    selects = SelectTables(archive)
    labels: dict[str, CodeLabel] = {}  # read on the first code label, not for every build
    table = GlyphTable.load() if label else None
    out: list[LineResult] = []
    for entry in translation:
        if (why := unreachable(entry.line_id)) is not None:
            out.append(LineResult(entry.line_id, None, (), unreachable=why))
            continue
        if entry.voice_only:
            out.append(_lay_out_voice_only(archive, walk, entry, encoder, box, voice_subtitles))
            continue
        if CODE_LABEL_MARK in entry.line_id and not labels:
            labels = {label.line_id: label for label in read_code_labels(archive)}
        if entry.line_id in DATE_LABELS:
            laid = lay_out_date_label(entry.line_id, " ".join(entry.pages), encoder)
            out.append(LineResult(entry.line_id, laid, laid.problems))
            continue
        if entry.line_id in labels:
            laid = lay_out_code_label(
                entry.line_id, labels[entry.line_id].runs, " ".join(entry.pages), encoder
            )
            out.append(LineResult(entry.line_id, laid, laid.problems))
            continue
        if entry.line_id == SAVE_TITLE_LINE_ID:
            laid = lay_out_save_title(entry.line_id, " ".join(entry.pages))
            out.append(LineResult(entry.line_id, laid, laid.problems))
            continue
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
        if banner_of(entry.line_id) is not None:
            text = " ".join(entry.pages)
            laid = lay_out_banner(entry.line_id, text, encoder, box_spec_for(entry.line_id))
            out.append(LineResult(entry.line_id, laid, laid.problems))
            continue
        kind = sites[0].kind.split("+")[0]
        if kind.startswith("SEL"):
            select_type, variant = (int(part) for part in kind[3:].split("."))
            shape = selects.shape(select_type, variant)
            # A box that opens with a question spends its first lines on it, and the
            # committed row lists the question first; the provisional loader has no field
            # for that, so the split is made here with the lint's own rule rather than
            # with a second reading of the convention.
            prompts, options = entry.prompts, entry.options
            if not prompts:
                prompts, options = select_fields(entry, shape[1])
            laid = lay_out_select(
                entry.line_id, options, original, shape, encoder, select_row, prompts
            )
        elif kind == "MSG":
            # The marks follow the original and the label is the translation's speaker
            # field: `Uncle「...」` where the Japanese had `おじ「...」`, bare `「...」`
            # where it had that (a chorus, an examine line), `『...』` for narration. A
            # blank speaker on a labelled line draws the bare mark, which is what the
            # lint charges for it, so the two keep reporting the same line.
            opening = closing = ""
            problems: tuple[str, ...] = ()
            if table is not None:
                marks = original_marks(original, table)
                name, unknown = speaker_label(entry.speaker) if marks.labelled else ("", [])
                opening, closing = name + marks.opening, marks.closing
                problems = tuple(
                    f"{entry.line_id}: speaker {who!r} is not a label of "
                    f"translation/style-guide.md § 9 and would be drawn as typed"
                    for who in unknown
                )
                if marks.problem:
                    problems += (f"{entry.line_id}: {marks.problem}",)
            laid = lay_out_message(
                entry.line_id,
                entry.pages,
                original,
                encoder,
                box,
                indent_continuations=indent_continuations,
                opening=opening,
                closing=closing,
            )
            if problems:
                laid = replace(laid, problems=laid.problems + problems)
        elif kind == "ARR-S" and entry.is_select:
            # A menu held in a code file, opened by `select_open_ptr`: a select's rows.
            laid = lay_out_array_select(
                entry.line_id,
                entry.options,
                original,
                encoder,
                byte_limit(entry.line_id, sites[0].size),
                select_row,
            )
        elif kind == "ARR-S":
            out.append(
                LineResult(
                    entry.line_id,
                    None,
                    (f"{entry.line_id} is {MENU_IS_SEL}",),
                )
            )
            continue
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
            if entry.line_id == ANSWER_PAIR.line_id:
                panel = box_for(entry.line_id)  # text-boxes.tsv carries it; a test says so
                laid = lay_out_answer_pair(
                    entry.line_id, " ".join(entry.pages), original, encoder, panel.right
                )
                out.append(LineResult(entry.line_id, laid, laid.problems))
                continue
            laid = lay_out_array(
                entry.line_id,
                " ".join(entry.pages),
                original,
                encoder,
                byte_limit(entry.line_id, sites[0].size),
                box_spec_for(entry.line_id),
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


def _lay_out_voice_only(
    archive: Archive,
    walk: Walk,
    entry: TranslationEntry,
    encoder: Encoder,
    box: BoxSpec,
    hooked: bool,
) -> LineResult:
    """A `(voice only)` row's English as a subtitle for its clip (`VO-02`)."""

    def refused(why: str) -> LineResult:
        where = f" ({entry.origin})" if entry.origin else ""
        return LineResult(entry.line_id, None, (f"{entry.line_id}{where}: {why}",))

    if not hooked:
        return refused(
            "a subtitle for a voice-only clip is drawn only by asm/voice.asm, and this build "
            "installs no executable patch at the XA handler (build with --vwf)"
        )
    if entry.line_id in walk.by_line:
        return refused(
            "is listed '(voice only)' but has text on the disc; give it its speaker instead"
        )
    slots = walk.voice_only.get(entry.line_id)
    if not slots:
        return refused("no voice-only entry (an XA clip with no text) has this id")
    keys = {archive.boku[s.absolute : s.absolute + VOICE_KEY_SIZE] for s in slots}
    if len(keys) != 1:
        return refused(f"its {len(slots)} copies carry {len(keys)} different voice keys")
    laid = lay_out_subtitle(entry.line_id, entry.pages, clip_ticks(keys.pop()), encoder, box)
    return LineResult(entry.line_id, laid, laid.problems)


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
    sector_patches: tuple[SectorEdit, ...] = ()
    arrays: ArrayPlan | None = None
    """The code-file arrays this build moved whole (`boku.array_relocate`)."""

    @property
    def refused_lines(self) -> list[LineResult]:
        return [line for line in self.lines if not line.written and not line.unreachable]

    @property
    def unreachable_lines(self) -> list[LineResult]:
        return [line for line in self.lines if line.unreachable]

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
    sector_patches: Sequence[SectorEdit] = (),
    in_place: bool = False,
    indent_continuations: bool = False,
    label: bool = True,
    skip_unfitted: bool = False,
    dry_run: bool = False,
    name: str = DEFAULT_BUILD_NAME,
    work_area_end: int = MAP_WORK_AREA_END,
    voice_subtitles: bool = False,
    select_row: BoxSpec = SELECT_ROW,
    array_regions: Sequence[Region] = DEAD_REGIONS,
    label_routines: Mapping[str, int] | None = None,
) -> BuildResult:
    """Read an import and a translation, and write a patched image (`PIPE-04`).

    `skip_unfitted` leaves a line that fails a lint in its original Japanese and reports
    it, which is what a work-in-progress translation needs; without it one overflowing
    line refuses the whole build. Either way the English is never shortened.

    `dry_run` does everything up to the copy and writes nothing — the lint report.

    `work_area_end` is the map work area of the engine the image will run
    (`EditSet.work_area_end`); a build with no renderer patch measures against retail.
    `sector_patches` are an edit set's whole-sector writes (`EditSet.sectors`), applied
    beside the relocation's and refused if any LBA is written twice.
    """
    box = box or DIALOGUE_BAND
    encoder = encoder or StockEncoder.load()
    lines: list[LineResult] = []
    the_plan: Plan | None = None
    moved: ArrayPlan | None = None
    edits = list(binary_patches)
    archive: Archive | None = None

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
            label=label,
            voice_subtitles=voice_subtitles,
            select_row=select_row,
        )
        problems = [p for line in lines for p in line.problems]
        if problems and not skip_unfitted:
            raise BuildRefused(
                f"{len(problems)} translation problem(s), first: {problems[0]}. Nothing is "
                f"cut to fit (README); pass --skip-unfitted to build the lines that do fit "
                f"and leave the rest in Japanese, or give the text more room."
            )
        words = {line.line_id: line.laid_out.words for line in lines if line.written}
        labels = {label.line_id for label in read_code_labels(archive)}  # code_label_patches'
        moved, refused = move_arrays(archive, words, array_regions, skip_unfitted, label_routines)
        binary_patches = [*binary_patches, *moved.edits]
        the_plan, still = _plan_what_fits(
            archive,
            walk,
            {k: v for k, v in words.items() if k not in moved.lines and k not in labels},
            in_place,
            skip_unfitted,
            work_area_end,
            binary_patches,
        )
        refused |= still
        carried = set(the_plan.carried)  # already inside a rebuilt member (reinsert.plan)
        binary_patches = [p for p in binary_patches if p not in carried]
        edits = list(binary_patches)
        lines = [
            replace(line, problems=line.problems + refused.get(line.line_id, ())) for line in lines
        ]
        answers = answer_pair_patches(archive, lines)
        labelled = code_label_patches(archive, lines)
        binary_patches = [*binary_patches, *answers, *labelled]
        edits += [*answers, *labelled, *the_plan.edits]

    edits.sort(key=lambda e: (e.file, e.offset))
    # `plan` checks its own edits are disjoint; the caller's binary patches (less the ones
    # it carried) were not in that set.
    check_disjoint(edits)
    check_resident(edits)
    sectors = [*(the_plan.sectors if the_plan else ()), *sector_patches]
    check_sectors_disjoint(sectors)
    if archive is not None:
        check_no_sector_clash(binary_patches, sectors, archive)
    result = BuildResult(
        written=None,
        plan=the_plan,
        lines=lines,
        source_problems=source_problems,
        encoder=getattr(encoder, "name", type(encoder).__name__),
        box=box,
        translation=getattr(translation, "name", "none") if translation else "none",
        binary_patches=tuple(binary_patches),
        sector_patches=tuple(sector_patches),
        arrays=moved,
    )
    if dry_run:
        check_before_writing(source, out_dir, edits, what=name, sectors=sectors)
        return result
    result.written = write_image(
        source,
        out_dir,
        edits,
        manifest=lambda written: manifest_json(written, result, name),
        what=name,
        sectors=sectors,
    )
    return result


def code_label_patches(archive: Archive, lines: Sequence[LineResult]) -> list[ByteEdit]:
    """The immediates of every written code label (`boku.code_text`), each expecting the
    retail instruction there."""
    written = {line.line_id: line.laid_out for line in lines if line.written}
    return [
        edit
        for label in read_code_labels(archive)
        if label.line_id in written and label.line_id not in DATE_LABELS
        for edit in code_label_edits(archive, label, written[label.line_id].words)
    ]


def answer_pair_patches(archive: Archive, lines: Sequence[LineResult]) -> list[ByteEdit]:
    """The drawer's two constants for a written `Yes | No` row (`boku.layout.ANSWER_PAIR`):
    edits in `BOKU.BIN` over the overlay's own words, each expecting the retail word there.
    Call it with the lines the plan kept, so a refused row leaves the stock split behind."""
    laid = next(
        (line.laid_out for line in lines if line.line_id == ANSWER_PAIR.line_id and line.written),
        None,
    )
    if laid is None or not laid.pages:  # words handed in already encoded keep the stock row
        return []
    stock = {
        ANSWER_PAIR.split_ram: ANSWER_PAIR.stock_split,
        ANSWER_PAIR.count_ram: ANSWER_PAIR.stock_count,
    }
    return [
        ByteEdit(
            ARCHIVE_NAME,
            archive.overlay_offset(ANSWER_PAIR.member, ram),
            stock[ram].to_bytes(4, "little"),
            word.to_bytes(4, "little"),
            f"{ANSWER_PAIR.line_id}: the answers' drawer word at 0x{ram:08X}",
        )
        for ram, word in answer_pair_code(laid).items()
    ]


def move_arrays(
    archive: Archive,
    words: dict[str, tuple[int, ...]],
    regions: Sequence[Region],
    skip_unfitted: bool,
    routines: Mapping[str, int] | None = None,
) -> tuple[ArrayPlan, dict[str, tuple[str, ...]]]:
    """Move the grown arrays (`boku.array_relocate`), popping from `words` what cannot move.

    With `skip_unfitted`, an array that does not fit leaves the items that grew in
    Japanese -- its other items fit their own bytes and go in place -- and the rest are
    placed again, so every refusal is found, not only the first. The lint runs this too.
    """
    refused: dict[str, tuple[str, ...]] = {}
    memo: list[Scanned] = []

    def scanned() -> Scanned:
        if not memo:
            memo.append(scans(archive))
        return memo[0]

    while True:
        try:
            return plan_arrays(archive, words, regions, scanned, routines), refused
        except ArrayRoomRefused as error:
            popped = [line for line in error.lines if words.pop(line, None) is not None]
            if not skip_unfitted or not popped:
                raise
            for line in popped:
                refused[line] = (str(error),)


def _plan_what_fits(
    archive: Archive,
    walk: Walk,
    words: dict[str, tuple[int, ...]],
    in_place: bool,
    skip_unfitted: bool,
    work_area_end: int = MAP_WORK_AREA_END,
    carry: Sequence[ByteEdit] = (),
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
            return (
                plan(
                    archive,
                    walk,
                    words,
                    in_place=in_place,
                    work_area_end=work_area_end,
                    carry=carry,
                ),
                refused,
            )
        except ReinsertRefused as error:
            if not skip_unfitted or not error.lines:
                raise
            for line_id in error.lines:
                words.pop(line_id, None)
                refused[line_id] = (str(error),)


def _patch_json(patch: ByteEdit) -> dict:
    return {
        "file": patch.file,
        "offset": f"0x{patch.offset:x}",
        "old": patch.old.hex(" "),
        "new": patch.new.hex(" "),
        "meaning": patch.reason,
    }


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
        "lines_unreachable": sorted(line.line_id for line in result.unreachable_lines),
        "members_rebuilt": sorted(result.plan.members_rebuilt) if result.plan else [],
        "member_growth": dict(sorted(result.plan.growth.items())) if result.plan else {},
        "relocations": [
            {
                "member": placement.member,
                "from_lba": placement.old_lba,
                "to_lba": placement.lba,
                "sectors": placement.sectors,
                "was_sectors": placement.old_sectors,
                "size": placement.size,
            }
            for placement in sorted(
                result.plan.relocations if result.plan else (), key=lambda p: p.member
            )
        ],
        "arrays_moved": [
            {"array": m.prefix, "from": f"0x{m.old:08X}", "to": f"0x{m.new:08X}", "bytes": m.size}
            for m in (result.arrays.moved if result.arrays else ())
        ],
        "rebased_containers": (
            {str(k): v for k, v in sorted(result.plan.layout.bases.items())} if result.plan else {}
        ),
        "binary_patches": [_patch_json(patch) for patch in result.binary_patches],
        # Offsets are the member as stored; the bytes are inside its rebuild.
        "carried_patches": [
            _patch_json(patch) for patch in (result.plan.carried if result.plan else ())
        ],
        "sector_patches": [
            {
                "lba": patch.lba,
                "sectors": patch.sectors,
                "sha1": hashlib.sha1(patch.new).hexdigest(),
                "meaning": patch.reason,
            }
            for patch in result.sector_patches
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
        + (
            f", {len(result.unreachable_lines)} left retail (drawn by no retail path)"
            if result.unreachable_lines
            else ""
        )
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
        for placement in sorted(result.plan.relocations, key=lambda p: p.member):
            out.append(
                f"    {placement.member}: LBA {placement.old_lba} -> {placement.lba}, "
                f"{placement.old_sectors} -> {placement.sectors} sectors"
            )
        for index, lba in sorted(result.plan.layout.bases.items()):
            out.append(f"    g_cd_dir[{index}] rebased to LBA {lba}")
        if result.plan.relocations:
            out.append(
                f"    arena: {result.plan.layout.free_after} of "
                f"{result.plan.layout.free_before} sectors left"
            )
    if result.arrays and result.arrays.moved:
        for m in result.arrays.moved:
            out.append(f"    {m.prefix}: moved to 0x{m.new:08X}, {m.size} bytes")
        out.append(f"    array room: {result.arrays.free_left} bytes left")
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
    vwf: Path | None = None,
    label: bool = True,
    textures: Path | None = None,
) -> int:
    """`boku build`. Every refusal reaches the contributor as one sentence.

    `textures` is a directory of texture strings (`translation/textures/`); each family is
    typeset into its image from this import and applied as verified byte edits
    (`boku.texture_text`).

    `vwf` is a `TXT-05` edit set. It brings both halves of that build — the executable,
    overlay and font-sheet bytes, and the character map those bytes were derived from —
    so `--cells` is only needed to measure in a *different* font from the one being
    installed, which is a mistake more often than an intention.
    """
    out_dir = Path(out_dir) if out_dir else BUILD_ROOT / name
    try:
        translation = (
            SampleScenes.from_directory(Path(translation_dir)) if translation_dir else None
        )
        edit_set = load_edit_set(Path(vwf)) if vwf else None
        if edit_set is not None:
            binary_patches = [*binary_patches, *edit_set.edits]
        installed = edit_set.encoder if edit_set is not None else None
        if textures is not None:
            typeset = build_texture_edits(Archive(disc_dir), Path(textures))
            binary_patches = [*binary_patches, *typeset.edits]
            print(
                f"boku build: textures {', '.join(typeset.families) or 'none'} typeset from "
                f"{textures} ({len(typeset.edits)} byte edits)"
            )
        if cell_map:
            chosen = CellMapEncoder.from_json(Path(cell_map))
            if installed is not None and chosen.cells != installed.cells:
                # Measuring in one font and drawing in another is invisible until it is on
                # screen: the lines wrap where the measured font says and the pen steps
                # where the installed one does. It is a legitimate experiment, so it is
                # said out loud rather than refused.
                print(
                    f"boku build: measuring in {cell_map} but installing the font in "
                    f"{vwf}; the two cell maps differ, so wrapping will not match the "
                    f"pen. Drop --cells to measure in the font being installed."
                )
            encoder: Encoder = chosen
        else:
            encoder = installed or StockEncoder.load()
        result = build(
            source=Path(source) if source else DEFAULT_IMAGE,
            out_dir=out_dir,
            disc_dir=disc_dir,
            translation=translation,
            encoder=encoder,
            binary_patches=binary_patches,
            sector_patches=edit_set.sectors if edit_set is not None else (),
            label=label,
            skip_unfitted=skip_unfitted,
            dry_run=dry_run,
            name=name,
            work_area_end=(edit_set.work_area_end if edit_set is not None else MAP_WORK_AREA_END),
            voice_subtitles=edit_set is not None and edit_set.voice_subtitles,
            select_row=(edit_set.select_row if edit_set is not None else SELECT_ROW),
            array_regions=(edit_set.array_regions if edit_set is not None else DEAD_REGIONS),
            label_routines=(edit_set.label_routines if edit_set is not None else None),
        )
    except (
        ArchiveError,
        ArrayError,
        ArrayRoomRefused,
        BuildRefused,
        DiscError,
        EventError,
        LayoutError,
        ReinsertRefused,
        RelocationRefused,
        SiteError,
        StagingRefused,
        TextError,
        TextureError,
        TextureTextError,
        TimError,
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
    "EditSet",
    "Ledger",
    "LineResult",
    "ReinsertRefused",
    "SectorRecord",
    "WrittenImage",
    "apply_edit",
    "build",
    "check_no_sector_clash",
    "check_resident",
    "file_entries",
    "format_summary",
    "lay_out",
    "load_edit_set",
    "verify_edits",
    "verify_written_sectors",
    "write_image",
]
