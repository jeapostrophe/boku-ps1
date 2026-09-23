#!/bin/sh
# Drive PCSX-Redux with no window and no human: boot an image, run a Lua script, exit
# with the script's status. This is the shape every automated emulator check in this
# project should take.
#
#   tools/redux/run-headless.sh [--iso PATH] [--lua PATH] [--] [extra redux flags...]
#
# Defaults: disc/image.cue and tools/redux/smoke.lua. Requires PCSX-Redux installed at
# $REDUX_APP, and REDUX_BIOS pointing at a retail Japanese BIOS dump: the bundled
# OpenBIOS reads this disc but never reaches the game's entry point, so the default
# gate FAILS without one. research/tooling-setup.md has the measurement.
#
# The flags are not interchangeable and each earns its place:
#   -no-ui       no window, no GL context — the only reason this runs without a display
#   -testmode    makes Lua's PCSX.quit(n) terminate the process with status n
#   -dofile      runs our script inside the emulator's LuaJIT VM
#   -lua_stdout  print() from Lua reaches this shell
#   -stdout      the emulator's own log reaches this shell
#   -debugger    arms the breakpoint machinery; without it breakpoints never fire
#   -interpreter the arm64 dynarec SIGILLs on `-run` with a retail BIOS
# Both are measured in research/tooling-setup.md; do not drop either.
#
# The disc image is INPUT ONLY. Redux can write to a mounted ISO (that is how it
# generates PPF patches), so this script hashes the image before and after and fails if
# it moved. A silently rewritten dump is unrecoverable without re-ripping the disc.
#
# This script also samples the executable and exports the bytes in BOKU_EXE_SAMPLES, so
# a gate can prove the GAME is running rather than the BIOS shell (smoke.lua says why).
# They are sampled at launch and never written to a tracked file: the repo ships none of
# the original (CLAUDE.md § "This repo is public and contains none of the original game").

set -eu

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)

REDUX_APP=${REDUX_APP:-$HOME/Dev/dist/pcsx-redux/PCSX-Redux.app}
REDUX_BIN="$REDUX_APP/Contents/MacOS/PCSX-Redux"

iso="$repo/disc/image.cue"
lua="$here/smoke.lua"

while [ $# -gt 0 ]; do
	case "$1" in
	--iso) [ $# -ge 2 ] || { echo "--iso needs a path" >&2; exit 127; }; iso=$2; shift 2 ;;
	--lua) [ $# -ge 2 ] || { echo "--lua needs a path" >&2; exit 127; }; lua=$2; shift 2 ;;
	--) shift; break ;;
	*) break ;;
	esac
done
extra_flags=$*

[ -x "$REDUX_BIN" ] || { echo "no PCSX-Redux at $REDUX_BIN (set REDUX_APP)" >&2; exit 127; }
[ -f "$iso" ] || { echo "no image at $iso" >&2; exit 127; }
[ -f "$lua" ] || { echo "no lua script at $lua" >&2; exit 127; }

