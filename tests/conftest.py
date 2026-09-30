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
from tests.test_real_reinsert import read_back

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
def game(texture_inventory: Inventory):
    """The game's own glyphs, decoded from the import's sheet: the face the textures are set in."""
    from boku.typeset import FONT_SHEET_ID, GameFace

    return GameFace.from_sheet(texture_inventory.get(FONT_SHEET_ID).tim)


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
def texture_image(texture_edits, real_image: Path, disc_dir: Path, tmp_path_factory) -> Path:
    """The `.cue` of an image carrying only the texture edits, built once for every Beetle
    test of the textures; skips unless `BOKU_EMU_TESTS=1` and the core is set up."""
    from boku.build import build

    if os.environ.get("BOKU_EMU_TESTS") != "1":
        pytest.skip("set BOKU_EMU_TESTS=1: an image build and Beetle boots")
    for var in ("BOKU_LIBRETRO_CORE", "BOKU_LIBRETRO_SYSTEM"):
        if not os.environ.get(var):
            pytest.skip(f"{var} is not set (research/tooling-setup.md)")
    out = build(
        source=real_image, out_dir=tmp_path_factory.mktemp("texture-image"), disc_dir=disc_dir,
        binary_patches=texture_edits.edits, name="textures",
    )  # fmt: skip
    assert out.written is not None
    return out.written.image.with_suffix(".cue")


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


@pytest.fixture(scope="session")
def days_built() -> Archive:
    """The days build read back (`./make.sh build-days`): what the patched game holds."""
    image = REPO_ROOT / "build" / "days" / "image.img"
    if not image.is_file():
        pytest.skip("no build/days: run `./make.sh build-days` first")
    return read_back(image)[0]
