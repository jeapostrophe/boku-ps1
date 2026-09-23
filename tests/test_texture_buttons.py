"""`boku.texture_buttons` without a disc: the stone and balloon recipes on invented images.

The textures are made here (`tests/synth_tim.py`): a grey ramp palette, entry 1 the palest and
15 the darkest, so which entries are ground, antialias and ink follows from the recipe's own
thresholds (`INK_DARK`, `SOFT`) through the palette, not from a list typed here. The real
buttons are `tests/test_real_texture_buttons.py`'s.
"""

from __future__ import annotations

import struct
from types import SimpleNamespace

import pytest

from boku import texture_buttons as tb
from boku import texture_paint as paint
from boku.archive import ARCHIVE_NAME
from boku.texture_text import Entry, TextureTextError
from boku.textures import Occurrence, Texture
from boku.tim import luminance, parse_exact
from tests import synth_tim as synth

GREYS = [0] + [(31 - 2 * k) * 0x421 for k in range(1, 16)]
"""Entry 0 transparent, then 15 greys from pale to dark (ABGR1555, equal channels)."""
PALETTE = [(31 - 2 * k) * 8 for k in range(1, 16)]


def lum(index: int) -> int:
    return luminance(parse_exact(tim_bytes(4, 1, [index] * 4)).palette_rgba(0)[index])


