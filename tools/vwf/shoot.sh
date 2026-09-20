#!/bin/sh
# Boot build/vwf/image.cue on both emulators through the arrival sequence and leave PNGs in
# work/txt05/ (gitignored: they are the game's pixels). The point is to LOOK at them --
# research/vwf-prototype.md says what each frame should show.
#
#   tools/vwf/shoot.sh [image.cue]
#
# Beetle PSX needs BOKU_LIBRETRO_CORE and BOKU_LIBRETRO_SYSTEM, PCSX-Redux REDUX_BIOS
# (research/tooling-setup.md). Both emulators run in the foreground and exit by themselves.
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
