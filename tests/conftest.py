"""Shared fixtures.

Nothing here brings disc content into the repo: the tests that need the real dump find
it through the environment or the project's own gitignored `disc/`, and skip with a
reason when it is not there -- a contributor's checkout has no disc.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.archive import ARCHIVE_NAME, EXE_NAME, Archive
from boku.events import EventWorld
from boku.importer import IMAGE_SIZE, SOURCE_ENV_VAR
from boku.sites import Walk, walk
from boku.text import SiteIndex
from boku.textures import Inventory, inventory

DISC_DIR = REPO_ROOT / "disc"


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


@pytest.fixture(scope="session")
def disc_dir() -> Path:
    """The import the walkers read: `disc/files/` as `boku import` wrote it."""
    files = DISC_DIR / "files"
    for name in (EXE_NAME, ARCHIVE_NAME):
        if not (files / name).is_file():
            pytest.skip(
                f"no {name} in {files}: run `./make.sh import` first. The repo ships "
                f"none of the game."
            )
    return DISC_DIR


@pytest.fixture(scope="session")
def archive(disc_dir: Path) -> Archive:
    """One `Archive` for the whole session; it holds 109 MB and is read-only."""
    return Archive(disc_dir)


@pytest.fixture(scope="session")
def texture_inventory(archive: Archive) -> Inventory:
    """Every distinct TIM on the import, scanned once for the session."""
    return inventory(archive)


@pytest.fixture(scope="session")
def texture_edits(archive: Archive, texture_inventory: Inventory):
    """Every edit the tracked texture English implies (`boku.texture_text.build_edits`)."""
    from boku.texture_text import build_edits

    return build_edits(archive, inv=texture_inventory)


@pytest.fixture(scope="session")
def texture_patched(archive: Archive, texture_edits) -> bytes:
    """`BOKU.BIN` with those edits applied, in memory."""
    from boku.texture_text import patched_archive

    return patched_archive(archive, texture_edits.edits)


@pytest.fixture(scope="session")
def site_index(disc_dir: Path, archive: Archive) -> SiteIndex:
    """The walk, over the archive that is already open -- not a second copy of it."""
    return SiteIndex.from_disc(disc_dir, archive=archive)


# The three decodings of the whole disc, each done once for the session. Between them
# they used to be repeated nine times across `test_real_extract.py` alone, and each one
# is seconds of work over 109 MB. They are read-only for the same reason `archive` is.


@pytest.fixture(scope="session")
def walk_reader(archive: Archive) -> Walk:
    """The `REC-06` partition: one string per item as its reader indexes it."""
    return walk(archive, array_partition="reader")


@pytest.fixture(scope="session")
def walk_rec03(archive: Archive) -> Walk:
    """The earlier partition, which `research/data/text-sites.tsv` is written from."""
    return walk(archive, array_partition="rec03")


@pytest.fixture(scope="session")
def event_world(archive: Archive) -> EventWorld:
    return EventWorld(archive)
