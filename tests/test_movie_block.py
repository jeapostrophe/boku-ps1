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
from boku.archive import EXE_LOAD_BIAS
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
NAME = 0x8002A32C
"""A name pointer, as `movie_names` reads them; any u32 serves, the loader only compares."""
OTHER = 0x8002A19C

HEADER = 12
"""magic, cue_count, glyphs_offset, cues_offset, movie_count: 4 + 2 * 4 bytes. Typed, not
imported, on purpose: these tests state the layout the assembly was written against."""
ROW = 8
"""A movie row: u32 name, u16 cues_offset, u16 cue_count."""


def one(cues: list[mb.Cue], font=FONT) -> bytes:
    """The block for one movie, as the loader leaves it once that movie has started."""
    return mb.select(mb.encode_block({NAME: cues}, font), NAME)


def test_the_block_is_laid_out_as_the_docstring_says():
    block = mb.encode_block({NAME: [mb.Cue(10, 20, ("ab",))]}, FONT)
    magic, count, glyphs, current, movies = struct.unpack_from("<IHHHH", block, 0)
    assert magic == 0x42534B42 and block[:4] == b"BKSB"
    assert (count, current) == (0, 0), "the playing movie's fields are the loader's to fill"
    assert movies == 1
    assert struct.unpack_from("<IHH", block, HEADER) == (NAME, HEADER + ROW, 1)
    start, end, lines, pad = struct.unpack_from("<HHHH", block, HEADER + ROW)
    assert (start, end, pad) == (10, 20, 0)
    assert lines == HEADER + ROW + 8, "the lines follow the one 8-byte cue row"
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


def test_movies_are_rows_in_name_order_each_naming_its_own_run_of_cues():
    block = mb.encode_block(
        {OTHER: [mb.Cue(1, 2, ("a",))], NAME: [mb.Cue(3, 4, ("b",)), mb.Cue(5, 6, ("a",))]}, FONT
    )
    assert struct.unpack_from("<H", block, 10) == (2,)
    first = HEADER + 2 * ROW
    assert struct.unpack_from("<IHH", block, HEADER) == (OTHER, first, 1)
    assert struct.unpack_from("<IHH", block, HEADER + ROW) == (NAME, first + 8, 2)
    assert [struct.unpack_from("<HH", block, first + 8 * n) for n in range(3)] == [
        (1, 2),
        (3, 4),
        (5, 6),
    ]


def test_a_movie_with_no_cues_gets_no_row():
    block = mb.encode_block({NAME: [], OTHER: [mb.Cue(1, 2, ("a",))]}, FONT)
    assert struct.unpack_from("<HI", block, 10) == (1, OTHER)


def test_the_loader_copies_the_playing_movies_row_and_nothing_else():
    block = mb.encode_block({NAME: [mb.Cue(1, 2, ("a",))], OTHER: [mb.Cue(3, 4, ("b",))]}, FONT)
    for name, row in ((OTHER, 0), (NAME, 1)):
        _, offset, count = struct.unpack_from("<IHH", block, HEADER + ROW * row)
        loaded = mb.select(block, name)
        assert struct.unpack_from("<H", loaded, 4) == (count,)
        assert struct.unpack_from("<H", loaded, 8) == (offset,)
        assert loaded[:4] + loaded[6:8] + loaded[10:] == block[:4] + block[6:8] + block[10:]


def test_a_movie_the_block_has_no_row_for_draws_nothing_even_after_another_movie():
    """The loader runs once per movie over the block it has just read, so a movie with no
    row gets a count of 0 -- including when the RAM copy still holds the last movie's."""
    block = mb.encode_block({NAME: [mb.Cue(1, 99, ("a",))]}, FONT)
    previous = mb.select(block, NAME)
    assert mb.render(previous, 50)
    assert mb.render(mb.select(previous, OTHER), 50) == {}


def test_one_movies_cue_is_never_drawn_over_another():
    """The per-movie key, which milestone 1 did not have: two movies with cues over the
    same frames, each drawn only under its own name."""
    block = mb.encode_block({NAME: [mb.Cue(1, 99, ("a",))], OTHER: [mb.Cue(1, 99, ("b",))]}, FONT)
    mine, theirs = mb.render(mb.select(block, NAME), 50), mb.render(mb.select(block, OTHER), 50)
    assert mine and theirs and mine != theirs
    assert mine == mb.render(one([mb.Cue(1, 99, ("a",))]), 50)


