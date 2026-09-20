"""`boku` -- the project's command line. One subcommand per pipeline step.

Run it through `make.sh`, which is where the documented command lines live
(CLAUDE.md § "Tooling is Python, run through uv").
"""

from __future__ import annotations

import argparse
from pathlib import Path

from boku.archive import DEFAULT_DISC_DIR
from boku.extract import SCRIPT_DIR_NAME, main_extract
from boku.importer import DEFAULT_OUT_DIR, SOURCE_ENV_VAR, main_import
from boku.patchfile import DEFAULT_OUT_DIR as PATCH_OUT_DIR
from boku.patchfile import MANIFEST_NAME, main_apply_patch, main_patch
from boku.trial import DEFAULT_IMAGE, IMAGE_NAME, TRIAL_TEXT, main_trial
from boku.trial import DEFAULT_OUT_DIR as TRIAL_OUT_DIR

DEFAULT_MODIFIED_IMAGE = TRIAL_OUT_DIR / IMAGE_NAME


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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)
