"""Textures out of the archive and edits back into it (PLAN `GFX-01`).

Export writes one **indexed** PNG per distinct image, palette and all, so an edit that
keeps to the exported palette comes back through `import_edits` without a colour decision
being made anywhere. Import turns that edit into binary patches — file, offset, old bytes,
new bytes — at **every** occurrence of the image, which is the point: a texture on this
disc is stored 2,607 times over 824 distinct images, one watercolour minimap in 287 of
them (`research/textures.md`), and every copy has to move together or the map flickers
between two versions.

Nothing here writes into the archive. The patches are a value; `boku.tim` guarantees that
applying them changes pixels and nothing else — not a depth, not a dimension, not a VRAM
origin, not one byte of a CLUT that other regions of the same atlas share.

Identity: a texture is named by its member and the offset of its *first* occurrence,
which is the scheme `research/data/texture-census.tsv` already uses, so the census's
`has_text` column joins straight onto an export.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import ARCHIVE_NAME, EXE_NAME, Archive, ArchiveError
from boku.png import Png, PngError, write_indexed
from boku.png import read as read_png
from boku.reinsert import ByteEdit
from boku.staging import StagingRefused, check_out_dir, staged
from boku.tim import MAGIC, Quantisation, Tim, TimError, indices_from_rgba
from boku.tim import nearest_indices as nearest_tim_indices
from boku.tim import parse as parse_tim

DEFAULT_OUT_DIR = Path("work/textures")
"""Under the gitignored `work/`: an exported texture is the game's own pixels."""

INDEX_NAME = "index.json"
FORMAT = 1
CENSUS_TSV = REPO_ROOT / "research/data/texture-census.tsv"
EXE_MEMBER = f"\\{EXE_NAME}"
TEXT_COLUMN = "has_text"
TEXT_VALUES = ("yes", "maybe")
"""`--only-text` takes the census's `maybe` as well: it means "marks that were not read"."""

PAD_COLOUR = (255, 0, 255)
"""What an index past the CLUT's own length is shown as. No TIM on the disc has one."""


class TextureError(Exception):
    """An export or an import cannot be done as asked."""


# --- enumeration -------------------------------------------------------------------------


def scan(blob: bytes) -> Iterator[tuple[int, Tim]]:
    """Every TIM in `blob`, left to right, non-overlapping.

    Greedy: a candidate that parses is accepted and the scan resumes past its end, so a
    stray magic word inside an accepted TIM's pixels cannot manufacture a nested one. Over
    all 104 MB the greediness never mattered — exactly the 4-aligned offsets that parse at
    all are the ones accepted (`research/textures.md` § Method).
    """
    magic = MAGIC.to_bytes(4, "little")
    at = 0
    while True:
        found = blob.find(magic, at)
        if found < 0:
            return
        if found & 3:
            at = found + 1
            continue
        tim = parse_tim(blob, found)
        if tim is None:
            at = found + 4
            continue
        yield found, tim
        at = found + tim.length


def texture_id(member: str, offset: int) -> str:
    """`_DATA_NIKKI.BIN_NIKKI_001__000000` — the census's id scheme, so the tables join."""
    return f"{member.strip(chr(92)).replace(chr(92), '_').replace('/', '_')}__{offset:06x}"


@dataclass(frozen=True)
class Occurrence:
    """One place a texture's bytes are stored."""

    file: str
    """`BOKU.BIN` or `SCPS_100.88` — what a patch addresses."""
    member: str
    """The dev-time member path; the same as `file` for the executable."""
    offset: int
    """Byte offset within the member."""
    file_offset: int
    """Byte offset within `file`, which is what a patch needs."""
    length: int


@dataclass(frozen=True)
class Texture:
    """One distinct image and every place it is stored."""

    id: str
    sha1: str
    tim: Tim
    occurrences: tuple[Occurrence, ...]

    @property
    def copies(self) -> int:
        return len(self.occurrences)

    @property
    def width(self) -> int:
        return self.tim.width

    @property
    def height(self) -> int:
        return self.tim.height


@dataclass(frozen=True)
class Inventory:
    """Every distinct texture on the disc, in first-occurrence order."""

    textures: tuple[Texture, ...]

    @property
    def occurrences(self) -> int:
        return sum(t.copies for t in self.textures)

    def get(self, texture_id: str) -> Texture:
        for texture in self.textures:
            if texture.id == texture_id:
                return texture
        raise TextureError(f"no texture {texture_id} on this disc")

    def by_id(self) -> dict[str, Texture]:
        return {t.id: t for t in self.textures}


