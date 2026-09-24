#!/usr/bin/env python3
"""A card on Beetle PSX, driven in the field from Python (PLAN `ENV-08`).

`sumo_bout.py` and `examine.py` share this: boot a card, land in a chosen map through the dawn
movie's return, stand Boku in an examine zone read from the loaded map, and poll RAM between
frames. research/sumo.md § Reaching a bout says why the route is this one.
"""

from __future__ import annotations

import argparse
import math
import os
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent

import run_core  # noqa: E402 -- beside this file, so on sys.path when run as a script

MODE_ACTIVE = 0x800237E1
"""The running mode (`0x800237E0` is the one asked for; `mode_set` `0x80011A98`)."""
FIELD = 5
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
EXAMINE = 0x20
SETTLE = 1200
"""Frames after arriving before ○ examines (600 was too soon at the secret base, measured)."""


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


def facing(x: int, z: int, px: int, pz: int) -> int:
    """The angle `ev_scan_triggers` wants of Boku at (x, z) examining the point (px, pz), all in
    the zone table's units: `ratan2(x - px, z - pz)`, 4096 to a turn."""
    return round(math.atan2(x - px, z - pz) * 4096 / (2 * math.pi)) & 0xFFF


def examine_placements(game: Game, event: int) -> list[tuple[tuple[int, int], int]]:
    """(point, zone index) of each examine placement of `event` in the loaded map."""
    places_at = game.u32(PLACEMENTS)
    out = []
    for i in range(game.u32(places_at)):
        rec = game.read(places_at + 4 + 20 * i, 20)
        if rec[0x10] == EXAMINE and struct.unpack_from("<h", rec, 0x12)[0] == event:
            out.append((struct.unpack_from("<hxxh", rec, 0), rec[0x11]))
    return out


def examine_zones(game: Game, event: int) -> list[tuple[int, int, int]]:
    """(x, z, angle) for each examine zone of `event`: the zone's centre in Boku's units, facing
    the placement's point."""
    zones_at = game.u32(ZONES)
    out = []
    for (px, pz), zone in examine_placements(game, event):
        halves = struct.unpack("<16h", game.read(zones_at + 4 + 36 * zone, 32))
        cx, cz = sum(halves[0::4]) // 4, sum(halves[2::4]) // 4
        out.append((cx << 4, cz << 4, facing(cx, cz, px, pz)))
    return out


def land_in(game: Game, map_base: str) -> None:
    """Load the card's slot-1 save (`boot-to-save.press`) and, during the dawn movie, point the
    field's return at `map_base` (three characters): the morning starts there."""
    presses = run_core.schedule_presses(
        argparse.Namespace(press=[], press_file=HERE / "boot-to-save.press")
    )
    for f in range(1, RETURN_AT + 1):
        game.fe.buttons = presses.get(f, frozenset())
        game.frame += 1
        game.fe.lib.retro_run()
    name = map_base.encode()
    game.write(MOVIE_RETURN_MAP, name + b"\0")
    game.until(
        map_base,
        lambda: game.read(MODE_ACTIVE, 1)[0] == FIELD and game.read(MAP_NAME, 3) == name,
        6000,
    )
    game.run(SETTLE)  # measured at A18; the same for every map so far


def stand(game: Game, x: int, z: int, angle: int) -> None:
    """Hold Boku at (x, z) facing `angle` for a moment, then let go."""
    for _ in range(30):
        game.write(BOKU, struct.pack("<i", x))
        game.write(BOKU + 8, struct.pack("<i", z))
        game.write(BOKU + 0x12, struct.pack("<h", angle))
        game.run(1)
    game.run(5)
