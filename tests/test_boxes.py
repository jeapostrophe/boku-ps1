"""`boku.boxes`: reading `research/data/text-boxes.tsv` and finding a line's box."""

from __future__ import annotations

import pytest

from boku.arrays import ARRAYS, splits_into_rows
from boku.boxes import COLUMNS, BoxError, box_for, load_boxes


def table(tmp_path, *rows: str):
    path = tmp_path / "boxes.tsv"
    path.write_text("\t".join(COLUMNS) + "\n" + "".join(r + "\n" for r in rows), encoding="utf-8")
    load_boxes.cache_clear()
    return load_boxes(path)


def test_a_line_s_own_row_wins_over_its_array_s(tmp_path):
    boxes = table(
        tmp_path,
        "exe@80046214.*\t40\t155\t12\t1\t12\tframe",
        "exe@80046214.3\t40\t100\t12\t1\t12\ta narrower row",
    )
    assert box_for("exe@80046214.3", boxes).right == 100
    assert box_for("exe@80046214.4", boxes).right == 155
    assert box_for("exe@80046214.4", boxes).spec.width == 115
    assert box_for("exe@80046398.0", boxes) is None, "an unmeasured surface has no box"


@pytest.mark.parametrize(
    ("row", "complaint"),
    [
        ("a.1\t40\tforty\t12\t1\ts\tb", "row 2"),
        ("a.1\t40\t40\t12\t1\ts\tb", "not past x"),
        ("a.1\t40\t41\t12\t0\ts\tb", "at least one line"),
    ],
)
def test_a_row_that_cannot_be_a_box_stops_the_read(tmp_path, row, complaint):
    with pytest.raises(BoxError, match=complaint):
        table(tmp_path, row)


def test_a_line_listed_twice_stops_the_read(tmp_path):
    with pytest.raises(BoxError, match="listed twice"):
        table(tmp_path, "a.1\t1\t2\t12\t1\ts\tb", "a.1\t1\t3\t12\t1\ts\tb")


def test_a_box_of_several_lines_is_an_e_array_s():
    """Only an **E** array finds its items by `0x8000`, so only there may the build put a
    `0x8001` inside an item (`boku.layout.holds`); in an **L** array every bit-15 word ends
    an item and an inserted break would shift every later one -- unless the build splits
    the rows into items of their own, which it does for the card messages alone
    (`boku.arrays.splits_into_rows`, `boku.card_messages`)."""
    shapes = {array.line_id_prefix: array.shape for array in ARRAYS}
    load_boxes.cache_clear()
    several = [line_id for line_id, box in load_boxes().items() if box.lines > 1]
    assert several, "no box holds several lines; this checks nothing"
    for line_id in several:
        assert shapes[line_id.rpartition(".")[0]] == "E" or splits_into_rows(line_id), line_id


def test_the_tracked_table_reads():
    load_boxes.cache_clear()
    boxes = load_boxes()
    assert box_for("exe@8003D9BC.4", boxes).x == 84
