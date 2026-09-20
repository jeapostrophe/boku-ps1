"""Event scripts: blocks, the bytecode VM, conditions and the scene flow graph.

`research/event-scripts.md` is the format note; this module is its executable form, ported
from `work/rec05/scenes.py` (+ `work/rec03/blocks.py`, `cond.py`, `evver.py`). It
reproduces `research/data/scenes.tsv` and `scene-edges.tsv` byte for byte
(`boku.research`), which is the gate that says the port did not change the reading.

An **event block** is one scene: a cast list, a condition tree, bytecode, and pairs of
(voice key, text). It is copied byte-identically into every map variant where it can fire,
and/or held once in `EV.BIN`. Messages are addressed **by index inside the block**, so the
logical line id is `E<event id>.<message index>` and every copy of that block is one of its
physical sites (`boku.sites`).

The **walker advances by the opcode size table, not by the size byte**, and requires the
two to agree, the walk to end exactly on `END`, fewer than 4 bytes to follow, every jump to
land on an instruction boundary and every message operand to be in range. That is what
makes a wrong table loud instead of silently decoding garbage.
"""

from __future__ import annotations

import re
import struct
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from boku.archive import EV_DIR_INDEX, MAP_DIR_INDEX, Archive, Member, parse_pack
from boku.arrays import SelectTables
from boku.glyphs import GlyphTable


class EventError(Exception):
    """A block, an instruction stream or a condition tree that does not decode."""


# --- the instruction set ----------------------------------------------------------------

OPS: dict[int, tuple[str, int | None]] = {
    0x00: ("POS", 7),
    0x01: ("INI", None),
    0x02: ("IPROG", 3),
    0x03: ("JMP", 2),
    0x04: ("JMPM", 4),
    0x05: ("JMPE", 4),
    0x06: ("PROG", 3),
    0x07: ("GO", 6),
    0x08: ("WALK", 5),
    0x09: ("RUN", 6),
    0x0A: ("MAP", 4),
    0x0B: ("BGM", 2),
    0x0C: ("SE", 4),
    0x0D: ("XAMSG", 4),
    0x0E: ("MSG", 4),
    0x0F: ("XA", 4),
    0x10: ("FLAG", 3),
    0x11: ("DISP", 2),
    0x12: ("ANM", 3),
    0x13: ("BGANM", 2),
    0x14: ("LOOK", 5),
    0x15: ("END", 1),
    0x16: ("AWT", 2),
    0x17: ("BWT", 3),
    0x18: ("XWT", 1),
    0x19: ("DIXA", 1),
    0x1A: ("WIN", 2),
    0x1B: ("WAT", 2),
    0x1C: ("MWT", 2),
    0x1D: ("TIME", 2),
    0x1E: ("IF", None),
    0x1F: ("DEBUG", None),
    0x20: ("FACE", 2),
    0x21: ("SELECT", 3),
    0x22: ("MOVIE", 5),
    0x23: ("LFLAG", 5),
    0x24: ("WARP", 6),
    0x25: ("MSGWT", None),
    0x26: ("YGO", 4),
    0x27: ("XSEEK", 1),
}
"""Opcode -> (name, size in 16-bit words). `None` = present in the dispatch table but
unused on this disc, so the walker refuses it rather than guessing a length."""

OP_JMP, OP_JMPM, OP_JMPE = 0x03, 0x04, 0x05
OP_PROG = 0x06
OP_MAP, OP_MOVIE = 0x0A, 0x22
OP_XAMSG, OP_MSG, OP_XA, OP_SELECT = 0x0D, 0x0E, 0x0F, 0x21
OP_FLAG, OP_LFLAG = 0x10, 0x23
OP_POS, OP_END = 0x00, 0x15

TEXT_OPS = frozenset({OP_XAMSG, OP_MSG, OP_XA, OP_SELECT})
"""The four opcodes that name a message entry by index."""

NATIVE = {15: "NSELECT", 16: "NMSG"}
"""`PROG` routines that open a message by a day-computed index — the aunt's dinner quiz."""

SEL_FLAG = 255
"""`g_flags[255]`, the VM's result register: `SELECT` writes the chosen index there."""
CANCEL = 99
"""What `SELECT` writes on ✕, when its fourth operand allows cancelling."""

TALK_GROUPS_ADDR = 0x80029438
DINNER_ANSWER_ADDR = 0x80029454
DINNER_MENU_ADDR = 0x80029474
DAYS_IN_AUGUST = 31


def s16(b: bytes, o: int) -> int:
    return struct.unpack_from("<h", b, o)[0]


def u16(b: bytes, o: int) -> int:
    return struct.unpack_from("<H", b, o)[0]


def u32s(b: bytes, o: int, n: int) -> tuple[int, ...]:
    return struct.unpack_from(f"<{n}I", b, o)


@dataclass
class Ins:
    """One decoded instruction: its offset in the code entry, its opcode and its bytes.

    The operand properties below exist because four modules were indexing `b` by hand,
    and two of them at different bases — `boku.sites`'s lenient walker used to yield the
    operands from `+2`, so the message index was `b[4]` in one place and `a[2]` in another.
    """

    pc: int
    op: int
    b: bytes

    @property
    def name(self) -> str:
        return OPS[self.op][0]

    @property
    def end(self) -> int:
        return self.pc + len(self.b)

    @property
    def message_index(self) -> int:
        """Operand `@4`: which `(voice key, text)` pair of the block this names."""
        return self.b[4]

    @property
    def slot(self) -> int:
        """Operand `@6` of `XAMSG`/`XA`: the actor slot whose mouth flaps."""
        return self.b[6]

    @property
    def clip(self) -> str:
        """`XAMSG`'s recording name, `"%02d%02d_%02d"` (`research/event-scripts.md`)."""
        return f"{self.b[2]:02d}{self.b[3]:02d}_{self.b[5]:02d}"

    @property
    def select_type(self) -> int:
        return self.b[2]

    @property
    def select_variant(self) -> int:
        return self.b[3]

    @property
    def select_cancellable(self) -> bool:
        """Operand `@5`: whether ✕ closes the box, writing `CANCEL` to the result register."""
        return bool(self.b[5])


