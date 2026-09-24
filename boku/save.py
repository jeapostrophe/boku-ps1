"""Memory-card saves: read, edit and write this game's save file (PLAN `ENV-06`).

`research/save-format.md` is the specification; this module is its executable form. Nothing
about the game is typed here that the import can supply: the list of saved RAM regions, the
file name, the title strings and the icon are all read from the contributor's own
`SCPS_100.88` and `TITLE.OVL` through `Archive`, at the addresses the game's own save code
reads them from, so a card written here holds the same bytes the game would write for the same
state. Why cards are never tracked: research/save-format.md.

A save is progress state and nothing else: the body is 21 RAM regions (`g_save_regions`)
copied end to end. Editing a save therefore means editing RAM bytes by address -- `SaveBody`
maps a RAM address to its place in the body -- and re-summing.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path

from boku.archive import DEFAULT_DISC_DIR, OVERLAY_LOAD_ADDRESS, Archive, ArchiveError
from boku.arrays import SAVE_TITLE_BYTES as TITLE_BYTES
from boku.arrays import ArrayError, read_save_title
from boku.sumo import (
    CAGE,
    STAGE,
    STAGE_MANTIS,
    STAGE_SHORTCUT,
    TYPES,
    SumoTables,
    cage_bytes,
    maxed,
    parse_bug,
)  # fmt: skip

# --- the PS1 memory card (Sony's format; research/save-format.md § "The card") -----------

CARD_BYTES = 128 * 1024
FRAME = 128
BLOCK = 8192
BLOCKS = 16
DIR_IN_USE_FIRST = 0x51
DIR_FREE = 0xA0
NO_NEXT = 0xFFFF
BROKEN_FRAMES = range(16, 36)

# --- this game's save file (research/save-format.md § "The save file") --------------------

SAVE_REGIONS_ADDR = 0x80081410
"""`g_save_regions` in `TITLE.OVL`: the head of `{ptr, len, next}` records `save_gather`
walks. A record whose `next` is 0 ends the list and is not itself saved."""
SAVE_NAME_ADDR = 0x80081400
"""The file-name prefix `save_build`'s caller formats with `"%s%d"` and the slot number."""
ICON_CLUT_ADDR = 0x80028C64
ICON_FRAMES_OFFSET_ADDR = 0x80028C58
"""`save_build` copies 0x20 bytes of CLUT from `ICON_CLUT_ADDR` and 0x180 bytes of icon
frames from `ICON_CLUT_ADDR + *(u32 *)ICON_FRAMES_OFFSET_ADDR`."""

HEADER_TITLE = 0x04
HEADER_CLUT = 0x60
ICON_CLUT_BYTES = 0x20
ICON_FRAMES_BYTES = 0x180
SUMMARY = 0x200
SUMMARY_BYTES = 12
BODY = 0x280
BODY_HEADER = 8
"""`{u32 sum, u32 size}` over the first 8 bytes of the first region."""
RAM_BYTES = 0x200000
ICON_FLAGS = 0x13  # three animation frames
BLOCKS_USED = 1

# --- the RAM the body holds that a corpus edits (research/save-format.md § "The body") -----

G_CLOCK = 0x80028FA0
"""`{u8 day, u8 hour, u8 minute, u8, char *map_name, s16 meal[4]}` (event-scripts.md)."""
G_FLAGS = 0x80035E48
"""`u8 g_flags[256]` (event-scripts.md § Flags)."""
PLAY_TIMER = 0x80025910
"""u32 inside the first region; the file list's PLAYTIME."""
SUMMARY_FLAG = 0x80025914
"""The second-playthrough byte: 1 once a new game starts from a card holding a finished save
(`FINISHED_DAY`); `save_summary_build` stores it beside the day."""
STAR_FLAGS = (237, 238)
"""The ★ bits: `star_set(n)` (`0x800336B8`, PROG 57) ORs bit n into `g_flags[237]` for n < 8,
bit n - 8 into `g_flags[238]` otherwise."""
EPILOGUE_FLAG = 250
"""`ending_pick` writes the epilogue here; `ENDOTI` plays `OTI0n` for n = this flag, and a
finished save keeps it -- Summer Memories' "ending" replays it."""
STAR_BITS = range(1, 16)
"""The bits the game sets: PROG 57 with 2-6 and 8-15, and bits 1 and 7 from `ending_prepare`.
Bit 0 is never set, so there are fifteen stars."""
BEDTIME = (20, 0)
"""The clock written into a generated save: the evening of the day before the morning it
wakes on. Loading any save starts the NEXT day at 07:00 (measured on Beetle)."""


