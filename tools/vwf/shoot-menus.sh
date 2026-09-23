#!/bin/sh
# The menu surfaces of research/vwf-prototype.md § "The fixed-pitch surfaces", on both
# emulators: the card check (TITLE.OVL), then the arrival sequence played out into free
# roam, START (the controls-help screen) and the item menu (triangle, then circle on the
# bag) -- with items 1-3 poked into it, for their names and a description -- and, from
# memory cards, "load this file?" and the summer-memories screen; and the insect box's
# notebook page and grid, forced open (book-pokes.lua on Redux, the same writes as pokes on
# Beetle) -- still Japanese: the walkers are not installed. PNGs land in
# work/txt05/menus/ (gitignored: the game's pixels).
#
# The cards come from ./make.sh saves (run it first): day05 for the load flow, and a
# "finished" card for summer memories -- a save whose day reads 31 (research/save-format.md
# § "Reaching the scenes other lanes asked for"); this script makes it from the same base.
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
saves=$repo/work/saves
[ -f "$saves/corpus/day05.mcd" ] || { echo "no $saves/corpus: run ./make.sh saves" >&2; exit 2; }
(cd "$repo" && ./make.sh save --base work/saves/newgame.ram --out "$work/finished.mcd" --day 31 \
    --poke 0x80028FA0=1F >/dev/null) || { echo "could not make the finished card" >&2; exit 2; }
beetle() { out=$1; shift; uv run python "$repo/tools/libretro/run_core.py" "$image" --work "$work/$out" --quiet "$@"; }

if [ "${ONLY:-beetle}" = beetle ]; then
# Beetle: frames are retro_run calls; free roam is reached by 24,000 with the boot presses.
beetle title --frames 3900 --press 3300:START --press 3600:CIRCLE --shot 3800:card-check
beetle roam --frames 24000 --press-file "$repo/tools/libretro/boot-to-dialogue.press" \
    --state-out 24000:free --ram-out 24000:free
beetle help --state-in "$work/roam/free.state" --frames 400 --press 30:START --shot 390:help
beetle items --state-in "$work/roam/free.state" --frames 600 --press 30:TRIANGLE \
    --press 300:CIRCLE --shot 500:items
beetle bag --state-in "$work/roam/free.state" --frames 700 --poke 420:80047E1E=03 \
    --poke 420:80047E28=010203 --press 30:TRIANGLE --press 300:CIRCLE --press 540:DOWN \
    --shot 620:bag-item2
beetle load --memcard "$saves/corpus/day05.mcd" --frames 4400 --press 3300:START \
    --press 3610:DOWN --press 3680:CIRCLE --press 4180:CIRCLE --shot 4260:load-question
beetle extras --memcard "$work/finished.mcd" --frames 6100 --press 3300:START \
    --press 3610:DOWN --press 3640:DOWN --press 3700:CIRCLE --press 4350:CIRCLE \
    --press 4700:CIRCLE --shot 6000:summer-memories
# Summer memories' quiz rate (label 5): its popup draws only while the word at 0x80025938 is
# 1 and the byte 0x800820DC is 1: both written (research/vwf-prototype.md, "The quiz rate").
beetle quiz-rate --memcard "$work/finished.mcd" --frames 6100 --press 3300:START \
    --press 3610:DOWN --press 3640:DOWN --press 3700:CIRCLE --press 4350:CIRCLE \
    --press 4700:CIRCLE --poke 6010:80025938=01000000 --poke 6010:800820DC=01 \
    --shot 6090:quiz-rate
# The insect box: tools/redux/book-pokes.lua's mode_set as pokes -- mode 10, the previous
# mode (the live one), the change flag, and the arena the mode's g_modes record names, all
# read from this image's RAM (the map-area raise moves the arena) -- with insect 0 at book
# state 2 and in cage slot 0. DOWN scrolls the hub to its notebook page; the grid sub-state
# (0x11) opens the grid. research/vwf-prototype.md § "The HHON walkers".
modes=$(uv run python -c "
import struct, sys
ram = open(sys.argv[1], 'rb').read()
u32 = lambda a: struct.unpack_from('<I', ram, a - 0x80000000)[0]
arena = struct.pack('<I', u32(u32(0x800236BC + 16 * 10 + 12))).hex()
print(f'{ram[0x237E4]:02x} {arena}')" "$work/roam/free.ram") || { echo "no RAM dump of free roam" >&2; exit 2; }
previous=${modes% *} arena=${modes#* }
beetle insects --state-in "$work/roam/free.state" --frames 1520 \
    --poke 1:8003DF92=02 --poke 1:80046F28=00 --poke 1:80046F2B=01 \
    --poke "3:800237E5=$previous" --poke 3:800237E0=0A --poke 3:800237E4=0A \
    --poke 3:80024728=01000000 --poke "3:800258E0=$arena" \
    --press 300:DOWN --shot 380:hub-page --poke 600:80080600=11000000 --shot 1500:grid
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
    vars=""; flags=""
    for arg in "$@"; do
        case "$arg" in
            *=*) vars="$vars $arg" ;;
            *) flags="$flags $arg" ;;
        esac
    done
    # shellcheck disable=SC2086  # word-split on purpose; no value holds a space
    env $vars "$repo/tools/redux/run-on-image.sh" "$image" "$script" $flags \
        >"$work/redux-$log.log" 2>&1
}
run title drive.lua BOKU_INPUT="2430:START:5;2600:CIRCLE:5" BOKU_FRAMES=2900 BOKU_SHOT_AT=2900 \
    BOKU_PREFIX=card-check
