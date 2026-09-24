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
import re
import struct
import sys
from functools import cache
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.archive import ARCHIVE_NAME, EXE_NAME, Archive, parse_pack
from boku.boxes import box_for
from boku.disc import DiscError, DiscWriter, form1_sectors
from boku.edc import FORM1_DATA_SIZE
from boku.movie_block import BLOCK_LBA, BLOCK_RAM, RECORD_SIZE
from boku.ppf import _SPAN_BLOCK, differing_spans
from boku.relocate import padded
from boku.text import SiteIndex

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


NEEDS_ARMIPS = pytest.mark.skipif(
    not vwf_prototype().DEFAULT_ARMIPS.exists(), reason="needs armips to assemble the patch"
)


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


def test_an_english_advance_equal_to_the_stock_pitch_is_refused():
    """The table holds `fixed_advance` for every cell that is not English, and the
    fixed-pitch walkers read that value as "use this surface's own stock pitch"
    (`asm/vwf.asm`, `vwf_lookup_at`). An English glyph advancing exactly that much would be
    drawn at 12 on a menu instead of 14 -- so the font is refused, not the walker trusted."""
    tool = vwf_prototype()
    layout = vwf_layout()
    blank = tuple([0] * tool.CELL)

    class NoSheet:
        def get(self, glyph_id):
            return ()

    wide = tool.Glyph((0xFFF, *blank[1:]), layout.fixed_advance)
    narrow = tool.Glyph((0xFFF, *blank[1:]), layout.fixed_advance - 1)
    tool.place_font(NoSheet(), layout, {"W": narrow}, set())
    with pytest.raises(tool.BuildRefused, match="stock pitch"):
        tool.place_font(NoSheet(), layout, {"W": wide}, set())