class SaveError(Exception):
    pass


def bytesum(data: bytes) -> int:
    """`bytesum` (`0x8007B014`): a plain add of unsigned bytes into a u32."""
    return sum(data) & 0xFFFFFFFF


def xor8(data: bytes) -> int:
    x = 0
    for b in data:
        x ^= b
    return x


# --- reading the game's own tables out of an import ---------------------------------------


@dataclass(frozen=True)
class Region:
    addr: int
    length: int


def _image_u32s(archive: Archive, ram: int, n: int) -> tuple[int, ...]:
    raw = archive.image_bytes("title" if ram >= OVERLAY_LOAD_ADDRESS else "exe", ram, 4 * n)
    if len(raw) != 4 * n:
        raise SaveError(f"0x{ram:08X} is outside both TITLE.OVL and the executable")
    return struct.unpack(f"<{n}I", raw)


def read_regions(archive: Archive) -> tuple[Region, ...]:
    """Walk `g_save_regions` as `save_gather` does: copy each record until one's `next` is 0."""
    regions: list[Region] = []
    record = SAVE_REGIONS_ADDR
    seen = set()
    while True:
        if record in seen:
            raise SaveError(f"g_save_regions loops at 0x{record:08X}")
        seen.add(record)
        ptr, length, following = _image_u32s(archive, record, 3)
        if following == 0:
            break
        regions.append(Region(ptr, length))
        record = following
    return tuple(regions)


def read_file_prefix(archive: Archive) -> str:
    blob = archive.overlay_bytes("TITLE.OVL", SAVE_NAME_ADDR, 32)
    if b"\0" not in blob:
        raise SaveError(f"no file-name prefix at 0x{SAVE_NAME_ADDR:08X} in TITLE.OVL")
    return blob[: blob.index(b"\0")].decode("ascii", "replace")


def read_icon(archive: Archive) -> bytes:
    """CLUT then frames, as `save_build` lays them out from HEADER_CLUT."""
    (frames_offset,) = _image_u32s(archive, ICON_FRAMES_OFFSET_ADDR, 1)
    clut = archive.exe_bytes(ICON_CLUT_ADDR, ICON_CLUT_BYTES)
    frames = archive.exe_bytes(ICON_CLUT_ADDR + frames_offset, ICON_FRAMES_BYTES)
    return clut + frames


