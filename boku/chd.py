"""A raw disc image to and from a `.chd`, with MAME's `chdman`.

`chdman createcd` is deterministic for a given chdman: the same 659 MB image packed twice
gave byte-identical CHDs (chdman 0.283, 2026-09-25).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

CHDMAN = "chdman"


class ChdError(Exception):
    """chdman is missing or failed; whatever was at the destination is untouched."""


def _chdman(command: str, source: Path, *outputs: str) -> None:
    arguments = [CHDMAN, command, "-f", "-i", str(source), *outputs]
    try:
        subprocess.run(arguments, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise ChdError(f"{CHDMAN} is not on PATH; `brew install rom-tools` has it") from error
    except subprocess.CalledProcessError as error:
        said = error.stderr.strip() or error.stdout.strip()
        raise ChdError(f"{CHDMAN} {command} failed on {source}:\n{said}") from error


def create_cd(cue: Path, chd: Path) -> Path:
    """Pack the disc `cue` describes into `chd`. Returns `chd`.

    chdman writes beside `chd` and the result is renamed into place, so a pack that dies
    half way leaves the previous file -- or none -- rather than half a disc."""
    partial = chd.with_name(f".{chd.stem}.partial.chd")
    try:
        _chdman("createcd", cue, "-o", str(partial))
        partial.replace(chd)
    finally:
        partial.unlink(missing_ok=True)
    return chd


def extract_cd(chd: Path, image: Path) -> Path:
    """Unpack `chd`'s one track as the raw image `image`. Returns `image`."""
    cue = image.with_name(f".{image.name}.cue")  # chdman insists on writing one
    try:
        _chdman("extractcd", chd, "-o", str(cue), "-ob", str(image))
    finally:
        cue.unlink(missing_ok=True)
    if not image.is_file():
        raise ChdError(f"{CHDMAN} reported success but wrote no image at {image}")
    return image