@pytest.mark.parametrize("position", sorted(mb.POSITIONS))
def test_two_lines_take_their_positions_rows_and_are_centred_separately(position):
    line_y = mb.POSITIONS[position]
    block = mb.encode_block({NAME: [mb.Cue(1, 2, ("a", "ab"), line_y)]}, FONT)
    _, _, lines, _ = struct.unpack_from("<HHHH", block, HEADER + ROW)
    assert struct.unpack_from("<HH", block, lines) == ((320 - 5) // 2, line_y[0])
    second = lines + 4 + 2
    assert struct.unpack_from("<HH", block, second) == ((320 - 9) // 2, line_y[1])


def test_the_top_rows_mirror_the_bottom_margin():
    # A glyph inked over its whole cell draws every row a line can: its outline is the
    # cell's first and last mask rows. The top position's first drawn row must sit as far
    # from row 0 as the bottom position's last does from the frame's last row.
    full = {"#": G(tuple([(1 << mb.CELL) - 1] * mb.CELL), 12)}

    def drawn(position):
        cue = mb.Cue(1, 2, ("#", "#"), mb.POSITIONS[position])
        return {y for _, y in mb.render(mb.select(mb.encode_block({NAME: [cue]}, full), NAME), 1)}

    assert min(drawn("top")) == (mb.FRAME_HEIGHT - 1) - max(drawn("bottom"))


def headers(block: bytes) -> list[int]:
    """The offset of every line header and of the end marker, walked as the routine walks:
    past the glyph bytes to the 0xFF, then to the next even byte."""
    (movies,) = struct.unpack_from("<H", block, 10)
    out = []
    for row in range(movies):
        _, first, count = struct.unpack_from("<IHH", block, HEADER + ROW * row)
        for n in range(count):
            cursor = struct.unpack_from("<HHHH", block, first + 8 * n)[2]
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
        block = mb.encode_block({NAME: [cue], OTHER: [mb.Cue(3, 4, ("b",))]}, FONT)
        found = headers(block)
        assert len(found) == len(lengths) + 1 + 2, lengths
        assert all(offset % 2 == 0 for offset in found), (lengths, found)


@pytest.mark.parametrize(
    ("cues", "message"),
    [
        ([mb.Cue(1, 2, ("ax",))], "no glyph for 'x'"),
        ([mb.Cue(1, 2, ("a" * 64,))], f"320 px wide; a movie line holds {mb.LINE_WIDTH}"),
        ([mb.Cue(5, 4, ("a",))], "not 0 <= start <= end"),
        ([mb.Cue(1, 2, ("a", "a", "a"))], "at most 2 lines"),
    ],
)
def test_what_the_encoder_refuses(cues, message):
    with pytest.raises(mb.BlockError, match=message):
        mb.encode_block({NAME: cues}, FONT)


def test_a_line_exactly_as_wide_as_the_band_is_drawn():
    """`LINE_WIDTH` is the widest line, not one past it: a line of exactly that many pixels
    of advance encodes, and the outline of its last glyph still lands on the frame."""
    advance = 6
    assert mb.LINE_WIDTH % advance == 0, "pick an advance that divides the band"
    text = "a" * (mb.LINE_WIDTH // advance)
    font = {"a": G(cell(*[(c, 0) for c in range(advance - 1)]), advance)}
    pixels = mb.render(one([mb.Cue(1, 2, (text,))], font), 1)
    assert min(x for x, _ in pixels) == 0 and max(x for x, _ in pixels) < mb.SCREEN_WIDTH
    with pytest.raises(mb.BlockError, match="a movie line holds"):
        mb.encode_block({NAME: [mb.Cue(1, 2, (text + "a",))]}, font)


def test_more_cues_than_the_count_field_holds_is_a_refusal():
    """A movie's `cue_count` is a u16: a 65,536th cue used to leave `encode_block` as a
    `struct.error`, straight past the build's `except BlockError` and out as a traceback."""
    with pytest.raises(mb.BlockError, match="65536 cues"):
        mb.encode_block({NAME: [mb.Cue(1, 2, ("a",))] * (mb.U16_MAX + 1)}, FONT)


def test_a_cue_whose_lines_start_past_the_u16_offset_is_a_refusal():
    """Each cue row carries its lines' offset as a u16. With 6,000 empty cues the lines
    begin at 12 + 8 + 8 * 6,000 = 48,020 and each empty cue's are 4 bytes, so the 4,380th
    is the first whose offset (65,536) the field cannot name -- and it refuses there."""
    with pytest.raises(mb.BlockError, match="lines start 65536 bytes in"):
        mb.encode_block({NAME: [mb.Cue(1, 2, ())] * 6000}, FONT)


def test_a_glyph_table_starting_past_the_u16_offset_is_a_refusal():
    """`glyphs_offset` is a u16 too, and it is the last thing in the block that can pass
    65,535 while every cue row is still inside it: 5,454 empty cues and one two-line cue
    put the last cue's lines at 12 + 8 + 8 * 5,455 + 4 * 5,454 = 65,476 (inside the field)
    and the glyph table 148 bytes later, at 65,624: 140 of lines, then the empty clip section
    (4) and its trailer (4)."""
    tail = mb.Cue(1, 2, ("a" * 63, "a" * 63))
    with pytest.raises(mb.BlockError, match="glyph table would start 65624 bytes in"):
        mb.encode_block({NAME: [mb.Cue(1, 2, ())] * 5454 + [tail]}, FONT)


def test_a_block_larger_than_its_reserved_sectors_is_a_refusal():
    """The executable reads the block from `boku.relocate.MOVIE_BLOCK_RESERVE`, and the
    sector after the reserve is `BOKU.BIN`'s first: one byte over is the refusal. The fixture
    is sized from the reserve by growing whole-line cues until the block crosses it."""
    limit = mb.BLOCK_MAX_SECTORS * FORM1_DATA_SIZE
    cue = mb.Cue(1, 2, ("a" * 63, "a" * 63))
    cues: list[mb.Cue] = []
    sizes = [len(mb.encode_block({}, FONT))]
    while True:
        try:
            sizes.append(len(mb.encode_block({NAME: [*cues, cue]}, FONT)))
        except mb.BlockError as error:
            assert f"reserved run holds {mb.BLOCK_MAX_SECTORS}" in str(error), error
            break
        cues.append(cue)
    step = sizes[-1] - sizes[-2]
    assert sizes[-1] <= limit < sizes[-1] + step + 3, (
        f"the last block that encoded is {sizes[-1]} bytes and a cue adds {step}; "
        f"the refusal is not at the {limit}-byte boundary"
    )


def test_the_index_byte_leaves_no_room_for_a_256th_glyph():
    """`END_OF_LINE` (0xFF) ends a line, so the indices a glyph may take are 0..254: a
    255-glyph font is the largest that fits, and its last glyph is index 254 -- never the
    terminator. The 256th is the refusal."""
    characters = [chr(0x100 + i) for i in range(255)]
    font = {c: G(cell(), 1) for c in characters}
    block = mb.encode_block({NAME: [mb.Cue(1, 2, (characters[-1],))]}, font)
    _, _, lines, _ = struct.unpack_from("<HHHH", block, HEADER + ROW)
    assert block[lines + 4 : lines + 6] == bytes([254, mb.END_OF_LINE])

    with pytest.raises(mb.BlockError, match="256 glyphs"):
        mb.encode_block({}, font | {chr(0x100 + 255): G(cell(), 1)})


# --- the movie table ------------------------------------------------------------------------------


def an_exe(names: list[str], pointers: list[int] | None = None) -> bytes:
    """An executable image holding `g_movie_table` and the strings its entries point at."""
    exe = bytearray(0x20000)
    strings = 0x8002A000
    placed: dict[str, int] = {}
    cursor = strings
    for name in names:
        if name not in placed:
            placed[name] = cursor
            text = f"\\__STR\\{name}.IKI;1".encode("ascii") + b"\0"
            exe[cursor - EXE_LOAD_BIAS : cursor - EXE_LOAD_BIAS + len(text)] = text
            cursor += 20
    pointers = pointers or [placed[name] for name in names]
    for entry, pointer in enumerate(pointers):
        struct.pack_into(
            "<I", exe, mb.MOVIE_TABLE + mb.MOVIE_ENTRY_SIZE * entry - EXE_LOAD_BIAS, pointer
        )
    return bytes(exe)


def test_movie_names_keys_each_file_by_the_one_string_its_entries_share():
    names = ["M27", "M010"] + ["M60"] * (mb.MOVIE_ENTRIES - 3) + ["M27"]
    found = mb.movie_names(an_exe(names))
    assert set(found) == {"M27", "M010", "M60"}
    assert found["M27"] == 0x8002A000 and found["M010"] == 0x8002A000 + 20


def test_a_file_with_two_name_strings_is_refused():
    """The loader matches the pointer, so a file reachable through two strings would draw
    its cues under one of them only."""
    names = ["M27"] * mb.MOVIE_ENTRIES
    exe = bytearray(an_exe(names))
    second = 0x8002A100
    text = b"\\__STR\\M27.IKI;1\0"
    exe[second - EXE_LOAD_BIAS : second - EXE_LOAD_BIAS + len(text)] = text
    struct.pack_into("<I", exe, mb.MOVIE_TABLE + mb.MOVIE_ENTRY_SIZE - EXE_LOAD_BIAS, second)
    with pytest.raises(mb.BlockError, match="M27 has two name strings"):
        mb.movie_names(bytes(exe))


# --- the reference rasteriser -------------------------------------------------------------------


def test_render_puts_the_glyph_at_the_pen_and_its_outline_one_pixel_around_it():
    pixels = mb.render(one([mb.Cue(10, 20, ("ab",))]), 15)
    y = mb.LINE_Y[0]
    assert pixels[155, y] == mb.WHITE
    assert pixels[154, y - 1] == mb.DARK and pixels[156, y + 1] == mb.DARK
    assert (153, y) not in pixels and (155, y - 2) not in pixels
    # 'b' starts at 155 + 5 and its pixel is at cell (2, 3).
    assert pixels[162, y + 3] == mb.WHITE
    assert len([p for p in pixels.values() if p == mb.WHITE]) == 2


def test_the_cues_frame_range_is_inclusive_at_both_ends():
    block = one([mb.Cue(10, 20, ("a",))])
    assert mb.render(block, 9) == {}
    assert mb.render(block, 10) and mb.render(block, 20)
    assert mb.render(block, 21) == {}


def test_a_block_without_the_magic_draws_nothing():
    block = bytearray(one([mb.Cue(1, 99, ("a",))]))
    block[0] = 0
    assert mb.render(bytes(block), 50) == {}
    assert mb.select(bytes(block), NAME) == bytes(block), "the loader leaves it alone"


def test_a_glyph_straddling_a_slice_edge_is_split_between_the_two_slices():
    """A 12-wide bar centred at x = (320 - 13) // 2 = 153 inks 153..164 and outlines
    152..165, across the boundary between slice 9 (144..159) and slice 10 (160..175)."""
    full = cell(*[(c, 0) for c in range(12)])
    block = one([mb.Cue(1, 1, ("w",))], {"w": G(full, 13)})
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
    pixels = mb.render(one([mb.Cue(1, 1, ("ww",))], {"w": G(full, 13)}), 1)
    y = mb.LINE_Y[0]
    x = (320 - 26) // 2
    assert pixels[x + 11, y] == mb.WHITE
    assert pixels[x + 12, y] == mb.DARK
    assert pixels[x + 13, y] == mb.WHITE


def test_a_one_cue_block_is_one_sector_the_disc_writers_own_padding_fills():
    """The block is carried as whole Form 1 sectors, counted and padded by the homes that
    already do that for every other blob on the disc -- this module owns neither."""
    block = mb.encode_block({NAME: [mb.Cue(1, 1, ("a",))]}, FONT)
    assert 0 < len(block) < FORM1_DATA_SIZE
    assert form1_sectors(len(block)) == 1
    assert len(padded(block)) == FORM1_DATA_SIZE


# --- the clip section (VO-03): native g_xa_clips subtitles ------------------------------------


def test_a_clips_words_are_found_the_way_clip_sub_play_walks_the_block():
    """`asm/voice.asm` `clip_sub_play` reads the u16 at glyphs_offset - 4, the section's
    count there, and compares 12 x each row's index with 12 x the playing clip's."""
    words = {34: (0x30, 0x31, 0x8000), 41: (0x40, 0x8002, 30, 0x41, 0x8000)}
    block = mb.encode_block({NAME: [mb.Cue(1, 2, ("a",))]}, FONT, clips=words)
    assert mb.clip_count(block) == 2
    for index, expected in words.items():
        assert mb.clip_words(block, index) == expected
    assert mb.clip_words(block, 35) is None


def test_the_clip_section_moves_nothing_the_movie_routine_reads_by_offset():
    """The glyph table is named by an offset, so the clips before it leave every movie's
    frame exactly as it was."""
    plain = mb.encode_block({NAME: [mb.Cue(10, 20, ("ab",))]}, FONT)
    with_clips = mb.encode_block(
        {NAME: [mb.Cue(10, 20, ("ab",))]}, FONT, clips={41: (0x40, 0x8000)}
    )
    assert with_clips != plain
    assert mb.render(mb.select(with_clips, NAME), 15) == mb.render(mb.select(plain, NAME), 15)
    assert mb.render(mb.select(plain, NAME), 15), "no pixel drawn: the comparison is empty"


def test_a_block_with_no_clips_still_carries_an_empty_section():
    """`clip_sub_play` always reads the count, so the section is never absent."""
    block = mb.encode_block({NAME: [mb.Cue(1, 2, ("a",))]}, FONT)
    assert mb.clip_words(block, 34) is None
    assert mb.clip_count(block) == 0


def test_clip_words_must_end_with_end():
    with pytest.raises(mb.BlockError, match="END"):
        mb.encode_block({}, FONT, clips={34: (0x30,)})


def test_a_clip_index_past_a_u16_is_named_as_that_not_as_missing_words():
    with pytest.raises(mb.BlockError, match="u16"):
        mb.encode_block({}, FONT, clips={0x10000: (0x30, 0x8000)})


# --- the panel (FMV-06) ---------------------------------------------------------------------------


def dark_box(pixels) -> tuple[range, range]:
    """The columns and rows the panel's pixels span, checked to hold every dark square of the
    checkerboard over that box (FMV-10); that the others are left alone is the hatched-panel
    test's."""
    xs = sorted({x for x, _ in pixels})
    ys = sorted({y for _, y in pixels})
    box = (range(xs[0], xs[-1] + 1), range(ys[0], ys[-1] + 1))
    parity = (xs[0] + ys[0]) % 2
    squares = {(x, y) for x in box[0] for y in box[1] if (x + y) % 2 == parity}
    assert squares <= set(pixels), "the panel's dark squares are all drawn"
    return box


def test_a_panel_is_a_dark_rectangle_behind_the_lines_with_the_text_on_top():
    """ "ab" is 9 px wide at x 155 (see the layout test), its cells rows 199-212. With
    `PANEL_PAD_X` 4 the panel wants 17 px, two 14-px tiles: 28 columns centred, 146-173.
    It is as tall as the position's two lines, rows 199-226, though the cue has one (Jay,
    FMV-09: the panel does not change height from cue to cue)."""
    assert mb.PANEL_PAD_X == 4, "the numbers below are worked for it"
    pixels = mb.render(one([mb.Cue(10, 20, ("ab",), panel=True)]), 15)
    assert dark_box(pixels) == (range(146, 174), range(199, 227))
    plain = mb.render(one([mb.Cue(10, 20, ("ab",))]), 15)
    white = {p for p, c in pixels.items() if c == mb.WHITE}
    assert white == {p for p, c in plain.items() if c == mb.WHITE}, "the text is on top"
    assert mb.render(one([mb.Cue(10, 20, ("ab",), panel=True)]), 21) == {}


def test_a_two_line_panel_spans_both_lines_and_the_wider_one():
    """Lines "a" (5 px) and "ab" (9 px), cells at rows 199-212 and 213-226: the panel is
    sized by the wider, 146-173, and runs from row 199 to 226, a row of tiles per line."""
    pixels = mb.render(one([mb.Cue(10, 20, ("a", "ab"), panel=True)]), 15)
    assert dark_box(pixels) == (range(146, 174), range(199, 227))


def test_a_panel_wider_than_the_frame_is_the_frames_width():
    """A 318-px line wants 326 px of panel: the 23 tiles that span the frame, from column 0;
    the last runs to column 321, which no slice holds."""
    font = {"w": G(cell(), 159)}
    block = one([mb.Cue(10, 20, ("ww",), panel=True)], font)
    assert dark_box(mb.render(block, 15))[0] == range(0, 320)
    assert dark_box(mb.render(block, 15, range(0, 400)))[0] == range(0, 322)


def test_a_panel_cue_the_font_cannot_draw_is_the_same_refusal_as_without_one():
    with pytest.raises(mb.BlockError, match="no glyph"):
        mb.encode_block({NAME: [mb.Cue(1, 2, ("a\u00e9",), panel=True)]}, FONT)


def test_the_panel_tile_takes_an_index_only_when_a_cue_asks_for_one():
    """The tile is one more record after the font's; a 255-glyph font leaves it no index."""
    characters = [chr(0x100 + i) for i in range(255)]
    font = {c: G(cell(), 1) for c in characters}
    mb.encode_block({NAME: [mb.Cue(1, 2, (characters[0],))]}, font)
    with pytest.raises(mb.BlockError, match="panel"):
        mb.encode_block({NAME: [mb.Cue(1, 2, (characters[0],), panel=True)]}, font)


def records(block: bytes, count: int) -> list[bytes]:
    (glyphs,) = struct.unpack_from("<H", block, 6)
    assert len(block) == glyphs + count * mb.RECORD_SIZE
    return [
        block[glyphs + mb.RECORD_SIZE * n : glyphs + mb.RECORD_SIZE * (n + 1)] for n in range(count)
    ]


def test_the_panel_tile_record_is_flagged_hatch_and_no_glyph_is():
    """FMV-10: byte 1 of a record tells `movie_sub_blit` to paint the tile's checkerboard
    without walking its masks (the fast path that keeps a two-row panel inside the frame's
    time); every glyph record keeps it 0. Sorted font `[' ', 'a', 'b']`, then the tile."""
    tile = records(mb.encode_block({NAME: [mb.Cue(1, 2, ("ab",), panel=True)]}, FONT), 4)
    assert [r[1] for r in tile] == [0, 0, 0, 1]


def test_the_panel_masks_are_the_checkerboard_the_fast_path_paints():
    """`@@hatch` paints DARK where mask column + row is even, without reading the masks, and
    `render` (the gate's prediction) reads them: they agree only while the tile is glyph-free
    and outlined on exactly those pixels."""
    assert mb.PANEL_MASKS.glyph == (0,) * mb.MASK
    assert mb.PANEL_MASKS.outline == tuple(
        bits(*[c for c in range(mb.MASK) if (c + r) % 2 == 0]) for r in range(mb.MASK)
    )


def test_a_hatched_panel_is_dark_on_alternate_pixels_and_the_picture_shows_between():
    block = one([mb.Cue(10, 20, ("ab",), panel=True)])
    pixels = mb.render(block, 15)
    plain = mb.render(one([mb.Cue(10, 20, ("ab",))]), 15)
    hatch = {p for p in pixels if p not in plain}
    assert hatch and all(pixels[p] == mb.DARK for p in hatch)
    assert all((x + y) % 2 == (146 + 199) % 2 for x, y in hatch), "a checkerboard"
    assert dark_box(pixels) == (range(146, 174), range(199, 227))


def test_a_panel_row_with_no_text_is_still_held_to_the_frame():
    """The panel fills every row of the position, so an empty row outside the frame is the
    same refusal as a line there; without a panel that row draws nothing and is not checked."""
    last = mb.FRAME_HEIGHT - mb.MASK + 1  # the lowest y whose 14 rows stay in the frame
    mb.encode_block({NAME: [mb.Cue(1, 2, ("a",), (200, last), panel=True)]}, FONT)
    mb.encode_block({NAME: [mb.Cue(1, 2, ("a",), (200, last + 1))]}, FONT)
    with pytest.raises(mb.BlockError, match="outside"):
        mb.encode_block({NAME: [mb.Cue(1, 2, ("a",), (200, last + 1), panel=True)]}, FONT)
