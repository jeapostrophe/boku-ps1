"""Build the archive's containers in memory, so the walkers can be tested without a disc.

Like `tests/synth.py`, this is a *writer* and the modules it tests only read: a layout is
laid out here and parsed there, so a bug shared between the two would have to be written
twice, in opposite directions. Nothing here is disc content — the "text" it emits is a
handful of glyph ids chosen for arithmetic, not for what they draw.
"""

from __future__ import annotations

import struct

SECTOR = 2048
EXE_LOAD_BIAS = 0x8000F800
BOKU_BIN_LBA = 1046
DIR_COUNT_ADDR = 0x80024698
SELECT_BASE_ADDR = 0x80028F6C
SELECT_LINES_ADDR = 0x80028F74
SELECT_FIRST_ADDR = 0x80028F80

END = 0x8000
NEWLINE = 0x8001
PAGE = 0x8002


def words(*values: int) -> bytes:
    """Little-endian `u16`s — the unit all of the game's text is written in."""
    return b"".join(v.to_bytes(2, "little") for v in values)


def align4(b: bytes) -> bytes:
    return b + bytes((-len(b)) % 4)


def pack(children: list[bytes | None]) -> bytes:
    """`u32 count; count * {u32 offset, u32 size}` then the children, 4-aligned.

    A `None` child is the `{0, 0}` null entry the map packs use for absent children.
    """
    head = len(children).to_bytes(4, "little")
    table = b""
    body = b""
    pos = 4 + 8 * len(children)
    for child in children:
        if child is None:
            table += struct.pack("<II", 0, 0)
            continue
        table += struct.pack("<II", pos, len(child))
        body += child
        pos += len(child)
        pad = (-pos) % 4
        body += bytes(pad)
        pos += pad
    return head + table + body


def instruction(opcode: int, size_words: int, payload: bytes = b"") -> bytes:
    """`u8 opcode, u8 size_in_words, operands` padded to `size_words` 16-bit words."""
    out = bytes([opcode, size_words]) + payload
    return out + bytes(2 * size_words - len(out))


def block(entries: list[bytes | None]) -> bytes:
    """An event block: `u32 n; u32 off[n]` then the entries, each 4-aligned.

    Offsets are absolute from the block start, ascending, 0 for a null entry — which is
    exactly what `boku.events.Block` expects to find.
    """
    n = len(entries)
    pos = 4 + 4 * n
    offsets = []
    body = b""
    for entry in entries:
        if entry is None:
            offsets.append(0)
            continue
        offsets.append(pos)
        chunk = align4(entry)
        body += chunk
        pos += len(chunk)
    return n.to_bytes(4, "little") + b"".join(o.to_bytes(4, "little") for o in offsets) + body


def cast(pairs: list[tuple[int, int]]) -> bytes:
    """Block entry 0: `u32 n; n * {u8 slot, u8 variant}`, padded to 4."""
    return align4(len(pairs).to_bytes(4, "little") + bytes(b for pair in pairs for b in pair))


def condition(tree: bytes = b"") -> bytes:
    """Block entry 1: `u32 length` then that many bytes of 8-byte nodes."""
    return len(tree).to_bytes(4, "little") + tree


def cond_node(kind: int, flag: int, op: int, count: int, value: int = 0) -> bytes:
    return bytes([kind, flag, op, count, value, 0, 0, 0])


def voice_key(start: int = 16, end: int = 32, channel: int = 0, file_no: int = 2) -> bytes:
    return struct.pack("<IIBBH", start, end, channel, file_no, 0)


def child1(blocks: list[tuple[int, bytes]]) -> bytes:
    """A map pack's child 1: `u32 n; n * {u16 id, u16 length, u32 offset}` then the blocks."""
    head = len(blocks).to_bytes(4, "little")
    table = b""
    body = b""
    pos = 4 + 8 * len(blocks)
    for event_id, data in blocks:
        table += struct.pack("<HHI", event_id, len(data), pos)
        body += data
        pos += len(data)
    return head + table + body


def placements(records: list[tuple[int, int, int]]) -> bytes:
    """A map pack's child 0: `u32 n; n * 20 bytes`, of which we fill flags, slot and id."""
    out = len(records).to_bytes(4, "little")
    for flags, slot, event_id in records:
        record = bytearray(20)
        record[0x10] = flags
        record[0x11] = slot
        record[0x12:0x14] = struct.pack("<h", event_id)
        out += bytes(record)
    return out


