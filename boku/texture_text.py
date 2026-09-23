"""English typeset into the game's textures at build time (PLAN `GFX-07`, the **P** path).

A programmatically translated texture is the original's pixels with English set into them,
so the image itself is never tracked (CLAUDE.md § "This repo is public"). What is tracked is
the English, keyed by string id in `translation/textures/*.txt`, and this module — the
geometry and the recipe — which rebuilds each image from the contributor's own import and
hands it to the image build as verified byte edits (`boku.textures.patches_for`).

A texture is handled by a *family*: the id before the last dot (`tex@T_TITLE`), mapped in
`FAMILIES` to the function that knows that image. A family takes all of its strings or none,
so a half-translated menu is refused rather than built, and an id no family owns is refused
rather than ignored — a translator's typo must not silently leave a texture in Japanese.
"""

from __future__ import annotations

import struct
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import ARCHIVE_NAME, Archive
from boku.reinsert import ByteEdit
from boku.textures import Inventory, inventory, patches_for
from boku.tim import Tim, luminance
from boku.typeset import CELL, FONT_SHEET_ID, Face, GameFace, TypesetError

TEXTURE_TEXT_DIR = REPO_ROOT / "translation/textures"


class TextureTextError(Exception):
    """A texture string that cannot be built: a malformed file, an unknown id, no room."""


# --- the tracked English -------------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    id: str
    text: str
    where: str
    """`file:line`, for a refusal to point at."""

    @property
    def family(self) -> str:
        return self.id.rsplit(".", 1)[0]


