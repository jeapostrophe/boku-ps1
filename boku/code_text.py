"""`PLAN PIPE-07`: the English that has no text site -- labels in code, and the save title.

Two surfaces `research/text-outside-events.md` traced that are not data a reinserter can
overwrite (`script_store.PLACED_BY_CODE`):

* **Labels assembled from immediate glyph ids** (`boku.arrays.CODE_LABELS`): each drawn
  glyph is an `addiu a0, zero, <id>` before a `jal glyph_draw` at a position the function
  computes. An English label with **one character per drawn glyph** is placed by
  rewriting those immediates -- every site, since a label reached down two branches is
  loaded twice (`CodeLabel.draws`). A label that needs more glyphs than the code draws
  changes the function's layout, which is not a substitution and is refused with the
  counts.
* **The memory-card save title** (`title@sjis:188`), which the BIOS card manager shows:
  `save_title_build` (`TITLE.OVL` `0x8007AEF4`) concatenates `g_save_title_parts[0]`, the
  slot number, `parts[1]`, the day, `parts[2]` into the 64-byte `SC` header field with no
  bound. The row is written `Boku's Memories {slot} August {day}`; the three parts are
  full-width Shift-JIS (the BIOS draws only full-width characters), written into resident
  free space by `boku.array_relocate`, and the three pointers repointed there.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from unicodedata import normalize

from boku.archive import ARCHIVE_NAME, EXE_LOAD_BIAS, EXE_NAME, Archive
from boku.arrays import CODE_LABEL_MARK, SAVE_TITLE_BYTES, CodeLabel, array_of
from boku.glyphs import END_WORD, PAD_WORD, words_to_bytes
from boku.layout import BoxSpec, Encoder, LaidOut, _sheet, sheet_cells
from boku.reinsert import ByteEdit


@dataclass(frozen=True)
class DateLabel:
    routine: str
    """Its drawer's replacement in `asm/labels.asm`, by its symbol in the edit set."""
    places: tuple[str, ...]
    """Where the row puts the numbers the drawer computes, in the order they are drawn."""
    example: str
    """The row as it is written, for a refusal to show."""


DATE_LABELS: dict[str, DateLabel] = {
    "exe@code:80037544": DateLabel(
        "vwf_caught_label", ("{month}", "{day}"), "Date caught {month}/{day}"
    ),
    "title@code:8007BB60": DateLabel("vwf_save_date_label", ("{day}",), "August {day}"),
}
"""The labels whose English the code cannot hold glyph for glyph -- a date, with numbers the
drawer computes between its words. `asm/labels.asm` redraws each through the advance table
and places the numbers after the measured text."""

LABEL_PITCH = 12
"""What `asm/labels.asm` steps a cell that is not English (`vwf_lookup_at LABEL_PITCH`)."""

HOOK_WORDS = 3
"""`lui t0, hi(text)` / `j routine` / `addiu t0, t0, lo(text)` over the drawer's entry."""

LABEL_FIELD = " / "
"""Between the runs of a code label -- where the function draws a computed digit."""

SLOT, DAY = "{slot}", "{day}"
"""Where `save_title_build` puts the slot number and the day in the save title."""

WIDEST_NUMBER = 2
"""Digits of the largest slot (15) and day (31) the title can carry."""


