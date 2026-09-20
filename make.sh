#!/usr/bin/env bash
# Every recurring command in this project is a verb here (CLAUDE.md § "Tooling is Python").
# Add a verb rather than documenting a command line somewhere else.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

usage() {
    cat >&2 <<'EOF'
usage: ./make.sh <verb> [arguments]

  import [SOURCE] [--out DIR]   write the image and its files from your own dump
                                (./make.sh import --help for the source kinds)
  extract [arguments]           decode your import's script into disc/script/
                                (./make.sh extract --help for the switches)
  research-tsv                  regenerate research/data/*.tsv from your import; a
                                test diffs them against the tracked copies, which is
                                the gate on the walk
  trial [arguments]             build the TXT-04 trial image into build/trial/
                                (./make.sh trial --help for the switches)
  patch [arguments]             emit the release patches into build/patch/
                                (./make.sh patch --help for the switches)
  apply-patch ORIG PATCH --out FILE
                                apply one of our patches, checking both hashes
  test [pytest arguments]       run the test suite
  lint                          ruff check + format check
  smoke [image.cue]             boot image.cue (default disc/image.cue) on both
                                headless emulator gates -- PCSX-Redux and Beetle PSX
                                -- and report each one's result; missing prerequisites
                                (emulator, env var, BIOS) fail loudly rather than
                                being skipped (research/tooling-setup.md)

Everything runs through uv, which installs Python and the dev tools on first use.
EOF
}

# ENV-05: the two headless boot gates, run in sequence and reported clearly, so a
# contributor never has to go find tools/redux/run-headless.sh or tools/libretro/smoke.sh
# by hand. Each gate's own prerequisites are checked here, before it runs, because
# tools/redux/run-headless.sh only *warns* about a missing REDUX_BIOS and then spends
# 10-20s failing slowly -- that is not "say which prerequisite and exit non-zero".
cmd_smoke() {
    local image="${1:-}"
    local status=0 redux_status=0 beetle_status=0

    echo "== gate 1/2: PCSX-Redux headless boot (tools/redux/run-headless.sh) =="
    local redux_app="${REDUX_APP:-$HOME/Dev/dist/pcsx-redux/PCSX-Redux.app}"
    if [ ! -x "$redux_app/Contents/MacOS/PCSX-Redux" ]; then
        echo "smoke: PCSX-Redux is not installed at $redux_app/Contents/MacOS/PCSX-Redux" >&2
        echo "       install it, or set REDUX_APP to point at it -- research/tooling-setup.md" >&2
        echo "       section \"Reproducing it on a fresh Mac\"" >&2
        redux_status=127
    elif [ -z "${REDUX_BIOS:-}" ]; then
        echo "smoke: REDUX_BIOS is not set -- the bundled OpenBIOS never reaches this game's" >&2
        echo "       entry point, so the gate would only fail slowly. Set REDUX_BIOS to a" >&2
        echo "       retail Japanese BIOS dump -- research/tooling-setup.md section \"The BIOS" >&2
        echo "       question\"" >&2
        redux_status=127
    elif [ ! -f "$REDUX_BIOS" ]; then
        echo "smoke: REDUX_BIOS=$REDUX_BIOS does not exist -- research/tooling-setup.md" >&2
        echo "       section \"The BIOS question\"" >&2
        redux_status=127
    elif [ -n "$image" ]; then
        ./tools/redux/run-headless.sh --iso "$image" || redux_status=$?
    else
        ./tools/redux/run-headless.sh || redux_status=$?
    fi
    if [ "$redux_status" -eq 0 ]; then
        echo "== gate 1/2: PCSX-Redux OK (exit 0) =="
    else
        echo "== gate 1/2: PCSX-Redux FAILED (exit $redux_status) ==" >&2
        status=1
    fi

    echo
    echo "== gate 2/2: Beetle PSX headless boot (tools/libretro/smoke.sh) =="
    if [ -z "${BOKU_LIBRETRO_CORE:-}" ]; then
        echo "smoke: BOKU_LIBRETRO_CORE is not set -- set it to the mednafen_psx_libretro" >&2
        echo "       dylib -- research/tooling-setup.md section \"Beetle PSX, headless\"" >&2
        beetle_status=127
    elif [ ! -f "$BOKU_LIBRETRO_CORE" ]; then
        echo "smoke: BOKU_LIBRETRO_CORE=$BOKU_LIBRETRO_CORE does not exist" >&2
        beetle_status=127
    elif [ -z "${BOKU_LIBRETRO_SYSTEM:-}" ]; then
        echo "smoke: BOKU_LIBRETRO_SYSTEM is not set -- set it to the directory holding" >&2
        echo "       scph5500.bin -- research/tooling-setup.md section \"Beetle PSX, headless\"" >&2
        beetle_status=127
    elif [ ! -d "$BOKU_LIBRETRO_SYSTEM" ]; then
        echo "smoke: BOKU_LIBRETRO_SYSTEM=$BOKU_LIBRETRO_SYSTEM is not a directory" >&2
        beetle_status=127
    elif [ -n "$image" ]; then
        ./tools/libretro/smoke.sh "$image" || beetle_status=$?
    else
        ./tools/libretro/smoke.sh || beetle_status=$?
    fi
    if [ "$beetle_status" -eq 0 ]; then
        echo "== gate 2/2: Beetle PSX OK (exit 0) =="
    else
        echo "== gate 2/2: Beetle PSX FAILED (exit $beetle_status) ==" >&2
        status=1
    fi

    echo
    if [ "$status" -eq 0 ]; then
        echo "smoke: both gates passed"
    else
        echo "smoke: FAILED -- redux exit $redux_status, beetle exit $beetle_status" >&2
    fi
    return "$status"
}

verb="${1:-}"
shift || true

case "$verb" in
    import)
        exec uv run boku import "$@"
        ;;
    extract)
        exec uv run boku extract "$@"
        ;;
    research-tsv)
        # The port's gate: the tables have to come back byte for byte. `git diff
        # research/data` afterwards is the answer.
        exec uv run boku extract --research-tsv research/data "$@"
        ;;
    trial)
        exec uv run boku trial "$@"
        ;;
    patch)
        exec uv run boku patch "$@"
        ;;
    apply-patch)
        exec uv run boku apply-patch "$@"
        ;;
    test)
        exec uv run pytest "$@"
        ;;
    lint)
        uv run ruff check .
        exec uv run ruff format --check .
        ;;
    smoke)
        cmd_smoke "$@"
        ;;
    ""|-h|--help|help)
        usage
        exit 0
        ;;
    *)
        echo "./make.sh: unknown verb '$verb'" >&2
        usage
        exit 2
        ;;
esac