def inventory(archive: Archive) -> Inventory:
    """Scan the whole import and group occurrences by the SHA-1 of the TIM's bytes."""
    order: list[str] = []
    found: dict[str, list[Occurrence]] = {}
    first: dict[str, Tim] = {}

    def add(file: str, member: str, base: int, blob: bytes) -> None:
        for offset, tim in scan(blob):
            raw = blob[offset : offset + tim.length]
            digest = hashlib.sha1(raw).hexdigest()
            if digest not in found:
                order.append(digest)
                found[digest] = []
                first[digest] = tim
            found[digest].append(Occurrence(file, member, offset, base + offset, tim.length))

    for member in archive.members:
        add(ARCHIVE_NAME, member.name, member.offset, archive.blob(member))
    add(EXE_NAME, EXE_MEMBER, 0, archive.exe)

    textures = []
    for digest in order:
        places = found[digest]
        textures.append(
            Texture(
                id=texture_id(places[0].member, places[0].offset),
                sha1=digest,
                tim=first[digest],
                occurrences=tuple(places),
            )
        )
    return Inventory(tuple(textures))


def text_bearing_ids(census: Path = CENSUS_TSV) -> set[str]:
    """The census ids whose `has_text` is `yes` or `maybe` — what `--only-text` keeps."""
    lines = Path(census).read_text(encoding="utf-8").splitlines()
    if not lines:
        raise TextureError(f"{census} is empty")
    header = lines[0].split("\t")
    try:
        column = header.index(TEXT_COLUMN)
    except ValueError:
        raise TextureError(f"{census} has no {TEXT_COLUMN} column") from None
    keep = set()
    for line in lines[1:]:
        row = line.split("\t")
        if len(row) > column and row[column] in TEXT_VALUES:
            keep.add(row[0])
    return keep


# --- the palette an artist edits against --------------------------------------------------


def png_palette(tim: Tim, clut: int = 0) -> tuple[list[tuple[int, int, int]], list[int]]:
    """The TIM's CLUT as a PNG palette and its `tRNS`, padded to cover every index used.

    A CLUT shorter than the depth can address is padded with `PAD_COLOUR`, which no TIM on
    this disc needs; using one of those entries in an edit is refused on the way back in.
    """
    entries = tim.palette_rgba(clut)
    colours = [c[:3] for c in entries]
    alpha = [c[3] for c in entries]
    padding = tim.highest_index() + 1 - len(colours)  # one scan of the pixels, not one per entry
    if padding > 0:
        colours += [PAD_COLOUR] * padding
        alpha += [255] * padding
    return colours, alpha


def to_png(tim: Tim, clut: int = 0) -> bytes:
    """An indexed PNG of `tim` through CLUT `clut`, at the TIM's own bit depth."""
    colours, alpha = png_palette(tim, clut)
    return write_indexed(tim.width, tim.height, tim.indices(), colours, alpha, tim.bpp)


# --- export ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportSummary:
    out_dir: Path
    textures: int
    occurrences: int
    skipped: int
    """Distinct images left out by `--only-text`."""
    clut_fallbacks: int = 0
    """Images with fewer palettes than `--clut` asked for, rendered through CLUT 0.

    `index.json` records the palette each PNG was really exported through, so an import
    stays right either way; what this is for is the summary line, because an artist who
    asked for CLUT 3 and silently got CLUT 0 is editing colours the game never shows."""


def export(
    archive: Archive,
    out_dir: Path = DEFAULT_OUT_DIR,
    *,
    only_text: bool = False,
    clut: int = 0,
    census: Path = CENSUS_TSV,
    inv: Inventory | None = None,
) -> ExportSummary:
    """Write one PNG per distinct image plus `index.json` listing every occurrence."""
    out_dir = Path(out_dir)
    check_out_dir(out_dir, manifest_name=INDEX_NAME, what="texture export")
    inv = inv if inv is not None else inventory(archive)
    wanted = text_bearing_ids(census) if only_text else None
    chosen = [t for t in inv.textures if wanted is None or t.id in wanted]
    records = []
    fallbacks = 0
    with staged(out_dir, suffix="textures") as staging:
        for texture in chosen:
            page = clut if clut < (texture.tim.clut.count if texture.tim.clut else 1) else 0
            fallbacks += page != clut
            (staging / f"{texture.id}.png").write_bytes(to_png(texture.tim, page))
            records.append(_record(texture, page))
        index = {
            "format": FORMAT,
            "what": "textures exported from a contributor's own import, one PNG per distinct image",
            "only_text": only_text,
            "clut": clut,
            "textures": records,
        }
        (staging / INDEX_NAME).write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return ExportSummary(
        out_dir=out_dir,
        textures=len(chosen),
        occurrences=sum(t.copies for t in chosen),
        skipped=len(inv.textures) - len(chosen),
        clut_fallbacks=fallbacks,
    )