def lay_out_code_label(
    line_id: str, runs_drawn: Sequence[Sequence[int]], text: str, encoder: Encoder
) -> LaidOut:
    """`text`'s cells in the order the function draws its glyphs (`runs_drawn`, the label's
    `CodeLabel.runs`), one per drawn glyph.

    Runs are separated by ` / `, as `boku.arrays.describe_label` writes them; spaces
    inside a run separate what the code already spaces (the digits between `W` and `L`)
    and draw nothing. A run shorter than the code draws is padded with the blank cell;
    a longer one needs more draws than the function makes -- a change to its layout."""
    runs = [run.replace(" ", "") for run in text.split(LABEL_FIELD)]
    laid = [sheet_cells(encoder, run) for run in runs]
    problems = [f"{line_id}: {p}" for run in laid for p in run.problems]
    wanted = [len(run) for run in runs_drawn]
    given = [len(run.cells) for run in laid]
    if len(given) != len(wanted) or any(g > w for g, w in zip(given, wanted, strict=False)):
        problems.insert(
            0,
            f"{line_id}: the code draws {wanted} glyph(s) per run and {text!r} needs "
            f"{given}; a label is placed one character per drawn glyph, and more glyphs "
            f"than the function draws is a change to its layout, not a substitution",
        )
        cells = tuple(cell for run in laid for cell in run.cells)
        return LaidOut(line_id, cells, (tuple(runs),), ((0,),), tuple(problems))
    sheet = _sheet()
    cells: list[int] = []
    for drawn, run in zip(runs_drawn, laid, strict=True):
        for glyph, cell in zip(drawn, run.cells, strict=False):
            # A cell the original glyph already spells (the extras screen's slash, 3, 1 and
            # percent; the narrow closing paren) keeps that glyph: the digits the code
            # computes beside it are the sheet's full-width ones, and an English cell there
            # would change the label's look for nothing.
            spelled = normalize("NFKC", sheet.characters.get(glyph, ""))
            again = sheet_cells(encoder, spelled) if spelled else None
            same = again is not None and not again.problems and again.cells == (cell,)
            cells.append(glyph if same else cell)
        cells += [PAD_WORD] * (len(drawn) - len(run.cells))
    width = sum(run.width for run in laid)
    return LaidOut(line_id, tuple(cells), (tuple(runs),), ((width,),), tuple(problems))


def code_label_edits(archive: Archive, label: CodeLabel, cells: Sequence[int]) -> list[ByteEdit]:
    """Every `addiu a0, zero, <id>` of the label, its immediate replaced by its glyph's cell."""
    edits = []
    for (ram, _), draw in zip(label.sites, label.draws, strict=True):
        word = int.from_bytes(archive.image_bytes(label.image, ram, 4), "little")
        new = (word & 0xFFFF0000) | cells[draw]
        if new != word:
            edits.append(
                _code_edit(
                    archive,
                    label.image,
                    ram,
                    new.to_bytes(4, "little"),
                    f"{label.line_id} 0x{ram:08X}: glyph {cells[draw]} (PLAN PIPE-07)",
                )
            )
    return edits


FULL_WIDTH_SPECIAL = {
    "'": chr(0x2019),  # right single quotation mark, Shift-JIS 0x8166
    '"': chr(0x201D),  # right double quotation mark, 0x8168
    "-": chr(0x2212),  # minus sign, 0x817C
    "~": chr(0x301C),  # wave dash, 0x8160
}
"""ASCII whose U+FF01 form strict Shift-JIS has no code for (only cp932 does)."""


def full_width(text: str) -> str:
    """ASCII as the full-width characters the BIOS card manager draws."""
    out = []
    for character in text:
        if character == " ":
            out.append(chr(0x3000))  # the ideographic space
        elif character in FULL_WIDTH_SPECIAL:
            out.append(FULL_WIDTH_SPECIAL[character])
        elif "!" <= character <= "~":
            out.append(chr(ord(character) - 0x21 + 0xFF01))
        else:
            out.append(character)
    return "".join(out)


def save_title_parts(text: str) -> tuple[bytes, bytes, bytes] | str:
    """The three Shift-JIS parts of `Boku's Memories {slot} August {day}`, or why not."""
    if text.count(SLOT) != 1 or text.count(DAY) != 1 or text.index(SLOT) > text.index(DAY):
        return (
            f"the title is written with {SLOT} and then {DAY} where the code puts the slot "
            f'number and the day, e.g. "Boku\'s Memories {SLOT} August {DAY}"'
        )
    first, rest = text.split(SLOT)
    second, third = rest.split(DAY)
    try:
        parts = tuple(full_width(part).encode("shift_jis") for part in (first, second, third))
    except UnicodeEncodeError as error:
        return f"{error.object[error.start : error.end]!r} has no full-width Shift-JIS form"
    longest = sum(len(part) for part in parts) + 2 * 2 * WIDEST_NUMBER + 1
    if longest > SAVE_TITLE_BYTES:
        return (
            f"the longest title (slot 15, day 31) is {longest} bytes with its terminator, "
            f"and the card's title field holds {SAVE_TITLE_BYTES}; save_title_build does not "
            f"stop, so it would run into the header past it"
        )
    return parts  # type: ignore[return-value]


