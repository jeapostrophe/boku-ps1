#!/usr/bin/env python3
"""Boot a memory card on Beetle PSX and play it to the morning its save wakes on (PLAN `ENV-06`).

    ./make.sh boot-save work/saves/corpus/day05.mcd                # -> work/boot-save/day05/
    ./make.sh boot-save CARD --image build/days/image.cue --frames 7600 --state-out 7600:breakfast

The card goes into slot 1 (`run_core.py --memcard`; the file is never written), the title menu
is driven by `boot-to-save.press`, and at `--at` (default the radio exercises in front of the
house) the frame is shot, main RAM is dumped and a state is saved -- the state is what a lane
resumes from instead of booting again. Then the gate: `g_clock` in RAM must read the save's
day + 1, which is what proves the save was loaded rather than a new game started or the menu
missed. Exit 0 on success; run_core's exit code if it failed; 11 if the clock disagrees; 12 if
the card holds no save of this game in slot 1 or the import cannot be read.

Any further arguments are passed to run_core.py unchanged (`--shot`, `--state-out`, ...).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

import run_core  # noqa: E402 -- beside this file, so on sys.path when run as a script

from boku.archive import DEFAULT_DISC_DIR, Archive, ArchiveError  # noqa: E402
from boku.save import GameTables, SaveBody, SaveError, body_of, read_card  # noqa: E402

EXIT_WRONG_DAY = 11
EXIT_NO_SAVE = 12
PRESS_FILE = HERE / "boot-to-save.press"
DEFAULT_AT = 6000
"""Radio exercises in front of the house, the first in-game scene of every morning (measured
on Beetle with boot-to-save.press; the clock already reads the new day)."""


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("card", type=Path, help="a raw 128 KB card with this game's save in slot 1")
    p.add_argument("--image", type=Path, default=REPO / "disc" / "image.cue")
    p.add_argument(
        "--disc", type=Path, default=DEFAULT_DISC_DIR, help="the import (for the save layout)"
    )
    p.add_argument("--work", type=Path, help="default work/boot-save/<card name>")
    p.add_argument(
        "--at", type=int, default=DEFAULT_AT, help=f"the frame to check (default {DEFAULT_AT})"
    )
    p.add_argument("--frames", type=int, help="run this long (default --at)")
    args, rest = p.parse_known_args(argv)

    try:
        tables = GameTables.read(Archive(args.disc))
        saves = read_card(args.card.read_bytes(), tables)
        if 1 not in saves:
            raise SaveError(f"no save in slot 1 (slots {sorted(saves)})")
        saved_day = body_of(saves[1], tables).clock[0]
    except (SaveError, ArchiveError, OSError) as exc:
        print(f"boot-save: {args.card}: {exc}", file=sys.stderr)
        return EXIT_NO_SAVE
    work = args.work or REPO / "work" / "boot-save" / args.card.stem
    frames = max(args.frames or args.at, args.at)
    status = run_core.main(
        [
            str(args.image),
            "--work", str(work),
            "--memcard", str(args.card),
            "--press-file", str(PRESS_FILE),
            "--frames", str(frames),
            "--shot", f"{args.at}:morning",
            "--assert-drawn", str(args.at),
            "--ram-out", f"{args.at}:morning",
            "--state-out", f"{args.at}:morning",
            "--quiet",
            *rest,
        ]
    )  # fmt: skip
    if status:
        return status
    ram = (work / "morning.ram").read_bytes()
    day, hour, minute = SaveBody.from_ram(tables.regions, ram).clock
    if day != saved_day + 1:
        print(
            f"boot-save: at frame {args.at} the clock reads August {day} {hour:02d}:{minute:02d}; "
            f"the save was made on August {saved_day}, so it should read August {saved_day + 1}. "
            f"Look at {work}/morning.png: the menu schedule missed, or the save did not load.",
            file=sys.stderr,
        )
        return EXIT_WRONG_DAY
    print(
        f"boot-save: {args.card.name} loaded -- August {day} {hour:02d}:{minute:02d} at frame "
        f"{args.at}; {work}/morning.png, morning.state, morning.ram"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
