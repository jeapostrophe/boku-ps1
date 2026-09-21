"""`PIPE-03`'s hard half: moving a member that has outgrown its sectors.

`boku.reinsert` rebuilds a member bottom-up and can make it longer. When the result still
fits the sectors the member already owns, nothing here runs. When it does not, the member
has to **move**, and everything that addresses it has to be rewritten. This module decides
where it moves to; `boku.reinsert` turns that decision into edits.

How a member is addressed — measured, not assumed
-------------------------------------------------
There are exactly two ways, and they differ in what a relocation costs:

* **A top-level member** is `g_cd_dir.lba[i]`, an **absolute disc LBA**, and
  `g_cd_dir.size[i]`, a byte count — two `u32` words in `SCPS_100.88`
  (`research/boku-bin.md`). `cd_load_sync` passes the LBA straight to `CdRead`. So a
  top-level member may be placed at **any** sector of the disc.

* **A `.SEC`-indexed member** is `container_lba + record.sector`, computed at run time by
  the selector that hands the slot to `file_load` — all three selectors are disassembled
  in `research/relocation.md`. The record's `sector` is therefore **relative to the
  container's own `g_cd_dir` entry and unsigned 16-bit**: a member of a sub-archive can be
  placed anywhere in `[lba[container], lba[container] + SECTOR_FIELD_MAX]` — nothing checks
  the container's extent — but **never below `lba[container]`**.

The free space is *below* the archive (the filler before `BOKU.BIN`), so the second rule
bites on every real relocation: the member wants to go somewhere its container's base
cannot reach. The answer is to **rebase the container** — lower `lba[container]` and add
the same delta to every record's `sector`, which leaves every unmoved member exactly where
it is. One `u32` in the executable and one rewrite of a resident index member that is
already being rewritten for the `size` fields. That is this module's whole design.

Where the room is
-----------------
`unclaimed_runs` derives it from the image's own filesystem rather than trusting a number:
the sectors covered by no directory record, no directory extent and not in the system
area. The two runs it finds on the retail disc are `PREFIX_FILLER` and `TAIL_FILLER`, and
a test on the real dump holds the constants against the derivation. Both are zero-filled
Mode 2 **Form 2** filler, so writing a member there means converting the sector to Form 1
(`DiscWriter.write_data_sector`).

Only `PREFIX_FILLER` is allocated from (`DEFAULT_ARENA`). The tail run is out of reach of
any `.SEC` record — 279,000 sectors past the containers, far past the `u16` — and a
top-level member placed there would fall outside the contiguous span the archive is read
back through, so it is counted as reserve by `capacity` and left alone. `BOKU.BIN` itself
tiles exactly (`research/relocation.md`), so it holds no free sector **until a member
moves out of it**.

The sectors a move vacates are the other pool
---------------------------------------------
A member that moves leaves its old sectors behind, and they are as good as the arena for
whatever else has to move: `FreeSpace` hands them out first and spends the arena only on
what they cannot hold. That is what makes a whole translation fit — under the estimate 181
members outgrow their sectors and ask for 11,141, abandoning 10,889, so the arena's 765
answer the *difference* and not the demand (`research/relocation.md` § "Does it fit?").

What it costs is the `.SEC` records' order. A member written into the hole another record
left is out of record order, and the retail invariant "record order is sector order" stops
holding inside a re-laid-out container — `boku.archive._record_order` says what survives of
it and why the alternative was refused. Nothing over the finished image can replace it
there, so what does the work instead is `check_placements` on every layout this module
plans and again before one becomes bytes, `sector_fields` keying a record's new sector by
the member's **name** so that pairing it with the wrong member is unrepresentable, and the
round-trip gate that reads a built image back and compares every line at every copy.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from boku.archive import SECTOR, SUB_ARCHIVES, Archive, DirEntry, Member, read_exe_dir
from boku.disc import DiscImage, form1_sectors

SECTOR_FIELD_MAX: int = 0xFFFF
"""A `.SEC` record's `sector` is read with `lhu`, so a member sits at most this many
sectors past its container's `g_cd_dir` LBA."""


