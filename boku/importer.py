"""The import step: a contributor's own dump in, `disc/` out.

Nothing in this repo works without it and nothing it writes is ever committed
(TECHNICAL § "The import step", CLAUDE.md § "This repo is public...").

What it produces under `--out` (default `disc/`)::

    image.img      the raw 2352-byte-sector image, verified byte for byte
    image.cue      a one-track cue sheet for emulators, generated here
    manifest.json  every ISO 9660 entry: path, LBA, size, XA attributes, form, sha1
    files/         every cooked file (on this disc: SCPS_100.88, SYSTEM.CNF, BOKU.BIN)

The `__STR` entries are recorded in the manifest and not extracted; `_is_cooked_file`
is the one home for that decision and what was measured behind it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from boku import staging
from boku.chd import ChdError, extract_cd
from boku.disc import RAW_SECTOR_SIZE, DirEntry, DiscError, DiscImage

# The dump this project is built from. research/disc-recon.md § "The dump" is the one home
# for these values and where they came from; they are here once, as constants, so the tool
# can refuse anything else.
IMAGE_SIZE = 658_959_840
IMAGE_SHA1 = "5959bf7d9835d0a60aeb0143e2d0fc564bfea9fa"

SOURCE_ENV_VAR = "BOKU_DISC"
DEFAULT_OUT_DIR = Path("disc")
IMAGE_NAME = "image.img"
CUE_NAME = "image.cue"
MANIFEST_NAME = "manifest.json"
FILES_DIR = "files"
MANIFEST_FORMAT = 1

CUE_TEXT = f'FILE "{IMAGE_NAME}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'

_HASH_CHUNK = 4 * 1024 * 1024


class ImportRefused(Exception):
    """The import cannot proceed, for a reason the message states in full."""


def _note(message: str) -> None:
    print(message, flush=True)


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_source(argument: str | None) -> Path:
    """The dump to import: the argument, else `$BOKU_DISC`. No default path lives in this repo."""
    raw = argument or os.environ.get(SOURCE_ENV_VAR)
    if not raw:
        raise ImportRefused(
            "no source dump given: pass the path to your own .chd, .cue or .bin/.img, "
            f"or set {SOURCE_ENV_VAR}. This repo ships none of the game (TECHNICAL principle 2)."
        )
    source = Path(raw).expanduser()
    if not source.exists():
        raise ImportRefused(f"source dump does not exist: {source}")
    if not source.is_file():
        raise ImportRefused(f"source dump is not a file: {source}")
    return source


def image_from_cue(cue: Path) -> Path:
    """The single MODE2/2352 binary a cue sheet points at, beside the cue."""
    text = cue.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines()]
    files = [
        line.split('"')[1] for line in lines if line.upper().startswith("FILE ") and '"' in line
    ]
    tracks = [line for line in lines if line.upper().startswith("TRACK ")]
    if len(files) != 1:
        raise ImportRefused(
            f"{cue} lists {len(files)} FILE entries; this disc is a single MODE2/2352 track "
            f"(research/disc-recon.md § 'The dump')"
        )
    if len(tracks) != 1 or "MODE2/2352" not in tracks[0].upper():
        raise ImportRefused(f"{cue} lists tracks {tracks!r}; expected exactly one MODE2/2352 track")
    binary = (cue.parent / files[0]).resolve()
    if not binary.is_file():
        raise ImportRefused(f"{cue} points at {files[0]}, which is not beside it ({binary})")
    return binary


def extract_chd(chd: Path, destination: Path) -> Path:
    """Run `chdman extractcd` to produce a raw image at `destination`. Returns it."""
    _note(f"chdman extractcd: {chd}")
    try:
        return extract_cd(chd, destination)
    except ChdError as error:
        raise ImportRefused(
            f"{error}\nAlternatively point this at an already extracted .cue/.bin or raw image."
        ) from error


def verify_image(path: Path, shown_as: Path | None = None) -> str:
    """Refuse anything that is not the dump this project is built from. Returns the sha1.

    `shown_as` names the file in the messages: during an import `path` is inside a staging
    directory that is deleted before the contributor can read the message, so what they
    need to see is the dump they pointed at.
    """
    named = shown_as if shown_as is not None else path
    size = path.stat().st_size
    if size != IMAGE_SIZE:
        raise ImportRefused(
            f"{named} is {size:,} bytes; the expected dump is {IMAGE_SIZE:,} bytes "
            f"(SCPS-10088, one MODE2/2352 track). This is a different disc, a different "
            f"dump method, or a truncated file."
        )
    actual = sha1_of(path)
    if actual != IMAGE_SHA1:
        raise ImportRefused(
            f"{named} is not the dump this project is built from.\n"
            f"  expected sha1: {IMAGE_SHA1}\n"
            f"  actual sha1:   {actual}\n"
            f"The expected value is the Redump image checksum recorded in "
            f"research/disc-recon.md § 'The dump'. Nothing was written."
        )
    return actual


class DestinationSet:
    """Reserves output paths, refusing two that differ only by case.

    macOS and Windows filesystems are case-insensitive, so two names that differ only
    in case are one file and the second write silently destroys the first. That is why
    the image is `image.img` and not `boku.bin` (research/disc-recon.md § "Trap worth
    remembering"); extracted files go under `files/`, so what this guard actually stops
    is two *disc* entries colliding there -- and it holds the image's, the cue's and the
    manifest's own names, so a later row that writes something beside them cannot
    reintroduce the trap.
    """

    def __init__(self) -> None:
        self._taken: dict[str, str] = {}

    def reserve(self, relative_path: str) -> str:
        key = relative_path.casefold()
        previous = self._taken.get(key)
        if previous is not None:
            raise ImportRefused(
                f"two outputs would collide on a case-insensitive filesystem: "
                f"{relative_path!r} and {previous!r}. Refusing rather than overwriting."
            )
        self._taken[key] = relative_path
        return relative_path


def check_out_dir(
    out_dir: Path,
    *,
    manifest_name: str = MANIFEST_NAME,
    what: str = "import",
    source: Path | None = None,
    doing: str | None = None,
) -> None:
    """`boku.staging.check_out_dir`, raising this module's refusal type.

    The rule itself lives in `boku.staging` with the rest of the build-beside-and-swap
    machinery, because four steps of the pipeline need it and it had grown four copies.
    """
    try:
        staging.check_out_dir(
            out_dir, manifest_name=manifest_name, what=what, source=source, doing=doing
        )
    except staging.StagingRefused as error:
        raise ImportRefused(str(error)) from error


@dataclass(frozen=True)
class ImportResult:
    out_dir: Path
    image_sha1: str
    entry_count: int
    extracted_count: int
    manifest: dict


def _entry_record(entry: DirEntry, image: DiscImage) -> dict:
    """The manifest row for one directory entry, before extraction fills in `extracted`.

    `xa.form` is what the directory record *declares*; `first_sector_form` is what the
    first sector actually is. Both are here because on this disc they differ, and neither
    alone describes a real-time extent -- see `_is_cooked_file` for the measurement.
    """
    xa = entry.xa
    return {
        "path": entry.path,
        "type": "directory" if entry.is_dir else "file",
        "lba": entry.lba,
        "size": entry.size,
        "sectors": entry.sector_count,
        "flags": entry.flags,
        "first_sector_form": image.read_sector(entry.lba).form if entry.size > 0 else None,
        "xa": None
        if xa is None
        else {
            "attributes": f"0x{xa.attributes:04x}",
            "flags": xa.flag_names(),
            "file_number": xa.file_number,
            "form": xa.form,
        },
        "extracted": None,
        "sha1": None,
        "not_extracted": None,
    }


def _is_cooked_file(entry: DirEntry, first_sector_form: int | None) -> tuple[bool, str]:
    """Whether a cooked, 2048-bytes-per-sector extraction of this file is meaningful.

    Returns the decision and, when it is no, the short reason the manifest records.
    Directories are not files; do not ask about them.

    Measured on this disc, which is why the interleaved bit decides and not the form:
    every `__STR` entry's record carries attributes `0x2555` -- interleaved, and
    *neither* form bit. Their extents do not overlap each other; the interleaving is
    internal, one subheader channel per stream, so an `.IKI` file's Form 1 video sectors
    and its Form 2 audio sectors alternate inside its own extent and its first sector is
    Form 1. Extracting one at 2048 bytes a sector would yield video sectors spliced
    together with the audio silently dropped -- neither file, and no error.
    """
    if entry.xa is not None and entry.xa.interleaved:
        return False, (
            "real-time interleaved: this extent mixes streams by subheader channel, so "
            "2048 bytes per sector is not this file's byte stream"
        )
    declared = entry.xa.form if entry.xa is not None else None
    if declared == 2 or (declared is None and first_sector_form == 2):
        return False, "Mode 2 Form 2: XA audio, not a cooked byte stream"
    if declared is None:
        return False, "the directory record declares neither Form 1 nor Form 2"
    return True, ""


def import_disc(
    source: Path,
    out_dir: Path,
    *,
    progress: Callable[[str], None] = _note,
) -> ImportResult:
    """Import `source` into `out_dir`, replacing it only once everything succeeded.

    The image is verified before `out_dir` is touched at all, so a refused import
    leaves no partial output. Everything else is built in a sibling staging directory
    and swapped in at the end -- and the swap deletes whatever was at `out_dir`, so
    `check_out_dir` first insists that it is empty or a previous import.
    """
    # Resolved so that `--out .` names a real directory: `boku.staging` builds the
    # staging and replaced directories from `out_dir.name`, empty for a relative ".".
    out_dir = Path(out_dir).resolve()
    check_out_dir(out_dir)
    try:
        with staging.staged(out_dir, suffix="importing") as stage:
            image_path = stage / IMAGE_NAME
            suffix = source.suffix.lower()
            if suffix == ".chd":
                extract_chd(source, image_path)
            else:
                binary = image_from_cue(source) if suffix == ".cue" else source
                progress(f"copying {binary}")
                shutil.copyfile(binary, image_path)

            progress(f"verifying {source.name} ({image_path.stat().st_size:,} bytes)")
            image_sha1 = verify_image(image_path, shown_as=source)
            progress(f"image verified: sha1 {image_sha1}")

            (stage / CUE_NAME).write_text(CUE_TEXT, encoding="ascii")
            destinations = DestinationSet()
            destinations.reserve(IMAGE_NAME)
            destinations.reserve(CUE_NAME)
            destinations.reserve(MANIFEST_NAME)
            destinations.reserve(FILES_DIR)

            files_root = stage / FILES_DIR
            files_root.mkdir()
            records: list[dict] = []
            extracted_count = 0
            with DiscImage(image_path) as image:
                pvd = image.primary_volume_descriptor()
                for entry in image.walk():
                    record = _entry_record(entry, image)
                    relative = f"{FILES_DIR}{entry.path}"
                    if entry.is_dir:
                        destinations.reserve(relative)
                        (stage / relative).mkdir(parents=True, exist_ok=True)
                    else:
                        cooked, reason = _is_cooked_file(entry, record["first_sector_form"])
                        if cooked:
                            destinations.reserve(relative)
                            record["sha1"] = _extract(image, entry, stage / relative)
                            record["extracted"] = relative
                            extracted_count += 1
                            progress(f"extracted {relative} ({entry.size:,} bytes)")
                        else:
                            record["not_extracted"] = reason
                            headline = reason.split(":")[0]
                            progress(
                                f"recorded only {entry.path} ({entry.size:,} bytes): {headline}"
                            )
                    records.append(record)

            manifest = {
                "format": MANIFEST_FORMAT,
                "source": source.name,
                "image": {
                    "file": IMAGE_NAME,
                    "size": image_path.stat().st_size,
                    "sha1": image_sha1,
                    "sectors": image_path.stat().st_size // RAW_SECTOR_SIZE,
                },
                "volume": {
                    "system_identifier": pvd.system_identifier,
                    "volume_identifier": pvd.volume_identifier,
                    "volume_space_size": pvd.volume_space_size,
                    "logical_block_size": pvd.logical_block_size,
                },
                "entries": records,
            }
            (stage / MANIFEST_NAME).write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    except DiscError as error:
        raise ImportRefused(f"{source}: {error}") from error

    return ImportResult(
        out_dir=out_dir,
        image_sha1=image_sha1,
        entry_count=len(records),
        extracted_count=extracted_count,
        manifest=manifest,
    )


def _extract(image: DiscImage, entry: DirEntry, destination: Path) -> str:
    """Write one Form 1 file out of the image and return its sha1."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1()
    with destination.open("wb") as handle:
        for chunk in image.iter_file(entry.lba, entry.size):
            handle.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def format_summary(result: ImportResult) -> str:
    return (
        f"imported into {result.out_dir}/: {result.entry_count} filesystem entries, "
        f"{result.extracted_count} files extracted under {FILES_DIR}/, "
        f"image {IMAGE_NAME} sha1 {result.image_sha1}"
    )


def main_import(source_argument: str | None, out_dir: Path) -> int:
    """The `boku import` command body. Returns a process exit status."""
    try:
        source = resolve_source(source_argument)
        result = import_disc(source, out_dir)
    except ImportRefused as refusal:
        print(f"boku import: refused: {refusal}", file=sys.stderr)
        return 2
    print(format_summary(result))
    return 0
