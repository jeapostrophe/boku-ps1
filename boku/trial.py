"""`TXT-04`, the trial: one English line on screen in a rebuilt image.

This builds `build/trial/image.img` -- a copy of your own import with a few EXE words
changed and, optionally, English written over a line of dialogue. It is the go/no-go for
the whole approach (`PLAN TXT-04`): it proves the chain *text table -> image -> emulator*
end to end, and it is the first thing on this project that has to be right on hardware as
well as in an emulator, because every sector it touches gets fresh EDC and ECC
(`boku.edc`).

Four pieces, each switchable
----------------------------
**The renderer patch** (`RENDERER_PATCH`, on unless `--no-renderer-patch`). Dialogue is
drawn vertically because two call sites pass a literal 1 for the direction argument;
`research/text-renderer.md` § 7 measured the three `addiu` immediates that decide where
the dialogue strip starts and which way it runs.

**The band** (`BAND_PATCH`, on with the renderer patch unless `--no-band`). Horizontal
text alone is illegible: the dialogue "box" is a 60-px strip down the *right* edge, so
left-to-right text lands on bare scenery. `research/renderer-runtime.md` § Q2 measured
the fix in RAM -- the same instruction slots made to draw a band across the foot of the
screen, with the pen moved into it.

**One line in English** (`--line`). A logical line has up to 53 physical copies on the
disc, and which copy the game reaches is not known statically, so every copy is
overwritten (`boku.text.SiteIndex.copies_of`).

**Markers** (`--all-lines-marker`). The recipe cannot name the opening line from static
analysis -- `research/text-renderer.md` § 7 says Step B's target "is chosen from Step A's
screen". So this mode writes each event message's own site id (`E0112.0`) over it, and
whatever line the game reaches announces which one it is. Feed that id back as `--line`.

Nothing grows: every write is the same byte length as what it replaces, because the image
is patched in place and 226,000 sectors of streaming media sit behind `BOKU.BIN` at fixed
addresses (`PIPE-04`).

Nothing half-built escapes either: the image is patched inside a staging directory beside
`--out` and moved into place only once every write and the manifest have succeeded, so a
failure leaves the previous complete build or nothing at all -- never this run's image
beside the last run's manifest.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from boku import edc
from boku.disc import DirEntry, DiscError, DiscImage, DiscWriter, SectorWrite
from boku.edc import FORM1_DATA_SIZE
from boku.importer import ImportRefused, check_out_dir, sha1_of
from boku.text import (
    ARCHIVE_NAME,
    EXE_NAME,
    MESSAGE_KINDS,
    GlyphTable,
    PlacedSite,
    SiteIndex,
    TextError,
    check_placement,
)

DEFAULT_IMAGE = Path("disc/image.img")
DEFAULT_OUT_DIR = Path("build/trial")
IMAGE_NAME = "image.img"
CUE_NAME = "image.cue"
MANIFEST_NAME = "manifest.json"
MANIFEST_FORMAT = 1

EXE_PATH = f"/{EXE_NAME}"
ARCHIVE_PATH = f"/{ARCHIVE_NAME}"

TRIAL_TEXT = "Hello, Boku!"
"""`research/text-renderer.md` § 7 Step B's line. Thirteen words including the terminator."""


@dataclass(frozen=True)
class PatchWord:
    """One word (or halfword) of `SCPS_100.88` to change, named by its file offset.

    `old` is what has to be there first: a build whose bytes differ is either already
    patched or not the dump these addresses were measured on, and either way the recipe
    does not describe it.
    """

    file_offset: int
    old: bytes
    new: bytes
    meaning: str

    @property
    def ram_address(self) -> int:
        """Where this word lives at run time. The EXE is identity-loaded (`Q0`)."""
        return self.file_offset + EXE_LOAD_BIAS


EXE_LOAD_BIAS = 0x8000F800
"""RAM address = file offset + this (`research/text-renderer.md`, confirmed by `Q0`)."""

RENDERER_PATCH: tuple[PatchWord, ...] = (
    PatchWord(0x1D7C4, bytes.fromhex("29010424"), bytes.fromhex("18000424"), "x = 24"),
    PatchWord(0x1D7C8, bytes.fromhex("16000524"), bytes.fromhex("84000524"), "y = 132"),
    PatchWord(0x1D7CC, bytes.fromhex("01000624"), bytes.fromhex("00000624"), "horizontal"),
)
"""The Step A table of `research/text-renderer.md` § 7, which a test reads back out of it."""

