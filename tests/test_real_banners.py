"""The fortune and the kite crash banner in English (`boku.code_text.BANNERS`, `asm/banners.asm`,
`PLAN TXT-05`): the days build's hooked drawers, run instruction by instruction."""

from __future__ import annotations

import struct

import pytest

from boku.archive import EXE_LOAD_BIAS, OVERLAY_LOAD_ADDRESS, Archive
from boku.boxes import box_for, box_spec_for
from boku.build import load_edit_set
from boku.code_text import (
    BANNER_CENTRE,
    BANNER_PANEL_H,
    BANNER_PANEL_W,
    BANNER_PANEL_X,
    BANNERS,
    LABEL_PITCH,
    Banner,
    banner_blob,
    lay_out_banner,
)
from boku.glyphs import END_WORD, words_of
from boku.translation import SampleScenes
from tests.mips import Machine
from tests.test_real_date_labels import ARRAYS, EDITS, GLYPH_FLUSH

FORTUNE, CRASH = "exe@80036750", "tako@440"
PANELLED = sorted(p for p, banner in BANNERS.items() if banner.retail is not None)
"""The banners whose panel is data the build widens; bug sumo's size their own
(tests/test_real_sumo_text.py)."""
FORTUNE_DRAWS, FORTUNE_LUCK = 0x8003E052, 0x8003DD1D  # asm/banners.asm's equates
TEXT_NTH = 0x800438F0


@pytest.fixture(scope="module")
def rows() -> dict[str, str]:
    return {e.line_id: " ".join(e.pages) for e in SampleScenes.from_paths([ARRAYS])}


@pytest.fixture(scope="module")
def encoder():
    if not EDITS.is_file():
        pytest.skip("no build/vwf: run `./make.sh build-days` first")
    return load_edit_set(EDITS).encoder


def _laid(rows, encoder, line_id: str):
    return lay_out_banner(line_id, rows[line_id], encoder, box_spec_for(line_id))


def _machine(archive: Archive, overlay: str | None = None) -> Machine:
    machine = Machine(stubs={GLYPH_FLUSH: []})
    machine.load(EXE_LOAD_BIAS, archive.exe)
    if overlay:
        machine.load(OVERLAY_LOAD_ADDRESS, archive.blob(archive.member(overlay)))
    return machine


def _assert_centred_line(machine: Machine, laid, prefix: str) -> None:
    english = [cell for cell in laid.words if cell != END_WORD]
    assert [draw[0] for draw in machine.draws] == english
    xs = [draw[1] for draw in machine.draws]
    assert xs == sorted(xs), "left to right"
    (width,) = laid.widths[0]
    assert xs[0] == BANNER_CENTRE - width // 2, "centred"
    assert {draw[2] for draw in machine.draws} == {BANNERS[prefix].y}
    assert len(machine.stubs[GLYPH_FLUSH]) == 1, "flushed once, as retail does"


@pytest.mark.parametrize("draws", [(1, 1, 1), (2, 1, 1), (1, 2, 2), (2, 2, 2)])
def test_the_fortune_draws_the_result_the_retail_drawer_picks(
    archive, days_built, rows, encoder, draws
):
    """The retail `fortune_draw`, run on the same draws, says which result and what it leaves
    at `FORTUNE_LUCK`; the hooked one must draw that result's English and leave the same."""
    retail = _machine(archive)
    retail.load(FORTUNE_DRAWS, bytes(draws))
    retail.call(BANNERS[FORTUNE].drawer[1])
    result = retail.read(FORTUNE_LUCK, 1)
    machine = _machine(days_built)
    machine.load(FORTUNE_DRAWS, bytes(draws))
    machine.call(BANNERS[FORTUNE].drawer[1])
    line_id = f"{FORTUNE}.{result}"
    _assert_centred_line(machine, _laid(rows, encoder, line_id), FORTUNE)
    assert machine.read(FORTUNE_LUCK, 1) == result