class RelocationRefused(Exception):
    """A member has outgrown its sectors and cannot be given new ones.

    `member` names it when there is one, so a build willing to leave a line in Japanese
    rather than stop (`--skip-unfitted`) knows which lines to drop.
    """

    def __init__(self, message: str, member: str | None = None) -> None:
        super().__init__(message)
        self.member = member


# --- free space, derived from the image ----------------------------------------------------


@dataclass(frozen=True)
class Run:
    """A run of whole sectors, by absolute LBA."""

    start: int
    count: int

    @property
    def end(self) -> int:
        """One past the last sector of the run."""
        return self.start + self.count

    def contains(self, other: Run) -> bool:
        """Is every sector of `other` inside this run?"""
        return self.start <= other.start and other.end <= self.end

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError(f"a run is at least one sector: {self.start} x {self.count}")


PREFIX_FILLER = Run(281, 765)
"""The filler between the `\\__STR` directory and `BOKU.BIN`, owned by no file.

Pinned here rather than derived at run time so a plan can be made from an import with no
image beside it; `unclaimed_runs` is the derivation and a test holds the two together."""

TAIL_FILLER = Run(280020, 150)
"""The filler at the end of the disc. Reserve — see the module docstring."""

DEFAULT_ARENA: tuple[Run, ...] = (PREFIX_FILLER,)
"""What `plan_layout` allocates from unless a caller says otherwise."""

SYSTEM_AREA_SECTORS = 16
"""LBA 0-15: the licence area, before the volume descriptors. In no directory record.

Only a floor — everything below the root directory's own LBA is marked claimed, which on
this disc is 0-21 and swallows the four free sectors at 12-15 as well."""


def unclaimed_runs(image: DiscImage) -> list[Run]:
    """Sector runs of `image` that belong to no file, no directory and no system area.

    The arena, derived from the disc instead of copied out of a note.

    Every extent is counted in whole 2,048-byte sectors, Form 2 files included. Measured
    on this dump: the `\\__STR` records carry XA attributes that set neither form bit, and
    their ISO sizes are exact 2,048 multiples (`BOKU_XA.XAM` 197,535,744 = 96,453 x 2,048),
    so that is their real sector count. An import whose XA records *did* mark Form 2 would
    have sizes in 2,324-byte units and this would over-count — which shrinks the arena and
    is the safe direction; counting them in 2,324s and being wrong would report a free run
    inside the voice bank.
    """
    claimed = bytearray(image.sector_count)

    def mark(lba: int, sectors: int) -> None:
        claimed[lba : lba + sectors] = b"\1" * max(0, min(sectors, image.sector_count - lba))

    volume = image.primary_volume_descriptor()
    mark(0, max(SYSTEM_AREA_SECTORS, volume.root_lba))
    mark(volume.root_lba, form1_sectors(volume.root_size))
    for entry in image.walk():
        mark(entry.lba, entry.sector_count)
    runs: list[Run] = []
    lba = 0
    while lba < len(claimed):
        if claimed[lba]:
            lba += 1
            continue
        end = lba
        while end < len(claimed) and not claimed[end]:
            end += 1
        runs.append(Run(lba, end - lba))
        lba = end
    return runs


def coalesce(runs: Iterable[Run]) -> list[Run]:
    """`runs` sorted by LBA, with touching or overlapping runs merged into one.

    Two members that both move and sat next to each other leave one run, not two, and a
    third member the size of the pair then fits where neither half would have.
    """
    out: list[Run] = []
    for run in sorted(runs, key=lambda run: run.start):
        if out and run.start <= out[-1].end:
            merged = out[-1]
            out[-1] = Run(merged.start, max(merged.end, run.end) - merged.start)
        else:
            out.append(run)
    return out


def subtract(run: Run, taken: Sequence[Run]) -> list[Run]:
    """What is left of `run` once every run in `taken` is removed from it.

    `taken` must already be `coalesce`d — sorted and non-overlapping — because the callers
    subtract the same set from run after run and re-sorting it each time is the whole cost.
    """
    out: list[Run] = []
    cursor = run.start
    for other in taken:
        if other.end <= cursor or other.start >= run.end:
            continue
        if other.start > cursor:
            out.append(Run(cursor, other.start - cursor))
        cursor = max(cursor, other.end)
    if cursor < run.end:
        out.append(Run(cursor, run.end - cursor))
    return out


