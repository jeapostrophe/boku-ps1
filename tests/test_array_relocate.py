"""`boku.array_relocate`: where a grown array goes, and what refusing looks like."""

from __future__ import annotations

import pytest

from boku.archive import EXE_LOAD_BIAS, EXE_NAME
from boku.array_relocate import (
    ALIGN,
    ArrayRoomRefused,
    Region,
    _addressed,
    _allocate,
    _block_units,
    _interior,
    plan_arrays,
)
from boku.arrays import relocatable, walk_all
from boku.events import Block
from boku.glyphs import END_WORD, words_of
from boku.pointers import LuiPair, Use, resolve_at
from boku.sites import RESIDENT_BLOCK_ADDRS, RESIDENT_BLOCK_ANCHORS, resident_line_id
from boku.sites import walk as sites_walk


def test_the_largest_array_goes_first_into_the_smallest_run_that_holds_it():
    regions = [Region(0x1000, 0x1100, "big"), Region(0x2000, 0x2040, "small")]
    placed, left = _allocate([("a", 0x30), ("b", 0xF0)], regions)
    assert placed == {"b": 0x1000, "a": 0x2000}
    assert left == (0x100 - 0xF0) + (0x40 - 0x30)


def test_a_placement_is_aligned_and_the_alignment_is_charged():
    placed, _ = _allocate([("a", 4), ("b", 2)], [Region(0x1002, 0x100C, "odd")])
    assert all(at % ALIGN == 0 for at in placed.values())


def test_running_out_names_the_array_and_the_numbers():
    refused = _allocate([("a", 0x20), ("b", 0x80)], [Region(0x1000, 0x1040, "r")])
    assert refused[0] == "b"
    assert "needs 128 contiguous bytes and the largest free run left is 64" in refused[1]


def test_an_array_with_no_room_gives_up_only_the_items_that_grew(archive):
    """Narrowest: one item one cell too long, and no region at all -- not even its own
    vacated bytes can hold a larger copy of itself. The item beside it fits its own bytes
    and is written in place, as before arrays could move."""
    walked = next(
        w for w in walk_all(archive) if w.array.line_id_prefix == "exe@80046214"
    )  # item names
    assert relocatable(walked.array)
    (s0, e0), (s1, e1) = walked.strings[:2]
    words = {
        walked.line_ids[0]: (0x100,) * ((e0 - s0) // 2) + (0x8000,),  # one cell too long
        walked.line_ids[1]: (0x100,) * ((e1 - s1) // 2 - 1) + (0x8000,),  # fits
    }
    with pytest.raises(ArrayRoomRefused) as refused:
        plan_arrays(archive, words, regions=())
    assert refused.value.lines == (walked.line_ids[0],)


def test_a_pointer_that_cannot_move_refuses_only_the_arrays_it_addresses():
    pair = LuiPair(0x80041000, (Use(0x80041004, 0x80046214, True),))
    spans = {
        "exe@80046214": ("exe", 0x80046214, 0x800462C6),
        "exe@80046398": ("exe", 0x80046398, 0x80046612),
    }
    assert _addressed(pair, "exe", spans) == ["exe@80046214"]


def test_a_use_inside_a_moved_array_is_refused_rather_than_left_on_the_old_bytes():
    """Only an array's start is ever addressed on this disc; a use of `arr + k` would keep
    reading the vacated span, which another array may already fill."""
    spans = {"exe@80046214": ("exe", 0x80046214, 0x800462C6)}
    inside = LuiPair(0x80041000, (Use(0x80041004, 0x80046216, True),))
    assert _interior(inside, "exe", spans) == ["exe@80046214"]
    start = LuiPair(0x80041000, (Use(0x80041004, 0x80046214, True),))
    assert _interior(start, "exe", spans) == []


def test_an_item_that_still_fits_its_bytes_moves_nothing(archive):
    walked = next(w for w in walk_all(archive) if w.array.line_id_prefix == "exe@80046214")
    start, end = walked.strings[0]
    words = {walked.line_ids[0]: (0x100,) * ((end - start) // 2 - 1) + (0x8000,)}
    assert plan_arrays(archive, words, regions=()).moved == ()


def _call(archive):
    """The uncle's evening call: the resident block, its message 0's site, and its anchor."""
    ram = RESIDENT_BLOCK_ADDRS[0]
    walk = sites_walk(archive)
    (site,) = walk.by_line[resident_line_id(ram, 0)]
    return ram, site


def test_a_resident_block_message_one_cell_past_its_site_moves_the_block(archive):
    """At the boundary the in-place writer enforces: `site.size` bytes still fit, one more
    cell does not, and the whole block then moves, repacked."""
    ram, site = _call(archive)
    line = resident_line_id(ram, 0)
    fits = (0x100,) * (site.size // 2 - 1) + (END_WORD,)
    assert not list(_block_units(archive, {line: fits}))
    over = (0x100,) * (site.size // 2) + (END_WORD,)
    (unit,) = _block_units(archive, {line: over})
    assert unit.grown == (line,)
    assert words_of(Block(unit.blob).entries[4])[: len(over)] == over


def test_the_chooser_s_pair_is_rewritten_to_form_the_block_s_new_address(archive):
    """Apply the plan's executable edits and read the chooser's `lui` back: it must form
    the address the block was written to. One cell over still repacks into the block's own
    span (its last entry's pad is spare), so the block may be rewritten where it was."""
    ram, site = _call(archive)
    over = (0x100,) * (site.size // 2) + (END_WORD,)
    plan = plan_arrays(archive, {resident_line_id(ram, 0): over})
    (moved,) = [m for m in plan.moved if m.old == ram]
    exe = bytearray(archive.exe)
    for e in plan.edits:
        if e.file == EXE_NAME:
            exe[e.offset : e.offset + len(e.new)] = e.new
    lui = RESIDENT_BLOCK_ANCHORS[ram]

    def read(at, n):
        return bytes(exe[at - EXE_LOAD_BIAS : at - EXE_LOAD_BIAS + n])

    assert resolve_at(read, lui) == moved.new
    assert read(moved.new, moved.size) == Block(read(moved.new, moved.size)).serialise()


def test_the_lint_s_room_check_lays_out_a_resident_block_s_rows_too(disc_dir, monkeypatch):
    """The block competes with the arrays for the same room, so the lint's `array_room`
    must hand `move_arrays` the block's words, laid out by the build's own `lay_out`."""
    from boku import build as build_module
    from boku.layout import StockEncoder
    from boku.lint import Options, _array_room
    from boku.translation import TranslationEntry

    offered: dict = {}

    def recording(archive, words, regions, skip_unfitted):
        offered.update(words)
        return None, {}

    monkeypatch.setattr(build_module, "move_arrays", recording)
    line = resident_line_id(RESIDENT_BLOCK_ADDRS[0], 0)
    entry = TranslationEntry(line, "Uncle", ("Right! Playtime is over.", "Dinner is ready!"))
    options = Options(encoder=StockEncoder.load(), label=False)
    room = _array_room(disc_dir, "stock", None, options)
    assert room({}, {line: entry}) is None
    assert line in offered, "the block's words never reached the room check"
