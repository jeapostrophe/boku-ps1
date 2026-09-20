"""Build a tiny Mode 2 CD image in memory, so the sector and ISO 9660 tests need no disc.

This is a *writer*, deliberately separate from `boku.disc`, which only reads: the tests
compare what the reader parses against the tree this module was asked to lay out, so a
bug shared between the two would have to be written twice, in opposite directions.

It is a minimum viable ISO 9660: a primary volume descriptor, a terminator, directory
extents that may span sectors, and file extents. No path tables, no Joliet, and EDC/ECC
are left zero -- nothing here reads them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RAW_SECTOR_SIZE = 2352
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
FORM1_DATA_SIZE = 2048
FORM2_DATA_SIZE = 2324
MSF_OFFSET = 150
PVD_LBA = 16

SUBMODE_DATA = 0x08
SUBMODE_FORM2 = 0x20
SUBMODE_AUDIO = 0x04

XA_ATTR_OWNER_READ = 0x0001
XA_ATTR_WORLD_READ = 0x0100
XA_ATTR_FORM1 = 0x0800
XA_ATTR_FORM2 = 0x1000
XA_ATTR_INTERLEAVED = 0x2000
XA_ATTR_DIRECTORY = 0x8000


@dataclass
class File:
    """A file to lay out.

    `form` picks the sectors' own form. `declare_form` False reproduces the shape measured
    on this disc's `__STR` entries, whose directory records set the interleaved bit and
    *neither* form bit.
    """

    name: str
    content: bytes
    form: int = 1
    interleaved: bool = False
    declare_form: bool = True

    @property
    def iso_name(self) -> str:
        return f"{self.name};1"


@dataclass
class Directory:
    name: str
    children: list = field(default_factory=list)

    @property
    def iso_name(self) -> str:
        return self.name


def _bcd(value: int) -> int:
    return ((value // 10) << 4) | (value % 10)


def raw_sector(lba: int, data: bytes, *, submode: int = SUBMODE_DATA) -> bytes:
    """One 2352-byte Mode 2 sector carrying `data`, zero-padded to its form's size."""
    form2 = bool(submode & SUBMODE_FORM2)
    capacity = FORM2_DATA_SIZE if form2 else FORM1_DATA_SIZE
    if len(data) > capacity:
        raise ValueError(f"{len(data)} bytes do not fit a form {2 if form2 else 1} sector")
    address = lba + MSF_OFFSET
    minute, rest = divmod(address, 60 * 75)
    second, frame = divmod(rest, 75)
    header = bytes([_bcd(minute), _bcd(second), _bcd(frame), 2])
    subheader = bytes([0, 0, submode, 0]) * 2
    sector = bytearray(RAW_SECTOR_SIZE)
    sector[0:12] = SYNC
    sector[12:16] = header
    sector[16:24] = subheader
    sector[24 : 24 + len(data)] = data
    return bytes(sector)


def _xa(attributes: int) -> bytes:
    return (
        (0).to_bytes(2, "big")
        + (0).to_bytes(2, "big")
        + attributes.to_bytes(2, "big")
        + b"XA"
        + bytes(6)
    )


def _directory_record(
    name: bytes, lba: int, size: int, *, is_dir: bool, attributes: int, xa: bool = True
) -> bytes:
    pad = 1 - len(name) % 2
    length = 33 + len(name) + pad + (14 if xa else 0)
    record = bytearray(length)
    record[0] = length
    record[2:6] = lba.to_bytes(4, "little")
    record[6:10] = lba.to_bytes(4, "big")
    record[10:14] = size.to_bytes(4, "little")
    record[14:18] = size.to_bytes(4, "big")
    record[18:25] = bytes([100, 1, 1, 0, 0, 0, 0])  # 2000-01-01 00:00:00 GMT
    record[25] = 0x02 if is_dir else 0x00
    record[28:30] = (1).to_bytes(2, "little")
    record[30:32] = (1).to_bytes(2, "big")
    record[32] = len(name)
    record[33 : 33 + len(name)] = name
    if xa:
        record[33 + len(name) + pad :] = _xa(attributes)
    return bytes(record)


def _pack(records: list[bytes]) -> list[bytes]:
    """Records into 2048-byte blocks; a record never straddles a block."""
    blocks: list[bytearray] = [bytearray(FORM1_DATA_SIZE)]
    offset = 0
    for record in records:
        if offset + len(record) > FORM1_DATA_SIZE:
            blocks.append(bytearray(FORM1_DATA_SIZE))
            offset = 0
        blocks[-1][offset : offset + len(record)] = record
        offset += len(record)
    return [bytes(block) for block in blocks]


def _file_attributes(entry: File) -> int:
    attributes = XA_ATTR_OWNER_READ | XA_ATTR_WORLD_READ
    if entry.declare_form:
        attributes |= XA_ATTR_FORM2 if entry.form == 2 else XA_ATTR_FORM1
    if entry.interleaved:
        attributes |= XA_ATTR_INTERLEAVED
    return attributes


