"""`BOKU.BIN`, its directory in the executable, and the member map (`research/boku-bin.md`).

`BOKU.BIN` is a raw copy of a sector range of the developers' CD image, and nothing inside
it says where anything is: the directory is three parallel arrays compiled into
`SCPS_100.88`, indexed by a file number the game holds as a compile-time constant. Four of
the members are themselves sector-granular sub-archives with a sibling `.SEC` index.

This module is the executable form of that note. It reads only the two files the import
step writes (`disc/files/SCPS_100.88` and `disc/files/BOKU.BIN`) and hands the rest of the
package a flat list of leaf members with byte offsets into the archive.

Every container parsed here can be handed back: `SubArchiveIndex` and `Pack` keep the
fields and the pad bytes their parsers would otherwise drop, and `serialise` rebuilds the
blob from the parsed parts. `PIPE-03` rewrites these tables when a translation grows, and
`tests/test_real_extract.py`'s identity gate is what says the reading loses nothing.

The scratch original is `work/rec01/build_map.py` + `exe_dir.py` + `formats.py`; this port
reproduces `research/data/boku-bin-members.tsv` byte for byte (`boku.research`).
"""

from __future__ import annotations

import math
import re
import struct
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from boku.edc import FORM1_DATA_SIZE
from boku.tim import parse as parse_tim

SECTOR = FORM1_DATA_SIZE
"""A Mode 2 Form 1 user-data sector, which is the unit `BOKU.BIN` is built out of. It is
the same 2,048 bytes `boku.edc` computes a sector's EDC over, so it is named there once."""

BOKU_BIN_LBA = 1046
"""Where `BOKU.BIN` sits on the retail disc — and where `\\_DATA` sat on the dev image."""

EXE_LOAD_BIAS = 0x8000F800
"""RAM address = `SCPS_100.88` file offset + this. The executable is identity-loaded."""

OVERLAY_LOAD_ADDRESS = 0x80079A08
"""Where every `.OVL` member loads (`research/text-format.md`; hypothesis for three of them)."""

DIR_COUNT_ADDR = 0x80024698
"""`g_cd_dir.count`. The three arrays are found from it, never by their own addresses."""

EXE_NAME = "SCPS_100.88"
ARCHIVE_NAME = "BOKU.BIN"

EV_DIR_INDEX = 29
"""`EV.BIN`, the event-script sub-archive."""
MAP_DIR_INDEX = 143
"""`M_FILES.BIN`, the map packs."""


class ArchiveError(Exception):
    """The import does not look like SCPS-10088's archive."""


# --- the directory compiled into the executable ----------------------------------------


@dataclass(frozen=True)
class DirEntry:
    """One file number of `g_cd_dir`: a dev-time path, an absolute LBA and a byte size."""

    index: int
    name: str
    lba: int
    size: int

    @property
    def sectors(self) -> int:
        return (self.size + SECTOR - 1) // SECTOR


@dataclass(frozen=True)
class DirArrays:
    """Where `g_cd_dir`'s three arrays start in the executable's own bytes.

    `PIPE-03` writes `lba[i]` and `size[i]` when a member moves, so it needs the byte
    offsets and not only the values `read_exe_dir` decodes from them.
    """

    count: int
    lba: int
    size: int
    name: int

    def lba_offset(self, index: int) -> int:
        return self.lba + 4 * index

    def size_offset(self, index: int) -> int:
        return self.size + 4 * index


def dir_arrays(exe: bytes) -> DirArrays:
    """Locate `g_cd_dir`'s three parallel arrays from the count word that follows them.

    The count sits immediately after `name[]`, which follows `size[]`, which follows
    `lba[]` — so one address finds all three, and a rebuilt executable that moved them
    would be read correctly rather than silently mis-parsed at a stale address.
    """
    off = DIR_COUNT_ADDR - EXE_LOAD_BIAS
    if off + 4 > len(exe):
        raise ArchiveError(f"{EXE_NAME} is {len(exe)} bytes: too short to hold g_cd_dir")
    (count,) = struct.unpack_from("<I", exe, off)
    if not 1 <= count <= 4096 or off - 12 * count < 0:
        raise ArchiveError(f"g_cd_dir says {count} files; that is not this game's directory")
    return DirArrays(count, off - 12 * count, off - 8 * count, off - 4 * count)