def _record(texture: Texture, clut: int) -> dict:
    tim = texture.tim
    return {
        "id": texture.id,
        "sha1": texture.sha1,
        "png": f"{texture.id}.png",
        "bpp": tim.bpp,
        "width": tim.width,
        "height": tim.height,
        "cluts": tim.clut.count if tim.clut else 0,
        "clut_colours": tim.clut.colours if tim.clut else 0,
        "clut_exported": clut,
        "pixel_origin": [tim.x, tim.y],
        "clut_origin": [tim.clut.x, tim.clut.y] if tim.clut else None,
        "copies": texture.copies,
        "occurrences": [
            {
                "file": o.file,
                "member": o.member,
                "offset": o.offset,
                "file_offset": o.file_offset,
                "size": o.length,
            }
            for o in texture.occurrences
        ],
    }


# --- import ------------------------------------------------------------------------------------


def patch_reason(texture_id: str, member: str) -> str:
    """What a texture patch calls itself in the build's manifest and in a refusal.

    The texture and the archive member both belong in it: a `verify_edits` failure over
    2,607 occurrences is unreadable without knowing which copy of which image it was.
    """
    return f"texture {texture_id} in {member}"


@dataclass(frozen=True)
class ImportResult:
    patches: tuple[ByteEdit, ...]
    """`boku.reinsert.ByteEdit`s — what `boku.build` verifies and writes, unadapted."""
    changed: tuple[str, ...]
    """Texture ids whose PNG differed from the disc."""
    unchanged: tuple[str, ...]
    quantisation: dict[str, Quantisation]
    """Only for textures that went through `--nearest`."""

    @property
    def bytes_changed(self) -> int:
        return sum(len(p.new) for p in self.patches)


def indices_for(
    texture: Texture, page: Png, clut: int = 0, *, nearest: bool = False
) -> tuple[bytes, Quantisation | None]:
    """The palette indices an edited PNG means for this texture, or a refusal saying why.

    An indexed PNG whose palette is the one we exported is taken at its indices, which is
    the only lossless path: two CLUT entries may hold the same colour, and going through
    colours would silently merge them. Anything else is matched by colour, exactly unless
    `nearest` was asked for.

    The palette's *length* decides nothing. A tool that re-saves a 16-colour 4bpp export
    as 8-bit indexed with 256 entries has changed nothing about the picture, and the
    depth an index has to fit is `Tim.with_indices`'s to enforce; what this looks at is
    whether the entries the pixels actually use are the CLUT's own.
    """
    tim = texture.tim
    if (page.width, page.height) != (tim.width, tim.height):
        raise TextureError(
            f"{texture.id} is {tim.width}x{tim.height} on the disc and the PNG is "
            f"{page.width}x{page.height}. The archive slot is the size it is; an edit "
            f"keeps the dimensions."
        )
    if page.is_indexed:
        colours, alpha = png_palette(tim, clut)
        shared = min(len(page.palette), len(colours))
        if (
            list(page.palette[:shared]) == colours[:shared]
            and list(page.alpha[:shared]) == alpha[:shared]
            and max(page.indices or b"", default=0) < shared
        ):
            return page.indices or b"", None
    if nearest:
        return nearest_tim_indices(tim, page.rgba, clut)
    return indices_from_rgba(tim, page.rgba, clut), None


def patches_for(texture: Texture, edited: Tim) -> list[ByteEdit]:
    """Every byte run that differs, at every occurrence of `texture`.

    Runs are maximal, so a one-pixel edit is one patch of one byte per occurrence, which
    is what makes the propagation gate mean something. The two serialisations are the
    same length by construction — `with_indices` rewrites pixel bytes and nothing else —
    and `_runs` pairs them strictly rather than trusting that.
    """
    old = texture.tim.serialise()
    new = edited.serialise()
    out = []
    for start, stop in _runs(old, new):
        for place in texture.occurrences:
            out.append(
                ByteEdit(
                    file=place.file,
                    offset=place.file_offset + start,
                    old=old[start:stop],
                    new=new[start:stop],
                    reason=patch_reason(texture.id, place.member),
                )
            )
    return out


def _runs(old: bytes, new: bytes) -> list[tuple[int, int]]:
    runs = []
    start = None
    for i, (a, b) in enumerate(zip(old, new, strict=True)):
        if a != b and start is None:
            start = i
        elif a == b and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(old)))
    return runs