# --- the band, measured in RAM: research/renderer-runtime.md § Q2 item 3 ------------------
#
# `dialog_panel_draw` (`0x8002E964`) builds one TILE from four halfwords at s0. Stock, it
# draws the right-hand strip: x from `g_dlgbox_x` + 5, y = 0, and `s1` carries 0xF0 as
# *both* the height and (through the store at 0x8002EA38) nothing else, so a band made by
# that route has y = h. The variant below spends the slot that stored x on a second
# constant instead -- x becomes the literal 0 -- which buys an independent y and h in the
# same five words and no new instructions. Measured values: y = 168, h = 72 leaves room
# for three lines and already contains the next-page arrow's stock position (266, 220).

BAND_Y = 168
BAND_H = 72
BAND_TEXT_Y = 176
"""The first baseline, 8 px inside the band. `research/renderer-runtime.md` § Q2 item 3."""

BAND_TEXT_ORIGIN = PatchWord(
    0x1D7C8,
    bytes.fromhex("16000524"),  # addiu a1, zero, 0x16   (y = 22, the strip's top line)
    bytes.fromhex("B0000524"),  # addiu a1, zero, 0xB0   (y = 176, inside the band)
    f"y = {BAND_TEXT_Y}, the first baseline inside the band",
)
"""Replaces `RENDERER_PATCH`'s y: (24, 132) is above the band and would print over scenery."""

BAND_PATCH: tuple[PatchWord, ...] = (
    PatchWord(
        0x1991C,
        bytes.fromhex("0401"),  # g_dlgbox_x = 260 (s16): the strip's left edge
        bytes.fromhex("FBFF"),  # g_dlgbox_x = -5: x 0, w = 0x145 - x = 330, fade off-screen
        "g_dlgbox_x = -5",
    ),
    PatchWord(
        0x1F234,
        bytes.fromhex("F0001124"),  # addiu s1, zero, 0xF0   (height 240: the full strip)
        bytes.fromhex("48001124"),  # addiu s1, zero, 0x48   (height 72)
        f"band height = {BAND_H}",
    ),
    PatchWord(
        0x1F238,
        bytes.fromhex("0A0000A6"),  # sh zero, 0xA(s0)       (tile y = 0)
        bytes.fromhex("080000A6"),  # sh zero, 8(s0)         (tile x = 0; frees the slot below)
        "tile x = 0",
    ),
    PatchWord(
        0x1F244,
        bytes.fromhex("05006224"),  # addiu v0, v1, 5        (x = g_dlgbox_x + 5)
        bytes.fromhex("A8000224"),  # addiu v0, zero, 0xA8   (y = 168)
        f"band y = {BAND_Y}",
    ),
    PatchWord(
        0x1F248,
        bytes.fromhex("080002A6"),  # sh v0, 8(s0)           (tile x = that sum)
        bytes.fromhex("0A0002A6"),  # sh v0, 0xA(s0)         (tile y = 168)
        "tile y = the band's top",
    ),
)


def patch_words(renderer_patch: bool, band: bool) -> tuple[PatchWord, ...]:
    """The words this build changes in `SCPS_100.88`, in the order they are written."""
    if not renderer_patch:
        return ()
    if not band:
        return RENDERER_PATCH
    origin = tuple(
        BAND_TEXT_ORIGIN if word.file_offset == BAND_TEXT_ORIGIN.file_offset else word
        for word in RENDERER_PATCH
    )
    return origin + BAND_PATCH


class TrialRefused(Exception):
    """The build will not proceed.

    Everything that can be checked is checked before the 660 MB copy -- the line exists,
    its sites are the writable kind, the English fits the font, and the EXE still holds
    the words the recipe expects -- so a refusal normally leaves nothing behind at all.
    A failure after that point discards the staging directory and leaves whatever was at
    `--out` before, untouched.
    """


@dataclass
class SectorRecord:
    """A sector the build changed. `offset` is where it starts inside `file`."""

    lba: int
    file: str
    offset: int
    old_sha1: str
    new_sha1: str


@dataclass
class TrialResult:
    image: Path
    cue: Path
    manifest: Path
    source_sha1: str
    result_sha1: str
    renderer_patched: bool
    band: bool
    line: str | None
    text: str
    line_copies: int
    markers_written: int
    markers_too_small: int
    markers_superseded: int
    sectors: list[SectorRecord] = field(default_factory=list)

    @property
    def unchanged(self) -> bool:
        return not self.sectors

    @property
    def words(self) -> tuple[PatchWord, ...]:
        return patch_words(self.renderer_patched, self.band)