class FreeSpace:
    """Where a relocated member may be written: what this re-layout vacates, then the arena.

    Two pools, and the order between them is the whole policy. The sectors the moving
    members leave behind are inside `BOKU.BIN` and cost the disc nothing, so they are spent
    first; the arena exists once, so it is spent last and only on what no hole can hold. A
    build that moves one member therefore still puts it in the arena — its own hole is the
    only other room and it is by definition too small — while a whole translation pays the
    arena only the *net* growth (module docstring).

    Inside a pool the fit is the **best** one, not the lowest, and `plan_layout` asks for
    the largest member first; the two halves are one policy and neither is right alone. A
    hole is whatever the members that left it happened to be — on the full-translation
    estimate `coalesce` makes 103 of them, 1 to 1,189 sectors, a third being the one or two
    an `EV` member leaves — so handing a 40-sector member a 106-sector hole strands 66
    sectors the next 60-sector member then cannot use. Measured on that estimate,
    lowest-first runs out of room and this places every member with the arena to spare
    (`research/relocation.md` § "Does it fit?"). Ties go to the lowest LBA, so the same
    request always gets the same answer.
    """

    def __init__(self, arena: Iterable[Run], vacated: Iterable[Run] = ()) -> None:
        self.arena = coalesce(arena)
        self.vacated = coalesce(vacated)

    @property
    def arena_free(self) -> int:
        return sum(run.count for run in self.arena)

    @property
    def vacated_free(self) -> int:
        return sum(run.count for run in self.vacated)

    def take(self, sectors: int) -> int | None:
        """First LBA of a `sectors`-long allocation, or `None` if no run can hold it.

        Whether the caller can *address* the run is not checked here: a `.SEC` record's
        `sector` is a `u16` counted from its container, and `boku.reinsert._sec_edit`
        refuses a member the field cannot reach, with the numbers, before any write.
        """
        for pool in (self.vacated, self.arena):
            best = min(
                ((run.count, run.start, i) for i, run in enumerate(pool) if run.count >= sectors),
                default=None,
            )
            if best is None:
                continue
            _count, start, index = best
            rest = pool[index].count - sectors
            pool[index : index + 1] = [Run(start + sectors, rest)] if rest else []
            return start
        return None


# --- the decision --------------------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """One member that moved: where it was, where it goes, and how big it now is."""

    member: str
    dir_index: int
    sub_index: int | None
    old_lba: int
    old_sectors: int
    lba: int
    size: int

    @property
    def sectors(self) -> int:
        return form1_sectors(self.size)

    @property
    def home(self) -> Run:
        """The sectors the member is written to."""
        return Run(self.lba, self.sectors)

    @property
    def vacated(self) -> Run:
        """The sectors the member leaves behind: free space, and zeroed where unused."""
        return Run(self.old_lba, self.old_sectors)


@dataclass(frozen=True)
class Layout:
    """What one reinsertion has to move, and what it costs.

    A layout with no placements and no rebased container is the **null re-layout**: every
    member stays where the disc put it and not one byte of the directory changes.
    """

    placements: tuple[Placement, ...] = ()
    bases: Mapping[int, int] = field(default_factory=dict)
    """Container `g_cd_dir` index -> its new LBA. Absent means unchanged."""
    free_before: int = 0
    """Arena sectors before the layout was planned; `free_after` is what is left of them.
    The arena only — the sectors the layout's own moves vacate are the other pool, and they
    cost the disc nothing (`FreeSpace`)."""
    free_after: int = 0
    arena: tuple[Run, ...] = ()
    """What was allocatable besides the layout's own holes, carried so that anything given
    a `Layout` can check it (`check_placements`) without being told again which arena it
    was planned against."""

    @property
    def unchanged(self) -> bool:
        return not self.placements and not self.bases

    @property
    def by_member(self) -> dict[str, Placement]:
        return {placement.member: placement for placement in self.placements}