def read_exe_dir(exe: bytes) -> list[DirEntry]:
    """`g_cd_dir` as a list of entries: a dev-time path, an absolute LBA and a size."""
    arrays = dir_arrays(exe)
    count = arrays.count
    names = struct.unpack_from(f"<{count}I", exe, arrays.name)
    sizes = struct.unpack_from(f"<{count}I", exe, arrays.size)
    lbas = struct.unpack_from(f"<{count}I", exe, arrays.lba)
    out = []
    for i in range(count):
        start = names[i] - EXE_LOAD_BIAS
        if not 0 <= start < len(exe):
            raise ArchiveError(f"g_cd_dir_name[{i}] points outside the executable")
        name = exe[start : exe.index(b"\0", start)].decode("ascii")
        out.append(DirEntry(i, name, lbas[i], sizes[i]))
    return out


# --- the four sub-archives and their `.SEC` indexes ------------------------------------


@dataclass(frozen=True)
class SubRecord:
    """One record of a `.SEC` index: the dev-time name, a relative sector and a byte size.

    The fields after `size` are what the record holds and our name does not: the event or
    model id it is keyed by, `M_FILES.SEC`'s 8-byte name field *with its padding*, and
    that record's trailing `u16`. They exist so a rebuilt index is byte-identical rather
    than a re-parse of the string we rendered.
    """

    key: str
    sector: int
    size: int
    ident: int = 0
    """`EV.SEC`/`NIKKI.SEC`'s id, or `H_FILES.SEC`'s model id. Unused by `M_FILES.SEC`."""
    variant: int = 0
    """`H_FILES.SEC`'s `vr`."""
    name_field: bytes = b""
    """`M_FILES.SEC`'s `char name[8]`, NUL padding included."""
    junk: int = 0
    """`M_FILES.SEC`'s trailing `u16`: build-tool stack garbage. `map_select` reads the
    record with `lhu` and never touches it, but a rebuilt index has to carry it back."""


@dataclass(frozen=True)
class SubArchiveIndex:
    """A whole `.SEC` member: its records and whatever pad follows the last of them."""

    kind: str
    """`"EV"`, `"NIKKI"`, `"H"` or `"M"` — which of the four record layouts this is."""
    records: tuple[SubRecord, ...]
    tail: bytes
    """Bytes after the last record inside the `.SEC` member."""

    def serialise(self) -> bytes:
        """The index's own bytes, rebuilt from the records (the `PIPE-03` identity gate)."""
        pack = _SEC_PACKERS[self.kind]
        return (
            len(self.records).to_bytes(4, "little")
            + b"".join(pack(r) for r in self.records)
            + self.tail
        )


def _parse_sec(kind: str, b: bytes, record_size: int, make) -> SubArchiveIndex:
    (n,) = struct.unpack_from("<I", b)
    records = tuple(
        make(struct.unpack_from(_SEC_FORMATS[kind], b, 4 + record_size * i)) for i in range(n)
    )
    return SubArchiveIndex(kind, records, b[4 + record_size * n :])


_SEC_FORMATS = {"EV": "<HHH", "NIKKI": "<HHH", "H": "<BBHI", "M": "<8sIHH"}


def parse_sec_ev(b: bytes) -> SubArchiveIndex:
    """`EV.SEC`: `u32 count; count * {u16 event_id, u16 size, u16 sector}`."""
    return _parse_sec(
        "EV",
        b,
        6,
        lambda f: SubRecord(f"EV{f[0]:04d}.BIN", f[2], f[1], ident=f[0]),
    )


