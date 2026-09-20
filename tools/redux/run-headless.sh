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

# Positional parameters, not a string: "-bios $REDUX_BIOS" expanded unquoted splits a
# path containing a space into two arguments and globs one containing * or ?.
set --
if [ -n "${REDUX_BIOS:-}" ]; then
	[ -f "$REDUX_BIOS" ] || { echo "no BIOS at $REDUX_BIOS" >&2; exit 127; }
	set -- -bios "$REDUX_BIOS"
else
	echo "warning: REDUX_BIOS unset — falling back to the bundled OpenBIOS, which does" >&2
	echo "         not reach this game's entry point. Expect the gate to report exit 3." >&2
fi

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

( sleep "$timeout"; kill -TERM "$emu" 2>/dev/null ) &
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