def decode_code(code: bytes, ops: dict[int, tuple[str, int | None]] = OPS) -> dict[int, Ins]:
    """Walk one code entry by the size table, refusing every disagreement.

    `ops` is a parameter so a test can hand in a deliberately wrong table and watch the
    gate fire — that is what `research/event-scripts.md`'s `--selftest` did.
    """
    out: dict[int, Ins] = {}
    p = 0
    while True:
        if p + 2 > len(code):
            raise EventError(f"ran off the end at {p:#x} without END")
        op, n = code[p], code[p + 1]
        if op not in ops or ops[op][1] is None:
            raise EventError(f"opcode {op:#04x} at {p:#x} not in table")
        if n != ops[op][1]:
            raise EventError(f"opcode {op:#04x} at {p:#x}: size byte {n}, table {ops[op][1]}")
        out[p] = Ins(p, op, code[p : p + 2 * n])
        p += 2 * n
        if op == OP_END:
            break
    rest = code[p:]
    if len(rest) >= 4:
        raise EventError(f"{len(rest)} bytes after END")
    for i in out.values():
        if i.op in (OP_JMP, OP_JMPM, OP_JMPE):
            t = i.pc + 2 * s16(i.b, 2)
            if t not in out:
                raise EventError(f"jump at {i.pc:#x} to {t:#x}: not an instruction boundary")
    return out


# --- the block --------------------------------------------------------------------------


def pack_block(entries: list[bytes | None]) -> bytes:
    """An event block laid out from its entries, every offset recomputed from the lengths.

    Each entry's bytes already carry whatever pad follows it — an entry's length *is* the
    distance to the next live offset — so this is where a reinserter's growth shows up:
    lengthen one entry and every later offset moves by the same amount.
    """
    n = len(entries)
    offsets = []
    body = b""
    position = 4 + 4 * n
    for entry in entries:
        if entry is None:
            offsets.append(0)
            continue
        offsets.append(position)
        body += entry
        position += len(entry)
    return struct.pack(f"<{1 + n}I", n, *offsets) + body


class Block:
    """An event block: `u32 n; u32 off[n]` then the entries those offsets point at.

    Entry 0 is the cast, 1 the condition tree, 2 the bytecode, then `(voice key, text)`
    pairs. An entry's length is the distance to the next live offset, so a null entry
    (offset 0) has no bytes at all.

    `serialise` rebuilds the block from those entries with the offsets recomputed, so it
    is an assertion about the header as well as the bytes: that the live offsets ascend,
    that the first is the header's own end, and that the entries tile the block exactly.
    """

    def __init__(self, data: bytes) -> None:
        self.data = data
        (self.n,) = u32s(data, 0, 1)
        self.offsets = u32s(data, 4, self.n)
        ends = sorted({o for o in self.offsets if o} | {len(data)})
        self._next = dict(pairwise(ends))
        self._next[ends[-1]] = len(data)
        self.entries: list[bytes | None] = [self.entry(i) for i in range(self.n)]

    @property
    def message_count(self) -> int:
        """`(n - 3) / 2` — the number of (voice key, text) pairs. 0 for a stub."""
        return (self.n - 3) // 2 if self.n >= 3 else 0

    @property
    def is_stub(self) -> bool:
        """`n == 2`: header and trigger data only; the full block lives in `EV.BIN`."""
        return self.n < 3

    def entry(self, i: int) -> bytes | None:
        """Entry `i`'s bytes, or `None` for a null entry or one this block does not have."""
        if i >= self.n or not self.offsets[i]:
            return None
        o = self.offsets[i]
        return self.data[o : self._next[o]]

    def entry_span(self, i: int) -> tuple[int, int] | None:
        """`(offset, end)` of entry `i` inside the block, for placing a physical site."""
        if i >= self.n or not self.offsets[i]:
            return None
        o = self.offsets[i]
        return o, self._next[o]

    def message_key(self, index: int) -> bytes | None:
        """Entry `3 + 2*index`: the 12-byte voice clip key, or `None` for silent text."""
        return self.entry(3 + 2 * index)

    def message_text(self, index: int) -> bytes | None:
        """Entry `4 + 2*index`: the glyph words, or `None` for a voice-only entry."""
        return self.entry(4 + 2 * index)

    def serialise(self) -> bytes:
        """The block's own bytes, rebuilt from the parsed entries."""
        return pack_block(self.entries)

    def replace_entry(self, i: int, raw: bytes) -> Block:
        """A new block with entry `i` replaced by `raw`, padded to 4, offsets recomputed.

        `replace_entry(4 + 2*index, ...)` is how `PIPE-03` rewrites one message. Handing
        back the entry that is already there reproduces the block byte for byte, because
        an entry's own bytes are already padded; a longer one moves every later offset by
        the padded difference and changes nothing else.
        """
        if self.entries[i] is None:
            raise EventError(f"entry {i} of this block is null; there is nothing to replace")
        entries = list(self.entries)
        entries[i] = raw + bytes(-len(raw) % 4)
        return Block(pack_block(entries))