def parse_sec_nikki(b: bytes) -> SubArchiveIndex:
    """`NIKKI.SEC`: the same shape as `EV.SEC`. `NIKKI_%03d` is our name, not the game's."""
    return _parse_sec(
        "NIKKI",
        b,
        6,
        lambda f: SubRecord(f"NIKKI_{f[0]:03d}", f[2], f[1], ident=f[0]),
    )


def parse_sec_h(b: bytes) -> SubArchiveIndex:
    """`H_FILES.SEC`: `u32 count; count * {u8 id, u8 vr, u16 sector, u32 size}`."""
    return _parse_sec(
        "H",
        b,
        8,
        lambda f: SubRecord(f"H_{f[0]:02d}_{f[1]:02d}.BIN", f[2], f[3], ident=f[0], variant=f[1]),
    )


def parse_sec_m(b: bytes) -> SubArchiveIndex:
    """`M_FILES.SEC`: `u32 count; count * {char name[8], u32 size, u16 sector, u16 junk}`."""
    return _parse_sec(
        "M",
        b,
        16,
        lambda f: SubRecord(
            f"M_{f[0].split(b'\0')[0].decode('ascii')}.BIN",
            f[2],
            f[1],
            name_field=f[0],
            junk=f[3],
        ),
    )


_SEC_PACKERS = {
    "EV": lambda r: struct.pack("<HHH", r.ident, r.size, r.sector),
    "NIKKI": lambda r: struct.pack("<HHH", r.ident, r.size, r.sector),
    "H": lambda r: struct.pack("<BBHI", r.ident, r.variant, r.sector, r.size),
    "M": lambda r: struct.pack("<8sIHH", r.name_field, r.size, r.sector, r.junk),
}

SUB_ARCHIVES: dict[str, tuple[str, object]] = {
    "EV.BIN": ("EV.SEC", parse_sec_ev),
    "H_FILES.BIN": ("H_FILES.SEC", parse_sec_h),
    "M_FILES.BIN": ("M_FILES.SEC", parse_sec_m),
    "NIKKI.BIN": ("NIKKI.SEC", parse_sec_nikki),
}
"""Container member -> (its `.SEC` index member, the parser for that index's records)."""


# --- the family pack container, and type sniffing --------------------------------------


@dataclass(frozen=True)
class Pack:
    """A family pack, kept in a form that can be written back out.

    `entries` is what every reader here wants — `(offset, size)` per child, `(0, 0)` for
    an absent one. `children`, `gaps` and `tail` are what re-serialising needs: the child
    bytes, the 0-3 byte alignment pad that follows each live child, and the pad between
    the last child and the blob's end.
    """

    entries: tuple[tuple[int, int], ...]
    children: tuple[bytes | None, ...]
    gaps: tuple[bytes, ...]
    tail: bytes

    def serialise(self) -> bytes:
        """The pack's own bytes, with every offset recomputed from the children's lengths."""
        table = b""
        body = b""
        pos = 4 + 8 * len(self.children)
        for child, gap in zip(self.children, self.gaps, strict=True):
            if child is None:
                table += struct.pack("<II", 0, 0)
                continue
            pos += len(gap)
            body += gap + child
            table += struct.pack("<II", pos, len(child))
            pos += len(child)
        return len(self.children).to_bytes(4, "little") + table + body + self.tail


