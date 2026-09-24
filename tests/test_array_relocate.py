"""`boku.array_relocate`: where a grown array goes, and what refusing looks like."""

from __future__ import annotations

from functools import cache

import pytest

from boku import exchange_notebook
from boku.archive import (
    ARCHIVE_NAME,
    EXE_LOAD_BIAS,
    EXE_NAME,
    OVERLAY_LOAD_ADDRESS,
    SECTOR,
    overlay_read_end,
)
from boku.array_relocate import (
    ALIGN,
    HEAP_POINTER,
    ArrayRoomRefused,
    Region,
    _addressed,
    _allocate,
    _block_units,
    _interior,
    _padded,
    plan_arrays,
    scans,
)
from boku.arrays import ANCHORS, relocatable, walk_all
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


def test_touching_runs_are_one_run():
    """Two neighbours that both move leave one run: an array longer than either fits there
    (the captions, 1,138 bytes, once the date routines had grown the island's code)."""
    regions = [Region(0x1000, 0x1034, "first"), Region(0x1034, 0x1080, "second")]
    placed, left = _allocate([("big", 0x78)], regions)
    assert placed == {"big": 0x1000}
    assert left == 0x80 - 0x78


def test_runs_apart_stay_apart():
    regions = [Region(0x1000, 0x1032, "first"), Region(0x1034, 0x1080, "second")]
    assert _allocate([("big", 0x78)], regions)[0] == "big"


class _Exe:
    def __init__(self, data: dict[int, bytes]) -> None:
        self.data = data

    def exe_bytes(self, ram: int, n: int) -> bytes:
        return b"".join(self.data.get(ram + i, b"\0") for i in range(n))


def test_a_vacated_span_takes_its_alignment_pad_only_when_the_pad_is_zero():
    """A walk ends where the reader stops; the two bytes to the next 4-aligned address are
    the linker's pad when they are zero, and something else's when they are not."""
    region = Region(0x1000, 0x1032, "an array")
    assert _padded(_Exe({}), region).end == 0x1034
    assert _padded(_Exe({0x1033: b"\x01"}), region).end == 0x1032


def test_a_placement_is_aligned_and_the_alignment_is_charged():
    placed, _ = _allocate([("a", 4), ("b", 2)], [Region(0x1002, 0x100C, "odd")])
    assert all(at % ALIGN == 0 for at in placed.values())


def test_running_out_names_the_array_and_the_numbers():
    refused = _allocate([("a", 0x20), ("b", 0x80)], [Region(0x1000, 0x1040, "r")])
    assert refused[0] == "b"
    assert "needs 128 contiguous bytes and the largest free run left is 64" in refused[1]


