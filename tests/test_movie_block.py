"""`boku.movie_block`: the subtitle block's bytes, and the rasteriser that reads them back.

Every expected value is derived by hand from the layout `boku/movie_block.py`'s docstring
states (offsets counted, bits placed), never by calling the encoder twice; the block is
parsed with `struct` here, not with the module's own reader, except where the test is
about that reader.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import pytest

from boku import movie_block as mb
from boku.disc import form1_sectors
from boku.edc import FORM1_DATA_SIZE
from boku.relocate import padded


@dataclass(frozen=True)
class G:
    rows: tuple[int, ...]
    advance: int


def cell(*pixels: tuple[int, int]) -> tuple[int, ...]:
    """A 12 x 12 cell (bit 11 = column 0) with the given (column, row) pixels inked."""
    rows = [0] * mb.CELL
    for column, row in pixels:
        rows[row] |= 1 << (mb.CELL - 1 - column)
    return tuple(rows)


def bits(*columns: int) -> int:
    """A mask row with the given 14-wide columns set (bit 15 = column 0)."""
    value = 0
    for column in columns:
        value |= 1 << (15 - column)
    return value


# --- masks --------------------------------------------------------------------------------------


def test_a_pixel_at_the_cells_origin_lands_at_mask_1_1_with_its_outline_around_it():
    masks = mb.masks_of(cell((0, 0)))
    assert masks.glyph[1] == bits(1)
    assert sum(masks.glyph) == bits(1), "no other glyph row is set"
    assert masks.outline[0] == bits(0, 1, 2)
    assert masks.outline[1] == bits(0, 2)
    assert masks.outline[2] == bits(0, 1, 2)
    assert masks.outline[3] == 0


def test_a_pixel_at_the_cells_far_corner_keeps_its_outline_inside_the_14_wide_mask():
    """The reason the mask is 14 and not 12: the outline of column 11 is column 13."""
    masks = mb.masks_of(cell((11, 11)))
    assert masks.glyph[12] == bits(12)
    assert masks.outline[11] == bits(11, 12, 13)
    assert masks.outline[12] == bits(11, 13)
    assert masks.outline[13] == bits(11, 12, 13)
    assert all(row & 0x0003 == 0 for row in masks.outline), "nothing past column 13"


def test_the_outline_never_overlaps_the_glyph():
    masks = mb.masks_of(cell((0, 0), (1, 0), (2, 0), (1, 1), (5, 7), (11, 11)))
    assert all(g & o == 0 for g, o in zip(masks.glyph, masks.outline, strict=True))


# --- the bytes ----------------------------------------------------------------------------------

FONT = {"a": G(cell((0, 0)), 5), "b": G(cell((2, 3)), 4), " ": G(cell(), 3)}


def test_the_block_is_laid_out_as_the_docstring_says():
    block = mb.encode_block([mb.Cue(10, 20, ("ab",))], FONT)
    magic, count, glyphs = struct.unpack_from("<IHH", block, 0)
    assert magic == 0x42534B42 and block[:4] == b"BKSB"
    assert count == 1
    start, end, lines, pad = struct.unpack_from("<HHHH", block, 8)
    assert (start, end, pad) == (10, 20, 0)
    assert lines == 16, "the lines follow the one 8-byte cue row"
    # sorted(FONT) is [' ', 'a', 'b'], so 'a' is index 1 and 'b' index 2. Advances 5 + 4
    # = 9 px, centred: x = (320 - 9) // 2 = 155.
    x, y = struct.unpack_from("<HH", block, lines)
    assert (x, y) == (155, mb.LINE_Y[0])
    assert block[lines + 4 : lines + 8] == bytes([1, 2, 0xFF, 0]), "padded to an even length"
    assert struct.unpack_from("<HH", block, lines + 8) == (0xFFFF, 0)
    assert glyphs % 4 == 0 and glyphs >= lines + 12
    assert len(block) == glyphs + 3 * mb.RECORD_SIZE
    record = glyphs + mb.RECORD_SIZE  # 'a'
    assert block[record] == 5
    assert struct.unpack_from("<14H", block, record + 4)[1] == bits(1)
    assert struct.unpack_from("<14H", block, record + 4 + 28)[0] == bits(0, 1, 2)


def test_two_lines_take_the_two_line_rows_and_are_centred_separately():
    block = mb.encode_block([mb.Cue(1, 2, ("a", "ab"))], FONT)
    _, _, lines, _ = struct.unpack_from("<HHHH", block, 8)
    assert struct.unpack_from("<HH", block, lines) == ((320 - 5) // 2, mb.LINE_Y[0])
    second = lines + 4 + 2
    assert struct.unpack_from("<HH", block, second) == ((320 - 9) // 2, mb.LINE_Y[1])


def headers(block: bytes) -> list[int]:
    """The offset of every line header and of the end marker, walked as the routine walks:
    past the glyph bytes to the 0xFF, then to the next even byte."""
    _, count, _ = struct.unpack_from("<IHH", block, 0)
    out = []
    for n in range(count):
        cursor = struct.unpack_from("<HHHH", block, 8 + 8 * n)[2]
        while True:
            out.append(cursor)
            if struct.unpack_from("<H", block, cursor)[0] == 0xFFFF:
                break
            cursor += 4
            while block[cursor] != 0xFF:
                cursor += 1
            cursor = (cursor + 2) & ~1
    return out


def test_every_line_header_is_halfword_aligned_whatever_the_line_lengths():
    """The routine reads x and y with `lhu`; an odd header is an address-error exception
    in the DMA callback, which is how the first hooked image stalled at the cue's first
    frame (2026-09-22: line 1 was 33 glyphs, line 2 was 46)."""
    for lengths in [(1, 1), (2, 1), (1, 2), (33, 46), (46, 33), (5,)]:
        cue = mb.Cue(1, 2, tuple("a" * n for n in lengths))
        block = mb.encode_block([cue, mb.Cue(3, 4, ("b",))], FONT)
        found = headers(block)
        assert len(found) == len(lengths) + 1 + 2, lengths
        assert all(offset % 2 == 0 for offset in found), (lengths, found)


@pytest.mark.parametrize(
    ("cues", "message"),
    [
        ([mb.Cue(1, 2, ("ax",))], "no glyph for 'x'"),
        ([mb.Cue(1, 2, ("a" * 64,))], "320 px wide"),
        ([mb.Cue(5, 4, ("a",))], "not 0 <= start <= end"),
        ([mb.Cue(1, 2, ("a", "a", "a"))], "at most 2 lines"),
    ],
)
def test_what_the_encoder_refuses(cues, message):
    with pytest.raises(mb.BlockError, match=message):
        mb.encode_block(cues, FONT)


def test_more_cues_than_the_count_field_holds_is_a_refusal():
    """`cue_count` is a u16, and the whole header is packed in one `struct.pack`: a 65,536th
    cue used to leave `encode_block` as a `struct.error`, straight past `movie_block_for`'s
    `except BlockError` and out of the build as a traceback."""
    with pytest.raises(mb.BlockError, match="65536 cues"):
        mb.encode_block([mb.Cue(1, 2, ("a",))] * (mb.U16_MAX + 1), FONT)


def test_a_cue_whose_lines_start_past_the_u16_offset_is_a_refusal():
    """Each cue row carries its lines' offset as a u16. With 6,000 empty cues the 4,383rd
    row is the first that would have to name an offset past the field, and it refuses
    there -- not at the end, where the block's size would have said so anyway."""
    with pytest.raises(mb.BlockError, match="lines start 65536 bytes in"):
        mb.encode_block([mb.Cue(1, 2, ())] * 6000, FONT)


