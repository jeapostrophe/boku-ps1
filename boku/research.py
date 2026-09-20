"""Regenerate the five tracked research tables from the package's own walks.

`research/data/*.tsv` were produced by independent scratch scripts (`work/rec01`,
`work/rec03`, `work/rec05`, `work/rec06`) while the formats were being decoded. This
module writes the same five tables out of `boku.archive`, `boku.events`, `boku.arrays` and
`boku.sites`, and a test diffs them against the tracked copies.

That is the gate on the port: two independent implementations of the same reading agreeing
byte for byte over 12,000 rows is evidence neither is inventing anything. The tables carry
no text — ids, offsets, sizes, hashes and our own symbol names only (`CLAUDE.md`).
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import (
    BOKU_BIN_LBA,
    Archive,
    Member,
    coarse_type,
    entropy,
    pack_signature,
    tim_length,
    zero_sector_notes,
)
from boku.archive import SECTOR as _SECTOR
from boku.arrays import SelectTables, walk_all
from boku.events import (
    OP_MAP,
    OP_MOVIE,
    OP_PROG,
    OP_SELECT,
    OP_XA,
    OP_XAMSG,
    TEXT_OPS,
    EventWorld,
    Scene,
    fmt_cond,
    s16,
)
from boku.sites import Walk, control_words, line_key_of, scan_text, walk

DATA_DIR = REPO_ROOT / "research/data"
JPSXDEC_IDX = REPO_ROOT / "reference/repos/boku1-reversing/ghidra_scripts/boku.idx"
"""psyouloveme's jPSXdec index, kept locally under the gitignored `reference/`. Without it
the member map's `jpsxdec_tims` column cannot be reproduced."""

MEMBERS_TSV_NAME = "boku-bin-members.tsv"
TSV_NAMES = (
    MEMBERS_TSV_NAME,
    "text-sites.tsv",
    "scenes.tsv",
    "scene-edges.tsv",
    "text-arrays.tsv",
)


class ResearchRefused(Exception):
    """A table cannot be regenerated truthfully, so it is not written at all."""


