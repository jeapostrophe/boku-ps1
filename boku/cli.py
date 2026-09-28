"""`boku` -- the project's command line. One subcommand per pipeline step.

Run it through `make.sh`, which is where the documented command lines live
(CLAUDE.md § "Tooling is Python, run through uv").
"""

from __future__ import annotations

import argparse
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import DEFAULT_DISC_DIR
from boku.build import DEFAULT_BUILD_NAME, DEFAULT_IMAGE, IMAGE_NAME, main_build
from boku.coverage import add_arguments as add_coverage_arguments
from boku.extract import SCRIPT_DIR_NAME, main_extract
from boku.importer import DEFAULT_OUT_DIR, SOURCE_ENV_VAR, main_import
from boku.lint import add_arguments as add_lint_arguments
from boku.mode_one import add_arguments as add_mode_one_arguments
from boku.movies import add_arguments as add_movies_arguments
from boku.packets import add_arguments as add_packet_arguments
from boku.packets import add_save_arguments as add_save_event_arguments
from boku.patchfile import DEFAULT_OUT_DIR as PATCH_OUT_DIR
from boku.patchfile import MANIFEST_NAME, main_apply_patch, main_patch
from boku.reader import DEFAULT_BUILD_DIR
from boku.reader import add_arguments as add_reader_arguments
from boku.release import (
    RELEASE_ROOT,
    VERSIONS_HEADING,
    main_publish,
    main_release,
    main_release_row,
)
from boku.save import add_arguments as add_save_arguments
from boku.texture_text import TEXTURE_TEXT_DIR
from boku.texture_text import main_check as main_texture_check
from boku.textures import DEFAULT_OUT_DIR as TEXTURES_OUT_DIR
from boku.textures import INDEX_NAME as TEXTURES_INDEX_NAME
from boku.textures import main_export as main_textures_export
from boku.textures import main_import as main_textures_import
from boku.trial import DEFAULT_OUT_DIR as TRIAL_OUT_DIR
from boku.trial import TRIAL_TEXT, main_trial, patch_words
from boku.voice import add_arguments as add_voice_arguments

DEFAULT_MODIFIED_IMAGE = TRIAL_OUT_DIR / IMAGE_NAME


