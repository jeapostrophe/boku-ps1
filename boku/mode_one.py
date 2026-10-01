"""`PLAN REL-02`: hand Mode One the built English image and the checksum it pins.

Mode One (`~/Dev/retro-trainer`, the phone frontend Jay plays on) does not apply our patch
(Jay, 2026-09-25). It loads a PS1 disc as a `.chd` and accepts one only if the file's own
SHA-1 is pinned in its compiled-in index, so `./make.sh export-to-mode-one`:

1. packs `build/days/image.cue` -- what `./make.sh build-days` wrote -- with
   `chdman createcd` into Mode One's host staging folder, `one/roms/boku.chd` (the folder
   its `./one/make.sh push-roms` copies onto the phone, filenames `<index id>.<ext>`);
2. writes that file's SHA-1 to `one/index/boku.sha1`, the one-line file Mode One's index
   entry for Boku (`boku()` in `src/one/index.rs`) includes at compile time.

The pin is the `.chd` file's own SHA-1 (what Mode One's `RomLibrary` hashes), so it is
taken after packing (`boku.chd`, which also says the pack is deterministic).

The pin moves only once the disc it names is in place, and a failed pack leaves the
previous disc and pin untouched, so Mode One is never pinned to a file it does not have.
Every export re-pins, and the app must be rebuilt to accept the new pin.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from boku.build import CUE_NAME
from boku.chd import ChdError, create_cd
from boku.importer import sha1_of
from boku.reader import BUILD_ID_NAME, DEFAULT_BUILD_DIR, build_id

MODE_ONE_ENV = "BOKU_MODE_ONE"
# Where this project already says Mode One lives (CLAUDE.md, research/tooling-setup.md).
DEFAULT_MODE_ONE = Path.home() / "Dev" / "retro-trainer"
# Both paths are Mode One's own: the folder `one/make.sh` stages ROMs in (`ROMS_DIR`), named
# `<id>.<ext>` after the index id `boku`, and the pin its index includes.
ROM_FILE = Path("one/roms/boku.chd")
PIN_FILE = Path("one/index/boku.sha1")


class ModeOneError(Exception):
    """An export we refuse, having written nothing into Mode One."""


@dataclass(frozen=True)
class Exported:
    chd: Path
    sha1: str
    build_id: str


def export_to_mode_one(build: Path, mode_one: Path) -> Exported:
    """Pack `build`'s image into `mode_one`'s ROM folder and pin its SHA-1 there."""
    pin = mode_one / PIN_FILE
    if not pin.is_file():
        raise ModeOneError(
            f"{mode_one} is not a Mode One checkout with a Boku entry: there is no {PIN_FILE}. "
            f"Point --mode-one (or ${MODE_ONE_ENV}) at retro-trainer."
        )
    cue = build / CUE_NAME
    if not cue.is_file():
        raise ModeOneError(f"no image at {cue}: run ./make.sh build-days first")

    chd = mode_one / ROM_FILE
    chd.parent.mkdir(parents=True, exist_ok=True)
    try:
        create_cd(cue, chd)
    except ChdError as error:
        raise ModeOneError(str(error)) from error
    sha1 = sha1_of(chd)

    staged = pin.with_name(f".{pin.name}.partial")
    staged.write_text(f"{sha1}\n")
    staged.replace(pin)

    return Exported(chd=chd, sha1=sha1, build_id=build_id(build))


def main_export(build: Path, mode_one: Path) -> int:
    try:
        result = export_to_mode_one(build, mode_one)
    except (ModeOneError, OSError) as error:
        print(f"boku export-to-mode-one: {error}")
        return 1
    print(
        f"build {result.build_id or f'(no {BUILD_ID_NAME})'}\n"
        f"wrote {result.chd}\n"
        f"  sha1 {result.sha1} -> {mode_one / PIN_FILE}\n"
        f"Mode One pins it at compile time. In {mode_one}:\n"
        f"  ./one/make.sh ios deploy   # rebuild the app with the new pin\n"
        f"  ./one/make.sh push-roms    # copy one/roms/ onto the phone\n"
        f"and commit {PIN_FILE} there if this is the build to keep. A playthrough saved on\n"
        f"another build boots this one fresh: load the memory card."
    )
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--build", type=Path, default=DEFAULT_BUILD_DIR, metavar="DIR",
        help=f"the build whose image.cue is exported (default: {DEFAULT_BUILD_DIR})",
    )  # fmt: skip
    parser.add_argument(
        "--mode-one", type=Path, metavar="DIR",
        default=Path(os.environ.get(MODE_ONE_ENV, DEFAULT_MODE_ONE)),
        help=f"the retro-trainer checkout (default: ${MODE_ONE_ENV}, else {DEFAULT_MODE_ONE})",
    )  # fmt: skip
    parser.set_defaults(run=lambda args: main_export(args.build, args.mode_one))
    return parser
