"""The emitted release: xdelta, hashes, `PATCH.json`, and our own applier.

Synthetic images throughout -- the real disc is `tests/test_real_patch.py`. The hash
helper is pinned against published vectors rather than against a second call to the same
standard library, so "our hex is the right hex" is checked against something outside this
repo.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import subprocess
import zlib

import pytest

from boku.patchfile import (
    MIN_SOURCE_WINDOW,
    PatchError,
    apply_patch,
    build_patches,
    hashes_of,
    make_xdelta,
    patch_stem,
    ppf_description,
    xdelta_app_header,
    xdelta_encode_command,
)
from boku.ppf import BLOCKCHECK_OFFSET_BIN, BLOCKCHECK_SIZE

needs_xdelta3 = pytest.mark.skipif(
    shutil.which("xdelta3") is None, reason="xdelta3 is not on PATH (brew install xdelta)"
)

IMAGE_SIZE = BLOCKCHECK_OFFSET_BIN + BLOCKCHECK_SIZE + 4096


@pytest.fixture
def pair(tmp_path):
    """An original and a modified image of equal length, differing in two places."""
    original = random.Random(7).randbytes(IMAGE_SIZE)
    modified = bytearray(original)
    for offset, length in ((0x1200, 4), (0x9800, 300)):
        modified[offset : offset + length] = bytes(
            b ^ 0xFF for b in original[offset : offset + length]
        )
    first = tmp_path / "original.img"
    second = tmp_path / "modified.img"
    first.write_bytes(original)
    second.write_bytes(bytes(modified))
    return first, second


# ---------------------------------------------------------------------------
# Hashes


def test_hashes_match_published_vectors(tmp_path):
    """RFC 3174 and RFC 1321 both publish the digests of "abc"; CRC-32 of "abc" is a
    standard vector too. None of the three is recomputed here from our own code."""
    path = tmp_path / "abc"
    path.write_bytes(b"abc")
    hashes = hashes_of(path)

    assert hashes.size == 3
    assert hashes.sha1 == "a9993e364706816aba3e25717850c26c9cd0d89d"
    assert hashes.md5 == "900150983cd24fb0d6963f7d28e17f72"
    assert hashes.crc32 == "352441c2"


def test_crc32_keeps_its_leading_zero(tmp_path):
    """A CRC32 below 0x10000000 prints as seven digits unless it is padded, and a
    seven-digit CRC32 in a README is one a user cannot match against redump."""
    payload = next(
        bytes([a, b]) for a in range(256) for b in range(256) if zlib.crc32(bytes([a, b])) < 1 << 28
    )
    path = tmp_path / "short"
    path.write_bytes(payload)

    # The length IS the gate. Comparing against `f"{zlib.crc32(payload):08x}"` would
    # re-run the expression `hashes_of` itself runs, and could only fail if the wrong
    # bytes were read -- which `test_hashes_match_published_vectors` already pins.
    assert len(hashes_of(path).crc32) == 8


# ---------------------------------------------------------------------------
# xdelta


def test_encode_command_covers_a_source_bigger_than_the_64_mb_default(tmp_path):
    """The source here is sparse and disc-sized, because that is the only size at which
    the harm shows: xdelta3's default source window is 64 MB, and over a 659 MB image
    "no source copy will be found more than half a window away" silently inflates the
    patch. A 40 KB fixture is covered by the default and proves nothing -- measured, it
    left this test green with the window hard-coded to 64 MB.
    """
    disc_sized = tmp_path / "disc-sized.img"
    with disc_sized.open("wb") as handle:
        handle.truncate(658_959_840)

    command = xdelta_encode_command(disc_sized, disc_sized, tmp_path / "out.xdelta")
    window = int(command[command.index("-B") + 1])
    assert window >= disc_sized.stat().st_size

    assert command[command.index("-A") + 1] == ""
    assert command[command.index("-S") + 1] == "lzma"
    assert "-9" in command


def test_the_source_window_is_clamped_up_to_xdeltas_minimum(tmp_path):
    tiny = tmp_path / "tiny.bin"
    tiny.write_bytes(b"x" * 16)
    command = xdelta_encode_command(tiny, tiny, tmp_path / "out.xdelta")

    assert int(command[command.index("-B") + 1]) == MIN_SOURCE_WINDOW


@needs_xdelta3
def test_a_tiny_source_still_encodes(tmp_path):
    """xdelta3 3.2.0 refuses `-B` below 524288, so a source smaller than that has to be
    clamped up: "the window is the source size" is wrong at the bottom of the range."""
    original = tmp_path / "small.bin"
    modified = tmp_path / "small2.bin"
    original.write_bytes(b"a" * 1024)
    modified.write_bytes(b"b" + b"a" * 1023)

    make_xdelta(original, modified, tmp_path / "small.xdelta")


@needs_xdelta3
def test_the_application_header_is_empty_and_the_check_can_see_a_full_one(tmp_path, pair):
    """`-A ""` blanks the application header -- which is also where 3.2.0 keeps armor's
    BLAKE3 digests, so this is the armor decision as well as the no-paths decision.
    The armored patch is here to prove the check is capable of failing."""
    original, modified = pair
    ours = tmp_path / "ours.xdelta"
    make_xdelta(original, modified, ours)
    assert xdelta_app_header(ours.read_bytes()) == b""

    armored = tmp_path / "armored.xdelta"
    subprocess.run(
        [
            "xdelta3",
            "-f",
            "-e",
            "-9",
            "-S",
            "lzma",
            "-B",
            str(MIN_SOURCE_WINDOW),
            "-s",
            str(original),
            str(modified),
            str(armored),
        ],
        check=True,
        capture_output=True,
    )
    header = xdelta_app_header(armored.read_bytes())
    assert header != b""
    assert original.name.encode() in header


@needs_xdelta3
def test_xdelta_round_trips_through_the_stock_decoder(tmp_path, pair):
    original, modified = pair
    patch = tmp_path / "p.xdelta"
    make_xdelta(original, modified, patch)

    out = tmp_path / "decoded.img"
    subprocess.run(
        ["xdelta3", "-d", "-s", str(original), str(patch), str(out)],
        check=True,
        capture_output=True,
    )
    assert out.read_bytes() == modified.read_bytes()


# ---------------------------------------------------------------------------
# The release directory


@needs_xdelta3
def test_make_xdelta_decodes_its_own_patch_and_notices_a_bad_one(tmp_path, pair, monkeypatch):
    """`make_xdelta` proves the patch by decoding it back. Here the decoder is replaced by
    one that returns the wrong bytes, so the proof is shown to be capable of failing --
    otherwise "we verify" would only mean "we call something"."""
    import boku.patchfile as patchfile

    original, modified = pair
    shim = tmp_path / "fake-xdelta3"
    shim.write_text(
        "#!/bin/bash\n"  # `${@: -1}` is a bashism; dash would not parse it
        'for arg in "$@"; do [ "$arg" = "-d" ] && { : > "${@: -1}"; exit 0; }; done\n'
        'exec xdelta3 "$@"\n'
    )
    shim.chmod(0o755)
    monkeypatch.setattr(patchfile, "XDELTA3", str(shim))

    with pytest.raises(PatchError, match="does not reproduce"):
        make_xdelta(original, modified, tmp_path / "p.xdelta")


@needs_xdelta3
def test_two_builds_of_the_same_pair_are_byte_for_byte_identical(tmp_path, pair):
    """A release nobody can rebuild is a release nobody can check, so nothing we write
    may carry a clock or an absolute path.

    The second build reads *copies* in a differently-named directory, keeping the
    basenames identical. Building twice from the same paths -- which the first draft did
    -- leaves a leaked absolute source path invisible, because it would be the same
    string both times; only a clock would be caught. (A leaked pid is still invisible:
    both builds share this process. That one is left to review.)
    """
    original, modified = pair
    elsewhere = tmp_path / "a-different-directory-entirely"
    elsewhere.mkdir()
    for source in (original, modified):
        (elsewhere / source.name).write_bytes(source.read_bytes())

    first = tmp_path / "first"
    second = tmp_path / "second"
    build_patches(original, modified, first, version="9.9.9")
    build_patches(elsewhere / original.name, elsewhere / modified.name, second, version="9.9.9")

    for name in sorted(path.name for path in first.iterdir()):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_patch_stem_follows_the_scene_convention():
    assert patch_stem("0.1.0") == "Boku no Natsuyasumi (Japan) [T-En boku-ps1 v0.1.0]"


def test_the_ppf_fingerprint_fits_a_fifty_byte_description():
    description = ppf_description("0.1.0", "a" * 40, "b" * 40)
    assert len(description.encode("ascii")) <= 50


@needs_xdelta3
def test_build_writes_both_patches_and_a_manifest_naming_both_sides(tmp_path, pair):
    original, modified = pair
    out = tmp_path / "patch"
    result = build_patches(original, modified, out, version="9.9.9")

    stem = patch_stem("9.9.9")
    assert {path.name for path in out.iterdir()} == {
        f"{stem}.ppf",
        f"{stem}.xdelta",
        "PATCH.json",
        "README.txt",
    }

    manifest = json.loads((out / "PATCH.json").read_text())
    assert manifest["original"]["sha1"] == hashlib.sha1(original.read_bytes()).hexdigest()
    assert manifest["result"]["sha1"] == hashlib.sha1(modified.read_bytes()).hexdigest()
    assert manifest["original"]["size"] == original.stat().st_size
    assert manifest["result"]["size"] == modified.stat().st_size
    assert {entry["format"] for entry in manifest["patches"]} == {"ppf3", "xdelta3"}
    assert result.manifest_path == out / "PATCH.json"

    readme = (out / "README.txt").read_text()
    for side in (original, modified):
        digest = hashlib.sha1(side.read_bytes()).hexdigest()
        assert digest in readme, "a README that omits a side's SHA-1 cannot be checked against"
    # A player holding a patched image asks which version it is: the result block says so in
    # words, not only through the file name, which a player renames.
    should_get = readme.split("WHAT YOU SHOULD GET", 1)[1].split("THE PATCHES THEMSELVES", 1)[0]
    said = [
        line
        for line in should_get.splitlines()
        if manifest["tool"] in line and not line.strip().startswith("file")
    ]
    assert said, "the result block does not name the version its SHA-1 identifies"


@needs_xdelta3
@pytest.mark.parametrize("suffix", [".ppf", ".xdelta"])
def test_apply_patch_reproduces_the_result(tmp_path, pair, suffix):
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")
    patch = out / f"{patch_stem('9.9.9')}{suffix}"

    produced = tmp_path / "produced.img"
    apply_patch(original, patch, produced)
    assert produced.read_bytes() == modified.read_bytes()


@needs_xdelta3
@pytest.mark.parametrize("suffix", [".ppf", ".xdelta"])
def test_apply_patch_refuses_the_wrong_original_before_writing_anything(tmp_path, pair, suffix):
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")
    patch = out / f"{patch_stem('9.9.9')}{suffix}"

    wrong = tmp_path / "wrong.img"
    wrong.write_bytes(bytes(b ^ 0x01 for b in original.read_bytes()))
    produced = tmp_path / "produced.img"

    # Not `match="sha1"`. Measured: with our pre-check deleted, the .xdelta case stays
    # green two ways -- xdelta3 3.2.0 refuses the wrong source itself with "verify the
    # source file with sha1sum or equivalent" (which `re.search("sha1", ...)` matches),
    # and the failure path unlinks the temp file so `not produced.exists()` still holds.
    # The message has to name OUR check.
    with pytest.raises(PatchError, match=re.escape("is not the image this patch is for")):
        apply_patch(wrong, patch, produced)
    assert not produced.exists()


@needs_xdelta3
def test_apply_patch_checks_the_result_too(tmp_path, pair):
    """The manifest is the contract; if it has been edited so that the result no longer
    matches, the produced file is not what the release promised and must not be kept."""
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")

    manifest = json.loads((out / "PATCH.json").read_text())
    manifest["result"]["sha1"] = "0" * 40
    (out / "PATCH.json").write_text(json.dumps(manifest))

    produced = tmp_path / "produced.img"
    with pytest.raises(PatchError, match="result"):
        apply_patch(original, out / f"{patch_stem('9.9.9')}.xdelta", produced)
    assert not produced.exists()


@needs_xdelta3
def test_apply_patch_leaves_the_original_byte_for_byte(tmp_path, pair):
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")
    before = original.read_bytes()

    apply_patch(original, out / f"{patch_stem('9.9.9')}.ppf", tmp_path / "produced.img")
    assert original.read_bytes() == before


@needs_xdelta3
def test_a_lone_ppf_is_checked_against_the_fingerprint_in_its_description(tmp_path, pair):
    """A `.ppf` dropped beside a CHD travels without the manifest, so it carries an eight
    hex digit fingerprint of both sides in the 50-byte description an applier prints."""
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")
    lone = tmp_path / "lone.ppf"
    lone.write_bytes((out / f"{patch_stem('9.9.9')}.ppf").read_bytes())

    apply_patch(original, lone, tmp_path / "produced.img")
    assert (tmp_path / "produced.img").read_bytes() == modified.read_bytes()

    wrong = tmp_path / "wrong.img"
    wrong.write_bytes(bytes(b ^ 0x01 for b in original.read_bytes()))
    with pytest.raises(PatchError, match="sha1"):
        apply_patch(wrong, lone, tmp_path / "other.img")


@needs_xdelta3
def test_a_lone_xdelta_with_no_expectation_is_refused(tmp_path, pair):
    """An xdelta carries nothing of its own -- we blanked the header that armor would
    have used -- so without a manifest there is nothing to check and we do not guess."""
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")
    lone = tmp_path / "lone.xdelta"
    lone.write_bytes((out / f"{patch_stem('9.9.9')}.xdelta").read_bytes())

    with pytest.raises(PatchError, match=re.escape("PATCH.json")):
        apply_patch(original, lone, tmp_path / "produced.img")


@needs_xdelta3
def test_apply_patch_accepts_hashes_given_on_the_command_line(tmp_path, pair):
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")
    lone = tmp_path / "lone.xdelta"
    lone.write_bytes((out / f"{patch_stem('9.9.9')}.xdelta").read_bytes())

    produced = tmp_path / "produced.img"
    apply_patch(
        original,
        lone,
        produced,
        expect_original=hashlib.sha1(original.read_bytes()).hexdigest(),
        expect_result=hashlib.sha1(modified.read_bytes()).hexdigest(),
    )
    assert produced.read_bytes() == modified.read_bytes()


@needs_xdelta3
def test_no_apply_command_writes_over_the_dump_it_reads(tmp_path):
    """The two images this pipeline builds from are `disc/image.img` and
    `build/trial/image.img` -- same basename, different directory. Naming the result
    after the built image would print `xdelta3 -d -s image.img ... image.img`, which
    destroys the reader's own dump, and a README is followed literally."""
    payload = random.Random(11).randbytes(IMAGE_SIZE)
    patched = bytearray(payload)
    patched[0x2000:0x2004] = bytes(b ^ 0xFF for b in payload[0x2000:0x2004])
    for folder, content in (("disc", payload), ("built", bytes(patched))):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "image.img").write_bytes(content)

    out = tmp_path / "patch"
    build_patches(tmp_path / "disc" / "image.img", tmp_path / "built" / "image.img", out)

    manifest = json.loads((out / "PATCH.json").read_text())
    assert manifest["original"]["name"] != manifest["result"]["name"]
    for entry in manifest["patches"]:
        assert entry["apply"].count(manifest["original"]["name"]) == 1, entry["apply"]
    readme = (out / "README.txt").read_text()
    for line in readme.splitlines():
        if "-d -s" in line or "apply-patch" in line:
            assert manifest["result"]["name"] in line, line


