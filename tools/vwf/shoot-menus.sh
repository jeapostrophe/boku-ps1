#!/bin/sh
# The menu surfaces of research/vwf-prototype.md § "The fixed-pitch surfaces", on both
# emulators: the card check (TITLE.OVL), then the arrival sequence played out into free
# roam, START (the controls-help screen) and the item menu (triangle, then circle on the
# bag). PNGs land in work/txt05/menus/ (gitignored: the game's pixels).
#
#   tools/vwf/shoot-menus.sh [image.cue]          # default build/vwf/image.cue
#   ISLAND_WATCH=1 tools/vwf/shoot-menus.sh disc/image.cue
#   ONLY=beetle | ONLY=redux                     # one emulator
#
# ISLAND_WATCH=1 arms tools/vwf/island-watch.lua on the Redux runs: an execution breakpoint
# over dbg_font_init (the islands asm/vwf.asm splits between the movie loader and the
# walkers) and a control one on glyph_draw. Run it on the
# STOCK image -- that is the measurement of the island being dead code; on a patched image
# the walkers jump into it by design.
#
# Beetle needs BOKU_LIBRETRO_CORE and BOKU_LIBRETRO_SYSTEM, Redux REDUX_BIOS
# (research/tooling-setup.md). Redux runs ~14,000 frames of free roam; allow ten minutes.
set -u
repo=$(cd "$(dirname "$0")/../.." && pwd)
image=${1:-$repo/build/vwf/image.cue}
work=$repo/work/txt05/menus
mkdir -p "$work"
beetle() { out=$1; shift; uv run python "$repo/tools/libretro/run_core.py" "$image" --work "$work/$out" --quiet "$@"; }

if [ "${ONLY:-beetle}" = beetle ]; then
# Beetle: frames are retro_run calls; free roam is reached by 24,000 with the boot presses.
beetle title --frames 3900 --press 3300:START --press 3600:CIRCLE --shot 3800:card-check
beetle roam --frames 24000 --press-file "$repo/tools/libretro/boot-to-dialogue.press" \
    --state-out 24000:free
beetle help --state-in "$work/roam/free.state" --frames 400 --press 30:START --shot 390:help
beetle items --state-in "$work/roam/free.state" --frames 600 --press 30:TRIANGLE \
    --press 300:CIRCLE --shot 500:items
fi

if [ "${ONLY:-redux}" = redux ]; then
# PCSX-Redux: its own clock (research/renderer-runtime.md); states are image-specific.
export BOKU_WORK="$work/redux" REDUX_TIMEOUT="${REDUX_TIMEOUT:-1800}"
if [ -n "${ISLAND_WATCH:-}" ]; then
    island() { sed -n "s/^$1 *equ 0x\([0-9A-Fa-f]*\).*/\1/p" "$repo/asm/vwf.asm"; }
    export BOKU_POKES="$repo/tools/vwf/island-watch.lua"
    export BOKU_ISLAND_RANGE="$(island DEBUG_FONT_ISLAND),$(island DEBUG_FONT_ISLAND_END)"
fi
rm -rf "$BOKU_WORK"
# run LOG SCRIPT [VAR=value ...]: the variables go through env(1), because an assignment in
# front of a shell *function* call outlives the call in POSIX sh and would leak into the next.
run() {
    log=$1 script=$2; shift 2
    env "$@" "$repo/tools/redux/run-on-image.sh" "$image" "$script" >"$work/redux-$log.log" 2>&1
}
run title drive.lua BOKU_INPUT="2430:START:5;2600:CIRCLE:5" BOKU_FRAMES=2900 BOKU_SHOT_AT=2900 \
    BOKU_PREFIX=card-check
run boot boot-to-dialogue.lua   # exits 4 on a patched image: it asserts the stock dialog_open
run free drive.lua BOKU_LOAD=first-dialogue BOKU_FRAMES=14000 BOKU_SAVE=free
run help drive.lua BOKU_LOAD=free BOKU_FRAMES=300 BOKU_INPUT="20:START:5" BOKU_SHOT_AT=290 \
    BOKU_PREFIX=help
run items drive.lua BOKU_LOAD=free BOKU_FRAMES=700 BOKU_INPUT="20:TRIANGLE:5;300:CIRCLE:5" \
    BOKU_SHOT_AT=690 BOKU_PREFIX=items
uv run python "$repo/tools/redux/shot2png.py" "$BOKU_WORK"/shots/*.raw >/dev/null
grep -H "ISLAND\|EXIT" "$work"/redux-*.log
fi
ls "$work"/*/*.png "$work"/redux/shots/*.png 2>/dev/null