@dataclass(frozen=True)
class BlockInstance:
    """One physical copy of an event block, and where it sits in the archive."""

    member: Member
    container: str
    """`"c1"` for a map pack's child 1, `"ev"` for an `EV.BIN` member."""
    table: int
    """Index in the child-1 table; always 0 for an `EV.BIN` member."""
    event_id: int
    offset_in_member: int
    data: bytes


MAP_PACK_CHILDREN = 7
MAP_PACK_BLOCK_TABLE = 1
"""A map file is a seven-child pack; child 1 is its table of event blocks."""


@dataclass(frozen=True)
class BlockTable:
    """A map pack's child 1: `u32 n; n * {u16 event_id, u16 length, u32 offset}`, then the
    blocks, which chain exactly.

    `serialise` recomputes every offset from the lengths, so it says the chain holds as
    well as reproducing the bytes — and it is the operation `PIPE-03` needs when a grown
    message makes one of these blocks longer.
    """

    blocks: tuple[tuple[int, bytes], ...]
    """`(event id, block bytes)` in table order."""

    @property
    def header_size(self) -> int:
        return 4 + 8 * len(self.blocks)

    def offset_of(self, index: int) -> int:
        """Where block `index` starts inside child 1."""
        return self.header_size + sum(len(b) for _ident, b in self.blocks[:index])

    def serialise(self) -> bytes:
        table = b""
        body = b""
        position = self.header_size
        for ident, data in self.blocks:
            table += struct.pack("<HHI", ident, len(data), position)
            body += data
            position += len(data)
        return len(self.blocks).to_bytes(4, "little") + table + body

    def replace(self, index: int, data: bytes) -> BlockTable:
        """A copy with block `index` replaced; every later offset follows its new length."""
        blocks = list(self.blocks)
        blocks[index] = (blocks[index][0], data)
        return BlockTable(tuple(blocks))


def parse_block_table(c1: bytes, where: str) -> BlockTable:
    """Read child 1, refusing a table whose offsets do not chain from its own header."""
    (n,) = u32s(c1, 0, 1)
    position = 4 + 8 * n
    blocks = []
    for t in range(n):
        ident, length, off = struct.unpack_from("<HHI", c1, 4 + 8 * t)
        if off != position:
            raise EventError(f"{where} table {t}: offset {off:#x} != chain {position:#x}")
        position = off + length
        blocks.append((ident, c1[off : off + length]))
    if position != len(c1):
        raise EventError(f"{where}: child 1 ends {len(c1) - position} bytes after the last block")
    return BlockTable(tuple(blocks))


def map_block_table(archive: Archive, member: Member) -> tuple[int, BlockTable]:
    """`(child 1's offset in the member, its parsed table)` for one map pack."""
    b = archive.blob(member)
    pack = parse_pack(b)
    if not pack or len(pack.entries) != MAP_PACK_CHILDREN:
        raise EventError(f"{member.name}: not a {MAP_PACK_CHILDREN}-child map pack")
    o, s = pack.entries[MAP_PACK_BLOCK_TABLE]
    return o, parse_block_table(b[o : o + s], member.name)


def iter_blocks(archive: Archive) -> Iterator[BlockInstance]:
    """Every event block on the disc, in archive order, with tiling checks on the way."""
    for m in archive.members:
        if m.dir_index == MAP_DIR_INDEX:
            base, table = map_block_table(archive, m)
            for t, (ident, data) in enumerate(table.blocks):
                yield BlockInstance(m, "c1", t, ident, base + table.offset_of(t), data)
        elif m.dir_index == EV_DIR_INDEX:
            yield BlockInstance(m, "ev", 0, int(m.short_name[2:6]), 0, archive.blob(m))


class Event:
    """One event id and every block instance that carries it."""

    def __init__(self, event_id: int) -> None:
        self.id = event_id
        self.members: list[str] = []
        self.instances: list[BlockInstance] = []
        self.block: Block | None = None
        self.signature: tuple[bytes | None, ...] = ()
        self.stub_only = True

    @property
    def name(self) -> str:
        return f"E{self.id:04d}"


def load_events(archive: Archive) -> dict[int, Event]:
    """Every distinct event id, with the full block chosen over a stub.

    The copies are cross-checked as they load: two full copies of an id must agree in
    entries 0-2, and a stub must agree with the full copy in entries 0-1. That is the
    duplication model (`research/text-format.md`) asserted rather than assumed.
    """
    events: dict[int, Event] = {}
    for inst in iter_blocks(archive):
        e = events.setdefault(inst.event_id, Event(inst.event_id))
        e.members.append(inst.member.short_name.replace(".BIN", ""))
        e.instances.append(inst)
        block = Block(inst.data)
        sig = (block.n, block.entry(0), block.entry(1), block.entry(2))
        if not block.is_stub:
            if e.block is not None and not e.stub_only and e.signature != sig:
                # `n` is compared with the rest: two copies that agreed in entries 0-2 but
                # held different numbers of messages would reach `sc.messages[index]` as an
                # IndexError rather than as a refusal naming the event.
                raise EventError(f"E{inst.event_id:04d} copies differ in entries 0-2")
            e.block, e.signature, e.stub_only = block, sig, False
        elif e.block is None:
            e.block, e.signature = block, (block.n, block.entry(0), block.entry(1), None)
        elif (block.entry(0), block.entry(1)) != e.signature[1:3]:
            raise EventError(f"E{inst.event_id:04d} stub differs from full copy in entries 0-1")
    return events


