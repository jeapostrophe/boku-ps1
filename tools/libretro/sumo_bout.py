#!/usr/bin/env python3
"""Boot a bug-sumo card on Beetle PSX and play it into a bout (PLAN `ENV-08`).

    ./make.sh sumo-bout work/saves/corpus/sumo-maxed-cage.mcd     # -> work/sumo-bout/<card>/

The card (slot 1) must wake on a morning `E4025` -- the secret base's desk, the only way into
bug sumo (mode 7) -- can run on, with a bug in the cage's first slot: `boku save --bug`, or the
corpus's `sumo-maxed-cage`. The route is research/sumo.md § Reaching a bout.

The gate: the bout flag must rise and the fighter the game builds from the record must have
the HP, STR and DEF `boku.sumo` predicts for it. Exit 0 then, with `bout.png` and `bout.state`
(resume from it with `run_core.py --state-in`); 11 if a step never came (the message names
it); 12 if the fighter's stats disagree; 13 if the card or import cannot be read.
"""

from __future__ import annotations

import argparse
import math
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

import run_core  # noqa: E402 -- beside this file, so on sys.path when run as a script

from boku.archive import DEFAULT_DISC_DIR, Archive, ArchiveError  # noqa: E402
from boku.save import GameTables, SaveError, body_of, read_card  # noqa: E402
from boku.sumo import CAGE, EMPTY, RECORD, SumoTables, bout_hp  # noqa: E402

EXIT_STEP, EXIT_STATS, EXIT_INPUT = 11, 12, 13

MODE_ACTIVE = 0x800237E1
"""The running mode (`0x800237E0` is the one asked for; `mode_set` `0x80011A98`)."""
FIELD, SUMO = 5, 7
MOVIE_RETURN_MAP = 0x80036588
RETURN_AT = 5100
"""A frame inside the dawn movie after `boot-to-save.press` has loaded the save (Beetle)."""
MAP_NAME = 0x80026C00
ZONES, PLACEMENTS = 0x80026BFC, 0x80026C18
"""Pointers to the loaded map's zone table (`u32 n; n x 36`: four corners, each an `s16 x` and
an `s16 z` in the low halves of two words) and
placement table (`u32 n; n x 20`), as `ev_scan_triggers` (`0x800204E0`) is handed them."""
BOKU = 0x80026C58
"""Boku: `s32 x, y, z` at +0, the facing angle `s16` at +0x12 (4096 to a turn)."""
DESK_EVENT = 4025
EXAMINE = 0x20
HELD = 0x8003E098
"""The bug in Boku's hand at the desk: a cage record, type 99 when empty."""
BOUT = 0x8008EF84
"""1 while a bout runs (measured: 0 at the drum, 1 once the bug is put down)."""
FIGHTER = 0x8008F018
"""Boku's fighter in `MUSI`: `+8 s32` HP, `+0xC` HP before the training bonus, `+0x10` STR,
`+0x12` DEF0, `+0x13` DEF1 (`sumo_stats` `0x80081380`)."""


class StepError(Exception):
    pass


class Game:
    def __init__(self, image: Path, card: bytes, work: Path) -> None:
        (work / "saves").mkdir(parents=True, exist_ok=True)
        self.fe = run_core.Frontend(
            Path(os.environ["BOKU_LIBRETRO_CORE"]),
            Path(os.environ["BOKU_LIBRETRO_SYSTEM"]),
            work / "saves",
            {},
            4,
        )
        self.fe.lib.retro_init()
        if not self.fe.load_game(image, True):
            raise StepError(f"the core refused {image}")
        if self.fe.firmware_missing:
            raise StepError("no BIOS in the system directory: an HLE boot confirms nothing")
        self.fe.lib.retro_set_controller_port_device(0, run_core.DEVICE_JOYPAD)
        self.fe.av_info()
        slot = self.fe.memory(run_core.MEMORY_SAVE_RAM)
        if slot is None or len(slot) != len(card):
            raise StepError("the core's memory card 1 does not take a raw 128 KB card")
        slot[:] = card
        self.ram = self.fe.memory(run_core.MEMORY_SYSTEM_RAM)
        self.frame = 0

    def read(self, addr: int, n: int) -> bytes:
        o = run_core.ram_offset(addr, n)
        return bytes(self.ram[o : o + n])

    def write(self, addr: int, value: bytes) -> None:
        o = run_core.ram_offset(addr, len(value))
        self.ram[o : o + len(value)] = value

    def u32(self, addr: int) -> int:
        return struct.unpack("<I", self.read(addr, 4))[0]

    def run(self, n: int, *buttons: str) -> None:
        self.fe.buttons = frozenset(run_core.BUTTONS[b] for b in buttons)
        for _ in range(n):
            self.frame += 1
            self.fe.lib.retro_run()
        self.fe.buttons = frozenset()

    def press(self, button: str, then: int) -> None:
        self.run(4, button)
        self.run(then)

    def until(self, what: str, test, limit: int) -> None:
        for _ in range(limit):
            if test():
                return
            self.run(1)
        raise StepError(f"{what}: not by frame {self.frame}")