def import_edits(
    archive: Archive,
    png_dir: Path,
    *,
    nearest: bool = False,
    inv: Inventory | None = None,
) -> ImportResult:
    """Read edited PNGs out of `png_dir` and return the patches they imply.

    Every `<id>.png` in the directory is taken as an edit of the texture that id names;
    `index.json` is read for the CLUT each was exported through, and a directory without
    one is read at CLUT 0. An unchanged PNG produces no patches at all, so running this
    over a fresh export is the cheapest possible check that the round trip is exact.
    """
    png_dir = Path(png_dir)
    if not png_dir.is_dir():
        raise TextureError(f"{png_dir} is not a directory")
    inv = inv if inv is not None else inventory(archive)
    known = inv.by_id()
    exported_clut = _exported_cluts(png_dir)
    patches: list[ByteEdit] = []
    changed: list[str] = []
    unchanged: list[str] = []
    reports: dict[str, Quantisation] = {}
    for path in sorted(png_dir.glob("*.png")):
        name = path.stem
        if name not in known:
            raise TextureError(
                f"{path.name} names no texture on this disc. Export writes the id a "
                f"texture is known by; renaming the file loses which bytes it belongs to."
            )
        texture = known[name]
        clut = exported_clut.get(name, 0)
        try:
            page = read_png(path.read_bytes())
        except PngError as exc:
            raise TextureError(f"{path.name}: {exc}") from None
        try:
            indices, report = indices_for(texture, page, clut, nearest=nearest)
            edited = texture.tim.with_indices(indices)
        except TimError as exc:  # OffPalette is one of these
            raise TextureError(f"{path.name}: {exc}") from None
        if report is not None and report.approximated:
            reports[name] = report
        if edited.serialise() == texture.tim.serialise():
            unchanged.append(name)
            continue
        changed.append(name)
        patches += patches_for(texture, edited)
    return ImportResult(tuple(patches), tuple(changed), tuple(unchanged), reports)


def _exported_cluts(png_dir: Path) -> dict[str, int]:
    index = png_dir / INDEX_NAME
    if not index.is_file():
        return {}
    try:
        loaded = json.loads(index.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TextureError(f"{index} is not readable JSON: {exc}") from None
    # A row without an `id` names no texture, so it says nothing about any PNG here;
    # a hand-edited index.json is a bad manifest, not a crash.
    return {
        t["id"]: t.get("clut_exported", 0)
        for t in loaded.get("textures", [])
        if isinstance(t, dict) and "id" in t
    }


# --- command line ---------------------------------------------------------------------------


REFUSALS = (TextureError, TimError, PngError, ArchiveError, StagingRefused, OSError)
"""What either verb can fail with. A command line says what went wrong; it does not
hand the contributor a traceback through the import they have not made yet."""


def main_export(disc_dir: Path, out_dir: Path, only_text: bool, clut: int) -> int:
    try:
        summary = export(Archive(disc_dir), out_dir, only_text=only_text, clut=clut)
    except REFUSALS as error:
        print(f"boku textures export: {error}")
        return 1
    print(
        f"{summary.textures} distinct textures ({summary.occurrences} occurrences) "
        f"-> {summary.out_dir}/"
        + (f", {summary.skipped} without text left out" if summary.skipped else "")
        + (
            f", {summary.clut_fallbacks} with fewer than {clut + 1} palettes rendered "
            f"through CLUT 0"
            if summary.clut_fallbacks
            else ""
        )
    )
    return 0


def main_import(disc_dir: Path, png_dir: Path, nearest: bool) -> int:
    try:
        result = import_edits(Archive(disc_dir), png_dir, nearest=nearest)
    except REFUSALS as error:
        print(f"boku textures import: {error}")
        return 1
    if not result.patches:
        print(f"{len(result.unchanged)} PNGs read, none differs from the disc: no patches")
        return 0
    places = len({(p.file, p.offset) for p in result.patches})
    print(
        f"{len(result.changed)} texture(s) edited -> {len(result.patches)} patches at "
        f"{places} places, {result.bytes_changed} bytes"
    )
    for edited_id in result.changed:
        mine = [p for p in result.patches if p.reason.startswith(patch_reason(edited_id, ""))]
        files = {p.file for p in mine}
        print(f"  {edited_id}: {len(mine)} patches in {', '.join(sorted(files))}")
        if edited_id in result.quantisation:
            print(f"    nearest-entry mapping: {result.quantisation[edited_id].describe()}")
    return 0