@needs_xdelta3
@pytest.mark.parametrize("stated", [None, "", "not-hex-at-all", 12345, "5959BF7D"])
def test_a_manifest_that_does_not_state_a_usable_sha1_is_refused(tmp_path, pair, stated):
    """ "Nothing to check" and "checked and passed" must not look the same.

    JSON `null` and `""` both used to sail through the manifest guard and then through
    the comparison -- `None` meant "agrees" and `""` is a prefix of everything -- so a
    hand-edited or truncated manifest turned BOTH checks off and `apply_patch` accepted
    any image. A non-string raised `TypeError` out of the CLI's except clause. A short
    but valid hex string is refused too: a half-pasted hash must not silently weaken the
    check to however many characters were pasted.
    """
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")

    manifest = json.loads((out / "PATCH.json").read_text())
    manifest["original"]["sha1"] = stated
    (out / "PATCH.json").write_text(json.dumps(manifest))

    produced = tmp_path / "produced.img"

    # The message has to blame the MANIFEST. `_agrees` alone would already refuse an
    # unusable expectation -- nothing equals `None` -- but it would say "this is not the
    # image this patch is for", sending a contributor with a perfectly good dump off to
    # find another one. Matching only `PatchError` leaves this test green with the
    # validation deleted; measured.
    with pytest.raises(PatchError, match=r"not text|not 40 hex digits"):
        apply_patch(original, out / f"{patch_stem('9.9.9')}.xdelta", produced)
    assert not produced.exists()


