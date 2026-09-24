"""`PLAN PIPE-07`: code-file text arrays that outgrow their bytes move, whole -- and so do
the event blocks the executable holds (`boku.sites.RESIDENT_BLOCK_ADDRS`, the uncle's evening
call), which are reached the same way.

An array has no slack -- the next symbol starts where it ends -- so an English item longer
than the Japanese one cannot be written in place. What can move is the array: its items
are found by walking control words from its start, and its start is reached only through
the `lui`/`addiu` pairs that build it (`boku.pointers`; no data word points at any array,
`research/text-outside-events.md` § "How the code reaches an array"). So a grown array is
written, all its items back to back, into resident free space, and every pair that
addressed the old start is rewritten to the new one -- in the executable and in every
overlay, since `TITLE` and `HHON` read executable arrays as well as their own.

Where it goes: an array whose every pair is in ONE overlay goes to that overlay's tail
(`overlay_tail`): appended to the member, so it loads with the only code that reads it,
and the resident room is kept for what the executable reads. Everything else goes to
`SCPS_100.88`'s dead regions (research/text-renderer.md § 6 owns the list), the tail of
the renderer's island past what its edit set uses, and the spans the moved arrays leave
behind -- all below the overlay region, so resident in every mode
(`boku.build.check_resident`). Placement is largest-first, best-fit, and running out is a
refusal with the numbers, never a truncation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from boku.archive import (
    ARCHIVE_NAME,
    EXE_LOAD_BIAS,
    EXE_NAME,
    OVERLAY_LOAD_ADDRESS,
    SECTOR,
    Archive,
    Member,
)
from boku.arrays import (
    SAVE_TITLE_LINE_ID,
    SAVE_TITLE_PARTS_ADDR,
    ArrayWalk,
    SelectTables,
    read_save_title,
    relocatable,
    splits_into_rows,
    walk_all,
)
from boku.card_messages import CardSplitRefused, Split, record_edits, splits
from boku.code_text import (
    BANNERS,
    DATE_LABELS,
    banner_blob,
    banner_edits,
    date_label_hook,
    drawer_of,
    is_laid_out_banner,
    split_title_blob,
)
from boku.events import Block, pack_block
from boku.glyphs import words_to_bytes
from boku.pointers import LuiPair, PointerError, repoint, scan
from boku.reinsert import ByteEdit, Tail
from boku.sites import RESIDENT_BLOCK_ADDRS, resident_block_at, resident_line_id, walk_block


class ArrayRoomRefused(Exception):
    """A grown array does not fit the free space, or a pointer to it cannot be moved.

    `lines` are the items that grew: the rest of that array still fits its own bytes."""

    def __init__(self, message: str, lines: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.lines = tuple(lines)


@dataclass(frozen=True)
class Region:
    """A run of resident RAM, `[start, end)`, that no retail code or data uses."""

    start: int
    end: int
    name: str

    @property
    def size(self) -> int:
        return self.end - self.start


DEAD_REGIONS = (Region(0x80025120, 0x80025860, "dbg_font_init's 8x8 font and CLUT"),)
"""research/text-renderer.md § 6's arrays rows that are dead in the retail executable:
referenced only from `dbg_font_init`, which nothing calls."""

PC_HOST_DATA = Region(0x8007224C, 0x80072670, "the PC-host module's data")
"""Dead only once the renderer patch clears `g_pc_host` in the file (`asm/vwf.asm`): on the
stock executable the PC-host branches can run before `sys_init` and write its `$gp`
variables here. So only an edit set offers it (`boku.build.EditSet.array_regions`)."""

ALIGN = 4

HEAP_POINTER = 0x80068AF0
"""The heap's bump pointer; the executable's initial word is the retail heap's first byte
(research/text-renderer.md § 6)."""


def overlay_tail(archive: Archive, member: Member) -> Region:
    """The RAM an overlay's arrays may be appended into: from its own end (aligned) to the
    last whole sector a load can write without passing the retail heap's first byte
    (research/text-renderer.md § 6 has why that is free). Empty when the overlay already
    reaches it (`MUSI`)."""
    heap = int.from_bytes(archive.exe_bytes(HEAP_POINTER, 4), "little")
    start = -(-(OVERLAY_LOAD_ADDRESS + member.size) // ALIGN) * ALIGN
    end = OVERLAY_LOAD_ADDRESS + SECTOR * ((heap - OVERLAY_LOAD_ADDRESS) // SECTOR)
    return Region(start, max(start, end), f"{member.short_name}'s tail")


Image = tuple[str, bytes, int, str, int]
"""`(image, code, RAM base, file, offset of the image in that file)`."""
Scanned = list[tuple[Image, list[LuiPair]]]
Spans = Mapping[str, tuple[str, int, int]]
"""Moved arrays by prefix: `(image, old start, old end)`."""


@dataclass(frozen=True)
class Moved:
    prefix: str
    old: int
    new: int
    size: int
    tail: str | None = None
    """The overlay member whose tail it was appended to; `None` for resident room."""


@dataclass(frozen=True)
class ArrayPlan:
    edits: tuple[ByteEdit, ...]
    moved: tuple[Moved, ...]
    lines: frozenset[str]
    """Every line id of a moved array or block: written by `edits` or `tails`, not in place."""
    free_left: int
    """Resident bytes left."""
    tails: Mapping[str, Tail] = field(default_factory=dict)
    """`{overlay member: what is appended to it}` for the arrays moved into its tail
    (`overlay_tail`); the reinserter rebuilds the grown member (`boku.reinsert.plan`)."""


def _array_bytes(archive: Archive, walked: ArrayWalk, words: Mapping[str, Sequence[int]]) -> bytes:
    out = b""
    for line_id, (start, end) in zip(walked.line_ids, walked.strings, strict=True):
        new = words.get(line_id)
        out += (
            words_to_bytes(new)
            if new is not None
            else archive.image_bytes(walked.image, start, end - start)
        )
    return out


def _grown_items(walked: ArrayWalk, words: Mapping[str, Sequence[int]]) -> list[str]:
    """The items whose new words outgrow their own bytes -- what makes the array move."""
    return [
        line_id
        for line_id, (start, end) in zip(walked.line_ids, walked.strings, strict=True)
        if line_id in words and 2 * len(words[line_id]) > end - start
    ]


def _reaches(image: str, pair_image: str) -> bool:
    """An executable array is addressed from any image; an overlay's only from itself --
    every overlay starts at `0x80079A08`, so one address names different bytes in each."""
    return image in ("exe", pair_image)


def _addressed(pair: LuiPair, pair_image: str, spans: Spans) -> list[str]:
    """The moved arrays whose start one of `pair`'s uses forms."""
    targets = {use.target for use in pair.uses}
    return [
        prefix
        for prefix, (image, start, _) in spans.items()
        if _reaches(image, pair_image) and start in targets
    ]


