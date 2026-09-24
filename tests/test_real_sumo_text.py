"""Bug sumo's desk text in English (`PLAN TXT-05`, `PIPE-07`; research/sumo.md § The desk's
text): the days build's hooked drawers, run instruction by instruction on what the image holds.

* **The button hint** (`musi@348`) is drawn centred on its board, and the board -- two
  sprites of `MUSI.OVL` in retail -- is widened with slices of its left half until it
  holds the line with the retail margins.
* **The rank board** (`musi@358`) draws each row centred where the retail rows are.
* **The exchange notebook's names** end where the item after them begins (x 271) instead of
  starting at x 175 and running under it.

Needs the import and `./make.sh build-days`.
"""

from __future__ import annotations

import json
import struct
from itertools import pairwise

import pytest

from boku.archive import EXE_LOAD_BIAS, OVERLAY_LOAD_ADDRESS, Archive
from boku.asm_source import asm_equate
from boku.boxes import box_spec_for
from boku.code_text import BANNERS, LABEL_PITCH, lay_out_banner
from boku.glyphs import END_WORD
from boku.layout import measure
from tests import test_real_banners
from tests.mips import Machine
from tests.test_pointers import jal
from tests.test_real_boxes import word
from tests.test_real_date_labels import DAYS, EDITS, GLYPH_FLUSH

rows, encoder = test_real_banners.rows, test_real_banners.encoder
"""The arrays' English and the days build's cell map: the banners' fixtures, shared."""
HINT, RANK = "musi@348", "musi@358"
TEXT_SET_LIGHT = asm_equate("TEXT_SET_LIGHT", "voice.asm")
PANEL_SPRITE = asm_equate("PANEL_SPRITE", "musi_text.asm")
HINT_LEFT = asm_equate("HINT_LEFT", "musi_text.asm")
HINT_RIGHT = asm_equate("HINT_RIGHT", "musi_text.asm")
HINT_MARGINS = asm_equate("HINT_MARGINS", "musi_text.asm")
OFFSCREEN_X = asm_equate("OFFSCREEN_X", "walkers.asm")
SYSMSG_LINE_DRAW = asm_equate("SYSNAME_DRAW", "walkers.asm")
NOTEBOOK = range(0x8007E670, 0x8007EC00)
"""The exchange notebook's drawer: its name calls are found in it, not listed here."""
RECORD = 22
"""A `MUSI.OVL` sprite record: `+2` x, `+6` u, `+8` w (`0x800368C8` reads it)."""
RANK_Y0, RANK_Y2 = 0x8007EE28, 0x8007EE84
"""musi_rank_draw's `addiu a2,s1,85` (rows 0-1: y = 85 + 16 row) and `addiu a2,zero,117`."""
RANK_X2 = 0x8007EE7C
"""Its `addiu a1,a1,90`: row 2's three cells, 12 px apart, from x 90."""
BEETLES = range(23, 31)
"""The sumo beetles' types, which are their name lines (research/sumo.md)."""


def _machine(archive: Archive, on_stub=None) -> Machine:
    stubs = (GLYPH_FLUSH, TEXT_SET_LIGHT, PANEL_SPRITE)
    machine = Machine(stubs={a: [] for a in stubs}, on_stub=on_stub or {})
    machine.load(EXE_LOAD_BIAS, archive.exe)
    machine.load(OVERLAY_LOAD_ADDRESS, archive.blob(archive.member("MUSI.OVL")))
    return machine


def _musi_word(archive: Archive, at: int) -> int:
    return word(archive, at, "MUSI.OVL")


def _imm(archive: Archive, at: int) -> int:
    found = _musi_word(archive, at)
    assert found >> 26 == 0x09, f"0x{at:08X} is not the addiu this test reads"
    return found & 0xFFFF


def _name_sites(archive: Archive) -> list[int]:
    call = jal(SYSMSG_LINE_DRAW)
    return [at for at in range(NOTEBOOK.start, NOTEBOOK.stop, 4) if _musi_word(archive, at) == call]


def _english(rows, encoder, line_id: str) -> tuple[list[int], int]:
    laid = lay_out_banner(line_id, rows[line_id], encoder, box_spec_for(line_id))
    assert not laid.problems, laid.problems
    ((width,),) = laid.widths
    return [cell for cell in laid.words if cell != END_WORD], width


def _record(archive_or_machine, at: int) -> tuple[int, int, int]:
    raw = (
        archive_or_machine.image_bytes("musi", at, RECORD)
        if isinstance(archive_or_machine, Archive)
        else bytes(archive_or_machine.ram[at - 0x80000000 : at - 0x80000000 + RECORD])
    )
    x, u, w = struct.unpack_from("<h", raw, 2)[0], raw[6], struct.unpack_from("<h", raw, 8)[0]
    return x, u, w