def parse_pack(b: bytes) -> Pack | None:
    """Family pack: `u32 count, count * {u32 offset, u32 size}`, offsets from the start.

    The chain is checked, not assumed: the first offset is the header's own end, each
    offset is the previous member's end rounded up to 4, and the last end covers the blob.
    A `{0, 0}` entry is an absent member. `None` means "not a pack" — the sniffing here
    has to reject far more blobs than it accepts.
    """
    if len(b) < 12:
        return None
    (n,) = struct.unpack_from("<I", b)
    if not 1 <= n <= 4096 or 4 + 8 * n > len(b):
        return None
    ents = [struct.unpack_from("<II", b, 4 + 8 * i) for i in range(n)]
    pos = 4 + 8 * n
    children: list[bytes | None] = []
    gaps: list[bytes] = []
    for off, size in ents:
        if off == 0 and size == 0:
            children.append(None)
            gaps.append(b"")
            continue
        if off != pos and off != (pos + 3) & ~3:
            return None
        gaps.append(b[pos:off])
        children.append(b[off : off + size])
        pos = off + size
        if pos > len(b):
            return None
    if (pos + 3) & ~3 != (len(b) + 3) & ~3:
        return None
    if all(e == (0, 0) for e in ents):
        return None
    return Pack(tuple(ents), tuple(children), tuple(gaps), b[pos:])


def parse_offtab(b: bytes) -> list[int] | None:
    """Offset-only table: `u32 count, count * u32 offset` from the table start, 0 = null."""
    if len(b) < 8:
        return None
    (n,) = struct.unpack_from("<I", b)
    if not 1 <= n <= 4096 or 4 + 4 * n > len(b):
        return None
    offs = list(struct.unpack_from(f"<{n}I", b, 4))
    live = [o for o in offs if o]
    if not live or live[0] != 4 + 4 * n or live != sorted(live) or live[-1] >= len(b):
        return None
    return offs


def tim_length(b: bytes, o: int = 0) -> int | None:
    """Byte length of a PsyQ TIM at `b[o:]`, or `None` if that is not a TIM.

    `boku.tim.parse` is the one acceptance test for the format — this used to be a looser
    second one, and the two disagreed about 62 four-aligned candidates whose CLUT block
    declares no palette at all. `boku.sites` answers "is this scan hit inside a texture?"
    with this function, so each disagreement was a fictitious span explaining away real
    sites; `boku.research` counted them as TIMs in the member map.
    """
    tim = parse_tim(b, o)
    return tim.length if tim is not None else None


def entropy(b: bytes) -> float:
    """Shannon entropy in bits per byte. `research/boku-bin.md` uses it to rule out packing."""
    if not b:
        return 0.0
    counts = [0] * 256
    for x in b:
        counts[x] += 1
    n = len(b)
    return -sum(c / n * math.log2(c / n) for c in counts if c)


def is_mips_code(b: bytes) -> bool:
    """Crude but sufficient: many `jr ra` words and many `addiu sp, sp, imm` halfwords."""
    jr = b.count(b"\x08\x00\xe0\x03")
    sp = b.count(b"\xbd\x27")
    return jr >= 4 and sp >= 8 and jr * 3000 > len(b)


def sniff(b: bytes) -> str:
    """A one-word guess at a blob's format, for the member map's `signature` column."""
    if not any(b):
        return "zero"
    if b[:4] == b"pBAV":
        return "VAB"
    if b[:4] == b"pQES":
        return "SEQ"
    if b[12:16] in (b"SShd", b"SSsq"):  # Sony sound header / sequence, magic at +0xC
        return b[12:16].decode()
    if tim_length(b) is not None:
        return "TIM"
    if is_mips_code(b):
        return "code"
    pk = parse_pack(b)
    if pk is not None:
        return f"pack[{len(pk.entries)}]"
    ot = parse_offtab(b)
    if ot is not None:
        return f"offtab[{len(ot)}]"
    if len(b) >= 4 and struct.unpack_from("<I", b)[0] == 0x41:
        return "TMD?"
    if len(b) >= 4 and struct.unpack_from("<I", b)[0] == 0x50:
        return "HMD?"
    return "unknown"