def test_a_glyph_table_starting_past_the_u16_offset_is_a_refusal():
    """`glyphs_offset` is a u16 too, and it is the last thing in the block that can pass
    65,535 while every cue row is still inside it: 5,454 empty cues and one two-line cue put
    the last cue's lines at 65,464 (inside the field) and the glyph table at 65,604."""
    tail = mb.Cue(1, 2, ("a" * 63, "a" * 63))
    with pytest.raises(mb.BlockError, match="glyph table would start 65604 bytes in"):
        mb.encode_block([mb.Cue(1, 2, ())] * 5454 + [tail], FONT)


def test_the_index_byte_leaves_no_room_for_a_256th_glyph():
    """`END_OF_LINE` (0xFF) ends a line, so the indices a glyph may take are 0..254: a
    255-glyph font is the largest that fits, and its last glyph is index 254 -- never the
    terminator. The 256th is the refusal."""
    characters = [chr(0x100 + i) for i in range(255)]
    font = {c: G(cell(), 1) for c in characters}
    block = mb.encode_block([mb.Cue(1, 2, (characters[-1],))], font)
    _, _, lines, _ = struct.unpack_from("<HHHH", block, 8)
    assert block[lines + 4 : lines + 6] == bytes([254, mb.END_OF_LINE])

    with pytest.raises(mb.BlockError, match="256 glyphs"):
        mb.encode_block([], font | {chr(0x100 + 255): G(cell(), 1)})