def tim_bytes(width: int, height: int, px: list[int]) -> bytes:
    words = GREYS + [0] * (256 - len(GREYS))
    return synth.tim(
        1, synth.pixel_block(width // 2, height, bytes(px)), clut=synth.clut_block(256, 1, words)
    )


def canvas_of(width: int, height: int, px: list[int], **kw) -> paint.Canvas:
    raw = tim_bytes(width, height, px)
    tim = parse_exact(raw)
    place = Occurrence(ARCHIVE_NAME, "\\_DATA\\X.BIN", 0, 0x1000, tim.length)
    return paint.Canvas(Texture("x", "0" * 40, tim, (place,)), **kw)


GROUND = [i for i in range(1, 16) if lum(i) >= tb.SOFT]
SOFT = next(i for i in range(1, 16) if tb.INK_DARK <= lum(i) < tb.SOFT)
INK = max(range(1, 16), key=lambda i: -lum(i))


class Blocks:
    """Each character a 3x5 block with a column of air."""

    name = "blocks"
    pitch = 6

    def measure(self, text):
        return max(0, 4 * len(text) - 1)

    def ink(self, text):
        return {(4 * n + dx, dy) for n, ch in enumerate(text) if ch != " "
                for dx in range(3) for dy in range(5)}  # fmt: skip


def stone_fixture():
    """A 48x24 stone: textured ground, a lip of ink-dark pixels on rows 19-20 (below the box),
    and "Japanese" in the box -- ink strokes with antialias to their right."""
    w, h = 48, 24
    px = [GROUND[(x * 7 + y * 3) % len(GROUND)] for y in range(h) for x in range(w)]
    for x in range(w):
        for y in (19, 20):
            px[y * w + x] = INK
    japanese = set()
    for x in range(10, 34, 5):
        for y in range(5, 14):
            px[y * w + x], px[y * w + x + 1] = INK, SOFT
            japanese |= {(x, y), (x + 1, y)}
    return canvas_of(w, h, px), japanese, tb.Button("x", "stone", (8, 4, 32, 11), 0)


def test_a_stone_changes_only_the_japanese_and_the_english():
    """Jay, 2026-09-23: the kite Back button's mock-up changed more than the hiragana's
    pixels, and the stone banded. Only the Japanese's ink and antialias may change, plus the
    English's own pixels; every other pixel of the stone -- its texture, its lip -- stays."""
    canvas, japanese, button = stone_fixture()
    tb.stone(canvas, button, Entry("btn@x.back", "Back", "b:1"), Blocks(), "the stone")
    pairs = zip(canvas.stock, canvas.pixels, strict=True)
    changed = {(i % canvas.width, i // canvas.width) for i, (a, b) in enumerate(pairs) if a != b}
    english = {p for p in paint.points(button.box) if canvas.at(p) == INK}
    assert changed - english <= japanese
    assert paint.normalised(english) == paint.normalised(paint.bold(Blocks().ink("Back")))


def test_a_stone_refills_the_japanese_from_its_own_ground():
    canvas, japanese, button = stone_fixture()
    tb.stone(canvas, button, Entry("btn@x.back", "Back", "b:1"), Blocks(), "the stone")
    refilled = {canvas.at(p) for p in japanese if canvas.at(p) != INK}
    assert refilled and refilled <= set(GROUND)
    assert not any(canvas.at(p) == SOFT for p in paint.points(button.box))


def test_a_stone_line_that_does_not_fit_the_japanese_box_is_refused():
    canvas, _, button = stone_fixture()
    with pytest.raises(TextureTextError, match=r"b:1: 'Back to the desk' is .* nothing is cut"):
        tb.stone(canvas, button, Entry("btn@x.back", "Back to the desk", "b:1"), Blocks(),
                 "the stone")  # fmt: skip


PAPER, OUTLINE, MARK, TAIL = GROUND[0], INK, INK - 1, SOFT


def balloon_fixture(w=44, h=30, spare=0):
    """An oval of paper ringed by an outline, "Japanese" in the middle, and the tail's shading
    reaching in from the outline at the bottom left; `spare` transparent columns to its right."""
    full = w + spare
    px = [0] * (full * h)
    cx, cy, rx, ry = w / 2, h / 2, w / 2 - 1, h / 2 - 1
    for y in range(h):
        for x in range(w):
            d = ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2
            if d <= 1:
                px[y * full + x] = OUTLINE if d > 0.8 else PAPER
    japanese = set()
    for x in range(12, 32, 3):
        for y in range(12, 18):
            px[y * full + x] = MARK
            japanese.add((x, y))
    tail = set()
    row = h - 4
    edge = min(x for x in range(w) if px[row * full + x] == PAPER)
    for x in (edge, edge + 1):
        px[row * full + x] = TAIL
        tail.add((x, row))
    return canvas_of(full, h, px), japanese, tail, tb.Button("x", "balloon", (0, 0, w, h), 0)


def test_a_balloon_blanks_the_label_and_sets_the_english_inside_its_paper():
    canvas, _, tail, button = balloon_fixture()
    tb.balloon(canvas, button, Entry("btn@x.a", "Go // on", "b:1"), Blocks(), "the balloon")
    marked = {p for p in paint.points(button.box) if canvas.at(p) == MARK}
    assert marked, "no English was set"
    paper = {p for p in paint.points(button.box) if canvas.stock[p[1] * canvas.width + p[0]]
             in (PAPER, MARK)} - tail  # fmt: skip
    assert paint.grown(marked, 1, 1, 1, 1) <= paper
    assert len(marked) == len(Blocks().ink("Go")) + len(Blocks().ink("on"))
    assert all(canvas.at(p) == TAIL for p in tail), "the tail's shading is not the label"


def test_a_balloon_that_cannot_hold_its_english_with_a_pixel_of_paper_is_refused():
    canvas, _, _, button = balloon_fixture()
    with pytest.raises(TextureTextError, match=r"b:1: .* cannot hold it with a pixel of paper"):
        tb.balloon(canvas, button, Entry("btn@x.a", "Belongings", "b:1"), Blocks(), "the balloon")


def test_a_button_nobody_measured_is_refused_not_ignored():
    with pytest.raises(TextureTextError, match=r"b:3: there is no button 'NOPE.back'"):
        tb.buttons(None, None, Blocks(), [Entry("btn@NOPE.back", "Back", "b:3")])


def test_an_8bpp_tim_drawn_at_4bpp_is_edited_a_nibble_at_a_time():
    """`_DATA_NIKKI_W.BIN__005450`'s shape: the header says 8bpp, the game draws 4bpp."""
    px = [(2 * i) & 0xF | ((2 * i + 1) & 0xF) << 4 for i in range(8 * 2)]
    canvas = canvas_of(8, 2, px, drawn_4bpp=True)
    assert (canvas.width, canvas.height) == (16, 2)
    assert canvas.at((3, 0)) == px[1] >> 4
    canvas.pixels[3] = 9
    (edit,) = canvas.patches()
    assert edit.new == bytes([px[1] & 0xF | 9 << 4]) and edit.old == bytes([px[1]])


ENTRY = (8, 0, 11, 30, 0, 0x41)
"""An atlas entry as the tables hold it: 11 VRAM words (44 texels at 4bpp) wide."""
TEXTURE_AT = 0x1000


def widening(extra: int):
    canvas, _, _, button = balloon_fixture(spare=extra)
    wide = tb.Button("x", "balloon", button.box, 0, widen=tb.Widen(extra, -12, ENTRY))
    return canvas, wide


def test_a_widened_balloon_holds_what_its_own_width_could_not():
    canvas, button = widening(8)
    entry = Entry("btn@x.a", "Belongings", "b:1")
    with pytest.raises(TextureTextError):
        tb.balloon(balloon_fixture()[0], balloon_fixture()[3], entry, Blocks(), "the balloon")
    width = canvas.width
    tb.balloon(canvas, button, entry, Blocks(), "the balloon")
    marked = {p for p in paint.points((0, 0, width, canvas.height)) if canvas.at(p) == MARK}
    assert paint.normalised(marked) == paint.normalised(Blocks().ink("Belongings"))


def test_a_balloon_is_widened_only_into_transparent_texels():
    canvas, button = widening(8)
    x0, y0, w, h = button.box
    canvas.stock = bytes(PAPER if (x, y) == (x0 + w + 3, y0 + h // 2) else v
                         for y in range(canvas.height) for x in range(canvas.width)
                         for v in [canvas.stock[y * canvas.width + x]])  # fmt: skip
    with pytest.raises(TextureTextError, match="not free for it to widen into"):
        tb.balloon(canvas, button, Entry("btn@x.a", "Go", "b:1"), Blocks(), "the balloon")


def test_a_widened_balloon_grows_its_atlas_entry_by_whole_vram_words():
    _, button = widening(8)
    boku = bytearray(TEXTURE_AT + 64)
    boku[TEXTURE_AT - 12 : TEXTURE_AT] = struct.pack("<6H", *ENTRY)
    place = SimpleNamespace(file=ARCHIVE_NAME, file_offset=TEXTURE_AT)
    inv = SimpleNamespace(get=lambda _id: SimpleNamespace(occurrences=(place,)))
    edit = tb.entry_edit(SimpleNamespace(boku=bytes(boku)), inv, button, "the balloon")
    assert edit.offset == TEXTURE_AT - 12
    assert struct.unpack("<6H", edit.new) == (8, 0, 11 + 8 // 4, 30, 0, 0x41)
    boku[TEXTURE_AT - 8] = 12  # a different revision: the width is not the one measured
    with pytest.raises(TextureTextError, match="not the one measured"):
        tb.entry_edit(SimpleNamespace(boku=bytes(boku)), inv, button, "the balloon")


def test_a_stone_keeps_its_outline_where_it_runs_into_the_box():
    """`M_S01100`'s stone: the outline's dark pixels reach into the box at its corners. They
    are dark, but they are the stone's -- next to transparency -- and stay as they are."""
    canvas, _, button = stone_fixture()
    w = canvas.width
    outline = {(9, 4), (9, 5)}
    for x, y in [(x, y) for x in range(0, 9) for y in range(0, 7)]:
        canvas.stock = canvas.stock[: y * w + x] + b"\0" + canvas.stock[y * w + x + 1 :]
    for x, y in outline:
        canvas.stock = canvas.stock[: y * w + x] + bytes([INK]) + canvas.stock[y * w + x + 1 :]
    canvas.pixels = bytearray(canvas.stock)
    tb.stone(canvas, button, Entry("btn@x.back", "Back", "b:1"), Blocks(), "the stone")
    assert all(canvas.at(p) == INK for p in outline)


def test_a_balloon_keeps_a_pixel_of_paper_between_its_english_and_shading_inside_it():
    """Shading that reaches in from the outline -- here up from the bottom, so the rows it is
    on still have paper either side of it -- is not blanked with the label, and the English
    may not be set touching it."""
    canvas, _, _, button = balloon_fixture(w=60)
    w, h = canvas.width, canvas.height
    bottom = max(y for y in range(h) if canvas.stock[y * w + 16] == PAPER)
    shade = {(16, y) for y in range(19, bottom + 1)}
    for x, y in shade:
        canvas.stock = canvas.stock[: y * w + x] + bytes([TAIL]) + canvas.stock[y * w + x + 1 :]
    canvas.pixels = bytearray(canvas.stock)
    entry = Entry("btn@x.a", "Go // on go", "b:1")  # reaches down past the Japanese
    try:
        tb.balloon(canvas, button, entry, Blocks(), "the balloon")
    except TextureTextError:
        return  # refusing is right too
    marked = {p for p in paint.points(button.box) if canvas.at(p) == MARK}
    assert not paint.grown(marked, 1, 1, 1, 1) & shade