# --- conditions (block entry 1, and `EVVER.BIN`) -----------------------------------------

COND_OPS = {2: "==", 3: "!=", 4: ">", 5: ">=", 6: "<", 7: "<="}

CondNode = tuple[Any, ...]


def parse_cond(b: bytes, o: int) -> tuple[CondNode, int]:
    """One 8-byte condition node at `o`, recursing into groups. Returns the next offset."""
    kind, fid, op, cnt = b[o], b[o + 1], b[o + 2], b[o + 3]
    if kind in (0, 1):
        kids = []
        p = o + 8
        for _ in range(cnt):
            k, p = parse_cond(b, p)
            kids.append(k)
        return ("and" if kind == 0 else "or", kids), p
    if kind == 8:
        name = b[o + 4 : o + 7].decode("ascii", "replace")
        return ("map", COND_OPS.get(op, f"?{op}"), name), o + 8
    val = b[o + 4]
    if b[o + 5]:
        raise EventError(f"string operand on a non-map condition node at {o:#x}")
    if kind == 9:
        return ("flag", f"flag[{fid}]" if cnt else "lflag", COND_OPS.get(op, f"?{op}"), val), o + 8
    if kind == 10:
        return ("hour", "hour", COND_OPS.get(op, f"?{op}"), val), o + 8
    if kind == 11:
        return ("day", "day", COND_OPS.get(op, f"?{op}"), val), o + 8
    raise EventError(f"unknown condition node kind {kind} at {o:#x}")


def fmt_cond(t: CondNode) -> str:
    if t[0] in ("and", "or"):
        joiner = " & " if t[0] == "and" else " | "
        return "(" + joiner.join(fmt_cond(k) for k in t[1]) + ")"
    if t[0] == "map":
        return f"map{t[1]}{t[2]}"
    return f"{t[1]}{t[2]}{t[3]}"


def uses_day(t: CondNode) -> bool:
    if t[0] in ("and", "or"):
        return any(uses_day(k) for k in t[1])
    return t[0] == "day"


# --- placements (map pack child 0) --------------------------------------------------------


def trigger_kind(flags: int) -> str:
    """What makes an event fire: `research/event-scripts.md` § Placement records."""
    if flags & 0x80:
        return "auto"
    if flags & 0x40:
        return "talk" if flags & 0x20 else "near"
    return "examine" if flags & 0x20 else "zone"


@dataclass(frozen=True)
class Placement:
    """One placement record: where an event can fire and what triggers it."""

    map_name: str
    """The map's `A01000`-style name, without the `M_` prefix."""
    flags: int
    slot: int
    """Actor slot for a `talk` trigger, zone index for `examine`/`zone`."""
    in_ev: bool
    """The record's event id was negative: the block is an `EV.BIN` member."""

    @property
    def kind(self) -> str:
        return trigger_kind(self.flags)

    @property
    def label(self) -> str:
        """`auto`, or `talk:OJI` / `examine:z3` — what `scenes.tsv`'s triggers column holds."""
        if self.flags & 0x80:
            return self.kind
        who = CHARACTERS.get(self.slot, str(self.slot)) if self.flags & 0x40 else f"z{self.slot}"
        return f"{self.kind}:{who}"


def placements(archive: Archive) -> dict[int, list[Placement]]:
    """Every map's child-0 placement records, grouped by the event id they name."""
    out: dict[int, list[Placement]] = defaultdict(list)
    for m in archive.members:
        if m.dir_index != MAP_DIR_INDEX:
            continue
        b = archive.blob(m)
        o, s = parse_pack(b).entries[0]
        c0 = b[o : o + s]
        (n,) = u32s(c0, 0, 1)
        for i in range(n):
            r = c0[4 + 20 * i : 24 + 20 * i]
            event = s16(r, 0x12)
            out[abs(event)].append(Placement(m.short_name[2:8], r[0x10], r[0x11], event < 0))
    return out


# --- speakers -----------------------------------------------------------------------------

CHARACTERS = {
    0: "BOKU",
    1: "OJI",
    2: "OBA",
    3: "MOE",
    4: "SHI",
    5: "SAORI",
    6: "GUTS",
    7: "FAT",
    8: "MEGANE",
    9: "FATHER",
    10: "MONK",
}
"""`XAMSG`/`XA` operand `@6`: actor slot = character = `H_FILES` model id."""

LABEL_NAMES = {
    "ボク": "BOKU",
    "おじ": "OJI",
    "おば": "OBA",
    "萌": "MOE",
    "詩": "SHI",
    "ガッツ": "GUTS",
    "ファット": "FAT",
    "メガネ": "MEGANE",
    "女性": "WOMAN",
    "少年": "BOY",
    "父": "FATHER",
    "お坊さん": "MONK",
    "": "NONE",
    "ボク＋詩": "BOKU+SHI",  # noqa: RUF001 (the sheet draws a full-width plus)
    "沙織": "SAORI",
}
"""The inline label the message itself opens with, before the `「`."""

LABEL_ALIASES = {"WOMAN": "SAORI", "BOY": "GUTS"}
"""The label used before a character is introduced by name."""

OPEN_BRACKET = 0x0017
"""`「` — the glyph that closes a speaker label."""
NARRATION_BRACKET = 0x0019
"""`『` — narration, which has no speaker."""


# --- the flow graph ------------------------------------------------------------------------
#
# Conditions are carried along a path as a set of `v>=k` / `v<k` atoms. Two things make
# the result readable rather than a transcript of every branch: a path remembers the
# constants it has itself assigned, so a test of a flag the script just set is *decided*
# instead of reported; and alternatives that differ only by a covering split of one
# variable are merged back together. Both are greedy, and their fixed point depends on
# iteration order -- so every iteration over a set below is sorted. Without those sorts
# E0787's ENTRY->END condition came out six different ways in eight runs.