def _interior(pair: LuiPair, pair_image: str, spans: Spans) -> list[str]:
    """The moved arrays one of `pair`'s uses addresses *inside*: only a start is rewritten,
    so such a use would keep reading the vacated bytes. None exists on this disc; one
    appearing is a refusal, not a quiet miss."""
    return [
        prefix
        for prefix, (image, start, end) in spans.items()
        if _reaches(image, pair_image) and any(start < use.target < end for use in pair.uses)
    ]


def _padded(archive: Archive, region: Region) -> Region:
    """`region` out to the next `ALIGN` boundary when the bytes up to it are zero: the
    0x0000 pad the linker put between two arrays belongs to neither, and a vacated span
    that swallows it meets its neighbour's."""
    end = -(-region.end // ALIGN) * ALIGN
    if any(archive.exe_bytes(region.end, end - region.end)):
        return region
    return Region(region.start, end, region.name)


def _allocate(
    wanted: list[tuple[str, int]], regions: Sequence[Region]
) -> tuple[dict[str, int], int] | tuple[str, str]:
    """Largest first, each into the smallest run it fits (4-aligned); on running out,
    `(prefix, why)` for the array that did not fit. Runs that touch are one run
    (`_padded` has already given a vacated span its alignment pad)."""
    free: list[tuple[int, int]] = []
    for start, end in sorted((r.start, r.end) for r in regions if r.end > r.start):
        if free and start <= free[-1][1]:
            free[-1] = (free[-1][0], max(end, free[-1][1]))
        else:
            free.append((start, end))
    placed: dict[str, int] = {}
    for prefix, size in sorted(wanted, key=lambda item: (-item[1], item[0])):
        best = None
        for index, (start, end) in enumerate(free):
            at = -(-start // ALIGN) * ALIGN
            if at + size <= end and (best is None or end - at < free[best][1] - free[best][0]):
                best = index
        if best is None:
            need = sum(size for _, size in wanted)
            have = sum(r.size for r in regions)
            largest = max((end - start for start, end in free), default=0)
            return prefix, (
                f"{prefix} needs {size} contiguous bytes and the largest free run left is "
                f"{largest}; the grown arrays want {need} bytes in all and the regions hold "
                f"{have} (research/text-renderer.md § 6)"
            )
        start, end = free[best]
        at = -(-start // ALIGN) * ALIGN
        placed[prefix] = at
        free[best] = (at + size, end)
    return placed, sum(end - start for start, end in free)


def images(archive: Archive) -> Iterator[Image]:
    """The executable and every overlay, as code at its load address."""
    yield "exe", archive.exe, EXE_LOAD_BIAS, EXE_NAME, 0
    for member in archive.members:
        if member.short_name.endswith(".OVL"):
            yield (
                member.short_name[:-4].lower(),
                archive.blob(member),
                OVERLAY_LOAD_ADDRESS,
                ARCHIVE_NAME,
                member.offset,
            )


def scans(archive: Archive) -> Scanned:
    """Every image with its `lui` pairs: the part of a plan no translation changes, so a
    caller that retries `plan_arrays` computes it once."""
    return [(image, scan(image[1], image[2])) for image in images(archive)]


@dataclass(frozen=True)
class _Unit:
    """One thing that moves whole: a code-file array, or an event block the executable holds."""

    prefix: str
    image: str
    start: int
    end: int
    blob: bytes
    grown: tuple[str, ...]
    """The items that outgrew their own bytes -- what a refusal leaves in Japanese."""
    lines: tuple[str, ...]
    table: tuple[tuple[int, int], ...] = ()
    """A unit reached through a pointer table in `BOKU.BIN` instead of `lui` pairs:
    `(offset of the table word, offset in the blob it must point at)` per word."""
    hook: Callable[[int], list[ByteEdit]] | None = None
    """For a unit its reader is pointed at by a patch: the edits, given where it landed."""


def _array_units(
    archive: Archive, words: Mapping[str, Sequence[int]], card: Sequence[Split]
) -> Iterator[_Unit]:
    """The grown arrays; `card` is the card messages split into rows (`boku.card_messages`),
    whose further rows are items appended after the array's last, so it grows whatever
    the item's own size."""
    for walked in walk_all(archive):
        if not relocatable(walked.array):
            continue
        prefix = walked.array.line_id_prefix
        split = card if splits_into_rows(prefix) else ()
        laid = {**words, **{s.line_id: s.head for s in split}} if split else words
        extra = b"".join(words_to_bytes(item) for s in split for item in s.rest)
        grown = list(dict.fromkeys([*_grown_items(walked, laid), *(s.line_id for s in split)]))
        if grown:
            yield _Unit(
                prefix,
                walked.image,
                walked.start,
                walked.end,
                _array_bytes(archive, walked, laid) + extra,
                tuple(grown),
                walked.line_ids,
            )


def _block_units(archive: Archive, words: Mapping[str, Sequence[int]]) -> Iterator[_Unit]:
    """The resident event blocks (`boku.sites.RESIDENT_BLOCK_ADDRS`) whose message grew.

    A block has no length field and nothing after it depends on its size but the next
    block (research/text-format.md § "Blocks in the executable"), so a block is its span to
    the next one; the last has no known end and does not move. A message has grown when
    it outgrows the site the walk measured -- the same size the in-place writer holds it
    to -- and the block's entries are then repacked by `boku.events.pack_block`, every
    offset recomputed, and the chooser's pair rewritten."""
    for ram, following in pairwise(RESIDENT_BLOCK_ADDRS):
        if not any(line.startswith(f"exe@{ram:08X}.") for line in words):
            continue
        start = resident_block_at(archive, ram)
        block = Block(archive.exe_bytes(start, following - ram))
        sites = walk_block(block, SelectTables(archive), [], f"exe-block at 0x{ram:08X}")
        entries = list(block.entries)
        grown: list[str] = []
        for index, _to, size, _kind, _slack, _voiced in sites:
            line_id = resident_line_id(ram, index)
            if line_id not in words:
                continue
            raw = words_to_bytes(words[line_id])
            if len(raw) > size:
                grown.append(line_id)
            entries[4 + 2 * index] = raw + bytes(-len(raw) % 4)
        if grown:
            lines = tuple(resident_line_id(ram, index) for index, *_ in sites)
            yield _Unit(
                f"exe@{ram:08X}",
                "exe",
                start,
                start + following - ram,
                pack_block(entries),
                tuple(grown),
                lines,
            )


def _title_units(archive: Archive, words: Mapping[str, Sequence[int]]) -> Iterator[_Unit]:
    """The save title's three Shift-JIS parts (`boku.code_text`), when translated: written
    anywhere resident, and `g_save_title_parts` (three words in `TITLE.OVL`) repointed."""
    if SAVE_TITLE_LINE_ID not in words:
        return
    blob = words_to_bytes(words[SAVE_TITLE_LINE_ID])
    member = archive.member("TITLE.OVL")
    table = tuple(
        (member.offset + SAVE_TITLE_PARTS_ADDR + 4 * k - OVERLAY_LOAD_ADDRESS, at)
        for k, at in enumerate(split_title_blob(blob))
    )
    old = read_save_title(archive).part_offsets[0] + OVERLAY_LOAD_ADDRESS
    yield _Unit(
        SAVE_TITLE_LINE_ID,
        "title",
        old,
        old,
        blob,
        (SAVE_TITLE_LINE_ID,),
        (SAVE_TITLE_LINE_ID,),
        table,
    )


def _date_units(
    archive: Archive, words: Mapping[str, Sequence[int]], routines: Mapping[str, int]
) -> Iterator[_Unit]:
    """A translated date label (`boku.code_text.DATE_LABELS`): its segments written anywhere
    resident, and its drawer's entry hooked to the edit set's routine with `t0` at them.
    The unit's "old" address is the drawer's, which is what the hook replaces."""
    for line_id, label in DATE_LABELS.items():
        if line_id not in words:
            continue
        image, drawer = drawer_of(line_id)
        routine = routines.get(label.routine)
        hook = None
        if routine is not None:
            hook = lambda at, line_id=line_id, routine=routine: [  # noqa: E731
                date_label_hook(archive, line_id, at, routine)
            ]
        blob = words_to_bytes(words[line_id])
        yield _Unit(line_id, image, drawer, drawer, blob, (line_id,), (line_id,), hook=hook)


def _banner_units(
    archive: Archive, words: Mapping[str, Sequence[int]], routines: Mapping[str, int]
) -> Iterator[_Unit]:
    """A translated banner (`boku.code_text.BANNERS`): all its items written anywhere
    resident, its drawer hooked to the edit set's routine with `t0` at them, and its panel
    widened. The unit's "old" address is the drawer's, which is what the hook replaces."""
    for prefix, banner in BANNERS.items():
        lines = tuple(line for line in words if line.split(".", 1)[0] == prefix)
        if not any(is_laid_out_banner(words[line]) for line in lines):
            continue  # only its retail cells were handed in: the retail drawer draws them
        image, drawer = banner.drawer
        routine = routines.get(banner.routine)
        hook = None
        if routine is not None:
            hook = lambda at, prefix=prefix, routine=routine: banner_edits(  # noqa: E731
                archive, prefix, at, routine
            )
        blob = banner_blob(archive, prefix, words)
        yield _Unit(prefix, image, drawer, drawer, blob, lines, lines, hook=hook)


def plan_arrays(
    archive: Archive,
    words: Mapping[str, Sequence[int]],
    regions: Sequence[Region] = DEAD_REGIONS,
    scanned: Callable[[], Scanned] | None = None,
    routines: Mapping[str, int] | None = None,
    no_tail: frozenset[str] = frozenset(),
) -> ArrayPlan:
    """Move every relocatable array, and every resident event block, one of whose items
    `words` grows past its bytes. An overlay member in `no_tail` is not grown (the disc had
    no room for it); its arrays take resident room like any other.

    `scanned` supplies `scans(archive)`, called only once something grows; a caller that
    plans more than once memoises it."""
    try:
        card = splits(words)
        card_records = record_edits(archive, card)
    except CardSplitRefused as error:
        raise ArrayRoomRefused(str(error), error.lines) from error
    units = {
        u.prefix: u
        for u in (
            *_array_units(archive, words, card),
            *_block_units(archive, words),
            *_title_units(archive, words),
            *_date_units(archive, words, routines or {}),
            *_banner_units(archive, words, routines or {}),
        )
    }
    if not units:
        return ArrayPlan((), (), frozenset(), sum(r.size for r in regions))

    for kinds, what in ((DATE_LABELS, "date label"), (BANNERS, "banner")):
        unhooked = [p for p, u in units.items() if p in kinds and u.hook is None]
        if unhooked:
            raise ArrayRoomRefused(
                f"{', '.join(unhooked)}: the English {what} is drawn by a routine of the "
                f"renderer patch, and this build installs no edit set that has it",
                [line for p in unhooked for line in units[p].grown],
            )

    def refusal(why: str, prefixes: Sequence[str]) -> ArrayRoomRefused:
        return ArrayRoomRefused(why, [line for prefix in prefixes for line in units[prefix].grown])

    spans = {
        prefix: (u.image, u.start, u.end)
        for prefix, u in units.items()
        if not u.table and u.hook is None
    }
    # Every pair that addresses a moving array, with the arrays it addresses: scanned once,
    # read here for who reads each array and below for the rewrites.
    addressing = [
        (source, pair, _addressed(pair, source[0], spans))
        for source, found in ((scanned or (lambda: scans(archive)))() if spans else ())
        for pair in found
    ]
    readers: dict[str, set[str]] = {prefix: set() for prefix in spans}
    for (image, *_), _pair, prefixes in addressing:
        for prefix in prefixes:
            readers[prefix].add(image)
    by_overlay: dict[str, list[str]] = {}
    for prefix, images in readers.items():
        if len(images) != 1:
            continue
        (only,) = images
        if (
            only != "exe"
            and f"{only.upper()}.OVL" not in no_tail
            and units[prefix].image in ("exe", only)
        ):
            by_overlay.setdefault(only, []).append(prefix)

    placed: dict[str, int] = {}
    tails: dict[str, Tail] = {}
    in_tail: dict[str, str] = {}
    for image, candidates in sorted(by_overlay.items()):
        member = archive.member(f"{image.upper()}.OVL")
        tail = overlay_tail(archive, member)
        # Largest first; one that does not fit is tried in the resident room below, and the
        # rest still take the tail.
        prefixes: list[str] = []
        fitted: dict[str, int] = {}
        for p in sorted(candidates, key=lambda p: (-len(units[p].blob), p)):
            trial = _allocate([(q, len(units[q].blob)) for q in (*prefixes, p)], [tail])
            if not isinstance(trial[0], str):
                prefixes.append(p)
                fitted = trial[0]
        if not prefixes:
            continue
        placed |= fitted
        in_tail |= dict.fromkeys(prefixes, member.short_name)
        end = OVERLAY_LOAD_ADDRESS + member.size
        grown = bytearray(max(placed[p] + len(units[p].blob) for p in prefixes) - end)
        for p in prefixes:
            grown[placed[p] - end : placed[p] - end + len(units[p].blob)] = units[p].blob
        lines = tuple(line for p in prefixes for line in units[p].grown)
        tails[member.short_name] = Tail(bytes(grown), lines)

    vacated = [
        _padded(archive, Region(u.start, u.end, f"{prefix}'s old bytes"))
        for prefix, u in units.items()
        if u.image == "exe" and u.end > u.start
    ]
    resident = [(p, len(u.blob)) for p, u in units.items() if p not in placed]
    allocated = _allocate(resident, [*regions, *vacated])
    if isinstance(allocated[0], str):
        prefix, why = allocated
        raise refusal(why, [prefix])
    placed |= allocated[0]
    free_left = allocated[1]

    moved = tuple(
        Moved(p, u.start, placed[p], len(u.blob), in_tail.get(p)) for p, u in units.items()
    )
    edits = [
        ByteEdit(
            file=EXE_NAME,
            offset=m.new - EXE_LOAD_BIAS,
            old=archive.exe_bytes(m.new, m.size),
            new=units[m.prefix].blob,
            reason=f"{m.prefix} moved to 0x{m.new:08X} (PLAN PIPE-07)",
        )
        for m in moved
        if m.tail is None
    ]
    new_start = {m.prefix: m.new for m in moved}
    for prefix, unit in units.items():
        if unit.hook is not None:
            edits += unit.hook(new_start[prefix])
    for prefix, unit in units.items():
        for offset, at in unit.table:
            edits.append(
                ByteEdit(
                    file=ARCHIVE_NAME,
                    offset=offset,
                    old=archive.boku[offset : offset + 4],
                    new=(new_start[prefix] + at).to_bytes(4, "little"),
                    reason=f"{prefix}: pointer table word to its moved text (PLAN PIPE-07)",
                )
            )

    for (image, code, base, file, file_base), pair, addressed in addressing:
        inside = _interior(pair, image, spans)
        if inside:
            raise refusal(
                f"the lui at 0x{pair.ram:08X} ({image}) addresses the inside of "
                f"{', '.join(inside)}, and only an array's start is rewritten",
                inside,
            )
        if addressed:
            moves = {spans[prefix][1]: new_start[prefix] for prefix in addressed}
            try:
                changed = repoint(pair, lambda t, moves=moves: moves.get(t, t), code, base)
            except PointerError as error:
                raise refusal(str(error), addressed) from error
            for ram, word in changed.items():
                edits.append(
                    ByteEdit(
                        file=file,
                        offset=file_base + ram - base,
                        old=code[ram - base : ram - base + 4],
                        new=word.to_bytes(4, "little"),
                        reason=f"{image} 0x{ram:08X}: pointer to a moved array (PLAN PIPE-07)",
                    )
                )
    edits += card_records
    lines = frozenset(line for u in units.values() for line in u.lines)
    return ArrayPlan(tuple(edits), moved, lines, free_left, tails)
