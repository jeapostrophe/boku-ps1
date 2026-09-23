"""`PIPE-03`: put new text back, rebuilding every container that has to move.

`research/text-format.md` § "What a reinserter rewrites when one line grows by N bytes" is
the list this module implements, bottom up and for **every physical copy** of a changed
line:

1. the message bytes, then the 0/2-byte pad to 4 (`boku.events.pack_block`);
2. `off[]` of every later entry of the block (the same call);
3. *map:* the block's `length` and every later block's `offset` in child 1
   (`boku.events.BlockTable.serialise`); *`EV`:* nothing at this level;
4. *map:* child 1's `size` and the `offset` of children 2…6 in the pack table
   (`boku.archive.Pack.serialise`);
5. the member's `size` in `M_FILES.SEC` (`u32`) / `EV.SEC` (`u16`)
   (`boku.archive.SubArchiveIndex.serialise`);
6. a member that outgrows its sectors is **relocated** (`boku.relocate`): it is written
   either to sectors another moving member vacates or, failing that, to the filler before
   `BOKU.BIN`; whatever is left over is zeroed; and whatever addresses it is rewritten —
   the `.SEC` record's `sector` (relative to the container's `g_cd_dir` LBA, so a
   container that now holds a member below its base is rebased) for a sub-archive member,
   `g_cd_dir.lba[i]` / `size[i]` for a top-level one. `research/relocation.md` is the
   evidence for which field is which.

**Nothing is written in the abstract.** The output is a list of `ByteEdit`s over the two
files a patch touches — `SCPS_100.88` and `BOKU.BIN` — each carrying the bytes it expects
to find, so `boku.build` can verify against the image before it writes and the same list
describes an EXE word patch and a rebuilt 220 KB map pack.

**A rebuild that changes nothing produces no edit, and that is the round-trip gate**
(`PIPE-05`): reinserting every line with its own original words walks the whole structural
path — block entries, child-1 table, pack table, `.SEC` — and the *comparison* with the
bytes on the disc is what says the path is lossless. `Plan.members_rebuilt` counts what was
actually rebuilt, so "no edits" cannot mean "nothing was tried".

The three measured limits, and where they come from
---------------------------------------------------
* **An event block must stay within `0x4000` bytes** (`research/loading-and-memory.md`
  § "`EV.BIN` members"): a demand-loaded block shares one `0x4000` buffer and
  `ev_list_step` panics with "event buffer over". The cap is applied to every block, not
  only to `EV.BIN` members, because 39 event ids exist as a full copy in both places and
  the two must stay byte-identical; the largest block on the disc is 6,136 bytes, so it
  binds on nothing that ships.
* **A map pack's child 6 must start below `0x6400`**, less 12 bytes per animated object,
  because `map_init` hands the bytes from `+0x34` on to `map_anim_init` as a work array
  (`research/loading-and-memory.md` § "Map packs"). `map_commit` tests only
  `pack[+0x34] > 0x6400`; the work-area allowance is the stricter figure the research
  computes, and it is what `head_room` reports. `0x6400` is the retail engine's word and a
  renderer patch may raise it, so every caller can hand its own in (`MAP_WORK_AREA_END`).
* **A member that outgrows its own sectors has to move.** `research/boku-bin.md` measured
  the slack (min 16 bytes, median 1,246) and that it is zero-filled everywhere, which is
  why a shrinking member has its tail zeroed here rather than left holding its own old
  bytes — and why a relocated member's new sectors are zero-padded too. The room is the
  sectors the other moving members vacate plus a finite arena
  (`boku.relocate.DEFAULT_ARENA`); running out is a refusal, with the numbers.

The `0x4000` event-block limit has not been watched in an emulator yet — the research asks
for that before anything relies on it (`PLAN PIPE-03`). The map work area has: `asm/arena.asm`
raises `0x6400` to `0x7C00`, and a build over that raise was run on both emulators
(`research/vwf-prototype.md` § "The map work area").
"""