run boot boot-to-dialogue.lua   # exits 4 on a patched image: it asserts the stock dialog_open
run free drive.lua BOKU_LOAD=first-dialogue BOKU_FRAMES=14000 BOKU_SAVE=free
run help drive.lua BOKU_LOAD=free BOKU_FRAMES=300 BOKU_INPUT="20:START:5" BOKU_SHOT_AT=290 \
    BOKU_PREFIX=help
run items drive.lua BOKU_LOAD=free BOKU_FRAMES=700 BOKU_INPUT="20:TRIANGLE:5;300:CIRCLE:5" \
    BOKU_SHOT_AT=690 BOKU_PREFIX=items
run bag drive.lua BOKU_LOAD=free BOKU_FRAMES=800 BOKU_POKES="$repo/tools/vwf/bag-items.lua" \
    BOKU_INPUT="20:TRIANGLE:5;300:CIRCLE:5;560:DOWN:5" BOKU_SHOT_AT=700 \
    BOKU_PREFIX=bag
# Redux writes a card back when the game saves, so it is given copies.
cp "$work/finished.mcd" "$work/redux-finished.mcd"
cp "$saves/corpus/day05.mcd" "$work/redux-day05.mcd"
run load drive.lua BOKU_FRAMES=3200 BOKU_SHOT_AT=3200 BOKU_PREFIX=load \
    BOKU_INPUT="2430:START:5;2590:DOWN:5;2660:CIRCLE:5;3050:CIRCLE:5" \
    -memcard1 "$work/redux-day05.mcd"
run extras drive.lua BOKU_FRAMES=5000 BOKU_SHOT_AT=5000 BOKU_PREFIX=extras \
    BOKU_INPUT="2430:START:5;2590:DOWN:5;2620:DOWN:5;2690:CIRCLE:5;3100:CIRCLE:5;3400:CIRCLE:5" \
    -memcard1 "$work/redux-finished.mcd"
cp "$work/finished.mcd" "$work/redux-finished.mcd"
run quiz-rate drive.lua BOKU_FRAMES=5000 BOKU_SHOT_AT=5000 BOKU_PREFIX=quiz-rate \
    BOKU_INPUT="2430:START:5;2590:DOWN:5;2620:DOWN:5;2690:CIRCLE:5;3100:CIRCLE:5;3400:CIRCLE:5" \
    BOKU_POKES="$repo/tools/vwf/word-pokes.lua" BOKU_W32=4900:0x80025938=1 BOKU_W8=4900:0x800820DC=1 \
    -memcard1 "$work/redux-finished.mcd"
# The insect box, forced open (book-pokes.lua): the hub scrolled to its page, then the grid.
run hub drive.lua BOKU_LOAD=free BOKU_FRAMES=420 BOKU_SHOT_AT=410 BOKU_PREFIX=hub-page \
    BOKU_POKES="$repo/tools/redux/book-pokes.lua" BOKU_MODE=10 BOKU_SEEN=0=2 BOKU_CAUGHT=0=0 \
    BOKU_W32=200:0x800805DC=200
run grid drive.lua BOKU_LOAD=free BOKU_FRAMES=420 BOKU_SHOT_AT=410 BOKU_PREFIX=grid \
    BOKU_POKES="$repo/tools/redux/book-pokes.lua" BOKU_MODE=10 BOKU_SEEN=0=2 BOKU_CAUGHT=0=0 \
    BOKU_SUBSTATE=120:17
uv run python "$repo/tools/redux/shot2png.py" "$BOKU_WORK"/shots/*.raw >/dev/null
grep -H "ISLAND\|EXIT" "$work"/redux-*.log
fi
ls "$work"/*/*.png "$work"/redux/shots/*.png 2>/dev/null