# --- the reference rasteriser -------------------------------------------------------------------


def test_render_puts_the_glyph_at_the_pen_and_its_outline_one_pixel_around_it():
    block = mb.encode_block([mb.Cue(10, 20, ("ab",))], FONT)
    pixels = mb.render(block, 15)
    y = mb.LINE_Y[0]
    assert pixels[155, y] == mb.WHITE
    assert pixels[154, y - 1] == mb.DARK and pixels[156, y + 1] == mb.DARK
    assert (153, y) not in pixels and (155, y - 2) not in pixels
    # 'b' starts at 155 + 5 and its pixel is at cell (2, 3).
    assert pixels[162, y + 3] == mb.WHITE
    assert len([p for p in pixels.values() if p == mb.WHITE]) == 2


def test_the_cues_frame_range_is_inclusive_at_both_ends():
    block = mb.encode_block([mb.Cue(10, 20, ("a",))], FONT)
    assert mb.render(block, 9) == {}
    assert mb.render(block, 10) and mb.render(block, 20)
    assert mb.render(block, 21) == {}


def test_a_block_without_the_magic_draws_nothing():
    block = bytearray(mb.encode_block([mb.Cue(1, 99, ("a",))], FONT))
    block[0] = 0
    assert mb.render(bytes(block), 50) == {}


def test_a_glyph_straddling_a_slice_edge_is_split_between_the_two_slices():
    """A 12-wide bar centred at x = (320 - 13) // 2 = 153 inks 153..164 and outlines
    152..165, across the boundary between slice 9 (144..159) and slice 10 (160..175)."""
    full = cell(*[(c, 0) for c in range(12)])
    block = mb.encode_block([mb.Cue(1, 1, ("w",))], {"w": G(full, 13)})
    whole = mb.render(block, 1)
    left = mb.render(block, 1, mb.slice_columns(9))
    right = mb.render(block, 1, mb.slice_columns(10))
    assert left and right
    assert all(x < 160 for x, _ in left) and all(x >= 160 for x, _ in right)
    assert {**left, **right} == whole
    assert (159, mb.LINE_Y[0]) in left and (160, mb.LINE_Y[0]) in right


def test_a_neighbours_outline_lands_in_the_gap_and_never_on_ink():
    """Advance = ink width + 1 leaves one column between glyphs; the next glyph's outline
    takes it and stops there, so the single draw pass never darkens a letter."""
    full = cell(*[(c, 0) for c in range(12)])
    font = {"w": G(full, 13)}
    block = mb.encode_block([mb.Cue(1, 1, ("ww",))], font)
    pixels = mb.render(block, 1)
    y = mb.LINE_Y[0]
    x = (320 - 26) // 2
    assert pixels[x + 11, y] == mb.WHITE
    assert pixels[x + 12, y] == mb.DARK
    assert pixels[x + 13, y] == mb.WHITE


def test_a_one_cue_block_is_one_sector_the_disc_writers_own_padding_fills():
    """The block is carried as whole Form 1 sectors, counted and padded by the homes that
    already do that for every other blob on the disc -- this module owns neither."""
    block = mb.encode_block([mb.Cue(1, 1, ("a",))], FONT)
    assert 0 < len(block) < FORM1_DATA_SIZE
    assert form1_sectors(len(block)) == 1
    assert len(padded(block)) == FORM1_DATA_SIZE
