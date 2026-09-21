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

import argparse
import importlib.util
import json
import sys
from functools import cache
from pathlib import Path

import pytest

from boku.archive import ARCHIVE_NAME, EXE_NAME, Archive, parse_pack
from boku.ppf import _SPAN_BLOCK, differing_spans
from boku.text import SiteIndex
from boku.tim import parse_exact

REPO_ROOT = Path(__file__).resolve().parent.parent
NEEDS_IMPORT = pytest.mark.skipif(
    not (REPO_ROOT / "disc" / "files").exists(), reason="needs the import"
)


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


# --- the select cursor and the glyph file ----------------------------------------------------


def test_a_quarter_turn_counter_clockwise_sends_what_pointed_down_to_the_right():
    """A 2 x 3 block whose bottom row is the "finger": after the turn it is the right column."""
    vwf = vwf_prototype()
    a, b, c, d, e, f = b"abcdef"
    turned = vwf.rotate_ccw(bytes([a, b, c, d, e, f]), 2, 3)
    assert turned == bytes([b, d, f, a, c, e])
    # Twice more and once again is the identity, which pins the size bookkeeping.
    back = turned
    for width, height in ((3, 2), (2, 3), (3, 2)):
        back = vwf.rotate_ccw(back, width, height)
    assert back == bytes([a, b, c, d, e, f])


def test_a_glyph_may_carry_a_left_bearing_but_its_advance_must_cover_ink_and_shadow(tmp_path):
    """The boundary, on a glyph inked to column 3: the renderer draws every glyph twice,
    one column apart, so the shadow lands on column 4 and the next glyph may not start
    before column 5. Advance 4 is the narrowest advance that puts a glyph on a shadow."""
    vwf = vwf_prototype()
    rows = ["............"] + ["..##........"] * 9 + ["............"] * 2
    path = tmp_path / "glyphs.txt"

    def load(advance: int):
        path.write_text(
            f"glyph U+300C advance {advance}\n" + "\n".join(rows) + "\n", encoding="utf-8"
        )
        return vwf.load_glyph_file(path)["「"]

    glyph = load(5)
    assert glyph.ink == (2, 3) and glyph.advance == 5
    with pytest.raises(vwf.BuildRefused, match="advance must cover the ink"):
        load(4)


def test_the_placeholder_sheet_leaves_room_for_every_closing_mark_s_shadow():
    """`』` shipped at advance 5 over ink to column 4, so its shadow was drawn under the
    first column of whatever followed it -- the one glyph in the file that broke the rule
    `「` 7, `『` 8 and `」` 4 all keep. Loaded rather than eyeballed."""
    vwf = vwf_prototype()
    font = vwf.load_glyph_file(vwf.PLACEHOLDERS)
    assert font, "the placeholder sheet is empty; this would pass over nothing"
    for character, glyph in sorted(font.items()):
        if glyph.ink:
            assert glyph.advance >= glyph.ink[1] + 2, f"{character!r} sits on its own shadow"


