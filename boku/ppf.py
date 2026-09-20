"""PPF 3.0 -- write one, read one, apply one, without trusting anybody's applier.

PPF is the format Mode One's patcher takes (`~/Dev/retro-trainer/src/one/patch.rs`) and
the one DuckStation picks up from beside a CHD, so `PIPE-05` ships it alongside the
canonical xdelta. It is a list of *overwrites*: an offset, a length, and the bytes that go
there. That is all. It cannot insert, cannot delete and **cannot change the image's
length** -- which is fine here, because nothing this project emits grows the image
(`PIPE-04`).

The format, from Icarus/Paradox's `PPF3.txt`
--------------------------------------------
```
00-04   "PPF30"
05      encoding method: 0x02 for PPF3.0
06-55   description, 50 bytes
56      imagetype: 0x00 = BIN, 0x01 = GI
57      blockcheck: 0x01 = the 1024-byte validation block follows
58      undo data: 0x01 = every record carries the bytes it replaced
59      dummy
60-1083 the validation block: 1024 bytes taken from the image at 0x9320 (BIN)
1084-   records: offset u64 little-endian, count u8, count bytes [, count undo bytes]
```
A `FILE_ID.DIZ` trailer may follow the records; `read_ppf` understands one and `make_ppf`
never writes one (see `_read_file_id`).

What this module does that stock appliers do not
------------------------------------------------
`applyppf3` prints `"Binblock/Patchvalidation failed. continue ? (y/n): "` and carries on
if you say yes; DuckStation's `ReadV3Patch` contains a literal `// TODO: Blockcheck` and
validates nothing. So the blockcheck is only as good as the applier, and ours refuses.
It is still a weak check by construction -- 1 KiB of the ISO 9660 primary volume
descriptor, which says *which game this is*, not which dump of it, and not whether it has
already been patched. The hash checks in `boku.patchfile` are what actually protect a
contributor; this is the belt to their braces.

Two shapes of patch we refuse to *write*, both because of the reference applier:
* a patch with no records, because `ApplyPPF3Patch`'s `do {...} while(count!=0)` loop
  **hangs**. Traced through the C: on a header-only patch `count` reaches exactly 0, the
  body runs once at EOF, `fread` leaves `anz` at its initialised 0 so `fwrite(..., 0, ...)`
  writes nothing, and `count -= (anz + 9)` then steps to -9, -18, ... The `!= 0` test never
  fires again. Nothing is corrupted; the applier simply never returns.
* a `FILE_ID.DIZ` trailer, because retro-trainer's reader runs to end-of-file and would
  read `@BEGIN_FILE_ID.DIZ` as a record header.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"PPF30"
METHOD_PPF30 = 0x02
DESCRIPTION_OFFSET = 6
DESCRIPTION_SIZE = 50
HEADER_SIZE = 60
BLOCKCHECK_SIZE = 1024
BLOCKCHECK_OFFSET_BIN = 0x9320
BLOCKCHECK_OFFSET_GI = 0x80A0
IMAGETYPE_BIN = 0x00
IMAGETYPE_GI = 0x01
#: `zz` in the spec is one unsigned byte, so this is the most one record can carry.
MAX_RECORD_SIZE = 0xFF
RECORD_HEADER_SIZE = 9  # u64 offset + u8 count

FILE_ID_BEGIN = b"@BEGIN_FILE_ID.DIZ"
FILE_ID_END = b"@END_FILE_ID.DIZ"
FILE_ID_LENGTH_SIZE = 2

DEFAULT_CHUNK_SIZE = 1 << 20


class PpfError(Exception):
    """A patch we will not write, or one we will not trust."""


@dataclass(frozen=True)
class PpfRecord:
    """One overwrite: `data` goes at `offset`. `undo` is what was there, if recorded."""

    offset: int
    data: bytes
    undo: bytes | None = None


@dataclass(frozen=True)
class PpfPatch:
    description: str
    imagetype: int
    blockcheck: bytes | None
    undo: bool
    records: tuple[PpfRecord, ...]
    file_id: str | None

    def touched_ranges(self) -> list[tuple[int, int]]:
        """`(offset, length)` per record, in the order they are applied.

        Records that abut are left separate: what a caller wants to know is which bytes
        of the image this patch claims, and adjacency is a detail of how the writer split
        a run at 255 bytes.
        """
        return [(record.offset, len(record.data)) for record in self.records]


def refuse_output_over_input(source: Path, out_path: Path) -> None:
    """Refuse to write a result on top of the image it was made from.

    Every applier here builds into a temporary file and renames it over `out_path`, so
    naming the source as the output destroys it on the *success* path, in silence. The
    `samefile` check catches the cases a string comparison misses -- a symlink, a hard
    link, `./dump.img` against an absolute path, a case-insensitive filesystem.
    """
    if out_path.exists() and out_path.samefile(source):
        raise PpfError(
            f"the output {out_path} is the image being patched. That would destroy "
            f"{source}, which is a dump this project cannot regenerate. Name a different "
            f"output file."
        )


def blockcheck_offset(imagetype: int) -> int:
    if imagetype == IMAGETYPE_BIN:
        return BLOCKCHECK_OFFSET_BIN
    if imagetype == IMAGETYPE_GI:
        return BLOCKCHECK_OFFSET_GI
    raise PpfError(f"unknown PPF imagetype {imagetype:#04x}; 0x00 is BIN and 0x01 is GI")


# ---------------------------------------------------------------------------
# Writing


def make_ppf(
    original: Path,
    modified: Path,
    description: str,
    *,
    undo: bool = False,
    blockcheck: bool = True,
    imagetype: int = IMAGETYPE_BIN,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> bytes:
    """A PPF3 patch turning `original` into `modified`, as bytes.

    The two images are compared a chunk at a time rather than read whole: this runs
    against a 659 MB disc image. Nothing here reads a clock or a filename, so the same
    two images always produce the same patch, byte for byte -- a release that cannot be
    reproduced cannot be audited.

    `undo` doubles the size of every record to store what it replaced, which lets
    `applyppf3 u` walk a patched image back. Off by default: we ship hashes and a
    contributor keeps their own dump, so the undo data is weight without a job.
    """
    encoded = description.encode("ascii", errors="strict")
    if len(encoded) > DESCRIPTION_SIZE:
        raise PpfError(
            f"a PPF description is {DESCRIPTION_SIZE} bytes; {description!r} is {len(encoded)}"
        )

    original_size = original.stat().st_size
    modified_size = modified.stat().st_size
    if original_size != modified_size:
        raise PpfError(
            f"a PPF overwrites in place, so both images must be the same length: "
            f"{original} is {original_size:,} bytes and {modified} is {modified_size:,}. "
            f"PPF cannot express an image that grew."
        )

    out = bytearray()
    out += MAGIC
    out += bytes([METHOD_PPF30])
    # The reference maker pads the description with spaces, and `applyppf3` prints it
    # straight out, so spaces are what a user sees rather than a row of NULs.
    out += encoded.ljust(DESCRIPTION_SIZE, b" ")
    out += bytes([imagetype, 1 if blockcheck else 0, 1 if undo else 0, 0])

    if blockcheck:
        start = blockcheck_offset(imagetype)
        if original_size < start + BLOCKCHECK_SIZE:
            raise PpfError(
                f"the blockcheck is {BLOCKCHECK_SIZE} bytes at {start:#x} and {original} is "
                f"only {original_size:,} bytes; pass blockcheck=False for an image this small"
            )
        with original.open("rb") as handle:
            handle.seek(start)
            out += handle.read(BLOCKCHECK_SIZE)

    records = 0
    with original.open("rb") as old, modified.open("rb") as new:
        for offset, data, replaced in _difference_runs(old, new, original_size, chunk_size):
            for piece in range(0, len(data), MAX_RECORD_SIZE):
                chunk = data[piece : piece + MAX_RECORD_SIZE]
                out += (offset + piece).to_bytes(8, "little")
                out += bytes([len(chunk)])
                out += chunk
                if undo:
                    out += replaced[piece : piece + len(chunk)]
                records += 1

    if records == 0:
        raise PpfError(
            f"{original} and {modified} are identical, so there is nothing to patch. "
            f"A PPF with no records is not an empty patch: it hangs `applyppf3` (see this "
            f"module's docstring for the loop that never terminates)."
        )
    return bytes(out)


def _difference_runs(old, new, size: int, chunk_size: int) -> Iterator[tuple[int, bytes, bytes]]:
    """Yield `(offset, new bytes, replaced bytes)` per maximal run of differing bytes.

    Maximal across read boundaries too: a run that straddles two chunks comes out as one
    run, because where the buffer happened to end is not a property of the images.
    """
    position = 0
    start: int | None = None
    data = bytearray()
    replaced = bytearray()

    while position < size:
        a = old.read(chunk_size)
        b = new.read(chunk_size)
        if len(a) != len(b) or not a:
            raise PpfError(
                f"the images stopped agreeing on their length at byte {position:,}; "
                f"something is writing to them while we read"
            )
        # Almost every chunk of a 659 MB image is unchanged, and one `memcmp` settles it;
        # without this, `_differing_spans` slices each equal chunk into 256 block pairs.
        spans = _differing_spans(a, b) if a != b else ()
        for span_start, span_end in spans:
            if start is not None and start + len(data) == position + span_start:
                data += b[span_start:span_end]
                replaced += a[span_start:span_end]
                continue
            if start is not None:
                yield start, bytes(data), bytes(replaced)
            start = position + span_start
            data = bytearray(b[span_start:span_end])
            replaced = bytearray(a[span_start:span_end])
        position += len(a)

    if start is not None:
        yield start, bytes(data), bytes(replaced)


_SPAN_BLOCK = 4096


def _differing_spans(a: bytes, b: bytes) -> Iterator[tuple[int, int]]:
    """Local `[start, end)` spans where `a` and `b` differ, in order.

    Byte-by-byte comparison of a 659 MB image in Python is minutes; comparing 4 KiB
    blocks first is one `memcmp` per block and reduces the byte loop to the blocks that
    actually differ. A run crossing a block boundary comes out as two adjacent spans and
    is rejoined by the caller, which already has to rejoin across chunk boundaries.
    """
    position = 0
    size = len(a)
    while position < size:
        block_end = min(position + _SPAN_BLOCK, size)
        if a[position:block_end] == b[position:block_end]:
            position = block_end
            continue
        index = position
        while index < block_end:
            if a[index] == b[index]:
                index += 1
                continue
            end = index
            while end < block_end and a[end] != b[end]:
                end += 1
            yield index, end
            index = end
        position = block_end


# ---------------------------------------------------------------------------
# Reading


def read_ppf(patch: bytes) -> PpfPatch:
    """Parse a PPF3 patch. Raises `PpfError` on anything it cannot account for."""
    if len(patch) < HEADER_SIZE:
        raise PpfError(f"a PPF3 header is {HEADER_SIZE} bytes; this file is {len(patch)}")
    if patch[:5] != MAGIC or patch[5] != METHOD_PPF30:
        raise PpfError(
            f"not a PPF3 patch: expected the magic {MAGIC.decode()} and method "
            f"{METHOD_PPF30:#04x}, found {patch[:5]!r} and {patch[5]:#04x}"
        )

    description = patch[DESCRIPTION_OFFSET : DESCRIPTION_OFFSET + DESCRIPTION_SIZE]
    imagetype = patch[56]
    has_blockcheck = patch[57] != 0
    undo = patch[58] != 0

    start = HEADER_SIZE
    block: bytes | None = None
    if has_blockcheck:
        start += BLOCKCHECK_SIZE
        if len(patch) < start:
            raise PpfError(
                f"the header says a {BLOCKCHECK_SIZE}-byte blockcheck follows, but the "
                f"patch is only {len(patch)} bytes: truncated"
            )
        block = patch[HEADER_SIZE:start]

    file_id, end = _read_file_id(patch, start)
    records = tuple(_read_records(patch, start, end, undo))
    return PpfPatch(
        description=description.decode("ascii", errors="replace").rstrip(" \0"),
        imagetype=imagetype,
        blockcheck=block,
        undo=undo,
        records=records,
        file_id=file_id,
    )


def _read_file_id(patch: bytes, start: int) -> tuple[str | None, int]:
    """The optional trailer, and the offset where the records stop.

    `applyppf3` finds it by reading the four bytes before the 2-byte length and comparing
    them with `.DIZ` -- the tail of `@END_FILE_ID.DIZ`. That alone would also match a
    record whose data happens to end that way, so we require the `@BEGIN` marker to be
    where the length says it is, and treat anything else as "no trailer".
    """
    tail = FILE_ID_LENGTH_SIZE + len(FILE_ID_END)
    if len(patch) < start + tail:
        return None, len(patch)
    if patch[-tail:-FILE_ID_LENGTH_SIZE] != FILE_ID_END:
        return None, len(patch)

    length = int.from_bytes(patch[-FILE_ID_LENGTH_SIZE:], "little")
    text_start = len(patch) - tail - length
    marker_start = text_start - len(FILE_ID_BEGIN)
    if marker_start < start or patch[marker_start:text_start] != FILE_ID_BEGIN:
        return None, len(patch)
    return patch[text_start : text_start + length].decode("ascii", errors="replace"), marker_start


def _read_records(patch: bytes, start: int, end: int, undo: bool) -> Iterator[PpfRecord]:
    position = start
    while position < end:
        if position + RECORD_HEADER_SIZE > end:
            raise PpfError(
                f"truncated record header at byte {position}: {end - position} bytes left, "
                f"a record header is {RECORD_HEADER_SIZE}"
            )
        offset = int.from_bytes(patch[position : position + 8], "little")
        size = patch[position + 8]
        position += RECORD_HEADER_SIZE
        if size == 0:
            raise PpfError(f"record at byte {position} claims zero bytes, which patches nothing")
        needed = size * 2 if undo else size
        if position + needed > end:
            raise PpfError(
                f"truncated record data at byte {position}: the record claims {needed} "
                f"bytes and {end - position} remain"
            )
        data = patch[position : position + size]
        position += size
        replaced = None
        if undo:
            replaced = patch[position : position + size]
            position += size
        yield PpfRecord(offset=offset, data=data, undo=replaced)


# ---------------------------------------------------------------------------
# Applying


def apply_ppf(
    image_path: Path,
    patch: bytes,
    out_path: Path,
    *,
    verify_blockcheck: bool = True,
) -> PpfPatch:
    """Write `image_path` patched by `patch` to `out_path`, or raise.

    The result is built in a temporary file beside `out_path` and moved into place once
    every record has landed, so an interrupted run leaves no half-patched image wearing
    the right name. The fsync is for the stronger claim: after a normal return the bytes
    are on the disk, not only in the page cache.

    `out_path` may not *be* `image_path`. Opening the original read-only is not enough to
    protect it -- the rename at the end would replace it with the patched image, and a
    contributor's dump is the one file here that cannot be regenerated.

    `verify_blockcheck=False` is for a patch that carries no validation block -- a
    deliberate decision by the caller, never a default, because "nothing to check" and
    "checked and passed" must not look the same.
    """
    refuse_output_over_input(image_path, out_path)
    parsed = read_ppf(patch)
    size = image_path.stat().st_size

    for record in parsed.records:
        if record.offset + len(record.data) > size:
            raise PpfError(
                f"the patch writes {len(record.data)} bytes at {record.offset:#x}, past the "
                f"end of {image_path} ({size:,} bytes). This patch is for a different image."
            )

    if verify_blockcheck:
        if parsed.blockcheck is None:
            raise PpfError(
                "this patch carries no blockcheck, so there is nothing to validate it "
                "against. Pass verify_blockcheck=False to apply it anyway."
            )
        start = blockcheck_offset(parsed.imagetype)
        with image_path.open("rb") as handle:
            handle.seek(start)
            found = handle.read(BLOCKCHECK_SIZE)
        if found != parsed.blockcheck:
            raise PpfError(
                f"blockcheck mismatch: the {BLOCKCHECK_SIZE} bytes at {start:#x} of "
                f"{image_path} are not the ones this patch was built against. This is the "
                f"wrong image (or the wrong game). Refusing -- stock appliers would ask "
                f"and carry on."
            )

    temporary = out_path.parent / f".{out_path.name}.applying.{os.getpid()}"
    try:
        with image_path.open("rb") as source, temporary.open("wb") as destination:
            while block := source.read(DEFAULT_CHUNK_SIZE):
                destination.write(block)
            for record in parsed.records:
                destination.seek(record.offset)
                destination.write(record.data)
            destination.flush()
            os.fsync(destination.fileno())
        temporary.replace(out_path)
    finally:
        temporary.unlink(missing_ok=True)
    return parsed
