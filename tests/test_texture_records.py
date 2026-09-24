"""`boku.texture_records` without a disc: labels beside run-time numbers, on invented plates.

The plate is made here (`tests/synth_tim.py`): noisy pale paper, "Japanese" in dark ink with a
mid-grey drop shadow. The real records are `tests/test_real_texture_records.py`'s.
"""

from __future__ import annotations

import pytest

from boku import texture_paint as paint
from boku import texture_records as tr
from boku.archive import ARCHIVE_NAME
from boku.texture_text import Entry, TextureTextError
from boku.textures import Occurrence, Texture
from boku.tim import parse_exact
from tests import synth_tim as synth

PAPER, PAPER2, SHADE, INK = 1, 2, 3, 4
WORDS = [0] * 256
WORDS[PAPER], WORDS[PAPER2] = 29 * 0x421, 28 * 0x421
WORDS[SHADE], WORDS[INK] = 18 * 0x421, 4 * 0x421
W, H = 64, 24


class Blocks:
    name, cell, pitch = "blocks", 5, 6

    def measure(self, text):
        return max(0, 4 * len(text) - 1)

    def ink(self, text):
        return {(4 * n + dx, dy) for n, ch in enumerate(text) if ch != " "
                for dx in range(3) for dy in range(5)}  # fmt: skip


def plate(*blocks: tuple[range, range]):
    """Paper in two noisy entries; "Japanese" at x 20-29, rows 6-12 (or at `blocks`, each
    (columns, rows)), with a shadow."""
    px = [PAPER if (x * 7 + y * 3) % 5 else PAPER2 for y in range(H) for x in range(W)]
    for xs, ys in blocks or ((range(20, 30), range(6, 13)),):
        for x, y in ((x, y) for x in xs[::2] for y in ys):
            px[(y + 1) * W + x + 1] = SHADE
            px[y * W + x] = INK
    raw = synth.tim(
        1, synth.pixel_block(W // 2, H, bytes(px)), clut=synth.clut_block(256, 1, WORDS)
    )
    tim = parse_exact(raw)
    place = Occurrence(ARCHIVE_NAME, "\\_DATA\\X.BIN", 0, 0x1000, tim.length)
    return paint.Canvas(Texture("x", "0" * 40, tim, (place,)))


def record(align="left", room=None, shadow=True, key="w"):
    label = tr.Label(key, (18, 4, 16, 12), room, align, face="game")
    return tr.Record("x", 0, (label,), shadow=shadow)


def test_a_label_is_cleared_to_paper_and_set_at_its_rooms_left_edge():
    canvas = plate()
    rec = record()
    tr.rebuild(canvas, rec, {"w": Entry("rec@x.w", "Go", "r:1")}, Blocks(), 0, 0, 0, "x")
    inked = {p for p in paint.points((0, 0, W, H)) if canvas.at(p) == INK}
    assert paint.extent(inked)[0] == 18, "a label after a number starts where its box does"
    assert paint.normalised(inked) == paint.normalised(Blocks().ink("Go"))
    shade = {p for p in paint.points((0, 0, W, H)) if canvas.at(p) == SHADE}
    assert shade == {(x + 1, y + 1) for x, y in inked} - inked, "its shadow and no other"


def test_a_label_before_a_number_ends_where_its_room_does():
    canvas = plate()
    rec = record("right", (10, 4, 24, 12))
    tr.rebuild(canvas, rec, {"w": Entry("rec@x.w", "Go", "r:1")}, Blocks(), 0, 0, 0, "x")
    inked = {p for p in paint.points((0, 0, W, H)) if canvas.at(p) == INK}
    x, _, w, _ = paint.extent(inked)
    assert x + w + 1 == 10 + 24, "the English and its shadow end at the room's edge"


def test_a_mark_with_no_word_is_cleared():
    canvas = plate()
    tr.rebuild(canvas, record(key=None), {}, Blocks(), 0, 0, 0, "x")
    assert not {canvas.at(p) for p in paint.points((0, 0, W, H))} & {INK, SHADE}


def test_a_label_wider_than_its_room_is_refused_not_cut():
    with pytest.raises(TextureTextError, match=r"r:1: 'Gone fishing' is .* nothing is cut"):
        tr.rebuild(plate(), record(), {"w": Entry("rec@x.w", "Gone fishing", "r:1")}, Blocks(),
                   0, 0, 0, "x")  # fmt: skip


def test_a_record_takes_all_its_labels_or_none():
    entries = [Entry("rec@FS_WAL.size", "Size", "r:1")]
    with pytest.raises(TextureTextError, match="takes exactly"):
        tr.records(None, None, Blocks(), entries)


def test_a_label_set_beside_another_is_not_smeared_by_its_clear():
    """The neighbour's box overlaps this label's on a row this label's shadow is set in, and
    its Japanese starts one column after that shadow: cleared after the English was set, it
    would refill from the shadow."""
    canvas = plate((range(20, 30), range(6, 13)), (range(34, 40), range(12, 16)))
    labels = (tr.Label("w", (18, 4, 16, 12), (10, 4, 24, 12), "right", face="game"),
              tr.Label(None, (30, 12, 12, 6)))  # fmt: skip
    rec = tr.Record("x", 0, labels, shadow=True)
    tr.rebuild(canvas, rec, {"w": Entry("rec@x.w", "Go", "r:1")}, Blocks(), 0, 0, 0, "x")
    inked = {p for p in paint.points((0, 0, W, H)) if canvas.at(p) == INK}
    shade = {p for p in paint.points((0, 0, W, H)) if canvas.at(p) == SHADE}
    assert shade == {(x + 1, y + 1) for x, y in inked} - inked, "no shadow smeared beside it"


def test_a_label_taller_than_its_room_is_refused_not_cut():
    rec = record(room=(18, 4, 16, 5))
    with pytest.raises(TextureTextError, match=r"r:1: 'Go' is 7x5 px .* holds 15x4"):
        tr.rebuild(plate(), rec, {"w": Entry("rec@x.w", "Go", "r:1")}, Blocks(), 0, 0, 0, "x")


def test_a_box_with_no_paper_is_refused_by_name():
    rec = tr.Record("x", 0, (tr.Label(None, (20, 6, 1, 7)),))
    with pytest.raises(TextureTextError, match=r"x's mark at \(20, 6, 1, 7\) shows no paper"):
        tr.rebuild(plate(), rec, {}, Blocks(), 0, 0, 0, "x")