@NEEDS_IMPORT
def test_the_hand_is_turned_in_place_and_its_record_follows():
    """On the real sheet, in pixels: the only pixels that change are the cell the hand
    vacates and the cell it claims, the new cell is the old one turned, and the rows it no
    longer covers are left transparent. The record follows the pixels.

    Every number is read out of the pack and the TIM -- the child's offset, the hand's
    `(x, y, w, h)`, the sheet's stride -- so a sheet rebuilt at another size, or a record
    moved, moves this test with it instead of past it.
    """
    vwf = vwf_prototype()
    archive = Archive(REPO_ROOT / "disc")
    member = archive.member(vwf.FONT_MEMBER)
    blob = archive.blob(member)
    pack = parse_pack(blob)
    table_offset, table_size = pack.entries[vwf.SPRITE_TABLE_CHILD]
    sheet_offset, sheet_size = pack.entries[vwf.UI_SHEET_CHILD]
    x, y, w, h = vwf.sprite_rects(blob, table_offset, table_size)[vwf.HAND_SPRITE]

    ranges, described = vwf.cursor_edits(archive)
    assert described == {"sprite": vwf.HAND_SPRITE, "was": f"{w}x{h}", "now": f"{h}x{w}"}

    record = next(patch for patch in ranges if "record" in patch.reason)
    assert record.file_name == ARCHIVE_NAME and record.base == member.offset + table_offset
    assert vwf.sprite_rects(record.new, 0, len(record.new))[vwf.HAND_SPRITE] == (x, y, h, w)

    sheet = next(patch for patch in ranges if "turned" in patch.reason)
    assert sheet.base == member.offset + sheet_offset
    assert sheet.stock == blob[sheet_offset : sheet_offset + sheet_size]
    before, after = parse_exact(sheet.stock), parse_exact(sheet.new)
    width = before.width
    old_pixels, new_pixels = before.indices(), after.indices()

    def at(pixels: bytes, rows: int, columns: int) -> bytes:
        return bytes(
            pixels[(y + row) * width + x + column]
            for row in range(rows)
            for column in range(columns)
        )

    changed = {i for i, (a, b) in enumerate(zip(old_pixels, new_pixels, strict=True)) if a != b}
    assert changed, "the sheet did not change; nothing was turned"
    hand_cells = {
        (y + row) * width + x + column
        for rows, columns in ((h, w), (w, h))
        for row in range(rows)
        for column in range(columns)
    }
    assert changed <= hand_cells, "the turn reached outside the cell it vacates and claims"
    assert at(new_pixels, w, h) == vwf.rotate_ccw(at(old_pixels, h, w), w, h)
    left = at(new_pixels, h, w)[w * w :]
    assert set(left) == {vwf.TRANSPARENT}, "the rows the hand left are not padded transparent"


@NEEDS_IMPORT
def test_a_sprite_in_the_rows_the_hand_is_turned_in_stops_the_turn(monkeypatch):
    """Ownership, not blankness, is what makes the turn safe.

    Index 0 of this sheet's CLUT is opaque white and index 1 transparent, so the padding
    beside the hand reads as `0` and no pixel test can tell it from art. The sprite table
    is what says those rows belong to nobody -- so a table that says otherwise, on either
    the cell being claimed or the cell being vacated, is a refusal.
    """
    vwf = vwf_prototype()
    archive = Archive(REPO_ROOT / "disc")
    member = archive.member(vwf.FONT_MEMBER)
    blob = archive.blob(member)
    pack = parse_pack(blob)
    table_offset, table_size = pack.entries[vwf.SPRITE_TABLE_CHILD]
    rects = vwf.sprite_rects(blob, table_offset, table_size)
    x, y, w, h = rects[vwf.HAND_SPRITE]
    assert vwf.trespassers(rects, vwf.HAND_SPRITE, (x, y, w, h), (x, y, h, w)) == [], (
        "this disc's own table already trespasses; the refusal would fire on every build"
    )

    other = next(index for index in range(len(rects)) if index != vwf.HAND_SPRITE)
    for corner in ((x + h - 1, y), (x, y + w)):
        # (right column of the turned cell, first row the old cell vacates): each is a
        # pixel exactly one of the two rectangles covers, which is the narrowest table
        # that must stop the turn.
        moved = list(rects)
        moved[other] = (*corner, 1, 1)
        monkeypatch.setattr(vwf, "sprite_rects", lambda *_, rects=moved: rects)
        with pytest.raises(vwf.BuildRefused, match=rf"sprite\(s\) \[{other}\]"):
            vwf.turn_the_hand(blob, member.offset)


