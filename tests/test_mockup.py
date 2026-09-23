"""`PLAN TRN-08`'s render check -- `tools/vwf/mockup.py` draws what the build would insert.

What is asked of it, with no disc:

* **The pen moves by the cell map's advance** and each glyph is drawn twice, the shadow
  `SHADOW_DX` right. Measured by where a one-column glyph's ink lands, against the
  encoder's own advances.
* **A page that does not fit is drawn so that it shows**: a line past the band's count, or
  wider than its limit, in the overflow colour; the next-page pencil's zone shaded.

With the import and an edit set, one day-1 scene is drawn end to end.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache

import pytest

from boku import REPO_ROOT
from boku.layout import DIALOGUE_BAND, CellMapEncoder, measure
from boku.lint import DEFAULT_CELLS
from boku.movie_block import CELL
from boku.png import read


@cache
def mockup():
    """`tools/vwf/mockup.py` as a module, loaded from its path once."""
    path = REPO_ROOT / "tools" / "vwf" / "mockup.py"
    spec = importlib.util.spec_from_file_location("vwf_mockup", path)
    assert spec and spec.loader, f"{path} is not importable"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BAR = tuple(1 << (CELL - 1) for _ in range(CELL))
"""A glyph whose only ink is column 0, top to bottom."""


def bar_font(advances: dict[str, int]) -> CellMapEncoder:
    return CellMapEncoder({c: (index + 1, a) for index, (c, a) in enumerate(advances.items())})


def ink_columns(canvas, row: int, colour) -> list[int]:
    return [x for x in range(canvas.width) if canvas.get(x, row) == colour]


def geometry():
    """The font build's own `Layout` with its defaults -- the geometry the edit set records."""
    return mockup().vwf.Layout()


def test_the_pen_moves_by_the_cell_map_s_advance_and_the_shadow_sits_one_right():
    m = mockup()
    encoder = bar_font({"A": 5, "B": 7, "C": 3})
    canvas = m.Canvas.blank(64, CELL, m.SCENE)
    end = m.draw_run(canvas, 2, 0, "ABC", encoder, lambda cell: BAR, m.INK)
    starts = [2, 2 + encoder.advance("A"), 2 + encoder.advance("A") + encoder.advance("B")]
    assert ink_columns(canvas, 5, m.INK) == starts
    assert ink_columns(canvas, 5, m.SHADOW) == [x + m.SHADOW_DX for x in starts]
    assert end == 2 + measure(encoder, "ABC")


def test_a_character_with_no_cell_is_drawn_as_a_red_block():
    m = mockup()
    canvas = m.Canvas.blank(32, CELL, m.SCENE)
    m.draw_run(canvas, 0, 0, "?", bar_font({"A": 5}), lambda cell: BAR, m.INK)
    assert m.OVER in {canvas.get(x, CELL // 2) for x in range(canvas.width)}


def lines_drawn_in(canvas, colour, geometry, top) -> set[int]:
    """Which line slots (1-based) hold `colour` on their middle row. A glyph is taller than
    the pitch, so only the middle row belongs to one line alone."""
    slots = set()
    for slot in range(1, 8):
        y = geometry.pen_y - top + (slot - 1) * geometry.line_pitch + CELL // 2
        if y < canvas.height and colour in {canvas.get(x, y) for x in range(canvas.width)}:
            slots.add(slot)
    return slots


def test_a_line_past_the_band_s_count_is_drawn_in_the_overflow_colour():
    m = mockup()
    g = geometry()
    encoder = bar_font({"A": 5})
    lines = ["A"] * (DIALOGUE_BAND.lines + 1)
    tile = m.page_tile(lines, [5] * len(lines), "", g, DIALOGUE_BAND, encoder, lambda c: BAR)
    top = m.page_top(g)
    assert lines_drawn_in(tile, m.OVER, g, top) == {DIALOGUE_BAND.lines + 1}
    assert lines_drawn_in(tile, m.INK, g, top) == set(range(1, DIALOGUE_BAND.lines + 1))


def test_a_line_wider_than_its_limit_is_drawn_in_the_overflow_colour():
    """The limit is the box's own for that line -- the guarded line's is the narrower one."""
    m = mockup()
    g = geometry()
    encoder = bar_font({"A": 5})
    guarded = DIALOGUE_BAND.guarded_from
    widths = [DIALOGUE_BAND.width_of_line(n) for n in range(1, DIALOGUE_BAND.lines + 1)]
    widths[guarded - 1] += 1
    tile = m.page_tile(["A"] * len(widths), widths, "", g, DIALOGUE_BAND, encoder, lambda c: BAR)
    top = m.page_top(g)
    assert lines_drawn_in(tile, m.OVER, g, top) == {guarded}


def test_the_pencil_zone_starts_where_the_guarded_line_s_limit_ends():
    m = mockup()
    g = geometry()
    tile = m.page_tile([], [], "", g, DIALOGUE_BAND, bar_font({}), lambda c: BAR)
    top = m.page_top(g)
    row = g.pen_y - top + (DIALOGUE_BAND.guarded_from - 1) * g.line_pitch
    zone = ink_columns(tile, row, m.PENCIL)
    assert zone[0] == g.pen_x + DIALOGUE_BAND.guarded_width
    assert zone[-1] == g.pen_x + DIALOGUE_BAND.width - 1


def test_a_select_row_wider_than_the_select_box_is_drawn_in_the_overflow_colour():
    m = mockup()
    g = geometry()
    tile = m.select_tile(
        ["A", "A"], [g.select_width, g.select_width + 1], "", g, bar_font({"A": 5}), lambda c: BAR
    )
    top = m.select_top(g)
    first, second = (g.sel_y - top + index * g.sel_pitch + CELL // 2 for index in range(2))
    assert m.INK in {tile.get(x, first) for x in range(tile.width)}
    assert m.OVER in {tile.get(x, second) for x in range(tile.width)}


def test_a_missing_import_is_a_message_and_exit_2_not_a_traceback(tmp_path, capsys):
    out = REPO_ROOT / "work" / "test-mockup"
    assert mockup().main(["--disc", str(tmp_path / "nowhere"), "--out", str(out)]) == 2
    assert capsys.readouterr().err.startswith("mockup: ")


NEEDS_IMPORT = pytest.mark.skipif(
    not (REPO_ROOT / "disc" / "files").exists() or not DEFAULT_CELLS.is_file(),
    reason="needs the import and build/vwf/edits.json (./make.sh build-days)",
)


@NEEDS_IMPORT
def test_a_day_one_scene_is_drawn_from_the_real_sheet():
    out = REPO_ROOT / "work" / "test-mockup"
    day = REPO_ROOT / "translation" / "days" / "day01.txt"
    code = mockup().main([str(day), "--events", "E0121", "--out", str(out), "--scale", "1"])
    assert code == 0
    picture = read((out / "day01" / "E0121.png").read_bytes())
    assert picture.width == mockup().SCREEN_WIDTH
    ink = bytes(mockup().INK) + b"\xff"
    rgba = picture.rgba
    assert any(rgba[i : i + 4] == ink for i in range(0, len(rgba), 4)), "no glyph was drawn"