_COMPARISON = re.compile(r"^(.*?)(>=|<|==|!=)(.*)$")
_RANGE = re.compile(r"^(-?\d+)<=(.*?)<(-?\d+)$")


def _split_cond(c: str) -> tuple[str, str, str]:
    m = _COMPARISON.match(c)
    if m is None:
        raise EventError(f"not a condition atom: {c!r}")
    return m.group(1), m.group(2), m.group(3)


def _atoms(conds) -> Iterator[str]:
    """Expand the simplified forms back to `v>=k` / `v<k` atoms."""
    for c in conds:
        if c == "*":
            continue
        m = _RANGE.match(c)
        if m:
            yield f"{m.group(2)}>={m.group(1)}"
            yield f"{m.group(2)}<{m.group(3)}"
            continue
        v, op, k = _split_cond(c)
        if op == "==" and v != "map":
            yield f"{v}>={k}"
            yield f"{v}<{int(k) + 1}"
            continue
        yield c


def _bounds(conds) -> tuple[dict[str, tuple[int | None, int | None]], dict, dict]:
    """Per numeric variable `[lo, hi)`; map tests stay as sets of names."""
    num: dict[str, tuple[int | None, int | None]] = {}
    meq: dict[str, set[str]] = {}
    mne: dict[str, set[str]] = defaultdict(set)
    for c in _atoms(conds):
        v, op, k = _split_cond(c)
        if v == "map":
            if op == "==":
                meq.setdefault(v, set()).add(k)
            else:
                mne[v].add(k)
            continue
        lo, hi = num.get(v, (None, None))
        value = int(k)
        if op == ">=":
            lo = value if lo is None else max(lo, value)
        else:
            hi = value if hi is None else min(hi, value)
        num[v] = (lo, hi)
    return num, meq, mne


def _feasible(conds) -> bool:
    num, meq, mne = _bounds(conds)
    if any(lo is not None and hi is not None and lo >= hi for lo, hi in num.values()):
        return False
    return all(len(eq) <= 1 and not eq & mne[v] for v, eq in meq.items())


def _simplify(conds) -> str:
    num, meq, mne = _bounds(conds)
    out = ["*"] if "*" in conds else []
    done: set[str] = set()
    for c in _atoms(conds):
        v = _split_cond(c)[0]
        if v in done:
            continue
        done.add(v)
        if v == "map":
            out += [f"map=={k}" for k in sorted(meq.get(v, ()))] or [
                f"map!={k}" for k in sorted(mne[v])
            ]
            continue
        lo, hi = num[v]
        if lo is not None and hi is not None:
            out.append(f"{v}=={lo}" if hi == lo + 1 else f"{lo}<={v}<{hi}")
        elif lo is not None:
            out.append(f"{v}>={lo}")
        else:
            out.append(f"{v}==0" if hi == 1 else f"{v}<{hi}")
    return " & ".join(out)


def _merge_alternatives(condition_sets) -> set[str]:
    """`(A & x<k) | (A & x>=k)` -> `A`, to a fixed point, over sorted iteration orders."""

    def norm(conds) -> frozenset[str]:
        num, _meq, _mne = _bounds(conds)
        out = set(["*"] if "*" in conds else [])
        for v, (lo, hi) in num.items():
            if lo is not None and lo > 0:
                out.add(f"{v}>={lo}")
            if hi is not None:
                out.add(f"{v}<{hi}")
        for c in _atoms(conds):
            if _split_cond(c)[0] == "map":
                out.add(c)
        return frozenset(out)

    sets = {norm(cs) for cs in condition_sets}
    changed = True
    while changed:
        changed = False
        for a in sorted(sets, key=sorted):
            variables = sorted(
                {_split_cond(c)[0] for c in a if c != "*" and not c.startswith("map")}
            )
            for v in variables:
                mine = frozenset(c for c in a if c != "*" and _split_cond(c)[0] == v)
                rest = a - mine
                family = sorted(
                    (
                        b
                        for b in sets
                        if rest <= b
                        and b - rest
                        and all(c != "*" and _split_cond(c)[0] == v for c in b - rest)
                    ),
                    key=sorted,
                )
                if len(family) < 2:
                    continue
                intervals = sorted(
                    (_bounds(list(b - rest))[0][v] for b in family), key=lambda x: x[0] or 0
                )
                cur: int | None = 0
                for lo, hi in intervals:
                    if (lo or 0) > cur:
                        break
                    if hi is None:
                        cur = None
                        break
                    cur = max(cur, hi)
                if cur is None:
                    sets -= set(family)
                    sets.add(rest)
                    changed = True
                    break
            if changed:
                break
    return {_simplify(tuple(sorted(x))) for x in sets}


