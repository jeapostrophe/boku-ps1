r"""`PIPE-05`: turn two images into a release, and apply one back without trusting it.

What goes out
-------------
`boku patch` writes four files into `build/patch/`:

* `Boku no Natsuyasumi (Japan) [T-En boku-ps1 v<version>].xdelta` -- canonical. This is
  what the scene expects and what every front-end on every desktop can apply.
* `... .ppf` -- the bonus path. DuckStation picks up a `.ppf` sitting beside a CHD with
  the same base name, which is a materially nicer experience than "extract, patch,
  recompress" (`research/ps1-translation-practice.md` §2.4). Only possible because nothing
  we emit changes the image's length.
* `PATCH.json` -- size, CRC32, MD5 and SHA-1 of *both* the required original and the
  expected result, plus each patch's own hash. This is the contract `boku apply-patch`
  checks against, and what a release page quotes.
* `README.txt` -- the same thing for a person, in the order the Snatcher release put it
  (§2.2): what you need, its four hashes, the command, the result's four hashes.

Armor is off, deliberately
--------------------------
xdelta3 3.2.0 added "armor": BLAKE3 digests of source and target, checked before
applying, **on by default**. We turn it off, because armor *is* the VCDIFF application
header -- measured on 3.2.0, `-A ""` and `-a -A ""` produce byte-identical patches, so
`PIPE-05`'s required `-A ""` and armor are the same switch and cannot both be had. Given
that, `-A ""` wins on three counts:

* xdelta3 3.0.11 (all current Debian and Ubuntu) and Delta Patcher 3.1.6 (statically
  linked 3.1.0) read an armored header's `name#hex` as a literal filename;
* the header is where a build path leaks -- a released PS1 patch was found carrying
  `F:\Isos\Saturn\...`; 3.2.0 writes only the basename, but an empty header cannot leak
  a name at all, and it makes the patch bytes independent of what we happened to call the
  files, which is half of why the output is reproducible;
* what armor would have bought us -- refusing the wrong source -- `boku apply-patch`
  does from `PATCH.json`, with SHA-1 on both sides rather than one.

What the patch keeps without armor, measured on 3.2.0 with the flags above: each VCDIFF
window still carries `VCD_ADLER32`, and `xdelta3 -d` against a wrong source stops with
*"target window checksum mismatch: the supplied source likely does not match"* having
written nothing. That is 32 bits a window, not a whole-file digest, so the published
SHA-1s remain the contract rather than a courtesy -- but "the patch cannot tell" would be
false and the README must not say it. A `.ppf` that travels alone (dropped beside a CHD)
carries a check of its own: its
50-byte description carries an eight-hex-digit fingerprint of both sides, which is enough
for `boku apply-patch` to refuse an obviously wrong image and is printed by every stock
applier.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path

from boku import __version__
from boku.importer import ImportRefused, check_out_dir, sha1_of
from boku.ppf import PpfError, apply_ppf, make_ppf, read_ppf, refuse_output_over_input
from boku.staging import staged

GAME_NAME = "Boku no Natsuyasumi (Japan)"
TEAM = "boku-ps1"
MANIFEST_NAME = "PATCH.json"
README_NAME = "README.txt"
MANIFEST_FORMAT = 1

DEFAULT_OUT_DIR = Path("build/patch")

XDELTA3 = "xdelta3"
#: `xdelta3 -B` below this is refused outright by 3.2.0 ("-B: minimum value: 524288"),
#: so a source smaller than it -- every test fixture here -- is clamped up.
MIN_SOURCE_WINDOW = 524_288
VCDIFF_MAGIC = b"\xd6\xc3\xc4"
VCD_DECOMPRESS = 0x01
VCD_CODETABLE = 0x02
VCD_APPHEADER = 0x04
VCD_KNOWN_HEADER_BITS = VCD_DECOMPRESS | VCD_CODETABLE | VCD_APPHEADER
#: Deliberately the loose three-byte sniff and not `ppf.MAGIC`: a PPF1 or PPF2 file then
#: reaches `read_ppf`, which says "not a PPF3 patch: expected the magic PPF30", rather
#: than being turned away with the less useful "neither a PPF nor an xdelta patch".
PPF_MAGIC_PREFIX = b"PPF"

CHUNK_SIZE = 1 << 20

_FINGERPRINT = re.compile(
    rf"^{TEAM} v(?P<version>\S+) (?P<original>[0-9a-f]{{8}})>(?P<result>[0-9a-f]{{8}})$"
)


class PatchError(Exception):
    """A patch we will not emit, or one we will not apply to this image."""


@dataclass(frozen=True)
class Hashes:
    """The four numbers a release states for each side, in the scene's order."""

    size: int
    crc32: str
    md5: str
    sha1: str

    def as_dict(self, name: str) -> dict:
        return {
            "name": name,
            "size": self.size,
            "crc32": self.crc32,
            "md5": self.md5,
            "sha1": self.sha1,
        }


