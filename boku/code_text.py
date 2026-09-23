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

from collections.abc import Sequence
from unicodedata import normalize

from boku.archive import ARCHIVE_NAME, EXE_LOAD_BIAS, EXE_NAME, OVERLAY_LOAD_ADDRESS, Archive
from boku.arrays import SAVE_TITLE_BYTES, CodeLabel
from boku.glyphs import PAD_WORD
from boku.layout import Encoder, LaidOut, _sheet, sheet_cells
from boku.reinsert import ByteEdit

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
        if label.image == "exe":
            file, offset = EXE_NAME, ram - EXE_LOAD_BIAS
            old = archive.exe_bytes(ram, 4)
        else:
            member = archive.member(f"{label.image.upper()}.OVL")
            file, offset = ARCHIVE_NAME, member.offset + ram - OVERLAY_LOAD_ADDRESS
            old = archive.image_bytes(label.image, ram, 4)
        word = int.from_bytes(old, "little")
        new = (word & 0xFFFF0000) | cells[draw]
        if new != word:
            edits.append(
                ByteEdit(
                    file=file,
                    offset=offset,
                    old=old,
                    new=new.to_bytes(4, "little"),
                    reason=f"{label.line_id} 0x{ram:08X}: glyph {cells[draw]} (PLAN PIPE-07)",
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