@needs_xdelta3
def test_a_manifest_that_does_not_list_this_patch_is_not_used(tmp_path, pair):
    """A release folder keeps its PATCH.json. Drop a newer lone `.ppf` into an older one
    and the old manifest would otherwise be believed, refusing a perfectly good patch
    while blaming the patch rather than the stale manifest."""
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")

    stale = tmp_path / "old-release"
    stale.mkdir()
    manifest = json.loads((out / "PATCH.json").read_text())
    manifest["original"]["sha1"] = "0" * 40
    manifest["result"]["sha1"] = "1" * 40
    manifest["patches"] = [
        dict(entry, file="some other release.xdelta") for entry in manifest["patches"]
    ]
    (stale / "PATCH.json").write_text(json.dumps(manifest))
    lone = stale / "lone.ppf"
    lone.write_bytes((out / f"{patch_stem('9.9.9')}.ppf").read_bytes())

    # The PPF's own fingerprint is used instead, so the patch applies.
    produced = tmp_path / "produced.img"
    apply_patch(original, lone, produced)
    assert produced.read_bytes() == modified.read_bytes()


@needs_xdelta3
def test_apply_patch_accepts_an_uppercase_hash_the_way_redump_prints_it(tmp_path, pair):
    """Redump publishes uppercase and a contributor pastes what they are shown; a correct
    dump refused over letter case is a support ticket and a bad first impression."""
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")
    lone = tmp_path / "lone.xdelta"
    lone.write_bytes((out / f"{patch_stem('9.9.9')}.xdelta").read_bytes())

    produced = tmp_path / "produced.img"
    apply_patch(
        original,
        lone,
        produced,
        expect_original=hashlib.sha1(original.read_bytes()).hexdigest().upper(),
        expect_result=hashlib.sha1(modified.read_bytes()).hexdigest().upper(),
    )
    assert produced.read_bytes() == modified.read_bytes()