class Scene:
    """One decoded event: instructions, text nodes, edges and where it can happen."""

    def __init__(self, event: Event) -> None:
        self.event = event
        self.id = event.id
        self.cast: list[tuple[int, int]] = []
        self.condition: CondNode | None = None
        self.ins: dict[int, Ins] = {}
        self.reach: set[int] = set()
        self.slots: dict[int, set[int]] = {}
        self.named: dict[int, list[int]] = {}
        self.messages: list[tuple[bytes | None, bytes | None]] = []
        self.edges: list[tuple[int, Any, str]] = []
        self.entry_edges: dict[Any, str] = {}
        self.chain: list[tuple[str, str, int, bool]] = []
        self.rname = "R"
        self.complex = False
        self.mismatches: list[tuple[str, str, str]] = []

    @property
    def message_count(self) -> int:
        return self.event.block.message_count if self.event.block else 0

    def branch(self, i: Ins) -> list[tuple[str | None, int]]:
        """Successor edges of one instruction, with the condition each one needs."""
        nxt = i.end
        if i.op == OP_END:
            return []
        if i.op == OP_JMP:
            return [(None, i.pc + 2 * s16(i.b, 2))]
        if i.op == OP_JMPM:
            m = i.b[4:7].decode("ascii")
            return [("map!=" + m, nxt), ("map==" + m, i.pc + 2 * s16(i.b, 2))]
        if i.op == OP_JMPE:
            f, v, t = s16(i.b, 4), s16(i.b, 6), i.pc + 2 * s16(i.b, 2)
            n = self.flag_name(f)
            return [(f"{n}<{v}", nxt), (f"{n}>={v}", t)]
        return [(None, nxt)]

    def flag_name(self, f: int) -> str:
        if f < 0:
            return "lflag"
        if f == SEL_FLAG:
            return self.rname
        return f"flag[{f}]"

    def is_node(self, i: Ins) -> bool:
        """A graph node: text, a native message routine, or a hand-over to another map."""
        return (
            i.op in TEXT_OPS
            or (i.op == OP_PROG and s16(i.b, 2) in NATIVE)
            or i.op in (OP_MAP, OP_MOVIE)
        )

    def chain_token(self, i: Ins) -> str:
        n = s16(i.b, 6)
        m = i.b[2:5].decode("ascii")
        head = "MAP" if i.op == OP_MAP else f"MOVIE{s16(i.b, 8)}"
        return f"{head}:{m}" + (f">E{n:04d}" if n > 0 else "")

    def node_id(self, p: Any) -> str:
        """`E0171.0@58` — a message shown from two places is two nodes, named by its pc."""
        if p == "END":
            return "END"
        i = self.ins[p]
        if i.op == OP_PROG:
            return f"E{self.id:04d}.P{s16(i.b, 2)}@{p:X}"
        if i.op in (OP_MAP, OP_MOVIE):
            return f"E{self.id:04d}.{self.chain_token(i)}@{p:X}"
        return f"E{self.id:04d}.{i.message_index}@{p:X}"

    def play_order(self) -> list[int]:
        """Node instructions in depth-first order from the entry, fall-through first."""
        order: list[int] = []
        seen: set[int] = set()
        stack = [0]
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            i = self.ins[p]
            if self.is_node(i):
                order.append(p)
            for _, t in reversed(self.branch(i)):
                stack.append(t)
        return order