def _file_entry(image: DiscImage, path: str) -> DirEntry:
    for entry in image.walk():
        if entry.path == path:
            return entry
    raise TrialRefused(f"{image.path} has no {path}; this is not SCPS-10088")


class _Ledger:
    """Collects sector writes so the manifest shows each LBA once, as it was and as it is.

    Two sites can share a sector, so the same LBA can be written twice; the manifest must
    still say what that sector looked like before the build touched it and after it
    finished. A sector whose bytes come back to where they started is dropped, so the
    manifest is exactly the set of sectors an image diff can see.
    """

    def __init__(self) -> None:
        self._first: dict[int, str] = {}
        self._last: dict[int, str] = {}
        self._where: dict[int, tuple[str, int]] = {}

    def add(self, writes: list[SectorWrite], file_name: str, file_lba: int) -> None:
        for write in writes:
            self._first.setdefault(write.lba, write.old_sha1)
            self._last[write.lba] = write.new_sha1
            self._where[write.lba] = (file_name, (write.lba - file_lba) * FORM1_DATA_SIZE)

    def records(self) -> list[SectorRecord]:
        out = []
        for lba in sorted(self._first):
            if self._first[lba] == self._last[lba]:
                continue
            file_name, offset = self._where[lba]
            out.append(
                SectorRecord(
                    lba=lba,
                    file=file_name,
                    offset=offset,
                    old_sha1=self._first[lba],
                    new_sha1=self._last[lba],
                )
            )
        return out


def _check_patch_words(image: DiscImage, exe: DirEntry, words: tuple[PatchWord, ...]) -> None:
    """Refuse unless every word the patch replaces is still what the recipe measured."""
    for word in words:
        found = image.read_file_bytes(exe.lba, word.file_offset, len(word.old))
        if found != word.old:
            raise TrialRefused(
                f"{EXE_NAME}+0x{word.file_offset:x} holds {found.hex(' ')}, and the "
                f"recipe says {word.old.hex(' ')} ({word.meaning}). Either this image is "
                f"already patched or it is not the dump the recipe was measured on; "
                f"nothing was written."
            )


def _apply_patch_words(
    writer: DiscWriter, exe: DirEntry, words: tuple[PatchWord, ...], ledger: _Ledger
) -> None:
    """Write the patch, having proved once more that the copy holds the expected bytes."""
    _check_patch_words(writer, exe, words)
    for word in words:
        ledger.add(
            writer.write_file_bytes(exe.lba, word.file_offset, word.new, file_size=exe.size),
            EXE_NAME,
            exe.lba,
        )


def _check_writable(placed: PlacedSite) -> None:
    """Only message sites are overwritten. The reason is the terminator's two meanings.

    A message reader stops at the first `0x8000`, so anything this module writes after
    one is never read and the site's original length can be padded out safely. In an
    array the same word *delimits* the items, and `REC-03` finds item `n + 1` by scanning
    past item `n`'s terminator -- so an early `0x8000` would move every item after it.
    The trial has no business in one, and `TXT-05` will need a different filler rule when
    the pipeline does.
    """
    if placed.site.kind not in MESSAGE_KINDS:
        raise TrialRefused(
            f"{placed.site.site_id} is a {placed.site.kind} site, and only message sites "
            f"({', '.join(MESSAGE_KINDS)}) are overwritten: an early terminator would "
            f"move every item after it in an array."
        )


def _write_site(
    writer: DiscWriter,
    placed: PlacedSite,
    text: str,
    glyphs: GlyphTable,
    files: dict[str, DirEntry],
    ledger: _Ledger,
) -> None:
    """Overwrite one site with `text`, after proving the disc agrees about what is there."""
    _check_writable(placed)
    site = placed.site
    entry = files[placed.file_name]
    current = writer.read_file_bytes(entry.lba, placed.file_offset, site.size)
    check_placement(placed, current)
    replacement = glyphs.message(text, site.size)
    ledger.add(
        writer.write_file_bytes(entry.lba, placed.file_offset, replacement, file_size=entry.size),
        placed.file_name,
        entry.lba,
    )


