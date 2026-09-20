"""`boku` -- the project's command line. One subcommand per pipeline step.

Run it through `make.sh`, which is where the documented command lines live
(CLAUDE.md § "Tooling is Python, run through uv").
"""

from __future__ import annotations

import argparse
from pathlib import Path

from boku.importer import DEFAULT_OUT_DIR, SOURCE_ENV_VAR, main_import
from boku.trial import DEFAULT_IMAGE, TRIAL_TEXT, main_trial
from boku.trial import DEFAULT_OUT_DIR as TRIAL_OUT_DIR


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
            "overwrite every physical copy of one line: a 12-hex-digit line_key from "
            "research/data/text-sites.tsv, or a site id such as E0112.0"
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)