class EventWorld:
    """Every event on the disc, decoded once, plus the executable tables they lean on."""

    def __init__(self, archive: Archive, table: GlyphTable | None = None) -> None:
        self.archive = archive
        self.table = table if table is not None else GlyphTable.load()
        self.selects = SelectTables(archive)
        self.talk_groups = archive.exe_bytes(TALK_GROUPS_ADDR, 28)
        self.dinner_answer = archive.exe_bytes(DINNER_ANSWER_ADDR, DAYS_IN_AUGUST)
        self.dinner_menu = archive.exe_bytes(DINNER_MENU_ADDR, DAYS_IN_AUGUST)
        self.events = load_events(archive)
        self.placements = placements(archive)
        self.scenes = {eid: self.build(self.events[eid]) for eid in sorted(self.events)}

    # --- executable tables ----------------------------------------------------------

    def select_shape(self, select_type: int, variant: int) -> tuple[int, int]:
        """`(lines, prompt lines)` of a select box; the counts live in the executable.

        A translation may change a line's length, never the line count
        (`research/text-format.md` § SELECT).
        """
        return self.selects.shape(select_type, variant)

    def slot_name(self, k: int | None) -> str | None:
        """Actor slot -> our character name, expanding `g_ev_talk_groups` for 12…18."""
        if k is None:
            return None
        if k in CHARACTERS:
            return CHARACTERS[k]
        if k == 11:
            return "ALL"
        if 12 <= k < 19:
            group = self.talk_groups[4 * (k - 12) : 4 * (k - 11)]
            return "+".join(CHARACTERS[x] for x in group if x != 0xFF)
        return None

    def label_of(self, text: bytes | None) -> str:
        """The speaker the message itself names, from the glyphs before the first `「`."""
        if text is None:
            return "CONT"
        words = struct.unpack_from(f"<{min(len(text) // 2, 8)}H", text)
        label: list[int] = []
        for w in words:
            if w == OPEN_BRACKET:
                s = "".join(self.table.characters.get(x, "?") for x in label).strip("　")
                return LABEL_NAMES.get(s) or ("L" + "_".join(f"{x:04X}" for x in label))
            if w == NARRATION_BRACKET:
                return "NARR"
            if w & 0x8000:
                break
            label.append(w)
        return "CONT"

    # --- decoding one event ----------------------------------------------------------

    def build(self, event: Event) -> Scene:
        """Decode one event into a `Scene`: instructions, text nodes, edges, reachability."""
        sc = Scene(event)
        block = event.block
        header = block.entry(0)
        (k,) = u32s(header, 0, 1)
        if 4 + 2 * k > len(header) or len(header) - (4 + 2 * k) >= 4:
            raise EventError(f"E{event.id:04d} header: count {k}, {len(header)} bytes")
        sc.cast = [(header[4 + 2 * i], header[5 + 2 * i]) for i in range(k)]
        cond_entry = block.entry(1)
        (clen,) = u32s(cond_entry, 0, 1)
        if clen:
            sc.condition, end = parse_cond(cond_entry, 4)
            if end != 4 + clen:
                raise EventError(f"E{event.id:04d} cond: length word {clen}, tree ends at {end}")
        if block.is_stub:
            return sc
        sc.ins = decode_code(block.entry(2))
        sc.rname = self._result_register_name(sc.ins)
        sc.reach = self._reachable(sc)
        sc.slots = defaultdict(set)
        for i in sc.ins.values():
            if i.op == OP_POS:
                sc.slots[i.b[0xC] % 100].add(i.b[0xD])
        named: dict[int, list[int]] = defaultdict(list)
        for p in sorted(sc.ins):
            i = sc.ins[p]
            if i.op in TEXT_OPS:
                mi = i.message_index
                if mi >= sc.message_count:
                    raise EventError(
                        f"E{event.id:04d} {i.name} at {p:#x} names message "
                        f"{mi} of {sc.message_count}"
                    )
                named[mi].append(p)
        sc.named = named
        sc.messages = []
        for mi in range(sc.message_count):
            key = block.message_key(mi)
            sc.messages.append((key[:12] if key else None, block.message_text(mi)))
        self._build_edges(sc)
        sc.mismatches = self._mismatches(sc)
        for p in sorted(sc.ins):
            i = sc.ins[p]
            if i.op == OP_MAP:
                sc.chain.append(("MAP", i.b[2:5].decode("ascii"), s16(i.b, 6), p in sc.reach))
            elif i.op == OP_MOVIE:
                sc.chain.append(
                    (f"MOVIE{s16(i.b, 8)}", i.b[2:5].decode("ascii"), s16(i.b, 6), p in sc.reach)
                )
        return sc

    @staticmethod
    def _result_register_name(ins: dict[int, Ins]) -> str:
        """Name `g_flags[255]` after whoever writes it, when only one kind of writer does."""
        writers = set()
        for i in ins.values():
            if i.op == OP_SELECT:
                writers.add("choice")
            if i.op == OP_PROG:
                writers |= {
                    4: {"day"},
                    6: {"side"},
                    12: {"hour"},
                    14: {"prog14"},
                }.get(s16(i.b, 2), set())
            if i.op == OP_FLAG and s16(i.b, 2) == SEL_FLAG:
                writers.add("R")
        return writers.pop() if len(writers) == 1 else "R"

    @staticmethod
    def _reachable(sc: Scene) -> set[int]:
        seen: set[int] = set()
        stack = [0]
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            for _, t in sc.branch(sc.ins[p]):
                stack.append(t)
        return seen

    def _build_edges(self, sc: Scene) -> None:
        ins = sc.ins
        rn = sc.rname

        def writes(i: Ins) -> tuple[str, int | None] | None:
            """The variable an instruction overwrites -> a constant, or `None` if unknown."""
            if i.op == OP_FLAG:
                return sc.flag_name(s16(i.b, 2)), s16(i.b, 4)
            if i.op == OP_SELECT:
                return rn, None
            if i.op == OP_PROG:
                n = s16(i.b, 2)
                if n in (4, 6, 12, 14):
                    return rn, None
                if n == 9:
                    return sc.flag_name(s16(i.b, 4)), None
                if n == 15:
                    return "flag[1]", None
            if i.op == OP_LFLAG and s16(i.b, 6) == sc.id:
                return "lflag", s16(i.b, 8)
            return None

        def walk(starts, env0=()):
            try:
                return walk1(starts, env0, True)
            except EventError:
                # One event (E4032) has too many independent tests to enumerate. Rather
                # than give up, re-walk reporting only the variables a reader can follow
                # (the result register and the local flag) and `*` for everything else.
                sc.complex = True
                return walk1(starts, env0, False)

        def walk1(starts, env0, track):
            res: dict[Any, set[tuple[str, ...]]] = defaultdict(set)
            stack = [(t, (c,) if c else (), tuple(env0)) for c, t in starts]
            visited: set[tuple] = set()
            while stack:
                p, cs, env = stack.pop()
                if (p, cs, env) in visited:
                    continue
                if len(visited) > 20000:
                    raise EventError(f"E{sc.id:04d}: path explosion")
                visited.add((p, cs, env))
                i = ins[p]
                if sc.is_node(i):
                    res[p].add(cs)
                    continue
                if i.op == OP_END:
                    res["END"].add(cs)
                    continue
                w = writes(i)
                if w:
                    # A rewritten variable becomes a NEW variable from here on (v'), or a
                    # known constant; either way the old constraints on it are dropped.
                    gen = dict(env).get(w[0] + "#", 0) + 1
                    env = (
                        *(x for x in env if x[0] not in (w[0], w[0] + "#")),
                        (w[0] + "#", gen),
                    )
                    if w[1] is not None:
                        env += ((w[0], w[1]),)
                if i.op == OP_JMPE:
                    v = sc.flag_name(s16(i.b, 4))
                    known = dict(env).get(v)
                    if known is not None:
                        taken = i.pc + 2 * s16(i.b, 2) if known >= s16(i.b, 6) else i.end
                        stack.append((taken, cs, env))
                        continue
                for c, t in sc.branch(i):
                    if c and i.op == OP_JMPE:
                        gen = dict(env).get(sc.flag_name(s16(i.b, 4)) + "#", 0)
                        if gen:
                            v0, o0, k0 = _split_cond(c)
                            c = v0 + "'" * gen + o0 + k0
                    if not track and c and _split_cond(c)[0] not in (rn, "lflag"):
                        c = "*"
                    ncs = cs + ((c,) if c and c not in cs else ())
                    if c and c != "*" and not _feasible(ncs):
                        continue
                    if c and c != "*":
                        ncs = tuple(sorted(_simplify(ncs).split(" & ")))
                    stack.append((t, ncs, env))
            return res

        def joined(condition_sets) -> str:
            alts = _merge_alternatives(condition_sets)
            return "" if "" in alts else " | ".join(sorted(alts))

        sc.entry_edges = {d: joined(c) for d, c in walk([(None, 0)]).items()}
        for p in sorted(ins):
            i = ins[p]
            if not sc.is_node(i):
                continue
            nxt = [(None, i.end)]
            if i.op == OP_SELECT:
                lines, first = self.select_shape(i.select_type, i.select_variant)
                options = list(range(lines - first)) + ([CANCEL] if i.select_cancellable else [])
                for v in options:
                    for dst, css in walk(nxt, [(rn, v)]).items():
                        c = joined(css)
                        tag = "cancel" if v == CANCEL else f"opt{v}"
                        sc.edges.append((p, dst, tag + (" & " + c if c else "")))
            else:
                for dst, css in walk(nxt).items():
                    sc.edges.append((p, dst, joined(css)))

    # --- reading one node ---------------------------------------------------------------

    def speaker(self, sc: Scene, p: int) -> tuple[str, int | None]:
        """`(who speaks, mouth-flap slot)` for one node, preferring the inline label.

        Pure, and called several times per node — once per line by the extract, once per
        node by the scene document, once more by `--research-tsv`. The label and the
        operand's slot disagree on a handful of voiced lines (`research/event-scripts.md`
        § Speakers); `_mismatches` collects those once per scene, in `build`.
        """
        i = sc.ins[p]
        if i.op == OP_PROG:
            return NATIVE[s16(i.b, 2)], None
        if i.op in (OP_MAP, OP_MOVIE):
            return "CHAIN", None
        _key, text = sc.messages[i.message_index]
        if i.op == OP_SELECT:
            label = "SELECT"
        elif text:
            label = self.label_of(text)
        else:
            label = "VOICE"
        slot = i.slot if i.op in (OP_XAMSG, OP_XA) else None
        who = self.slot_name(slot) if slot is not None else None
        label = LABEL_ALIASES.get(label, label)
        keep = label in CHARACTERS.values() or label in ("NARR", "BOKU+SHI") or not who
        return (label if keep else who), slot

    def _mismatches(self, sc: Scene) -> list[tuple[str, str, str]]:
        """Nodes whose inline label names someone other than the actor slot's character.

        Authoring slips in the operand, so the label wins; the list is what says how many
        there were, and `index.json` carries the total.
        """
        out = []
        for p in sorted(sc.ins):
            i = sc.ins[p]
            if i.op not in (OP_XAMSG, OP_XA):
                continue
            _key, text = sc.messages[i.message_index]
            label = self.label_of(text) if text else "VOICE"
            who = self.slot_name(i.slot)
            if (
                who
                and label in CHARACTERS.values()
                and LABEL_ALIASES.get(label, label) != who
                and "+" not in who
                and who != "ALL"
            ):
                out.append((sc.node_id(p), label, who))
        return out

    def when(self, sc: Scene) -> tuple[int | None, int | None]:
        """`(day, meal hour)` — the parts of the firing condition that are in the id.

        `id / 100` is the day for ids below 4000 unless the tree carries its own day
        node; in map `G02` the last digits name a meal slot (`research/event-scripts.md`).
        """
        dd, r = divmod(sc.id, 100)
        day = dd if 1 <= dd < 40 and not (sc.condition and uses_day(sc.condition)) else None
        meal = None
        if dd < 40 and sc.id >= 5:
            meal = {1: 7, 2: 8, 3: 18, 4: 19}.get(r) if dd else None
            meal = {6: 7, 7: 8, 9: 18, 10: 19}.get(sc.id, meal)
        if sc.id == 705:
            meal = 19
        return day, meal

    def voice_key(self, raw: bytes | None) -> dict[str, int] | None:
        """The 12-byte clip key: `{u32 start, u32 end, u8 channel, u8 file, u16 0}`."""
        if raw is None:
            return None
        start, end, channel, file_no, _pad = struct.unpack("<IIBBH", raw)
        return {"start": start, "end": end, "channel": channel, "file": file_no}

    def dinner_quiz(self, sc: Scene) -> dict[str, Any] | None:
        """The day -> message-index mapping for the two natively indexed routines.

        `PROG 15` (the aunt's "guess tonight's dinner" quiz) opens select `day + 1`, and 0
        on day 15; `PROG 16` opens message `g_dinner_menu[day - 1] + 7`. Both tables are
        read out of the executable here, so a wrong day mapping is a wrong disc, not a
        wrong transcription.
        """
        natives = {s16(i.b, 2) for i in sc.ins.values() if i.op == OP_PROG} & set(NATIVE)
        if not natives:
            return None
        out: dict[str, Any] = {"routines": sorted(natives)}
        if 15 in natives:
            out["quiz"] = [
                {
                    "day": day,
                    "message": 0 if day == 15 else day + 1,
                    "answer": self.dinner_answer[day - 1],
                }
                for day in range(1, DAYS_IN_AUGUST + 1)
            ]
        if 16 in natives:
            out["menu"] = [
                {"day": day, "message": self.dinner_menu[day - 1] + 7}
                for day in range(1, DAYS_IN_AUGUST + 1)
            ]
        return out
