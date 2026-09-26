#!/bin/sh
# Run one of the scripts in this directory against an image OTHER than disc/image.cue:
#
#   tools/redux/run-on-image.sh <image.cue> <script.lua> [extra redux flags...]
#
# run-txt01.sh is the same wrapper pinned to the contributor's own import; this one takes
# the image, which is what `TXT-04` needs — the whole point of that row is booting a
# *rebuilt* image (`./make.sh trial` writes build/trial/image.cue) and looking at it, with
# no RAM pokes anywhere. run-headless.sh still owns the flags, the wall clock and the
# image-unchanged guard, and it guards whichever image is passed here.
#
# BOKU_WORK defaults to work/txt04 rather than work/txt01-emu: shots of a patched image
# are a different experiment from the notes in renderer-runtime.md, and both are pixels of
# the game, so both stay under the gitignored work/.
#
# BOKU_EXE still points at disc/files/SCPS_100.88 unless you set it. run-headless.sh reads
# it only to sample bytes for smoke.lua's "is the game running" check; against a patched
# image those samples are the *unpatched* ones, which is harmless here (the three patched
# words are nowhere near the sampled offsets) and would matter only to smoke.lua.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
[ $# -ge 2 ] || { echo "usage: $0 <image.cue> <script.lua> [redux flags]" >&2; exit 127; }
image=$1; shift
script=$1; shift
case "$script" in */*) ;; *) script="$here/$script" ;; esac
[ -f "$image" ] || { echo "no image at $image" >&2; exit 127; }

export BOKU_REDUX_DIR="$here"
export BOKU_REPO="$repo"
export BOKU_WORK="${BOKU_WORK:-$repo/work/txt04}"
mkdir -p "$BOKU_WORK/shots" "$BOKU_WORK/states"

exec "$here/run-headless.sh" --iso "$image" --lua "$script" -- "$@"
