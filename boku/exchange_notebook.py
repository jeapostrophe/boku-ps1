"""`PLAN TXT-12`: bug sumo's exchange notebook draws some insect names shorter.

`MUSI`'s exchange notebook (`0x8007E670`) ends a sumo fighter's name at x 271, the item after
it (`vwf_name_before_sym`, `asm/musi_text.asm`), with the size badge on its left
(research/sumo.md § The desk's text). A name the badge would cover has a version for the
notebook alone (Jay, 2026-09-24: "Miyama Stag", not "Miyama Stag Beetle"), a row
`exe@8003D2E0.<n>@exchange` in `arrays.txt`; every other screen keeps the full name.

The build writes the versions as one list with an item per sumo fighter type (`FIGHTERS`),
each ended by `0x8000` and empty for a type with no version, anywhere resident; and hooks the
notebook's entry (`drawer_hook`) to `vwf_exchange_entry` with `t0` at the list.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable, Mapping, Sequence

from boku.archive import Archive
from boku.boxes import EVERY_ITEM, TextBox, load_boxes
from boku.code_text import lay_out_banner
from boku.glyphs import END_WORD, words_to_bytes
from boku.layout import Encoder, LaidOut
from boku.sumo import TYPES

ARRAY = "exe@8003D2E0"
"""The insect names (`g_sysmsg_text`)."""
VARIANT = "@exchange"
"""Suffix of a notebook-only version's id: `exe@8003D2E0.28@exchange`."""
UNIT = ARRAY + VARIANT
"""The list's name as a moved unit (`boku.array_relocate`)."""
NOTEBOOK = ("musi", 0x8007E670)
"""The notebook's page, whose entry the build hooks."""
ROUTINE = "vwf_exchange_entry"
FIGHTERS = tuple(sorted(TYPES.values()))
"""The list's items, in order: the sumo fighter types (`FIGHTERS_A`, `FIGHTERS_B` in
`asm/musi_text.asm`)."""
REMAP_TYPES, REMAP_LINES, REMAP_COUNT = 0x80036708, 0x80036710, 4
"""`g_insect_name_remap`: four halfword types (the females, 56-59) and the four lines
`sysmsg_line_draw` (`0x80037BA8`) draws for them."""
MANTIS_TYPE, MANTIS_LINE = 60, 56
"""`sysmsg_line_draw`'s one other case, in its code (`0x80037C4C`): type 60 draws line 56."""


def is_variant(line_id: str) -> bool:
    return line_id.startswith(ARRAY + ".") and line_id.endswith(VARIANT)


def base_of(line_id: str) -> str:
    """`exe@8003D2E0.28@exchange` -> `exe@8003D2E0.28`; any other id as it is."""
    return line_id.removesuffix(VARIANT)


def box(boxes: Mapping[str, TextBox] | None = None) -> TextBox:
    """The room a version has: its own row of `research/data/text-boxes.tsv`."""
    return (load_boxes() if boxes is None else boxes)[ARRAY + EVERY_ITEM + VARIANT]


def lay_out(
    line_id: str, text: str, encoder: Encoder, boxes: Mapping[str, TextBox] | None = None
) -> LaidOut:
    """A version's cells, ended by `0x8000`, laid out as a banner item is, in `box`."""
    return lay_out_banner(line_id, text, encoder, box(boxes).spec)


def line_of_type(archive: Archive) -> dict[int, int]:
    """`{fighter type: the line of ARRAY it draws}`, as `sysmsg_line_draw` maps it."""
    count = f"<{REMAP_COUNT}H"
    types = struct.unpack(count, archive.exe_bytes(REMAP_TYPES, 2 * REMAP_COUNT))
    lines = struct.unpack(count, archive.exe_bytes(REMAP_LINES, 2 * REMAP_COUNT))
    remap = dict(zip(types, lines, strict=True)) | {MANTIS_TYPE: MANTIS_LINE}
    return {kind: remap.get(kind, kind) for kind in FIGHTERS}


def undrawn(archive: Archive, line_ids: Iterable[str]) -> tuple[str, ...]:
    """The versions no fighter draws: of a line outside `line_of_type`, or of no line."""
    drawn = {f"{ARRAY}.{line}{VARIANT}" for line in line_of_type(archive).values()}
    return tuple(line_id for line_id in line_ids if line_id not in drawn)


def names_blob(archive: Archive, versions: Mapping[str, Sequence[int]]) -> bytes:
    """The list the notebook draws from, given every version's words by id (none `undrawn`)."""
    by_line = {int(base_of(line).rpartition(".")[2]): cells for line, cells in versions.items()}
    items = [by_line.get(line, (END_WORD,)) for line in line_of_type(archive).values()]
    return b"".join(words_to_bytes(item) for item in items)