def write_all(
    archive: Archive,
    out_dir: Path,
    world: EventWorld | None = None,
    jpsxdec_idx: Path = JPSXDEC_IDX,
) -> list[Path]:
    """Write the tracked tables into `out_dir` and return the paths, in a fixed order.

    The member map needs psyouloveme's jPSXdec index for one of its columns, and that
    index lives under the gitignored `reference/`. Without it the map is **not written**:
    it used to be written with `jpsxdec_tims` silently zeroed in every row, which on a
    normal checkout meant `boku extract --research-tsv` rewrote a tracked file with a
    column of zeros where 858 of 1,302 rows have a count.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    world = world if world is not None else EventWorld(archive)
    written = []
    if Path(jpsxdec_idx).is_file():
        written.append(write_members_tsv(archive, out_dir / MEMBERS_TSV_NAME, jpsxdec_idx))
    written.append(write_text_sites_tsv(archive, out_dir / "text-sites.tsv"))
    written += write_scene_tsvs(world, out_dir / "scenes.tsv", out_dir / "scene-edges.tsv")
    written.append(write_text_arrays_tsv(archive, out_dir / "text-arrays.tsv"))
    return written


def missing_tables(jpsxdec_idx: Path = JPSXDEC_IDX) -> list[str]:
    """Which of `TSV_NAMES` `write_all` will skip, and therefore what a caller must say."""
    return [] if Path(jpsxdec_idx).is_file() else [MEMBERS_TSV_NAME]


# --- REC-01: the member map ----------------------------------------------------------------

MEMBERS_HEADER = (
    "dir_index\tsub_index\tname\toffset\tlba\tsize\tsectors\ttype\tsignature\tentropy\t"
    "zero_sectors\tjpsxdec_tims\ttext_lines\ttext_lines_only_here\tnotes\n"
)


PLACEHOLDER_KIND = "iso-directory-placeholder"


@dataclass
class MemberStats:
    """One row of the member map: measurements of a member, not state of the archive.

    These used to be six mutable fields on `Member` itself, which meant regenerating the
    map wrote into the shared `Archive.members` every caller reads (in the tests, into a
    session fixture). Nothing but this table ever wanted them.
    """

    member: Member
    kind: str
    entropy: float
    zero_sectors: int
    tims: int = 0
    text_lines: int = 0
    text_unique_here: int = 0
    notes: list[str] = field(default_factory=list)


def read_jpsxdec_tims(path: Path) -> list[tuple[int, int]]:
    """`(BOKU.BIN offset, last sector)` per TIM in psyouloveme's jPSXdec index.

    Third-party analysis of the same disc, used as an independent opinion on where the
    member boundaries are: every TIM it found must lie wholly inside one member.
    """
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "|Type:Tim|" not in line or "|ID:BOKU.BIN[" not in line:
            continue
        f = dict(p.split(":", 1) for p in line.split("|") if ":" in p)
        s, e = (int(v) for v in f["Sectors"].split("-"))
        out.append(((s - BOKU_BIN_LBA) * _SECTOR + int(f["Start Offset"]), e - BOKU_BIN_LBA))
    return out


def member_stats(archive: Archive, jpsxdec_idx: Path) -> list[MemberStats]:
    """Every `REC-01` measurement, in archive order. Refuses without the jPSXdec index."""
    jpsxdec_idx = Path(jpsxdec_idx)
    if not jpsxdec_idx.is_file():
        raise ResearchRefused(
            f"{jpsxdec_idx} is not there, so the member map's jpsxdec_tims column would be "
            f"zero in every row. It lives under the gitignored reference/; the map is not "
            f"written rather than written wrong."
        )
    rows = []
    by_member: dict[int, MemberStats] = {}
    for m in archive.members:
        b = archive.blob(m)
        kind = PLACEHOLDER_KIND if m.is_directory_placeholder else pack_signature(b)
        zero_sectors = sum(1 for s in range(0, len(b), _SECTOR) if not any(b[s : s + _SECTOR]))
        row = MemberStats(m, kind, entropy(b), zero_sectors)
        if zero_sectors and kind != PLACEHOLDER_KIND:
            row.notes.append(zero_sector_notes(b))
        rows.append(row)
        by_member[m.offset] = row

    for off, end_sector in read_jpsxdec_tims(jpsxdec_idx):
        m = archive.owner(off)
        n = tim_length(archive.boku, off)
        if m is None or n is None or off + n > m.offset + m.size or end_sector >= m.end_sector:
            continue
        by_member[m.offset].tims += 1

    where: dict[bytes, set[str]] = defaultdict(set)
    per_line: list[tuple[MemberStats, bytes]] = []
    for a, b in scan_text(archive.boku):
        m = archive.owner(a)
        if m is None:
            continue
        digest = hashlib.sha1(archive.boku[a:b]).digest()
        where[digest].add(m.name)
        row = by_member[m.offset]
        per_line.append((row, digest))
        row.text_lines += 1
    for row, digest in per_line:
        if len(where[digest]) == 1:
            row.text_unique_here += 1
    return rows


def write_members_tsv(archive: Archive, path: Path, jpsxdec_idx: Path = JPSXDEC_IDX) -> Path:
    """`boku-bin-members.tsv`: one row per leaf member, with every `REC-01` measurement."""
    rows = member_stats(archive, jpsxdec_idx)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(MEMBERS_HEADER)
        for r in rows:
            m = r.member
            f.write(
                f"{m.dir_index}\t{'' if m.sub_index is None else m.sub_index}\t{m.name}\t"
                f"0x{m.offset:x}\t{m.lba}\t{m.size}\t{m.sectors}\t"
                f"{coarse_type(m.name, r.kind)}\t{r.kind}\t{r.entropy:.2f}\t"
                f"{r.zero_sectors}\t{r.tims}\t{r.text_lines}\t{r.text_unique_here}\t"
                f"{'; '.join(r.notes)}\n"
            )
    return path


# --- REC-03: the physical text sites ----------------------------------------------------------

SITES_HEADER = (
    "member\tcontainer\ttable\tblock_id\tindex\toffset\tsize\tslack\tkind\tline_key\tcontrols\n"
)


def write_text_sites_tsv(archive: Archive, path: Path, result: Walk | None = None) -> Path:
    """`text-sites.tsv`: `REC-03`'s enumeration, so the array partition is that one."""
    result = result if result is not None else walk(archive, array_partition="rec03")
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(SITES_HEADER)
        for s in result.sites:
            raw = result.raw(archive, s)
            controls = ",".join(f"{k:04X}x{v}" for k, v in sorted(control_words(raw).items()))
            f.write(
                "\t".join(
                    map(
                        str,
                        [
                            s.member,
                            s.container,
                            s.table,
                            s.block_id,
                            s.index,
                            f"{s.offset:#x}",
                            s.size,
                            s.slack,
                            s.kind,
                            line_key_of(raw),
                            controls,
                        ],
                    )
                )
                + "\n"
            )
    return path