def container_names(archive: Archive) -> dict[int, str]:
    """`g_cd_dir` index -> container name, for the four sub-archives with a `.SEC` index."""
    return {index: entry.name.rsplit("\\", 1)[-1] for index, entry in _containers(archive).items()}


def containers_touched(archive: Archive, layout: Layout) -> dict[int, str]:
    """`g_cd_dir` index -> container name, for every sub-archive the layout disturbs.

    A rebased container moves the origin all its records count from, and a placed member
    changes one record's `sector`, so both mean that container's `.SEC` has to be
    rewritten. Derived rather than listed: `plan_layout` will place a member of any of the
    four sub-archives, and a caller that rewrote only two of them would move a container's
    base and leave its records pointing at where it used to be.
    """
    names = container_names(archive)
    out = {index: names[index] for index in layout.bases if index in names}
    for placement in layout.placements:
        if placement.sub_index is not None and placement.dir_index in names:
            out[placement.dir_index] = names[placement.dir_index]
    return out


def _containers(archive: Archive) -> dict[int, DirEntry]:
    """`g_cd_dir` index -> entry, for the four sub-archives that have a `.SEC` index."""
    out = {}
    for entry in read_exe_dir(archive.exe):
        if entry.name.rsplit("\\", 1)[-1] in SUB_ARCHIVES:
            out[entry.index] = entry
    return out


def needs_room(member: Member, size: int) -> bool:
    """Does `size` bytes of rebuilt member no longer fit the sectors it already owns?"""
    return size > member.sectors * SECTOR


def plan_layout(
    archive: Archive,
    sizes: Mapping[str, int],
    *,
    arena: Sequence[Run] | None = None,
) -> Layout:
    """Decide where every member that has outgrown its sectors goes.

    `sizes` maps a member's short name to its rebuilt byte length; members absent from it,
    and members whose new length still fits, are not touched — which is what makes the
    null re-layout produce no edits at all.

    Every member that has to move is known before the first one is placed, so the sectors
    they all vacate are free space from the start and `FreeSpace` hands them out ahead of
    the arena. The order they are considered in is **largest first** — a hole is a whole
    member and the big ones are the only things a big member fits in, so placing them
    while the big holes are still whole is what keeps the arena out of it. Ties go to
    directory order, so the same input always produces the same image.

    A `.SEC`-indexed member that lands below its container's `g_cd_dir` LBA rebases the
    container (see the module docstring); the new base is the lowest LBA any of its
    members ends up at, so the rebase is as small as the placement requires.
    """
    arena_runs = tuple(DEFAULT_ARENA if arena is None else arena)
    moving = [
        (member, size, form1_sectors(size))
        for member in archive.members
        if (size := sizes.get(member.short_name)) is not None and needs_room(member, size)
    ]
    space = FreeSpace(arena_runs, [Run(member.lba, member.sectors) for member, _s, _n in moving])
    free_before = space.arena_free
    vacated_total = space.vacated_free
    containers = _containers(archive)
    placements: list[Placement] = []
    for member, size, sectors in sorted(moving, key=lambda row: (-row[2], _record_key(row[0]))):
        start = space.take(sectors)
        if start is None:
            raise RelocationRefused(
                f"{member.short_name} is {size} bytes and needs {sectors} sectors; the "
                f"{free_before}-sector arena before BOKU.BIN has {space.arena_free} left "
                f"and {space.vacated_free} of the {vacated_total} sector(s) this re-layout "
                f"vacates are still unclaimed, with no run that long. "
                f"research/relocation.md § 'Where the room is' has the other candidates.",
                member.short_name,
            )
        placements.append(
            Placement(
                member=member.short_name,
                dir_index=member.dir_index,
                sub_index=member.sub_index,
                old_lba=member.lba,
                old_sectors=member.sectors,
                lba=start,
                size=size,
            )
        )
    placements.sort(key=_record_key)
    layout = Layout(
        placements=tuple(placements),
        bases=_rebased(archive, containers, placements),
        free_before=free_before,
        free_after=space.arena_free,
        arena=arena_runs,
    )
    check_placements(archive, layout)
    return layout


