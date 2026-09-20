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


def read_exe_dir(exe: bytes) -> list[DirEntry]:
    """`g_cd_dir`'s three parallel arrays, located from the count word that follows them.

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
    names = struct.unpack_from(f"<{count}I", exe, off - 4 * count)
    sizes = struct.unpack_from(f"<{count}I", exe, off - 8 * count)
    lbas = struct.unpack_from(f"<{count}I", exe, off - 12 * count)
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
        return BOKU_BIN_LBA + self.offset // SECTOR

    @property
    def sector_slack(self) -> int:
        """Free bytes from the member's size to its last sector's end (`PIPE-03`'s head room)."""
        return (-self.size) % SECTOR


def build_members(exe: bytes, boku: bytes) -> tuple[list[Member], list[str]]:
    """Leaf members in archive order, plus every tiling problem found (empty = perfect).

    The tiling check is the gate: each member must start where the previous one's last
    sector ended, at both levels, and the records of a `.SEC` must end exactly on the
    container's last sector. A directory that has drifted from the archive shows up here
    rather than as a mis-aimed write later.
    """
    problems: list[str] = []
    entries = read_exe_dir(exe)
    total = len(boku) // SECTOR
    inside = [e for e in entries if BOKU_BIN_LBA <= e.lba < BOKU_BIN_LBA + total]
    by_name = {e.name.rsplit("\\", 1)[-1]: e for e in inside}
    out: list[Member] = []

    def blob(e: DirEntry) -> bytes:
        o = (e.lba - BOKU_BIN_LBA) * SECTOR
        return boku[o : o + e.size]

    pos = 0
    for e in inside:
        rel = e.lba - BOKU_BIN_LBA
        if rel != pos:
            problems.append(f"top-level: {e.name} starts at sector {rel}, expected {pos}")
        pos = rel + e.sectors
        short = e.name.rsplit("\\", 1)[-1]
        if short in SUB_ARCHIVES:
            sec_name, parse = SUB_ARCHIVES[short]
            recs = parse(blob(by_name[sec_name])).records
            sub_pos = 0
            for i, r in enumerate(recs):
                if r.sector != sub_pos:
                    problems.append(f"{short}: {r.key} at sector {r.sector}, expected {sub_pos}")
                sub_pos = r.sector + (r.size + SECTOR - 1) // SECTOR
                out.append(
                    Member(e.index, i, f"{e.name}\\{r.key}", (rel + r.sector) * SECTOR, r.size)
                )
            if sub_pos != e.sectors:
                problems.append(
                    f"{short}: records end at sector {sub_pos}, container has {e.sectors}"
                )
        else:
            out.append(
                Member(
                    e.index,
                    None,
                    e.name,
                    rel * SECTOR,
                    e.size,
                    is_directory_placeholder="." not in short,
                )
            )
    if pos != total:
        problems.append(f"top-level ends at sector {pos}, {ARCHIVE_NAME} has {total}")
    return out, problems


# --- the import, opened ------------------------------------------------------------------

DEFAULT_DISC_DIR = Path("disc")
"""Where `boku import` puts its output. Everything under it is gitignored."""


class Archive:
    """The two files the import writes, plus the member map derived from them.

    Everything downstream addresses bytes through this object, so there is one place that
    knows the archive is `BOKU.BIN` with a directory in `SCPS_100.88` and one place that
    refuses an import whose tiling does not check out.
    """

    def __init__(
        self,
        disc_dir: Path = DEFAULT_DISC_DIR,
        *,
        exe: bytes | None = None,
        boku: bytes | None = None,
        source: str | None = None,
    ) -> None:
        """Open an import. `exe`/`boku` supply the two files directly (`from_bytes`).

        One constructor, so an archive built over bytes is the same object as one built
        over a directory — every attribute either kind has, both kinds have.
        """
        self.disc_dir = Path(disc_dir)
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
        self.members, self.problems = build_members(self.exe, self.boku)
        self._by_short: dict[str, Member] = {}
        for m in self.members:
            if m.short_name in self._by_short:
                raise ArchiveError(f"two members are named {m.short_name}")
            self._by_short[m.short_name] = m
        self._starts = [m.offset for m in self.members]

    @classmethod
    def from_bytes(cls, exe: bytes, boku: bytes, source: str = "<bytes>") -> Archive:
        """The same archive over two byte strings rather than two files on disk.

        What `PIPE-05`'s round-trip gate reads a *built image* back through: the two files
        come out of the image with `DiscImage.read_file`, and everything downstream — the
        member map, the structural walk, the line ids — then works on the build's own
        output exactly as it works on the import. `source` only names them in messages.
        """
        return cls(exe=exe, boku=boku, source=source)

    def require_clean(self) -> None:
        """Refuse an archive whose members do not tile it exactly."""
        if self.problems:
            raise ArchiveError(
                f"{self.source} does not tile: {self.problems[0]} ({len(self.problems)} problems)"
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
        m = self.members[bisect_right(self._starts, offset) - 1]
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
