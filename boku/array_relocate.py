"""`PLAN PIPE-07`: code-file text arrays that outgrow their bytes move, whole.

An array has no slack -- the next symbol starts where it ends -- so an English item longer
than the Japanese one cannot be written in place. What can move is the array: its items
are found by walking control words from its start, and its start is reached only through
the `lui`/`addiu` pairs that build it (`boku.pointers`; no data word points at any array,
`research/text-outside-events.md` § "How the code reaches an array"). So a grown array is
written, all its items back to back, into resident free space, and every pair that
addressed the old start is rewritten to the new one -- in the executable and in every
overlay, since `TITLE` and `HHON` read executable arrays as well as their own.

Where it goes: `SCPS_100.88`'s dead regions (research/text-renderer.md § 6 owns the
list), the tail of the renderer's island past what its edit set uses, and the spans the
moved arrays leave behind. All of it is below the overlay region, so it is resident in
every mode (`boku.build.check_resident`); an overlay's own array may move there too,
because its reader's pair can point anywhere. Placement is largest-first, best-fit, and
running out is a refusal with the numbers, never a truncation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from boku.archive import ARCHIVE_NAME, EXE_LOAD_BIAS, EXE_NAME, OVERLAY_LOAD_ADDRESS, Archive
from boku.arrays import ArrayWalk, relocatable, walk_all
from boku.glyphs import words_to_bytes
from boku.pointers import LuiPair, PointerError, repoint, scan
from boku.reinsert import ByteEdit


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


@dataclass(frozen=True)
class ArrayPlan:
    edits: tuple[ByteEdit, ...]
    moved: tuple[Moved, ...]
    lines: frozenset[str]
    """Every line id of a moved array: written by `edits`, not in place."""
    free_left: int


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


def _allocate(
    wanted: list[tuple[str, int]], regions: Sequence[Region]
) -> tuple[dict[str, int], int] | tuple[str, str]:
    """Largest first, each into the smallest run it fits (4-aligned); on running out,
    `(prefix, why)` for the array that did not fit."""
    free = [(r.start, r.end) for r in regions]
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


def plan_arrays(
    archive: Archive,
    words: Mapping[str, Sequence[int]],
    regions: Sequence[Region] = DEAD_REGIONS,
    scanned: Callable[[], Scanned] | None = None,
) -> ArrayPlan:
    """Move every relocatable array one of whose items `words` grows past its bytes.

    `scanned` supplies `scans(archive)`, called only once something grows; a caller that
    plans more than once memoises it."""
    candidates = {w.array.line_id_prefix: w for w in walk_all(archive) if relocatable(w.array)}
    items = {prefix: _grown_items(w, words) for prefix, w in candidates.items()}
    grown = {prefix: w for prefix, w in candidates.items() if items[prefix]}
    if not grown:
        return ArrayPlan((), (), frozenset(), sum(r.size for r in regions))

    def refusal(why: str, prefixes: Sequence[str]) -> ArrayRoomRefused:
        return ArrayRoomRefused(why, [line for prefix in prefixes for line in items[prefix]])

    spans = {prefix: (w.image, w.start, w.end) for prefix, w in grown.items()}
    blobs = {prefix: _array_bytes(archive, w, words) for prefix, w in grown.items()}
    vacated = [
        Region(w.start, w.end, f"{prefix}'s old bytes")
        for prefix, w in grown.items()
        if w.image == "exe"
    ]
    allocated = _allocate([(p, len(b)) for p, b in blobs.items()], [*regions, *vacated])
    if isinstance(allocated[0], str):
        prefix, why = allocated
        raise refusal(why, [prefix])
    placed, free_left = allocated

    moved = tuple(
        Moved(prefix, w.start, placed[prefix], len(blobs[prefix])) for prefix, w in grown.items()
    )
    edits = [
        ByteEdit(
            file=EXE_NAME,
            offset=m.new - EXE_LOAD_BIAS,
            old=archive.exe_bytes(m.new, m.size),
            new=blobs[m.prefix],
            reason=f"{m.prefix} moved to 0x{m.new:08X} (PLAN PIPE-07)",
        )
        for m in moved
    ]
    new_start = {m.prefix: m.new for m in moved}

    for (image, code, base, file, file_base), pairs in (scanned or (lambda: scans(archive)))():
        for pair in pairs:
            inside = _interior(pair, image, spans)
            if inside:
                raise refusal(
                    f"the lui at 0x{pair.ram:08X} ({image}) addresses the inside of "
                    f"{', '.join(inside)}, and only an array's start is rewritten",
                    inside,
                )
            addressed = _addressed(pair, image, spans)
            if not addressed:
                continue
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
    lines = frozenset(line for w in grown.values() for line in w.line_ids)
    return ArrayPlan(tuple(edits), moved, lines, free_left)