def _record_key(member: Member | Placement) -> tuple[int, int]:
    """Directory order: the container's file number, then the record number inside it.

    A top-level member sorts before any record of the same file number, which no archive
    has — it is only there so the key is total."""
    return (member.dir_index, -1 if member.sub_index is None else member.sub_index)


def check_placements(archive: Archive, layout: Layout) -> None:
    """Refuse a layout that is not a re-layout of **this** archive's members.

    Three checks, all of them on the plan:

    * every placement names a member the archive has, at the LBA and record number the
      placement says it came from — which holds by construction for a layout `plan_layout`
      made, and is the acceptance test for one that came from anywhere else;
    * no two placements may be written over one sector;
    * a placement may only be written into space this layout actually frees — the arena,
      or the sectors its own moving members vacate. Anything else would be laid over a
      member that is staying where it is. This is the check with teeth: it is what the
      old ordering rule over the finished image used to make impossible, and it is
      independently derived, from the archive's member map rather than from the layout.

    It does **not** replace `boku.archive._record_order`; the module docstring says what
    does. Called by `plan_layout` on what it just built and by `relocation_edits` before
    any of it becomes bytes, which is the boundary that matters.
    """
    by_name = {member.short_name: member for member in archive.members}
    for placement in layout.placements:
        member = by_name.get(placement.member)
        if member is None:
            raise RelocationRefused(
                f"the layout places {placement.member}, which {archive.source} has no member of",
                placement.member,
            )
        was = (member.dir_index, member.sub_index, member.lba, member.sectors)
        claims = (
            placement.dir_index,
            placement.sub_index,
            placement.old_lba,
            placement.old_sectors,
        )
        if was != claims:
            raise RelocationRefused(
                f"{placement.member}'s placement says record {placement.sub_index} of "
                f"g_cd_dir[{placement.dir_index}] at LBA {placement.old_lba} x"
                f"{placement.old_sectors}, and the archive has record {member.sub_index} of "
                f"g_cd_dir[{member.dir_index}] at LBA {member.lba} x{member.sectors}: the "
                f"layout and the directory disagree about which member this is",
                placement.member,
            )
    ordered = sorted(layout.placements, key=lambda placement: placement.lba)
    for left, right in pairwise(ordered):
        if right.lba < left.home.end:
            raise RelocationRefused(
                f"{left.member} is written to LBA {left.lba}..{left.home.end - 1} and "
                f"{right.member} to LBA {right.lba}..{right.home.end - 1}; one of them "
                f"would be lost",
                right.member,
            )
    free = coalesce(list(layout.arena) + [placement.vacated for placement in layout.placements])
    for placement in layout.placements:
        home = placement.home
        if not any(run.contains(home) for run in free):
            raise RelocationRefused(
                f"{placement.member} is written to LBA {home.start}..{home.end - 1}, which "
                f"this re-layout does not free: a member that is staying where it is would "
                f"be written over",
                placement.member,
            )


def _rebased(
    archive: Archive, containers: Mapping[int, DirEntry], placements: Sequence[Placement]
) -> dict[int, int]:
    """New `g_cd_dir` LBA for each container that now holds a member below its base."""
    out: dict[int, int] = {}
    for placement in placements:
        if placement.sub_index is None:
            continue
        base = containers[placement.dir_index].lba
        low = min(placement.lba, out.get(placement.dir_index, base))
        if low < base:
            out[placement.dir_index] = low
    return out


