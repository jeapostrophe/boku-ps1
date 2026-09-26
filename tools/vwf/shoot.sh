#!/bin/sh
# Boot build/vwf/image.cue on both emulators through the arrival sequence and leave PNGs in
# work/txt05/ (gitignored: they are the game's pixels). The point is to LOOK at them --
# research/vwf-prototype.md says what each frame should show.
#
#   tools/vwf/shoot.sh [image.cue]
#
# Beetle PSX needs its core and BIOS, PCSX-Redux a BIOS (tools/libretro/emulator_paths.py
# finds them; research/tooling-setup.md). Both emulators run in the foreground and exit by themselves.
set -eu
repo=$(cd "$(dirname "$0")/../.." && pwd)
image=${1:-$repo/build/vwf/image.cue}
work=$repo/work/txt05
mkdir -p "$work/shots"

# Beetle: frames are retro_run calls from a cold boot, on tools/libretro's own schedule.
# The named frames were read off a --shot-every 50 sweep of this image; Beetle is
# deterministic, so they hold until the lines file or the boot schedule changes.
rm -rf "$work/beetle"
uv run python "$repo/tools/libretro/run_core.py" "$image" --work "$work/beetle" --quiet \
    --frames 12200 --press-file "$repo/tools/libretro/boot-to-dialogue.press" \
    --state-out 5790:pre-dialogue \
    --shot 5850:E0171.0 --shot 6200:E0171.1-page1 --shot 6550:E0171.1-page2 \
    --shot 7000:E0171.3 --shot 7600:E0174.0-wrapped --shot 8300:E0174.1 \
    --shot 8700:E0175.0-overflow --shot 8900:E0175.0-tilde --shot 9800:E0177.0-japanese \
    --shot 10750:E0177.2-five-lines --shot 11000:E0177.2-digits --shot 11420:E0181-japanese --shot 11900:E0182-japanese
# The next-page pencil only shows once CIRCLE has cancelled auto-advance.
uv run python "$repo/tools/libretro/run_core.py" "$image" --work "$work/beetle-arrow" --quiet \
    --state-in "$work/beetle/pre-dialogue.state" --frames 500 --press 410:CIRCLE \
    --shot 470:E0171.1-page1-arrow
for f in "$work"/beetle/E*.png "$work"/beetle-arrow/E*.png; do
    cp "$f" "$work/shots/beetle-$(basename "$f")"
done

# PCSX-Redux: boot-to-dialogue.lua saves a state at the first line, then exits 4 because it
# asserts the STOCK dialog_open arguments (297, 22, 1) and this image passes (PEN_X, PEN_Y, 0).
export BOKU_WORK="$work/redux"
rm -rf "$BOKU_WORK"
"$repo/tools/redux/run-on-image.sh" "$image" boot-to-dialogue.lua >"$work/redux-boot.log" 2>&1 || [ $? -eq 4 ]
BOKU_LOAD=first-dialogue BOKU_FRAMES=6000 BOKU_SHOT_EVERY=40 BOKU_PREFIX=seq BOKU_PROBE=dialog \
    "$repo/tools/redux/run-on-image.sh" "$image" drive.lua >"$work/redux-seq.log" 2>&1
