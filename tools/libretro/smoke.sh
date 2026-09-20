#!/usr/bin/env bash
# Does Beetle PSX still boot a disc image and draw the game, headlessly, on this machine?
#
#   tools/libretro/smoke.sh [CONTENT.cue]           # default disc/image.cue
#
# Needs BOKU_LIBRETRO_CORE (the mednafen_psx dylib) and BOKU_LIBRETRO_SYSTEM (the directory
# holding scph5500.bin); research/tooling-setup.md § "Beetle PSX, headless" says where
# retro-trainer keeps both. Screenshots and the memory card go under work/beetle/smoke/,
# which is gitignored -- nothing is written next to the image.
#
# The exit codes are run_core.py's own, one for one (its --help lists them), plus 9 for
# "run_core.py fell over". The case arms below are the whole table; each is distinct so a
# caller can tell the failures apart.
#
# No `set -e`: mapping run_core's exit code IS the job, so a non-zero status must not end
# the script.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 2
root="$(dirname "$(dirname "$here")")"
content="${1:-$root/disc/image.cue}"
work="$root/work/beetle/smoke"

# The title screen on Beetle with these timings; tools/libretro/boot-to-dialogue.press has
# the rest of the schedule and where the numbers came from.
TITLE_FRAME=3251

fail() {
    echo "smoke: $2" >&2
    exit "$1"
}

[ -n "${BOKU_LIBRETRO_CORE:-}" ] || fail 2 "BOKU_LIBRETRO_CORE is not set"
[ -n "${BOKU_LIBRETRO_SYSTEM:-}" ] || fail 2 "BOKU_LIBRETRO_SYSTEM is not set"
[ -f "$content" ] || fail 2 "no content at $content"

rm -rf "$work"
uv run python "$here/run_core.py" "$content" \
    --work "$work" \
    --frames "$TITLE_FRAME" \
    --shot "$TITLE_FRAME:title" \
    --assert-drawn "$TITLE_FRAME" \
    --log-level 4
status=$?

case "$status" in
    0) echo "smoke: OK -- $content reached the title screen, shot in $work/title.png" ;;
    2) echo "smoke: run_core rejected its arguments" >&2 ;;
    3) echo "smoke: the core at $BOKU_LIBRETRO_CORE did not load" >&2 ;;
    4) echo "smoke: the core could not read $content" >&2 ;;
    5) echo "smoke: a save state failed" >&2 ;;
    6) echo "smoke: the title screen was blank at frame $TITLE_FRAME" >&2 ;;
    7) echo "smoke: no BIOS in $BOKU_LIBRETRO_SYSTEM -- Beetle fell back to its HLE BIOS" >&2 ;;
    8) echo "smoke: frame $TITLE_FRAME was never reached" >&2 ;;
    *) echo "smoke: run_core.py exited $status" >&2; status=9 ;;
esac
exit "$status"
