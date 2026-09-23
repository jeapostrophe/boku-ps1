"""Bug sumo's insects: Boku's cage record and the fighter stats a record gives (PLAN `ENV-08`).

`research/sumo.md` is the specification. The per-species base stats and typical sizes are read
from the contributor's own `MUSI.OVL` at the addresses `MUSI`'s own stat code reads them from,
so nothing here is a retyped table.
"""

from __future__ import annotations

from dataclasses import dataclass

from boku.archive import Archive

CAGE = 0x80045A10
"""Boku's cage: `CAGE_SLOTS` records of `RECORD` bytes; the one bug sumo lists and fights from."""
CAGE_SLOTS = 10
RECORD = 12
EMPTY = 99
"""A record whose type is this is an empty slot (every table of insects uses it)."""

SPECIES_STATS = 0x80079E3C
"""`MUSI.OVL`: 8 bytes per species -- u16 HP, u8 STR, DEF0, DEF1, then three bytes copied
unscaled (the debug screen's SPD and SICL are the first two)."""
SPECIES_TYPICAL = 0x80079EA4
"""`MUSI.OVL`: one byte per species -- the size (mm) at which a bug has exactly its base stats."""

TYPES = {
    "miyama": 23, "giant": 24, "flat": 25, "little": 26, "saw": 27, "red-legged": 28,
    "oni": 29, "rhino": 30,
    "miyama-f": 56, "giant-f": 57, "saw-f": 58, "rhino-f": 59, "mantis": 60,
}  # fmt: skip
"""Sumo's insect types (the insect ids of `exe@8003D2E0`; 56-59 share lines 23, 24, 27, 30
through `g_insect_name_remap` -- the females: 57 is drawn with the female mark, measured)."""


def species(kind: int) -> int:
    """`sumo_species` (`MUSI` `0x80081358`): the stat-table row of an insect type."""
    if kind not in TYPES.values():
        raise ValueError(f"insect type {kind} does not fight in bug sumo")
    return kind - 0x17 if kind < 0x1F else kind - 0x30


def scaled(base: int, diff: int) -> int:
    """`sumo_stats` (`MUSI` `0x80081380`): a stat in sixteenths, `v = base << 4`, moved by
    `v // 100` for each millimetre from the typical size -- up above it, down below."""
    v = base << 4
    return v + (v // 100) * diff


@dataclass(frozen=True)
class Stats:
    hp: int
    """In sixteenths, as the fighter's `+8` word holds it."""
    strength: int
    defence: tuple[int, int]


@dataclass(frozen=True)
class SumoTables:
    base: tuple[tuple[int, int, int, int], ...]
    """(HP, STR, DEF0, DEF1) per species row."""
    typical: tuple[int, ...]

    @classmethod
    def read(cls, archive: Archive) -> SumoTables:
        rows = len(TYPES)  # one row per type (`species`)
        raw = archive.overlay_bytes("MUSI.OVL", SPECIES_STATS, 8 * rows)
        base = tuple(
            (int.from_bytes(raw[8 * i : 8 * i + 2], "little"), *raw[8 * i + 2 : 8 * i + 5])
            for i in range(rows)
        )
        return cls(base, tuple(archive.overlay_bytes("MUSI.OVL", SPECIES_TYPICAL, rows)))

    def stats(self, kind: int, size: int) -> Stats:
        """What the game computes for a bug of this type and size (below its typical size the
        same percentage is taken off). The byte stats are stored `(char)(v >> 4)`, so past
        `max_size` they wrap as the game's do."""
        row = species(kind)
        hp, strength, d0, d1 = self.base[row]
        diff = size - self.typical[row]
        return Stats(
            scaled(hp, diff),
            scaled(strength, diff) >> 4 & 0xFF,
            (scaled(d0, diff) >> 4 & 0xFF, scaled(d1, diff) >> 4 & 0xFF),
        )

    def max_size(self, kind: int) -> int:
        """The largest size (a byte) whose byte stats still fit their byte: one millimetre more
        and STR or a DEF wraps round to a weakling."""
        row = species(kind)
        _, *bytes_ = self.base[row]
        for size in range(self.typical[row] + 1, 256):
            if any(scaled(b, size - self.typical[row]) >= 256 << 4 for b in bytes_):
                return size - 1
        return 255


TRAINING_MAX = 250
"""The record's `+8`: 250 is +25 % HP, the most a byte gives in whole steps (`bout_hp`)."""


def bout_hp(hp: int, training: int) -> int:
    """The fighter's HP once the bout starts: up `training // 10` percent (`MUSI`
    `0x80081018`)."""
    return hp + hp * (training // 10) // 100


@dataclass(frozen=True)
class Bug:
    kind: int
    size: int
    number: int = 1
    """The catch number the cage prints beside the name."""
    day: int = 1
    """The day it was caught (the cage prints "caught August n")."""
    wins: int = 0
    losses: int = 0
    training: int = 0

    def record(self) -> bytes:
        """`+2` and `+3` stay 0: the game rewrites `+3` when a bug is taken out, and the badge
        beside the name follows the size, not `+3` (research/sumo.md)."""
        return bytes(
            [self.kind, self.size, 0, 0, self.number, self.day, self.wins, self.losses,
             self.training, 0, 0, 0]
        )  # fmt: skip


def maxed(tables: SumoTables, kind: int, size: int | None = None, number: int = 1,
          day: int = 1) -> Bug:  # fmt: skip
    """Fully trained, at `size` or else the largest its species allows."""
    size = tables.max_size(kind) if size is None else size
    return Bug(kind, size, number, day, training=TRAINING_MAX)


EMPTY_RECORD = bytes([EMPTY]) + bytes(RECORD - 1)


def cage_bytes(bugs: list[Bug]) -> bytes:
    """The whole cage: these bugs from its first slot, the rest empty."""
    if len(bugs) > CAGE_SLOTS:
        raise ValueError(f"the cage holds {CAGE_SLOTS} bugs; asked for {len(bugs)}")
    return b"".join(b.record() for b in bugs) + EMPTY_RECORD * (CAGE_SLOTS - len(bugs))


def parse_bug(text: str) -> tuple[int, int | None]:
    """`NAME[:SIZE]` or `TYPE[:SIZE]` -> (type, size or None for the maxed size)."""
    name, _, size = text.partition(":")
    kind = TYPES[name] if name in TYPES else int(name, 0)
    species(kind)
    if not size:
        return kind, None
    mm = int(size, 0)
    if not 0 <= mm <= 255:
        raise ValueError(f"a size is a byte; got {mm}")
    return kind, mm