def _sectors_for(entry: File) -> int:
    capacity = FORM2_DATA_SIZE if entry.form == 2 else FORM1_DATA_SIZE
    return max(1, (len(entry.content) + capacity - 1) // capacity)


def recorded_size(entry: File) -> int:
    """What the directory record says -- Form 2 sizes are counted in 2048-byte units."""
    if entry.form == 2:
        return _sectors_for(entry) * FORM1_DATA_SIZE
    return len(entry.content)


def build_image(children: list, *, volume_id: str = "BOKU_TEST", pad_sectors: int = 2) -> bytes:
    """Lay out a whole image: system area, PVD, terminator, directories, then file data."""
    directories: list[tuple[Directory | None, list]] = []

    def collect(node: Directory | None, kids: list) -> None:
        directories.append((node, kids))
        for child in kids:
            if isinstance(child, Directory):
                collect(child, child.children)

    collect(None, children)

    # Pass 1: record lengths (which do not depend on the addresses) give each extent's size.
    extent_sectors: list[int] = []
    for _, kids in directories:
        names = [b"\x00", b"\x01"] + [child.iso_name.encode("ascii") for child in kids]
        placeholders = [_directory_record(name, 0, 0, is_dir=True, attributes=0) for name in names]
        extent_sectors.append(len(_pack(placeholders)))

    lba = PVD_LBA + 2
    directory_lba: list[int] = []
    for count in extent_sectors:
        directory_lba.append(lba)
        lba += count

    file_lba: dict[int, int] = {}
    for _, kids in directories:
        for child in kids:
            if isinstance(child, File):
                file_lba[id(child)] = lba
                lba += _sectors_for(child)
    end_lba = lba + pad_sectors

    index = {id(node): position for position, (node, _) in enumerate(directories) if node}
    sectors: dict[int, bytes] = {}

    for position, (node, kids) in enumerate(directories):
        self_lba = directory_lba[position]
        self_size = extent_sectors[position] * FORM1_DATA_SIZE
        parent_position = 0
        if node is not None:
            for other, other_kids in directories:
                if any(child is node for child in other_kids):
                    parent_position = index.get(id(other), 0) if other is not None else 0
        records = [
            _directory_record(
                b"\x00", self_lba, self_size, is_dir=True, attributes=XA_ATTR_DIRECTORY
            ),
            _directory_record(
                b"\x01",
                directory_lba[parent_position],
                extent_sectors[parent_position] * FORM1_DATA_SIZE,
                is_dir=True,
                attributes=XA_ATTR_DIRECTORY,
            ),
        ]
        for child in kids:
            if isinstance(child, Directory):
                child_position = index[id(child)]
                records.append(
                    _directory_record(
                        child.iso_name.encode("ascii"),
                        directory_lba[child_position],
                        extent_sectors[child_position] * FORM1_DATA_SIZE,
                        is_dir=True,
                        attributes=XA_ATTR_DIRECTORY,
                    )
                )
            else:
                records.append(
                    _directory_record(
                        child.iso_name.encode("ascii"),
                        file_lba[id(child)],
                        recorded_size(child),
                        is_dir=False,
                        attributes=_file_attributes(child),
                    )
                )
        for offset, block in enumerate(_pack(records)):
            sectors[self_lba + offset] = raw_sector(self_lba + offset, block)

    for _, kids in directories:
        for child in kids:
            if not isinstance(child, File):
                continue
            start = file_lba[id(child)]
            capacity = FORM2_DATA_SIZE if child.form == 2 else FORM1_DATA_SIZE
            submode = SUBMODE_DATA if child.form == 1 else SUBMODE_FORM2 | SUBMODE_AUDIO
            for offset in range(_sectors_for(child)):
                chunk = child.content[offset * capacity : (offset + 1) * capacity]
                sectors[start + offset] = raw_sector(start + offset, chunk, submode=submode)

    sectors[PVD_LBA] = raw_sector(
        PVD_LBA,
        _primary_volume_descriptor(
            volume_id=volume_id,
            space_size=end_lba,
            root_lba=directory_lba[0],
            root_size=extent_sectors[0] * FORM1_DATA_SIZE,
        ),
    )
    terminator = bytearray(FORM1_DATA_SIZE)
    terminator[0] = 255
    terminator[1:6] = b"CD001"
    terminator[6] = 1
    sectors[PVD_LBA + 1] = raw_sector(PVD_LBA + 1, bytes(terminator))

    return b"".join(sectors.get(n, raw_sector(n, b"")) for n in range(end_lba))


def _primary_volume_descriptor(
    *, volume_id: str, space_size: int, root_lba: int, root_size: int
) -> bytes:
    descriptor = bytearray(FORM1_DATA_SIZE)
    descriptor[0] = 1
    descriptor[1:6] = b"CD001"
    descriptor[6] = 1
    descriptor[8:40] = b"PLAYSTATION".ljust(32)
    descriptor[40:72] = volume_id.encode("ascii").ljust(32)
    descriptor[80:84] = space_size.to_bytes(4, "little")
    descriptor[84:88] = space_size.to_bytes(4, "big")
    descriptor[128:130] = FORM1_DATA_SIZE.to_bytes(2, "little")
    descriptor[130:132] = FORM1_DATA_SIZE.to_bytes(2, "big")
    descriptor[156:190] = _directory_record(
        b"\x00", root_lba, root_size, is_dir=True, attributes=0, xa=False
    )
    return bytes(descriptor)