def desk_zones(game: Game) -> list[tuple[int, int, int]]:
    """(x, z, angle) for each examine zone of `E4025` in the loaded map: the zone's centre, in
    Boku's units, with the angle `ev_scan_triggers` wants from there to the placement's point."""
    zones_at, places_at = game.u32(ZONES), game.u32(PLACEMENTS)
    out = []
    for i in range(game.u32(places_at)):
        rec = game.read(places_at + 4 + 20 * i, 20)
        if rec[0x10] != EXAMINE or struct.unpack_from("<h", rec, 0x12)[0] != DESK_EVENT:
            continue
        px, pz = struct.unpack_from("<hxxh", rec, 0)
        halves = struct.unpack("<16h", game.read(zones_at + 4 + 36 * rec[0x11], 32))
        cx, cz = sum(halves[0::4]) // 4, sum(halves[2::4]) // 4
        angle = round(math.atan2(cx - px, cz - pz) * 4096 / (2 * math.pi)) & 0xFFF
        out.append((cx << 4, cz << 4, angle))
    return out


def enter_desk(game: Game) -> None:
    zones = desk_zones(game)
    if not zones:
        raise StepError(f"no examine placement for E{DESK_EVENT} in {game.read(MAP_NAME, 6)!r}")
    for x, z, angle in reversed(zones):  # the first zone sits in a boy's reach: ○ talks
        for _ in range(30):
            game.write(BOKU, struct.pack("<i", x))
            game.write(BOKU + 8, struct.pack("<i", z))
            game.write(BOKU + 0x12, struct.pack("<h", angle))
            game.run(1)
        game.run(5)
        game.press("CIRCLE", 0)
        try:
            game.until("mode 7", lambda: game.read(MODE_ACTIVE, 1)[0] == SUMO, 900)
            return
        except StepError:
            print(f"sumo-bout: zone at {x},{z} facing {angle}: no desk", file=sys.stderr)
    raise StepError(f"none of E{DESK_EVENT}'s {len(zones)} zones opened the desk")


def drive(game: Game) -> None:
    presses = run_core.schedule_presses(
        argparse.Namespace(press=[], press_file=HERE / "boot-to-save.press")
    )
    for f in range(1, RETURN_AT + 1):
        game.fe.buttons = presses.get(f, frozenset())
        game.frame += 1
        game.fe.lib.retro_run()
    game.write(MOVIE_RETURN_MAP, b"A18\0")
    game.until(
        "the secret base (A18)",
        lambda: game.read(MODE_ACTIVE, 1)[0] == FIELD and game.read(MAP_NAME, 3) == b"A18",
        6000,
    )
    game.run(1200)  # the arrival: 600 frames was too soon for ○ to examine (measured)
    enter_desk(game)
    game.run(1100)  # the desk: the insect notebook, the cage, the photo
    game.press("CIRCLE", 900)  # the cage, its first bug
    game.press("CIRCLE", 50)  # "出す" / "もどる"
    game.press("LEFT", 40)
    game.press("CIRCLE", 0)
    game.until("the bug in hand", lambda: game.read(HELD, 1)[0] != EMPTY, 300)
    game.run(400)
    for button, then in (("DOWN", 40), ("RIGHT", 90), ("RIGHT", 50), ("UP", 55)):
        game.press(button, then)  # over to the drum
    game.press("CIRCLE", 0)
    game.until("the bout", lambda: game.read(BOUT, 1)[0] == 1, 900)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("card", type=Path, help="a card whose slot-1 save opens bug sumo")
    p.add_argument("--image", type=Path, default=REPO / "disc" / "image.cue")
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC_DIR)
    p.add_argument("--work", type=Path, help="default work/sumo-bout/<card name>")
    args = p.parse_args(argv)
    try:
        archive = Archive(args.disc)
        tables, sumo = GameTables.read(archive), SumoTables.read(archive)
        card = args.card.read_bytes()
        saves = read_card(card, tables)
        if 1 not in saves:
            raise SaveError(f"no save in slot 1 (slots {sorted(saves)})")
        record = body_of(saves[1], tables).read(CAGE, RECORD)
        want = sumo.stats(record[0], record[1])
    except (SaveError, ArchiveError, OSError, ValueError) as exc:
        print(f"sumo-bout: {args.card}: {exc}", file=sys.stderr)
        return EXIT_INPUT
    work = args.work or REPO / "work" / "sumo-bout" / args.card.stem
    game = Game(args.image, card, work)
    try:
        drive(game)
    except StepError as exc:
        game.fe.screenshot(work / "stuck.png")
        print(f"sumo-bout: {exc}", file=sys.stderr)
        return EXIT_STEP
    hp, hp_max = struct.unpack("<ii", game.read(FIGHTER + 8, 8))  # before any blow lands
    strength, _, d0, d1 = game.read(FIGHTER + 0x10, 4)
    game.run(300)  # the bout on screen
    game.fe.screenshot(work / "bout.png")
    game.fe.save_state(work / "bout.state")
    got = (hp_max, strength, (d0, d1))
    print(
        f"sumo-bout: bout at frame {game.frame}; type {record[0]} size {record[1]}: HP "
        f"{hp_max} (trained {hp}), STR {strength}, DEF {d0}/{d1}; predicted "
        f"{want.hp}, {want.strength}, {want.defence[0]}/{want.defence[1]} -> {work}/bout.png"
    )
    if got != (want.hp, want.strength, want.defence) or hp != bout_hp(want.hp, record[8]):
        return EXIT_STATS
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