# --- REC-05: the scene inventory and the flow graph ----------------------------------------------

SCENES_HEADER = [
    "event", "copies", "in_ev", "map_bases", "time_slots", "maps", "triggers", "day",
    "meal_hour", "condition", "cast_slot/model", "messages", "voiced_nodes", "play_order",
    "speakers", "unreachable", "chains",
]  # fmt: skip
EDGES_HEADER = ["event", "from", "to", "condition"]


def scene_row(world: EventWorld, sc: Scene) -> tuple[list[str], list[str], list[str]]:
    """One `scenes.tsv` row, plus this event's natively-indexed and unreachable line ids."""
    event = sc.event
    maps = sorted({m[2:8] for m in event.members if m.startswith("M_")})
    bases = sorted({m[:3] for m in maps})
    slots = "".join(sorted({m[3] for m in maps}))
    triggers = Counter(p.label for p in world.placements.get(sc.id, []))
    day, meal = world.when(sc)
    order = sc.play_order() if sc.ins else []

    tokens: list[str] = []
    voiced = 0
    speakers: Counter[str] = Counter()
    natives: set[int] = set()
    for p in order:
        i = sc.ins[p]
        label, slot = world.speaker(sc, p)
        if i.op == OP_PROG:
            natives.add(s16(i.b, 2))
            tokens.append(f"P{s16(i.b, 2)}:{label}")
            continue
        if i.op in (OP_MAP, OP_MOVIE):
            tokens.append(sc.chain_token(i))
            continue
        clip = i.clip if i.op == OP_XAMSG else ""
        if i.op in (OP_XAMSG, OP_XA):
            voiced += 1
        if i.op != OP_SELECT and sc.messages[i.message_index][1]:
            speakers[label] += 1
        tokens.append(
            f"{i.message_index}:{i.name}:{label}"
            + (f":s{slot}" if slot is not None else "")
            + (f":{clip}" if clip else "")
        )

    reachable = {sc.ins[p].message_index for p in order if sc.ins[p].op in TEXT_OPS}
    dead: list[str] = []
    native: list[str] = []
    for mi in range(sc.message_count):
        if sc.messages[mi][1] is None:
            continue
        line_id = f"E{sc.id:04d}.{mi}"
        if mi not in sc.named:
            continue
        if mi in reachable:
            continue
        kinds = {sc.ins[p].op for p in sc.named[mi]}
        quiz = 15 in natives and kinds == {OP_SELECT}
        menu = 16 in natives and kinds <= {OP_XAMSG, 0x0E} and mi >= 7
        if quiz or menu:
            native.append(line_id)
            if kinds != {OP_SELECT}:
                speakers[world.label_of(sc.messages[mi][1])] += 1
        else:
            dead.append(line_id)
    if native:
        dead = ["native:" + ",".join(x.split(".")[1] for x in native), *dead]

    row = [
        f"E{sc.id:04d}",
        str(len(event.members)),
        "EV" if any(m.startswith("EV") for m in event.members) else "",
        ",".join(bases),
        slots,
        ",".join(maps),
        " ".join(f"{k}={v}" for k, v in sorted(triggers.items())),
        str(day or ""),
        str(meal or ""),
        fmt_cond(sc.condition) if sc.condition else "",
        " ".join(f"{a}/{b}" for a, b in sc.cast),
        str(sc.message_count),
        str(voiced),
        " ".join(tokens),
        " ".join(f"{k}={v}" for k, v in speakers.most_common()),
        " ".join(dead),
        " ".join(f"{kind}>{m}" + (f">E{n:04d}" if n > 0 else "") for kind, m, n, _r in sc.chain),
    ]
    return row, native, dead


