"""English typeset into the game's textures at build time (PLAN `GFX-07`, the **P** path).

A programmatically translated texture is the original's pixels with English set into them,
so the image itself is never tracked (CLAUDE.md § "This repo is public"). What is tracked is
the English, keyed by string id in `translation/textures/*.txt`, and this module — the
geometry and the recipe — which rebuilds each image from the contributor's own import and
hands it to the image build as verified byte edits (`boku.textures.patches_for`).

A texture is handled by a *family*, mapped in `FAMILIES` to the function that knows it: the
id before the last dot for a single texture's strings (`tex@T_TITLE`), or the namespace of a
bulk family whose ids name a page (`nikki@` for `nikki@NIKKI_072`, keyed so in `FAMILIES`). A
single texture takes all of its strings or none, so a half-translated menu is refused rather
than built; a bulk family builds the pages it is given, since its entries are translated a
few at a time. An id no family owns is refused rather than ignored -- a translator's typo
must not silently leave a texture in Japanese.
"""

from __future__ import annotations

import struct
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from boku import REPO_ROOT
from boku import diary as diary_mod
from boku import texture_paint as paint
from boku.archive import ARCHIVE_NAME, Archive
from boku.reinsert import ByteEdit
from boku.textures import Inventory, Texture, inventory, patches_for, to_png
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
        """`tex@T_TITLE` for `tex@T_TITLE.0`; a bulk family is its namespace (`mzkan@`)."""
        namespace = self.id.split("@", 1)[0] + "@"
        return namespace if namespace in FAMILIES else self.id.rsplit(".", 1)[0]


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


# --- shared by the recipes below -------------------------------------------------------------


def keyed(family: str, entries: Sequence[Entry], names: Sequence[str]) -> dict[str, Entry]:
    """`entries` by the part of the id after the family, refusing a missing or extra key."""
    by_key = {e.id.rsplit(".", 1)[1]: e for e in entries}
    if len(by_key) != len(entries) or set(by_key) != set(names):
        ids = ", ".join(sorted(e.id for e in entries))
        raise TextureTextError(f"{family} takes exactly .{', .'.join(names)}; given {ids}")
    return by_key


LINE_BREAK = " // "
"""Splits a string into lines -- honoured only where a recipe says so (`lines_of`)."""


def ink_of(face: Face, entry: Entry, text: str | None = None) -> paint.Ink:
    """The ink of `entry`'s English (or of `text`, one of its lines), refusals named."""
    if text is None and LINE_BREAK in entry.text:
        raise TextureTextError(
            f"{entry.where}: {entry.id} is set on one line; `{LINE_BREAK.strip()}` would be "
            f"drawn as slashes"
        )
    try:
        return face.ink(entry.text if text is None else text)
    except TypesetError as error:
        raise TextureTextError(f"{entry.where}: {error}") from None


def lines_of(entry: Entry) -> list[str]:
    return entry.text.split(LINE_BREAK)


def found(mask: paint.Ink, what: str) -> paint.Ink:
    """`mask`, refused when empty: the image is not the one the recipe was measured on."""
    if not mask:
        raise TextureTextError(
            f"{what}: no type where the recipe measured it -- a different "
            f"revision of the image, or a wrong CLUT"
        )
    return mask


def painted_out(
    canvas: paint.Canvas, box: paint.Box, mask: paint.Ink, *, avoid: paint.Ink = frozenset(),
    what: str,
) -> None:  # fmt: skip
    """`Canvas.paint_out`, refused -- naming `what` -- if any Japanese pixel is left."""
    left = canvas.paint_out(box, mask, avoid=avoid)
    if left:
        raise TextureTextError(
            f"{what}: {len(left)} pixel(s) of Japanese had no clean pixel "
            f"to be painted out from, first {sorted(left)[:3]}"
        )


def filled_from_nearest(
    canvas: paint.Canvas, mask: paint.Ink, donors: paint.Ink, *, what: str, reach: int = 8,
    parity: bool = False,
) -> None:  # fmt: skip
    """`Canvas.fill_from_nearest`, refused -- naming `what` -- if any pixel had no donor."""
    left = canvas.fill_from_nearest(mask, donors, reach=reach, parity=parity)
    if left:
        raise TextureTextError(
            f"{what}: {len(left)} pixel(s) had nothing near to be refilled from, first {left[:3]}"
        )


