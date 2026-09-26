#!/bin/sh
# The stack's low-water mark on Beetle under the screens a player meets after the arrival
# sequence (PLAN TXT-05's "watch the stack"; research/vwf-prototype.md § "The map work area"
# says why it matters: the raised work area leaves a fixed margin above the level-C arena).
#
#   tools/vwf/stack-watch.sh [image.cue]      # default build/vwf/image.cue
#
# Needs tools/vwf/shoot-menus.sh's Beetle free-roam state and RAM (work/txt05/menus/roam/),
# made from the same image, and Beetle (tools/libretro/emulator_paths.py). For each scenario
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
# The fill runs from level C's base (g_modes' level-C word 0x800258FC, moved by every arena
# raise) to the stack's top 0x801FFFF0 less the live frames, because the item menu's stack
# reaches below level C + 0x6000. A scenario that stays in the field or reaches an event can
# change map, and bg_swap_in then writes its 0x6000 scratch at level C: those are scanned
# from level C + 0x6000 (`scenario NAME scratch`), the rest from level C (`scenario NAME
# level`); research/vwf-prototype.md § "The map work area".
lo=$(uv run python -c "
import struct, sys
ram = open(sys.argv[1], 'rb').read()
print(hex(struct.unpack_from('<I', ram, 0x258FC)[0]))" "$menus/roam/free.ram") || exit 2
scratch_end=$(printf '0x%x' $((lo + 0x6000)))
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
    name=$1 floor=$lo; [ "$2" = scratch ] && floor=$scratch_end; shift 2
    printf '%-10s ' "$name"
    rm -f "$work/$name/end.state"
    if beetle "$name" --state-in "$work/filled.state" --state-out "${FRAMES}:end" \
        --frames "$FRAMES" --shot "${FRAMES}:end" "$@" >"$work/$name.log" 2>&1 \
        && [ -f "$work/$name/end.state" ]; then
        poke "$work/$name/end.state" --scan "$floor" $hi 0xEE | grep -E "^(scan|stack)" | tr '\n' ' '
        echo
    else
        echo "run_core failed: $work/$name.log"
    fi
}

FRAMES=3000 scenario field scratch --press 60:UP:600 --press 700:LEFT:40 --press 760:UP:600 --press 1400:RIGHT:80 --press 1500:UP:900
FRAMES=900 scenario help scratch --press 30:START --press 600:START
FRAMES=900 scenario bag level --press 30:TRIANGLE --press 300:CIRCLE --poke 420:80047E1E=03 \
    --poke 420:80047E28=010203 --press 540:DOWN --press 640:DOWN
# shellcheck disable=SC2046
FRAMES=1600 scenario insects level $(force 10) --poke 1:8003DF92=02 --poke 1:80046F28=00 \
    --poke 1:80046F2B=01 --press 300:DOWN --poke 600:80080600=11000000
# shellcheck disable=SC2046
# MUSI forced from free roam shows the room again before a bout, though the end state is
# still mode 7 with g_arena_cur at B: not a sumo depth.
FRAMES=1200 scenario sumo level $(force 7) --press 400:CIRCLE --press 700:CIRCLE
# shellcheck disable=SC2046
# TAKO runs: the kite flies, with its wind and height readouts.
FRAMES=1200 scenario kite level $(force 6) --press 400:CIRCLE --press 700:CIRCLE
# shellcheck disable=SC2046
# Mode 15 (TITLE for saving from the game) forced from the afternoon does not stay on a save
# screen: the game runs on into the evening's dinner scene, so this is the event and dialogue
# path's depth, not a save's. (The state brings its own card, formatted and empty.)
FRAMES=1500 scenario save scratch $(force 15) \
    --press 400:CIRCLE --press 800:CIRCLE --press 1100:CIRCLE
ls "$work"/*/end.png