from __future__ import annotations

import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise

from boku.archive import (
    ARCHIVE_NAME,
    EV_DIR_INDEX,
    EXE_NAME,
    SECTOR,
    SUB_ARCHIVES,
    Archive,
    Member,
    dir_arrays,
    parse_pack,
    read_exe_dir,
)
from boku.events import MAP_PACK_BLOCK_TABLE, Block, pack_block, parse_block_table
from boku.glyphs import END_WORD, PAD_WORD, words_to_bytes
from boku.relocate import (
    SECTOR_FIELD_MAX,
    Layout,
    Placement,
    RelocationRefused,
    Run,
    SectorEdit,
    container_names,
    containers_touched,
    plan_layout,
    relocation_edits,
    sector_fields,
)
from boku.relocate import check_disjoint as check_sectors_disjoint
from boku.sites import Site, Walk

EVENT_BLOCK_LIMIT = 0x4000
"""The `EV` member buffer a demand-loaded block is read into (`ev_list_step`)."""

MAP_WORK_AREA_END = 0x6400
"""`map_commit`'s test on the word at pack `+0x34`, and the size of arena half "A".

The retail engine's limit, and so the default. It is a **patchable** number, not a law of
the format: a renderer patch that moves the work area raises it, and the reinserter must
then measure against the engine the image will actually run — hence the `work_area_end`
keyword on `plan`, `_rebuilt_map` and `map_head_room`. A build that raised the engine's
limit and left this one alone would refuse lines that fit."""

MAP_WORK_RECORD_BYTES = 12
"""One animated object's work record, allocated from child 6's address once the map is live."""

CHILD6_OFFSET_FIELD = 4 + 8 * 6
"""`0x34` — where the pack table holds child 6's offset, which is the word `map_commit` tests."""

EV_SEC_SIZE_MAX = 0xFFFF
"""`EV.SEC`'s `size` is a `u16` (`research/boku-bin.md`); the largest shipped is 3,812."""