uv run python "$repo/tools/redux/shot2png.py" "$BOKU_WORK"/shots/*.raw >/dev/null
for f in 00040 00400 00680 01160 01720 02400 02800 04000 04880 05520; do
    cp "$BOKU_WORK/shots/seq-$f.png" "$work/shots/redux-seq-$f.png"
done
ls "$work/shots"

# TITLE.OVL: the memory-card check (CIRCLE on "start"), continue with no card (DOWN, CIRCLE),
# and the config screen (DOWN x3, CIRCLE), each from a cold boot so the rebuilt overlay is the
# one in RAM (a state saved from an older build carries that build's RAM).
rm -rf "$work/beetle-title"
uv run python "$repo/tools/libretro/run_core.py" "$image" --work "$work/beetle-title" --quiet \
    --frames 4300 --press 3300:START --press 3600:CIRCLE --shot 3800:title-card-check
uv run python "$repo/tools/libretro/run_core.py" "$image" --work "$work/beetle-title" --quiet \
    --frames 4100 --press 3300:START --press 3600:DOWN --press 3700:CIRCLE --shot 4080:title-no-file
uv run python "$repo/tools/libretro/run_core.py" "$image" --work "$work/beetle-title" --quiet \
    --frames 4100 --press 3300:START --press 3580:DOWN --press 3600:DOWN --press 3620:DOWN \
    --press 3700:CIRCLE --shot 4080:title-config
for f in "$work"/beetle-title/title-*.png; do cp "$f" "$work/shots/beetle-$(basename "$f")"; done
for route in "card-check|2600:CIRCLE:5|2900" "no-file|2700:DOWN:5;2850:CIRCLE:5|3150" \
             "config|2700:DOWN:5;2730:DOWN:5;2760:DOWN:5;2850:CIRCLE:5|3700"; do
    name=${route%%|*}; rest=${route#*|}; input=${rest%|*}; at=${rest##*|}
    export BOKU_WORK="$work/redux-title-$name"
    rm -rf "$BOKU_WORK"
    BOKU_INPUT="2430:START:5;$input" BOKU_FRAMES="$at" BOKU_SHOT_AT="$at" BOKU_PREFIX=title \
        "$repo/tools/redux/run-on-image.sh" "$image" drive.lua >"$work/redux-title-$name.log" 2>&1
    uv run python "$repo/tools/redux/shot2png.py" "$BOKU_WORK"/shots/*.raw >/dev/null
    cp "$BOKU_WORK/shots/title-$(printf %05d "$at").png" "$work/shots/redux-title-$name.png"
done

# SELECT (Redux only): play the arrival sequence out into free roam, send Boku to the living
# room with the same words the MAP opcode writes (tools/vwf/reach-select.lua says why: the
# room is sealed on day 1), turn to face the uncle, walk up, talk -- E0112.0, then its yes/no
# -- then DOWN, UP and CIRCLE on the select. Frames are state-relative.
export BOKU_WORK="$work/redux"
BOKU_LOAD=first-dialogue BOKU_FRAMES=14000 BOKU_SAVE=free \
    "$repo/tools/redux/run-on-image.sh" "$image" drive.lua >"$work/redux-free.log" 2>&1
BOKU_LOAD=free BOKU_MAP=G01 BOKU_FRAMES=1100 BOKU_SAVE=select BOKU_PREFIX=sel \
    BOKU_INPUT="60:RIGHT:8;80:UP:50;180:CIRCLE:6;250:CIRCLE:6;320:CIRCLE:6" \
    BOKU_SHOT_AT=100,250,500 \
    "$repo/tools/redux/run-on-image.sh" "$image" "$repo/tools/vwf/reach-select.lua" >"$work/redux-select.log" 2>&1
BOKU_LOAD=select BOKU_FRAMES=700 BOKU_PREFIX=cursor \
    BOKU_INPUT="20:DOWN:4;120:UP:4;220:DOWN:4;320:CIRCLE:4" BOKU_SHOT_AT=15,80,180,280,560 \
    "$repo/tools/redux/run-on-image.sh" "$image" "$repo/tools/vwf/reach-select.lua" >"$work/redux-cursor.log" 2>&1
uv run python "$repo/tools/redux/shot2png.py" "$BOKU_WORK"/shots/sel-*.raw "$BOKU_WORK"/shots/cursor-*.raw >/dev/null
cp "$BOKU_WORK/shots/sel-00100.png" "$work/shots/redux-G01-living-room.png"
cp "$BOKU_WORK/shots/sel-00250.png" "$work/shots/redux-E0112.0-line.png"
cp "$BOKU_WORK/shots/sel-00500.png" "$work/shots/redux-select-E0112.1-yes.png"
cp "$BOKU_WORK/shots/cursor-00080.png" "$work/shots/redux-select-E0112.1-no-after-DOWN.png"
cp "$BOKU_WORK/shots/cursor-00180.png" "$work/shots/redux-select-E0112.1-yes-after-UP.png"
cp "$BOKU_WORK/shots/cursor-00280.png" "$work/shots/redux-select-E0112.1-no-again.png"
cp "$BOKU_WORK/shots/cursor-00560.png" "$work/shots/redux-E0112.2-after-select.png"
grep -E "REQUEST|MAP f|DLG|SELOPEN|END" "$work/redux-select.log" "$work/redux-cursor.log"
ls "$work/shots"
