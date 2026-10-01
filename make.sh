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
                                movies, voice-only -- and glyph-table.tsv is kept by hand (research/font.md)
  textures export [arguments]   write one indexed PNG per distinct texture into
                                work/textures/, plus an index of every occurrence
                                (./make.sh textures export --help for the switches)
  textures import DIR           read edited PNGs and report the patches they imply
                                at every place each image is stored
  textures check [DIR]          typeset translation/textures/ (or DIR) into its textures
                                from your import and report what each recipe made or
                                refused -- the diary's per-page lint; --out DIR writes
                                the rebuilt images
  movies [arguments]            decode every movie on your import into work/movies/*.avi --
                                one file VLC plays per __STR/*.IKI, the XA narration muxed
                                in -- and regenerate research/data/movies.tsv, the list of
                                what each MOVIE id plays. Needs jPSXdec and a JDK
                                (research/movies.md section 4); --tsv regenerates just the
                                table and needs neither
                                (./make.sh movies --help for the switches)
  voice-only [arguments]        regenerate research/data/voice-only.tsv -- one row per XA
                                instruction, a voice with no text -- and decode every
                                clip, and the voiced movies' audio, into work/voice/;
                                --transcribe runs Whisper (Japanese) over them there,
                                --tsv regenerates just the table
                                (./make.sh voice-only --help for the switches)
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
                                build/vwf/edits.json, then build the translation
                                (translation/days/) and the English textures
                                (translation/textures/) through it into
                                build/days/ -- proportional English, every line laid
                                out in the dialogue band's pixels, containers grown
                                and members relocated where a line outgrew its
                                sectors; then the reader (work/reader/) against it.
                                Extra arguments go to `boku build`
  patch [arguments]             emit the release patches into build/patch/
                                (./make.sh patch --help for the switches)
  apply-patch ORIG PATCH --out FILE
                                apply one of our patches, checking both hashes
  export-to-mode-one [arguments]
                                pack build/days/ as Mode One's one/roms/boku.chd in
                                ~/Dev/retro-trainer (--mode-one DIR, or $BOKU_MODE_ONE)
                                and pin its SHA-1 in one/index/boku.sha1; needs chdman
                                (./make.sh export-to-mode-one --help for the switches)
  release [arguments]           cut a release of HEAD: refuse anything uncommitted, run
                                build-days, then write the patches against the Redump
                                base, the .cue and the notes into release/v<version>/
                                (v<version> is HEAD's tag, else a snapshot named by git
                                describe) -- the xdelta in one zip, the PPF in its own
                                (--no-ppf: no PPF) -- and apply each patch back; beside
                                them the patched disc as image, .cue and .chd, and the
                                dump the same way in release/v0/ (--base-chd: your .chd)
                                (uv run boku release --help)
  release-row DIR               write the tagged release DIR's two SHA-1s into README.md's
                                "Which version do I have?" table, from the zip it posts;
                                commit and push README.md before publish-release --yes,
                                which refuses a release the README on GitHub's default
                                branch does not list
  publish-release DIR [--yes]   print the gh release create line that posts DIR's zips and
                                notes under its (already pushed) tag; post only with --yes
                                (--draft, --prerelease, --repo OWNER/REPO; --withdraw-ppf
                                takes the PPF off a posted release)
  packet [arguments]            assemble a translator packet into work/packets/<unit>/:
                                system.md (format, story bible, style guide, glossary,
                                checklist -- each whole) given once, one <EVENT>.md per
                                event in order.txt's order, each the event's lines in the
                                day-file shape with the Japanese where the English goes;
                                --arrays does the same per menu, book and screen for
                                translation/days/arrays.txt; --game is the whole game in
                                play order (translation/README.md). Never tracked
                                (./make.sh packet --help for the switches)
  save-event PART [arguments]   write a translator's answer for one event or surface into
                                its day file, replacing its block or placing it at its
                                place in the packet's order.txt (--order)
                                (./make.sh save-event --help for the switches)
  mockup [arguments]            draw every page of the translation files with the font
                                sheet's glyphs at the dialogue band's geometry, one PNG
                                per scene under work/mockup/ -- no emulator; needs
                                build/vwf/edits.json (./make.sh build-days writes it)
                                (./make.sh mockup --help for the switches)
  lint-translation [arguments]  check the committed translation files against your
                                import's script store: ids, select shape, page counts,
                                encodable characters, pixel fit, array byte sizes, and
                                the additive-word heuristic; and translation/movies.txt,
                                the movie subtitles (translation/README.md)
                                (./make.sh lint-translation --help for the switches)
  reader [arguments]            the whole translation, in order, as one page to read and
                                cite ids from -> work/reader/index.html (boku/reader.py);
                                build-days runs it too
  coverage [arguments]          per in-game day, every line the player can meet and what
                                the build did with it -- translated, refused (English
                                exists, the image did not get it), missing (never given to
                                a translator) or not-event (a menu, book or title-screen
                                line arrays.txt has no English for yet)
                                (./make.sh coverage --help for the switches)
  save --base B --out CARD [..] write one memory-card save from parameters: the morning it
                                wakes on, the stars that pick the ending, any flag or saved
                                byte (./make.sh save --help; research/save-format.md)
  saves                         the save corpus into work/saves/corpus/ -- every morning
                                from August 2 to 31, one card per ending and a finished
                                game -- starting from a new game's RAM, dumped once on Beetle
  duckstation-cards             the same saves packed a few to a card for playing them in
                                DuckStation -> work/saves/duckstation/ (research/save-format.md
                                § "Playing a generated save in DuckStation")
  boot-save CARD [arguments]    boot CARD's slot-1 save on Beetle to the morning it wakes
                                on; shoot it, save a state to resume from, and check the
                                clock (tools/libretro/boot_save.py --help)
  sumo-bout CARD [arguments]    boot CARD on Beetle and play it into a bug-sumo bout with the
                                first bug of its cage; check the fighter the game builds;
                                --mantis fights the mantis and follows E1754 to the shortcut
                                (tools/libretro/sumo_bout.py --help; research/sumo.md)
  examine CARD MAP EVENT [..]   wake CARD's save in MAP on Beetle, examine EVENT's spot and
                                log every voice clip it plays (tools/libretro/examine.py --help)
  movie-timing [--write]        every movie cue's timing against the reviewed transcripts
                                in work/voice/reviewed (onset, end, 1.5 s, 17 cps); --write
                                moves the frames of translation/movies.txt to pass where
                                they can, never the English (boku/movie_timing.py)
  movie-review [MOVIE...]       every cue at its first, middle and last frame on Beetle, and an
                                MP4 with the narration, from build/days -> work/movie-review/
                                index.html (tools/libretro/movie_review.py --help)
  screenshots [arguments]       the README's screenshots, one screen of each kind the patch
                                translates, from build/days on Beetle -> docs/screenshots/
                                (tools/libretro/screenshots.py --help)
  epilogue-review [N...]        the five epilogues on Beetle from build/days: when each
                                subtitle page was up against the stills and the production
                                card, beside what clips.txt's times predict, with a shot of
                                each page -> work/epilogue-review/index.html; exits 1 if a
                                page was up with the card (tools/libretro/epilogue_review.py)
  test [pytest arguments]       run the test suite
  emu-test [pytest arguments]   the tests that boot an emulator (minutes each; skipped by
                                `test`): the movie, voice-only and native-clip subtitle
                                gates on PCSX-Redux, and on Beetle PSX the English title
                                menu, buttons, the generated-save boot, the bug-sumo bout, the
                                kite-flying HUD and the native-clip subtitles reached as
                                play reaches them
  lint                          ruff check + format check
  smoke [image.cue]             boot image.cue (default disc/image.cue) on both
                                headless emulator gates -- PCSX-Redux and Beetle PSX
                                -- and report each one's result; missing prerequisites
                                (emulator, core, BIOS) fail loudly rather than
                                being skipped (research/tooling-setup.md)

Everything runs through uv, which installs Python and the dev tools on first use. The
verbs that boot an emulator find Beetle PSX's core, its BIOS directory and PCSX-Redux's
BIOS in ~/Dev/retro-trainer/config/ (or $BOKU_MODE_ONE's) unless BOKU_LIBRETRO_CORE,
BOKU_LIBRETRO_SYSTEM or REDUX_BIOS says otherwise (tools/libretro/emulator_paths.py).
EOF
}

# ENV-09: the emulator tests read BOKU_LIBRETRO_CORE, BOKU_LIBRETRO_SYSTEM and REDUX_BIOS from
# the environment, so `test` and `emu-test` export whichever tools/libretro/emulator_paths.py
# finds; the tools themselves resolve them (run_core.py, field.py, smoke.sh, run-headless.sh).
emulator_env() {
    eval "$(uv run python tools/libretro/emulator_paths.py --exports)"
}

# ENV-05: the two headless boot gates, run in sequence and reported clearly, so a
# contributor never has to go find tools/redux/run-headless.sh or tools/libretro/smoke.sh
# by hand. Redux's BIOS is checked here, before its gate runs, because
# tools/redux/run-headless.sh only *warns* about a missing BIOS and then spends 10-20s
# failing slowly -- that is not "say which prerequisite and exit non-zero". smoke.sh checks
# Beetle's own.
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
    elif ! uv run python tools/libretro/emulator_paths.py --check bios >/dev/null; then
        # The bundled OpenBIOS never reaches this game's entry point, so without a retail
        # BIOS the gate would only fail slowly; the check has said what to set.
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
    if [ -n "$image" ]; then
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
    local font="build/vwf" began="build/.days-began"
    # The id is stamped with the time the build began, so an edit saved while it runs
    # reads as newer than the build (boku.reader.stale_build).
    mkdir -p build && touch "$began"
    echo "== 1/3: assembling the TXT-05 renderer -> $font/edits.json =="
    uv run python tools/vwf/build_prototype.py --edits-only --out "$font"
    echo
    echo "== 2/3: building translation/days through it -> build/days/ =="
    uv run boku build --vwf "$font/edits.json" --translation translation/days \
        --textures translation/textures --name days --out build/days --skip-unfitted "$@"
    # A dry run writes no image, so it gets no id and no reader: stamping one would say the
    # image has edits it does not.
    case " $* " in *" --dry-run "*) rm -f "$began"; return ;; esac
    # A second .cue named by the revision, so the emulator's window title says what is
    # being played while builds and edits overlap (Jay, 2026-09-20). Same image.img.
    local id
    id="$(date -u +%Y%m%dT%H%MZ)-$(git describe --always --dirty --abbrev=8 --exclude='*')"
    rm -f build/days/days-*.cue
    cp build/days/image.cue "build/days/days-$id.cue"
    echo "$id" > build/days/BUILD-ID.txt
    # REL-04: a release is only of a build given no arguments (boku.release.BUILD_ARGS_NAME).
    printf '%s\n' "$@" > build/days/BUILD-ARGS.txt
    touch -r "$began" build/days/BUILD-ID.txt
    rm -f "$began"
    # TRN-14: the reader is rewritten with every build, so it can never be older than the
    # image it is read against (Jay, 2026-09-25).
    echo
    echo "== 3/3: the reader, against this build -> work/reader/index.html =="
    uv run boku reader --build build/days
    echo
    echo "== build id $id: load build/days/days-$id.cue =="
}

# REL-04: a release is HEAD and nothing else. The tree is checked before the build, so a
# dirty one wastes no build, and again by `boku release` after it, which also refuses a build
# of any other commit or one given arguments: the release is the default build.
cmd_release() {
    case " $* " in *" --preflight "*) uv run boku release "$@"; return ;; esac
    uv run boku release --preflight
    cmd_build_days
    echo
    echo "== the release -> release/v<version>/ =="
    uv run boku release "$@"
}

# ENV-06: the corpus's base is a new game's RAM at the first dialogue, dumped once from your own
# import; what that base can and cannot reach is research/save-format.md's.
# `saves` writes a save per card for the headless tools; ENV-07's `duckstation-cards` packs the
# same saves a card per purpose, to play in DuckStation.
saves_run() {
    local dir="work/saves" mode="$1" out="$2"
    shift 2
    if [ ! -f "$dir/newgame.ram" ]; then
        echo "== 1/2: a new game's RAM, from a Beetle boot to the first dialogue -> $dir/newgame.ram =="
        uv run python tools/libretro/run_core.py disc/image.cue --work "$dir/base" \
            --frames 5850 --press-file tools/libretro/boot-to-dialogue.press \
            --ram-out 5850:newgame --quiet
        mv "$dir/base/newgame.ram" "$dir/newgame.ram"
    else
        echo "== 1/2: $dir/newgame.ram is already there (delete it to dump it again) =="
    fi
    echo "== 2/2: the saves -> $dir/$out/ =="
    uv run boku save --base "$dir/newgame.ram" "$mode" --out "$dir/$out" "$@"
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
    voice-only)
        # The gate is tests/test_real_voice.py: it regenerates research/data/voice-only.tsv
        # and diffs it against the tracked copy.
        exec uv run boku voice-only "$@"
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
    export-to-mode-one)
        exec uv run boku export-to-mode-one "$@"
        ;;
    release)
        cmd_release "$@"
        ;;
    release-row)
        exec uv run boku release-row "$@"
        ;;
    publish-release)
        exec uv run boku publish-release "$@"
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
    reader)
        exec uv run boku reader "$@"
        ;;
    coverage)
        exec uv run boku coverage "$@"
        ;;
    save)
        exec uv run boku save "$@"
        ;;
    saves)
        saves_run --corpus corpus "$@"
        ;;
    duckstation-cards)
        saves_run --cards duckstation "$@"
        ;;
    boot-save)
        exec uv run python tools/libretro/boot_save.py "$@"
        ;;
    sumo-bout)
        exec uv run python tools/libretro/sumo_bout.py "$@"
        ;;
    examine)
        exec uv run python tools/libretro/examine.py "$@"
        ;;
    movie-timing)
        exec uv run python -m boku.movie_timing "$@"
        ;;
    movie-review)
        exec uv run python tools/libretro/movie_review.py "$@"
        ;;
    screenshots)
        exec uv run python tools/libretro/screenshots.py "$@"
        ;;
    epilogue-review)
        exec uv run python tools/libretro/epilogue_review.py "$@"
        ;;
    test)
        emulator_env
        exec uv run pytest "$@"
        ;;
    emu-test)
        emulator_env
        BOKU_EMU_TESTS=1 exec uv run pytest tests/test_real_movie_subtitle.py \
            tests/test_real_texture_text_beetle.py tests/test_real_texture_buttons.py \
            tests/test_real_texture_books.py tests/test_real_credits_card.py \
            tests/test_real_texture_records.py tests/test_real_texture_sumo.py \
            tests/test_real_texture_kite.py \
            tests/test_real_save_boot.py tests/test_real_sumo_bout.py \
            tests/test_real_voice_subtitle.py tests/test_real_clip_subtitle.py \
            tests/test_real_clip_subtitle_beetle.py tests/test_real_sumo_voice.py "$@"
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
