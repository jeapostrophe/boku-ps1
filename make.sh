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
  research-tsv                  regenerate the script walk's five research/data tables from
                                your import; a test diffs them against the tracked copies,
                                which is the gate on the walk. The other generated tables
                                there have their own verbs -- texture-census, texture-plan,
                                movies -- and glyph-table.tsv is kept by hand (research/font.md)
  textures export [arguments]   write one indexed PNG per distinct texture into
                                work/textures/, plus an index of every occurrence
                                (./make.sh textures export --help for the switches)
  textures import DIR           read edited PNGs and report the patches they imply
                                at every place each image is stored
  movies [arguments]            decode every movie on your import into work/movies/*.avi --
                                one file VLC plays per __STR/*.IKI, the XA narration muxed
                                in -- and regenerate research/data/movies.tsv, the list of
                                what each MOVIE id plays. Needs jPSXdec and a JDK
                                (research/movies.md section 4); --tsv regenerates just the
                                table and needs neither
                                (./make.sh movies --help for the switches)
  texture-census                regenerate research/data/texture-census.tsv -- what every
                                distinct image is and whether it carries Japanese -- from
                                work/rec08/distinct.tsv (REC-08's extractor writes that
                                from your import; research/textures.md says how)
  texture-plan                  regenerate research/data/texture-plan.tsv: the path chosen
                                for each text-bearing image (GFX-03). Reads the tracked
                                census, so it needs no disc
  trial [arguments]             build the TXT-04 trial image into build/trial/
                                (./make.sh trial --help for the switches)
  build [arguments]             build a patched image from your import and a
                                translation into build/image/, rebuilding every
                                container a grown line moves
                                (./make.sh build --help for the switches)
  build-days [arguments]        the whole thing: assemble the TXT-05 renderer into
                                build/vwf/edits.json, then build the reviewed
                                translation (days 1-7 + shared.txt) and the English
                                textures (translation/textures/) through it into
                                build/days/ -- proportional English, every line laid
                                out in the dialogue band's pixels, containers grown
                                and members relocated where a line outgrew its
                                sectors. Extra arguments go to `boku build`
  patch [arguments]             emit the release patches into build/patch/
                                (./make.sh patch --help for the switches)
  apply-patch ORIG PATCH --out FILE
                                apply one of our patches, checking both hashes
  packet [arguments]            assemble a translator packet into work/packets/<unit>/:
                                system.md (format, style guide, glossary, the day) given
                                once, one <EVENT>.md per event in order.txt's order, each
                                the event's lines in the day-file shape with the Japanese
                                where the English goes. Never tracked
                                (./make.sh packet --help for the switches)
  save-event EVENT [arguments]  write a translator's answer for one event into its day
                                file, replacing its block or placing it in play order
                                (./make.sh save-event --help for the switches)
  mockup [arguments]            draw every page of the translation files with the font
                                sheet's glyphs at the dialogue band's geometry, one PNG
                                per scene under work/mockup/ -- no emulator; needs
                                build/vwf/edits.json (./make.sh build-days writes it)
                                (./make.sh mockup --help for the switches)
  lint-translation [arguments]  check the committed translation files against your
                                import's script store: ids, select shape, page counts,
                                encodable characters, pixel fit, array byte sizes, and
                                the additive-word heuristic
                                (./make.sh lint-translation --help for the switches)
  coverage [arguments]          per in-game day, every line the player can meet and what
                                the build did with it -- translated, refused (English
                                exists, the image did not get it), missing (never given to
                                a translator) or not-event (a menu, book or title-screen
                                line no day file covers)
                                (./make.sh coverage --help for the switches)
  test [pytest arguments]       run the test suite
  emu-test [pytest arguments]   the tests that boot an emulator (minutes each; skipped by
                                `test`): the movie-subtitle gate on PCSX-Redux and
                                the English title menu on Beetle PSX
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

# TXT-05 + PIPE-03/04 in one command: the renderer patch is assembled and emitted as an
# edit set, then the image build applies it beside the reviewed translation. Two steps and
# not one because the font build needs armips and the image build does not, and because the
# edit set is the artefact the two agree through (boku.build.load_edit_set).
cmd_build_days() {
    local font="build/vwf"
    echo "== 1/2: assembling the TXT-05 renderer -> $font/edits.json =="
    uv run python tools/vwf/build_prototype.py --edits-only --out "$font"
    echo
    echo "== 2/2: building translation/days through it -> build/days/ =="
    uv run boku build --vwf "$font/edits.json" --translation translation/days \
        --textures translation/textures --name days --out build/days --skip-unfitted "$@"
    # A second .cue named by the revision, so the emulator's window title says what is
    # being played while builds and edits overlap (Jay, 2026-09-20). Same image.img.
    local id
    id="$(date -u +%Y%m%dT%H%MZ)-$(git describe --always --dirty --abbrev=8)"
    rm -f build/days/days-*.cue
    cp build/days/image.cue "build/days/days-$id.cue"
    echo "$id" > build/days/BUILD-ID.txt
    echo
    echo "== build id $id: load build/days/days-$id.cue =="
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
    textures)
        exec uv run boku textures "$@"
        ;;
    movies)
        # The gate is tests/test_real_movies.py: it regenerates research/data/movies.tsv
        # and diffs it against the tracked copy, so a note edit that was never run here
        # is caught.
        exec uv run boku movies "$@"
        ;;
    texture-census)
        exec uv run python tools/textures/classify.py "$@"
        ;;
    texture-plan)
        # The gate is tests/test_texture_plan.py: it regenerates the plan and diffs it
        # against the tracked copy, so a rule edit that was never run here is caught.
        exec uv run python tools/textures/make_plan.py "$@"
        ;;
    trial)
        exec uv run boku trial "$@"
        ;;
    build)
        exec uv run boku build "$@"
        ;;
    build-days)
        cmd_build_days "$@"
        ;;
    patch)
        exec uv run boku patch "$@"
        ;;
    apply-patch)
        exec uv run boku apply-patch "$@"
        ;;
    packet)
        exec uv run boku packet "$@"
        ;;
    save-event)
        exec uv run boku save-event "$@"
        ;;
    mockup)
        exec uv run python tools/vwf/mockup.py "$@"
        ;;
    lint-translation)
        exec uv run boku lint "$@"
        ;;
    coverage)
        exec uv run boku coverage "$@"
        ;;
    test)
        exec uv run pytest "$@"
        ;;
    emu-test)
        BOKU_EMU_TESTS=1 exec uv run pytest tests/test_real_movie_subtitle.py \
            tests/test_real_title_menu_beetle.py "$@"
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
