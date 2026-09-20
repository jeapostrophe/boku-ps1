"""Shared fixtures.

Nothing here brings disc content into the repo: the tests that need the real dump find
it through the environment or the project's own gitignored `disc/`, and skip with a
reason when it is not there -- a contributor's checkout has no disc.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from boku.importer import IMAGE_SIZE, SOURCE_ENV_VAR

REPO_ROOT = Path(__file__).resolve().parent.parent


def find_real_image() -> Path | None:
    """The raw image, if this machine has one: `$BOKU_DISC` if it is one, else `disc/image.img`.

    A `.chd` in `$BOKU_DISC` is not one -- it fails the size check and the tests skip,
    telling the contributor to run the import, which is what puts `disc/image.img` there.
    """
    candidates = [
        os.environ.get(SOURCE_ENV_VAR),
        REPO_ROOT / "disc" / "image.img",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file() and path.stat().st_size == IMAGE_SIZE:
            return path
    return None


@pytest.fixture(scope="session")
def real_image() -> Path:
    image = find_real_image()
    if image is None:
        pytest.skip(
            f"no raw image of SCPS-10088 on this machine: run `./make.sh import` to write "
            f"disc/image.img, or point ${SOURCE_ENV_VAR} at a raw image. The repo ships "
            f"none of the game."
        )
    return image
