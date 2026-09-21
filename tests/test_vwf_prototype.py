"""`TXT-05`'s font build, in the parts that decide what a cell means.

`tools/vwf/build_prototype.py` is a script and not a package member, so it is loaded from
its path here. What is asked of it:

* **A cell carries pixels and a width, and the Japanese script reads both.** The sheet and
  the advance table are one array each, indexed by cell id, and the hooked renderer reads
  them for a still-Japanese page exactly as it does for an English one. So no cell the
  script draws may change in either -- `place_font` is where that is decided and
  `narrowed_cells` is the half nothing was checking.
* **The edit set is the runs that really differ.** `byte_runs` is what turns a patched
  blob into `edits.json` entries, and it now merges over `boku.ppf.differing_spans`; the
  merge has to survive that scanner's own block boundaries.

The two tests over the real sheet skip without `disc/`; the rest need nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from pathlib import Path

import pytest

from boku.archive import EXE_NAME, Archive
from boku.ppf import _SPAN_BLOCK, differing_spans
from boku.text import SiteIndex

REPO_ROOT = Path(__file__).resolve().parent.parent


@cache
def vwf_prototype():
    """`tools/vwf/build_prototype.py` as a module, loaded from its path once."""
    path = REPO_ROOT / "tools" / "vwf" / "build_prototype.py"
    spec = importlib.util.spec_from_file_location("build_prototype", path)
    assert spec and spec.loader, f"{path} is not importable"
    module = importlib.util.module_from_spec(spec)
    # Registered before it is run: `Layout` is a dataclass in a module using postponed
    # annotations, and `dataclasses` resolves those through `sys.modules[__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def vwf_layout(**fields):
    """The renderer's own geometry and font settings, with the build's defaults."""
    return vwf_prototype().Layout(**fields)


# --- a cell the Japanese draws keeps its width --------------------------------------------------


def test_a_drawn_cell_whose_advance_changed_is_named_with_its_character():
    """The gate itself, at the narrowest input: two cells, one of them drawn."""
    tool = vwf_prototype()
    fixed = vwf_layout().fixed_advance
    table = [fixed, fixed - 5, fixed]
    cells = {"A": 1, "B": 2}

    assert tool.narrowed_cells(table, cells, {1}, fixed) == [(1, "A")]
    assert tool.narrowed_cells(table, cells, {2}, fixed) == [], "cell 2 steps the stock width"
    assert tool.narrowed_cells(table, cells, set(), fixed) == [], "nothing drawn, nothing clashes"
    # A cell nobody claims still has a width, and a Japanese page still steps by it.
    assert tool.narrowed_cells([fixed, 3], {}, {1}, fixed) == [(1, "")]


@pytest.mark.parametrize("advance_model", ["c1", "c2"])
def test_no_cell_the_script_draws_changes_width_under_either_advance_model(
    archive: Archive, site_index: SiteIndex, advance_model: str
):
    """The real sheet, the real script, both models -- and no refusal.

    This is the defect the gate was written for, measured on this dump: laying the English
    out over the game's own Latin cells gave 26 cells the Japanese still draws an English
    advance under `c1`, and one (`/`) under `c2`. Every Japanese page drawing one of them
    stepped at English widths, with no other symptom. `place_font` now moves those
    characters to cells nothing draws; that it does is what this asserts, by running the
    build's own placement rather than a copy of it.
    """
    tool = vwf_prototype()
    layout = vwf_layout(advance_model=advance_model)
    offset, size = tool.font_child_range(archive)
    sheet = tool.Sheet(archive.boku[offset : offset + size])
    font = tool.game_font(sheet, layout) | tool.load_glyph_file(tool.PLACEHOLDERS)
    drawn = set().union(
        *(
            tool.glyph_ids_in(
                (archive.exe if placed.file_name == EXE_NAME else archive.boku)[
                    placed.file_offset : placed.end
                ]
            )
            for placed in site_index.placed
        )
    )
    assert drawn, "no cell is drawn by this disc; the gate would pass over nothing"

    cells, table, redrawn = tool.place_font(sheet, layout, font, drawn)

    assert tool.narrowed_cells(table, cells, drawn, layout.fixed_advance) == []
    assert not drawn & set(redrawn.values())
    # The English really is in this font: a cell map that placed nothing would also pass.
    assert {"A", "a", "1", "/"} <= set(cells)


# --- the runs `edits.json` is made of -----------------------------------------------------------


def naive_runs(old: bytes, new: bytes, gap: int) -> list[tuple[int, int]]:
    """The specification, written out: differing bytes, runs closer than `gap` joined."""
    runs: list[list[int]] = []
    for offset, (a, b) in enumerate(zip(old, new, strict=True)):
        if a == b:
            continue
        if runs and offset - runs[-1][1] <= gap:
            runs[-1][1] = offset + 1
        else:
            runs.append([offset, offset + 1])
    return [(start, end) for start, end in runs]


def test_two_differences_are_one_run_or_two_by_the_gap_between_them():
    """The knob's own boundary: `RUN_MERGE_GAP` unchanged bytes merge, one more does not."""
    tool = vwf_prototype()
    gap = tool.RUN_MERGE_GAP
    old = bytes(gap + 8)
    near = bytearray(old)
    near[0], near[gap + 1] = 1, 1
    far = bytearray(old)
    far[0], far[gap + 2] = 1, 1

    assert tool.byte_runs(old, bytes(near)) == [(0, gap + 2)]
    assert tool.byte_runs(old, bytes(far)) == [(0, 1), (gap + 2, gap + 3)]
    assert tool.byte_runs(old, old) == []


def test_a_run_across_the_scanners_block_boundary_is_still_one_run():
    """`differing_spans` stops at each 4 KiB block; the merge has to sew those back up.

    The fixture straddles the boundary on purpose: split there, `edits.json` would carry
    two entries for one run -- harmless -- but a run split *and* then measured as two
    would also mean a `RUN_MERGE_GAP` decision made about a boundary rather than about the
    bytes, which is what this pins.
    """
    tool = vwf_prototype()
    old = bytes(2 * _SPAN_BLOCK)
    new = bytearray(old)
    new[_SPAN_BLOCK - 2 : _SPAN_BLOCK + 2] = b"\1\1\1\1"
    assert len(list(differing_spans(old, bytes(new)))) == 2, "the scanner no longer splits here"
    assert tool.byte_runs(old, bytes(new)) == [(_SPAN_BLOCK - 2, _SPAN_BLOCK + 2)]


def test_the_runs_are_the_ones_the_specification_describes():
    """A pattern of differences scattered around the gap and the block boundary.

    Compared with a plain per-byte reading of the rule rather than with a list written
    here: the point of the change is that the blocked scanner and the loop agree, and a
    transcribed expectation would only say the author agreed with themselves.
    """
    tool = vwf_prototype()
    gap = tool.RUN_MERGE_GAP
    size = 2 * _SPAN_BLOCK + 64
    old = bytes(size)
    new = bytearray(old)
    for offset in (0, 3, 4 + gap, _SPAN_BLOCK - 1, _SPAN_BLOCK, _SPAN_BLOCK + gap + 3, size - 1):
        new[offset] = 0xFF
    assert tool.byte_runs(old, bytes(new)) == naive_runs(old, bytes(new), gap)


def test_two_blobs_of_different_lengths_are_refused():
    tool = vwf_prototype()
    with pytest.raises(tool.BuildRefused, match="byte_runs"):
        tool.byte_runs(b"\0", b"\0\0")