def palette_number(text: str) -> int:
    """A CLUT index. Refused here rather than a thousand images into an export."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a palette number") from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"there is no palette {value}; CLUTs count from 0")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boku",
        description="Tools for the boku-ps1 English translation patch.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    importer = subcommands.add_parser(
        "import",
        help="verify your own dump and write the image and its files",
        description=(
            "Verify a dump of SCPS-10088 against the Redump checksum and write the raw "
            "image, the files on it and a manifest. Nothing it writes is ever committed."
        ),
    )
    importer.add_argument(
        "source",
        nargs="?",
        metavar="SOURCE",
        help=f".chd, .cue or raw .bin/.img to import; defaults to ${SOURCE_ENV_VAR}",
    )
    importer.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        metavar="DIR",
        help=f"directory to write (default: {DEFAULT_OUT_DIR}/); replaced on success",
    )
    importer.set_defaults(run=lambda args: main_import(args.source, args.out))

    extract = subcommands.add_parser(
        "extract",
        help="decode the whole Japanese script out of your import",
        description=(
            f"Walk your import's archive and executable and write {SCRIPT_DIR_NAME}/ "
            "beside them: every logical line with its id, speaker, layout and physical "
            "sites, a flow graph per event, and the code-file arrays. It reads only the "
            "import and writes only that one directory, and neither is ever committed."
        ),
    )
    extract.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        metavar="DIR",
        help=f"the import to read (default: {DEFAULT_DISC_DIR}/)",
    )
    extract.add_argument(
        "--research-tsv",
        type=Path,
        metavar="DIR",
        help=(
            "also regenerate the five research/data tables into DIR; a test diffs them "
            "against the tracked copies, which is the gate on this walk"
        ),
    )
    extract.set_defaults(run=lambda args: main_extract(args.disc, args.research_tsv))

    trial = subcommands.add_parser(
        "trial",
        help="build the TXT-04 trial image from your import",
        description=(
            "Copy the raw image and apply the TXT-04 trial to the copy in place: the "
            "renderer immediates from research/text-renderer.md, the band from "
            "research/renderer-runtime.md, and optionally English over one line or an "
            "identifying tag over every event message. Every sector written gets fresh "
            "EDC and ECC."
        ),
    )
    trial.add_argument(
        "source",
        nargs="?",
        metavar="IMAGE",
        help=f"raw image to copy and patch (default: {DEFAULT_IMAGE})",
    )
    trial.add_argument(
        "--out",
        type=Path,
        default=TRIAL_OUT_DIR,
        metavar="DIR",
        help=f"directory to write the image, cue and manifest (default: {TRIAL_OUT_DIR}/)",
    )
    trial.add_argument(
        "--line",
        metavar="ID",
        help=(
            "overwrite every physical copy of one line: a logical line id such as "
            "E0112.0 or exe@80046214.3 (they are listed in disc/script/lines.jsonl), "
            "or a 12-hex-digit line_key"
        ),
    )
    trial.add_argument(
        "--text",
        default=TRIAL_TEXT,
        metavar="ENGLISH",
        help=f"what --line writes (default: {TRIAL_TEXT!r})",
    )
    trial.add_argument(
        "--all-lines-marker",
        action="store_true",
        help=(
            "write each event message's own site id over it, so whatever line the game "
            "reaches says which line it is; feed that id back as --line"
        ),
    )
    trial.add_argument(
        "--no-renderer-patch",
        action="store_true",
        help="leave the three immediates alone (with nothing else asked for: the null build)",
    )
    trial.add_argument(
        "--band",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "redraw the dialogue strip as a band across the foot of the screen and put "
            "the pen inside it, so horizontal text is legible over scenery "
            "(default: on whenever the renderer patch is)"
        ),
    )
    trial.set_defaults(
        run=lambda args: main_trial(
            args.source,
            args.out,
            args.line,
            args.text,
            args.all_lines_marker,
            not args.no_renderer_patch,
            args.band,
        )
    )

    builder = subcommands.add_parser(
        "build",
        help="build a patched image from your import and a translation",
        description=(
            "PIPE-04's general build: read your import, lay a translation out in pixels, "
            "rebuild every container a grown line moves (PIPE-03), and write a patched "
            "image, cue and manifest. Every byte range is verified against the image "
            "before anything is written and every sector written gets fresh EDC and ECC. "
            "Nothing is cut to fit: a line that does not fit its box, or a member that "
            "would outgrow its sectors, is refused with its numbers."
        ),
    )
    builder.add_argument(
        "source",
        nargs="?",
        metavar="IMAGE",
        help=f"raw image to copy and patch (default: {DEFAULT_IMAGE})",
    )
    builder.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="DIR",
        help="directory to write the image, cue and manifest (default: build/<name>/)",
    )
    builder.add_argument(
        "--translation",
        type=Path,
        metavar="DIR",
        help=(
            "directory of translation files to apply; with none, only the executable "
            "patches are written. The format is translation/days/README.md's (PLAN PIPE-02)"
        ),
    )
    builder.add_argument(
        "--cells",
        type=Path,
        metavar="FILE",
        help=(
            "a JSON character -> cell map with per-cell pixel advances, as TXT-05's font "
            "build emits; without it English is spelled with the stock full-width Latin "
            "cells at a fixed 14 px"
        ),
    )
    # `--vwf` installs a renderer, so it is the opposite of "leave the executable alone";
    # accepting both would silently honour one and produce neither the stock-renderer
    # image a contributor asked for nor a coherent VWF one.
    renderer = builder.add_mutually_exclusive_group()
    renderer.add_argument(
        "--vwf",
        type=Path,
        metavar="FILE",
        help=(
            "a TXT-05 renderer edit set (build/vwf/edits.json, written by "
            "`tools/vwf/build_prototype.py --edits-only`): the executable words, the "
            "rebuilt overlays and the rebuilt font sheet, applied as verified byte edits, "
            "and the character map they were derived from. It replaces the TXT-04 "
            "renderer immediates, which patch the same words"
        ),
    )
    builder.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        metavar="DIR",
        help=f"the import whose text sites are walked (default: {DEFAULT_DISC_DIR}/)",
    )
    builder.add_argument(
        "--name",
        default=DEFAULT_BUILD_NAME,
        metavar="NAME",
        help=(
            f"what the manifest calls this build, and the directory under build/ it goes "
            f"in (default: {DEFAULT_BUILD_NAME})"
        ),
    )
    builder.add_argument(
        "--skip-unfitted",
        action="store_true",
        help=(
            "leave a line that fails a lint in Japanese and report it, instead of "
            "refusing the whole build; the English is never shortened either way"
        ),
    )
    builder.add_argument(
        "--dry-run",
        action="store_true",
        help="lay the translation out and report what fits, writing nothing",
    )
    renderer.add_argument(
        "--no-renderer-patch",
        action="store_true",
        help=(
            "leave the executable alone; without it the TXT-04 renderer and band words "
            "are applied, because English drawn vertically down the right-hand strip is "
            "illegible. Not combinable with --vwf, which installs a renderer"
        ),
    )
    builder.add_argument(
        "--textures",
        type=Path,
        metavar="DIR",
        help=(
            "a directory of texture strings (translation/textures/): each texture a "
            "recipe exists for is typeset in English from your import and applied as "
            "verified byte edits (boku.texture_text)"
        ),
    )
    builder.add_argument(
        "--no-label",
        action="store_true",
        help=(
            "insert the English undressed: no speaker label, and neither the opening nor "
            "the closing mark the Japanese drew around it (the lint's --no-label measures "
            "the same bare text)"
        ),
    )
    builder.set_defaults(
        run=lambda args: main_build(
            args.source,
            args.out,
            args.translation,
            args.cells,
            args.disc,
            args.name,
            args.skip_unfitted,
            args.dry_run,
            ()
            if (args.no_renderer_patch or args.vwf)
            else tuple(w.edit() for w in patch_words(True, True)),
            args.vwf,
            not args.no_label,
            args.textures,
        )
    )

    patch = subcommands.add_parser(
        "patch",
        help="emit the release patches from an original and a built image",
        description=(
            "Write an xdelta (canonical) and a PPF (DuckStation and the common patchers) turning "
            "the original image into the built one, plus a PATCH.json and a README "
            "stating size, CRC32, MD5 and SHA-1 of both sides. Neither image is written."
        ),
    )
    patch.add_argument(
        "--original",
        type=Path,
        default=DEFAULT_IMAGE,
        metavar="IMAGE",
        help=f"the dump the patch applies to (default: {DEFAULT_IMAGE})",
    )
    patch.add_argument(
        "--modified",
        type=Path,
        default=DEFAULT_MODIFIED_IMAGE,
        metavar="IMAGE",
        help=f"the image the patch produces (default: {DEFAULT_MODIFIED_IMAGE})",
    )
    patch.add_argument(
        "--out",
        type=Path,
        default=PATCH_OUT_DIR,
        metavar="DIR",
        help=f"directory to write (default: {PATCH_OUT_DIR}/); replaced on success",
    )
    patch.set_defaults(run=lambda args: main_patch(args.original, args.modified, args.out))

    apply_patch = subcommands.add_parser(
        "apply-patch",
        help="apply one of our patches, checking the hashes on both sides",
        description=(
            "Apply a .ppf or .xdelta to a dump. The dump's SHA-1 is checked against the "
            f"release's {MANIFEST_NAME} (or the fingerprint in a lone PPF's description) "
            "before anything is produced, and the result's afterwards; either failing "
            "leaves nothing behind. The dump itself is only ever read."
        ),
    )
    apply_patch.add_argument("original", type=Path, metavar="ORIGINAL", help="your own dump")
    apply_patch.add_argument("patch", type=Path, metavar="PATCH", help="the .ppf or .xdelta")
    apply_patch.add_argument(
        "--out", type=Path, required=True, metavar="FILE", help="the patched image to write"
    )
    apply_patch.add_argument(
        "--expect-original-sha1",
        metavar="SHA1",
        help=f"what the dump must hash to, when there is no {MANIFEST_NAME} beside the patch",
    )
    apply_patch.add_argument(
        "--expect-result-sha1",
        metavar="SHA1",
        help="what the patched image must hash to",
    )
    apply_patch.set_defaults(
        run=lambda args: main_apply_patch(
            args.original,
            args.patch,
            args.out,
            args.expect_original_sha1,
            args.expect_result_sha1,
        )
    )

    release = subcommands.add_parser(
        "release",
        help="turn HEAD's days build into release/v<version>/ (./make.sh release builds it first)",
        description="PLAN REL-04: what a release holds and checks is boku.release's docstring.",
    )
    release.add_argument(
        "--preflight",
        action="store_true",
        help="only check the tree is clean and print the version it would release",
    )
    release.add_argument(
        "--base",
        type=Path,
        default=DEFAULT_IMAGE,
        metavar="IMAGE",
        help=f"the Redump dump the patches apply to (default: {DEFAULT_IMAGE})",
    )
    release.add_argument(
        "--build",
        type=Path,
        default=DEFAULT_BUILD_DIR,
        metavar="DIR",
        help="the days build of HEAD (default: build/days)",
    )
    release.add_argument(
        "--out",
        type=Path,
        default=RELEASE_ROOT,
        metavar="DIR",
        help=f"where release/v<version>/ goes (default: {RELEASE_ROOT}/)",
    )
    release.add_argument(
        "--no-ppf",
        dest="ppf",
        action="store_false",
        help="no PPF download and no PPF section in the notes (boku.release says why)",
    )
    release.set_defaults(
        run=lambda args: main_release(
            REPO_ROOT, args.base, args.build, args.out, args.preflight, args.ppf
        )
    )

    release_row = subcommands.add_parser(
        "release-row",
        help="write a tagged release's two SHA-1s into README.md's table of versions",
        description=(
            f"Write release/v<version>/'s row -- the SHA-1 of the dump it patches and of the "
            f"image it makes, read from the zip it posts -- into README.md's table "
            f"'{VERSIONS_HEADING}', replacing a row for that version that disagrees. Commit "
            f"and push README.md before publish-release --yes, which refuses a release the "
            f"README on GitHub's default branch does not list."
        ),
    )
    release_row.add_argument("release_dir", type=Path, metavar="DIR", help="release/v<version>")
    release_row.set_defaults(run=lambda args: main_release_row(args.release_dir, REPO_ROOT))

    publish = subcommands.add_parser(
        "publish-release",
        help="post a release/v<version>/ directory as a GitHub Release with gh",
        description=(
            "PLAN REL-04: print the gh release create line that posts the directory's zips "
            "with its RELEASE-NOTES.md, under its version tag (which must already be pushed); "
            "run it only with --yes. A snapshot, a moved tag, a changed file, or a release "
            "the README.md on GitHub's default branch does not list (release-row) is refused."
        ),
    )
    publish.add_argument(
        "--withdraw-ppf",
        action="store_true",
        help=(
            "instead take the PPF off the posted release: DIR is that tag cut again with "
            "release --no-ppf (boku.release says how)"
        ),
    )
    publish.add_argument("release_dir", type=Path, metavar="DIR", help="release/v<version>")
    publish.add_argument("--yes", action="store_true", help="post it; without this, a dry run")
    publish.add_argument("--draft", action="store_true", help="post it as a draft release")
    publish.add_argument("--prerelease", action="store_true", help="mark it a prerelease")
    publish.add_argument(
        "--repo",
        metavar="OWNER/REPO",
        help="the GitHub repository (default: from the origin remote)",
    )
    publish.set_defaults(
        run=lambda args: main_publish(
            args.release_dir,
            yes=args.yes,
            draft=args.draft,
            prerelease=args.prerelease,
            github=args.repo,
            git_repo=REPO_ROOT,
            withdraw_ppf=args.withdraw_ppf,
        )
    )

    textures = subcommands.add_parser(
        "textures",
        help="export the disc's textures as PNGs, or turn edited PNGs into patches",
        description=(
            "One indexed PNG per distinct image, its palette the texture's own CLUT, so "
            "an edit that keeps to that palette re-imports without a colour decision. "
            "Import reports the binary patches an edit implies at every place the image "
            "is stored -- one minimap is stored 287 times."
        ),
    )
    texture_verbs = textures.add_subparsers(
        dest="textures_command", required=True, metavar="COMMAND"
    )

    export = texture_verbs.add_parser(
        "export",
        help="write one PNG per distinct texture, plus an index of every occurrence",
    )
    export.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        metavar="DIR",
        help=f"the import to read (default: {DEFAULT_DISC_DIR}/)",
    )
    export.add_argument(
        "--out",
        type=Path,
        default=TEXTURES_OUT_DIR,
        metavar="DIR",
        help=f"directory to write (default: {TEXTURES_OUT_DIR}/); replaced on success",
    )
    export.add_argument(
        "--only-text",
        action="store_true",
        help="just the images research/data/texture-census.tsv marks yes or maybe for text",
    )
    export.add_argument(
        "--clut",
        type=palette_number,
        default=0,
        metavar="N",
        help=(
            "which palette to render with, for the 488 images that carry several "
            "(default: 0); the pixels are the same either way, the colours are not"
        ),
    )
    export.set_defaults(
        run=lambda args: main_textures_export(args.disc, args.out, args.only_text, args.clut)
    )

    texture_check = texture_verbs.add_parser(
        "check",
        help="build the English textures and report what each recipe made or refused",
        description=(
            "Every string in DIR (translation/textures/ by default) is typeset into its "
            "texture from your import, as `boku build --textures` does, and nothing is "
            "written to an image. A string that does not fit, or a character the glyph sheet "
            "cannot draw, is refused with its file and line. --out writes each rebuilt "
            "image as a PNG to look at (the game's own pixels: keep it under work/)."
        ),
    )
    texture_check.add_argument(
        "dir", type=Path, nargs="?", default=TEXTURE_TEXT_DIR, metavar="DIR",
        help="a directory of texture strings (default: translation/textures/)",
    )  # fmt: skip
    texture_check.add_argument(
        "--disc", type=Path, default=DEFAULT_DISC_DIR, metavar="DIR",
        help=f"the import to read (default: {DEFAULT_DISC_DIR}/)",
    )  # fmt: skip
    texture_check.add_argument(
        "--out", type=Path, default=None, metavar="DIR",
        help="write each rebuilt image here, e.g. work/textures-en",
    )  # fmt: skip
    texture_check.set_defaults(run=lambda args: main_texture_check(args.disc, args.dir, args.out))
    texture_import = texture_verbs.add_parser(
        "import",
        help="read edited PNGs and report the patches they imply at every occurrence",
        description=(
            "Each <id>.png in DIR is read as an edit of the texture that id names, using "
            f"{TEXTURES_INDEX_NAME} for the palette it was exported through. Nothing is "
            "written: the patches are handed to the image build."
        ),
    )
    texture_import.add_argument("dir", type=Path, metavar="DIR", help="a directory of edited PNGs")
    texture_import.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        metavar="DIR",
        help=f"the import to read (default: {DEFAULT_DISC_DIR}/)",
    )
    texture_import.add_argument(
        "--nearest",
        action="store_true",
        help=(
            "map a colour the CLUT does not hold onto its nearest entry and report the "
            "error, instead of refusing the edit"
        ),
    )
    texture_import.set_defaults(
        run=lambda args: main_textures_import(args.disc, args.dir, args.nearest)
    )

    add_packet_arguments(
        subcommands.add_parser(
            "packet",
            help=(
                "assemble the local translator packet for a day, a day file, events, the "
                "arrays or the whole game"
            ),
            description=(
                "PLAN TRN-08: a directory per unit -- system.md (the day-file format, then "
                "the story bible, the style guide, the glossary and the checklist, each "
                "whole), one <EVENT>.md per event or surface holding its lines in the "
                "day-file shape with the Japanese where the English goes, and order.txt, "
                "one row per part in the order to give them: its key, a tab, and the "
                "translation file its answer is saved into. A packet is the game's own "
                "text, so it is written under the gitignored work/ and is never tracked."
            ),
        )
    )

    add_save_event_arguments(
        subcommands.add_parser(
            "save-event",
            help="write a translator's answer for one event into its day file",
            description=(
                "PLAN TRN-08: the parent's half of a directed translation. The answer is "
                "the event's block from its packet with the Japanese replaced; it replaces "
                "that event's block in the day file, or goes in at its place in play order. "
                "Refused, with the file untouched, when an id is missing, extra or doubled, "
                "a row still holds Japanese, or a speaker is not a style-guide label. Run "
                "`./make.sh lint-translation` after."
            ),
        )
    )

    add_lint_arguments(
        subcommands.add_parser(
            "lint",
            help="check the committed translation files against the script store",
            description=(
                "PLAN PIPE-06: every id exists and is translated once, select options map "
                "1:1, a voiced message keeps its page count, every character has a cell, "
                "every page fits its box in pixels, an array item fits its site, and the "
                "pilot's additive-word heuristic warns. Nothing is rewritten and nothing is "
                "shortened to fit: a finding reports what is over and by how much. Exits "
                "non-zero when there is an error, zero on warnings alone."
            ),
        )
    )

    add_movies_arguments(
        subcommands.add_parser(
            "movies",
            help="decode every movie on your import into something VLC plays",
            description=(
                "Slice each __STR/*.IKI off the raw image and decode it with "
                "jPSXdec into work/movies/<name>.avi, the XA narration muxed in, then "
                "regenerate research/data/movies.tsv -- the list of what every MOVIE id "
                "plays, which is filled in from watching them. An .IKI is real-time "
                "interleaved, so `boku import` does not extract it and ffmpeg cannot "
                "decode its video (research/movies.md section 4)."
            ),
        )
    )

    add_voice_arguments(
        subcommands.add_parser(
            "voice-only",
            help="list the voice-only clips and decode them, and the voiced movies, to listen to",
            description=(
                "PLAN VO-01 / FMV-02: regenerate research/data/voice-only.tsv (one row per XA "
                "instruction -- a voice played with no text), decode every clip from "
                "__STR/BOKU_XA.XAM and every voiced movie's XA audio to WAV under work/voice/, "
                "and with --transcribe run whisper-cli (Japanese) over them. The audio and the "
                "transcripts are the game's own content, so they stay under work/."
            ),
        )
    )

    add_reader_arguments(
        subcommands.add_parser(
            "reader",
            help="one page that walks every translated thing in order, for reading it",
            description=(
                "PLAN TRN-14: the whole translation as one page under the gitignored work/ "
                "(boku.reader says what it shows)."
            ),
        )
    )

    add_coverage_arguments(
        subcommands.add_parser(
            "coverage",
            help="per day, which lines the player meets are English and why the rest are not",
            description=(
                "For every line an in-game day can reach: translated (English exists and "
                "the build wrote it), refused (English exists and the image did not get "
                "it -- the manifest says why), missing (nobody was asked for it), or "
                "not-event (a menu, book or title-screen line arrays.txt has no English for). The "
                "day files answer 'is what we wrote correct?'; this answers 'that line "
                "was still in Japanese -- why?'"
            ),
        )
    )

    add_save_arguments(
        subcommands.add_parser(
            "save",
            help="write a memory-card save generated from parameters, or the whole corpus",
            description=(
                "PLAN ENV-06: build a raw 128 KB card (.mcd) holding one save of this game, "
                "from a base state (a card or a main-RAM dump) with the day, the stars and "
                "any flag or saved byte changed, summed so the game accepts it. The layout, "
                "the saved regions, the title and the icon are read from your import "
                "(research/save-format.md)."
            ),
        )
    )

    add_mode_one_arguments(
        subcommands.add_parser(
            "export-to-mode-one",
            help="pack the built image as Mode One's boku.chd and pin its SHA-1 there",
            description=(
                "PLAN REL-02: chdman-pack build/days/image.cue into the retro-trainer "
                "checkout's one/roms/boku.chd and write that file's SHA-1 to its "
                "one/index/boku.sha1, the checksum Mode One's index pins (boku.mode_one)."
            ),
        )
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)
