"""`boku` -- the project's command line. One subcommand per pipeline step.

Run it through `make.sh`, which is where the documented command lines live
(CLAUDE.md § "Tooling is Python, run through uv").
"""

from __future__ import annotations

import argparse
from pathlib import Path

from boku.archive import DEFAULT_DISC_DIR
from boku.build import DEFAULT_BUILD_NAME, DEFAULT_IMAGE, IMAGE_NAME, main_build
from boku.extract import SCRIPT_DIR_NAME, main_extract
from boku.importer import DEFAULT_OUT_DIR, SOURCE_ENV_VAR, main_import
from boku.lint import add_arguments as add_lint_arguments
from boku.packets import add_arguments as add_packet_arguments
from boku.patchfile import DEFAULT_OUT_DIR as PATCH_OUT_DIR
from boku.patchfile import MANIFEST_NAME, main_apply_patch, main_patch
from boku.textures import DEFAULT_OUT_DIR as TEXTURES_OUT_DIR
from boku.textures import INDEX_NAME as TEXTURES_INDEX_NAME
from boku.textures import main_export as main_textures_export
from boku.textures import main_import as main_textures_import
from boku.trial import DEFAULT_OUT_DIR as TRIAL_OUT_DIR
from boku.trial import TRIAL_TEXT, main_trial, patch_words

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
            "patches are written. The committed format is PLAN PIPE-02 and is not settled "
            "-- the reader here is the provisional one for translation/samples/"
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
        "--no-label",
        action="store_true",
        help=(
            "wrap page 1's first line to the full box instead of reserving the speaker "
            "label's pixels in front of it (the lint's --no-label, for the same reason)"
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
        )
    )

    patch = subcommands.add_parser(
        "patch",
        help="emit the release patches from an original and a built image",
        description=(
            "Write an xdelta (canonical) and a PPF (Mode One and DuckStation) turning "
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
            help="assemble a local translator packet per scene for a day or an event list",
            description=(
                "PLAN TRN-02: one Markdown file per scene holding everything a translator "
                "agent needs -- the scene as the game plays it, every line with its Japanese "
                "and its capacity, the day's bible entry, the glossary rows whose term "
                "occurs in the scene, the settled style rulings, and the neighbouring "
                "scenes' English. A packet is the game's own text, so it is written under "
                "the gitignored work/ and is never tracked."
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)