@dataclass(frozen=True)
class PatchSet:
    out_dir: Path
    ppf_path: Path
    xdelta_path: Path
    manifest_path: Path
    readme_path: Path
    original: Hashes
    result: Hashes


def hashes_of(path: Path) -> Hashes:
    """Size, CRC32, MD5 and SHA-1 in one pass over the file."""
    crc = 0
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(CHUNK_SIZE):
            crc = zlib.crc32(block, crc)
            md5.update(block)
            sha1.update(block)
            size += len(block)
    # Zero-padded: a CRC32 below 0x10000000 printed as seven digits is one a user cannot
    # match against the eight redump publishes.
    return Hashes(size=size, crc32=f"{crc:08x}", md5=md5.hexdigest(), sha1=sha1.hexdigest())


def patch_stem(version: str) -> str:
    """The scene's naming convention: `Game (Region) [T-En by <author> v<version>]`."""
    return f"{GAME_NAME} [T-En {TEAM} v{version}]"


def ppf_description(version: str, original_sha1: str, result_sha1: str) -> str:
    """What a stock applier prints, and the only check a lone `.ppf` carries.

    Eight hex digits a side is a fingerprint, not a proof -- `PATCH.json` is the contract.
    It is this short because the field is 50 bytes and two full SHA-1s are 80.
    """
    return f"{TEAM} v{version} {original_sha1[:8]}>{result_sha1[:8]}"


# ---------------------------------------------------------------------------
# xdelta


def xdelta_encode_command(original: Path, modified: Path, out_path: Path) -> list[str]:
    """The canonical encode line, with its two non-obvious flags.

    `-B` because xdelta3's source window defaults to 64 MB and "a source copy will not be
    found if it lies more than half the source buffer size away from its absolute
    position" -- on a 659 MB image the default silently inflates the patch. `-A ""`
    because that header is where filenames and armor live; see the module docstring.
    """
    window = max(original.stat().st_size, MIN_SOURCE_WINDOW)
    return [
        XDELTA3, "-e", "-9", "-S", "lzma", "-B", str(window), "-A", "",
        "-s", str(original), str(modified), str(out_path),
    ]  # fmt: skip


def _run(command: list[str], what: str) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise PatchError(
            f"{XDELTA3} is not on PATH; `brew install xdelta` installs 3.2.0"
        ) from error
    except subprocess.CalledProcessError as error:
        raise PatchError(
            f"{what} failed:\n{error.stderr.strip() or error.stdout.strip()}"
        ) from error


def make_xdelta(
    original: Path, modified: Path, out_path: Path, *, expected_sha1: str | None = None
) -> None:
    """Encode, then prove it: decode the patch back and compare SHA-1 with the target.

    An encoder that produced a patch nobody can apply is the failure this guards, and it
    is the only thing that makes the emitted file evidence rather than a hope. It costs
    one decode plus one hash of the decoded image; pass `expected_sha1` when the caller
    has already hashed `modified` and a second full pass over 659 MB is saved.
    """
    out_path.unlink(missing_ok=True)
    _run(xdelta_encode_command(original, modified, out_path), "xdelta3 encode")

    header = xdelta_app_header(out_path.read_bytes())
    if header:
        raise PatchError(
            f"the patch carries a {len(header)}-byte application header ({header[:60]!r}); "
            f'-A "" should have left it empty, and that header is where build paths leak'
        )

    check = out_path.parent / f".{out_path.name}.verify.{os.getpid()}"
    try:
        _run(
            [XDELTA3, "-f", "-d", "-s", str(original), str(out_path), str(check)], "xdelta3 verify"
        )
        produced = sha1_of(check)
        expected = expected_sha1 or sha1_of(modified)
        if produced != expected:
            raise PatchError(
                f"the patch does not reproduce {modified}: decoding it gives sha1 {produced}, "
                f"the image is {expected}"
            )
    finally:
        check.unlink(missing_ok=True)


