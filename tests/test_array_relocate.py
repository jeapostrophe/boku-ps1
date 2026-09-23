"""`boku.array_relocate`: where a grown array goes, and what refusing looks like."""

from __future__ import annotations

import pytest

from boku.array_relocate import (
    ALIGN,
    ArrayRoomRefused,
    Region,
    _addressed,
    _allocate,
    _interior,
    plan_arrays,
)
from boku.arrays import relocatable, walk_all
from boku.pointers import LuiPair, Use


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