def pack_signature(b: bytes, depth: int = 0) -> str:
    """`sniff`, recursing into packs, so `pack[2]{TIM unknown}` describes a whole member."""
    t = sniff(b)
    if t.startswith("pack") and depth < 4:
        kids = Counter(
            pack_signature(b[o : o + s], depth + 1) if s else "null"
            for o, s in parse_pack(b).entries
        )
        return t + "{" + " ".join(f"{k}x{v}" if v > 1 else k for k, v in sorted(kids.items())) + "}"
    return t


def coarse_type(name: str, signature: str) -> str:
    """The member map's `type` column: the signature plus what the dev-time name says."""
    ext = name.rsplit(".", 1)[-1] if "." in name.rsplit("\\", 1)[-1] else ""
    if signature == "iso-directory-placeholder":
        return signature
    if ext == "SEC":
        return "sub-archive index"
    if ext == "OVL" or signature == "code":
        return "code overlay"
    if "SShd" in signature or "SSsq" in signature:
        return "sound pack (SShd/SSsq + body)"
    if "\\EV.BIN\\" in name:
        return "event script (offset table)"
    if "\\M_FILES.BIN\\" in name:
        return "map pack"
    if "\\H_FILES.BIN\\" in name:
        return "model pack"
    if signature == "TIM":
        return "TIM"
    if signature.startswith("pack"):
        kinds = set(re.findall(r"[A-Za-z?]+", signature)) - {"pack", "x", "null"}
        return "pack of TIM" if kinds == {"TIM"} else "pack"
    return signature


def zero_sector_notes(b: bytes) -> str:
    """Which pack leaf each all-zero sector of a member starts in, for the map's `notes`."""
    spans: list[tuple[int, int, str]] = []

    def walk(x: bytes, base: int, path: str, depth: int = 0) -> None:
        pk = parse_pack(x) if depth < 6 else None
        if pk is None:
            spans.append((base, base + len(x), f"{path or '/'}:{sniff(x)}"))
            return
        for i, (o, s) in enumerate(pk.entries):
            if s:
                walk(x[o : o + s], base + o, f"{path}/{i}", depth + 1)

    walk(b, 0, "")
    hits: Counter[str] = Counter()
    for s in range(0, len(b), SECTOR):
        if not any(b[s : s + SECTOR]):
            hits[next((lab for a, e, lab in spans if a <= s < e), "pack header")] += 1
    return ", ".join(f"zero sector in {k}" + (f" x{v}" if v > 1 else "") for k, v in hits.items())


# --- the member map ---------------------------------------------------------------------


@dataclass(frozen=True)
class Member:
    """One leaf of the archive: a plain top-level file, or one record of a sub-archive.

    Frozen on purpose: `Archive.members` is shared by every walk in the package, and the
    measurements the member map reports (entropy, TIM counts, text-line counts) are a
    report's rows, not the archive's state — they live in `boku.research.MemberStats`.
    """

    dir_index: int
    """Index in `g_cd_dir`. 29 is `EV.BIN`, 143 `M_FILES.BIN`."""
    sub_index: int | None
    """Record number inside the container's `.SEC`, or `None` for a plain member."""
    name: str
    """The dev-time path, e.g. `\\_DATA\\M_FILES.BIN\\M_A01000.BIN`."""
    offset: int
    """Byte offset inside `BOKU.BIN`."""
    size: int
    is_directory_placeholder: bool = False
    """A `g_cd_dir` entry whose dev-time name has no extension: an ISO directory, not a file."""
    base_lba: int = BOKU_BIN_LBA
    """The disc LBA `offset` counts from. `BOKU.BIN`'s own start unless the archive was
    read back over the filler before it, which is where `PIPE-03` relocates members to."""

    @property
    def short_name(self) -> str:
        """The leaf name: `M_A01000.BIN`, which is unique across all 1,302 members."""
        return self.name.rsplit("\\", 1)[-1]

    @property
    def sectors(self) -> int:
        return (self.size + SECTOR - 1) // SECTOR

    @property
    def end_sector(self) -> int:
        return self.offset // SECTOR + self.sectors

    @property
    def lba(self) -> int:
        return self.base_lba + self.offset // SECTOR

    @property
    def sector_slack(self) -> int:
        """Free bytes from the member's size to its last sector's end (`PIPE-03`'s head room)."""
        return (-self.size) % SECTOR


