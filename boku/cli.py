"""`boku` -- the project's command line. One subcommand per pipeline step.

Run it through `make.sh`, which is where the documented command lines live
(CLAUDE.md § "Tooling is Python, run through uv").
"""

from __future__ import annotations

import argparse
from pathlib import Path

from boku.importer import DEFAULT_OUT_DIR, SOURCE_ENV_VAR, main_import


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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)
