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

With `--mantis` the gate is the story instead (no stats are checked): King on the rank board,
the bout won, `E1754` followed until Boku stands in `E02` with `g_flags[69]` and `[70]` set.
Exit 0 then, with `mantis.png`, `shortcut.png` and `shortcut.state`.

`--gong` then strikes the gong, which starts the fight with a boy's voice (`XCH.nn`), and
checks that clip's subtitle (PLAN `VO-06`): it must open while the clip plays with its words
in bug sumo's home for them (level C's base, `asm/voice.asm`) and the band up, and be down
again when the clip ends -- `clip.png` shows it, `after.png` the frame after. Exit 14 if not.
Run it on an image built with clip subtitles.

`--leave` then lets the fight end, backs out to the desk's "もどる" and leaves bug sumo: the
field must come back (a build whose SUB.TIM reload ran into the stack hung here on a black
screen -- research/loading-and-memory.md § Leaving a mode). Exit 15 if it does not.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from field import (  # noqa: E402 -- beside this file, so on sys.path when run as a script
    FIELD,
    MAP_NAME,
    MODE_ACTIVE,
    Game,
    StepError,
    examine_zones,
    land_in,
    stand,
)  # fmt: skip

from boku.archive import DEFAULT_DISC_DIR, Archive, ArchiveError  # noqa: E402
from boku.asm_source import asm_equate  # noqa: E402
from boku.movie_block import MAGIC  # noqa: E402
from boku.save import G_FLAGS, GameTables, SaveError, body_of, read_card  # noqa: E402
from boku.sumo import CAGE, EMPTY, RECORD, SumoTables, bout_hp  # noqa: E402

EXIT_STEP, EXIT_STATS, EXIT_INPUT, EXIT_SUBTITLE, EXIT_LEAVE = 11, 12, 13, 14, 15

SUMO = 7
DESK_EVENT = 4025
HELD = 0x8003E098
"""The bug in Boku's hand at the desk: a cage record, type 99 when empty."""
BOUT = 0x8008EF84
"""1 while a bout runs (measured: 0 at the drum, 1 once the bug is put down)."""
RANK_CHOICE = 0x8008EFC8
"""The row of the rank board ("弱い", "強い", "キング") the hand is on."""
KING = 2
RESULT = 0x8008EF82
"""How the bout ended: 3 when Boku's bug won (measured against the mantis)."""
WON = 3
MANTIS_WON = G_FLAGS + 69
SHORTCUT = G_FLAGS + 70
"""`g_flags[69]` (the mantis beaten) and `g_flags[70]` (the shortcut shown, `E1754`)."""
FIGHTER = 0x8008F018
"""Boku's fighter in `MUSI`: `+8 s32` HP, `+0xC` HP before the training bonus, `+0x10` STR,
`+0x12` DEF0, `+0x13` DEF1 (`sumo_stats` `0x80081380`)."""
XA_STATUS = 0x800359D8
"""The XA status word: bits 0 and 2 while a clip plays (what `XAMSG` waits on)."""
TEXT_PAGE = 0x800359EC
"""`g_text_page`: the page the dialogue renderer draws, NULL when none."""
PANEL_VISIBLE = 0x8002911E
LEVEL_C = asm_equate("LEVEL_C_BASE", "voice.asm")
"""`g_arena_lvl_c` -> level C's base: bug sumo's copy of the subtitle block."""
HOME_BYTES = asm_equate("SUMO_HOME_BYTES", "voice.asm")
"""The room the block may take there."""
SUBTITLE_LAG = 4
"""Frames the subtitle may trail the clip's start or end (it is served once a frame)."""
DESK_CURSOR, BACK = 0x8008EF78, 3
"""The desk's cursor (`MUSI` `0x8007C77C`); 3 is "もどる"."""


def enter_desk(game: Game) -> None:
    zones = examine_zones(game, DESK_EVENT)
    if not zones:
        raise StepError(f"no examine placement for E{DESK_EVENT} in {game.read(MAP_NAME, 6)!r}")
    for x, z, angle in reversed(zones):  # the first zone sits in a boy's reach: ○ talks
        stand(game, x, z, angle)
        game.press("CIRCLE", 0)
        try:
            game.until("mode 7", lambda: game.read(MODE_ACTIVE, 1)[0] == SUMO, 900)
            return
        except StepError:
            print(f"sumo-bout: zone at {x},{z} facing {angle}: no desk", file=sys.stderr)
    raise StepError(f"none of E{DESK_EVENT}'s {len(zones)} zones opened the desk")


def drive(game: Game, king: bool = False) -> None:
    land_in(game, "A18")
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
    if king:
        # With the mantis fight open the hand lands on the rank board ("虫ランク") instead.
        game.press("CIRCLE", 60)
        game.press("DOWN", 60)
        game.press("DOWN", 60)
        if game.read(RANK_CHOICE, 1)[0] != KING:
            raise StepError("the rank board did not open on King")
        game.press("CIRCLE", 1300)  # the mantis walks on
        game.press("RIGHT", 60)  # over the drum: "虫を置く"
    game.press("CIRCLE", 0)
    game.until("the bout", lambda: game.read(BOUT, 1)[0] == 1, 900)