def lay_out_save_title(line_id: str, text: str) -> LaidOut:
    """The three parts, NUL-terminated back to back, as the words a build carries them in."""
    parts = save_title_parts(text)
    if isinstance(parts, str):
        return LaidOut(line_id, (), ((text,),), ((0,),), (f"{line_id}: {parts}",))
    blob = b"".join(part + b"\0" for part in parts)
    blob += bytes(len(blob) % 2)
    words = tuple(int.from_bytes(blob[i : i + 2], "little") for i in range(0, len(blob), 2))
    return LaidOut(line_id, words, ((text,),), ((len(blob),),), ())


def split_title_blob(blob: bytes) -> list[int]:
    """Offsets of the three parts in a blob `lay_out_save_title` made (NUL-terminated, and
    Shift-JIS never holds a zero byte)."""
    first = blob.index(b"\0") + 1
    second = blob.index(b"\0", first) + 1
    blob.index(b"\0", second)  # the third part is terminated too, or this is not a title
    return [0, first, second]


def lay_out_date_label(line_id: str, text: str, encoder: Encoder) -> LaidOut:
    """A date label's segments -- the text between its numbers -- as cells, each ended by
    `0x8000`, which is what `asm/labels.asm`'s `vwf_label_cells` walks."""
    label = DATE_LABELS[line_id]
    problems: list[str] = []
    segments = [text]
    for place in label.places:
        head, found, tail = segments[-1].partition(place)
        if not found:
            problems.append(
                f"{line_id}: the row marks where the code draws its numbers with "
                f"{' and then '.join(label.places)}, e.g. {label.example!r}"
            )
            break
        segments[-1:] = [head, tail]
    cells: list[int] = []
    width = 0
    for segment in segments:
        laid = sheet_cells(encoder, segment, LABEL_PITCH)
        problems += [f"{line_id}: {p}" for p in laid.problems]
        cells += [*laid.cells, END_WORD]
        width += laid.width
    return LaidOut(line_id, tuple(cells), (tuple(segments),), ((width,),), tuple(problems))


def date_label_hook(archive: Archive, line_id: str, text: int, routine: int) -> ByteEdit:
    """`drawer_hook` over a date label's drawer."""
    image, ram = drawer_of(line_id)
    return drawer_hook(archive, image, ram, text, routine, line_id)


def drawer_hook(
    archive: Archive, image: str, ram: int, text: int, routine: int, what: str
) -> ByteEdit:
    """The three words over a drawer's entry that hand it to `routine` with `t0 = text`.

    The retail drawer's first three instructions are replaced, never run: the jump leaves
    before its frame is made, and `t0` is a temporary no caller keeps."""
    words = (
        0x3C080000 | ((text + 0x8000) >> 16) & 0xFFFF,  # lui t0, hi(text)
        0x08000000 | (routine >> 2) & 0x03FFFFFF,  # j routine
        0x25080000 | text & 0xFFFF,  # addiu t0, t0, lo(text)
    )
    new = b"".join(word.to_bytes(4, "little") for word in words)
    return _code_edit(archive, image, ram, new, f"{what}: into {routine:#010x} (PLAN PIPE-07)")


def drawer_of(line_id: str) -> tuple[str, int]:
    """`(image, RAM)` of the function a code label's id names."""
    image, function = line_id.split(CODE_LABEL_MARK)
    return image, int(function, 16)


def _code_edit(archive: Archive, image: str, ram: int, new: bytes, reason: str) -> ByteEdit:
    """`new` over the code at `ram` in the executable or an overlay, expecting what is there."""
    old = archive.image_bytes(image, ram, len(new))
    if image == "exe":
        return ByteEdit(EXE_NAME, ram - EXE_LOAD_BIAS, old, new, reason)
    return ByteEdit(
        ARCHIVE_NAME, archive.overlay_offset(f"{image.upper()}.OVL", ram), old, new, reason
    )


# --- the two banners ------------------------------------------------------------------------

BANNER_PANEL_X = 100
BANNER_PANEL_W = 120
BANNER_PANEL_H = 36
"""Both banners' panel once it holds one horizontal line: x 100..220, so centred on the
retail column (glyphs at x 154, `LABEL_PITCH` wide), and 36 tall, centred where the retail
panel was. The line is centred on `BANNER_CENTRE`, which the text hands `asm/banners.asm`."""

BANNER_CENTRE = BANNER_PANEL_X + BANNER_PANEL_W // 2