def _check_out_dir(out_dir: Path, source: Path) -> None:
    """Refuse an output directory that would damage the import, or someone else's files.

    Two rules. The first is this module's: `--out` is replaced wholesale, and the import
    it is reading from is the one thing in the repo that cannot be regenerated without
    the contributor's own disc, so `--out` may not be, contain, or sit inside the
    directory holding the source image -- `boku trial --out disc` would otherwise leave
    every later "real disc" test running against a patched image. The second is the
    import step's own (`boku.importer.check_out_dir`): a non-empty directory with no
    manifest in it is not this tool's to delete.
    """
    # Both sides are resolved here rather than by the caller: on macOS `/tmp` is a
    # symlink to `/private/tmp`, so an unresolved pair of paths to the same directory
    # are not relative to each other and the whole guard silently passes.
    source_dir = source.resolve().parent
    out_dir = out_dir.resolve()
    if out_dir == source_dir or out_dir.is_relative_to(source_dir):
        raise TrialRefused(
            f"--out {out_dir} is inside {source_dir}, which holds the image this build "
            f"reads. The trial writes a patched copy; putting it there would overwrite "
            f"your verified import, and every test that checks against the real disc "
            f"would silently run on the patched one."
        )
    if source_dir.is_relative_to(out_dir):
        raise TrialRefused(
            f"--out {out_dir} contains {source_dir}, and a successful build replaces "
            f"--out whole; that would delete your verified import."
        )
    try:
        check_out_dir(out_dir, manifest_name=MANIFEST_NAME, what="trial")
    except ImportRefused as error:
        raise TrialRefused(str(error)) from error