@needs_xdelta3
@pytest.mark.parametrize("suffix", [".ppf", ".xdelta"])
def test_apply_patch_refuses_to_write_over_the_dump(tmp_path, pair, suffix):
    """`--out` naming the dump destroys it on the SUCCESS path: every check passes and
    the finished image is renamed over the contributor's only copy of the original."""
    original, modified = pair
    out = tmp_path / "patch"
    build_patches(original, modified, out, version="9.9.9")
    before = original.read_bytes()

    with pytest.raises(PatchError, match="destroy"):
        apply_patch(original, out / f"{patch_stem('9.9.9')}{suffix}", original)
    assert original.read_bytes() == before


def test_an_unreadable_vcdiff_header_is_not_called_empty(tmp_path):
    """`xdelta_app_header`'s answer decides that a patch leaks no filenames, so a header
    we cannot fully parse must not come back as "empty"."""
    reserved = bytes([0xD6, 0xC3, 0xC4, 0x00, 0x08])
    with pytest.raises(PatchError, match="unknown header bits"):
        xdelta_app_header(reserved)


def test_build_refuses_an_output_directory_that_is_not_ours(tmp_path, pair):
    original, modified = pair
    out = tmp_path / "somebody-elses"
    out.mkdir()
    (out / "holiday-photos.jpg").write_bytes(b"not ours")

    with pytest.raises(PatchError):
        build_patches(original, modified, out, version="9.9.9")
    assert (out / "holiday-photos.jpg").exists()
