#!/usr/bin/env python3
"""Poke main RAM inside a Beetle PSX (mednafen_psx) libretro save state, and read it back.

Beetle has no debugger, but a `retro_serialize` state carries the 2 MB of main RAM at
offset `RAM_OFFSET` (found by searching a state for the executable's own text segment;
`research/diary-redraw.md`). So the RAM writes a PCSX-Redux script would make through
`PCSX.getMemPtr()` can be made to a state file instead, and `tools/libretro/run_core.py
--state-in` runs the game from it. Everything here is bytes at RAM addresses; the
addresses and what they mean belong to the research notes that name them.

    state_poke.py IN.state OUT.state --map G01          # the MAP opcode's request words
    state_poke.py IN.state OUT.state --day 2 --hour 10  # g_clock
    state_poke.py IN.state OUT.state --fill 0x801FD700 0x801FF700 0xEE
    state_poke.py IN.state --scan 0x801FD700 0x801FF700 0xEE   # lowest byte that changed
    state_poke.py IN.state OUT.state --word 0x8002982C 0x8002A19C  # any u32, repeatable

`--map` writes what `map_request` (`0x80017A04`) writes, as `tools/vwf/reach-select.lua`
does from Lua: the base name, the request pointer, the one-shot flag and the two bits.
`--scan` is the read-back for a `--fill` made earlier: it prints the lowest address in the
range whose byte is no longer the sentinel: the stack's low-water mark, when nothing but the
stack writes the range (`tools/vwf/stack-probe.lua` measures on Redux).
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

RAM_OFFSET = 0x7F
RAM_SIZE = 0x200000

REQ_NAME, REQ_PTR, REQ_BLOCK = 0x80026C48, 0x80026BD0, 0x80026C20
REQ_FLAGS, REQ_ONE = 0x80024714, 0x80024728
G_CLOCK = 0x80028FA0
"""`{u8 day @0, u8 hour @1, u8 minute @2}` as `tools/vwf/reach-select.lua` reads it."""


def ram_offset(address: int, count: int = 1) -> int:
    physical = address & 0x1FFFFFFF
    if (address >> 28) not in (0, 8, 0xA) or physical + count > RAM_SIZE:
        raise SystemExit(f"0x{address:08X} is not main RAM")
    return RAM_OFFSET + physical


def parse_int(text: str) -> int:
    return int(text, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("state", type=Path)
    parser.add_argument("out", type=Path, nargs="?", help="omit with --scan alone")
    parser.add_argument("--map", metavar="BASE", help="request this map base name (G01, H06)")
    parser.add_argument("--day", type=int)
    parser.add_argument("--hour", type=int)
    parser.add_argument("--minute", type=int)
    parser.add_argument(
        "--fill", nargs=3, type=parse_int, metavar=("LO", "HI", "BYTE"), help="[LO, HI) := BYTE"
    )
    parser.add_argument(
        "--scan", nargs=3, type=parse_int, metavar=("LO", "HI", "BYTE"), help="report the change"
    )
    parser.add_argument(
        "--word",
        nargs=2,
        type=parse_int,
        action="append",
        default=[],
        metavar=("ADDRESS", "VALUE"),
        help="write one little-endian u32; repeatable (a table entry is several)",
    )
    args = parser.parse_args(argv)

    data = bytearray(args.state.read_bytes())
    if len(data) < RAM_OFFSET + RAM_SIZE:
        raise SystemExit(f"{args.state} is too small to hold main RAM at 0x{RAM_OFFSET:X}")

    if args.scan:
        low, high, sentinel = args.scan
        touched = [a for a in range(low, high) if data[ram_offset(a)] != sentinel]
        if touched:
            print(f"scan: {len(touched)} of {high - low} bytes changed")
            print(f"stack: low-water 0x{touched[0]:08X}")
        else:
            print(f"scan: nothing in 0x{low:08X}..0x{high:08X} changed")

    changed = False
    if args.fill:
        low, high, byte = args.fill
        data[ram_offset(low, high - low) : ram_offset(high)] = bytes([byte]) * (high - low)
        changed = True
    if args.map:
        name = args.map.encode("ascii")
        if len(name) > 3:
            raise SystemExit("a map base name is at most three characters")
        data[ram_offset(REQ_NAME, 4) : ram_offset(REQ_NAME) + 4] = name.ljust(4, b"\0")
        struct.pack_into("<I", data, ram_offset(REQ_PTR, 4), REQ_BLOCK)
        struct.pack_into("<I", data, ram_offset(REQ_ONE, 4), 1)
        (flags,) = struct.unpack_from("<I", data, ram_offset(REQ_FLAGS, 4))
        struct.pack_into("<I", data, ram_offset(REQ_FLAGS, 4), flags | 3)
        changed = True
    for address, value in args.word:
        was = struct.unpack_from("<I", data, ram_offset(address, 4))[0]
        struct.pack_into("<I", data, ram_offset(address, 4), value)
        print(f"word 0x{address:08X}: 0x{was:08X} -> 0x{value:08X}")
        changed = True
    for offset, value in ((0, args.day), (1, args.hour), (2, args.minute)):
        if value is not None:
            data[ram_offset(G_CLOCK + offset)] = value
            changed = True

    day, hour, minute = data[ram_offset(G_CLOCK, 3) : ram_offset(G_CLOCK) + 3]
    print(f"clock: day {day} {hour:02d}:{minute:02d}")
    if changed:
        if args.out is None:
            raise SystemExit("a poke needs an output state")
        args.out.write_bytes(data)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