def rows_of(mask: paint.Ink) -> list[paint.Box]:
    """The boxes of `mask`'s lines: runs of rows that carry ink, split at empty rows."""
    ys = sorted({y for _, y in mask})
    runs: list[list[int]] = []
    for y in ys:
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    return [paint.extent({p for p in mask if run[0] <= p[1] <= run[-1]}) for run in runs]


def fits(entry: Entry, ink: paint.Ink, room: paint.Box, where: str) -> None:
    _, _, w, h = paint.extent(ink)
    if w > room[2] or h > room[3]:
        raise TextureTextError(
            f"{entry.where}: {entry.text!r} is {w}x{h} px and {where} holds {room[2]}x"
            f"{room[3]}; nothing is cut to fit (README)"
        )


def stacked(inks: Sequence[paint.Ink], gap: int) -> paint.Ink:
    """Already-drawn `inks` one under another, `gap` rows apart, each centred on the widest."""
    inks = [paint.normalised(ink) for ink in inks]
    widest = max(paint.extent(ink)[2] for ink in inks)
    out: paint.Ink = set()
    y = 0
    for ink in inks:
        _, _, w, h = paint.extent(ink)
        out |= {(x + (widest - w) // 2, dy + y) for x, dy in ink}
        y += h + gap
    return out


def centred(ink: paint.Ink, on: paint.Box) -> tuple[int, int]:
    """Where to stamp normalised `ink` so its extent is centred on box `on`."""
    _, _, w, h = paint.extent(ink)
    return on[0] + (on[2] - w) // 2, on[1] + (on[3] - h) // 2


def erase_type(
    canvas: paint.Canvas, clut: int, box: paint.Box, kind: str, *, grow=(1, 1, 1, 1),
    avoid: paint.Ink = frozenset(), what: str,
) -> tuple[paint.Ink, int]:  # fmt: skip
    """Find the Japanese type in `box` (`kind` "pale" or "dark", through `clut`), paint it
    out grown by `grow` (left, up, right, down), and return its pixels and the entry it was
    drawn in most -- the entry the English is set in."""
    mask = found(canvas.type_mask(kind, clut, box) - avoid, what)
    ink_index = canvas.most_used(mask)
    painted_out(canvas, box, paint.grown(mask, *grow) - avoid, avoid=avoid, what=what)
    return mask, ink_index


NOTE_GAP = 3
"""Rows (or, turned, columns) of air between stacked lines' ink."""


def flat_plaque(
    canvas: paint.Canvas, clut: int, box: paint.Box, entry: Entry, face: Face, what: str,
    *, lines: bool = False,
) -> None:  # fmt: skip
    """Dark type on a flat pale plaque: refill the Japanese's own rectangle, grown by two
    pixels to take its antialiasing, with the plaque's ground, and set the English centred in
    the dark entry the Japanese used. Only that rectangle is refilled, so any detail in the
    plaque's corners survives. `lines` lets ` // ` break the English."""
    japanese = found(canvas.type_mask("dark", clut, box), what)
    dark, ground = canvas.most_used(japanese), canvas.most_used(paint.points(box))
    jx, jy, jw, jh = paint.extent(japanese)
    left, top = max(box[0], jx - 2), max(box[1], jy - 2)
    right = min(box[0] + box[2], jx + jw + 2)
    bottom = min(box[1] + box[3], jy + jh + 2)
    canvas.fill((left, top, right - left, bottom - top), ground)
    inks = [ink_of(face, entry, line) for line in (lines_of(entry) if lines else [None])]
    ink = stacked(inks, NOTE_GAP)
    fits(entry, ink, box, what)
    canvas.stamp(centred(ink, box), ink, dark)


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
    ring = paint.grown(ink, 1, 1, 1, 1) - ink
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
    ink = ink_of(face, entry)
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
    by_line = keyed("tex@T_TITLE", entries, [str(i) for i in range(MENU_LINES)])
    texture = inv.get(TITLE_ATLAS)
    tim = texture.tim
    width = tim.width
    pixels = bytearray(tim.indices())
    menu = paint.points((0, 0, MENU_WIDTH, MENU_BAND * MENU_LINES))
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


# --- T_CONFIG: the settings screen -----------------------------------------------------------


CONFIG_FRAME = "_DATA_T_CONFIG.BIN__000014"
"""Child 0: the frame, the heading plaque, the back button, the sound plate, `OFF`."""
CONFIG_PLATES = "_DATA_T_CONFIG.BIN__017234"
"""Child 1: the message plate, the `ON`/`OFF` plate, the controller chart, the value labels."""

CONFIG_HEADING, HEADING_CLUT = (64, 164, 50, 30), 2
"""The heading plaque's flat interior."""
MESSAGE_PLATE, MESSAGE_CLUT = (0, 0, 128, 146), 7
"""Radial plate naming both message modes small, drawn at screen (168, 28)."""
SOUND_PLATE, SOUND_CLUT = (256, 0, 128, 146), 1
"""The same for stereo and mono, in child 0."""
CHART_HEAD, CHART_CLUT = (256, 0, 128, 66), 5
"""The controller chart's four column headings; row 66 is the rule under them."""
CHART_KEYS = ("action", "cancel", "run", "sub_screen")
"""The chart's columns, left to right."""
VALUE_CLUT = 3
VALUE_LABELS = {
    "voice_text": (96, 148, 107, 45),
    "voice_only": (0, 148, 96, 48),
    "stereo": (96, 196, 96, 32),
    "mono": (0, 196, 96, 32),
}
"""The selected value, drawn large and opaque over its small twin on the plate
(`VALUE_CLUT`), each at the size of its sprite record in `TITLE.OVL`."""
VALUE_NOTES = {"voice_text": "voice_text_note", "voice_only": "voice_only_note"}
"""The values that carry a note under them, set 1x."""
SHADOW = 2
"""The large values' drop shadow: the ink repeated 1 and 2 px down-right."""
CONFIG_KEYS = (
    "heading", *VALUE_LABELS, *VALUE_NOTES.values(), *CHART_KEYS,
)  # fmt: skip


def large(face: Face, entry: Entry, room: paint.Box) -> paint.Ink:
    """`entry` at 2x if that fits `room`, else 1x bold: the emphasis the Japanese large type
    has, as far as the room allows."""
    ink = ink_of(face, entry)
    _, _, w, h = paint.extent(ink)
    return paint.scaled(ink, 2) if 2 * w <= room[2] and 2 * h <= room[3] else paint.bold(ink)


def _small_labels(canvas, clut, plate, labels, face, where) -> None:
    """Paint out the plate's two small labels and set the English in their place: `labels`
    is (upper, lower), each the entries of its lines, set on the rows the Japanese used and
    centred on the plate."""
    mask, white = erase_type(canvas, clut, plate, "pale", what=where)
    middle = plate[1] + plate[3] // 2
    groups = [{p for p in mask if p[1] < middle}, {p for p in mask if p[1] >= middle}]
    placed: list[tuple[Entry, int]] = []
    for group, lines in zip(groups, labels, strict=True):
        rows = rows_of(group)
        if len(rows) != len(lines):
            raise TextureTextError(
                f"{where}: {len(rows)} lines of Japanese where {len(lines)} were measured"
            )
        for entry, row in zip(lines, rows, strict=True):
            ink = paint.normalised(ink_of(face, entry))
            fits(entry, ink, plate, where)
            top, bottom = row[1], row[1] + paint.extent(ink)[3]
            if bottom > plate[1] + plate[3] or (placed and top < placed[-1][1]):
                into = "its edge" if bottom > plate[1] + plate[3] else placed[-1][0].id
                raise TextureTextError(
                    f"{entry.where}: {entry.text!r} set at rows {top}-{bottom - 1} of {where} "
                    f"would run into {into}"
                )
            placed.append((entry, bottom))
            canvas.stamp((centred(ink, plate)[0], top), ink, white)


def chart_rules(head: paint.Ink) -> paint.Ink:
    """The chart's vertical rules among its pale pixels: the columns pale down more than half
    the heading rows (a rule is dithered, so not every row)."""
    per_column = Counter(x for x, _ in head)
    return {p for p in head if per_column[p[0]] > CHART_HEAD[3] // 2}


def config_screen(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """The settings screen's heading, value plates, value labels and controller chart."""
    text = keyed("tex@T_CONFIG", entries, CONFIG_KEYS)
    frame, plates = paint.Canvas(inv.get(CONFIG_FRAME)), paint.Canvas(inv.get(CONFIG_PLATES))

    flat_plaque(frame, HEADING_CLUT, CONFIG_HEADING, text["heading"], face, "the heading")

    # the two plates that name both values small
    _small_labels(
        plates, MESSAGE_CLUT, MESSAGE_PLATE,
        (
            [text["voice_text"], text[VALUE_NOTES["voice_text"]]],
            [text["voice_only"], text[VALUE_NOTES["voice_only"]]],
        ),
        face, "the message plate",
    )  # fmt: skip
    _small_labels(
        frame, SOUND_CLUT, SOUND_PLATE, ([text["stereo"]], [text["mono"]]), face,
        "the sound plate",
    )  # fmt: skip

    # the selected value, large, with a drop shadow
    palette = plates.palette(VALUE_CLUT)
    for key, cell in VALUE_LABELS.items():
        what = f"the {key} label"
        pale, white = erase_type(plates, VALUE_CLUT, cell, "pale", grow=(1, 1, 3, 3), what=what)
        shadow_area = (paint.grown(pale, 0, 0, 3, 3) - pale) & set(paint.points(cell))
        darkest = min((plates.at(p) for p in shadow_area), key=lambda i: luminance(palette[i]))
        inner = (cell[0], cell[1], cell[2] - SHADOW, cell[3] - SHADOW)
        note = VALUE_NOTES.get(key)
        room = (0, 0, inner[2], inner[3] - (face.pitch if note else 0))
        inks = [large(face, text[key], room)]
        if note:
            inks.append(ink_of(face, text[note]))
        block = stacked(inks, NOTE_GAP)
        fits(text[key], block, inner, what)
        x, y = centred(block, inner)
        for depth in range(SHADOW, 0, -1):
            plates.stamp((x + depth, y + depth), block, darkest)
        plates.stamp((x, y), block, white)

    # the controller chart: one heading per column, set top to bottom
    rules = chart_rules(found(plates.type_mask("pale", CHART_CLUT, CHART_HEAD), "the chart"))
    labels, white = erase_type(plates, CHART_CLUT, CHART_HEAD, "pale", avoid=rules,
                               what="the chart")  # fmt: skip
    edges = [CHART_HEAD[0] - 1, *sorted({x for x, _ in rules}), CHART_HEAD[0] + CHART_HEAD[2]]
    if len(edges) - 1 != len(CHART_KEYS):
        raise TextureTextError(
            f"{CONFIG_PLATES}'s chart has {len(edges) - 1} columns, not {len(CHART_KEYS)}"
        )
    for key, (left, right) in zip(CHART_KEYS, pairwise(edges), strict=True):
        entry = text[key]
        room = (left + 1, CHART_HEAD[1], right - left - 1, CHART_HEAD[3] - 1)
        lines = [ink_of(face, entry, line) for line in lines_of(entry)]
        ink = paint.normalised(paint.rotated_cw(stacked(lines, NOTE_GAP)))
        fits(entry, ink, (0, 0, room[2] - 2, room[3] - 2), f"the {key} column")
        _, _, w, h = paint.extent(ink)
        jp = {p for p in labels if left < p[0] < right}
        if jp:
            _, jp_top, _, jp_h = paint.extent(jp)
            bottom = jp_top + jp_h
        else:
            bottom = room[1] + room[3] - 1
        y = max(room[1] + 1, min(bottom, room[1] + room[3] - 1) - h)
        plates.stamp((room[0] + (room[2] - w) // 2, y), ink, white)

    return frame.patches() + plates.patches()


# --- T_MEMORY: the "summer memories" album -----------------------------------------------------


MEMORY_ALBUM = "_DATA_T_MEMORY.BIN__00d634"
"""640x202, 6 CLUTs: five filmstrip miniatures (they stay) and the heading plaque."""
MEMORY_HEADING, MEMORY_CLUT = (16, 158, 99, 30), 0
"""The heading plaque's flat interior. The Japanese is one line of seven glyphs; the
English is two (`Summer // Memories`), 107 px on one line against 99."""


def memory_album(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """The album's heading plaque. The menu labels under it are renderer text (`TXT-05`)."""
    text = keyed("tex@T_MEMORY", entries, ["heading"])
    album = paint.Canvas(inv.get(MEMORY_ALBUM))
    flat_plaque(album, MEMORY_CLUT, MEMORY_HEADING, text["heading"], face,
                "the album heading", lines=True)  # fmt: skip
    return album.patches()


# --- marker signs: hand-lettered in coloured marker on a flat ground (GFX-08) ---------------


@dataclass(frozen=True)
class MarkerSign:
    texture: str
    clut: int
    box: paint.Box
    """Where the marker lettering is found and painted out."""
    room: paint.Box
    """Where the English may go; it is set centred on it."""
    scales: tuple[int, ...]
    """Each line's scale over the game's glyphs; the English has exactly this many lines."""


MARKER = 30
"""How much redder (red minus green) than the box's median ground a pixel is to be the marker:
the pink on the white sign is ~58 over it, and the tan cover's own noise ~25 at most."""
MARKER_REACH = 2
"""The marker's antialias and dark shading lie within this many pixels of it (the notebook's
under the 虫's middle stroke, two rows down); they are painted out with it."""
DONOR_DARK = 125
"""Luminance under which a pixel that is not the marker is dark: the notebook frame's lighter
pixels reach ~124, its tan ground's darkest ~131."""

MARKER_SIGNS: dict[str, MarkerSign] = {
    # The keep-out sign on the upstairs door (the close-up in `E0835`; `M_I18000` and
    # `M_I18001` hold the same image): pink marker across a white oval.
    "M_I18": MarkerSign(
        "_DATA_M_FILES.BIN_M_I18000.BIN__000450", 0, (96, 90, 122, 40), (100, 76, 112, 72), (2, 2)
    ),
    # The bug-trading notebook's cover on the bug-sumo desk: red marker inside the cover's
    # frame, the first line large as the Japanese's 虫 is.
    "M_S01000": MarkerSign(
        "_DATA_M_S01000.BIN__017d24", 3, (297, 10, 78, 93), (300, 13, 70, 86), (2, 1, 1)
    ),
}


def paint_marker_sign(
    canvas: paint.Canvas, sign: MarkerSign, entry: Entry, face: Face, what: str
) -> None:
    """Paint the marker lettering and its shading out of its ground and set the English's
    lines, each at its scale, stacked and centred on the room, in the marker's own entry."""
    lines = lines_of(entry)
    if len(lines) != len(sign.scales):
        raise TextureTextError(
            f"{entry.where}: {what} is set on {len(sign.scales)} lines (` // ` between them)"
        )
    points = set(paint.points(sign.box))
    colour = {p: canvas.colour(sign.clut, p, stock=True) for p in points}
    red = {p: c[0] - c[1] for p, c in colour.items()}
    ground = sorted(red.values())[len(red) // 2]
    marker = found({p for p in points if red[p] - ground >= MARKER}, what)
    ink_index = canvas.most_used(marker, stock=True)
    dark = {p for p in points if luminance(colour[p]) < DONOR_DARK} - marker
    near = paint.grown(marker, *(MARKER_REACH,) * 4)
    # A dark group reaching beyond the marker's reach is a line of the picture (the cover's
    # frame, broken by lighter texels into short runs): never painted out, and neither it nor
    # its pale edge (the frame is two texels wide, one pale brown) refills anything.
    rules = {p for group in paint.groups(dark) if group - near for p in group}
    mask = (near & points) - rules
    donors = points - mask - paint.grown(rules, 1, 1, 1, 1)
    filled_from_nearest(canvas, mask, donors, reach=12, what=what)
    inks = [paint.scaled(ink_of(face, entry, line), n)
            for line, n in zip(lines, sign.scales, strict=True)]  # fmt: skip
    ink = stacked(inks, NOTE_GAP)
    fits(entry, ink, sign.room, what)
    canvas.stamp(centred(ink, sign.room), ink, ink_index)


def marker_sign(name: str, sign: MarkerSign) -> Family:
    def family(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
        entry = keyed(f"tex@{name}", entries, ["0"])["0"]
        canvas = paint.Canvas(inv.get(sign.texture))
        paint_marker_sign(canvas, sign, entry, face, f"the {name} sign")
        return canvas.patches()

    return family


# --- M_C15: the notice board on the path to the beach --------------------------------------


BEACH_BACKGROUNDS = (
    "_DATA_M_FILES.BIN_M_C15000.BIN__00305c",
    "_DATA_M_FILES.BIN_M_C15100.BIN__00305c",
)
"""The map's two variants' background atlases, 490x252 8bpp, 8 CLUTs each: the same scene
in two lightings (different indices and palettes), the board in the top-right corner of
both at the same place. `C15000` is the one day 1 loads."""
BEACH_CLUT = 5
"""The CLUT the board is drawn in (the others colour other regions of the atlas)."""
BEACH_VISIBLE = 489
"""The first atlas column the screen does not show: the board runs off the screen there, and
the English must end before it (Jay, 2026-09-24: the wording fits the visible part). The
column itself is another region's, transparent through the board's CLUT -- no line box
reaches it, so nothing is refilled from it."""
BEACH_LINES = ((387, 18, BEACH_VISIBLE - 387, 30), (334, 50, BEACH_VISIBLE - 334, 28))
"""The two painted lines' rows on the board, to the last column on screen. The first starts a
column clear of the painted bird and wave on its left (their last column is x 385), which
stay."""
BEACH_SCALE = 2
"""The Japanese is painted about 22 px high with 2 px strokes: the game's glyphs doubled."""


def beach_notice(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """Paint the notice's Japanese out of the wood and paint the English in its place."""
    text = keyed("tex@M_C15", entries, [str(i) for i in range(len(BEACH_LINES))])
    inks = [
        paint.normalised(paint.scaled(ink_of(face, text[str(n)]), BEACH_SCALE))
        for n in range(len(BEACH_LINES))
    ]
    edits: list[ByteEdit] = []
    for texture_id in BEACH_BACKGROUNDS:
        board = paint.Canvas(inv.get(texture_id))
        for n, (box, ink) in enumerate(zip(BEACH_LINES, inks, strict=True)):
            entry = text[str(n)]
            what = f"line {n} of the beach notice in {texture_id}"
            japanese, white = erase_type(board, BEACH_CLUT, box, "pale", what=what)
            jx, jy, _, jh = paint.extent(japanese)
            _, _, w, h = paint.extent(ink)
            at = (min(jx, box[0] + box[2] - w), jy + (jh - h) // 2)
            if at[0] < box[0]:
                raise TextureTextError(
                    f"{entry.where}: {entry.text!r} is {w} px wide at {BEACH_SCALE}x and "
                    f"{what} shows {box[2]} px on screen; nothing is cut to fit"
                )
            if at[1] < box[1] or at[1] + h > box[1] + box[3]:
                raise TextureTextError(
                    f"{entry.where}: {entry.text!r} is {h} px tall at {BEACH_SCALE}x and "
                    f"{what} has rows {box[1]}-{box[1] + box[3] - 1}; nothing is cut to fit"
                )
            board.stamp(at, ink, white)
        edits += board.patches()
    return edits


# --- OTI0n: the epilogue's closing card ---------------------------------------------------------


CREDITS_STRIP = "_DATA_OTI00.BIN__0261f4"
"""276x33 4bpp: the two-line production and copyright card `ENDOTI` shows on black after its
stills (`research/texture-recipes.md` § `OTI0n`); the same TIM in each of `OTI00`-`OTI04`."""
CREDITS_LINES = (("production", (0, 0, 276, 12)), ("company", (0, 20, 276, 12)))
"""Each line's key and its rows: pale grey type on transparent, a line of glyphs each."""


def credits_strip(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """Clear the card to transparent and set each English line, in the game's glyphs, centred
    on the rows the Japanese line used, in the entry the Japanese's pale core (within
    `CORE_SPREAD` of its palest) used most."""
    text = keyed("tex@OTI", entries, [key for key, _ in CREDITS_LINES])
    card = paint.Canvas(inv.get(CREDITS_STRIP))
    palette = card.palette(0)
    transparent = next(i for i, c in enumerate(palette) if not c[3])
    placed = []
    for key, box in CREDITS_LINES:
        what = f"the {key} line of the credits card"
        grey = {p: luminance(palette[card.at(p, stock=True)]) for p in paint.points(box)
                if palette[card.at(p, stock=True)][3]}  # fmt: skip
        found(set(grey), what)
        core = [p for p, v in grey.items() if v >= max(grey.values()) - CORE_SPREAD]
        ink = paint.normalised(ink_of(face, text[key]))
        fits(text[key], ink, box, what)
        placed.append((centred(ink, (0, box[1], card.width, box[3])), ink,
                       card.most_used(core, stock=True)))  # fmt: skip
    card.fill((0, 0, card.width, card.height), transparent)
    for at, ink, index in placed:
        card.stamp(at, ink, index)
    return card.patches()


CORE_SPREAD = 40
"""The credits type's own grey: within this much luminance of its palest pixel."""


# --- NIKKI: the picture diary --------------------------------------------------------------------


def diary(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """Each entry's page, re-measured on this import and redrawn with its English."""
    pages = diary_mod.diary_pages(inv)
    edits: list[ByteEdit] = []
    problems: list[str] = []
    for entry in sorted(entries, key=lambda e: e.id):
        try:
            edits += _diary_page(pages, entry, face)
        except TextureTextError as error:
            problems.append(str(error))
    if problems:
        raise TextureTextError(
            f"{len(problems)} diary page(s) refused:\n  " + "\n  ".join(problems)
        )
    return edits


def _diary_page(pages: dict[str, Texture], entry: Entry, face: Face) -> list[ByteEdit]:
    page = entry.id.split("@", 1)[1]
    number = page.removeprefix("NIKKI_")
    if number == diary_mod.DUMMY_PAGE:
        raise TextureTextError(
            f"{entry.where}: {page} is the unused dummy page -- no day shows it, so it "
            f"gets no entry"
        )
    if page == number or number not in pages:
        raise TextureTextError(f"{entry.where}: there is no diary page {page}")
    texture = pages[number]
    measured = diary_mod.measure_page(texture)
    notes = measured.notes
    if notes:
        raise TextureTextError(
            f"{entry.where}: {page}'s panel is not the one the diary recipe was measured "
            f"on -- {'; '.join(notes)}"
        )
    if LINE_BREAK in entry.text:
        raise TextureTextError(
            f"{entry.where}: a diary entry is one paragraph; `{LINE_BREAK.strip()}` would be "
            f"drawn as slashes"
        )
    width = diary_mod.PANEL.text_width
    for word in entry.text.split():
        if face.measure(word) > width:
            raise TextureTextError(
                f"{entry.where}: {word!r} is {face.measure(word)} px, wider than a line of "
                f"the page ({width}); nothing is cut to fit (README)"
            )
    redrawn = diary_mod.redraw_page(texture, entry.text, face, colours=measured.colours)
    if redrawn.missing:
        raise TextureTextError(
            f"{entry.where}: the game's glyph sheet has no drawing for {''.join(redrawn.missing)!r}"
        )
    if redrawn.overflow:
        lines = len(redrawn.lines) + len(redrawn.overflow)
        raise TextureTextError(
            f"{entry.where}: {page}'s entry wraps to {lines} lines and the page holds "
            f"{len(redrawn.lines)}; nothing is cut to fit (README)"
        )
    return patches_for(texture, redrawn.tim)


# --- the build's entry point ---------------------------------------------------------------


Family = Callable[[Archive, Inventory, Face, Sequence[Entry]], list[ByteEdit]]


def buttons(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """The stone and balloon buttons (`boku.texture_buttons`, which builds on this module)."""
    from boku import texture_buttons

    return texture_buttons.buttons(archive, inv, face, entries)


def insect_book(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """The insect book's spreads (`boku.texture_books`)."""
    from boku import texture_books

    return texture_books.insect_book(archive, inv, face, entries)


def kite_book(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """The kite book's spreads (`boku.texture_books`)."""
    from boku import texture_books

    return texture_books.kite_book(archive, inv, face, entries)


def records(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """Labels beside run-time numbers (`boku.texture_records`)."""
    from boku import texture_records

    return texture_records.records(archive, inv, face, entries)


def sumo_bout(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """Bug sumo's stamina plate, rank marks and winning-move banner (`boku.texture_sumo`)."""
    from boku import texture_sumo

    return texture_sumo.sumo(archive, inv, face, entries)


def closeup_note(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """Saori's farewell note (`boku.texture_closeups`)."""
    from boku import texture_closeups

    return texture_closeups.note(archive, inv, face, entries)


def closeup_board(archive: Archive, inv: Inventory, face: Face, entries: Sequence[Entry]):
    """The hunting association's warning board (`boku.texture_closeups`)."""
    from boku import texture_closeups

    return texture_closeups.board(archive, inv, face, entries)


FAMILIES: Mapping[str, Family] = {
    "tex@T_TITLE": title_menu,
    "tex@T_CONFIG": config_screen,
    "tex@T_MEMORY": memory_album,
    "tex@M_C15": beach_notice,
    "tex@M_I14000": closeup_note,
    **{f"tex@{name}": marker_sign(name, sign) for name, sign in MARKER_SIGNS.items()},
    "tex@M_I23000": closeup_board,
    "nikki@": diary,
    "tex@OTI": credits_strip,
    "btn@": buttons,
    "rec@": records,
    "sumo@": sumo_bout,
    "mzkan@": insect_book,
    "tzkan@": kite_book,
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


# --- the check a translator runs ---------------------------------------------------------------


def patched_archive(archive: Archive, edits: Sequence[ByteEdit]) -> bytes:
    """`BOKU.BIN` with the `edits` addressed to it applied, in memory, `old` bytes checked."""
    blob = bytearray(archive.boku)
    for edit in edits:
        if edit.file == ARCHIVE_NAME:
            if blob[edit.offset : edit.end] != edit.old:
                raise TextureTextError(f"{edit.reason}: the bytes at {edit.offset:#x} differ")
            blob[edit.offset : edit.end] = edit.new
    return bytes(blob)


def main_check(disc_dir: Path, directory: Path, out_dir: Path | None) -> int:
    """`boku textures check`: build every texture edit the English implies, report what each
    family made or why it refused, and optionally write each rebuilt image for a look."""
    from boku.archive import ArchiveError
    from boku.textures import TextureError
    from boku.tim import TimError, parse_exact

    try:
        archive = Archive(disc_dir)
        inv = inventory(archive)
        result = build_edits(archive, directory, inv=inv)
    except (
        TextureTextError, TextureError, TimError, TypesetError, ArchiveError, OSError,
    ) as error:  # fmt: skip
        print(f"boku textures check: {error}")
        return 1
    print(
        f"{len(result.families)} famil{'y' if len(result.families) == 1 else 'ies'} built from "
        f"{directory}: {', '.join(result.families) or 'none'} ({len(result.edits)} byte edits)"
    )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        blob = patched_archive(archive, result.edits)
        touched = [
            t for t in inv.textures
            for o in t.occurrences[:1]
            if o.file == ARCHIVE_NAME
            and blob[o.file_offset : o.file_offset + o.length]
            != archive.boku[o.file_offset : o.file_offset + o.length]
        ]  # fmt: skip
        for texture in touched:
            after = parse_exact(blob, texture.occurrences[0].file_offset)
            (out_dir / f"{texture.id}.png").write_bytes(to_png(after))
        print(f"{len(touched)} rebuilt image(s), through CLUT 0 -> {out_dir}/")
    return 0


__all__ = [
    "FAMILIES",
    "TEXTURE_TEXT_DIR",
    "Entry",
    "TextureEdits",
    "TextureTextError",
    "beach_notice",
    "build_edits",
    "chart_rules",
    "config_screen",
    "diary",
    "erase_type",
    "ink_roles",
    "outlined",
    "patched_archive",
    "read_entries",
    "set_line",
    "stacked",
    "title_menu",
]