def write_scene_tsvs(world: EventWorld, scenes_path: Path, edges_path: Path) -> list[Path]:
    """`scenes.tsv` (one row per event) and `scene-edges.tsv` (the flow graph)."""
    rows = []
    edges = []
    for sc in world.scenes.values():
        row, _native, _dead = scene_row(world, sc)
        rows.append(row)
        name = f"E{sc.id:04d}"
        for dst, condition in sc.entry_edges.items():
            edges.append([name, "ENTRY", sc.node_id(dst), condition])
        for src, dst, condition in sc.edges:
            if src in sc.reach:
                edges.append([name, sc.node_id(src), sc.node_id(dst), condition])
    scenes_path.write_text(
        "\n".join("\t".join(r) for r in [SCENES_HEADER, *rows]) + "\n", encoding="utf-8"
    )
    edges_path.write_text(
        "\n".join("\t".join(r) for r in [EDGES_HEADER, *edges]) + "\n", encoding="utf-8"
    )
    return [scenes_path, edges_path]


# --- REC-06: the arrays outside event blocks ---------------------------------------------------

ARRAYS_HEADER = (
    "file\tline_id_prefix\tfile_offset\tram_start\tram_end\tshape\titems\titem_structure\t"
    "reader\tpurpose\tglyphs\n"
)

_SHAPE_TEXT = {
    "E": "items end 0x8000 (0x8001 = newline inside)",
    "L": "every bit-15 word ends a line; indexed by line",
    "S1": "one line ended by a bit-15 word",
}


def array_structure(archive: Archive, array, select_lines: SelectTables) -> str:
    """The `item_structure` column: how the array's reader walks it, in one sentence."""
    if array.shape == "S":
        return f"select: {select_lines(*array.spec)} lines each ended 0x8001, no 0x8000"
    if array.shape == "R":
        return "raw u16 glyphs, no control words, {}x{}".format(*array.spec)
    return _SHAPE_TEXT[array.shape]


def write_text_arrays_tsv(archive: Archive, path: Path) -> Path:
    """`text-arrays.tsv`: the arrays of `research/text-outside-events.md`, with bounds
    their own readers proved."""
    select_lines = SelectTables(archive)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(ARRAYS_HEADER)
        for w in walk_all(archive):
            a = w.array
            f.write(
                "\t".join(
                    str(x)
                    for x in (
                        a.file_name,
                        a.line_id_prefix,
                        f"0x{a.file_offset:X}",
                        f"0x{a.ram:08X}",
                        f"0x{w.end:08X}",
                        a.shape,
                        w.items,
                        array_structure(archive, a, select_lines),
                        a.reader,
                        a.purpose,
                        w.drawn_cells,
                    )
                )
                + "\n"
            )
    return path