def test_the_cursor_offset_follows_the_hand_the_build_installs():
    """`--cursor down` alone kept the turned hand's offset, and the invariant that they go
    together lived only in `--help`: the stock sprite is 16 px wide and the turned one 24,
    so the narrower hand was drawn eight pixels further from its row than it belongs."""
    right, down = vwf_layout(), vwf_layout(cursor="down")
    assert right.cursor == "right" and down.cursor == "down"
    assert -right.sel_cursor_dx >= 24, "the turned hand is 24 px wide and sits left of the row"
    assert -down.sel_cursor_dx >= 16, "the stock hand is 16 px wide and sits left of the row"
    assert down.sel_cursor_dx > right.sel_cursor_dx, "the narrower hand sits nearer its row"
    assert vwf_layout(cursor="down", sel_cursor_dx=-30).sel_cursor_dx == -30, "--sel-cursor-dx wins"


# --- what the patch promises and what the image is given ----------------------------------------


class _WalkEntry:
    """A `DiscWriter.walk()` entry, reduced to what the write path reads off one."""

    def __init__(self, path: str) -> None:
        self.path, self.lba, self.size = path, 0, 0


class _NoDisc:
    """`DiscWriter` and `DiscImage` with the 660 MB image taken out of them."""

    def __init__(self, path):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def walk(self):
        return [_WalkEntry(f"/{EXE_NAME}"), _WalkEntry(f"/{ARCHIVE_NAME}")]

    def flush(self):
        pass


def prototype_arguments(tool, out: Path, **extra) -> argparse.Namespace:
    """What `main` hands `build` for a default run, taken from the parser's own sources."""
    defaults = tool.Layout()
    arguments = {
        "image": str(REPO_ROOT / "disc" / "image.img"),
        "disc": str(REPO_ROOT / "disc"),
        "out": str(out),
        "lines": str(tool.DEFAULT_LINES),
        "days": None,
        "label": False,
        "font": None,
        "asm": str(tool.ASM),
        "armips": str(tool.DEFAULT_ARMIPS),
        "skip_image_hash": True,
        "edits_only": False,
        "advance_model": defaults.advance_model,
        "cursor": defaults.cursor,
    }
    for name in tool.LAYOUT_ARGUMENTS:
        arguments[name] = tool.Layout.__dataclass_fields__[name].default
    return argparse.Namespace(**(arguments | extra))


@NEEDS_IMPORT
@pytest.mark.skipif(
    not vwf_prototype().DEFAULT_ARMIPS.exists(), reason="needs armips to assemble the patch"
)
def test_every_edit_the_patch_promises_is_a_range_the_image_build_writes(tmp_path, monkeypatch):
    """`edits.json` and the prototype's own `image.img` are two renderings of one patch.

    They were assembled by two pieces of code, and the select cursor reached only the
    first: the image drew the stock downward hand while the `manifest.json` beside it said
    `cursor: 24x16`, and nothing read the image back to notice. So the build runs here for
    real -- armips, the font, the lines -- with only the copy and the sector writer taken
    out, and every entry of the `edits.json` it writes has to lie inside a range its image
    writer was handed.
    """
    tool = vwf_prototype()
    written: list[tuple[str, int, int]] = []

    def record(writer, entry, name, offset, expected, new, ledger):
        assert len(expected) == len(new), f"{name}+0x{offset:x} changes the file's length"
        written.append((entry.path.lstrip("/"), offset, len(expected)))

    monkeypatch.setattr(tool, "DiscWriter", _NoDisc)
    monkeypatch.setattr(tool, "DiscImage", _NoDisc)
    monkeypatch.setattr(tool, "replace_range", record)
    monkeypatch.setattr(tool.shutil, "copyfile", lambda source, target: Path(target).touch())
    tool.build(prototype_arguments(tool, tmp_path))

    document = json.loads((tmp_path / tool.EDITS_NAME).read_text(encoding="utf-8"))
    assert any("cursor" in str(edit["reason"]) for edit in document["edits"]), (
        "the default build promised no cursor edit; this gate would pass over nothing"
    )
    for edit in document["edits"]:
        start, length = edit["offset"], len(edit["old"]) // 2
        assert any(
            name == edit["file"] and base <= start and start + length <= base + size
            for name, base, size in written
        ), f"promised in {tool.EDITS_NAME} and never written: {edit['reason']}"
