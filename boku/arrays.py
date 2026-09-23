"""Text that is not in an event block: the code-file arrays, labels and the save title.

`research/text-outside-events.md` is the format note. Its method is the important part:
the arrays were found by enumerating the **readers** — every call site of `glyph_draw`,
counted in that note's opening — and each array's bounds are then *derived by walking it
the way its reader walks it* (item count from the caller's index range, select line count
from `g_select_lines`), not delimited by eye. So the catalogue below carries a reader per
array and no end address; the end is whatever the walk reaches.

A wrong item count is caught only when the walk leaves the file it is reading: `walk_array`
is bounded by the image's end and raises `ArrayError` naming the array. A count that is
merely *slightly* too large stays inside the image and silently emits strings carved out of
the next symbol — which is why the catalogue's counts come from the readers and the tracked
`text-arrays.tsv` is diffed against an independent walk.

Three further surfaces have no array to walk:

* **Immediate glyph ids in the instruction stream** — a label assembled from `addiu a0,
  zero, <id>` before each `glyph_draw`. Translating one is a code patch, so the unit is
  the function (`exe@code:80037544`), and the ids are read out of the instructions here.
* **The Shift-JIS memory-card save title** (`title@sjis:188`), which the BIOS card manager
  shows. Its parts and digit strings are pointer tables in `TITLE.OVL`.
* Digits drawn as `0x34 + d`, and the HUD's sprite numbers, which are not text at all.

This module reproduces `research/data/text-arrays.tsv` byte for byte (`boku.research`).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from boku.archive import EXE_LOAD_BIAS, OVERLAY_LOAD_ADDRESS, Archive
from boku.glyphs import END_WORD, NEWLINE_WORD, GlyphTable, words_of
from boku.pointers import destination, resolve_at, words32

OVL = OVERLAY_LOAD_ADDRESS


class ArrayError(Exception):
    """An array whose declared reader and the bytes on the disc disagree."""


@dataclass(frozen=True)
class ArrayDef:
    """One text array, named by where it is and by how its reader walks it.

    `shape` is `research/text-format.md`'s:

    * `E` — items ended by `0x8000`; `0x8001` is a newline *inside* an item.
    * `L` — every bit-15 word ends a line, and code passes a line index.
    * `S` — a select drawn whole; `spec` is `(type, variant)` and the line count comes
      from `g_select_lines`, so the array's length is proved by the executable.
    * `S1` — a single line ended by a bit-15 word (the fishing screen's one-word arrays).
    * `R` — raw glyph cells with no control word at all; `spec` is `(rows, cells)` and the
      reader's loop bound is what says where it stops.
    """

    image: str
    """`"exe"`, or an overlay's lowercase stem (`"hhon"`)."""
    ram: int
    shape: str
    spec: int | tuple[int, int]
    reader: str
    purpose: str

    @property
    def file_name(self) -> str:
        return "SCPS_100.88" if self.image == "exe" else f"{self.image.upper()}.OVL"

    @property
    def file_offset(self) -> int:
        """Offset inside the file that holds it — the EXE, or the overlay member."""
        return self.ram - (EXE_LOAD_BIAS if self.image == "exe" else OVL)

    @property
    def line_id_prefix(self) -> str:
        """`exe@80046214` (RAM) or `hhon@5328` (file offset) — the normative id form."""
        if self.image == "exe":
            return f"exe@{self.ram:08X}"
        return f"{self.image}@{self.file_offset:X}"


ARRAYS: tuple[ArrayDef, ...] = (
    ArrayDef(
        "exe",
        0x80029AFC,
        "E",
        1,
        "ant_msg_open 0x80032030 -> dialog_open",
        "ant-count message; code writes 3 digit glyphs into words 1-3",
    ),
    ArrayDef(
        "exe",
        0x80029B20,
        "L",
        22,
        "help_draw 0x80035674 via help_line 0x800353F8 / 0x80035448 -> text_nth_line",
        "controls help screen (3 pad types)",
    ),
    ArrayDef(
        "exe",
        0x80036750,
        "R",
        (4, 3),
        "fortune_draw 0x8003A7A4",
        "fortune result, 4 results x 3 glyphs, drawn vertically",
    ),
    ArrayDef(
        "exe",
        0x8003D2E0,
        "L",
        57,
        "sysname_draw 0x80037BA8 -> line_draw 0x800379EC",
        "insect names (ids 0-56; ids 56-59 remap to 23/24/27/30, id 60 to 56)",
    ),
    ArrayDef(
        "exe",
        0x8003D5F0,
        "L",
        32,
        "TITLE mc_msg_draw 0x8007CB54 / 0x8007CC4C via g_mc_msg 0x800814C0",
        "memory-card and save/load messages",
    ),
    ArrayDef("exe", 0x8003D9BC, "L", 5, "TITLE config_draw 0x8007FA94", "config screen labels"),
    ArrayDef(
        "exe", 0x8003DA00, "L", 6, "TITLE extras_draw 0x80080680, 0x800803D8", "extras menu labels"
    ),
    ArrayDef("exe", 0x8003DA4C, "L", 3, "fish_name_draw 0x8003C5EC", "fish names"),
    ArrayDef(
        "exe",
        0x80046158,
        "S",
        (3, 3),
        "select_open_ptr 0x8002D10C from 0x8003F1E4 and HHON 0x8007C988",
        "insect cage: release?",
    ),
    ArrayDef("exe", 0x80046178, "S", (6, 1), "select_open_ptr from 0x8003F0B0", "insect cage full"),
    ArrayDef(
        "exe", 0x800461BC, "S", (5, 1), "select_open_ptr from 0x8003F02C", "insect cage select"
    ),
    ArrayDef("exe", 0x800461CC, "E", 8, "kite_list_draw 0x80041FE4 -> text_nth", "kite names"),
    ArrayDef("exe", 0x80046214, "E", 15, "bag_draw 0x800416E8 -> text_nth", "item names"),
    ArrayDef(
        "exe", 0x800462C8, "E", 1, "fish_msg_draw 0x80043ED8 -> text_draw_h", "fishing message 0"
    ),
    ArrayDef("exe", 0x800462E4, "E", 1, "fish_msg_draw 0x80043ED8", "fishing message 1"),
    ArrayDef("exe", 0x80046314, "E", 1, "fish_msg_draw 0x80043ED8", "fishing message 2"),
    ArrayDef("exe", 0x80046334, "E", 1, "fish_msg_draw 0x80043ED8", "fishing message 3"),
    ArrayDef(
        "exe", 0x80046364, "S1", 1, "fish_menu_draw 0x80043F5C -> text_draw", "fishing menu word"
    ),
    ArrayDef("exe", 0x8004636C, "S1", 1, "fish_menu_draw 0x80043F5C", "fishing menu word"),
    ArrayDef("exe", 0x8004637C, "E", 1, "fish_word_draw 0x80043FAC -> text_draw", "fishing word 0"),
    ArrayDef("exe", 0x80046384, "E", 1, "fish_word_draw 0x80043FAC", "fishing word 1"),
    ArrayDef("exe", 0x80046390, "E", 1, "fish_word_draw 0x80043FAC", "fishing word 2"),
    ArrayDef(
        "exe",
        0x80046398,
        "E",
        13,
        "bag_draw 0x800416E8 -> text_nth, text_draw_h",
        "item descriptions",
    ),
    ArrayDef(
        "exe",
        0x80046614,
        "E",
        19,
        "bag_draw 0x800416E8 (index from 0x80047E38[])",
        "photo and morning-glory captions",
    ),
    ArrayDef(
        "hhon",
        OVL + 0x5328,
        "E",
        61,
        "hhon_page_draw 0x8007B410, 0x8007B598 -> text_nth -> "
        "hhon_entry_draw 0x8007C278 / 0x8007C220",
        "insect book entries (60 = empty slot)",
    ),
    ArrayDef(
        "hhon", OVL + 0x6874, "S", (3, 3), "select_open_ptr from 0x8007D23C", "insect book select"
    ),
    ArrayDef(
        "zukan",
        OVL + 0x32E8,
        "S",
        (4, 4),
        "select_open_ptr from 0x8007B07C",
        "write the diary and sleep?",
    ),
    ArrayDef("tako", OVL + 0x4, "S", (2, 1), "select_open_ptr from 0x8007F55C", "kite menu"),
    ArrayDef(
        "tako",
        OVL + 0x440,
        "R",
        (1, 4),
        "tako_crash_draw 0x8007C684 (copied to stack)",
        "kite crash banner, 4 glyphs, vertical",
    ),
    ArrayDef(
        "musi", OVL + 0x4, "S", (4, 3), "select_open_ptr from 0x8007EF0C", "release this insect?"
    ),
    ArrayDef(
        "musi", OVL + 0x2C, "L", 32, "musi_move_draw 0x80084F64, 0x800850D8", "bug-sumo move names"
    ),
    ArrayDef(
        "musi",
        OVL + 0x348,
        "R",
        (1, 7),
        "musi_hint_draw 0x8007C690",
        "bug-sumo button hint, 7 glyphs",
    ),
    ArrayDef(
        "musi",
        OVL + 0x358,
        "R",
        (3, 3),
        "musi_rank_draw 0x8007EDB0",
        "bug-sumo strength labels, 3 x 3 cells (rows 0-1 use 2)",
    ),
    ArrayDef(
        "title", 0x80081480, "R", (1, 5), "mc_yesno_draw (in 0x8007CF7C)", "yes / no, 2+3 glyphs"
    ),
)
"""Every array `research/text-outside-events.md` traced, in that note's table order."""

ANCHORS: dict[str, tuple[str, int]] = {
    "exe@80029AFC": ("exe", 0x8003203C),
    "exe@80029B20": ("exe", 0x80035410),
    "exe@80036750": ("exe", 0x8003A7D0),
    "exe@8003D2E0": ("exe", 0x80037C74),
    "exe@8003D5F0": ("title", 0x8007CC00),
    "exe@8003D9BC": ("title", 0x8007FAE4),
    "exe@8003DA00": ("title", 0x800803E4),
    "exe@8003DA4C": ("exe", 0x8003C608),
    "exe@80046158": ("exe", 0x8003F1CC),
    "exe@80046178": ("exe", 0x8003F0A0),
    "exe@800461BC": ("exe", 0x8003F01C),
    "exe@800461CC": ("exe", 0x80042054),
    "exe@80046214": ("exe", 0x8004174C),
    "exe@800462C8": ("exe", 0x80043EF0),
    "exe@800462E4": ("exe", 0x80043F08),
    "exe@80046314": ("exe", 0x80043F1C),
    "exe@80046334": ("exe", 0x80043F2C),
    "exe@80046364": ("exe", 0x80043F60),
    "exe@8004636C": ("exe", 0x80043F88),
    "exe@8004637C": ("exe", 0x80043FB8),
    "exe@80046384": ("exe", 0x80043FCC),
    "exe@80046390": ("exe", 0x80043FE0),
    "exe@80046398": ("exe", 0x800417E0),
    "exe@80046614": ("exe", 0x80041834),
    "hhon@5328": ("hhon", 0x8007B478),
    "hhon@6874": ("hhon", 0x8007D22C),
    "zukan@32E8": ("zukan", 0x8007B06C),
    "tako@4": ("tako", 0x8007F53C),
    "tako@440": ("tako", 0x8007C688),
    "musi@4": ("musi", 0x8007EEEC),
    "musi@2C": ("musi", 0x80084FA8),
    "musi@348": ("musi", 0x8007C6E0),
    "musi@358": ("musi", 0x8007EDD8),
    "title@7A78": ("title", 0x8007CFF8),
}
"""One `lui` per array whose address pair the walk reads the array's start from -- the
reader's own pointer, so an image a build relocated an array in is walked where the game
will look (`boku.pointers`, `PLAN PIPE-07`). On the import each resolves to the catalogue's
own address, and every reference `boku.pointers.scan` finds is checked against the list on
the real disc (`tests/test_real_pointers.py`)."""

RELOCATABLE_SHAPES = frozenset({"E", "L", "S", "S1"})
"""Arrays a build may move whole: their items are found by walking control words from
the start, so only the start's address pairs change. A raw (`R`) row's cell count is its
reader's loop bound, so it never grows and never moves."""


def relocatable(array: ArrayDef) -> bool:
    return array.shape in RELOCATABLE_SHAPES and array.line_id_prefix in ANCHORS


def byte_limit(line_id: str, size: int) -> int | None:
    """What an array item's English is held to: its own `size` bytes, or `None` when a
    grown array moves whole and only the free space limits it (`boku.array_relocate`).
    The build and the lint both ask here, so they refuse the same items."""
    array = array_of(line_id)
    return None if array is not None and relocatable(array) else size


def array_of(line_id: str) -> ArrayDef | None:
    """The catalogue entry a line id (`exe@80046214.3`, `zukan@32E8`) belongs to."""
    prefix = line_id.split(".", 1)[0]
    return next((a for a in ARRAYS if a.line_id_prefix == prefix), None)


@dataclass(frozen=True)
class ArrayWalk:
    """The result of walking one array the way its reader does."""

    array: ArrayDef
    end: int
    """RAM address one past the last word the reader reads."""
    items: int
    """What the note's TSV counts: lines for a select, rows for a raw table, else items."""
    drawn_cells: int
    """Cells that draw something: `text-arrays.tsv`'s `glyphs` column. It is **not** the
    `glyphs` of a `lines.jsonl` record, which counts a raw array's blank cells as well —
    the two numbers measure the same bytes and had the same name until `PIPE-01`'s review."""
    strings: tuple[tuple[int, int], ...]
    """`(start, end)` RAM spans of the translatable units — a select is one span."""
    image: str
    """Where the walk found it: `array.image`, or `"exe"` for an array a build moved there."""
    start: int
    """RAM address it starts at: `array.ram`, unless a build moved it."""

    @property
    def line_ids(self) -> tuple[str, ...]:
        """One id per string: `prefix` for a select, `prefix.<item>` for everything else."""
        prefix = self.array.line_id_prefix
        if self.array.shape == "S":
            return (prefix,)
        return tuple(f"{prefix}.{i}" for i in range(len(self.strings)))


def locate(archive: Archive, array: ArrayDef) -> tuple[str, int]:
    """`(image, RAM)` where the reader will find `array`: its anchor pair, read."""
    anchor = ANCHORS.get(array.line_id_prefix)
    if anchor is None:
        return array.image, array.ram
    image, lui = anchor
    ram = resolve_at(lambda at, n: archive.image_bytes(image, at, n), lui)
    return ("exe" if ram < OVL else array.image), ram


def walk_array(archive: Archive, array: ArrayDef, select_lines) -> ArrayWalk:
    """Walk one array by its shape, and stop exactly where its reader would stop.

    The walk is bounded by the end of the file it reads: an item count too large for the
    symbol runs on until the image is exhausted, and that is an `ArrayError` naming the
    array rather than an `IndexError` out of `struct`.
    """

    image, start = locate(archive, array)

    def word(at: int) -> int:
        raw = archive.image_bytes(image, at, 2)
        if len(raw) != 2:
            raise ArrayError(
                f"{array.line_id_prefix}: the walk ran off the end of {array.file_name} "
                f"at {at:#010x}; the declared item count is larger than the symbol"
            )
        return words_of(raw)[0]

    if array.shape == "R":
        rows, cells = array.spec
        raw = archive.image_bytes(image, start, 2 * rows * cells)
        if len(raw) != 2 * rows * cells:
            raise ArrayError(
                f"{array.line_id_prefix}: a {rows}x{cells} raw array does not fit in "
                f"{array.file_name}"
            )
        values = words_of(raw)
        if any(v & 0x8000 for v in values):
            raise ArrayError(f"{array.line_id_prefix}: a raw array holds a control word")
        return ArrayWalk(
            array,
            start + 2 * rows * cells,
            rows,
            sum(1 for v in values if v),
            tuple((start + 2 * cells * r, start + 2 * cells * (r + 1)) for r in range(rows)),
            image,
            start,
        )

    if array.shape == "S":
        wanted = select_lines(*array.spec)
    elif array.shape == "S1":
        wanted = 1
    else:
        wanted = array.spec

    p = start
    glyphs = 0
    seen = 0
    starts = [p]
    while seen < wanted:
        w = word(p)
        p += 2
        if array.shape == "E":
            if w == END_WORD:
                seen += 1
                starts.append(p)
            elif w & 0x8000:
                if w != NEWLINE_WORD:
                    raise ArrayError(
                        f"{array.line_id_prefix}: control word {w:#06x} inside an E item"
                    )
            else:
                glyphs += 1
        elif array.shape == "S":
            if w & 0x8000:
                if w != NEWLINE_WORD:
                    raise ArrayError(f"{array.line_id_prefix}: a select line ends with {w:#06x}")
                seen += 1
            else:
                glyphs += 1
        else:  # L, S1
            if w & 0x8000:
                seen += 1
                starts.append(p)
            else:
                glyphs += 1
    # A select is one translatable unit however many lines it holds; everything else is
    # one unit per item, delimited by the starts collected above.
    strings = ((start, p),) if array.shape == "S" else tuple(pairwise(starts))
    return ArrayWalk(array, p, wanted, glyphs, strings, image, start)


SELECT_BASE_ADDR = 0x80028F6C
SELECT_LINES_ADDR = 0x80028F74
SELECT_FIRST_ADDR = 0x80028F80
"""`g_select_base`, `g_select_lines` and `g_select_first`. Each table's length is the
distance to the next, so none of the three is typed: 8, 12 and (the last) 12 bytes."""


class SelectTables:
    """The three executable tables a select box's shape comes out of.

    One home for them, because there were two: `boku.arrays` read `g_select_base` as 8
    bytes and `g_select_lines` as 16 (which overruns into `g_select_first`), and
    `boku.events` read them as 6 and 12 — two lengths for one table, and a reader could
    not tell which was wrong. The index is **bounds-checked**: `type` or `variant` 0 used
    to wrap negatively, and did so to *different* answers in the two readers.
    """

    def __init__(self, archive: Archive) -> None:
        self._base = archive.exe_bytes(SELECT_BASE_ADDR, SELECT_LINES_ADDR - SELECT_BASE_ADDR)
        self._lines = archive.exe_bytes(SELECT_LINES_ADDR, SELECT_FIRST_ADDR - SELECT_LINES_ADDR)
        self._first = archive.exe_bytes(SELECT_FIRST_ADDR, SELECT_FIRST_ADDR - SELECT_LINES_ADDR)

    def _index(self, select_type: int, variant: int) -> int:
        if not 1 <= select_type <= len(self._base):
            raise ArrayError(
                f"select type {select_type} is outside g_select_base[1..{len(self._base)}]"
            )
        if variant < 1:
            raise ArrayError(f"select variant {variant} is below the first variant, 1")
        index = self._base[select_type - 1] + variant - 1
        if index >= len(self._lines):
            raise ArrayError(
                f"select {select_type}.{variant} indexes g_select_lines[{index}], and the "
                f"table holds {len(self._lines)}"
            )
        return index

    def lines(self, select_type: int, variant: int) -> int:
        """How many lines the box draws — the count a translation may never change."""
        return self._lines[self._index(select_type, variant)]

    def shape(self, select_type: int, variant: int) -> tuple[int, int]:
        """`(lines, prompt lines)`; the options are the difference between the two."""
        index = self._index(select_type, variant)
        return self._lines[index], self._first[index]

    def __call__(self, select_type: int, variant: int) -> int:
        return self.lines(select_type, variant)


def walk_all(archive: Archive) -> list[ArrayWalk]:
    """Every array in catalogue order."""
    select_lines = SelectTables(archive)
    return [walk_array(archive, a, select_lines) for a in ARRAYS]


# --- the REC-03 spans, derived from the catalogue ------------------------------------------


@dataclass(frozen=True)
class LegacySpan:
    """One span of `research/data/text-sites.tsv`'s array walk (`REC-03`'s enumeration).

    `REC-06` refined that walk in two ways: it split the 103-line array at `0x8003D2E0`
    into the five arrays their readers actually index separately, and it found five raw
    arrays the scans could not see because they hold no control word. Both refinements are
    *undone* here, so the tracked TSV keeps reproducing — a merged run of chained `L`
    arrays and no raw ones. Nothing is typed: the merged span's end and its 103 items come
    out of the same catalogue rows the refined walk uses.
    """

    image: str
    start: int
    end: int
    """RAM addresses."""
    shape: str
    """`E`, `L` or `S` — `REC-03` had no `S1`/`R` distinction."""


def legacy_spans(archive: Archive) -> list[LegacySpan]:
    """The 25 spans `REC-03` walked, in `text-sites.tsv`'s order (EXE first, then overlays)."""
    walks = {id(w.array): w for w in walk_all(archive)}
    out: list[LegacySpan] = []
    for array in ARRAYS:
        if array.shape == "R":
            continue  # REC-03's scans could not see an array with no control word
        walk = walks[id(array)]
        shape = "S" if array.shape in ("S", "S1") else array.shape
        previous = out[-1] if out else None
        chains = (
            previous is not None
            and previous.image == array.image
            and previous.shape == "L" == shape
            and 0 <= array.ram - previous.end <= 2
        )
        if chains:
            out[-1] = LegacySpan(array.image, previous.start, walk.end, "L")
        else:
            out.append(LegacySpan(array.image, array.ram, walk.end, shape))
    order = {"exe": 0, "hhon": 1, "musi": 2, "tako": 3, "zukan": 4, "title": 5}
    return sorted(out, key=lambda s: (order[s.image], s.start))


# --- glyph ids that are instruction immediates ---------------------------------------------

GLYPH_DRAW = 0x8002BA2C
GLYPH_DRAW_LAYER = 0x8002B9FC
"""`research/font.md`. Overlays call both at their executable addresses."""

_OP_SPECIAL = 0x00
_OP_J = 0x02
_OP_JAL = 0x03
_OP_ADDIU = 0x09
_OP_ORI = 0x0D
_REG_A0 = 4
_JR_RA = 0x03E00008
_FUNCTION_WORD_LIMIT = 512
"""A safety net: no label drawer is anywhere near this long, and an unterminated scan
would otherwise read to the end of the image."""


CODE_LABEL_MARK = "@code:"
"""What sets a code label's id (`exe@code:80037544`) apart from an array item's."""


@dataclass(frozen=True)
class CodeLabel:
    """A label a function assembles from immediate glyph ids, with no data to extract."""

    image: str
    function: int
    """RAM address of the function — the unit of translation, per the research note."""
    runs: tuple[tuple[int, ...], ...]
    """Glyph ids in the order they are **drawn**, split where a draw took a computed id
    instead — which is where the function switches to a digit."""
    sites: tuple[tuple[int, int], ...]
    """`(RAM address, glyph id)` of every instruction that loads one of these ids. There
    are more sites than draws: a label reached down two branches is assembled twice, so
    `）` is one drawn character and four instructions a code patch has to change."""  # noqa: RUF001
    purpose: str
    draws: tuple[int, ...] = ()
    """For each of `sites`, which drawn glyph it feeds: an index into `glyph_ids`."""

    @property
    def line_id(self) -> str:
        return f"{self.image}{CODE_LABEL_MARK}{self.function:X}"

    @property
    def glyph_ids(self) -> tuple[int, ...]:
        return tuple(i for run in self.runs for i in run)


CODE_LABELS: tuple[tuple[str, int, str], ...] = (
    ("exe", 0x80037544, "caught_label_draw: caught, month, day"),
    ("exe", 0x80037698, "specimen_label_draw: specimen made, month, day (no caller found)"),
    ("exe", 0x800377F8, "winloss_draw: wins, losses"),
    ("title", 0x8007BB60, "save_date_draw: 8, month, day"),
    ("title", 0x8007C8EC, "file_rows_draw: the ) after a slot number"),
    ("title", 0x80080484, "extras_numbers_draw: the separators of 'n / 31' and 'n %'"),
)
"""The six functions `research/text-outside-events.md` traced. Their glyph ids are read
from the instruction stream below, not copied out of the note."""


def _a0_literal(word: int) -> int | None:
    """The immediate of `addiu`/`ori a0, zero, imm`, which is a glyph id being passed."""
    rs, rt = (word >> 21) & 0x1F, (word >> 16) & 0x1F
    if (word >> 26) in (_OP_ADDIU, _OP_ORI) and rs == 0 and rt == _REG_A0:
        return word & 0xFFFF
    return None


def _jump_target(word: int, op: int) -> int | None:
    return 0x80000000 | ((word & 0x03FFFFFF) << 2) if word >> 26 == op else None


def _draw_of(words: list[int], start: int, function: int) -> int | None:
    """Index of the `glyph_draw` a literal loaded at `start` reaches, or `None`.

    Walks forward from the load: an unconditional `j` inside the function is followed
    (`file_rows_draw` loads its closing paren and jumps to the shared call), and it dies at
    anything that overwrites `a0` — another literal, a computed value, or a call to
    something that is not `glyph_draw`, because the callee clobbers its own arguments.

    A delay slot is read as what it is. The instruction after a `jal` executes *before*
    the call, so a literal there is that call's argument and belongs to nobody else; a
    literal in a plain jump's delay slot survives the jump and carries on at its target.
    """
    previous = words[start - 1] if start else 0
    if previous >> 26 == _OP_SPECIAL and previous & 0x3F in (0x08, 0x09):  # jr, jalr
        return None
    if previous >> 26 == _OP_JAL:
        target = _jump_target(previous, _OP_JAL)
        return start - 1 if target in (GLYPH_DRAW, GLYPH_DRAW_LAYER) else None
    jumped = _jump_target(previous, _OP_J)
    p = (jumped - function) // 4 if jumped is not None else start + 1
    seen: set[int] = set()
    while 0 <= p < len(words) and p not in seen:
        seen.add(p)
        word = words[p]
        slot = words[p + 1] if p + 1 < len(words) else 0
        # The delay slot runs before the transfer, so a write to a0 there is not ours.
        slot_takes_a0 = _a0_literal(slot) is not None or destination(slot) == _REG_A0
        target = _jump_target(word, _OP_JAL)
        if target is not None or (word >> 26 == _OP_SPECIAL and word & 0x3F == 0x09):
            if target in (GLYPH_DRAW, GLYPH_DRAW_LAYER) and not slot_takes_a0:
                return p
            return None
        jumped = _jump_target(word, _OP_J)
        if jumped is not None:
            if slot_takes_a0:
                return None
            p = (jumped - function) // 4
            continue
        if word == _JR_RA or _a0_literal(word) is not None or destination(word) == _REG_A0:
            return None
        p += 1
    return None


def read_code_labels(archive: Archive) -> list[CodeLabel]:
    """Disassemble just enough of each label drawer to read the ids it passes `glyph_draw`.

    Two passes. The first resolves each `addiu`/`ori a0, zero, imm` to the `glyph_draw`
    call it reaches, if any (`_draw_of`). The second walks the calls in program order and
    emits one id per call that got a literal, breaking the run at a call that did not —
    that is where the function switches to a computed digit.
    """
    out = []
    for image, function, purpose in CODE_LABELS:
        raw = archive.image_bytes(image, function, 4 * _FUNCTION_WORD_LIMIT)
        words = words32(raw)
        stop = len(words)
        for i, word in enumerate(words):
            if word == _JR_RA:
                stop = min(stop, i + 2)  # the delay slot still runs
        words = words[:stop]

        drawn: dict[int, int] = {}
        sites: list[tuple[int, int]] = []
        feeds: list[int] = []
        for i, word in enumerate(words):
            value = _a0_literal(word)
            if value is None:
                continue
            draw = _draw_of(words, i, function)
            if draw is not None:
                drawn[draw] = value
                sites.append((function + 4 * i, value))
                feeds.append(draw)

        runs: list[tuple[int, ...]] = []
        current: list[int] = []
        for i, word in enumerate(words):
            if _jump_target(word, _OP_JAL) not in (GLYPH_DRAW, GLYPH_DRAW_LAYER):
                continue
            if i in drawn:
                current.append(drawn[i])
            elif current:
                runs.append(tuple(current))
                current = []
        if current:
            runs.append(tuple(current))
        order = sorted(drawn)
        draws = tuple(order.index(draw) for draw in feeds)
        out.append(CodeLabel(image, function, tuple(runs), tuple(sites), purpose, draws))
    return out


# --- the Shift-JIS memory-card save title ----------------------------------------------------

SAVE_TITLE_DIGITS_ADDR = 0x8008141C
SAVE_TITLE_PARTS_ADDR = 0x80081444
"""`g_save_title_digits` and `g_save_title_parts` in `TITLE.OVL`. The digit table's length
is the distance between them; the part table's is however many pointers land in the
overlay, so neither count is typed here."""

SAVE_TITLE_LINE_ID = "title@sjis:188"
SAVE_TITLE_BYTES = 64
"""The `SC` header's title field. The BIOS wants full-width characters (two bytes each),
and `save_title_build` adds the slot and the day (up to 2 + 2 of them) and a terminator, so
the English around them is at most 27 characters (`boku.code_text.save_title_parts`)."""


@dataclass(frozen=True)
class SaveTitle:
    """The one Shift-JIS string a player sees: the save's name in the BIOS card manager."""

    parts: tuple[str, ...]
    digits: tuple[str, ...]
    part_offsets: tuple[int, ...]
    """File offsets inside `TITLE.OVL`, so a patch knows where the strings live."""

    @property
    def line_id(self) -> str:
        return SAVE_TITLE_LINE_ID


def read_save_title(archive: Archive) -> SaveTitle:
    """Follow both pointer tables and decode the Shift-JIS strings they name."""
    member = archive.member("TITLE.OVL")
    blob = archive.blob(member)
    low, high = OVL, OVL + len(blob)

    def pointer(addr: int) -> int:
        return int.from_bytes(archive.overlay_bytes("TITLE.OVL", addr, 4), "little")

    def string_at(ram: int) -> tuple[str, int]:
        off = ram - OVL
        end = blob.index(b"\0", off)
        return blob[off:end].decode("shift_jis"), off

    digit_count = (SAVE_TITLE_PARTS_ADDR - SAVE_TITLE_DIGITS_ADDR) // 4
    digits = []
    for i in range(digit_count):
        p = pointer(SAVE_TITLE_DIGITS_ADDR + 4 * i)
        if not low <= p < high:
            raise ArrayError(f"g_save_title_digits[{i}] points outside TITLE.OVL")
        digits.append(string_at(p)[0])
    parts: list[str] = []
    offsets: list[int] = []
    i = 0
    while True:
        p = pointer(SAVE_TITLE_PARTS_ADDR + 4 * i)
        if not low <= p < high:
            break
        text, off = string_at(p)
        parts.append(text)
        offsets.append(off)
        i += 1
    if not parts:
        raise ArrayError("g_save_title_parts holds no pointer into TITLE.OVL")
    return SaveTitle(tuple(parts), tuple(digits), tuple(offsets))


def describe_label(label: CodeLabel, table: GlyphTable) -> str:
    """A code label as readable text, with its runs separated — for `lines.jsonl`."""
    return " / ".join(
        "".join(table.unambiguous.get(i) or f"{{G:{i}}}" for i in run) for run in label.runs
    )