def xdelta_app_header(patch: bytes) -> bytes:
    """The VCDIFF application header, which must be empty in anything we ship.

    RFC 3284 §4.1 defines the magic `0xD6 0xC3 0xC4`, the version byte, Hdr_Indicator and
    its two bits -- `VCD_DECOMPRESS` (0x01) and `VCD_CODETABLE` (0x02). **The application
    header is not in the RFC**: `VCD_APPHEADER` (0x04) and the length-prefixed block that
    follows the other two are xdelta3's own extension, which is why an RFC-conforming
    decoder such as RomPatcher.js ignores it. Reading these bytes ourselves rather than
    parsing `xdelta3 printhdr` keeps the check off a human-readable format.

    Unknown indicator bits are refused rather than skipped: this function's answer is used
    to decide that a patch leaks no filenames, and a header we cannot fully parse is not
    an empty one.
    """
    if len(patch) < 5 or patch[:3] != VCDIFF_MAGIC:
        raise PatchError(f"not a VCDIFF patch: it starts {patch[:4]!r}, not {VCDIFF_MAGIC!r}")
    position = 4
    indicator = patch[position]
    position += 1
    if indicator & ~VCD_KNOWN_HEADER_BITS:
        raise PatchError(
            f"this VCDIFF sets unknown header bits ({indicator:#04x}); refusing to call its "
            f"application header empty when we cannot read the header at all"
        )
    if indicator & VCD_DECOMPRESS:
        position += 1  # secondary compressor id
    if indicator & VCD_CODETABLE:
        raise PatchError("this VCDIFF carries a custom code table; we do not emit those")
    if not indicator & VCD_APPHEADER:
        return b""
    length, position = _read_varint(patch, position)
    if position + length > len(patch):
        raise PatchError("truncated VCDIFF application header")
    return patch[position : position + length]


def _read_varint(data: bytes, position: int) -> tuple[int, int]:
    """RFC 3284's integer: base-128, most significant group first, 0x80 = "more follows"."""
    value = 0
    while True:
        if position >= len(data):
            raise PatchError("truncated VCDIFF integer")
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, position


# ---------------------------------------------------------------------------
# Emitting a release