def test_a_fixture_wider_than_its_surface_s_box_is_refused():
    """The prototype's in-place fixtures meet the same measured box the build and lint use
    (`research/data/text-boxes.tsv`); a fixture running under a frame is a build error."""
    tool = vwf_prototype()
    box = box_for("exe@80046214.0").spec
    blank = tuple([0] * tool.CELL)
    font = {"M": tool.Glyph(blank, 10), " ": tool.Glyph(blank, 4)}
    cells = {"M": 300, " ": 10}
    raw = bytes(2 * 30) + b"\x00\x80"
    fits = "M" * (box.width // 10)
    tool.encode_array_item(
        tool.LineSpec("exe@80046214.0", "fixture", False, False, fits),
        raw,
        font,
        cells,
        vwf_layout(),
    )
    with pytest.raises(tool.BuildRefused, match="px"):
        tool.encode_array_item(
            tool.LineSpec("exe@80046214.0", "fixture", False, False, fits + "M"),
            raw,
            font,
            cells,
            vwf_layout(),
        )


def test_a_description_fixture_breaks_where_it_says_up_to_its_box_s_lines():
    """An item description's box holds `lines` lines (`text-boxes.tsv`); a fixture's `\\n`
    is a `0x8001` there, and one line more or a one-line surface refuses it."""
    tool = vwf_prototype()
    blank = tuple([0] * tool.CELL)
    font = {"a": tool.Glyph(blank, 6), " ": tool.Glyph(blank, 4)}
    cells = {"a": 300, " ": 10}
    raw = bytes(2 * 20) + b"\x00\x80"

    def encode(site, text):
        spec = tool.LineSpec(site, "fixture", False, False, text)
        return tool.encode_array_item(spec, raw, font, cells, vwf_layout())[0]

    words = list(struct.unpack("<21H", encode("exe@80046398.1", "aa\naa\na")))
    assert words[:8] == [300, 300, 0x8001, 300, 300, 0x8001, 300, 10]
    assert words[-1] == 0x8000
    lines = box_for("exe@80046398.1").lines
    encode("exe@80046398.1", "\n".join("a" * lines))
    with pytest.raises(tool.BuildRefused, match="lines"):
        encode("exe@80046398.1", "\n".join("a" * (lines + 1)))
    with pytest.raises(tool.BuildRefused, match="holds 1"):
        encode("exe@80046214.0", "a\na")


JAL_GLYPH_DRAW = 0x0C000000 | ((0x8002BA2C >> 2) & 0x3FFFFFF)
JAL_OTHER = 0x0C000000 | ((0x80011000 >> 2) & 0x3FFFFFF)
NOP = 0
ADDIU_A0_ZERO = 0x24040000  # addiu a0,zero,imm
ANDI_A0_V0 = 0x30440000  # andi a0,v0,imm
MOVE_A0_S0 = 0x02002021  # addu a0,s0,zero
BNE_V0_ZERO = 0x14400000  # bne v0,zero,+imm


def a0_of(words, site, entries=None):
    return vwf_prototype()._a0_immediate(words, site, entries or {})


def test_an_immediate_id_is_found_anywhere_in_the_draw_s_block():
    """TITLE's save-date drawer sets its first id far above the draw, arithmetic between."""
    words = [ADDIU_A0_ZERO | 0x3C, *[NOP] * 20, JAL_GLYPH_DRAW, NOP]
    assert a0_of(words, 21) == {(0x3C, 1)}


@pytest.mark.parametrize(
    ("words", "site", "entries", "why"),
    [
        # a call between: a0 is whatever the call left
        ([ADDIU_A0_ZERO | 0x3C, JAL_OTHER, NOP, NOP, JAL_GLYPH_DRAW, NOP], 4, None, "call"),
        # the immediate sits in an earlier call's delay slot: it was that call's argument
        ([JAL_OTHER, ADDIU_A0_ZERO | 0x3C, NOP, JAL_GLYPH_DRAW, NOP], 3, None, "call's slot"),
        # a way in nobody can read (a jump table) between the write and the draw
        ([ADDIU_A0_ZERO | 0x3C, NOP, NOP, JAL_GLYPH_DRAW, NOP], 3, {2: [-1]}, "table"),
        # a0 computed after the immediate
        ([ADDIU_A0_ZERO | 5, ANDI_A0_V0 | 0xFF, JAL_GLYPH_DRAW, NOP], 2, None, "andi"),
        # a0 set in the draw's own delay slot, by a move
        ([ADDIU_A0_ZERO | 5, JAL_GLYPH_DRAW, MOVE_A0_S0], 1, None, "slot move"),
    ],
)
def test_a0_not_proven_immediate_is_reported_unknown(words, site, entries, why):
    """Unknown is safe -- the site goes to the walker audit (`tests/test_real_glyph_sites.py`);
    a wrong immediate is not: the draw's real ids would be protected by nothing."""
    assert a0_of(words, site, entries) is None, why


def test_a_conditional_branch_s_fallthrough_keeps_its_block():
    """Falling through a branch does not leave the block: the id set above it still holds."""
    words = [ADDIU_A0_ZERO | 0x3C, BNE_V0_ZERO | 8, NOP, NOP, JAL_GLYPH_DRAW, NOP]
    assert a0_of(words, 4) == {(0x3C, 1)}


def test_every_path_s_id_is_collected():
    """`count_label_draw`'s shape: a branch to the draw carries one id in its delay slot, the
    fall-through another; both are ids the code draws."""
    # 0: beq zero,zero,+2 (to 3) with a0=0x26A in its slot; 2: a0=0x4B9; 3: the draw
    words = [0x10000002, ADDIU_A0_ZERO | 0x26A, ADDIU_A0_ZERO | 0x4B9, JAL_GLYPH_DRAW, NOP]
    assert a0_of(words, 3, {3: [0]}) == {(0x26A, 1), (0x4B9, 1)}


def test_a_function_entry_is_not_walked_into_its_callers():
    """A function that passes its caller's `a0` to the draw: the one caller in this image
    sets an immediate, but another image or a `jalr` can call it with anything."""
    tool = vwf_prototype()
    base = 0x80010000
    jal_f = 0x0C000000 | (((base + 16) >> 2) & 0x3FFFFFF)  # jal F (word 4)
    jr_ra = 0x03E00008
    words = [jal_f, ADDIU_A0_ZERO | 0x3C, jr_ra, NOP, JAL_GLYPH_DRAW, NOP]
    assert a0_of(words, 4, tool.branch_entries(words, base)) is None


def test_only_the_digit_base_is_read_as_digits():
    tool = vwf_prototype()
    digits = 0x24440000 | tool.DIGIT_BASE  # addiu a0,v0,0x34
    other = 0x24440000 | 0x1234  # addiu a0,v0,0x1234: an address, not a digit
    assert a0_of([digits, JAL_GLYPH_DRAW, NOP], 1) == {(tool.DIGIT_BASE, 10)}
    assert a0_of([other, JAL_GLYPH_DRAW, NOP], 1) is None


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


MOVE_A3_ZERO = 0x00003821
"""`addu a3, zero, zero`: the retail word at `SELECT_HAND_ARG`."""
ADDIU_A3_ZERO = 0x24070000  # addiu a3,zero,imm


@NEEDS_IMPORT
@NEEDS_ARMIPS
@pytest.mark.parametrize("cursor", ["right", "down"])
def test_the_select_draws_the_game_s_own_sideways_hand_and_leaves_the_shared_one_alone(
    tmp_path, monkeypatch, cursor
):
    """The hand is one sprite of `ONMEM.BIN`'s resident UI sheet, and every screen that
    points at a button draws it. The build used to turn that sprite a quarter turn so the
    select rows got a hand pointing right -- and the settings and load screens' hand,
    which pointed down at the stone Back button, pointed sideways at nothing (Jay,
    DuckStation, 2026-09-23). The sheet already holds a right-pointing hand (record 0, the
    title menu's and the file list's); `0x80042B64` draws it when its `a3` is non-zero. So
    the select passes `a3 = 1`, and neither the sprite table nor the sheet is touched.
    """
    tool = vwf_prototype()
    archive = Archive(REPO_ROOT / "disc")
    member = archive.member(tool.FONT_MEMBER)
    blob = archive.blob(member)
    pack = parse_pack(blob)
    shared = {
        child: (member.offset + pack.entries[child][0], pack.entries[child][1])
        for child in (tool.SPRITE_TABLE_CHILD, tool.UI_SHEET_CHILD)
    }
    rects = tool.sprite_rects(blob, *pack.entries[tool.SPRITE_TABLE_CHILD])
    assert rects[tool.SIDE_HAND_SPRITE][2] == tool.CURSOR_WIDTH["right"]
    assert rects[tool.DOWN_HAND_SPRITE][2] == tool.CURSOR_WIDTH["down"]

    captured: dict[str, tuple] = {}
    assemble = tool.assemble

    def capture(*arguments, **keywords):
        captured["it"] = assemble(*arguments, **keywords)
        return captured["it"]

    monkeypatch.setattr(tool, "assemble", capture)
    build_without_a_disc(tool, tmp_path, monkeypatch, cursor=cursor)
    document = json.loads((tmp_path / tool.EDITS_NAME).read_text(encoding="utf-8"))
    touched = [
        (child, edit["reason"])
        for edit in document["edits"]
        if edit["file"] == ARCHIVE_NAME
        for child, (start, size) in shared.items()
        if edit["offset"] < start + size and start < edit["offset"] + len(edit["old"]) // 2
    ]
    assert touched == [], f"the shared hand is edited for every screen that draws it: {touched}"

    images, _ = captured["it"]
    site = tool.SELECT_HAND_ARG - tool.EXE_LOAD_BIAS
    (stock,) = struct.unpack_from("<I", archive.exe, site)
    (patched,) = struct.unpack_from("<I", images[EXE_NAME], site)
    assert stock == MOVE_A3_ZERO, "the retail select does not choose its hand here"
    side = {"right": 1, "down": 0}[cursor]
    assert patched == ADDIU_A3_ZERO | side, f"--cursor {cursor}: 0x{patched:08X} is the wrong hand"


@NEEDS_IMPORT
@pytest.mark.parametrize(("cursor", "sprite"), [("right", 0), ("down", 1)])
def test_a_hand_of_another_width_than_the_offset_assumes_is_refused(monkeypatch, cursor, sprite):
    """`sel_cursor_dx` is `CURSOR_WIDTH` plus the gap, so a table whose hand is one pixel
    narrower than that would draw it a pixel off its row -- the narrowest table that must
    stop the build."""
    tool = vwf_prototype()
    archive = Archive(REPO_ROOT / "disc")
    member = archive.member(tool.FONT_MEMBER)
    blob = archive.blob(member)
    rects = tool.sprite_rects(blob, *parse_pack(blob).entries[tool.SPRITE_TABLE_CHILD])
    tool.select_hand(archive, cursor)
    x, y, width, height = rects[sprite]
    narrower = [*rects[:sprite], (x, y, width - 1, height), *rects[sprite + 1 :]]
    monkeypatch.setattr(tool, "sprite_rects", lambda *_: narrower)
    with pytest.raises(tool.BuildRefused, match=rf"sprite {sprite} is not the {width}-px"):
        tool.select_hand(archive, cursor)


def test_the_cursor_offset_follows_the_hand_the_build_installs():
    """`--cursor down` alone kept the sideways hand's offset, and the invariant that they go
    together lived only in `--help`: the stock sprite is 16 px wide and the sideways one 24,
    so the narrower hand was drawn eight pixels further from its row than it belongs."""
    right, down = vwf_layout(), vwf_layout(cursor="down")
    assert right.cursor == "right" and down.cursor == "down"
    assert -right.sel_cursor_dx >= 24, "the sideways hand is 24 px wide and sits left of the row"
    assert -down.sel_cursor_dx >= 16, "the stock hand is 16 px wide and sits left of the row"
    assert down.sel_cursor_dx > right.sel_cursor_dx, "the narrower hand sits nearer its row"
    assert vwf_layout(cursor="down", sel_cursor_dx=-30).sel_cursor_dx == -30, "--sel-cursor-dx wins"


# --- the movie block, its sectors and the hooks that read it -------------------------------------


class _Sectors:
    """A `DiscWriter` reduced to what `write_movie_block` uses: what the span at
    `BLOCK_LBA` reads back (or the error reading it raises), and the sectors written."""

    sector_count = 330_000
    """A whole disc: the bounds half of `verify_sectors` is its own tests' business."""

    write_data_sectors = DiscWriter.write_data_sectors
    """The real splitter, so this fake takes only the one-sector write under it."""

    def __init__(self, span: bytes = b"", raises: Exception | None = None) -> None:
        self.span = span
        self.raises = raises
        self.written: list[tuple[int, bytes]] = []

    def read_form1_span(self, lba: int, sectors: int) -> bytes:
        assert lba == BLOCK_LBA, f"the span read starts at {lba}; the block is at {BLOCK_LBA}"
        if self.raises is not None:
            raise self.raises
        return self.span.ljust(FORM1_DATA_SIZE * sectors, b"\0")

    def write_data_sector(self, lba: int, data: bytes):
        self.written.append((lba, data))
        return None


def test_a_sector_at_the_blocks_lba_that_is_no_longer_filler_stops_the_write():
    """`write_data_sector` converts zero filler and refuses XA, but it overwrites a Form 1
    sector without a word -- so a member the relocation allocator has already put at
    `BLOCK_LBA`, or a block from an earlier build, is read back first. One non-zero byte in
    the span is the narrowest image that must stop it, and nothing may be written before
    the refusal."""
    tool = vwf_prototype()
    writer = _Sectors(b"\x01")
    with pytest.raises(tool.BuildRefused, match=f"LBA {BLOCK_LBA}\\+0x0 holds 01"):
        tool.write_movie_block(writer, bytes(64), tool.Ledger())
    assert writer.written == [], "sectors were written before the span was refused"


def test_filler_takes_the_block_one_padded_sector_at_a_time():
    tool = vwf_prototype()
    block = bytes(range(256)) * 12  # 3,072 bytes: two sectors, the second mostly padding
    writer = _Sectors()
    tool.write_movie_block(writer, block, tool.Ledger())
    assert form1_sectors(len(block)) == 2, "the fixture no longer straddles a sector boundary"
    assert [lba for lba, _ in writer.written] == [BLOCK_LBA, BLOCK_LBA + 1]
    assert b"".join(data for _, data in writer.written) == padded(block)


def test_a_span_that_cannot_be_read_as_filler_is_a_refusal_not_a_traceback():
    """`read_form1_span` raises `DiscError` on a Form 2 sector carrying real-time data --
    an image whose LBA 1040 is XA. That is a build input being wrong, which `main` reports;
    it reached the terminal as a traceback, with nothing said about what was written."""
    tool = vwf_prototype()
    writer = _Sectors(raises=DiscError("sector 1040 is Form 2 and not zero-filled"))
    with pytest.raises(tool.BuildRefused, match="Nothing further was written"):
        tool.write_movie_block(writer, bytes(64), tool.Ledger())


def test_a_font_that_cannot_draw_a_cue_is_a_refusal_naming_the_row(tmp_path):
    """`--font` is a build input and the cue file is text: a glyph file missing one of a
    cue's characters is the lint's `cue-unencodable`, reported with the file and line, and
    never a `BlockError` out of `main` as a traceback."""
    tool = vwf_prototype()
    cues = tmp_path / "movies.txt"
    cues.write_text("# a note\nM60\t1\t2\tab\n", encoding="utf-8")
    blank = tool.Glyph((0,) * tool.CELL, 4)
    with pytest.raises(tool.BuildRefused, match=r"movies\.txt:2 M60@1 the font has no glyph"):
        tool.movie_block_for({"a": blank}, cues, b"")


def test_a_cue_file_that_is_not_there_is_a_refusal(tmp_path):
    tool = vwf_prototype()
    with pytest.raises(tool.BuildRefused, match="the movie cues"):
        tool.movie_block_for({}, tmp_path / "missing.txt", b"")


def test_the_build_defines_every_equate_movie_asm_leaves_to_it():
    """The `-equ` contract, read from the assembly's half of it: the `MOVIE_SUB_*` names (and
    bug sumo's `SUMO_PEN_INDENT`) that `movie.asm` and the clip subtitles' `voice.asm` and
    `voice_resident.asm`, which read the same block, use and never
    define themselves are exactly the ones `movie_equates` supplies, so one added there fails
    here rather than inside armips."""
    tool = vwf_prototype()
    source = "\n".join(
        (tool.ASM.parent / name).read_text(encoding="utf-8")
        for name in ("movie.asm", "voice.asm", "voice_resident.asm")
    )
    code = "\n".join(line.split(";", 1)[0] for line in source.splitlines())
    defined = set(re.findall(r"^\s*(\w+)\s+equ\s", code, re.M))
    used = set(re.findall(r"\b(?:MOVIE_SUB|SUMO_PEN)_\w+", code)) - defined
    assert used, "movie.asm defines every name it uses; the parse lost the source"
    assert set(tool.movie_equates(bytes(FORM1_DATA_SIZE))) == used
    equates = tool.movie_equates(bytes(FORM1_DATA_SIZE + 1))
    assert equates["MOVIE_SUB_BLOCK"] == BLOCK_RAM and equates["MOVIE_SUB_LBA"] == BLOCK_LBA
    assert equates["MOVIE_SUB_SECTORS"] == 2, "a byte past the sector is another sector to read"
    assert 1 << equates["MOVIE_SUB_RECORD_SHIFT"] == RECORD_SIZE


def test_a_word_in_any_block_the_manifest_hashes_is_left_out_of_the_word_list():
    """`changed_words` takes both the free-space gap and the movie island; a word in either
    is the block's business (the manifest hashes it), a word outside both is a row."""
    tool = vwf_prototype()
    stock = bytes(16)
    patched = bytearray(stock)
    for offset in (0, 4, 8, 12):
        patched[offset] = 1
    gap = tool.Region(range(0, 4), {"sha1": "the gap's"})
    island = tool.Region(range(8, 12), {"sha1": "the island's"})

    found = tool.changed_words(stock, bytes(patched), gap, island)
    assert [word["file"] for word in found] == ["0x4", "0xC"]
    assert found[0] == {
        "ram": f"0x{4 + tool.EXE_LOAD_BIAS:08X}",
        "file": "0x4",
        "old": "00 00 00 00",
        "new": "01 00 00 00",
    }
    assert len(tool.changed_words(stock, bytes(patched))) == 4, "no gap, no word dropped"


# --- what the patch promises and what the image is given ----------------------------------------


class _WalkEntry:
    """A `DiscWriter.walk()` entry, reduced to what the write path reads off one."""

    def __init__(self, path: str) -> None:
        self.path, self.lba, self.size = path, 0, 0


class _NoDisc:
    """`DiscWriter` and `DiscImage` with the 660 MB image taken out of them."""

    sector_count = 330_000
    """A whole disc, so `verify_sectors`' bounds check has an image to bound against."""

    write_data_sectors = DiscWriter.write_data_sectors

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

    def read_form1_span(self, lba, sectors):
        """The relocation arena as shipped: zero filler (`write_movie_block` reads it)."""
        return bytes(FORM1_DATA_SIZE * sectors)

    def write_data_sector(self, lba, data):
        return None


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
        "movie_cues": str(tool.CUE_FILE),
        "movie_panel": tool.PANEL_STYLE,
        "clip_subs": str(tool.clip_subs.CLIP_FILE),
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


def build_without_a_disc(tool, out: Path, monkeypatch, record=None, **extra) -> dict:
    """The build for real -- armips, the font, the lines -- with only the 660 MB copy and
    the sector writer taken out. `record` stands in for `replace_range`."""
    monkeypatch.setattr(tool, "DiscWriter", _NoDisc)
    monkeypatch.setattr(tool, "DiscImage", _NoDisc)
    monkeypatch.setattr(tool, "replace_range", record or (lambda *arguments: None))
    monkeypatch.setattr(tool.shutil, "copyfile", lambda source, target: Path(target).touch())
    return tool.build(prototype_arguments(tool, out, **extra))


MOVIE_PLAYER = range(0x80034000, 0x80035200)
"""The movie player's code (`research/movies.md` § 2.1), coarse on purpose: the three hook
sites are somewhere in it, and this test may not be a copy of where `movie_sites` looks."""


@NEEDS_IMPORT
@NEEDS_ARMIPS
def test_the_edit_set_carries_the_movie_hooks_the_islands_and_the_block_they_read(
    tmp_path, monkeypatch
):
    """`FMV-04` milestone 2: `boku build --vwf` gets the whole of the movie subtitles or
    none of it. The executable the edit set rebuilds from the stock one is the image's,
    byte for byte -- hooks and both islands included -- and the block they read is its
    `sectors` entry at `BLOCK_LBA`, the same bytes this script writes into its own image.
    """
    tool = vwf_prototype()
    blocks: list[bytes] = []
    monkeypatch.setattr(
        tool, "write_movie_block", lambda writer, block, ledger: blocks.append(block)
    )
    captured: dict[str, tuple] = {}
    assemble = tool.assemble

    def capture(*arguments, **keywords):
        captured["it"] = assemble(*arguments, **keywords)
        return captured["it"]

    monkeypatch.setattr(tool, "assemble", capture)
    manifest = build_without_a_disc(tool, tmp_path, monkeypatch)
    document = json.loads((tmp_path / tool.EDITS_NAME).read_text(encoding="utf-8"))

    rebuilt = bytearray((REPO_ROOT / "disc" / "files" / EXE_NAME).read_bytes())
    for edit in document["edits"]:
        if edit["file"] == EXE_NAME:
            old, new = bytes.fromhex(edit["old"]), bytes.fromhex(edit["new"])
            assert rebuilt[edit["offset"] : edit["offset"] + len(old)] == old
            rebuilt[edit["offset"] : edit["offset"] + len(new)] = new
    images, _ = captured["it"]
    assert bytes(rebuilt) == images[EXE_NAME], "the edit set is not the image's executable"
    hooked = [word for word in manifest["exe_words"] if int(word["ram"], 16) in MOVIE_PLAYER]
    assert len(hooked) >= 3, "the image carries no movie hook; this would pass over nothing"
    assert len(document["movie_subtitles"]["islands"]) == 2

    (sector,) = document["sectors"]
    (block,) = blocks
    assert sector["lba"] == BLOCK_LBA == document["movie_subtitles"]["lba"]
    assert bytes.fromhex(sector["new"]) == padded(block)
    assert document["movie_subtitles"]["sha1"] == manifest["movie_subtitles"]["sha1"]


@NEEDS_IMPORT
@NEEDS_ARMIPS
def test_two_executables_differing_only_inside_the_island_are_two_manifests(tmp_path, monkeypatch):
    """The manifest lists every changed word outside the gap and the island, and carries
    those two blocks as a SHA-1 each instead. The island had no hash: an executable whose
    `movie_sub_blit` lost an instruction described itself exactly as one that had not.
    """
    tool = vwf_prototype()
    captured: dict[str, tuple] = {}
    assemble = tool.assemble

    def capture(*arguments, **keywords):
        captured["it"] = assemble(*arguments, **keywords)
        return captured["it"]

    monkeypatch.setattr(tool, "assemble", capture)
    first = build_without_a_disc(tool, tmp_path / "a", monkeypatch)

    images, symbols = captured["it"]
    exe = bytearray(images[EXE_NAME])
    site = symbols["movie_sub_blit"] - tool.EXE_LOAD_BIAS
    assert exe[site : site + 4] != bytes(4), "the blit's first instruction is already a nop"
    exe[site : site + 4] = bytes(4)
    monkeypatch.setattr(
        tool, "assemble", lambda *_, **__: ({**images, EXE_NAME: bytes(exe)}, symbols)
    )
    second = build_without_a_disc(tool, tmp_path / "b", monkeypatch)

    assert first["exe_words"] == second["exe_words"], "the word list sees inside the island"
    assert first["result_sha1"] == second["result_sha1"], "no image is written here"
    assert [key for key in first if first[key] != second[key]] == ["movie_subtitles"]
    was, now = first["movie_subtitles"]["islands"], second["movie_subtitles"]["islands"]
    assert was[0]["sha1"] != now[0]["sha1"] and was[1] == now[1]


@NEEDS_IMPORT
@NEEDS_ARMIPS
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

    build_without_a_disc(tool, tmp_path, monkeypatch, record)

    document = json.loads((tmp_path / tool.EDITS_NAME).read_text(encoding="utf-8"))
    assert any(edit["file"] == ARCHIVE_NAME for edit in document["edits"]), (
        "the default build promised no archive edit; this gate would pass over nothing"
    )
    for edit in document["edits"]:
        start, length = edit["offset"], len(edit["old"]) // 2
        assert any(
            name == edit["file"] and base <= start and start + length <= base + size
            for name, base, size in written
        ), f"promised in {tool.EDITS_NAME} and never written: {edit['reason']}"
