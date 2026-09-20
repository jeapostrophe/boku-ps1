"""Checks that need the real dump. They skip cleanly where there is none (see conftest).

Nothing here hard-codes the disc's contents: each check crosses one place on the disc
against another, or against the one constant the project pins.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from boku.disc import FORM1_DATA_SIZE, RAW_SECTOR_SIZE, USER_DATA_OFFSET, DiscImage
from boku.importer import IMAGE_SHA1, verify_image


@pytest.fixture(scope="session")
def image(real_image: Path):
    with DiscImage(real_image) as opened:
        yield opened


def naive_sha1(path: Path, lba: int, size: int) -> str:
    """The dumbest possible Form 1 reader: seek, skip 24 bytes, take 2048, repeat.

    Independent of `boku.disc` on purpose -- it shares no code with the reader it checks,
    so the two agreeing is evidence, not a tautology.
    """
    digest = hashlib.sha1()
    remaining = size
    with path.open("rb") as handle:
        sector = lba
        while remaining > 0:
            handle.seek(sector * RAW_SECTOR_SIZE + USER_DATA_OFFSET)
            block = handle.read(min(FORM1_DATA_SIZE, remaining))
            if not block:
                raise AssertionError(f"image ends inside the file at sector {sector}")
            digest.update(block)
            remaining -= len(block)
            sector += 1
    return digest.hexdigest()


def test_the_pinned_sha1_is_this_dump(real_image: Path):
    """The constant the import step refuses everything else against."""
    assert verify_image(real_image) == IMAGE_SHA1


def test_the_reader_agrees_with_a_naive_sector_reader_on_the_largest_file(
    image: DiscImage, real_image: Path
):
    """104 MiB read two ways: chunked and validated, versus seek-and-slice."""
    entry = next(e for e in image.walk() if e.path == "/BOKU.BIN")
    assert entry.size > 100_000_000, "BOKU.BIN is not the size this test expects to exercise"
    assert image.sha1_file(entry.lba, entry.size) == naive_sha1(real_image, entry.lba, entry.size)


def test_a_declared_form_always_matches_the_sectors_and_only_interleaved_files_omit_it(
    image: DiscImage,
):
    """The XA attributes in the directory record versus the submode bit in the sectors.

    Two independently written places on the disc. Where the record declares a form, the
    sectors must agree -- that is what the import step's extract/record-only decision
    rests on. Where it declares none (attributes `0x2555` on this disc), the file must be
    the interleaved kind, which is the other half of the same decision: an `.IKI` file's
    first sector is Form 1 video, so without this the importer would cook one.
    """
    entries = [entry for entry in image.walk() if entry.size > 0]
    assert entries
    for entry in entries:
        assert entry.xa is not None, f"{entry.path} has no XA extension"
        first = image.read_sector(entry.lba)
        if entry.xa.form is None:
            assert entry.xa.interleaved, f"{entry.path} declares no form and is not interleaved"
        else:
            assert entry.xa.form == first.form, f"{entry.path}: record says form {entry.xa.form}"


def test_every_cookable_file_reads_the_same_bytes_as_a_naive_reader(
    image: DiscImage, real_image: Path
):
    """And the cookable files are exactly the ones outside `__STR` -- two facts, one disc.

    The comparison is against `naive_sha1`, not against the recorded size: `iter_file`
    yields exactly `size` bytes by construction, so a length assertion here could only
    ever fail by raising, which is not what it would look like it was checking.
    """
    files = [entry for entry in image.walk() if not entry.is_dir]
    cookable = [
        entry
        for entry in files
        if entry.xa is not None and entry.xa.form == 1 and not entry.xa.interleaved
    ]
    at_the_root = [entry for entry in files if "/" not in entry.path.lstrip("/")]
    assert at_the_root, "the disc has no files at its root"
    assert cookable == at_the_root
    for entry in cookable:
        expected = naive_sha1(real_image, entry.lba, entry.size)
        assert image.sha1_file(entry.lba, entry.size) == expected, entry.path


def test_system_cnf_boots_a_file_that_is_on_the_disc(image: DiscImage):
    """SYSTEM.CNF names the executable; the filesystem must contain exactly that name."""
    entries = {entry.path: entry for entry in image.walk()}
    config = entries["/SYSTEM.CNF"]
    text = image.read_file(config.lba, config.size).decode("ascii", errors="replace")
    match = re.search(r"BOOT\s*=\s*cdrom:?\\?([A-Z0-9_.]+);?\d*", text, re.IGNORECASE)
    assert match, f"no BOOT line in SYSTEM.CNF: {text!r}"
    booted = match.group(1)
    assert f"/{booted}" in entries, f"SYSTEM.CNF boots {booted}, which is not on the disc"
    assert entries[f"/{booted}"].size > 0


def test_the_volume_descriptor_fits_inside_the_image(image: DiscImage):
    pvd = image.primary_volume_descriptor()
    assert pvd.logical_block_size == FORM1_DATA_SIZE
    assert 0 < pvd.volume_space_size <= image.sector_count
