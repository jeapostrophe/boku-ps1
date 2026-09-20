"""Read a raw PlayStation CD image: Mode 2 sectors and the ISO 9660 directory tree.

Sector layout, stated once for the whole project
------------------------------------------------
A raw ("2352-byte") sector of a Mode 2 track is::

    offset  size  contents
    0       12    sync pattern: 00 FF*10 00
    12      3     address, BCD minute/second/frame (frame = 1/75 s)
    15      1     mode; 2 for every sector of this disc's only track
    16      8     subheader: file, channel, submode, coding -- written TWICE
    24      N     user data
    24+N    ...   EDC/ECC

Bit 0x20 of the submode byte picks the *form*, and the form picks N:

* **Form 1** -- ``N = 2048`` user bytes, then 4 bytes EDC and 276 bytes of ECC.
  This is the form that carries a filesystem. Everything this module calls a
  "file" is a run of Form 1 sectors.
* **Form 2** -- ``N = 2324`` user bytes then 4 bytes EDC, no ECC: XA audio.

A real-time file mixes the two *within its own extent*, one subheader channel per
stream, so its sectors are not a single cooked byte stream in either form. Reading
one as 2048-byte blocks produces garbage, so this module refuses to.

A logical block address (LBA) is a sector index from the start of the image; the
address field in the header counts from the two-second pregap that precedes LBA 0
and is not part of the image, so ``lba = (minute * 60 + second) * 75 + frame - 150``.

`DiscImage` only reads. `DiscWriter` is the same reader opened read-write, and every
write goes through `boku.edc`: a sector's sync pattern, header and subheader are carried
through untouched and its EDC and ECC are regenerated from the result, because an image
whose EDC/ECC no longer match works in emulators and fails on hardware (`PIPE-04`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from boku import edc

# The layout above, as numbers. They live in `boku.edc`, which is the module everything
# else imports; this file is where what they mean is written down.
from boku.edc import (
    FORM1_DATA_SIZE,
    FORM2_DATA_SIZE,
    HEADER_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_MODE,
    USER_DATA_OFFSET,
)

SYNC_PATTERN = b"\x00" + b"\xff" * 10 + b"\x00"
SUBHEADER_OFFSET = 16
SUBHEADER_SIZE = 8
MSF_LBA_OFFSET = 150
"""The two-second pregap, in sectors. It is not in the image: address 00:02:00 is LBA 0."""

SUBMODE_END_OF_RECORD = 0x01
SUBMODE_VIDEO = 0x02
SUBMODE_AUDIO = 0x04
SUBMODE_DATA = 0x08
SUBMODE_TRIGGER = 0x10
SUBMODE_FORM2 = 0x20
SUBMODE_REAL_TIME = 0x40
SUBMODE_END_OF_FILE = 0x80

FIRST_VOLUME_DESCRIPTOR_LBA = 16
VOLUME_DESCRIPTOR_TYPE_PRIMARY = 1
VOLUME_DESCRIPTOR_TYPE_TERMINATOR = 255
VOLUME_DESCRIPTOR_MAGIC = b"CD001"

DIRECTORY_RECORD_MIN_SIZE = 34
FILE_FLAG_DIRECTORY = 0x02

# CD-XA extends each directory record with this 14-byte structure, recognised by the
# "XA" signature six bytes in.
XA_SIGNATURE = b"XA"
XA_SIGNATURE_OFFSET = 6
XA_RECORD_SIZE = 14
XA_ATTR_OWNER_READ = 0x0001
XA_ATTR_OWNER_EXEC = 0x0004
XA_ATTR_GROUP_READ = 0x0010
XA_ATTR_GROUP_EXEC = 0x0040
XA_ATTR_WORLD_READ = 0x0100
XA_ATTR_WORLD_EXEC = 0x0400
XA_ATTR_FORM1 = 0x0800
XA_ATTR_FORM2 = 0x1000
XA_ATTR_INTERLEAVED = 0x2000
XA_ATTR_CDDA = 0x4000
XA_ATTR_DIRECTORY = 0x8000

_READ_CHUNK_SECTORS = 64
"""Sectors per `read` while streaming a file; purely a syscall-count tradeoff."""


class DiscError(Exception):
    """The image is not the shape this module can read."""


def _bcd(byte: int, what: str) -> int:
    high, low = byte >> 4, byte & 0x0F
    if high > 9 or low > 9:
        raise DiscError(f"{what} is not BCD: 0x{byte:02x}")
    return high * 10 + low


@dataclass(frozen=True)
class Subheader:
    """The 8-byte Mode 2 subheader, as its first 4-byte copy reads."""

    file_number: int
    channel: int
    submode: int
    coding: int

    @classmethod
    def parse(cls, raw: bytes) -> Subheader:
        if len(raw) != SUBHEADER_SIZE:
            raise DiscError(f"subheader is {len(raw)} bytes, expected {SUBHEADER_SIZE}")
        return cls(file_number=raw[0], channel=raw[1], submode=raw[2], coding=raw[3])

    @property
    def form(self) -> int:
        """1 or 2 -- which user-data size this sector carries."""
        return 2 if self.submode & SUBMODE_FORM2 else 1

    @property
    def data_size(self) -> int:
        return FORM2_DATA_SIZE if self.form == 2 else FORM1_DATA_SIZE

    @property
    def is_audio(self) -> bool:
        return bool(self.submode & SUBMODE_AUDIO)


@dataclass(frozen=True)
class Sector:
    """One raw sector, parsed: where it says it is, what it says it holds, and its user data."""

    lba: int
    header_lba: int
    subheader: Subheader
    data: bytes

    @property
    def form(self) -> int:
        return self.subheader.form


def parse_sector(raw: bytes, lba: int) -> Sector:
    """Parse one 2352-byte raw sector. `lba` is where it was read from, for messages."""
    if len(raw) != RAW_SECTOR_SIZE:
        raise DiscError(f"sector {lba}: read {len(raw)} bytes, expected {RAW_SECTOR_SIZE}")
    if raw[:HEADER_OFFSET] != SYNC_PATTERN:
        raise DiscError(
            f"sector {lba}: sync pattern is {raw[:HEADER_OFFSET].hex()}, "
            f"expected {SYNC_PATTERN.hex()} -- is this a raw 2352-byte-sector image?"
        )
    minute = _bcd(raw[HEADER_OFFSET], f"sector {lba} header minute")
    second = _bcd(raw[HEADER_OFFSET + 1], f"sector {lba} header second")
    frame = _bcd(raw[HEADER_OFFSET + 2], f"sector {lba} header frame")
    header_lba = (minute * 60 + second) * 75 + frame - MSF_LBA_OFFSET
    mode = raw[HEADER_OFFSET + 3]
    if mode != SECTOR_MODE:
        raise DiscError(f"sector {lba}: mode {mode}, expected Mode {SECTOR_MODE}")
    subheader = Subheader.parse(raw[SUBHEADER_OFFSET : SUBHEADER_OFFSET + SUBHEADER_SIZE])
    data = raw[USER_DATA_OFFSET : USER_DATA_OFFSET + subheader.data_size]
    return Sector(lba=lba, header_lba=header_lba, subheader=subheader, data=data)


@dataclass(frozen=True)
class XaAttributes:
    """The CD-XA extension of a directory record: who may read it, and in which form."""

    group_id: int
    user_id: int
    attributes: int
    file_number: int

    @classmethod
    def parse(cls, raw: bytes) -> XaAttributes:
        return cls(
            group_id=int.from_bytes(raw[0:2], "big"),
            user_id=int.from_bytes(raw[2:4], "big"),
            attributes=int.from_bytes(raw[4:6], "big"),
            file_number=raw[8],
        )

    @property
    def form(self) -> int | None:
        """1, 2, or None when the record claims neither (or both)."""
        form1 = bool(self.attributes & XA_ATTR_FORM1)
        form2 = bool(self.attributes & XA_ATTR_FORM2)
        if form1 == form2:
            return None
        return 1 if form1 else 2

    @property
    def interleaved(self) -> bool:
        return bool(self.attributes & XA_ATTR_INTERLEAVED)

    @property
    def directory(self) -> bool:
        return bool(self.attributes & XA_ATTR_DIRECTORY)

    def flag_names(self) -> list[str]:
        named = [
            (XA_ATTR_OWNER_READ, "owner_read"),
            (XA_ATTR_OWNER_EXEC, "owner_exec"),
            (XA_ATTR_GROUP_READ, "group_read"),
            (XA_ATTR_GROUP_EXEC, "group_exec"),
            (XA_ATTR_WORLD_READ, "world_read"),
            (XA_ATTR_WORLD_EXEC, "world_exec"),
            (XA_ATTR_FORM1, "form1"),
            (XA_ATTR_FORM2, "form2"),
            (XA_ATTR_INTERLEAVED, "interleaved"),
            (XA_ATTR_CDDA, "cdda"),
            (XA_ATTR_DIRECTORY, "directory"),
        ]
        return [name for bit, name in named if self.attributes & bit]


def _form1_sectors(size: int) -> int:
    """Sectors a `size`-byte extent spans at 2048 bytes of user data per sector."""
    return (size + FORM1_DATA_SIZE - 1) // FORM1_DATA_SIZE


@dataclass(frozen=True)
class DirEntry:
    """One ISO 9660 directory record, with its absolute "/"-separated path.

    `size` is the extent's length in bytes -- for a directory, the size of its
    directory extent (not the record's own byte count, which is its first byte).
    """

    path: str
    name: str
    lba: int
    size: int
    is_dir: bool
    flags: int
    xa: XaAttributes | None

    @property
    def sector_count(self) -> int:
        """Form 1 sectors the extent spans (how many sectors a cooked read would take)."""
        return _form1_sectors(self.size)


@dataclass(frozen=True)
class PrimaryVolumeDescriptor:
    system_identifier: str
    volume_identifier: str
    volume_space_size: int
    logical_block_size: int
    root_lba: int
    root_size: int


def _strip_version(name: str) -> str:
    """`SYSTEM.CNF;1` -> `SYSTEM.CNF`. Only a trailing `;<digits>` is a version."""
    head, sep, version = name.rpartition(";")
    return head if sep and version.isdigit() else name


def _parse_directory_record(record: bytes, prefix: str) -> DirEntry | None:
    """Parse one record into an entry placed under `prefix`; None for the "." and ".." records."""
    if len(record) < DIRECTORY_RECORD_MIN_SIZE:
        raise DiscError(f"directory record is {len(record)} bytes, minimum is 34")
    lba = int.from_bytes(record[2:6], "little")
    size = int.from_bytes(record[10:14], "little")
    flags = record[25]
    name_length = record[32]
    name_end = 33 + name_length
    if name_end > len(record):
        raise DiscError(
            f"directory record claims a {name_length}-byte name, record is {len(record)}"
        )
    raw_name = record[33:name_end]
    system_use = record[name_end + (1 - name_length % 2) :]
    xa = None
    if (
        len(system_use) >= XA_RECORD_SIZE
        and system_use[XA_SIGNATURE_OFFSET : XA_SIGNATURE_OFFSET + 2] == XA_SIGNATURE
    ):
        xa = XaAttributes.parse(system_use[:XA_RECORD_SIZE])
    is_dir = bool(flags & FILE_FLAG_DIRECTORY)
    if name_length == 1 and raw_name in (b"\x00", b"\x01"):
        return None  # "." and ".." -- not entries of their own
    name = _strip_version(raw_name.decode("ascii", errors="replace"))
    if not name or "/" in name or "\x00" in name or name in (".", ".."):
        raise DiscError(f"directory record names {name!r}, which cannot be a path component")
    return DirEntry(
        path=f"{prefix}/{name}",
        name=name,
        lba=lba,
        size=size,
        is_dir=is_dir,
        flags=flags,
        xa=xa,
    )


class DiscImage:
    """A raw CD image opened for reading: sectors, files, and the ISO 9660 tree.

    Use as a context manager, or call `close()`; every read is a positioned read on
    one file handle, so instances are not safe to share between threads.
    """

    _OPEN_MODE = "rb"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        size = self.path.stat().st_size
        if size == 0:
            raise DiscError(f"{self.path} is empty")
        if size % RAW_SECTOR_SIZE:
            raise DiscError(
                f"{self.path} is {size} bytes, not a whole number of {RAW_SECTOR_SIZE}-byte "
                f"sectors ({size % RAW_SECTOR_SIZE} bytes over)"
            )
        self.size = size
        self.sector_count = size // RAW_SECTOR_SIZE
        self._file: BinaryIO | None = None

    def __enter__(self) -> DiscImage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    @property
    def _handle(self) -> BinaryIO:
        if self._file is None:
            self._file = self.path.open(self._OPEN_MODE)
        return self._file

    def read_raw(self, lba: int, count: int = 1) -> bytes:
        """The untouched bytes of `count` sectors: sync, header, subheader, data, EDC/ECC.

        What a checker of EDC/ECC needs and `read_sector` throws away.
        """
        if lba < 0 or count < 0 or lba + count > self.sector_count:
            raise DiscError(
                f"sectors {lba}..{lba + count - 1} fall outside the image, which has "
                f"{self.sector_count} sectors"
            )
        self._handle.seek(lba * RAW_SECTOR_SIZE)
        raw = self._handle.read(count * RAW_SECTOR_SIZE)
        if len(raw) != count * RAW_SECTOR_SIZE:
            raise DiscError(f"image ended while reading sector {lba} (+{count})")
        return raw

    def read_sector(self, lba: int) -> Sector:
        """One parsed sector: subheader plus the user data its form defines."""
        return parse_sector(self.read_raw(lba, 1), lba)

    def iter_sectors(self, lba: int, count: int) -> Iterator[Sector]:
        """Parsed sectors `lba..lba+count-1`, read in chunks."""
        read = 0
        while read < count:
            batch = min(_READ_CHUNK_SECTORS, count - read)
            raw = self.read_raw(lba + read, batch)
            for i in range(batch):
                start = i * RAW_SECTOR_SIZE
                yield parse_sector(raw[start : start + RAW_SECTOR_SIZE], lba + read + i)
            read += batch

    def iter_file(self, lba: int, size: int) -> Iterator[bytes]:
        """Stream `size` bytes of a Form 1 file starting at `lba`, one sector per chunk.

        Raises `DiscError` on the first Form 2 sector: the extent is real-time data whose
        streams are interleaved by channel, so cooked bytes out of it are meaningless
        rather than merely lossy.
        """
        if size < 0:
            raise DiscError(f"file at sector {lba} has negative size {size}")
        remaining = size
        count = _form1_sectors(size)
        for sector in self.iter_sectors(lba, count):
            if sector.form != 1:
                raise DiscError(
                    f"file at sector {lba} ({size} bytes): sector {sector.lba} is Mode 2 Form 2 "
                    f"(submode 0x{sector.subheader.submode:02x}); Form 2 data is not a cooked "
                    f"byte stream and is not extracted"
                )
            chunk = sector.data[:remaining]
            remaining -= len(chunk)
            yield chunk

    def read_file(self, lba: int, size: int) -> bytes:
        """The whole file at `lba` as bytes. See `iter_file` for the Form 2 refusal."""
        return b"".join(self.iter_file(lba, size))

    def read_file_bytes(self, file_lba: int, offset: int, length: int) -> bytes:
        """`length` bytes at `offset` in the Form 1 file at `file_lba`, across sectors.

        The counterpart of `DiscWriter.write_file_bytes`, and the read a caller makes to
        prove it knows what it is about to overwrite. Like the write, it knows nothing
        about ISO 9660, so it cannot tell that a range has run past the file's size.
        """
        if offset < 0 or length < 0:
            raise DiscError(f"file at sector {file_lba}: offset {offset}, length {length}")
        if length == 0:
            return b""
        first = file_lba + offset // FORM1_DATA_SIZE
        last = file_lba + (offset + length - 1) // FORM1_DATA_SIZE
        blocks = []
        for sector in self.iter_sectors(first, last - first + 1):
            if sector.form != 1:
                raise DiscError(
                    f"file at sector {file_lba}: sector {sector.lba} is Mode 2 Form 2 "
                    f"(submode 0x{sector.subheader.submode:02x}) and holds no file bytes"
                )
            blocks.append(sector.data)
        start = offset % FORM1_DATA_SIZE
        return b"".join(blocks)[start : start + length]

    def sha1_file(self, lba: int, size: int) -> str:
        digest = hashlib.sha1()
        for chunk in self.iter_file(lba, size):
            digest.update(chunk)
        return digest.hexdigest()

    def primary_volume_descriptor(self) -> PrimaryVolumeDescriptor:
        """The PVD from the volume descriptor set that starts at LBA 16."""
        lba = FIRST_VOLUME_DESCRIPTOR_LBA
        while lba < self.sector_count:
            data = self.read_sector(lba).data
            if data[1:6] != VOLUME_DESCRIPTOR_MAGIC:
                raise DiscError(
                    f"sector {lba} is not a volume descriptor: magic is {data[1:6]!r}, "
                    f"expected {VOLUME_DESCRIPTOR_MAGIC!r}"
                )
            kind = data[0]
            if kind == VOLUME_DESCRIPTOR_TYPE_PRIMARY:
                return self._parse_pvd(data)
            if kind == VOLUME_DESCRIPTOR_TYPE_TERMINATOR:
                break
            lba += 1
        raise DiscError(
            f"no primary volume descriptor in the set at sector {FIRST_VOLUME_DESCRIPTOR_LBA}"
        )

    @staticmethod
    def _parse_pvd(data: bytes) -> PrimaryVolumeDescriptor:
        logical_block_size = int.from_bytes(data[128:130], "little")
        if logical_block_size != FORM1_DATA_SIZE:
            raise DiscError(
                f"volume's logical block size is {logical_block_size}, expected {FORM1_DATA_SIZE}"
            )
        root = data[156 : 156 + DIRECTORY_RECORD_MIN_SIZE]
        return PrimaryVolumeDescriptor(
            system_identifier=data[8:40].decode("ascii", errors="replace").rstrip(),
            volume_identifier=data[40:72].decode("ascii", errors="replace").rstrip(),
            volume_space_size=int.from_bytes(data[80:84], "little"),
            logical_block_size=logical_block_size,
            root_lba=int.from_bytes(root[2:6], "little"),
            root_size=int.from_bytes(root[10:14], "little"),
        )

    def read_directory(self, lba: int, size: int, prefix: str = "") -> list[DirEntry]:
        """The records of one directory extent, in on-disc order, without "." and "..".

        `prefix` is this directory's own path, which each entry's `path` is placed under;
        the default names the root, so a bare call gives `/SYSTEM.CNF`.

        A directory's extent may span sectors; records never straddle a sector boundary,
        so a zero length byte means "this sector's records are done", not "the directory is".
        """
        entries: list[DirEntry] = []
        sector_count = _form1_sectors(size)
        for sector in self.iter_sectors(lba, sector_count):
            if sector.form != 1:
                raise DiscError(f"directory at sector {lba}: sector {sector.lba} is Form 2")
            block = sector.data
            offset = 0
            while offset < len(block):
                record_length = block[offset]
                if record_length == 0:
                    break
                if offset + record_length > len(block):
                    raise DiscError(
                        f"directory at sector {lba}: a {record_length}-byte record at offset "
                        f"{offset} of sector {sector.lba} runs past the sector"
                    )
                entry = _parse_directory_record(block[offset : offset + record_length], prefix)
                if entry is not None:
                    entries.append(entry)
                offset += record_length
        return entries

    def walk(self) -> Iterator[DirEntry]:
        """Every entry below the root, depth first, each directory before its contents.

        Paths are absolute and "/"-separated (`/__STR/M27.IKI`); the root itself and the
        "." / ".." records are not yielded.
        """
        pvd = self.primary_volume_descriptor()
        yield from self._walk(pvd.root_lba, pvd.root_size, "", set())

    def _walk(self, lba: int, size: int, prefix: str, seen: set[int]) -> Iterator[DirEntry]:
        if lba in seen:
            raise DiscError(f"directory at sector {lba} contains itself")
        seen = seen | {lba}
        for entry in self.read_directory(lba, size, prefix):
            yield entry
            if entry.is_dir:
                yield from self._walk(entry.lba, entry.size, entry.path, seen)


@dataclass(frozen=True)
class SectorWrite:
    """One sector this process changed: what it was, and what it became."""

    lba: int
    old_sha1: str
    new_sha1: str


class DiscWriter(DiscImage):
    """The reader, opened read-write, with user data writable a byte range at a time.

    Everything `DiscImage` does still works, so the same object can walk the filesystem
    it is patching. Only Form 1 user data is writable: Form 2 sectors are interleaved
    real-time streams whose bytes are not addressable as a file (`iter_file`), and the
    trial and the pipeline never have business in one.

    Writes are read-modify-write on whole sectors and a sector whose bytes do not change
    is not written at all, so an unchanged run is byte-identical to its source -- the
    property `PIPE-05`'s round-trip gate rests on.
    """

    _OPEN_MODE = "r+b"

    def _write_raw(self, lba: int, raw: bytes) -> None:
        if len(raw) != RAW_SECTOR_SIZE:
            raise DiscError(f"sector {lba}: {len(raw)} bytes to write, expected {RAW_SECTOR_SIZE}")
        self._handle.seek(lba * RAW_SECTOR_SIZE)
        self._handle.write(raw)

    def flush(self) -> None:
        if self._file is not None:
            self._file.flush()

    def write_sector_data(self, lba: int, data: bytes) -> SectorWrite | None:
        """Replace sector `lba`'s 2048 user bytes, regenerating its EDC and ECC.

        Returns None when the sector's bytes are unchanged; otherwise the record the
        build manifest carries. Raises `DiscError` if the sector is not Form 1.
        """
        old = self.read_raw(lba)
        sector = parse_sector(old, lba)
        if sector.form != 1:
            raise DiscError(
                f"sector {lba} is Mode 2 Form 2 (submode "
                f"0x{sector.subheader.submode:02x}); only Form 1 user data is writable"
            )
        if len(data) != FORM1_DATA_SIZE:
            raise DiscError(
                f"sector {lba}: {len(data)} bytes of user data, Form 1 holds {FORM1_DATA_SIZE}"
            )
        new = edc.set_form1_data(old, data)
        if new == old:
            return None
        self._write_raw(lba, new)
        return SectorWrite(
            lba=lba,
            old_sha1=hashlib.sha1(old).hexdigest(),
            new_sha1=hashlib.sha1(new).hexdigest(),
        )

    def write_file_bytes(
        self, file_lba: int, offset: int, data: bytes, *, file_size: int
    ) -> list[SectorWrite]:
        """Patch `data` over the byte range at `offset` in the Form 1 file at `file_lba`.

        The range may start and end anywhere and may cross any number of sectors; each
        sector it touches is read, spliced and written back with fresh EDC/ECC.

        `file_size` is the extent's recorded length (`DirEntry.size`) and is required,
        because this call has no other way to know where the file ends: without it a
        write that runs one byte past a text site's file silently lands in whatever
        follows it on the disc, which here is another file's first sector. The whole
        range is checked -- in bounds, and every sector of it Form 1 -- **before** the
        first sector is written, so a refusal leaves the image as it was rather than
        half patched.
        """
        if offset < 0:
            raise DiscError(f"file at sector {file_lba}: negative offset {offset}")
        end = offset + len(data)
        if end > file_size:
            raise DiscError(
                f"file at sector {file_lba} is {file_size} bytes; writing {len(data)} "
                f"bytes at offset {offset} would end at {end}, past the file's own "
                f"extent. Nothing was written."
            )
        if not data:
            return []
        first = file_lba + offset // FORM1_DATA_SIZE
        last = file_lba + (end - 1) // FORM1_DATA_SIZE
        for sector in self.iter_sectors(first, last - first + 1):
            if sector.form != 1:
                raise DiscError(
                    f"file at sector {file_lba}: sector {sector.lba} is Mode 2 Form 2 "
                    f"(submode 0x{sector.subheader.submode:02x}); only Form 1 user data "
                    f"is writable. Nothing was written."
                )
        writes: list[SectorWrite] = []
        written = 0
        while written < len(data):
            position = offset + written
            lba = file_lba + position // FORM1_DATA_SIZE
            start = position % FORM1_DATA_SIZE
            chunk = data[written : written + FORM1_DATA_SIZE - start]
            block = bytearray(self.read_sector(lba).data)
            block[start : start + len(chunk)] = chunk
            write = self.write_sector_data(lba, bytes(block))
            if write is not None:
                writes.append(write)
            written += len(chunk)
        return writes