@dataclass(frozen=True)
class Banner:
    """A raw array its drawer stacks vertically in a tall panel (`asm/banners.asm`). In
    English its items become cells ended by `0x8000`, drawn by `routine` as one centred line,
    and the panel is made wide: at `rect`, the retail `(x, y, w, h)` as four halfwords, or
    at `literals`, as four `addiu v0,zero,n` words."""

    routine: str
    drawer: tuple[str, int]
    retail: tuple[int, int, int, int]
    rect: tuple[str, int] | None = None
    literals: tuple[str, tuple[int, int, int, int]] | None = None

    @property
    def panel(self) -> tuple[int, int, int, int]:
        """The wide panel, centred on the retail one's middle row."""
        _, y, _, h = self.retail
        return BANNER_PANEL_X, y + (h - BANNER_PANEL_H) // 2, BANNER_PANEL_W, BANNER_PANEL_H

    @property
    def y(self) -> int:
        """The line's y: centred in the panel."""
        _, top, _, h = self.panel
        return top + (h - LABEL_PITCH) // 2

    def panel_edits(self) -> list[tuple[str, int, bytes]]:
        """`(image, RAM, new bytes)` over the retail rect."""
        if self.rect is not None:
            return [(*self.rect, struct.pack("<4h", *self.panel))]
        image, rams = self.literals
        return [
            (image, ram, (0x24020000 | value).to_bytes(4, "little"))
            for ram, value in zip(rams, self.panel, strict=True)
        ]


BANNERS: dict[str, Banner] = {
    "exe@80036750": Banner(  # fortune_panel_draw 0x8003A6A8 reads the rect at 0x8003DA90
        "vwf_fortune_banner", ("exe", 0x8003A7A4), (125, 26, 70, 108), rect=("exe", 0x8003DA90)
    ),
    "tako@440": Banner(  # tako_panel_draw 0x8007C5B0 builds it from four literals
        "vwf_crash_banner",
        ("tako", 0x8007C684),
        (125, 66, 70, 108),
        literals=("tako", (0x8007C610, 0x8007C618, 0x8007C620, 0x8007C628)),
    ),
}
"""The fortune (`fortune_draw`, four results) and the kite crash (`tako_crash_draw`)."""


def banner_of(line_id: str) -> Banner | None:
    return BANNERS.get(line_id.split(".", 1)[0])


def is_laid_out_banner(words: Sequence[int]) -> bool:
    """Words `lay_out_banner` made (ended by `0x8000`), not an item's retail cells."""
    return tuple(words[-1:]) == (END_WORD,)


def lay_out_banner(line_id: str, text: str, encoder: Encoder, box: BoxSpec | None) -> LaidOut:
    """A banner item as cells ended by `0x8000`, no wider than its measured `box`."""
    laid = sheet_cells(encoder, text, LABEL_PITCH)
    problems = [f"{line_id}: {p}" for p in laid.problems]
    if not text:
        problems.append(
            f"{line_id}: no English was given for this array item; writing it empty would "
            f"blank an item the game still draws"
        )
    if box is not None and laid.width > box.width:
        problems.append(
            f"{line_id}: {text!r} is {laid.width} px and {box.name} holds {box.width}, "
            f"{laid.width - box.width} over"
        )
    return LaidOut(line_id, (*laid.cells, END_WORD), ((text,),), ((laid.width,),), tuple(problems))


def banner_blob(archive: Archive, prefix: str, words: Mapping[str, Sequence[int]]) -> bytes:
    """What the hook points `t0` at: the line's centre x and y, then every item -- its
    English, or the retail cells of one left untranslated (or handed in as those cells) --
    each ended by `0x8000`."""
    array = array_of(prefix)
    rows, cells = array.spec
    out = struct.pack("<2h", BANNER_CENTRE, BANNERS[prefix].y)
    for row in range(rows):
        new = words.get(f"{prefix}.{row}")
        if new is not None and is_laid_out_banner(new):
            out += words_to_bytes(new)
        else:
            out += archive.image_bytes(array.image, array.ram + 2 * cells * row, 2 * cells)
            out += words_to_bytes([END_WORD])
    return out


def banner_edits(archive: Archive, prefix: str, text: int, routine: int) -> list[ByteEdit]:
    """The hook over the banner's drawer and the wide panel."""
    banner = BANNERS[prefix]
    image, ram = banner.drawer
    return [
        drawer_hook(archive, image, ram, text, routine, prefix),
        *(
            _code_edit(archive, im, at, new, f"{prefix}: the banner's panel (PLAN TXT-05)")
            for im, at, new in banner.panel_edits()
        ),
    ]