def test_the_crash_banner_draws_its_english(days_built, rows, encoder):
    machine = _machine(days_built, "TAKO.OVL")
    machine.call(BANNERS[CRASH].drawer[1])
    _assert_centred_line(machine, _laid(rows, encoder, f"{CRASH}.0"), CRASH)


def _panel_words(archive: Archive, banner) -> tuple[int, ...]:
    edits = banner.panel_edits()
    raw = b"".join(archive.image_bytes(image, ram, len(new)) for image, ram, new in edits)
    if banner.rect is not None:
        return struct.unpack("<4h", raw)
    return tuple(w & 0xFFFF for w in struct.unpack("<4I", raw))


@pytest.mark.parametrize("prefix", PANELLED)
def test_the_panel_edits_sit_on_the_retail_rect(archive, prefix):
    """What `panel_edits` overwrites is the retail rect the drawer's panel is drawn from."""
    banner = BANNERS[prefix]
    assert _panel_words(archive, banner) == banner.retail
    if banner.literals is not None:
        for image, ram, _ in banner.panel_edits():
            raw = archive.image_bytes(image, ram, 4)
            assert int.from_bytes(raw, "little") >> 16 == 0x2402, "addiu v0,zero,n"


@pytest.mark.parametrize("prefix", PANELLED)
def test_the_built_panel_is_wide_centred_on_the_retail_one_and_holds_the_line(days_built, prefix):
    banner = BANNERS[prefix]
    x, top, w, h = _panel_words(days_built, banner)
    rx, ry, rw, rh = banner.retail
    assert (x, w, h) == (BANNER_PANEL_X, BANNER_PANEL_W, BANNER_PANEL_H)
    assert 2 * x + w == 2 * rx + rw and 2 * top + h == 2 * ry + rh, "the same middle"
    assert top < banner.y and banner.y + LABEL_PITCH < top + h


def test_each_banner_s_box_is_inside_its_panel_and_centred():
    for prefix in PANELLED:
        box = box_for(f"{prefix}.0")
        assert box.x > BANNER_PANEL_X and box.right < BANNER_PANEL_X + BANNER_PANEL_W
        assert box.x + box.right == 2 * BANNER_CENTRE, "the line is centred, so its room is too"


def test_an_untranslated_item_is_found_where_text_nth_looks(archive):
    """One fortune row translated, the rest handed in as their retail cells: every item of
    the text is still one `0x8000` apart, so `text_nth` finds result n at item n."""
    words = {f"{FORTUNE}.2": (0x101, 0x102, END_WORD)}
    blob = banner_blob(archive, FORTUNE, words)
    machine = Machine()
    machine.load(EXE_LOAD_BIAS, archive.exe)
    text = 0x801F0000
    machine.load(text, blob)
    rows, cells = 4, 3
    for n in range(rows):
        at = machine.call(TEXT_NTH, text + 4, n)
        item = words_of(machine.ram[at - 0x80000000 : at - 0x80000000 + 2 * (cells + 1)])
        expected = (
            words[f"{FORTUNE}.{n}"]
            if n == 2
            else words_of(archive.exe_bytes(0x80036750 + 2 * cells * n, 2 * cells))
        )
        assert tuple(item[: len(expected)]) == tuple(expected), n


def test_a_sumo_banner_s_box_is_centred_where_its_line_is():
    """Bug sumo's banners size their own board, so the box the lint holds a line to must be
    centred on the x the routine centres it on."""
    for prefix, banner in BANNERS.items():
        if banner.line is None:
            continue
        box = box_for(f"{prefix}.0")
        assert box is not None and box.x + box.right == 2 * banner.centre[0], prefix


@pytest.mark.parametrize(
    "fields",
    [{}, {"line": (1, 2), "retail": (1, 2, 3, 4)}, {"retail": (1, 2, 3, 4)}],
)
def test_a_banner_has_exactly_one_shape(fields):
    with pytest.raises(ValueError, match="one of rect/literals"):
        Banner("r", ("exe", 0), **fields)