def build_members(
    exe: bytes, boku: bytes, base_lba: int = BOKU_BIN_LBA
) -> tuple[list[Member], list[str], list[tuple[int, int]]]:
    """Leaf members in directory order, the problems found, and the sectors nobody claims.

    A **problem** is an inconsistency: a member that runs off the end of the bytes read,
    two members whose sectors overlap, a `.SEC`'s records out of order, or live bytes no
    member claims. Each means the directory has drifted from the archive, and finding it
    here is what keeps a later write from being mis-aimed.

    A **gap** is a run of sectors no member covers, reported as `(lba, sectors)`. The
    retail archive has none — it tiles exactly — but `PIPE-03` relocates a member that has
    outgrown its sectors and **zeroes the ones it leaves**, so a gap is the normal shape of
    a built image and is not a problem *as long as it is zero*.

    Coverage alone is weaker than the exact tiling this used to require, and in one way
    that matters: coverage is invariant under a *permutation*. Two equal-sized records of
    one `.SEC` with their `sector` fields swapped still cover every sector exactly once,
    and a rebuild would then write one map's English into the other's bytes.
    `_record_order` restores that for every container a re-layout has left tiling, which
    is the shape a permutation has; a container the re-layout did re-lay out is guarded at
    plan time instead, by `boku.relocate.check_placements`.
    """
    problems: list[str] = []
    entries = read_exe_dir(exe)
    total = len(boku) // SECTOR
    inside = [e for e in entries if base_lba <= e.lba < base_lba + total]
    by_name = {e.name.rsplit("\\", 1)[-1]: e for e in inside}
    out: list[Member] = []

    def blob(e: DirEntry) -> bytes:
        o = (e.lba - base_lba) * SECTOR
        return boku[o : o + e.size]

    def member(index: int, sub: int | None, name: str, lba: int, size: int) -> Member:
        return Member(
            index,
            sub,
            name,
            (lba - base_lba) * SECTOR,
            size,
            is_directory_placeholder=sub is None and "." not in name.rsplit("\\", 1)[-1],
            base_lba=base_lba,
        )

    for e in inside:
        short = e.name.rsplit("\\", 1)[-1]
        if short in SUB_ARCHIVES:
            sec_name, parse = SUB_ARCHIVES[short]
            for i, r in enumerate(parse(blob(by_name[sec_name])).records):
                out.append(member(e.index, i, f"{e.name}\\{r.key}", e.lba + r.sector, r.size))
        else:
            out.append(member(e.index, None, e.name, e.lba, e.size))

    by_index = {e.index: e for e in inside}
    for index in {m.dir_index for m in out if m.sub_index is not None}:
        problems += _record_order(
            by_index[index],
            [m for m in out if m.dir_index == index and m.sub_index is not None],
        )

    covered = bytearray(total)
    for m in sorted(out, key=lambda m: m.offset):
        first = m.offset // SECTOR
        if m.offset < 0 or first + m.sectors > total:
            problems.append(
                f"{m.short_name} spans sectors {first}..{first + m.sectors - 1} of an "
                f"archive that has {total}"
            )
            continue
        for s in range(first, first + m.sectors):
            if covered[s]:
                problems.append(f"{m.short_name} overlaps another member at sector {s}")
                break
            covered[s] = 1
    gaps: list[tuple[int, int]] = []
    s = 0
    while s < total:
        if covered[s]:
            s += 1
            continue
        end = s
        while end < total and not covered[end]:
            end += 1
        gaps.append((base_lba + s, end - s))
        if any(boku[s * SECTOR : end * SECTOR]):
            problems.append(
                f"sectors {base_lba + s}..{base_lba + end - 1} belong to no member and are "
                f"not zero: the directory has drifted from the archive, or a member was "
                f"moved without its old sectors being cleared"
            )
        s = end
    return out, problems, gaps


