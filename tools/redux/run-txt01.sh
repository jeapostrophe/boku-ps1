#!/bin/sh
# Run one of the TXT-01 emulator scripts headlessly:
#
#   tools/redux/run-txt01.sh <script.lua> [extra redux flags...]
#
# A thin layer over run-headless.sh (which owns the flags, the wall clock and the
# image-unchanged guard). Adds what the scripts here share: BOKU_REDUX_DIR so they can
# dofile lib.lua, BOKU_REPO, BOKU_WORK (gitignored scratch for screenshots and save
# states — game pixels and RAM never leave it). run-headless.sh finds the BIOS.
# Set REDUX_TIMEOUT (seconds) for long runs.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
[ $# -ge 1 ] || { echo "usage: $0 <script.lua> [redux flags]" >&2; exit 127; }
script=$1; shift
case "$script" in */*) ;; *) script="$here/$script" ;; esac

export BOKU_REDUX_DIR="$here"
export BOKU_REPO="$repo"
export BOKU_WORK="${BOKU_WORK:-$repo/work/txt01-emu}"
mkdir -p "$BOKU_WORK/shots" "$BOKU_WORK/states"

exec "$here/run-headless.sh" --lua "$script" -- "$@"