# A .cue names the data track; hash what the emulator will actually open. Accept both
# quoted and bare FILE paths, and treat "a .cue with no FILE line we could parse" as a
# hard error rather than quietly hashing the .cue — that reports the image unchanged
# even when it was rewritten, which is the one thing this guard exists to catch.
case "$iso" in
*.cue | *.CUE)
	track=$(sed -n -e 's/^[[:space:]]*FILE[[:space:]]*"\([^"]*\)".*/\1/p' \
		-e 's/^[[:space:]]*FILE[[:space:]][[:space:]]*\([^" ][^ ]*\).*/\1/p' "$iso" | head -1)
	[ -n "$track" ] || { echo "cannot find a FILE line in $iso" >&2; exit 127; }
	case "$track" in
	/*) data=$track ;;
	*) data=$(dirname "$iso")/$track ;;
	esac
	;;
*) data=$iso ;;
esac
[ -f "$data" ] || { echo "the image $data named by $iso does not exist" >&2; exit 127; }

before=$(shasum -a 256 "$data" | cut -d' ' -f1)

# Sample the executable for the gate. A PS-X EXE header is magic, 8 zero bytes, then u32
# pc0 at 0x10 and u32 t_addr at 0x18; the image that goes to t_addr is the 0x800 bytes on.
# Everything here is DERIVED from the file — the load address, the entry point and the
# bytes themselves — so nothing about the game is written down in this repo. The offsets
# land in code that the program never writes to (the last is the entry point), so they
# still match the file long after boot; an all-zero window would assert nothing, so a
# sample that comes back zero is a hard error rather than a check that cannot fail.
exe=${BOKU_EXE:-$repo/disc/files/SCPS_100.88}
[ -f "$exe" ] || { echo "no executable at $exe (run ./make.sh import first, or set BOKU_EXE)" >&2; exit 127; }
hdr=$((0x800))
t_addr=$(od -An -tu4 -j 24 -N 4 "$exe" | tr -d ' ')
pc0=$(od -An -tu4 -j 16 -N 4 "$exe" | tr -d ' ')
samples=
for off in $((0x2000)) $((0x8000)) $((0x1C000)) $((0x28000)) $((0x30000)) $((pc0 - t_addr)); do
	bytes=$(dd if="$exe" bs=1 skip=$((hdr + off)) count=16 2>/dev/null | od -An -tx1 | tr -d ' \n')
	[ ${#bytes} -eq 32 ] || { echo "could not sample 16 bytes at offset $off of $exe" >&2; exit 127; }
	[ "$bytes" != "00000000000000000000000000000000" ] ||
		{ echo "sample at offset $off of $exe is all zero and would assert nothing" >&2; exit 127; }
	samples="$samples $(printf '%x' $((t_addr + off))):$bytes"
done
export BOKU_EXE_SAMPLES="$samples"

# Positional parameters, not a string: "-bios $REDUX_BIOS" expanded unquoted splits a
# path containing a space into two arguments and globs one containing * or ?.
set --
if [ -n "${REDUX_BIOS:-}" ]; then
	[ -f "$REDUX_BIOS" ] || { echo "no BIOS at $REDUX_BIOS" >&2; exit 127; }
	set -- -bios "$REDUX_BIOS"
else
	echo "warning: REDUX_BIOS unset — falling back to the bundled OpenBIOS, which does" >&2
	echo "         not reach this game's entry point. Expect the gate to report exit 5." >&2
fi

# Memory cards of this run's own. Redux otherwise opens ~/.config/pcsx-redux/memcard1.mcd
# and memcard2.mcd, one pair for every run on the machine, and writes them back, so
# concurrent runs read a file another run may be writing. (Suspected of the boot flake in
# research/movies.md § 8; measured not to be its cause, § 9.) Each run gets two empty cards,
# deleted afterwards: boku.save.format_card with its write-test frame (63) a copy of
# frame 0, which is what the shared cards held. Measured: with frame 63 zero, as
# format_card leaves it, the boot writes it and then misses the opening at vsync 6000
# both times it was tried. A caller who passes -memcard1 or -memcard2 gets no private
# cards at all, so pass both.
cards=
case " $extra_flags " in
*" -memcard1 "* | *" -memcard2 "*) ;;
*)
	cards=$(mktemp -d "${TMPDIR:-/tmp}/boku-redux-cards.XXXXXX")
	trap 'rm -rf "$cards"' EXIT
	(cd "$repo" && uv run --quiet python -c "import sys; from boku.save import format_card; card = format_card(); card[0x1F80:0x2000] = card[:0x80]; [open(p, 'wb').write(card) for p in sys.argv[1:]]" \
		"$cards/memcard1.mcd" "$cards/memcard2.mcd") ||
		{ echo "could not write this run's memory cards" >&2; exit 127; }
	set -- "$@" -memcard1 "$cards/memcard1.mcd" -memcard2 "$cards/memcard2.mcd"
	;;
esac

# The wall clock lives here, not in the Lua. A watchdog inside the emulator cannot be
# trusted to fire when the emulator is what has gone wrong, and measured 2026-09-20,
# calling PCSX.quit() from a PCSX.nextTick callback segfaults the process (exit 139)
# with no output at all — so the one path that existed to report a hang was itself the
# least reliable code in the gate. A kill from outside always works.
timeout=${REDUX_TIMEOUT:-300}

status=0
# shellcheck disable=SC2086 # extra_flags is a caller-supplied flag list, split on purpose
"$REDUX_BIN" "$@" -interpreter -debugger -no-ui -testmode -lua_stdout -stdout \
	-loadiso "$iso" -run -dofile "$lua" $extra_flags &
emu=$!

# Detached from this script's stdout on purpose: killing the watchdog leaves its `sleep`
# orphaned, and an orphan that still holds the write end keeps a `run-headless.sh | grep`
# open for the whole timeout after the gate has already answered — a gate that looks hung
# exactly when it has passed.
( sleep "$timeout"; kill -TERM "$emu" 2>/dev/null ) >/dev/null 2>&1 &
watchdog=$!

wait "$emu" || status=$?
kill "$watchdog" 2>/dev/null || true

# SIGTERM from the watchdog arrives as 143; report it as the gate's own timeout code so
# a hang is distinguishable from an assertion failure.
if [ "$status" -eq 143 ]; then
	echo "FATAL: no exit within ${timeout}s — treating as a hang" >&2
	status=2
fi

after=$(shasum -a 256 "$data" | cut -d' ' -f1)
if [ "$before" != "$after" ]; then
	echo "FATAL: $data changed during the run ($before -> $after)" >&2
	exit 70
fi

exit "$status"
