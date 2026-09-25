"""`PIPE-05`'s round-trip gate, on the real dump and the real trial build.

Everything here skips cleanly on a checkout with no `disc/` and no `build/trial/` -- the
repo ships neither. Three things are being asked:

1. **Round trip.** The patch we emit, applied to a copy of the original, reproduces the
   trial image byte for byte -- and the bytes it claims are exactly the sectors
   `boku trial` says it wrote, in both directions. A patch that reproduces the image
   while touching something else would pass a hash check and still be wrong.
2. **Not wrong together.** Our writer and our reader share a module and a mental model,
   so they could agree on a format nobody else speaks. Icarus/Paradox's own
   `applyppf3` -- built here from `reference/repos/ppf`, which is a different program by
   a different author from the spec's own authors -- applies our PPF and must get the
   same image. Likewise `xdelta3 -d` for the xdelta.
3. **What 0x9320 actually is.** The research note says the PPF blockcheck window is the
   ISO 9660 primary volume descriptor. That is checkable against the disc's geometry
   rather than against our own constant, and it is checked here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from boku.disc import RAW_SECTOR_SIZE, USER_DATA_OFFSET
from boku.importer import IMAGE_SHA1
from boku.patchfile import apply_patch, build_patches, hashes_of, patch_stem
from boku.ppf import (
    BLOCKCHECK_OFFSET_BIN,
    BLOCKCHECK_SIZE,
    HEADER_SIZE,
    apply_ppf,
    make_ppf,
    read_ppf,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TRIAL_DIR = REPO_ROOT / "build" / "trial"
PPF_DEV = REPO_ROOT / "reference" / "repos" / "ppf" / "ppfdev"
PPF_SOURCE = PPF_DEV / "applyppf_src" / "applyppf3_linux.c"
MAKEPPF_SOURCE = PPF_DEV / "makeppf_src" / "makeppf3_linux.c"
PVD_LBA = 16


@pytest.fixture(scope="session")
def trial_image() -> Path:
    image = TRIAL_DIR / "image.img"
    if not image.is_file():
        pytest.skip(
            "no build/trial/image.img: run `./make.sh trial --line 'M_H02001.BIN:c1:0:171.0' "
            '--text "Hello, Boku!"` first. The repo ships no built image.'
        )
    return image


@pytest.fixture(scope="session")
def trial_manifest() -> dict:
    manifest = TRIAL_DIR / "manifest.json"
    if not manifest.is_file():
        pytest.skip("no build/trial/manifest.json beside the trial image")
    return json.loads(manifest.read_text())


@pytest.fixture(scope="session")
def patch_bytes(real_image: Path, trial_image: Path) -> bytes:
    return make_ppf(real_image, trial_image, "boku-ps1 round-trip gate")


def test_the_trial_was_built_from_the_dump_we_are_patching(real_image: Path, trial_manifest: dict):
    """A guard on the gate itself: comparing the wrong two images would make every check
    below meaningless in the same direction."""
    assert hashes_of(real_image).sha1 == IMAGE_SHA1 == trial_manifest["source_sha1"]


def test_the_blockcheck_window_is_the_primary_volume_descriptor(real_image: Path):
    """`0x9320` is not a magic number: it is byte 8 of the user data of sector 16, which
    ISO 9660 puts the primary volume descriptor in. Derived from the disc's geometry
    here, so this says what the window *is* rather than repeating what we wrote down."""
    assert BLOCKCHECK_OFFSET_BIN == PVD_LBA * RAW_SECTOR_SIZE + USER_DATA_OFFSET + 8

    window = real_image.read_bytes()[
        BLOCKCHECK_OFFSET_BIN : BLOCKCHECK_OFFSET_BIN + BLOCKCHECK_SIZE
    ]
    with real_image.open("rb") as handle:
        handle.seek(PVD_LBA * RAW_SECTOR_SIZE + USER_DATA_OFFSET)
        user_data = handle.read(2048)
    # Byte 0 is the descriptor type and 1..6 the identifier and version; the window
    # starts after them, at the system identifier.
    assert user_data[:6] == b"\x01CD001"
    assert window == user_data[8 : 8 + BLOCKCHECK_SIZE]


def test_our_ppf_round_trips_to_the_trial_image(
    real_image: Path, trial_image: Path, patch_bytes, tmp_path
):
    produced = tmp_path / "produced.img"
    apply_ppf(real_image, patch_bytes, produced)

    assert hashes_of(produced).sha1 == hashes_of(trial_image).sha1
    assert hashes_of(real_image).sha1 == IMAGE_SHA1, "the dump must not have been written to"


def test_the_ppf_touches_exactly_the_sectors_the_trial_says_it_wrote(
    patch_bytes, trial_manifest: dict
):
    """Both directions. A patch that reproduces the image while also rewriting a sector
    nobody asked about would pass every hash check in this file."""
    patched_sectors = {
        offset // RAW_SECTOR_SIZE
        for start, length in read_ppf(patch_bytes).touched_ranges()
        for offset in range(start, start + length)
    }
    written_sectors = {entry["lba"] for entry in trial_manifest["sectors"]}

    assert patched_sectors == written_sectors


def test_the_ppf_stays_inside_the_user_data_of_those_sectors(patch_bytes):
    """Every byte the patch claims is either user data or the EDC/ECC that covers it --
    never the 16-byte sync and header, which `boku trial` does not rewrite."""
    for start, length in read_ppf(patch_bytes).touched_ranges():
        for offset in range(start, start + length):
            assert offset % RAW_SECTOR_SIZE >= USER_DATA_OFFSET


def _build_reference(source: Path, binary: Path) -> Path:
    """Compile one of Icarus/Paradox's tools, skipping where the source is not cloned.

    `-fno-stack-protector` is not decoration. Both tools do `char desc[50]; fread(...50);
    desc[50]=0;` -- a one-byte write past the array. On macOS the stack protector turns
    that into `abort()` when the function returns, which is *after* the patch loop but
    *before* `fclose`, so the buffered writes to the image are never flushed and you are
    left with a silently half-patched file and exit 134. Measured 2026-09-20: built with
    the default flags, `applyppf3` applied our patch and produced sha1 c7b438b2...; built
    with this flag, the same patch and the same image produce the right one. Anyone
    building these on a modern toolchain should know that.
    """
    if not source.is_file():
        pytest.skip(
            f"no {source.relative_to(REPO_ROOT)}: "
            "`git clone https://github.com/meunierd/ppf reference/repos/ppf` to run this"
        )
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("no cc on PATH to build the reference tools")
    subprocess.run(
        [compiler, "-O2", "-fno-stack-protector", "-D_LARGEFILE_SOURCE",
         "-D_FILE_OFFSET_BITS=64", "-o", str(binary), str(source)],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return binary


@pytest.fixture(scope="session")
def reference_applier(tmp_path_factory) -> Path:
    return _build_reference(PPF_SOURCE, tmp_path_factory.mktemp("applyppf3") / "applyppf3")


@pytest.fixture(scope="session")
def reference_maker(tmp_path_factory) -> Path:
    return _build_reference(MAKEPPF_SOURCE, tmp_path_factory.mktemp("makeppf3") / "makeppf3")


def test_the_reference_applier_gets_the_same_image(
    real_image: Path, trial_image: Path, patch_bytes, reference_applier: Path, tmp_path
):
    """The one check our reader and our writer cannot pass by being wrong together."""
    target = tmp_path / "by-reference.img"
    shutil.copyfile(real_image, target)
    patch = tmp_path / "gate.ppf"
    patch.write_bytes(patch_bytes)

    result = subprocess.run(
        [str(reference_applier), "a", str(target), str(patch)],
        capture_output=True,
        text=True,
        input="",
        timeout=600,
    )
    assert result.returncode == 0, result.stdout
    assert "successful" in result.stdout, result.stdout
    # It prompts and continues on a bad blockcheck, so a passing hash is the real check.
    assert "failed" not in result.stdout, result.stdout
    assert hashes_of(target).sha1 == hashes_of(trial_image).sha1


@pytest.fixture(scope="session")
def reference_patch(
    real_image: Path, trial_image: Path, reference_maker: Path, tmp_path_factory
) -> bytes:
    """The same patch, made by Icarus/Paradox's own `makeppf3`."""
    theirs = tmp_path_factory.mktemp("reference-ppf") / "reference.ppf"
    result = subprocess.run(
        [
            str(reference_maker),
            "c",
            "-d",
            "reference",
            str(real_image),
            str(trial_image),
            str(theirs),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout
    return theirs.read_bytes()


def test_our_writer_emits_the_same_record_stream_as_the_reference_writer(
    patch_bytes, reference_patch
):
    """Byte for byte after the header, and nothing here goes through our own reader.

    The two writers can diverge in principle and still both be right: the reference
    restarts its difference run at every 1 MiB read boundary while we carry a run across
    one, so a difference straddling a boundary would come out as two records there and
    one here. This trial's four sectors contain no such run, and no run over 255 bytes,
    so on this pair the streams are expected to be identical -- which makes it the
    strongest form the check can take, and it is taken.
    """
    header = HEADER_SIZE + BLOCKCHECK_SIZE
    assert patch_bytes[header:] == reference_patch[header:]
    assert patch_bytes[56:header] == reference_patch[56:header], "imagetype, flags and blockcheck"
    assert len(patch_bytes) == len(reference_patch)


def test_our_reader_applies_a_patch_we_did_not_write(
    real_image: Path, trial_image: Path, reference_patch, tmp_path
):
    """The other half of "not wrong together": our reader against foreign bytes, judged
    by the image it produces rather than by agreeing with our own writer."""
    produced = tmp_path / "from-reference-ppf.img"
    apply_ppf(real_image, reference_patch, produced)

    assert hashes_of(produced).sha1 == hashes_of(trial_image).sha1


ONE_PATCH = Path.home() / "Dev" / "retro-trainer" / "target" / "debug" / "examples" / "one-patch"


def test_the_first_consumers_applier_gets_the_same_image(
    real_image: Path, trial_image: Path, patch_bytes, tmp_path
):
    """retro-trainer's PPF applier is a third implementation again -- Rust, written from the
    format rather than from the C. (Mode One itself is handed the built image, not this
    patch: `PLAN REL-02`, `boku.mode_one`.)

    It runs only if retro-trainer has already been built: this never builds there, because
    `cargo` would write into that repo's `target/`. Skips otherwise.
    """
    if not ONE_PATCH.is_file():
        pytest.skip(f"no prebuilt {ONE_PATCH}; this test never builds retro-trainer itself")

    patch = tmp_path / "gate.ppf"
    patch.write_bytes(patch_bytes)
    produced = tmp_path / "by-retro-trainer.img"
    result = subprocess.run(
        [str(ONE_PATCH), str(real_image), str(patch), str(produced)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr

    assert hashes_of(produced).sha1 == hashes_of(trial_image).sha1


def test_build_patches_emits_a_release_that_applies_back(
    real_image: Path, trial_image: Path, tmp_path
):
    """The whole `boku patch` -> `boku apply-patch` path, both formats, on the real pair."""
    out = tmp_path / "patch"
    release = build_patches(real_image, trial_image, out, version="0.0.0-gate")

    assert release.original.sha1 == IMAGE_SHA1
    assert release.result.sha1 == hashes_of(trial_image).sha1

    for patch in (release.xdelta_path, release.ppf_path):
        produced = tmp_path / f"from{patch.suffix}.img"
        apply_patch(real_image, patch, produced)
        assert hashes_of(produced).sha1 == release.result.sha1
        produced.unlink()

    assert patch_stem("0.0.0-gate") in release.xdelta_path.name


def test_the_xdelta_round_trips_through_the_stock_decoder(
    real_image: Path, trial_image: Path, tmp_path
):
    out = tmp_path / "patch"
    release = build_patches(real_image, trial_image, out, version="0.0.0-gate")

    produced = tmp_path / "by-xdelta3.img"
    subprocess.run(
        ["xdelta3", "-f", "-d", "-s", str(real_image), str(release.xdelta_path), str(produced)],
        check=True,
        capture_output=True,
        timeout=600,
    )
    assert hashes_of(produced).sha1 == hashes_of(trial_image).sha1