def _record_order(container: DirEntry, members: list[Member]) -> list[str]:
    """Problems with one `.SEC`'s records: a member that went backwards without leaving.

    The retail invariant is that record order *is* sector order, and coverage alone cannot
    see it broken: two equal-sized records with their `sector` fields exchanged still tile
    the container exactly, and a rebuild would then write one map's English into the
    other's bytes.

    A re-layout breaks that invariant legitimately: a member written into the run another
    record of the same container vacated is behind its neighbours for a good reason, and
    nothing in the finished image tells that apart from a permutation — once records may be
    written into each other's holes, sector order carries no information about record order
    at all. Keeping the ordering rule instead was measured and refused: with it, every
    member that grows is confined to the space its record-order neighbours leave it, and a
    whole translation asks the arena for 11,141 sectors rather than 456
    (`research/relocation.md` § "Does it fit?").

    So the rule is applied where it can still decide: **a container whose members still
    fill its own `g_cd_dir` extent, exactly, must have them in record order.** That is the
    retail shape, and it is every build that moved nothing in this container —
    `g_cd_dir.size[container]` is deliberately never rewritten
    (`boku.reinsert.directory_edits`), so the extent stays the retail one and a re-layout,
    which only ever happens because a member grew, can no longer fill it. The permutation
    this check exists for *does* leave the extent exactly filled, which is why it is still
    caught here. A container that no longer fills it has been re-laid out, and what guards
    that is named in `boku.relocate`'s module docstring.

    "Fills it exactly" is three sums rather than a sort: the members' sectors add up to the
    extent's, and they start and end on it. Overlapping members could satisfy that, but
    they are a problem `build_members` reports in its own right, and the only cost is
    running this check on an archive that is already being refused.
    """
    if not members:
        return []
    if (
        sum(m.sectors for m in members) != container.sectors
        or min(m.lba for m in members) != container.lba
        or max(m.lba + m.sectors for m in members) != container.lba + container.sectors
    ):
        return []
    problems: list[str] = []
    position = 0
    for member in sorted(members, key=lambda m: m.sub_index or 0):
        if member.lba < position:
            problems.append(
                f"{member.short_name} is record {member.sub_index} and starts at LBA "
                f"{member.lba}, behind record {member.sub_index - 1 if member.sub_index else 0}"
                f" which ends at {position}: the .SEC's records have been reordered"
            )
            continue
        position = member.lba + member.sectors
    return problems


# --- the import, opened ------------------------------------------------------------------

DEFAULT_DISC_DIR = Path("disc")
"""Where `boku import` puts its output. Everything under it is gitignored."""