def read_entries(directory: Path = TEXTURE_TEXT_DIR) -> dict[str, Entry]:
    """Every `id<TAB>English` row of `directory/*.txt`. `#` lines and blank lines are notes."""
    directory = Path(directory)
    if not directory.is_dir():
        raise TextureTextError(f"{directory} is not a directory of texture strings")
    entries: dict[str, Entry] = {}
    for path in sorted(directory.glob("*.txt")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{path.name}:{number}"
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, tab, text = line.partition("\t")
            if not tab or not key or " " in key:
                raise TextureTextError(f"{where}: a row is `id<TAB>English`, not {line!r}")
            if not text.strip():
                raise TextureTextError(f"{where}: {key} has no English")
            if key in entries:
                raise TextureTextError(f"{where}: {key} is already given at {entries[key].where}")
            entries[key] = Entry(key, text.strip(), where)
    return entries


# --- drawing into palette indices ------------------------------------------------------------


def outlined(
    pixels: bytearray,
    width: int,
    box: tuple[int, int, int, int],
    ink: set[tuple[int, int]],
    fill: int,
    outline: int,
) -> None:
    """Set `ink` (box-relative) in `fill`, ringed on all eight sides in `outline`.

    Nothing outside `box` (x, y, w, h) is written; `set_line` is what refuses a line whose
    ring would not fit.
    """
    x0, y0, w, h = box
    ring = {
        (x + dx, y + dy) for x, y in ink for dx in (-1, 0, 1) for dy in (-1, 0, 1)
    } - ink  # fmt: skip
    for points, index in ((ring, outline), (ink, fill)):
        for x, y in points:
            if 0 <= x < w and 0 <= y < h:
                pixels[(y0 + y) * width + x0 + x] = index


def set_line(
    pixels: bytearray,
    width: int,
    box: tuple[int, int, int, int],
    entry: Entry,
    face: Face,
    fill: int,
    outline: int,
) -> None:
    """Set one line of `entry`'s English, outlined, with its ring's top-left at `box`'s.

    Refuses, naming the row, a character the face cannot draw and a line whose outlined
    ink does not fit the box -- nothing is cut to fit (README).
    """
    try:
        ink = face.ink(entry.text)
    except TypesetError as error:
        raise TextureTextError(f"{entry.where}: {error}") from None
    need_w, need_h = face.measure(entry.text) + 2, CELL + 2
    if need_w > box[2] or need_h > box[3]:
        raise TextureTextError(
            f"{entry.where}: {entry.text!r} needs {need_w}x{need_h} px with its outline and "
            f"its space holds {box[2]}x{box[3]}; nothing is cut to fit (README)"
        )
    outlined(pixels, width, box, {(x + 1, y + 1) for x, y in ink}, fill, outline)


def ink_roles(tim: Tim, region: list[tuple[int, int]], blank: int) -> tuple[int, int]:
    """The (outline, fill) entries outlined type in `region` is drawn in: the two most-used
    entries other than `blank`, the paler (CLUT 0) being the outline."""
    used = Counter(tim.indices()[y * tim.width + x] for x, y in region)
    ranked = [index for index, _ in used.most_common() if index != blank]
    if len(ranked) < 2:
        raise TextureTextError("the region carries no outlined type to match")
    outline, fill = ranked[0], ranked[1]
    palette = tim.palette_rgba(0)
    if luminance(palette[outline]) <= luminance(palette[fill]):
        raise TextureTextError(
            f"the most-used entry ({outline}) should be the outline, paler than its fill "
            f"({fill}), and it is not; the recipe would invert them"
        )
    return outline, fill


# --- T_TITLE: the title menu ----------------------------------------------------------------


TITLE_ATLAS = "_DATA_T_TITLE.BIN__000014"
"""248x198 8bpp, 4 CLUTs: the menu, the copyright line, PRESS START and the logo."""
TITLE_OVERLAY = "TITLE.OVL"
TITLE_MENU_RECORDS = (0x80081814, 0x80079DD8, 0x80079DF0, 0x80079E08)
"""The four menu lines' sprite records in `TITLE.OVL`, top to bottom (`research/texture-recipes.md`
§ "`T_TITLE`"): 0x18 bytes each, the u16 at +8 the sprite's width."""
TITLE_RECORD_WIDTH = 8
TITLE_HIGHLIGHT_WIDTH = 0x8007F85C
"""`addiu $a1, $zero, 0x54`: the width of the selected line's highlight sprite."""
RETAIL_MENU_WIDTH = 0x54
"""84 px: the Japanese lines are seven 12 px glyphs wide."""
MENU_WIDTH = 128
"""What the build widens each line to: the atlas is transparent from x 84 to 127 over the
menu's rows, and the (TM) sprite starts at x 128."""
MENU_BAND = 16
MENU_LINES = 4
MENU_INK_TOP = 1
"""Band row of the glyph cell's top row: capitals ink band rows 2-10, their outline 1-11."""


def _addiu_a1(immediate: int) -> bytes:
    return struct.pack("<I", 0x24050000 | immediate)


def title_menu(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """Typeset the four title-menu lines and widen their sprites to fit English."""
    by_line = {e.id.rsplit(".", 1)[1]: e for e in entries}
    if len(by_line) != len(entries) or set(by_line) != {str(i) for i in range(MENU_LINES)}:
        ids = ", ".join(sorted(e.id for e in entries))
        raise TextureTextError(
            f"tex@T_TITLE takes exactly .0-.{MENU_LINES - 1}, one per menu line; given {ids}"
        )
    texture = inv.get(TITLE_ATLAS)
    tim = texture.tim
    width = tim.width
    pixels = bytearray(tim.indices())
    menu = [(x, y) for y in range(MENU_BAND * MENU_LINES) for x in range(MENU_WIDTH)]
    transparent = pixels[0]
    spare = {pixels[y * width + x] for x, y in menu if x >= RETAIL_MENU_WIDTH}
    if spare != {transparent} or tim.palette_rgba(0)[transparent][3] != 0:
        raise TextureTextError(
            f"{TITLE_ATLAS} is not the atlas this recipe was measured on: x "
            f"{RETAIL_MENU_WIDTH}-{MENU_WIDTH - 1} of the menu rows should be transparent"
        )
    try:
        outline, fill = ink_roles(tim, menu, transparent)
    except TextureTextError as error:
        raise TextureTextError(f"{TITLE_ATLAS}'s menu: {error}") from None

    for line in range(MENU_LINES):
        top = line * MENU_BAND
        for y in range(top, top + MENU_BAND):
            pixels[y * width : y * width + MENU_WIDTH] = bytes([transparent]) * MENU_WIDTH
        box = (0, top + MENU_INK_TOP - 1, MENU_WIDTH, MENU_BAND - MENU_INK_TOP + 1)
        set_line(pixels, width, box, by_line[str(line)], face, fill, outline)

    edits = patches_for(texture, tim.with_indices(bytes(pixels)))
    reason = "GFX-07: the title menu's sprites widened for English"
    for record in TITLE_MENU_RECORDS:
        edits.append(
            ByteEdit(
                ARCHIVE_NAME,
                archive.overlay_offset(TITLE_OVERLAY, record + TITLE_RECORD_WIDTH),
                struct.pack("<H", RETAIL_MENU_WIDTH),
                struct.pack("<H", MENU_WIDTH),
                reason,
            )
        )
    edits.append(
        ByteEdit(
            ARCHIVE_NAME,
            archive.overlay_offset(TITLE_OVERLAY, TITLE_HIGHLIGHT_WIDTH),
            _addiu_a1(RETAIL_MENU_WIDTH),
            _addiu_a1(MENU_WIDTH),
            reason,
        )
    )
    return edits


# --- the build's entry point ---------------------------------------------------------------


Family = Callable[[Archive, Inventory, Face, Sequence[Entry]], list[ByteEdit]]

FAMILIES: Mapping[str, Family] = {
    "tex@T_TITLE": title_menu,
}


@dataclass(frozen=True)
class TextureEdits:
    edits: tuple[ByteEdit, ...]
    families: tuple[str, ...]
    """The families built, in `FAMILIES` order."""


def build_edits(
    archive: Archive,
    directory: Path = TEXTURE_TEXT_DIR,
    *,
    inv: Inventory | None = None,
) -> TextureEdits:
    """Every texture edit the tracked English implies, against this import."""
    entries = read_entries(directory)
    grouped: dict[str, list[Entry]] = {}
    for entry in entries.values():
        if entry.family not in FAMILIES:
            raise TextureTextError(
                f"{entry.where}: no texture recipe builds {entry.family} "
                f"(boku.texture_text.FAMILIES); the string would be ignored"
            )
        grouped.setdefault(entry.family, []).append(entry)
    if not grouped:
        return TextureEdits((), ())
    inv = inv if inv is not None else inventory(archive)
    face = GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim)
    edits: list[ByteEdit] = []
    built = []
    for name, family in FAMILIES.items():
        if name in grouped:
            edits += family(archive, inv, face, grouped[name])
            built.append(name)
    return TextureEdits(tuple(edits), tuple(built))


__all__ = [
    "FAMILIES",
    "TEXTURE_TEXT_DIR",
    "Entry",
    "TextureEdits",
    "TextureTextError",
    "build_edits",
    "ink_roles",
    "outlined",
    "read_entries",
    "set_line",
    "title_menu",
]
