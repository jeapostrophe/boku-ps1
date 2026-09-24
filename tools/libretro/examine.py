#!/usr/bin/env python3
"""Wake a card's save in a map on Beetle PSX, examine one event's spot, and name every
voice it plays (PLAN `ENV-08`; research/sumo.md § The well on the shortcut).

    ./make.sh examine work/saves/corpus/shortcut-open.mcd E08 2405

Boku is put in the event's examine zone (or `--at X,Z`, in the zone table's units, when the
centre sits in something solid) and ○ is pressed every 40 frames for `--after` frames, except
while a clip plays -- each ○ past the end of a scene examines again, so one run sees the first
and the second look. Printed: map changes, queued next events, and each clip `xa_play` starts
with the message whose disc key it is. Shots every `--every` frames go to WORK. Exit 0; 11 if
the map or the zone never came.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from field import (  # noqa: E402 -- beside this file, so on sys.path when run as a script
    MAP_NAME,
    Game,
    StepError,
    examine_placements,
    examine_zones,
    facing,
    land_in,
    stand,
)  # fmt: skip

from boku.archive import DEFAULT_DISC_DIR, Archive  # noqa: E402
from boku.disc import DiscImage  # noqa: E402
from boku.events import Block, decode_voice_key, load_events  # noqa: E402
from boku.voice import disc_key, xam_entry, xch_nodes  # noqa: E402

XA_KEY = 0x800357AC
"""A pointer to the key `xa_play` (`0x8002B3E4`) was last handed."""
XA_PLAYING = 0x800359D8
NEXT_EVENT = 0x80036359
"""`{u8 armed, s16 event}`: the event a `MAP` or `MOVIE` starts in the next map."""


KeyTuple = tuple[int, int, int, int]


def key_tuple(key: dict[str, int]) -> KeyTuple:
    return key["start"], key["end"], key["channel"], key["file"]


def voice_index(disc: Path) -> dict[KeyTuple, list[str]]:
    """Every disc key -> the line ids it voices: event messages (text or not) and `XCH.nn`."""
    archive = Archive(disc)
    index: dict[KeyTuple, set[str]] = {}
    for event in load_events(archive).values():
        for inst in event.instances:
            block = Block(inst.data)
            for m in range(block.message_count):
                raw = block.message_key(m)
                if raw is not None:
                    key = key_tuple(decode_voice_key(raw[:12]))
                    index.setdefault(key, set()).add(f"E{event.id:04d}.{m}")
    for node in xch_nodes(archive):
        index.setdefault((node.start, node.end, node.channel, node.file), set()).add(node.line_id)
    return {k: sorted(v) for k, v in index.items()}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("card", type=Path)
    p.add_argument("map", help="the map base to wake in, e.g. E08")
    p.add_argument("event", type=int, help="the examine event, e.g. 2405")
    p.add_argument("--after", type=int, default=1500)
    p.add_argument("--every", type=int, default=60)
    p.add_argument("--at", help="X,Z to stand at instead of the zone's centre")
    p.add_argument("--image", type=Path, default=REPO / "disc" / "image.cue")
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC_DIR)
    p.add_argument("--work", type=Path, help="default work/examine/<map>-<event>")
    args = p.parse_args(argv)
    work = args.work or REPO / "work" / "examine" / f"{args.map}-{args.event}"
    game = Game(args.image, args.card.read_bytes(), work)
    seen: dict[str, object] = {}
    started = 0
    played: list[bytes] = []

    def watch() -> None:
        nonlocal started
        key, playing = game.u32(XA_KEY), game.read(XA_PLAYING, 1)[0] & 1
        now = {
            "map": game.read(MAP_NAME, 6).decode("ascii", "replace"),
            "next": game.read(NEXT_EVENT, 3).hex(),
        }
        for name, value in now.items():
            if seen.get(name) != value:
                print(f"{game.frame:6d} {name} {value}")
                seen[name] = value
        if playing and (not seen.get("playing") or key != seen.get("key")):
            started = game.frame
            played.append(game.read(key, 12))
            print(f"{game.frame:6d} xa_play {decode_voice_key(played[-1])}")
        if seen.get("playing") and not playing:
            print(f"{game.frame:6d} xa stopped after {game.frame - started} frames")
        seen["playing"], seen["key"] = playing, key

    try:
        land_in(game, args.map)
        zones = examine_zones(game, args.event)
        if not zones:
            raise StepError(f"no examine zone for E{args.event:04d} in {args.map}")
        x, z, angle = zones[-1]
        if args.at:
            ax, az = map(int, args.at.split(","))
            (px, pz), _ = examine_placements(game, args.event)[-1]
            x, z, angle = ax << 4, az << 4, facing(ax, az, px, pz)
        stand(game, x, z, angle)
        game.press("CIRCLE", 0)
        for i in range(args.after):
            if i % 40 == 39 and not seen.get("playing"):
                game.run(4, "CIRCLE")
            game.run(1)
            watch()
            if i % args.every == 0:
                game.fe.screenshot(work / f"examine-{i:04d}.png")
        game.fe.save_state(work / "after.state")
    except StepError as exc:
        game.fe.screenshot(work / "stuck.png")
        print(f"examine: {exc}", file=sys.stderr)
        return 11
    if played:
        xam_lba = xam_entry(DiscImage(args.image.with_suffix(".img"))).lba
        index = voice_index(args.disc)
        for raw in played:
            key = disc_key(raw, xam_lba)
            ids = index.get(key_tuple(key), ["no message on the disc has this key"])
            print(f"examine: clip {key} voices {', '.join(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
