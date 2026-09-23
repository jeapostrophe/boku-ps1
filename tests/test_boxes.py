"""`boku.boxes`: reading `research/data/text-boxes.tsv` and finding a line's box."""

from __future__ import annotations

import pytest

from boku.boxes import COLUMNS, BoxError, box_for, load_boxes


def table(tmp_path, *rows: str):
    path = tmp_path / "boxes.tsv"
    path.write_text("\t".join(COLUMNS) + "\n" + "".join(r + "\n" for r in rows), encoding="utf-8")
    load_boxes.cache_clear()
    return load_boxes(path)


def test_a_line_s_own_row_wins_over_its_array_s(tmp_path):
    boxes = table(
        tmp_path,
        "exe@80046214.*\t40\t155\t12\t12\tframe",
        "exe@80046214.3\t40\t100\t12\t12\ta narrower row",
    )
    assert box_for("exe@80046214.3", boxes).right == 100
    assert box_for("exe@80046214.4", boxes).right == 155
    assert box_for("exe@80046214.4", boxes).spec.width == 115
    assert box_for("exe@80046398.0", boxes) is None, "an unmeasured surface has no box"


@pytest.mark.parametrize(
    ("row", "complaint"),
    [
        ("a.1\t40\tforty\t12\ts\tb", "row 2"),
        ("a.1\t40\t40\t12\ts\tb", "not past x"),
    ],
)
def test_a_row_that_cannot_be_a_box_stops_the_read(tmp_path, row, complaint):
    with pytest.raises(BoxError, match=complaint):
        table(tmp_path, row)


def test_a_line_listed_twice_stops_the_read(tmp_path):
    with pytest.raises(BoxError, match="listed twice"):
        table(tmp_path, "a.1\t1\t2\t12\ts\tb", "a.1\t1\t3\t12\ts\tb")


def test_the_tracked_table_reads():
    load_boxes.cache_clear()
    boxes = load_boxes()
    assert box_for("exe@8003D9BC.4", boxes).x == 88
