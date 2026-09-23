#!/bin/sh
# The stack's low-water mark on Beetle under the screens a player meets after the arrival
# sequence (PLAN TXT-05's "watch the stack"; research/vwf-prototype.md § "The map work area"
# says why it matters: the raised work area leaves a fixed margin above the level-C arena).
#
#   tools/vwf/stack-watch.sh [image.cue]      # default build/vwf/image.cue
#
# Needs tools/vwf/shoot-menus.sh's Beetle free-roam state and RAM (work/txt05/menus/roam/),
# made from the same image, and BOKU_LIBRETRO_CORE / BOKU_LIBRETRO_SYSTEM. For each scenario
# the state's RAM from STACK_LO up to the stack's top is filled with a sentinel
# (tools/vwf/state_poke.py --fill), the scenario runs, and --scan reports the lowest byte
# that changed. The overlays are forced into their modes the way book-pokes.lua does it.
set -u
repo=$(cd "$(dirname "$0")/../.." && pwd)
image=${1:-$repo/build/vwf/image.cue}
menus=$repo/work/txt05/menus
work=$repo/work/txt05/stack
mkdir -p "$work"
for f in free.state free.ram; do
    [ -f "$menus/roam/$f" ] || { echo "run tools/vwf/shoot-menus.sh first" >&2; exit 2; }
done
# From above what bg_swap_in scratches (level C + 0x6000, level C moving with every arena
# raise: tools/vwf/stack-probe.lua does the same on Redux), so only the stack can disturb
# the fill, up to the stack's top 0x801FFFF0 less the live frames.
lo=$(uv run python -c "
import struct, sys
ram = open(sys.argv[1], 'rb').read()
print(hex(struct.unpack_from('<I', ram, 0x258FC)[0] + 0x6000))" "$menus/roam/free.ram") || exit 2
hi=0x801FFF00
poke() { uv run python "$repo/tools/vwf/state_poke.py" "$@"; }
beetle() { out=$1; shift; uv run python "$repo/tools/libretro/run_core.py" "$image" --work "$work/$out" --quiet "$@"; }
rm -f "$work/filled.state"
poke "$menus/roam/free.state" "$work/filled.state" --fill "$lo" $hi 0xEE >/dev/null || exit 2

# mode_set(m) as pokes: the live mode as the previous one, the mode pair, the change flag,
# and the arena word of the mode's own g_modes record (read from the free-roam RAM).
modes() {
    uv run python -c "
import struct, sys
ram = open(sys.argv[1], 'rb').read()
u32 = lambda a: struct.unpack_from('<I', ram, a - 0x80000000)[0]
m = int(sys.argv[2])
print(f'{ram[0x237E4]:02x}', struct.pack('<I', u32(u32(0x800236BC + 16 * m + 12))).hex())" \
        "$menus/roam/free.ram" "$1"
}
force() {
    set -- $(modes "$1") "$1"
    printf -- '--poke 3:800237E5=%s --poke 3:800237E0=%02x --poke 3:800237E4=%02x --poke 3:80024728=01000000 --poke 3:800258E0=%s' \
        "$1" "$3" "$3" "$2"
}

scenario() {
    name=$1; shift
    printf '%-10s ' "$name"
    rm -f "$work/$name/end.state"
    if beetle "$name" --state-in "$work/filled.state" --state-out "${FRAMES}:end" \
        --frames "$FRAMES" --shot "${FRAMES}:end" "$@" >"$work/$name.log" 2>&1 \
        && [ -f "$work/$name/end.state" ]; then
        poke "$work/$name/end.state" --scan "$lo" $hi 0xEE | grep -E "^(scan|stack)" | tr '\n' ' '
        echo
    else
        echo "run_core failed: $work/$name.log"
    fi
}

FRAMES=3000 scenario field --press 60:UP:600 --press 700:LEFT:40 --press 760:UP:600 --press 1400:RIGHT:80 --press 1500:UP:900
FRAMES=900 scenario help --press 30:START --press 600:START
FRAMES=900 scenario bag --press 30:TRIANGLE --press 300:CIRCLE --poke 420:80047E1E=03 \
    --poke 420:80047E28=010203 --press 540:DOWN --press 640:DOWN
# shellcheck disable=SC2046
FRAMES=1600 scenario insects $(force 10) --poke 1:8003DF92=02 --poke 1:80046F28=00 \
    --poke 1:80046F2B=01 --press 300:DOWN --poke 600:80080600=11000000
# shellcheck disable=SC2046
# MUSI forced from free roam returns to the field before its match starts (measured): the
# number is its init, not a bout.
FRAMES=1200 scenario sumo $(force 7) --press 400:CIRCLE --press 700:CIRCLE
# shellcheck disable=SC2046
# TAKO runs: the kite flies, with its wind and height readouts.
FRAMES=1200 scenario kite $(force 6) --press 400:CIRCLE --press 700:CIRCLE
# shellcheck disable=SC2046
# Mode 15 (TITLE for saving from the game) forced from the afternoon does not stay on a save
# screen: the game runs on into the evening's dinner scene, so this is the event and dialogue
# path's depth, not a save's. (The state brings its own card, formatted and empty.)
FRAMES=1500 scenario save $(force 15) \
    --press 400:CIRCLE --press 800:CIRCLE --press 1100:CIRCLE
ls "$work"/*/end.png