def fight_to_the_shortcut(game: Game) -> None:
    """Ring the gong, tap with △ until the bout ends, then ○ through `E1754` until Boku
    stands at the shortcut's far end (`E02`) with `g_flags[70]` set."""
    game.run(420)  # the bug is set down; the gong answers only after (measured)
    game.press("RIGHT", 60)
    game.press("DOWN", 60)  # the gong ("ゴング")
    game.press("CIRCLE", 60)
    result = 0
    for _ in range(300):
        result = game.read(RESULT, 1)[0]
        if result:
            break
        game.press("TRIANGLE", 6)
    if result != WON:
        raise StepError(f"the bout ended {result}, not a win")
    for _ in range(400):
        if game.read(MAP_NAME, 3) == b"E02" and game.read(SHORTCUT, 1)[0]:
            if not game.read(MANTIS_WON, 1)[0]:
                raise StepError("in E02 with the shortcut shown, but g_flags[69] is not set")
            return
        game.press("CIRCLE", 36)
    raise StepError("E1754 did not reach the shortcut (E02)")


def gong(game: Game, work: Path) -> None:
    """Strike the gong and watch the first clip's subtitle."""
    game.run(200)
    game.press("RIGHT", 60)  # the drum to the gong
    game.press("CIRCLE", 0)
    playing = lambda: game.u32(XA_STATUS) & 5  # noqa: E731
    game.until("the gong's clip", playing, 600)
    start, home = game.frame, game.u32(LEVEL_C)
    if game.u32(home) != MAGIC:
        raise StepError(f"no subtitle block at level C's base 0x{home:08X} when the clip started")
    game.run(SUBTITLE_LAG)
    page, panel = game.u32(TEXT_PAGE), game.read(PANEL_VISIBLE, 1)[0]
    if not (home <= page < home + HOME_BYTES and panel):
        raise StepError(f"clip at frame {start}: page 0x{page:08X}, band {panel} -- no subtitle up")
    game.run(16)
    game.fe.screenshot(work / "clip.png")
    game.until("the clip's end", lambda: not playing(), 1200)
    end = game.frame
    game.run(SUBTITLE_LAG)
    game.fe.screenshot(work / "after.png")
    page, panel = game.u32(TEXT_PAGE), game.read(PANEL_VISIBLE, 1)[0]
    if page or panel:
        raise StepError(f"clip ended at frame {end}: page 0x{page:08X}, band {panel} -- still up")
    print(f"sumo-bout: the gong's clip, frames {start}-{end}: subtitle from 0x{home:08X}")


def leave(game: Game, work: Path) -> None:
    """From the fight: its end, ✕ back to the desk's "もどる", ○, and the field again."""
    game.run(1800)  # the fight and its clips (the maxed bug wins in ~1,000 frames)
    for _ in range(2):
        for _ in range(10):
            game.press("CROSS", 4)
        game.run(120)
    game.until("the desk's back button", lambda: game.read(DESK_CURSOR, 1)[0] == BACK, 300)
    game.press("CIRCLE", 0)
    game.until("the field after bug sumo", lambda: game.read(MODE_ACTIVE, 1)[0] == FIELD, 900)
    game.fe.screenshot(work / "field.png")
    print(f"sumo-bout: back in the field at frame {game.frame}")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("card", type=Path, help="a card whose slot-1 save opens bug sumo")
    p.add_argument("--image", type=Path, default=REPO / "disc" / "image.cue")
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC_DIR)
    p.add_argument("--work", type=Path, help="default work/sumo-bout/<card name>")
    p.add_argument(
        "--mantis",
        action="store_true",
        help="the card is set up for the mantis fight: choose King, win it, and follow E1754 "
        "to the shortcut (research/sumo.md § The mantis and the shortcut)",
    )
    p.add_argument("--gong", action="store_true", help="then strike the gong: VO-06's gate")
    p.add_argument("--leave", action="store_true", help="after --gong, leave bug sumo")
    args = p.parse_args(argv)
    if args.leave and not args.gong:
        p.error("--leave runs after --gong's fight; give both")
    if args.gong and args.mantis:
        p.error("--gong fights the stats bout; --mantis fights its own")
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
        drive(game, king=args.mantis)
        if args.mantis:
            game.fe.screenshot(work / "mantis.png")
            fight_to_the_shortcut(game)
            game.run(300)
            game.fe.screenshot(work / "shortcut.png")
            game.fe.save_state(work / "shortcut.state")
            print(
                f"sumo-bout: the mantis beaten (g_flags[69] = {game.read(MANTIS_WON, 1)[0]}), "
                f"the shortcut shown (g_flags[70] = {game.read(SHORTCUT, 1)[0]}), Boku in "
                f"{game.read(MAP_NAME, 6).decode()} at frame {game.frame} -> {work}/shortcut.png"
            )
            return 0
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
    steps = [(gong, EXIT_SUBTITLE)] if args.gong else []
    steps += [(leave, EXIT_LEAVE)] if args.leave else []
    for step, code in steps:
        try:
            step(game, work)
        except StepError as exc:
            game.fe.screenshot(work / "stuck.png")
            print(f"sumo-bout: {exc}", file=sys.stderr)
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