def sector_fields(
    archive: Archive, layout: Layout, container_index: int
) -> Iterator[tuple[str, int]]:
    """`(member, new sector field)` for every record of one container, after the layout.

    Relative to the container's *new* base, which is what the selector adds at run time.
    Every record is yielded, not only the moved ones: a rebase moves the origin every
    record counts from.

    Keyed by the member's name and not by its record number, because `boku.reinsert`
    applies these to a *fresh parse* of the `.SEC` bytes: a position that had drifted from
    the member map would hand one record another member's sectors, and a re-laid-out
    container is legitimately out of sector order, so nothing downstream would see it.
    Every other member lookup in this package is by name for the same reason
    (`Archive.member`, which refuses an archive with two members alike).
    """
    base = layout.bases.get(container_index, _containers(archive)[container_index].lba)
    moved = layout.by_member
    for member in archive.members:
        if member.dir_index != container_index or member.sub_index is None:
            continue
        placement = moved.get(member.short_name)
        lba = placement.lba if placement is not None else member.lba
        yield member.short_name, lba - base


# --- the capacity question -------------------------------------------------------------------


@dataclass(frozen=True)
class Capacity:
    """How many sectors a translation needs against how many the disc can give it.

    `needed` is the whole new allocation of every member that has to move and `vacated` is
    what those same members abandon, so `net` — the difference — is what the growth costs
    the *disc*, which is the question `research/relocation.md` § "Does it fit?" asks. The
    arena has to cover `net` and not `needed`, because the sectors a move vacates are
    re-used by the other members that move (`FreeSpace`).

    `fits` is therefore a lower bound and not the decision: the vacated sectors come as
    one hole per member, so a member only fits one that is at least as big as it is.
    `plan_layout` is the decision, and it refuses with the numbers.
    """

    needed: int
    """Sectors the members that outgrew their allocation now want."""
    vacated: int
    """Sectors those members already own and abandon, which the re-layout re-uses."""
    members: int
    """How many members those are."""
    arena: int
    """Sectors allocatable by `plan_layout` (the filler before `BOKU.BIN`)."""
    reserve: int
    """Sectors the disc has but this unit does not hand out (the tail filler)."""

    @property
    def net(self) -> int:
        """Sectors the growth adds to the disc's total, holes discounted."""
        return self.needed - self.vacated

    @property
    def fits(self) -> bool:
        """Does the disc have the room at all? `plan_layout` answers whether it can be used."""
        return self.net <= self.arena

    def __str__(self) -> str:
        return (
            f"{self.members} member(s) outgrow their sectors and need {self.needed} new "
            f"sector(s); they abandon {self.vacated} sector(s), so the growth is "
            f"{self.net} net against an arena of {self.arena} "
            f"({self.arena - self.net:+d}), with {self.reserve} more in reserve at the "
            f"end of the disc"
        )


def capacity(archive: Archive, sizes: Mapping[str, int]) -> Capacity:
    """What a whole translation would cost, without planning it.

    `sizes` is every member's rebuilt length. `needed` counts the *whole* new allocation
    of each member that has to move, because a relocated member does not keep its old
    sectors; `vacated` is what it hands back to the next one that moves. The two together
    say how much of the demand the re-layout answers out of itself and how much the disc
    has to find.
    """
    needed = 0
    vacated = 0
    members = 0
    for member in archive.members:
        size = sizes.get(member.short_name)
        if size is None or not needs_room(member, size):
            continue
        members += 1
        needed += form1_sectors(size)
        vacated += member.sectors
    return Capacity(
        needed=needed,
        vacated=vacated,
        members=members,
        arena=sum(run.count for run in DEFAULT_ARENA),
        reserve=TAIL_FILLER.count,
    )


# --- writing into the arena --------------------------------------------------------------------


@dataclass(frozen=True)
class SectorEdit:
    """Whole sectors of the image, addressed by LBA rather than through a file.

    A relocation writes on both sides of `BOKU.BIN`'s extent. The sectors a member vacates
    are always inside it; the member's new home is inside it too when it was given a run
    another member vacated, and in the arena — which belongs to no directory record, and so
    has no extent a `ByteEdit` could name — when it was not. Addressing every one of them by
    LBA is what lets one edit kind describe all of it, and a home inside the file is why
    `boku.reinsert._check_no_double_write` exists. `old` and `new` are Form 1 user data — a
    whole number of 2,048-byte sectors.
    """

    lba: int
    old: bytes
    new: bytes
    reason: str

    def __post_init__(self) -> None:
        if len(self.old) != len(self.new) or len(self.new) % SECTOR or not self.new:
            raise RelocationRefused(
                f"{self.reason}: a sector edit writes a whole number of {SECTOR}-byte "
                f"sectors and never changes a length ({len(self.old)} -> {len(self.new)})"
            )

    @property
    def sectors(self) -> int:
        return len(self.new) // SECTOR

    @property
    def end(self) -> int:
        """One past the last LBA this edit writes."""
        return self.lba + self.sectors

    @property
    def changes(self) -> bool:
        return self.old != self.new


