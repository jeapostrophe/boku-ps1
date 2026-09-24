"""`boku.card_messages`: a memory-card message on two rows, split across `g_mc_msg` records."""

from __future__ import annotations

import json

import pytest

from boku import REPO_ROOT
from boku.archive import OVERLAY_LOAD_ADDRESS
from boku.array_relocate import ArrayRoomRefused, plan_arrays
from boku.arrays import ROW_SPLIT, walk_all
from boku.card_messages import RECORD_BYTES, RECORDS, TITLE, _records
from boku.glyphs import NEWLINE_WORD, words_of
from boku.row_split import splits

A, B = 0x100, 0x101
TWO_ROWS = (A, NEWLINE_WORD, B, NEWLINE_WORD)
"""An L item laid out on two rows: each row ends with the item's own terminator."""


def _items(archive) -> int:
    walked = next(w for w in walk_all(archive) if w.array.line_id_prefix == ROW_SPLIT)
    return len(walked.line_ids)


def _rewritten(archive, plan) -> dict[int, bytes]:
    """`{record: its new bytes}` among the plan's edits."""
    first = archive.overlay_offset(TITLE, RECORDS)
    return {
        (e.offset - first) // len(e.new): e.new
        for e in plan.edits
        if first <= e.offset < first + RECORD_BYTES * len(_records(archive))
    }


def test_a_two_row_item_keeps_its_first_row_and_its_second_follows_the_last_item(archive):
    (split,) = splits({f"{ROW_SPLIT}.3": TWO_ROWS}, ROW_SPLIT)
    assert split.head == (A, NEWLINE_WORD)
    assert split.rest == ((B, NEWLINE_WORD),)
    assert split.added == (_items(archive),)


def test_the_records_showing_item_3_gain_its_row_and_move_up(archive):
    """Narrowest: item 3, which records 3 (with item 8 under it) and 6 (alone) show. The
    layouts are the ones seen right on Beetle (research/vwf-prototype.md): record 3 moves
    from layout 3 to 4 and draws three rows, record 6 from 0 to 1 and draws two."""
    new = _items(archive)
    plan = plan_arrays(archive, {f"{ROW_SPLIT}.3": TWO_ROWS}, regions=())
    assert _rewritten(archive, plan) == {
        3: bytes([3, 4, 3, new, 8]),
        6: bytes([2, 1, 3, new, 99]),
    }


def test_a_record_that_would_pass_three_rows_refuses_the_line(archive):
    """Record 20 already draws items 21-23 on three rows; the arrays' room check refuses
    item 21 on two rows, so the lint, which runs the same check, sees it too."""
    rows, _, *slots = _records(archive)[20]
    assert rows == 3
    line = f"{ROW_SPLIT}.{slots[0]}"
    with pytest.raises(ArrayRoomRefused, match="4 rows and a record holds 3") as refused:
        plan_arrays(archive, {line: TWO_ROWS}, regions=())
    assert refused.value.lines == (line,)


def test_the_moved_array_holds_the_head_in_place_and_the_rest_after_its_last_item(archive):
    plan = plan_arrays(archive, {f"{ROW_SPLIT}.3": TWO_ROWS}, regions=())
    (moved,) = plan.moved
    start = moved.new - (OVERLAY_LOAD_ADDRESS + archive.member(TITLE).size)
    rows = _rows(words_of(plan.tails[TITLE].data[start : start + moved.size]))
    assert len(rows) == _items(archive) + 1
    assert rows[3] == (A, NEWLINE_WORD)
    assert rows[-1] == (B, NEWLINE_WORD)


def _rows(words) -> list[tuple[int, ...]]:
    rows, row = [], []
    for word in words:
        row.append(word)
        if word & 0x8000:
            rows.append(tuple(row))
            row = []
    return rows


def test_the_days_build_draws_every_row_of_each_card_message_it_split(archive, days_built):
    """Read back: every item of the built array past the stock count is a row drawn by
    some record right after the item it continues, and every stock record that showed
    that item shows the new row after it too."""
    manifest = json.loads((REPO_ROOT / "build" / "days" / "manifest.json").read_text())
    (entry,) = [e for e in manifest["arrays_moved"] if e["array"] == ROW_SPLIT]
    items = _items(archive)
    walked = next(w for w in walk_all(days_built) if w.array.line_id_prefix == ROW_SPLIT)
    rows = _rows(words_of(days_built.image_bytes(walked.image, walked.start, entry["bytes"])))
    assert len(rows) > items, "the days build split no card message; this checks nothing"
    stock, built = _records(archive), _records(days_built)
    shown = [slots[:count] for count, _, *slots in stock]
    now = [slots[:count] for count, _, *slots in built]
    continues: dict[int, int] = {}  # new item -> the stock item whose row it continues
    for row in now:
        for at, item in enumerate(row):
            if item >= items:
                assert at > 0, "a new row drawn first, above the row it continues"
                continues.setdefault(item, continues.get(row[at - 1], row[at - 1]))
    assert set(continues) == set(range(items, len(rows))), "an added row no record draws"
    for number in range(len(stock)):
        assert [item for item in now[number] if item < items] == shown[number], number
        for new, base in continues.items():
            if base in shown[number]:
                at = now[number].index(base)
                assert new in now[number][at + 1 :], f"record {number} misses {new}'s row"
    for new in continues:
        assert rows[new][-1] == NEWLINE_WORD and len(rows[new]) > 1