def build_trial(
    source: Path = DEFAULT_IMAGE,
    out_dir: Path = DEFAULT_OUT_DIR,
    line: str | None = None,
    text: str = TRIAL_TEXT,
    markers: bool = False,
    renderer_patch: bool = True,
    band: bool | None = None,
) -> TrialResult:
    """Copy `source` to `out_dir/image.img` and apply the trial to the copy, in place.

    `band` defaults to whatever `renderer_patch` is: the band exists to back horizontal
    text and is meaningless without it. With `renderer_patch` off and neither `line` nor
    `markers` asked for, nothing is written and the copy is byte-identical to `source` --
    the null round trip.
    """
    source = Path(source)
    out_dir = Path(out_dir).resolve()
    band = renderer_patch if band is None else band
    if band and not renderer_patch:
        raise TrialRefused(
            "--band redraws the dialogue strip as a band under horizontal text; with "
            "--no-renderer-patch the text is still vertical and the band would only "
            "cover the scene. Pass --no-band as well."
        )
    if not source.is_file():
        raise TrialRefused(f"{source} is not there: run `./make.sh import` first")
    _check_out_dir(out_dir, source)

    words = patch_words(renderer_patch, band)
    glyphs = GlyphTable.load()
    index = SiteIndex() if (line or markers) else None
    copies: list[PlacedSite] = []
    if line:
        try:
            copies = index.copies_of(line)
        except TextError as error:
            raise TrialRefused(str(error)) from error
        # Everything checkable, checked before the 660 MB copy.
        for placed in copies:
            _check_writable(placed)
            try:
                glyphs.message(text, placed.site.size)
            except TextError as error:
                raise TrialRefused(f"{placed.site.site_id}: {error}") from error

    with DiscImage(source) as reader:
        exe = _file_entry(reader, EXE_PATH)
        archive = _file_entry(reader, ARCHIVE_PATH)
        _check_patch_words(reader, exe, words)
    files = {exe.name: exe, archive.name: archive}

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = out_dir.parent / f".{out_dir.name}.building.{os.getpid()}"
    replaced = out_dir.parent / f".{out_dir.name}.replaced.{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        image = staging / IMAGE_NAME
        shutil.copyfile(source, image)
        (staging / CUE_NAME).write_text(
            f'FILE "{IMAGE_NAME}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n',
            encoding="ascii",
        )

        ledger = _Ledger()
        markers_written = 0
        markers_too_small = 0
        markers_superseded = 0
        with DiscWriter(image) as writer:
            _apply_patch_words(writer, exe, words, ledger)
            if markers:
                # A site `--line` is about to rewrite must not be tagged first: the tag
                # would become what is on the disc, and the line write's check_placement
                # -- which proves the table still describes this image -- would fail
                # against its own marker. The English wins, and the sites it takes are
                # counted separately.
                claimed = {(entry.file_name, entry.file_offset) for entry in copies}
                for placed in index.event_messages():
                    if (placed.file_name, placed.file_offset) in claimed:
                        markers_superseded += 1
                        continue
                    tag = placed.site.site_id
                    try:
                        glyphs.message(tag, placed.site.size)
                    except TextError:
                        # `GlyphTable.message` is the one authority on what fits; this
                        # loop asks it rather than reproducing its arithmetic.
                        markers_too_small += 1
                        continue
                    _write_site(writer, placed, tag, glyphs, files, ledger)
                    markers_written += 1
            for placed in copies:
                _write_site(writer, placed, text, glyphs, files, ledger)
            writer.flush()

        result = TrialResult(
            image=out_dir / IMAGE_NAME,
            cue=out_dir / CUE_NAME,
            manifest=out_dir / MANIFEST_NAME,
            source_sha1=sha1_of(source),
            result_sha1=sha1_of(image),
            renderer_patched=renderer_patch,
            band=band,
            line=line,
            text=text,
            line_copies=len(copies),
            markers_written=markers_written,
            markers_too_small=markers_too_small,
            markers_superseded=markers_superseded,
            sectors=ledger.records(),
        )
        (staging / MANIFEST_NAME).write_text(_manifest_json(result), encoding="utf-8")

        if out_dir.exists():
            out_dir.rename(replaced)
        try:
            staging.rename(out_dir)
        except OSError:
            if replaced.exists():
                replaced.rename(out_dir)
            raise
        shutil.rmtree(replaced, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return result


def _manifest_json(result: TrialResult) -> str:
    return (
        json.dumps(
            {
                "format": MANIFEST_FORMAT,
                "source_sha1": result.source_sha1,
                "result_sha1": result.result_sha1,
                "band": result.band,
                "exe_patch": [
                    {
                        "file": EXE_NAME,
                        "offset": f"0x{word.file_offset:x}",
                        "ram": f"0x{word.ram_address:08x}",
                        "old": word.old.hex(" "),
                        "new": word.new.hex(" "),
                        "meaning": word.meaning,
                    }
                    for word in result.words
                ],
                "line": result.line,
                "line_text": result.text if result.line else None,
                "line_copies": result.line_copies,
                "markers_written": result.markers_written,
                "markers_too_small": result.markers_too_small,
                "markers_superseded_by_line": result.markers_superseded,
                "sectors": [
                    {
                        "lba": record.lba,
                        "file": record.file,
                        "offset": f"0x{record.offset:x}",
                        "old_sha1": record.old_sha1,
                        "new_sha1": record.new_sha1,
                    }
                    for record in result.sectors
                ],
            },
            indent=2,
        )
        + "\n"
    )


def verify_written_sectors(image: Path, records: list[SectorRecord]) -> list[int]:
    """LBAs among `records` whose stored EDC/ECC do not match their own bytes (want: none)."""
    bad = []
    with DiscImage(image) as opened:
        for record in records:
            if not edc.check_sector(opened.read_raw(record.lba), record.lba).ok:
                bad.append(record.lba)
    return bad


def format_summary(result: TrialResult) -> str:
    lines = [
        f"wrote {result.image} ({result.result_sha1})",
        f"  from {result.source_sha1}",
        f"  renderer patch: {'applied' if result.renderer_patched else 'skipped'}"
        f"{', with the band' if result.band else ''}"
        f" ({len(result.words)} words)",
    ]
    if result.line:
        lines.append(f"  line {result.line}: {result.line_copies} physical copies overwritten")
    if result.markers_written or result.markers_too_small:
        superseded = (
            f", {result.markers_superseded} left to --line" if result.markers_superseded else ""
        )
        lines.append(
            f"  markers: {result.markers_written} event messages tagged, "
            f"{result.markers_too_small} too small to hold their own id{superseded}"
        )
    lines.append(f"  {len(result.sectors)} sectors changed; manifest: {result.manifest}")
    if result.unchanged:
        lines.append("  nothing was written: this image is byte-identical to its source")
    return "\n".join(lines)


def main_trial(
    source: str | None,
    out_dir: Path,
    line: str | None,
    text: str,
    markers: bool,
    renderer_patch: bool,
    band: bool | None,
) -> int:
    try:
        result = build_trial(
            source=Path(source) if source else DEFAULT_IMAGE,
            out_dir=out_dir,
            line=line,
            text=text,
            markers=markers,
            renderer_patch=renderer_patch,
            band=band,
        )
    except (TrialRefused, TextError, DiscError, OSError) as error:
        # OSError covers shutil.SameFileError and every permission, space and
        # cross-device failure of the copy and the swap: the caller gets the sentence,
        # not a traceback.
        print(f"boku trial: {error}")
        return 1
    bad = verify_written_sectors(result.image, result.sectors)
    print(format_summary(result))
    if bad:
        print(f"boku trial: {len(bad)} written sectors fail their own EDC/ECC: {bad[:8]}")
        return 1
    return 0