def map_pack(blocks: list[tuple[int, bytes]], records: list[tuple[int, int, int]]) -> bytes:
    """The seven-child pack a map file is; only children 0 and 1 carry anything here."""
    return pack(
        [placements(records), child1(blocks), b"\0\0\0\0", None, None, b"\0\0\0\0", b"\0\0\0\0"]
    )


def sec_ev(records: list[tuple[int, int, int]]) -> bytes:
    """`EV.SEC`: `u32 count; count * {u16 event_id, u16 size, u16 sector}`."""
    return len(records).to_bytes(4, "little") + b"".join(
        struct.pack("<HHH", event_id, size, sector) for event_id, size, sector in records
    )


def sec_m(records: list[tuple[str, int, int]]) -> bytes:
    """`M_FILES.SEC`: `u32 count; count * {char name[8], u32 size, u16 sector, u16 junk}`."""
    return len(records).to_bytes(4, "little") + b"".join(
        struct.pack("<8sIHH", name.encode("ascii"), size, sector, 0x4934)
        for name, size, sector in records
    )


class ExeBuilder:
    """A `SCPS_100.88` big enough to hold `g_cd_dir` and the tables the walkers read."""

    SIZE = 0x80000

    def __init__(self) -> None:
        self.data = bytearray(self.SIZE)

    def put(self, ram: int, raw: bytes) -> None:
        off = ram - EXE_LOAD_BIAS
        self.data[off : off + len(raw)] = raw

    def directory(self, entries: list[tuple[str, int, int]], names_at: int = 0x80010000) -> None:
        """Write `g_cd_dir`'s three parallel arrays and the dev-time path strings.

        The count word at `DIR_COUNT_ADDR` is what the reader finds the arrays from, so
        the arrays go immediately before it, in the order the executable has them.
        """
        count = len(entries)
        name_ptrs = []
        cursor = names_at
        for name, _lba, _size in entries:
            self.put(cursor, name.encode("ascii") + b"\0")
            name_ptrs.append(cursor)
            cursor += len(name) + 1
        end = DIR_COUNT_ADDR
        self.put(end, count.to_bytes(4, "little"))
        self.put(end - 4 * count, b"".join(p.to_bytes(4, "little") for p in name_ptrs))
        self.put(end - 8 * count, b"".join(s.to_bytes(4, "little") for _n, _l, s in entries))
        self.put(end - 12 * count, b"".join(lba.to_bytes(4, "little") for _n, lba, _s in entries))

    def select_tables(self, base: bytes, lines: bytes, first: bytes) -> None:
        self.put(SELECT_BASE_ADDR, base)
        self.put(SELECT_LINES_ADDR, lines)
        self.put(SELECT_FIRST_ADDR, first)

    def build(self) -> bytes:
        return bytes(self.data)


def archive_of(members: list[tuple[str, bytes]]) -> tuple[bytes, list[tuple[str, int, int]]]:
    """Lay members out sector by sector and return `(BOKU.BIN, directory entries)`.

    The directory entries are `(dev path, absolute LBA, byte size)` in archive order —
    exactly what `ExeBuilder.directory` wants, so a test lays a tiling out once.
    """
    blob = b""
    entries = []
    lba = BOKU_BIN_LBA
    for name, data in members:
        entries.append((name, lba, len(data)))
        padded = data + bytes((-len(data)) % SECTOR)
        blob += padded
        lba += len(padded) // SECTOR
    return blob, entries


class FakeImage:
    """The `image_bytes` surface `boku.arrays` reads through, over plain byte strings."""

    def __init__(self, images: dict[str, tuple[int, bytes]]) -> None:
        self._images = images

    def image_bytes(self, image: str, ram: int, n: int) -> bytes:
        base, data = self._images[image]
        return data[ram - base : ram - base + n]


class FakeExe:
    """The `exe_bytes` surface `SelectTables` reads through, over a plain byte string."""

    def __init__(self, exe: bytes) -> None:
        self.exe = exe

    def exe_bytes(self, ram: int, n: int) -> bytes:
        return self.exe[ram - EXE_LOAD_BIAS : ram - EXE_LOAD_BIAS + n]