class ReinsertRefused(Exception):
    """The reinsertion will not proceed: a limit is exceeded, or the words do not fit.

    `lines` names the logical lines the refusal is about, when it is about lines at all.
    A build that is willing to leave a line untranslated rather than stop (`--skip-unfitted`)
    needs to know *which* lines to drop, and it has to drop them **everywhere**: a line
    kept in one map and dropped in another would break the invariant that every copy of a
    line is byte-identical, which is the one thing the whole id scheme rests on.
    """

    def __init__(self, message: str, lines: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.lines = tuple(sorted(set(lines)))


# --- what a reinsertion produces -----------------------------------------------------------


@dataclass(frozen=True)
class ByteEdit:
    """One byte range of one file, with what has to be there first.

    `old` is not decoration: it is checked against the image before the first sector is
    written, so a mis-resolved offset, a dump that is not this one, and an already-patched
    image are all refusals rather than a corrupted build.
    """

    file: str
    """`SCPS_100.88` or `BOKU.BIN` — the two files a patch writes into."""
    offset: int
    """Byte offset inside that file."""
    old: bytes
    new: bytes
    reason: str
    """What this edit is, for the manifest and for a refusal's message."""

    def __post_init__(self) -> None:
        if len(self.old) != len(self.new):
            raise ReinsertRefused(
                f"{self.reason}: {len(self.old)} bytes replaced by {len(self.new)}; "
                f"an edit never changes a file's length (PIPE-04 keeps every LBA)"
            )

    @property
    def end(self) -> int:
        return self.offset + len(self.old)

    @property
    def changes(self) -> bool:
        return self.old != self.new


@dataclass(frozen=True)
class Plan:
    """Everything one reinsertion would write, and what it had to rebuild to know that."""

    edits: tuple[ByteEdit, ...]
    """Only the ranges whose bytes actually change, in `(file, offset)` order."""
    members_rebuilt: tuple[str, ...]
    """Members taken apart and put back together, changed or not — the gate's witness."""
    sites_written: int
    """Physical copies of the changed lines that were re-encoded."""
    lines: tuple[str, ...]
    growth: Mapping[str, int]
    """Member -> bytes its `size` gained (negative if it shrank). Unchanged members absent."""
    sectors: tuple[SectorEdit, ...] = ()
    """Whole sectors written outside any file: a relocated member's new home, and the
    sectors it vacated, zeroed (`boku.relocate`). Empty unless something had to move."""
    layout: Layout = field(default_factory=Layout)
    """What moved and what it cost. `Layout.unchanged` is the null re-layout."""

    @property
    def unchanged(self) -> bool:
        return not self.edits and not self.sectors

    @property
    def relocations(self) -> tuple[Placement, ...]:
        return self.layout.placements


# --- head room, per the two measured limits --------------------------------------------------


def map_work_records(child0: bytes) -> int:
    """Animated objects in a map's child 0 — one 12-byte work record each once it is live.

    `map_child0_parse` (`0x8001727C`): a `u32` placement count and that many `0x14`-byte
    records, a `0x14`-byte map header, a `u32` count of 8-byte records, then a `u8` count
    of the animated objects (`research/loading-and-memory.md` § "The role of each child").
    Ported from `work/rec06/mapstats2.py`, which is where the research's per-map head room
    comes from.
    """
    (placements,) = struct.unpack_from("<I", child0)
    after_placements = 4 + 0x14 * placements
    (records,) = struct.unpack_from("<I", child0, after_placements + 0x14)
    return child0[after_placements + 0x18 + 8 * records]


def map_head_room(pack_bytes: bytes, work_area_end: int = MAP_WORK_AREA_END) -> int:
    """Bytes a map pack's children 0-5 may still grow by before `map_commit` breaks.

    `work_area_end - child6_offset - 12 * animated objects`. A null child 6 is not tested
    by the engine (`0 > work_area_end` is false), so it has no limit here either.

    `work_area_end` is the engine's limit **as the image being built will run it**, which
    a renderer patch may have raised; it defaults to the retail `MAP_WORK_AREA_END`.
    """
    pack = parse_pack(pack_bytes)
    if pack is None:
        raise ReinsertRefused("not a pack; a map file is a seven-child pack")
    child6 = pack.entries[6][0] if len(pack.entries) > 6 else 0
    if not child6:
        return work_area_end
    child0_offset, child0_size = pack.entries[0]
    work = map_work_records(pack_bytes[child0_offset : child0_offset + child0_size])
    return work_area_end - child6 - MAP_WORK_RECORD_BYTES * work


def sector_head_room(member: Member) -> int:
    """Bytes a member may grow by before it needs a sector that belongs to the next member."""
    return member.sectors * SECTOR - member.size


# --- validating the words a caller hands in ---------------------------------------------------


def _control_words(words: Sequence[int]) -> list[int]:
    """The bit-15 words in order, a page break's parameter skipped as `iter_tokens` does."""
    out: list[int] = []
    skip = False
    for word in words:
        if skip:
            skip = False
        elif word & 0x8000:
            out.append(word)
            skip = word == 0x8002
    return out


def check_words(site: Site, words: Sequence[int], original: Sequence[int]) -> None:
    """Refuse words whose *structure* would move something the reader counts on.

    Box limits, page counts and pixel widths are `boku.layout`'s lints, not this module's;
    what is checked here is only what the containers and the readers require:

    * a **message** ends at its first `0x8000`, so the terminator has to be the last word
      — anything after it would be unreachable bytes occupying the block;
    * a **select** has no terminator and is exactly `L` lines, each ended by a bit-15 word,
      with `L` coming from the executable (`research/text-format.md` § SELECT);
    * an **array item** is delimited by its control words and its neighbours are found by
      scanning past them, so the control words must come back in the same order.
    """
    kind = site.kind.split("+")[0]
    if kind == "MSG":
        if not words or words[-1] != END_WORD:
            raise ReinsertRefused(
                f"{site.line_id}: a message ends with {{END}}; these words end with "
                + (f"{words[-1]:#06x}" if words else "nothing"),
                [site.line_id],
            )
        if _control_words(words).count(END_WORD) != 1:
            raise ReinsertRefused(
                f"{site.line_id}: {_control_words(words).count(END_WORD)} {{END}} words; a "
                f"message has one and it is the last, or the rest is unreachable bytes",
                [site.line_id],
            )
    elif kind.startswith("SEL"):
        want = len(_control_words(original))
        got = len(_control_words(words))
        if got != want:
            raise ReinsertRefused(
                f"{site.line_id}: a {kind} box draws {want} lines and these words end "
                f"{got}; the line count is in the executable and a translation may not "
                f"change it (research/text-format.md § SELECT)",
                [site.line_id],
            )
        if not words or not words[-1] & 0x8000:
            raise ReinsertRefused(
                f"{site.line_id}: every line of a select ends with a control word",
                [site.line_id],
            )
    elif kind.startswith("ARR"):
        want, got = _control_words(original), _control_words(words)
        if want != got:
            raise ReinsertRefused(
                f"{site.line_id}: the array item's control words are "
                f"{[f'{w:#06x}' for w in want]} and these words carry "
                f"{[f'{w:#06x}' for w in got]}; item {site.index + 1} is found by scanning "
                f"past item {site.index}'s, so they may not move",
                [site.line_id],
            )


def _fill_in_place(site: Site, raw: bytes) -> bytes:
    """Pad `raw` out to the site's own byte length, keeping the reader's partition intact.

    A message is filled after its `{END}` with the blank cell, which no reader reaches
    (`boku.glyphs.GlyphTable.message`, the rule `TXT-04` writes by). Everything else —
    array items, select lines — is delimited by its control words, so the filler goes
    *before* the last one: trailing blank cells on the last line, not extra items.
    """
    if len(raw) > site.size:
        raise ReinsertRefused(
            f"{site.line_id}: {len(raw)} bytes into a {site.size}-byte site, "
            f"{len(raw) - site.size} over. This site is written in place "
            f"({site.container} {site.kind}), so nothing may grow here; relocating the "
            f"array and repointing its lui/addiu pair is not this unit's (PLAN PIPE-03).",
            [site.line_id],
        )
    filler = PAD_WORD.to_bytes(2, "little") * ((site.size - len(raw)) // 2)
    if site.kind.split("+")[0] == "MSG" or not raw:
        return raw + filler
    return raw[:-2] + filler + raw[-2:]


# --- the rebuild ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Message:
    """One site's new words, with the bytes the walk read there to place them against."""

    site: Site
    raw: bytes
    was: bytes


def _entry_bytes(block: Block, message: _Message) -> bytes:
    """A message entry's replacement: the words, then the pad to 4 the block needs.

    The original pad is **uninitialised build-tool memory** — 339 distinct values across
    the disc, never read (`research/text-format.md`). It is carried back whenever the new
    text needs a pad of the same length, which is what makes reinserting a line with its
    own words reproduce the block byte for byte instead of zeroing 2,881 pads.

    The entry is *identified* by re-reading it: the bytes the walk found at this site have
    to be the head of the entry the block's own offset table points at. A member resolved
    to the wrong offset, or a block table read at the wrong base, is a refusal here rather
    than a silently misplaced write.
    """
    site = message.site
    index = 4 + 2 * site.index
    old = block.entries[index] if index < len(block.entries) else None
    if not site.size:
        # A voice-only slot (`sites.Walk.voice_only`): the null entry a subtitle fills.
        if old is not None or block.entries[index - 1] is None:
            raise ReinsertRefused(
                f"{site.line_id}: entry {index} of its block is not a voice-only slot",
                [site.line_id],
            )
        old = b""
    elif old is None:
        raise ReinsertRefused(f"{site.line_id}: entry {index} of its block is null", [site.line_id])
    if old[: site.size] != message.was:
        raise ReinsertRefused(
            f"{site.line_id}: entry {index} of the block in {site.member} does not hold "
            f"the bytes the walk read at that site; the block was resolved to the wrong "
            f"place and nothing was written",
            [site.line_id],
        )
    pad_length = -len(message.raw) % 4
    old_pad = old[site.size :]
    return message.raw + (old_pad if len(old_pad) == pad_length else bytes(pad_length))


def _rebuilt_block(data: bytes, messages: Mapping[int, _Message], where: str) -> bytes:
    """One event block with some message entries replaced and every offset recomputed."""
    block = Block(data)
    entries = list(block.entries)
    for index, message in messages.items():
        entries[4 + 2 * index] = _entry_bytes(block, message)
    rebuilt = pack_block(entries)
    if len(rebuilt) > EVENT_BLOCK_LIMIT:
        raise ReinsertRefused(
            f"{where}: the block is {len(rebuilt)} bytes and an event block loads into a "
            f"{EVENT_BLOCK_LIMIT}-byte buffer ({len(rebuilt) - EVENT_BLOCK_LIMIT} bytes "
            f'over); ev_list_step panics with "event buffer over" '
            f"(research/loading-and-memory.md)"
        )
    return rebuilt


def _rebuilt_map(
    member: Member,
    blob: bytes,
    per_block: Mapping[int, dict[int, _Message]],
    work_area_end: int = MAP_WORK_AREA_END,
) -> bytes:
    """A whole map pack with its child-1 table, its pack table and its blocks rebuilt."""
    pack = parse_pack(blob)
    if pack is None or len(pack.entries) != 7:
        raise ReinsertRefused(f"{member.short_name}: not a seven-child map pack")
    offset, size = pack.entries[MAP_PACK_BLOCK_TABLE]
    table = parse_block_table(blob[offset : offset + size], member.name)
    for index, entries in per_block.items():
        ident, data = table.blocks[index]
        where = f"{member.short_name} c1[{index}] id E{ident:04d}"
        table = table.replace(index, _rebuilt_block(data, entries, where))
    children = list(pack.children)
    children[MAP_PACK_BLOCK_TABLE] = table.serialise()
    rebuilt = replace(pack, children=tuple(children)).serialise()
    room = map_head_room(rebuilt, work_area_end)
    if room < 0:
        was = map_head_room(blob, work_area_end)
        raise ReinsertRefused(
            f"{member.short_name}: child 6 would start at "
            f"{struct.unpack_from('<I', rebuilt, CHILD6_OFFSET_FIELD)[0]:#x} and everything "
            f"before it must fit {work_area_end:#x} bytes less "
            f"{MAP_WORK_RECORD_BYTES} per animated object — {-room} bytes over, from "
            f"{was} bytes of head room (research/loading-and-memory.md § Map packs)",
            [m.site.line_id for block in per_block.values() for m in block.values()],
        )
    return rebuilt


def _grown_member(member: Member, blob: bytes, rebuilt: bytes) -> ByteEdit:
    """The archive edit for one rebuilt member that stays where it is.

    The range covers the larger of the two sizes so that a member which *shrinks* has its
    tail zeroed: `research/boku-bin.md` measured that the bytes between a member's size and
    its sector end are zero everywhere, and leaving the old text there would break that and
    hand the next reader of the archive a ghost of the Japanese.
    """
    span = max(len(rebuilt), len(blob))
    return ByteEdit(
        file=ARCHIVE_NAME,
        offset=member.offset,
        old=blob[:span].ljust(span, b"\0"),
        new=rebuilt.ljust(span, b"\0"),
        reason=f"{member.short_name} rebuilt ({len(blob)} -> {len(rebuilt)} bytes)",
    )


def _sec_edit(
    archive: Archive,
    container: str,
    container_index: int,
    sizes: Mapping[str, int],
    lines: Mapping[str, set[str]],
    layout: Layout,
) -> ByteEdit | None:
    """The `.SEC` index of one sub-archive: the changed `size` and `sector` fields.

    Both fields are rewritten from the same layout, because they answer one question —
    where the selector will point `g_cd_dir`'s slot. `sector` is **relative to the
    container's `g_cd_dir` LBA** (`research/relocation.md`), so a rebased container moves
    every record's field even though only one member moved.

    Both are keyed by the record's **name**, never by its position. A position that had
    drifted from the archive's member map would give one record another member's sectors,
    and a re-laid-out container is legitimately out of sector order, so nothing downstream
    would see it (`boku.relocate.sector_fields`). The two sets of names are required to
    match exactly, which also catches a member the map has and the `.SEC` does not, and a
    record no member answers for.
    """
    sec_name, parse = SUB_ARCHIVES[container]
    member = archive.member(sec_name)
    index = parse(archive.blob(member))
    fields = dict(sector_fields(archive, layout, container_index))
    keys = {record.key for record in index.records}
    if fields and set(fields) != keys:
        raise ReinsertRefused(
            f"{sec_name} holds {len(keys)} record(s) and the member map has "
            f"{len(fields)} for g_cd_dir[{container_index}]; they differ over "
            f"{sorted(set(fields) ^ keys)[:4]}, so this layout does not describe the "
            f"archive it is about to be written into"
        )
    records = []
    changed = False
    for record in index.records:
        size = sizes.get(record.key, record.size)
        sector = fields.get(record.key, record.sector)
        if size != record.size and index.kind == "EV" and size > EV_SEC_SIZE_MAX:
            raise ReinsertRefused(
                f"{record.key}: {size} bytes, and {sec_name}'s size field is a u16 "
                f"({EV_SEC_SIZE_MAX} max)",
                lines.get(record.key, ()),
            )
        if not 0 <= sector <= SECTOR_FIELD_MAX:
            raise ReinsertRefused(
                f"{record.key}: sector {sector} past {sec_name}'s u16 field; the record "
                f"counts from the container's g_cd_dir LBA and the selector reads it with "
                f"lhu (research/relocation.md)",
                lines.get(record.key, ()),
            )
        if (size, sector) != (record.size, record.sector):
            record = replace(record, size=size, sector=sector)
            changed = True
        records.append(record)
    if not changed:
        return None
    rebuilt = replace(index, records=tuple(records)).serialise()
    old = archive.blob(member)
    return ByteEdit(
        file=ARCHIVE_NAME,
        offset=member.offset,
        old=old,
        new=rebuilt,
        reason=f"{sec_name}: member sizes and sectors",
    )


def directory_edits(archive: Archive, layout: Layout) -> list[ByteEdit]:
    """The `g_cd_dir` words a layout changes: a moved member's pair, a rebase's `lba`.

    A top-level member *is* its two directory words — `cd_load_sync` reads `size[i]`
    sectors from `lba[i]` — so relocating one is exactly this write.

    A rebased container gets **`lba` only**. `size[container]` is not rewritten to cover
    the members' new span, which an earlier draft did: no reader in this toolchain uses a
    container's `size` (`build_members` takes its `lba` and reads the `.SEC` sibling), and
    `cd_dir_size` has 21 call sites in the game whose indexes are not documented
    (`research/boku-bin.md` § "Loader"), so a value spanning the arena *and* every member
    below the container would be an unmeasured write to a live executable field. Neither
    the old value nor a recomputed one describes where the records sit; the old one is the
    one the retail game ran with.
    """
    arrays = dir_arrays(archive.exe)
    entries = {e.index: e for e in read_exe_dir(archive.exe)}
    out: list[ByteEdit] = []

    def word(index: int, offset: int, was: int, now: int, reason: str) -> None:
        out.append(
            ByteEdit(
                file=EXE_NAME,
                offset=offset,
                old=was.to_bytes(4, "little"),
                new=now.to_bytes(4, "little"),
                reason=reason,
            )
        )

    for placement in sorted(layout.placements, key=lambda p: p.dir_index):
        if placement.sub_index is not None:
            continue
        index, entry = placement.dir_index, entries[placement.dir_index]
        reason = f"g_cd_dir[{index}] {placement.member} -> LBA {placement.lba}"
        word(index, arrays.lba_offset(index), entry.lba, placement.lba, reason)
        word(index, arrays.size_offset(index), entry.size, placement.size, reason)
    for index in sorted(layout.bases):
        entry = entries[index]
        name = entry.name.rsplit("\\", 1)[-1]
        word(
            index,
            arrays.lba_offset(index),
            entry.lba,
            layout.bases[index],
            f"g_cd_dir[{index}] {name} rebased to LBA {layout.bases[index]} "
            f"(every .SEC sector counts from it)",
        )
    return [edit for edit in out if edit.changes]


# --- the whole reinsertion -----------------------------------------------------------------


def plan(
    archive: Archive,
    walk: Walk,
    replacements: Mapping[str, Sequence[int]],
    *,
    in_place: bool = False,
    arena: Sequence[Run] | None = None,
    work_area_end: int = MAP_WORK_AREA_END,
) -> Plan:
    """Every byte range one set of new lines would change, with nothing written yet.

    `replacements` maps a **logical line id** to its new words — control words included,
    already encoded. Every physical copy of each id is rewritten, because which copy the
    game reaches is not known statically (`research/text-format.md` § Duplication).

    With `in_place` the site keeps its own byte length and the containers are left alone:
    that is `TXT-04`'s rule, the only thing a code-file array can do, and what the trial
    image is built with. Otherwise the enclosing structures are rebuilt bottom up and the
    limits above are enforced.

    `work_area_end` is the map work area of the engine **this build installs**: a renderer
    patch that raises `map_commit`'s limit hands the new value in, and a caller that does
    not gets the retail one (`MAP_WORK_AREA_END`).
    """
    sites: list[Site] = []
    for line_id in replacements:
        found = walk.by_line.get(line_id) or walk.voice_only.get(line_id)
        if found and in_place and not found[0].size:
            raise ReinsertRefused(
                f"{line_id} is a voice-only entry: its text offset is null, so there are no "
                f"bytes to overwrite in place and its block has to be rebuilt",
                [line_id],
            )
        if not found:
            raise ReinsertRefused(
                f"no text site is called {line_id!r}; the ids are the ones "
                f"`boku extract` writes to disc/script/lines.jsonl"
            )
        sites += found

    edits: list[ByteEdit] = []
    rebuilt_members: list[str] = []
    growth: dict[str, int] = {}
    # member -> block index in its child-1 table (0 for `EV.BIN`) -> message index -> words.
    structural: dict[str, dict[int, dict[int, _Message]]] = {}

    for site in sites:
        raw = words_to_bytes(replacements[site.line_id])
        source = archive.exe if site.file == "EXE" else archive.boku
        was = source[site.absolute : site.absolute + site.size]
        check_words(site, replacements[site.line_id], struct.unpack(f"<{site.size // 2}H", was))
        if in_place or site.container not in ("c1", "ev"):
            edits.append(
                ByteEdit(
                    file=EXE_NAME if site.file == "EXE" else ARCHIVE_NAME,
                    offset=site.absolute,
                    old=was,
                    new=_fill_in_place(site, raw),
                    reason=f"{site.line_id} in {site.member} ({site.kind})",
                )
            )
            continue
        block_index = site.table if site.container == "c1" else 0
        per_block = structural.setdefault(site.member, {}).setdefault(block_index, {})
        per_block[site.index] = _Message(site, raw, was)

    by_member: dict[str, set[str]] = {}
    for site in sites:
        by_member.setdefault(site.member, set()).add(site.line_id)
    blobs: dict[str, bytes] = {}
    for short_name in sorted(structural):
        member = archive.member(short_name)
        blob = archive.blob(member)
        if member.dir_index == EV_DIR_INDEX:
            rebuilt = _rebuilt_block(blob, structural[short_name][0], f"{short_name} (EV.BIN)")
        else:
            rebuilt = _rebuilt_map(member, blob, structural[short_name], work_area_end)
        rebuilt_members.append(short_name)
        blobs[short_name] = rebuilt
        if len(rebuilt) != member.size:
            growth[short_name] = len(rebuilt) - member.size

    sizes = {name: len(blob) for name, blob in blobs.items()}
    try:
        layout = plan_layout(archive, sizes, arena=arena)
    except RelocationRefused as error:
        raise ReinsertRefused(str(error), by_member.get(error.member or "", ())) from error
    moved = layout.by_member
    for short_name, rebuilt in blobs.items():
        if short_name in moved:
            continue
        member = archive.member(short_name)
        edit = _grown_member(member, archive.blob(member), rebuilt)
        if edit.changes:
            edits.append(edit)

    # Every sub-archive whose records the layout disturbs, plus every one holding a member
    # whose size changed -- derived, not the two that hold text today: `plan_layout` will
    # place a member of any of the four, and rebasing a container without rewriting its
    # records puts every model or diary page 765 sectors below where it lives.
    names = container_names(archive)
    touched = set(containers_touched(archive, layout))
    touched |= {archive.member(name).dir_index for name in sizes} & set(names)
    for index_of in sorted(touched):
        changed = {
            name: sizes[name] for name in sizes if archive.member(name).dir_index == index_of
        }
        sec = _sec_edit(archive, names[index_of], index_of, changed, by_member, layout)
        if sec is not None:
            edits.append(sec)
    edits += directory_edits(archive, layout)

    sectors = relocation_edits(archive, layout, blobs)
    edits = [e for e in edits if e.changes]
    edits.sort(key=lambda e: (e.file, e.offset))
    check_disjoint(edits)
    check_sectors_disjoint(sectors)
    check_no_double_write(edits, sectors, archive)
    return Plan(
        edits=tuple(edits),
        members_rebuilt=tuple(rebuilt_members),
        sites_written=len(sites),
        lines=tuple(sorted(replacements)),
        growth=growth,
        sectors=tuple(sorted(sectors, key=lambda e: e.lba)),
        layout=layout,
    )


def check_no_double_write(
    edits: Sequence[ByteEdit],
    sectors: Sequence[SectorEdit],
    archive: Archive,
    refused: type[Exception] = ReinsertRefused,
) -> None:
    """A sector may not be written both through `BOKU.BIN` and by LBA.

    The two edit kinds are verified against different reads and applied in different
    passes, so an overlap would make the image depend on which ran last. For the edits
    *this module* plans it cannot happen — members are sector-aligned and a relocated one
    is written only by LBA — but a patch handed in from outside was never in that set, so
    `boku.build.check_no_sector_clash` asks the same question of those and names its own
    refusal through `refused`.
    """
    by_lba = {lba for edit in sectors for lba in range(edit.lba, edit.end)}
    if not by_lba:
        return
    for edit in edits:
        if edit.file != ARCHIVE_NAME:
            continue
        first = archive.base_lba + edit.offset // SECTOR
        last = archive.base_lba + (edit.end - 1) // SECTOR
        clash = by_lba.intersection(range(first, last + 1))
        if clash:
            raise refused(
                f"{edit.reason} writes {ARCHIVE_NAME}+0x{edit.offset:x}, which lands on "
                f"LBA {min(clash)} — a sector a relocation also writes. One of them would "
                f"be lost; nothing was written."
            )


def check_disjoint(edits: Sequence[ByteEdit]) -> None:
    """Two edits over one byte would make the build's result depend on their order."""
    for left, right in pairwise(edits):
        if left.file == right.file and right.offset < left.end:
            raise ReinsertRefused(
                f"{left.reason} and {right.reason} both write {left.file}"
                f"+0x{right.offset:x}; one of them would be lost"
            )