def build_title(parts: tuple[str, ...], digits: tuple[str, ...], slot: int, day: int) -> bytes:
    """`save_title_build` (`0x8007AEF4`): part 0, the slot, part 1, the day, part 2 -- each
    number without a leading zero -- in Shift-JIS."""

    def number(n: int) -> str:
        return (digits[n // 10] if n // 10 else "") + digits[n % 10]

    text = parts[0] + number(slot) + parts[1] + number(day) + parts[2]
    raw = text.encode("shift_jis")
    if len(raw) >= TITLE_BYTES:
        raise SaveError(f"save title is {len(raw)} bytes; the header holds {TITLE_BYTES - 1}")
    return raw


@dataclass(frozen=True)
class GameTables:
    """Everything a save needs from the import, read once."""

    regions: tuple[Region, ...]
    file_prefix: str
    icon: bytes
    title_parts: tuple[str, ...]
    title_digits: tuple[str, ...]
    sumo: SumoTables | None = None
    """What a cage of bugs needs (`boku.sumo`)."""

    @classmethod
    def read(cls, archive: Archive) -> GameTables:
        title = read_save_title(archive)
        return cls(
            read_regions(archive),
            read_file_prefix(archive),
            read_icon(archive),
            title.parts,
            title.digits,
            SumoTables.read(archive),
        )

    @property
    def body_size(self) -> int:
        return body_size(self.regions)


# --- the body -----------------------------------------------------------------------------


def body_size(regions: tuple[Region, ...]) -> int:
    return sum(r.length for r in regions)


def ram_offset(addr: int, n: int = 1) -> int:
    """Byte offset into main RAM of an address in any of its mirrors (KUSEG, KSEG0, KSEG1).
    `tools/libretro/run_core.py` keeps its own copy: it is standard library only."""
    if addr >> 28 not in (0x0, 0x8, 0xA) or (addr & 0x1FFFFFFF) + n > RAM_BYTES:
        raise SaveError(f"0x{addr:08X}+{n} is not main RAM")
    return addr & 0x1FFFFFFF


class SaveBody:
    """The saved regions, addressable by RAM address."""

    def __init__(self, regions: tuple[Region, ...], data: bytes) -> None:
        size = body_size(regions)
        if len(data) != size:
            raise SaveError(f"a body for these regions is {size} bytes, got {len(data)}")
        self.regions = regions
        self.data = bytearray(data)
        self._starts: list[int] = []
        at = 0
        for r in regions:
            self._starts.append(at)
            at += r.length

    @classmethod
    def from_ram(cls, regions: tuple[Region, ...], ram: bytes) -> SaveBody:
        """From a main-RAM dump (`run_core.py --ram-out`)."""
        if len(ram) != RAM_BYTES:
            raise SaveError(f"a main-RAM dump is {RAM_BYTES} bytes, got {len(ram)}")
        out = bytearray()
        for r in regions:
            lo = ram_offset(r.addr, r.length)
            out += ram[lo : lo + r.length]
        return cls(regions, bytes(out))

    def _offset(self, addr: int, n: int) -> int:
        """`addr` may be in any RAM mirror; the regions are compared by RAM offset."""
        at = ram_offset(addr, n)
        for r, start in zip(self.regions, self._starts, strict=True):
            lo = ram_offset(r.addr)
            if lo <= at and at + n <= lo + r.length:
                return start + at - lo
        raise SaveError(f"RAM 0x{addr:08X}+{n} is not inside one saved region")

    def read(self, addr: int, n: int = 1) -> bytes:
        o = self._offset(addr, n)
        return bytes(self.data[o : o + n])

    def write(self, addr: int, value: bytes) -> None:
        if not value:
            raise SaveError(f"nothing to write at 0x{addr:08X}")
        o = self._offset(addr, len(value))
        if o < BODY_HEADER:
            raise SaveError(
                f"0x{addr:08X} is the body's sum and size, which packing overwrites; the first "
                f"writable byte is 0x{self.regions[0].addr + BODY_HEADER:08X}"
            )
        self.data[o : o + len(value)] = value

    def u32(self, addr: int) -> int:
        return int.from_bytes(self.read(addr, 4), "little")

    def flag(self, n: int) -> int:
        return self.read(G_FLAGS + n)[0]

    def set_flag(self, n: int, value: int) -> None:
        if not 0 <= n < 256 or not 0 <= value < 256:
            raise SaveError(f"flag {n} = {value}: flags are u8[256]")
        self.write(G_FLAGS + n, bytes([value]))

    @property
    def clock(self) -> tuple[int, int, int]:
        day, hour, minute = self.read(G_CLOCK, 3)
        return day, hour, minute

    def set_clock(self, day: int, hour: int, minute: int) -> None:
        self.write(G_CLOCK, bytes([day, hour, minute]))

    @property
    def stars(self) -> int:
        """The ★ mask as `ending_pick` (`0x8002E848`) reads it: flag 237 low, 238 high."""
        return self.flag(STAR_FLAGS[0]) | self.flag(STAR_FLAGS[1]) << 8

    def set_stars(self, mask: int) -> None:
        if not 0 <= mask <= 0xFFFF:
            raise SaveError(f"star mask 0x{mask:X} is wider than 16 bits")
        self.set_flag(STAR_FLAGS[0], mask & 0xFF)
        self.set_flag(STAR_FLAGS[1], mask >> 8)

    def packed(self) -> bytes:
        """The body as the card holds it: the first 8 bytes become `{u32 sum, u32 size}`,
        `sum` over all `size` bytes with its own field zeroed (`save_build`)."""
        out = bytearray(self.data)
        out[0:BODY_HEADER] = struct.pack("<II", 0, len(out))
        out[0:4] = struct.pack("<I", bytesum(out))
        return bytes(out)

    @classmethod
    def unpack(cls, regions: tuple[Region, ...], blob: bytes) -> SaveBody:
        """The inverse, refusing a body `save_verify` (`0x8007A9D4`) would refuse."""
        stored_sum, size = struct.unpack_from("<II", blob, 0)
        expected = body_size(regions)
        if size != expected:
            raise SaveError(f"body size field is {size}; these regions total {expected}")
        body = bytearray(blob[:size])
        body[0:4] = bytes(4)
        if bytesum(body) != stored_sum:
            raise SaveError(f"body sum is 0x{stored_sum:X}; the bytes sum to 0x{bytesum(body):X}")
        return cls(regions, bytes(blob[:size]))


def epilogue_for(stars: int) -> int:
    """Which `ENDOTI` epilogue (`g_flags[250]`, `OTI0n`) `ending_pick` chooses for a ★ mask:
    it counts all 16 bits, then 13+ -> 3, 10-12 -> 1, 7-9 -> 0, 4-6 -> 2, 0-3 -> 4."""
    count = bin(stars & 0xFFFF).count("1")
    if count > 12:
        return 3
    if count > 9:
        return 1
    if count > 6:
        return 0
    if count > 3:
        return 2
    return 4


def star_mask(count: int) -> int:
    """The first `count` star bits the game uses -- bit 1 upward, bit 0 never."""
    if not 0 <= count <= len(STAR_BITS):
        raise SaveError(f"there are {len(STAR_BITS)} stars; asked for {count}")
    return sum(1 << b for b in STAR_BITS[:count])


# --- the save file and the card -----------------------------------------------------------


def build_save_file(tables: GameTables, body: SaveBody, slot: int) -> bytes:
    """One 8 KB block laid out as `save_build` (`0x8007B100`) lays it out."""
    day = body.clock[0]
    out = bytearray(BLOCK)
    out[0:4] = bytes([ord("S"), ord("C"), ICON_FLAGS, BLOCKS_USED])
    title = build_title(tables.title_parts, tables.title_digits, slot, day)
    out[HEADER_TITLE : HEADER_TITLE + len(title)] = title
    out[HEADER_CLUT : HEADER_CLUT + len(tables.icon)] = tables.icon
    summary = bytearray(SUMMARY_BYTES)
    struct.pack_into("<IIBB", summary, 0, 0, body.u32(PLAY_TIMER), day, body.read(SUMMARY_FLAG)[0])
    struct.pack_into("<I", summary, 0, bytesum(summary))
    out[SUMMARY : SUMMARY + SUMMARY_BYTES] = summary
    packed = body.packed()
    if BODY + len(packed) > BLOCK:
        raise SaveError(f"a {len(packed)}-byte body does not fit one block")
    out[BODY : BODY + len(packed)] = packed
    return bytes(out)


def _frame(data: bytes) -> bytes:
    frame = bytearray(FRAME)
    frame[: len(data)] = data
    frame[FRAME - 1] = xor8(frame[: FRAME - 1])
    return bytes(frame)


def format_card() -> bytearray:
    """An empty card as Beetle formats one (`InputDevice_Memcard_Format`): header, 15 free
    directory frames, an empty broken-sector list, everything else zero."""
    card = bytearray(CARD_BYTES)
    card[0:FRAME] = _frame(b"MC")
    for i in range(1, BLOCKS):
        card[i * FRAME : (i + 1) * FRAME] = _frame(struct.pack("<IIH", DIR_FREE, 0, NO_NEXT))
    for i in BROKEN_FRAMES:
        card[i * FRAME : (i + 1) * FRAME] = _frame(struct.pack("<IIH", 0xFFFFFFFF, 0, NO_NEXT))
    return card


def write_card(saves: dict[int, bytes], tables: GameTables) -> bytes:
    """A formatted card holding each `{slot: save file}` in consecutive blocks from 1."""
    if len(saves) > BLOCKS - 1:
        raise SaveError(f"a card holds {BLOCKS - 1} one-block saves")
    card = format_card()
    for block, (slot, data) in enumerate(sorted(saves.items()), start=1):
        if not 1 <= slot < BLOCKS:
            raise SaveError(f"slot {slot}: the game's slots run 1-{BLOCKS - 1}")
        if len(data) != BLOCK:
            raise SaveError(f"slot {slot}'s file is {len(data)} bytes, not one block")
        name = f"{tables.file_prefix}{slot}".encode("ascii")
        entry = struct.pack("<IIH", DIR_IN_USE_FIRST, BLOCK, NO_NEXT) + name
        card[block * FRAME : (block + 1) * FRAME] = _frame(entry)
        card[block * BLOCK : (block + 1) * BLOCK] = data
    return bytes(card)


def read_card(card: bytes, tables: GameTables) -> dict[int, bytes]:
    """`{slot: save file}` for every one of this game's files on a card."""
    if len(card) != CARD_BYTES or card[0:2] != b"MC":
        raise SaveError("not a raw 128 KB memory card image (no 'MC' header)")
    out: dict[int, bytes] = {}
    prefix = tables.file_prefix.encode("ascii")
    for block in range(1, BLOCKS):
        entry = card[block * FRAME : (block + 1) * FRAME]
        state = int.from_bytes(entry[0:4], "little")
        name = entry[10:31].split(b"\0")[0]
        if state == DIR_IN_USE_FIRST and name.startswith(prefix):
            suffix = name[len(prefix) :].decode("ascii", "replace")
            if not suffix.isdigit():
                raise SaveError(f"directory entry {block} names {name!r}: no slot number")
            out[int(suffix)] = card[block * BLOCK : (block + 1) * BLOCK]
    return out


def body_of(save_file: bytes, tables: GameTables) -> SaveBody:
    if save_file[0:2] != b"SC":
        raise SaveError("save file has no 'SC' header")
    summary = bytearray(save_file[SUMMARY : SUMMARY + SUMMARY_BYTES])
    stored = int.from_bytes(summary[0:4], "little")
    summary[0:4] = bytes(4)
    if bytesum(summary) != stored:
        raise SaveError("slot summary sum does not match")
    return SaveBody.unpack(tables.regions, save_file[BODY:])


# --- a corpus -----------------------------------------------------------------------------


LAST_DAY = 31
FINISHED_DAY = 31
"""A save whose summary day is at least this is a finished game: the card scan in `TITLE.OVL`
(`mc_summary_scan` `0x8007B65C`) lists it in red, Summer Memories opens it, and a New Game
started from that card sets `SUMMARY_FLAG` (research/save-format.md § A finished game)."""
ENDING_STAR_COUNTS = (0, 5, 8, 11, 15)
"""One count inside each of `ending_pick`'s five bands."""
TICKS_PER_SECOND = 60
"""`PLAY_TIMER` and the file list's PLAYTIME count 60 a second (measured on Beetle)."""


@dataclass(frozen=True)
class CorpusEntry:
    """One save: the evening it is saved on (it wakes the next morning), and its edits.
    `play_hours` sets the play timer, which the file list shows -- a way to tell apart saves
    that share a day on one card."""

    name: str
    saved_day: int
    kind: str = "morning"
    """`morning`, `ending`, `finished` or `sumo`: which card of `card_sets` it goes on."""
    stars: int | None = None
    flags: tuple[tuple[int, int], ...] = ()
    play_hours: int | None = None
    cage: tuple[tuple[int, int | None], ...] = ()
    """Boku's cage from its first slot, as (insect type, size or None for the largest); fully
    trained, caught on the save's day (`boku.sumo.maxed`). The rest of the cage is emptied."""
    pokes: tuple[tuple[int, bytes], ...] = ()
    """Other saved RAM to set, by address."""
    note: str = ""
    """What the save is for, when its day and stars do not say it (INDEX.tsv)."""

    @property
    def finished(self) -> bool:
        return self.saved_day >= FINISHED_DAY

    def why(self) -> str:
        wake = f"wakes on the morning of August {self.saved_day + 1}"
        if self.note:
            return f"{wake}: {self.note}"
        if self.stars is None and not self.finished:
            return wake
        stars = self.stars or 0
        count, epilogue = stars.bit_count(), f"epilogue OTI0{epilogue_for(stars)}"
        if self.finished:
            return (
                f"a finished game with {count} stars: Summer Memories opens, and its "
                f"ending replays {epilogue}"
            )
        return f"{wake} with {count} stars (mask 0x{stars:04X}): the ending picks {epilogue}"


SUMO_DAY = 10
"""The morning the sumo save wakes on: `E4025`, the secret base's desk, wants a day before 28
and not 15."""
SUMO_FLAGS = ((25, 2), (30, 1))
"""`E4025`'s flags: Guts's pact made, all three boys met."""
MANTIS_FLAGS = (*SUMO_FLAGS, (64, 2), (65, 2), (68, 1))
"""Guts's secret-weapon chain up to the fight: his rhinoceros beaten (64), the weapon
announced (65, which also keeps `E1650` from playing), the challenge made (68 = 1: the next
visit to the desk is against Guts)."""
SHORTCUT_FLAGS = (*SUMO_FLAGS, (64, 2), (65, 2), (68, 2), (69, 1), (70, 1))
"""As a Beetle run left them after the mantis was beaten and `E1754` played: 69 the mantis
beaten, 70 the shortcut known."""
SUMO_CAGE = tuple(
    (TYPES[name], None)
    for name in ("giant-f", "rhino", "giant", "rhino-f", "miyama-f", "oni", "red-legged",
                 "miyama", "flat", "saw")
)  # fmt: skip
"""The ten beetles the sumo save's cage holds, each at its largest size (`boku.sumo.maxed`),
roughly strongest first (research/sumo.md)."""


def corpus() -> list[CorpusEntry]:
    entries = [CorpusEntry(f"day{d:02d}", d - 1) for d in range(2, LAST_DAY + 1)]
    for kind, day in (("ending", LAST_DAY - 1), ("finished", FINISHED_DAY)):
        for count in ENDING_STAR_COUNTS:
            mask = star_mask(count)
            name = f"{kind}-oti{epilogue_for(mask)}-{count:02d}stars"
            entries.append(CorpusEntry(name, day, kind, mask, play_hours=count))
    entries += [
        CorpusEntry(
            "sumo-maxed-cage", SUMO_DAY - 1, "sumo", flags=SUMO_FLAGS, cage=SUMO_CAGE,
            play_hours=1, note="bug sumo open, ten maxed beetles in the cage",
        ),
        CorpusEntry(
            "sumo-mantis-ready", SUMO_DAY - 1, "sumo", flags=MANTIS_FLAGS, cage=SUMO_CAGE,
            pokes=((STAGE, bytes([STAGE_MANTIS])),), play_hours=2,
            note="the mantis fight is next: at the desk take a bug, set the rank board to "
            "King, put the bug down, ring the gong",
        ),
        CorpusEntry(
            "shortcut-open", SUMO_DAY - 1, "sumo", flags=SHORTCUT_FLAGS, cage=SUMO_CAGE,
            pokes=((STAGE, bytes([STAGE_SHORTCUT])),), play_hours=3,
            note="the mantis beaten and the secret shortcut shown: examine the spot by the "
            "tool store (A07) to take it",
        ),
    ]  # fmt: skip
    return entries


def edited_body(base: SaveBody, entry: CorpusEntry, sumo: SumoTables | None = None) -> SaveBody:
    body = SaveBody(base.regions, bytes(base.data))
    body.set_clock(entry.saved_day, *BEDTIME)
    if entry.stars is not None:
        body.set_stars(entry.stars)
    if entry.finished:
        finish(body)
    for n, v in entry.flags:
        body.set_flag(n, v)
    for addr, value in entry.pokes:
        body.write(addr, value)
    if entry.play_hours is not None:
        body.write(PLAY_TIMER, struct.pack("<I", entry.play_hours * 3600 * TICKS_PER_SECOND))
    if entry.cage:
        if sumo is None:
            raise SaveError("a cage needs the sumo tables (GameTables.read gives them)")
        bugs = [
            maxed(sumo, kind, size, number=i, day=entry.saved_day)
            for i, (kind, size) in enumerate(entry.cage, 1)
        ]
        try:
            body.write(CAGE, cage_bytes(bugs))
        except ValueError as exc:
            raise SaveError(str(exc)) from exc
    return body


def finish(body: SaveBody) -> None:
    """What the ending leaves in a save besides the day: `ending_pick`'s epilogue."""
    body.set_flag(EPILOGUE_FLAG, epilogue_for(body.stars))


def card_sets() -> dict[str, list[CorpusEntry]]:
    """The corpus packed for a player: `{file name: saves}`, save n in slot n -- the order the
    game's file list shows them. Mornings fill two cards in day order; the five ending bands
    share one (PLAYTIME shows the star count in hours); the finished games get a card of their
    own, because a New Game started from a card holding one is a second playthrough."""
    entries = corpus()
    mornings = [e for e in entries if e.kind == "morning"]
    sets = {}
    for i in range(0, len(mornings), BLOCKS - 1):
        chunk = mornings[i : i + BLOCKS - 1]
        first, last = chunk[0].saved_day + 1, chunk[-1].saved_day + 1
        sets[f"boku-mornings-aug{first:02d}-aug{last:02d}.mcd"] = chunk
    sets["boku-endings-by-stars.mcd"] = [e for e in entries if e.kind == "ending"]
    sets["boku-finished-game.mcd"] = [e for e in entries if e.kind == "finished"]
    sets["boku-bug-sumo.mcd"] = [e for e in entries if e.kind == "sumo"]
    return sets


def corpus_sets() -> dict[str, list[CorpusEntry]]:
    """The corpus a save per card, for the headless tools (each boots slot 1)."""
    return {f"{e.name}.mcd": [e] for e in corpus()}


def write_set(base: SaveBody, tables: GameTables, entries: list[CorpusEntry]) -> bytes:
    return write_card(
        {
            n: build_save_file(tables, edited_body(base, e, tables.sumo), n)
            for n, e in enumerate(entries, 1)
        },
        tables,
    )


def load_base(path: Path, tables: GameTables, slot: int) -> SaveBody:
    """A base state: a raw card (`.mcd`/`.mcr`, its save in `slot`) or a 2 MB RAM dump."""
    raw = path.read_bytes()
    if len(raw) == CARD_BYTES:
        saves = read_card(raw, tables)
        if slot not in saves:
            raise SaveError(f"{path} holds no save in slot {slot} (it has {sorted(saves)})")
        return body_of(saves[slot], tables)
    if len(raw) == RAM_BYTES:
        return SaveBody.from_ram(tables.regions, raw)
    raise SaveError(
        f"{path} is {len(raw)} bytes: a base is a raw card ({CARD_BYTES}) or a main-RAM dump "
        f"({RAM_BYTES})"
    )


# --- command line -------------------------------------------------------------------------


def _pair(text: str) -> tuple[int, int]:
    key, sep, value = text.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError(f"want N=V, got {text!r}")
    return int(key, 0), int(value, 0)


def _poke(text: str) -> tuple[int, bytes]:
    """ADDR=HEX, the spelling run_core's --poke takes; `SaveBody.write` checks the address."""
    key, sep, value = text.partition("=")
    try:
        addr, data = int(key, 16), bytes.fromhex(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"want ADDR=HEXBYTES, got {text!r}") from exc
    if not sep or not data:
        raise argparse.ArgumentTypeError(f"want ADDR=HEXBYTES, got {text!r}")
    return addr, data


def _bug(text: str) -> tuple[int, int | None]:
    try:
        return parse_bug(text)
    except (KeyError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"{text!r}: not a sumo insect ({exc})") from exc


def main_save(args: argparse.Namespace) -> int:
    try:
        edited = args.day is not None or args.finished or args.stars is not None
        edited = edited or args.stars_mask is not None or args.flag or args.poke or args.bug
        whole = "--corpus" if args.corpus else "--cards" if args.cards else None
        if whole and edited:
            raise SaveError(
                f"{whole} writes its own days and stars and takes no --day, --finished, "
                "--stars, --stars-mask, --flag, --poke or --bug; build a single card for an "
                "edited state"
            )
        tables = GameTables.read(Archive(args.disc))
        base = load_base(args.base, tables, args.slot)
        if whole:
            sets = corpus_sets() if args.corpus else card_sets()
            args.out.mkdir(parents=True, exist_ok=True)
            index = []
            for name, entries in sets.items():
                (args.out / name).write_bytes(write_set(base, tables, entries))
                index += [
                    f"{name}\t{slot}\t{e.saved_day}\t{e.why()}" for slot, e in enumerate(entries, 1)
                ]
            (args.out / "INDEX.tsv").write_text(
                "card\tslot\tsaved_on_august\twhat\n" + "\n".join(index) + "\n"
            )
            print(f"save: {len(sets)} cards in {args.out}/ (INDEX.tsv lists them)")
            return 0
        if args.finished:
            saved = FINISHED_DAY
        elif args.day is not None:
            saved = args.day - 1
        else:
            saved = base.clock[0]
        entry = CorpusEntry(
            args.out.stem,
            saved,
            stars=star_mask(args.stars) if args.stars is not None else args.stars_mask,
            flags=tuple(args.flag),
            cage=tuple(args.bug),
        )
        body = edited_body(base, entry, tables.sumo)
        for addr, value in args.poke:
            body.write(addr, value)
        card = write_card({args.slot: build_save_file(tables, body, args.slot)}, tables)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(card)
        day, hour, minute = body.clock
        what = "a finished game" if day >= FINISHED_DAY else f"wakes on August {day + 1}"
        print(
            f"save: {args.out} -- slot {args.slot}, saved on August {day} at {hour:02d}:"
            f"{minute:02d}, {what}; stars 0x{body.stars:04X} "
            f"(epilogue OTI0{epilogue_for(body.stars)})"
        )
        return 0
    except (SaveError, ArchiveError, ArrayError, OSError) as exc:
        print(f"save: {exc}")
        return 1


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--base",
        type=Path,
        required=True,
        help="the state to start from: a card image (its save in --slot) or a main-RAM dump "
        "(`./make.sh saves` makes work/saves/newgame.ram)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="the card (or, with --corpus, the directory) to write",
    )
    parser.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        help="the import to read the game's tables from (default disc/)",
    )
    whole = parser.add_mutually_exclusive_group()
    whole.add_argument(
        "--corpus",
        action="store_true",
        help="write the whole corpus into --out, a save per card: every morning, the five ending "
        "bands, and the same five as finished games",
    )
    whole.add_argument(
        "--cards",
        action="store_true",
        help="write the corpus packed for a player into --out: a few cards of up to 15 saves "
        "(research/save-format.md § Playing a generated save in DuckStation)",
    )
    when = parser.add_mutually_exclusive_group()
    when.add_argument(
        "--finished",
        action="store_true",
        help="save after the ending (August 31): a finished game, which opens Summer Memories",
    )
    when.add_argument(
        "--day",
        type=int,
        choices=range(2, LAST_DAY + 1),
        metavar="2..31",
        help="the morning to wake on (the save is made the evening before)",
    )
    stars = parser.add_mutually_exclusive_group()
    stars.add_argument(
        "--stars",
        type=int,
        choices=range(len(STAR_BITS) + 1),
        metavar="0..15",
        help="set this many ★ bits (which epilogue the ending picks)",
    )
    stars.add_argument(
        "--stars-mask",
        type=lambda t: int(t, 0),
        metavar="MASK",
        help="set g_flags[237..238] to exactly this 16-bit mask",
    )
    parser.add_argument(
        "--flag",
        type=_pair,
        action="append",
        default=[],
        metavar="N=V",
        help="set g_flags[N] = V; repeatable",
    )
    parser.add_argument(
        "--poke",
        type=_poke,
        action="append",
        default=[],
        metavar="ADDR=HEX",
        help="write bytes at a saved RAM address; repeatable",
    )
    parser.add_argument(
        "--bug",
        type=_bug,
        action="append",
        default=[],
        metavar="NAME[:SIZE]",
        help="put a bug in Boku's cage, in order from its first slot: rhino, rhino-f, giant, "
        "giant-f, miyama, miyama-f, saw, saw-f, flat, little, red-legged, oni, mantis (not "
        "tried in a bout), or an insect type; at its largest size unless SIZE is given, and "
        "fully trained either way (research/sumo.md); repeatable, up to 10",
    )
    parser.add_argument(
        "--slot",
        type=int,
        default=1,
        choices=range(1, BLOCKS),
        metavar="1..15",
        help="the save slot (default 1; the file list opens on slot 1)",
    )
    parser.set_defaults(run=main_save)
    return parser