def build_patches(
    original: Path,
    modified: Path,
    out_dir: Path,
    *,
    version: str | None = None,
) -> PatchSet:
    """Write both patches, the manifest and the README into `out_dir`.

    Built in a staging directory and moved into place at the end, the way `boku trial`
    builds: a failure leaves the previous complete release or nothing, never this run's
    xdelta beside the last run's manifest.
    """
    version = version or __version__
    for path in (original, modified):
        if not path.is_file():
            raise PatchError(f"{path} is not a file")
    try:
        check_out_dir(out_dir, manifest_name=MANIFEST_NAME, what="patch")
    except ImportRefused as error:
        raise PatchError(str(error)) from error

    original_hashes = hashes_of(original)
    result_hashes = hashes_of(modified)
    stem = patch_stem(version)

    with staged(out_dir, suffix="building") as stage:
        ppf_path = stage / f"{stem}.ppf"
        try:
            ppf_path.write_bytes(
                make_ppf(
                    original,
                    modified,
                    ppf_description(version, original_hashes.sha1, result_hashes.sha1),
                )
            )
            _prove_ppf(original, ppf_path, result_hashes.sha1, stage)
        except PpfError as error:
            raise PatchError(str(error)) from error
        xdelta_path = stage / f"{stem}.xdelta"
        make_xdelta(original, modified, xdelta_path, expected_sha1=result_hashes.sha1)
        manifest = _manifest(
            version=version,
            original=original_hashes,
            original_name=original.name,
            result=result_hashes,
            # Never `modified.name`: this pipeline's two images are `disc/image.img` and
            # `build/trial/image.img`, so that would print `xdelta3 -d -s image.img ...
            # image.img` -- an instruction that overwrites the reader's own dump. The
            # result gets the release's name, which no dump is called.
            result_name=f"{stem}{modified.suffix}",
            ppf_path=ppf_path,
            xdelta_path=xdelta_path,
        )
        (stage / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (stage / README_NAME).write_text(_readme(manifest), encoding="utf-8")

    return PatchSet(
        out_dir=out_dir,
        ppf_path=out_dir / f"{stem}.ppf",
        xdelta_path=out_dir / f"{stem}.xdelta",
        manifest_path=out_dir / MANIFEST_NAME,
        readme_path=out_dir / README_NAME,
        original=original_hashes,
        result=result_hashes,
    )


def _prove_ppf(original: Path, ppf_path: Path, expected_sha1: str, staging: Path) -> None:
    """Apply the PPF we just wrote and check it reproduces the image.

    `make_xdelta` proves its own output by decoding it; before this, the `.ppf` shipped on
    nothing but the writer being right -- and the PPF writer is the hand-rolled one, whose
    difference runs are rejoined across both read-chunk and block boundaries. A defect
    there yields a patch that writes wrong bytes while `boku patch` reports success, and
    the only gate that would catch it needs the real dump and a built trial, which a
    contributor cutting a release may not have.
    """
    produced = staging / ".ppf-proof"
    try:
        apply_ppf(original, ppf_path.read_bytes(), produced)
        actual = sha1_of(produced)
        if actual != expected_sha1:
            raise PatchError(
                f"the PPF we just wrote does not reproduce the built image: applying it "
                f"gives sha1 {actual}, the image is {expected_sha1}. Not shipping it."
            )
    finally:
        produced.unlink(missing_ok=True)


def _manifest(
    *,
    version: str,
    original: Hashes,
    original_name: str,
    result: Hashes,
    result_name: str,
    ppf_path: Path,
    xdelta_path: Path,
) -> dict:
    """Everything a person or a script needs, and nothing that changes between runs.

    No timestamp on purpose: two builds of the same two images must produce the same
    bytes, or nobody can reproduce a release and check it against what we published.
    """
    return {
        "format": MANIFEST_FORMAT,
        "game": GAME_NAME,
        "tool": f"{TEAM} v{version}",
        "original": original.as_dict(original_name),
        "result": result.as_dict(result_name),
        "patches": [
            {
                "file": xdelta_path.name,
                "format": "xdelta3",
                "size": xdelta_path.stat().st_size,
                "sha1": hashes_of(xdelta_path).sha1,
                "apply": f'xdelta3 -d -s "{original_name}" "{xdelta_path.name}" "{result_name}"',
            },
            {
                "file": ppf_path.name,
                "format": "ppf3",
                "size": ppf_path.stat().st_size,
                "sha1": hashes_of(ppf_path).sha1,
                "apply": (
                    f'boku apply-patch "{original_name}" "{ppf_path.name}" --out "{result_name}"'
                ),
            },
        ],
    }


def _readme(manifest: dict) -> str:
    original = manifest["original"]
    result = manifest["result"]
    by_format = {entry["format"]: entry for entry in manifest["patches"]}
    xdelta = by_format["xdelta3"]
    ppf = by_format["ppf3"]

    def block(side: dict) -> str:
        return (
            f"  file  : {side['name']}\n"
            f"  size  : {side['size']:,} bytes\n"
            f"  crc32 : {side['crc32']}\n"
            f"  md5   : {side['md5']}\n"
            f"  sha1  : {side['sha1']}\n"
        )

    return f"""{manifest["game"]} -- English translation patch
{manifest["tool"]}

WHAT YOU NEED
  A raw BIN/IMG dump of the Japanese disc, 2352-byte sectors, one track. Hash it before
  you patch: if these four numbers do not match, the patch is not for your file.

{block(original)}
  Do not apply the patch to a .iso (2048-byte sectors) or to a .chd. Convert first
  (chdman extractcd), hash the result, patch that.

HOW TO APPLY IT
  Ours, which checks both hashes for you and never writes to your dump:

    boku apply-patch "{original["name"]}" "{xdelta["file"]}" --out "{result["name"]}"

  Or the standard tools. xdelta3 (the canonical patch):

    {xdelta["apply"]}

  The patch is NOT armored: it carries no whole-file digest of your dump, so nothing
  checks that the *right* file went in end to end -- the four hashes above are what does
  that, which is why they lead. xdelta3 does still carry a 32-bit Adler-32 per window and
  will stop with "the supplied source likely does not match" on a clearly wrong dump.
  Applying needs an xdelta3 build with LZMA secondary compression, which every mainstream
  one has; the browser patcher at RomPatcher.js does not, and cannot apply this patch.

  The .ppf is a bonus for two specific tools. DuckStation applies it at load time if you
  drop it next to your disc image with the same base name (a .chd works) and tick
  Settings -> CD-ROM -> Apply Image Patches, which is OFF by default. No other PPF applier
  refuses a wrong image: the Icarus/Paradox one asks and carries on if you say yes, and
  DuckStation does not check at all.

WHAT YOU SHOULD GET
{block(result)}
THE PATCHES THEMSELVES
  {xdelta["file"]}
    {xdelta["size"]:,} bytes, sha1 {xdelta["sha1"]}
  {ppf["file"]}
    {ppf["size"]:,} bytes, sha1 {ppf["sha1"]}

IF THE HASHES DO NOT MATCH
  You have a different dump. Nothing here is a fix for that: get a dump whose SHA-1 is
  the one stated above. This patch is free; it is never sold and never shipped with a
  disc image.
"""


# ---------------------------------------------------------------------------
# Applying


@dataclass(frozen=True)
class Expectation:
    """What the original and the result must hash to, and where that came from.

    Both values are always present: an expectation that could be absent would let
    "nothing to check" and "checked and passed" look the same, which is the single
    failure this whole module exists to prevent.

    `partial` is true only for a lone `.ppf`'s description fingerprint, which has room
    for eight hex digits a side. Everywhere else a full 40 is required -- otherwise a
    half-pasted hash on the command line would silently weaken the check to however many
    characters were pasted.
    """

    original: str
    result: str
    source: str
    partial: bool = False


_HEX = re.compile(r"^[0-9a-f]+$")


def _sha1_field(value: object, what: str, source: str, *, digits: int) -> str:
    """One stated SHA-1, normalised, or `PatchError`.

    Lower-cased because redump publishes uppercase and a contributor pastes what they are
    shown; length- and alphabet-checked because JSON `null`, `""` and `12345` all reach
    here from a hand-edited manifest, and each of them used to disable the check it was
    supposed to be.
    """
    if not isinstance(value, str):
        raise PatchError(f"{source} states a {what} that is not text: {value!r}")
    text = value.strip().lower()
    if len(text) != digits or not _HEX.match(text):
        raise PatchError(
            f"{source} states a {what} of {text!r}, which is not {digits} hex digits. "
            f"Refusing to patch against an expectation we cannot read."
        )
    return text


def _expectation(
    patch_path: Path,
    patch: bytes,
    expect_original: str | None,
    expect_result: str | None,
) -> Expectation:
    """Where the two hashes come from: the command line, then `PATCH.json`, then the PPF.

    The manifest is only honoured when it actually lists *this* patch. A release folder
    keeps its `PATCH.json`, so dropping a newer lone `.ppf` into an older one would
    otherwise check the new patch against the old release's hashes and blame the patch.
    """
    if expect_original and expect_result:
        return Expectation(
            _sha1_field(expect_original, "original sha1", "--expect-original-sha1", digits=40),
            _sha1_field(expect_result, "result sha1", "--expect-result-sha1", digits=40),
            "the command line",
        )

    manifest_path = patch_path.parent / MANIFEST_NAME
    stale_manifest = False
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            listed = {entry.get("file") for entry in manifest.get("patches", [])}
            original_sha1 = manifest["original"]["sha1"]
            result_sha1 = manifest["result"]["sha1"]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise PatchError(
                f"{manifest_path} is not a patch manifest we can read: {error}"
            ) from error
        if patch_path.name in listed:
            source = str(manifest_path)
            return Expectation(
                _sha1_field(expect_original or original_sha1, "original sha1", source, digits=40),
                _sha1_field(expect_result or result_sha1, "result sha1", source, digits=40),
                source,
            )
        stale_manifest = True

    if patch.startswith(PPF_MAGIC_PREFIX):
        try:
            description = read_ppf(patch).description
        except PpfError as error:
            raise PatchError(str(error)) from error
        matched = _FINGERPRINT.match(description)
        if matched:
            source = "the fingerprint in the PPF description"
            return Expectation(
                _sha1_field(
                    expect_original or matched["original"], "original sha1", source, digits=8
                ),
                _sha1_field(expect_result or matched["result"], "result sha1", source, digits=8),
                source,
                partial=True,
            )

    beside = (
        f"The {MANIFEST_NAME} beside it does not list {patch_path.name}, so it belongs to a "
        f"different release. "
        if stale_manifest
        else f"There is no {MANIFEST_NAME} beside it "
    )
    raise PatchError(
        f"nothing says what {patch_path.name} expects. {beside}and the patch carries no "
        f"fingerprint. Put this release's {MANIFEST_NAME} next to the patch, or pass "
        f"--expect-original-sha1 and --expect-result-sha1. Refusing to patch an image we "
        f"cannot check."
    )


def _agrees(actual: str, expected: str, *, partial: bool) -> bool:
    return actual.startswith(expected) if partial else actual == expected


def apply_patch(
    original: Path,
    patch_path: Path,
    out_path: Path,
    *,
    expect_original: str | None = None,
    expect_result: str | None = None,
) -> Hashes:
    """Apply a `.ppf` or a `.xdelta` of ours, checking both sides. Returns the result's hashes.

    The original's SHA-1 is checked *before* anything is produced and the result's *after*
    it is produced but before it is given its name, so a failure of either leaves nothing
    behind that could be mistaken for a patched image. `original` is never written, and
    `--out` may not name it (`refuse_output_over_input`) -- opening it read-only would not
    save it from the rename at the end.
    """
    try:
        refuse_output_over_input(original, out_path)
    except PpfError as error:
        raise PatchError(str(error)) from error

    patch = patch_path.read_bytes()
    expectation = _expectation(patch_path, patch, expect_original, expect_result)

    before = sha1_of(original)
    if not _agrees(before, expectation.original, partial=expectation.partial):
        raise PatchError(
            f"{original} is not the image this patch is for.\n"
            f"  its sha1     : {before}\n"
            f"  expected     : {expectation.original}  (from {expectation.source})\n"
            f"Nothing has been written."
        )

    temporary = out_path.parent / f".{out_path.name}.patching.{os.getpid()}"
    try:
        if patch.startswith(PPF_MAGIC_PREFIX):
            try:
                apply_ppf(original, patch, temporary)
            except PpfError as error:
                raise PatchError(str(error)) from error
        elif patch.startswith(VCDIFF_MAGIC):
            _run(
                [XDELTA3, "-f", "-d", "-s", str(original), str(patch_path), str(temporary)],
                "xdelta3 decode",
            )
        else:
            raise PatchError(
                f"{patch_path.name} is neither a PPF nor an xdelta patch: it starts {patch[:5]!r}"
            )

        after = hashes_of(temporary)
        if not _agrees(after.sha1, expectation.result, partial=expectation.partial):
            raise PatchError(
                f"the patched image is not what this patch promised.\n"
                f"  produced sha1: {after.sha1}\n"
                f"  expected     : {expectation.result}  (from {expectation.source})\n"
                f"The result has been discarded; {original} is untouched."
            )
        temporary.replace(out_path)
    finally:
        temporary.unlink(missing_ok=True)
    return after


# ---------------------------------------------------------------------------
# Command line


def main_patch(original: Path, modified: Path, out_dir: Path) -> int:
    try:
        result = build_patches(original, modified, out_dir)
    except (PatchError, OSError) as error:
        print(f"boku patch: {error}")
        return 1
    print(
        f"wrote {result.out_dir}/\n"
        f"  {result.xdelta_path.name}  {result.xdelta_path.stat().st_size:,} bytes\n"
        f"  {result.ppf_path.name}  {result.ppf_path.stat().st_size:,} bytes\n"
        f"  original sha1 {result.original.sha1}\n"
        f"  result   sha1 {result.result.sha1}"
    )
    return 0


def main_apply_patch(
    original: Path,
    patch_path: Path,
    out_path: Path,
    expect_original: str | None,
    expect_result: str | None,
) -> int:
    try:
        produced = apply_patch(
            original,
            patch_path,
            out_path,
            expect_original=expect_original,
            expect_result=expect_result,
        )
    except (PatchError, PpfError, OSError) as error:
        print(f"boku apply-patch: {error}")
        return 1
    print(f"wrote {out_path}\n  sha1 {produced.sha1}  crc32 {produced.crc32}  md5 {produced.md5}")
    return 0