def test_an_array_with_no_room_gives_up_only_the_items_that_grew(archive):
    """Narrowest: one item two cells too long -- one more than the array's alignment pad
    could absorb -- and no region at all, so not even its own vacated bytes hold a larger
    copy of it. The item beside it fits its own bytes and is written in place, as before
    arrays could move."""
    walked = next(
        w for w in walk_all(archive) if w.array.line_id_prefix == "exe@80046214"
    )  # item names
    assert relocatable(walked.array)
    (s0, e0), (s1, e1) = walked.strings[:2]
    words = {
        walked.line_ids[0]: (0x100,) * ((e0 - s0) // 2 + 1) + (0x8000,),  # two cells over
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

    def recording(archive, words, regions, skip_unfitted, routines=None):
        offered.update(words)
        return None, {}

    monkeypatch.setattr(build_module, "move_arrays", recording)
    line = resident_line_id(RESIDENT_BLOCK_ADDRS[0], 0)
    entry = TranslationEntry(line, "Uncle", ("Right! Playtime is over.", "Dinner is ready!"))
    options = Options(encoder=StockEncoder.load(), label=False)
    room = _array_room(disc_dir, "stock", None, options)
    assert room({}, {line: entry}) is None
    assert line in offered, "the block's words never reached the room check"


def _grown_first_item(archive, prefix, extra_cells=1):
    """`prefix`'s walk and words growing its item 0 `extra_cells` past its own bytes."""
    walked = next(w for w in walk_all(archive) if w.array.line_id_prefix == prefix)
    start, end = walked.strings[0]
    words = {walked.line_ids[0]: (0x100,) * ((end - start) // 2 - 1 + extra_cells) + (0x8000,)}
    return walked, words


def _overlay_code(archive, plan, name):
    """`name`'s stored bytes with the plan's edits inside it applied, then its tail."""
    member = archive.member(name)
    code = bytearray(archive.blob(member))
    for e in plan.edits:
        if e.file == ARCHIVE_NAME and member.offset <= e.offset < member.offset + member.size:
            code[e.offset - member.offset : e.end - member.offset] = e.new
    tail = plan.tails.get(name)
    return bytes(code) + (tail.data if tail else b"")


def test_an_array_only_one_overlay_reads_moves_into_that_overlay_s_tail(archive):
    """Narrowest: the memory-card messages, read only by `TITLE.OVL`, one item one cell
    over, and no resident room at all. The array still moves -- into the tail of the
    overlay that reads it, which loads with it -- and `TITLE`'s own pair forms the new
    address; nothing is written to the executable for it."""
    walked, words = _grown_first_item(archive, "exe@8003D5F0")
    plan = plan_arrays(archive, words, regions=())
    (moved,) = plan.moved
    title = archive.member("TITLE.OVL")
    assert moved.new >= OVERLAY_LOAD_ADDRESS + title.size, "not past the overlay's own bytes"
    code = _overlay_code(archive, plan, "TITLE.OVL")

    def read(at, n):
        return code[at - OVERLAY_LOAD_ADDRESS : at - OVERLAY_LOAD_ADDRESS + n]

    assert resolve_at(read, ANCHORS["exe@8003D5F0"][1]) == moved.new
    first = words[walked.line_ids[0]]
    assert words_of(read(moved.new, 2 * len(first))) == first
    assert not [e for e in plan.edits if e.file == EXE_NAME], "the executable was written"


def test_an_array_the_executable_reads_never_moves_into_an_overlay(archive):
    """The item names are read by `bag_draw` in the executable, and no overlay is loaded
    in every mode: with no resident room they are refused, however much tail room an
    overlay has."""
    _, words = _grown_first_item(archive, "exe@80046214", extra_cells=2)  # past its pad
    with pytest.raises(ArrayRoomRefused):
        plan_arrays(archive, words, regions=())


def test_an_overlay_s_tail_stops_where_its_load_would_pass_the_retail_heap(archive):
    """A load writes whole sectors (`research/text-renderer.md` § 6): the grown member's
    last sector must end at or below the retail heap's first byte, the word `g_heap_base`
    starts at in the executable -- the most a retail load ever left to the overlays -- and
    the tail is not cut short of it: the longest item that still moves fills the last
    sector below the heap. Found by search, not by restating the bound."""
    heap = int.from_bytes(archive.exe_bytes(HEAP_POINTER, 4), "little")
    title = archive.member("TITLE.OVL")
    walked = next(w for w in walk_all(archive) if w.array.line_id_prefix == "exe@8003D5F0")
    scanned = cache(lambda: scans(archive))

    def plan_with(n):
        words = {walked.line_ids[0]: (0x100,) * n + (0x8000,)}
        try:
            return plan_arrays(archive, words, regions=(), scanned=scanned)
        except ArrayRoomRefused:
            return None

    low, high = 1, (heap - OVERLAY_LOAD_ADDRESS) // 2  # fits; cannot fit in all of RAM
    assert plan_with(low) is not None and plan_with(high) is None
    while high - low > 1:
        middle = (low + high) // 2
        low, high = (middle, high) if plan_with(middle) is not None else (low, middle)
    load_end = overlay_read_end([title.size + len(plan_with(low).tails["TITLE.OVL"].data)])
    assert load_end <= heap, "the load runs past the heap's first byte"
    assert load_end + SECTOR > heap, "a whole sector below the heap was left unused"


def test_an_overlay_the_disc_could_not_grow_leaves_its_arrays_to_resident_room(archive):
    """`no_tail` names an overlay the reinserter refused to grow: its arrays are placed
    in resident room instead of being left in Japanese."""
    _, words = _grown_first_item(archive, "exe@8003D9BC")
    (moved,) = plan_arrays(archive, words, no_tail=frozenset({"TITLE.OVL"})).moved
    assert moved.tail is None and moved.new < OVERLAY_LOAD_ADDRESS


def test_an_array_too_big_for_its_overlay_s_tail_does_not_push_the_others_out(archive):
    """The memory-card messages grown past `TITLE.OVL`'s whole tail go to resident room
    (a large one, for the test); the config labels, which `TITLE` alone reads too, still
    take the tail."""
    _, card_words = _grown_first_item(archive, "exe@8003D5F0", extra_cells=40_000)
    _, config_words = _grown_first_item(archive, "exe@8003D9BC")
    resident = Region(0x80020000, 0x80020000 + 0x20000, "a large resident run")
    plan = plan_arrays(archive, card_words | config_words, regions=(resident,))
    where = {m.prefix: m.tail for m in plan.moved}
    assert where == {"exe@8003D5F0": None, "exe@8003D9BC": "TITLE.OVL"}


@pytest.mark.parametrize("line_id", ["exe@8003D2E0.31@exchange", "exe@8003D2E0.2x@exchange"])
def test_a_notebook_name_for_a_line_no_fighter_draws_is_refused(archive, line_id):
    """`boku.exchange_notebook`: the notebook's list holds the sumo fighters' lines alone, so
    a version of any other line (or of no line) would be written and never drawn."""
    words = {line_id: (0x100, 0x8000), "exe@8003D2E0.23@exchange": (0x100, 0x8000)}
    with pytest.raises(ArrayRoomRefused) as refused:
        plan_arrays(archive, words, routines={exchange_notebook.ROUTINE: 0x80025000})
    assert refused.value.lines == (line_id,)