def padded(blob: bytes) -> bytes:
    """`blob` zero-filled to a whole sector — the shape a member has on the disc.

    `research/boku-bin.md` measured that the bytes between a member's size and its sector
    end are zero everywhere; a relocated member keeps that true of its new home.
    """
    return blob.ljust(form1_sectors(len(blob)) * SECTOR, b"\0")


def _span(archive: Archive, run: Run) -> bytes:
    """`run`'s bytes out of the archive's own byte span, or zeros for arena sectors.

    The arena is outside `BOKU.BIN`, so an import that holds only the file has nothing to
    show there; it is zero-filled on the disc (`unclaimed_runs`) and the build verifies
    that against the image before it writes.
    """
    start = (run.start - archive.base_lba) * SECTOR
    length = run.count * SECTOR
    if start < 0 or start + length > len(archive.boku):
        return bytes(length)
    return archive.boku[start : start + length]


def relocation_edits(
    archive: Archive, layout: Layout, blobs: Mapping[str, bytes]
) -> list[SectorEdit]:
    """Every sector a layout writes: each moved member's new home, and what it leaves.

    `blobs` holds the rebuilt bytes of the moved members. A vacated sector is zeroed
    rather than left holding the Japanese, for the reason a shrinking member's tail is
    (`boku.reinsert._grown_member`): the archive's slack is zero everywhere and a ghost
    copy of a line nobody points at is worse than a hole.

    Only the part of a vacated run **no other member was given** is zeroed. Re-using the
    holes means one member's old sectors are usually another's new ones, and zeroing the
    whole run would either erase what was just written there or make the image depend on
    which edit ran last; `check_disjoint` refuses that shape rather than ordering it.
    """
    check_placements(archive, layout)
    edits: list[SectorEdit] = []
    homes = coalesce(placement.home for placement in layout.placements)
    for placement in layout.placements:
        edits.append(
            SectorEdit(
                lba=placement.lba,
                old=_span(archive, placement.home),
                new=padded(blobs[placement.member]),
                reason=(
                    f"{placement.member} relocated to LBA {placement.lba} "
                    f"({placement.sectors} sectors, {placement.size} bytes)"
                ),
            )
        )
    for placement in layout.placements:
        for run in subtract(placement.vacated, homes):
            edits.append(
                SectorEdit(
                    lba=run.start,
                    old=_span(archive, run),
                    new=bytes(run.count * SECTOR),
                    reason=(
                        f"{placement.member}: {run.count} of its {placement.old_sectors} "
                        f"vacated sectors zeroed, from LBA {run.start}"
                    ),
                )
            )
    return [edit for edit in edits if edit.changes]


def check_disjoint(edits: Sequence[SectorEdit]) -> None:
    """Two sector edits over one LBA would make the image depend on their order."""
    for left, right in pairwise(sorted(edits, key=lambda edit: edit.lba)):
        if right.lba < left.end:
            raise RelocationRefused(
                f"{left.reason} and {right.reason} both write LBA {right.lba}; "
                f"one of them would be lost"
            )


__all__ = [
    "DEFAULT_ARENA",
    "PREFIX_FILLER",
    "SECTOR_FIELD_MAX",
    "TAIL_FILLER",
    "Capacity",
    "FreeSpace",
    "Layout",
    "Placement",
    "RelocationRefused",
    "Run",
    "SectorEdit",
    "capacity",
    "check_disjoint",
    "check_placements",
    "container_names",
    "containers_touched",
    "needs_room",
    "padded",
    "plan_layout",
    "relocation_edits",
    "sector_fields",
    "unclaimed_runs",
]