class Archive:
    """The two files the import writes, plus the member map derived from them.

    Everything downstream addresses bytes through this object, so there is one place that
    knows the archive is `BOKU.BIN` with a directory in `SCPS_100.88` and one place that
    refuses an import whose directory disagrees with its bytes.
    """

    def __init__(
        self,
        disc_dir: Path = DEFAULT_DISC_DIR,
        *,
        exe: bytes | None = None,
        boku: bytes | None = None,
        source: str | None = None,
        base_lba: int = BOKU_BIN_LBA,
    ) -> None:
        """Open an import. `exe`/`boku` supply the two files directly (`from_bytes`).

        One constructor, so an archive built over bytes is the same object as one built
        over a directory — every attribute either kind has, both kinds have.
        """
        self.disc_dir = Path(disc_dir)
        self.base_lba = base_lba
        """The disc LBA the `boku` bytes start at. `BOKU.BIN`'s own 1046 for an import;
        lower for an archive read back over the filler `PIPE-03` relocates members into."""
        files = self.disc_dir / "files"
        self.exe_path = files / EXE_NAME
        self.archive_path = files / ARCHIVE_NAME
        self.source = source or str(self.disc_dir)
        """What a message calls this import. For an archive read out of a built image
        there is no `disc/files/` to name, and naming one that is not there sends the
        reader looking for a file nobody wrote."""
        if exe is None or boku is None:
            for path in (self.exe_path, self.archive_path):
                if not path.is_file():
                    raise ArchiveError(
                        f"{path} is not there: run `./make.sh import` to write your own "
                        f"import. The repo ships none of the game."
                    )
            self.exe = self.exe_path.read_bytes()
            self.boku = self.archive_path.read_bytes()
        else:
            self.exe, self.boku = exe, boku
        self._index()

    def _index(self) -> None:
        # `gaps` is the sectors no member claims, `(lba, sectors)` -- empty on the retail
        # archive, and where a relocated member's old sectors show up on a built one.
        self.members, self.problems, self.gaps = build_members(self.exe, self.boku, self.base_lba)
        self._by_short: dict[str, Member] = {}
        for m in self.members:
            if m.short_name in self._by_short:
                raise ArchiveError(f"two members are named {m.short_name}")
            self._by_short[m.short_name] = m
        self._ordered = sorted(self.members, key=lambda m: m.offset)
        self._starts = [m.offset for m in self._ordered]

    @classmethod
    def from_bytes(
        cls, exe: bytes, boku: bytes, source: str = "<bytes>", base_lba: int = BOKU_BIN_LBA
    ) -> Archive:
        """The same archive over two byte strings rather than two files on disk.

        What `PIPE-05`'s round-trip gate reads a *built image* back through: the two files
        come out of the image with `DiscImage.read_file`, and everything downstream — the
        member map, the structural walk, the line ids — then works on the build's own
        output exactly as it works on the import. `source` only names them in messages.
        """
        return cls(exe=exe, boku=boku, source=source, base_lba=base_lba)

    def require_clean(self) -> None:
        """Refuse an archive whose members overlap or run off its end.

        Not a tiling check any more: a relocated member leaves a hole (`build_members`),
        and a hole is reported as a gap. What is refused is a directory that disagrees
        with the bytes — which is what would mis-aim a write.
        """
        if self.problems:
            raise ArchiveError(
                f"{self.source}'s directory disagrees with its bytes: {self.problems[0]} "
                f"({len(self.problems)} problems)"
            )

    def member(self, short_name: str) -> Member:
        try:
            return self._by_short[short_name]
        except KeyError:
            raise ArchiveError(f"{self.source} has no member {short_name}") from None

    def blob(self, member: Member) -> bytes:
        return self.boku[member.offset : member.offset + member.size]

    def owner(self, offset: int) -> Member | None:
        """The member whose bytes cover `offset`, or `None` if it falls in sector padding."""
        index = bisect_right(self._starts, offset) - 1
        if index < 0:
            return None
        m = self._ordered[index]
        return m if offset < m.offset + m.size else None

    def exe_bytes(self, ram: int, n: int) -> bytes:
        """`n` bytes of the executable at a RAM address."""
        return self.exe[ram - EXE_LOAD_BIAS : ram - EXE_LOAD_BIAS + n]

    def overlay_bytes(self, short_name: str, ram: int, n: int) -> bytes:
        """`n` bytes of an overlay at the RAM address it has once loaded."""
        b = self.blob(self.member(short_name))
        return b[ram - OVERLAY_LOAD_ADDRESS : ram - OVERLAY_LOAD_ADDRESS + n]

    def image_bytes(self, image: str, ram: int, n: int) -> bytes:
        """`n` bytes of `"exe"` or of an overlay named by its lowercase stem (`"hhon"`)."""
        if image == "exe":
            return self.exe_bytes(ram, n)
        return self.overlay_bytes(f"{image.upper()}.OVL", ram, n)