def test_the_hint_is_centred_on_a_board_widened_to_hold_it(archive, days_built, rows, encoder):
    pieces: list[tuple[int, int, int]] = []
    machine = _machine(
        days_built,
        on_stub={PANEL_SPRITE: lambda m: pieces.append(_record(m, m.regs[5]))},
    )
    machine.call(BANNERS[HINT].drawer[1])
    cells, width = _english(rows, encoder, f"{HINT}.0")
    assert [d[0] for d in machine.draws] == cells
    retail_left, retail_right = _record(archive, HINT_LEFT), _record(archive, HINT_RIGHT)
    centre = (retail_left[0] + retail_right[0] + retail_right[2]) // 2  # the retail board's
    y = BANNERS[HINT].centre[1]
    left = centre - width // 2
    assert machine.draws[0][1] == left and {d[2] for d in machine.draws} == {y}
    assert len(machine.stubs[GLYPH_FLUSH]) == 1, "flushed once, as retail does"

    assert pieces[0][1:] == retail_left[1:], "the board opens with its retail left half"
    assert pieces[-1][1:] == retail_right[1:], "and closes with its retail right half"
    for (x, _, w), (next_x, _, _) in pairwise(pieces):
        assert x + w == next_x, "the pieces meet"
    for _, u, w in pieces[1:-1]:
        assert retail_left[1] <= u and u + w <= retail_left[1] + retail_left[2], "slices of it"
    board_left, board_right = pieces[0][0], pieces[-1][0] + pieces[-1][2]
    assert board_left + board_right == 2 * centre, "centred where the retail board was"
    margin = HINT_MARGINS // 2
    assert board_left + margin <= left and left + width <= board_right - margin, (
        f"the {width}-px line at x {left} is not inside the board {board_left}..{board_right} "
        f"with the retail {margin}-px margins"
    )


def test_each_rank_row_is_centred_where_the_retail_rows_are(archive, days_built, rows, encoder):
    top, bottom = _imm(archive, RANK_Y0), _imm(archive, RANK_Y2)
    centre = _imm(archive, RANK_X2) + 3 * LABEL_PITCH // 2
    machine = _machine(days_built)
    machine.call(BANNERS[RANK].drawer[1])
    at = 0
    for row in range(3):
        cells, width = _english(rows, encoder, f"{RANK}.{row}")
        drawn = machine.draws[at : at + len(cells)]
        at += len(cells)
        assert [d[0] for d in drawn] == cells
        assert drawn[0][1] == centre - width // 2
        assert {d[2] for d in drawn} == {top + (bottom - top) * row // 2}
    assert at == len(machine.draws)
    assert len(machine.stubs[GLYPH_FLUSH]) == 1


@pytest.fixture(scope="module")
def name_routine() -> int:
    walker = json.loads(EDITS.read_text(encoding="utf-8"))["walker_island"]["symbols"]
    return int(walker["vwf_name_before_sym"], 16)


def test_the_notebook_sites_call_the_name_that_ends_before_the_next_item(
    archive, days_built, name_routine
):
    sites = _name_sites(archive)
    assert len(sites) == 3, "the notebook's three name calls"
    want = jal(name_routine)
    for site in sites:
        assert _musi_word(days_built, site) == want, f"0x{site:08X} does not call it"


def test_the_widest_fighter_s_name_ends_where_the_item_after_it_begins(
    archive, days_built, rows, encoder, name_routine
):
    """The retail item after the name is `addiu a1,zero,x` just after each call."""
    (item_x,) = {_imm(archive, site + 8) for site in _name_sites(archive)}
    widest = max(BEETLES, key=lambda n: measure(encoder, rows[f"exe@8003D2E0.{n}"]))
    machine = _machine(days_built)
    machine.call(name_routine, widest, 175, 0x1C, 0)
    shown = [d for d in machine.draws if d[1] < OFFSCREEN_X]
    advance = {cell_id: adv for cell_id, adv in encoder.cells.values()}
    assert shown, "nothing was drawn on screen"
    end = shown[-1][1] + advance.get(shown[-1][0], LABEL_PITCH)
    assert end == item_x, f"the name ends at x {end}, not at the item's x {item_x}"
    assert len(machine.stubs[GLYPH_FLUSH]) == 1, "the measuring pass flushed as well"


def test_the_days_build_leaves_the_move_names_retail_and_does_not_call_them_refused(rows):
    """`boku.arrays.UNREACHABLE`: every `musi@2C` row of arrays.txt is listed as
    unreachable in the days build's manifest, none as refused or written."""
    manifest_path = DAYS / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip("no build/days: run `./make.sh build-days` first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    moves = sorted(line for line in rows if line.startswith("musi@2C."))
    assert moves, "arrays.txt carries the move names"
    assert sorted(manifest["lines_unreachable"]) == moves
    assert not set(moves) & (set(manifest["lines_refused"]) | set(manifest["lines_written"]))
