"""`boku.tim` against synthetic TIMs built from the layout, not from the codec itself.

The gate that matters is on the real disc (`tests/test_real_textures.py`); these cover the
shapes a 2,607-image corpus happens not to contain — a CLUT shorter than the depth, a
word-padded pixel block, a 16bpp image — and every refusal, which by construction the disc
cannot exercise.
"""

from __future__ import annotations

import pytest

from boku.tim import (
    OffPalette,
    TimError,
    indices_from_rgba,
    nearest_indices,
    parse,
    parse_exact,
)
from tests import synth_tim as synth


def four_bpp(
    width=8, height=2, *, cluts=1, clut_x=0, clut_y=0, colours=16, pix_pad=b"", clut_pad=b""
):
    """A 4bpp TIM and the index list it was built from."""
    indices = [(x + y) % colours for y in range(height) for x in range(width)]
    words = []
    for c in range(cluts):
        words += [(w + c) & 0xFFFF if w else 0 for w in synth.ramp(colours)]
    blob = synth.tim(
        0,
        synth.pixel_block(
            width // 4, height, synth.image_4bpp(width, height, indices), pad=pix_pad
        ),
        clut=synth.clut_block(colours, cluts, words, x=clut_x, y=clut_y, pad=clut_pad),
    )
    return blob, indices


def eight_bpp(width=6, height=3, *, colours=256):
    indices = [(x * 7 + y * 13) % colours for y in range(height) for x in range(width)]
    blob = synth.tim(
        1,
        synth.pixel_block(width // 2, height, bytes(indices)),
        clut=synth.clut_block(colours, 1, synth.ramp(colours)),
    )
    return blob, indices


# --- the identity that the whole module exists for -------------------------------------


@pytest.mark.parametrize(
    "blob",
    [
        pytest.param(four_bpp()[0], id="4bpp"),
        pytest.param(four_bpp(cluts=21, clut_x=320, clut_y=241)[0], id="4bpp-21-cluts-placed"),
        pytest.param(four_bpp(colours=4)[0], id="4bpp-clut-shorter-than-depth"),
        pytest.param(four_bpp(width=764, height=256)[0], id="4bpp-largest-on-disc"),
        pytest.param(eight_bpp()[0], id="8bpp"),
        pytest.param(eight_bpp(colours=16)[0], id="8bpp-clut-shorter-than-depth"),
    ],
)
def test_parse_serialise_is_byte_identical(blob):
    assert parse_exact(blob).serialise() == blob


def test_word_padded_pixel_block_round_trips():
    """A block whose declared size rounds `w*h*2` up to a word keeps its padding byte for byte."""
    blob, _ = four_bpp(width=4, height=1, pix_pad=b"\x00\x00")
    tim = parse_exact(blob)
    assert tim.padding == b"\x00\x00"
    assert tim.serialise() == blob


def test_clut_block_padding_round_trips():
    blob, _ = four_bpp(clut_pad=b"\xde\xad\xbe\xef")
    tim = parse_exact(blob)
    assert tim.clut.padding == b"\xde\xad\xbe\xef"
    assert tim.serialise() == blob


def test_clut_vram_origin_survives():
    """758 TIMs on the disc place their CLUT somewhere other than 0,0 (research/textures.md)."""
    blob, _ = four_bpp(clut_x=832, clut_y=498)
    tim = parse_exact(blob)
    assert (tim.clut.x, tim.clut.y) == (832, 498)
    assert tim.serialise() == blob


def test_parse_at_an_offset_reads_the_tim_not_the_prefix():
    blob, _ = eight_bpp()
    assert parse_exact(b"\x00" * 16 + blob, 16).serialise() == blob


# --- widths, which the header states in VRAM units --------------------------------------


def test_width_is_the_stride_times_the_pixels_per_word():
    blob, _ = four_bpp(width=12, height=2)
    tim = parse_exact(blob)
    assert (tim.stride_words, tim.width, tim.height) == (3, 12, 2)
    blob8, _ = eight_bpp(width=6, height=3)
    assert (parse_exact(blob8).stride_words, parse_exact(blob8).width) == (3, 6)


def test_a_4bpp_width_off_the_word_grid_is_not_representable():
    """The header counts words, so a 6-px-wide 4bpp image is stored — and read — as 8 px.

    Anything that wants the artist's 6 has to carry it outside the TIM; this pins that the
    codec reports the padded width rather than inventing one.
    """
    with pytest.raises(AssertionError):
        synth.image_4bpp(6, 1, [0] * 6)
    blob = synth.tim(
        0,
        synth.pixel_block(2, 1, synth.image_4bpp(8, 1, [1, 2, 3, 4, 5, 6, 0, 0])),
        clut=synth.clut_block(16, 1, synth.ramp(16)),
    )
    assert parse_exact(blob).width == 8


# --- indices ----------------------------------------------------------------------------


def test_4bpp_low_nibble_is_the_left_pixel():
    blob = synth.tim(
        0,
        synth.pixel_block(1, 1, b"\x21\x43"),
        clut=synth.clut_block(16, 1, synth.ramp(16)),
    )
    assert parse_exact(blob).indices() == bytes([1, 2, 3, 4])


def test_indices_then_with_indices_is_the_identity():
    for blob, expected in (four_bpp(), eight_bpp(), four_bpp(width=764, height=256)):
        tim = parse_exact(blob)
        assert list(tim.indices()) == expected
        assert tim.with_indices(tim.indices()).serialise() == blob


def test_with_indices_changes_only_the_pixels():
    blob, indices = four_bpp(clut_x=64, clut_y=496)
    tim = parse_exact(blob)
    edited = tim.with_indices(bytes([3] * len(indices)))
    assert edited.clut.serialise() == tim.clut.serialise()
    assert (edited.flags, edited.x, edited.y, edited.stride_words, edited.height) == (
        tim.flags,
        tim.x,
        tim.y,
        tim.stride_words,
        tim.height,
    )
    assert len(edited.serialise()) == len(blob)
    assert edited.serialise() != blob


# --- colour -----------------------------------------------------------------------------


def test_colour_zero_is_transparent_and_opaque_black_is_not():
    blob = synth.tim(
        1,
        synth.pixel_block(1, 1, bytes([0, 1])),
        clut=synth.clut_block(2, 1, [0x0000, 0x8000]),
    )
    tim = parse_exact(blob)
    assert tim.palette_rgba() == [(0, 0, 0, 0), (0, 0, 0, 255)]
    assert tim.decode_rgba() == bytes([0, 0, 0, 0, 0, 0, 0, 255])


def test_stp_is_carried_beside_the_rgba_not_folded_into_it():
    """STP on a non-zero colour is a blend instruction; RGBA has nowhere to put it."""
    blob = synth.tim(
        1,
        synth.pixel_block(1, 1, bytes([0, 1])),
        clut=synth.clut_block(2, 1, [0x001F, 0x801F]),
    )
    tim = parse_exact(blob)
    assert tim.palette_rgba() == [(255, 0, 0, 255), (255, 0, 0, 255)]
    assert tim.palette_stp() == [0, 1]
    assert tim.decode_stp() == bytes([0, 1])


def test_five_bit_channels_expand_to_full_range():
    blob = synth.tim(
        1,
        synth.pixel_block(1, 1, bytes([0, 1])),
        clut=synth.clut_block(2, 1, [0x7FFF, 0x0400]),
    )
    tim = parse_exact(blob)
    assert tim.palette_rgba() == [(255, 255, 255, 255), (0, 0, 8, 255)]


def test_a_second_clut_gives_different_colours_for_the_same_pixels():
    blob, _ = four_bpp(cluts=3)
    tim = parse_exact(blob)
    assert tim.decode_rgba(0) != tim.decode_rgba(2)
    assert tim.indices() == tim.indices()


def test_decode_pads_a_clut_shorter_than_the_depth():
    """An index past a short CLUT renders as a flag colour rather than crashing the export."""
    blob, _ = four_bpp(colours=4)
    tim = parse_exact(blob)
    assert len(tim.palette_rgba()) == 4
    assert len(tim.decode_rgba()) == tim.width * tim.height * 4


# --- refusals ---------------------------------------------------------------------------


def test_parse_rejects_a_wrong_magic():
    blob, _ = four_bpp()
    assert parse(b"\x11" + blob[1:]) is None


def test_parse_rejects_flags_outside_the_low_nibble():
    blob, _ = four_bpp()
    assert parse(blob[:4] + b"\x08\x01\x00\x00" + blob[8:]) is None


def test_parse_rejects_a_pixel_block_whose_size_disagrees_with_its_dimensions():
    """The acceptance test that keeps a stray 0x10 word from manufacturing a TIM."""
    blob, _ = eight_bpp()
    pixel_block = 8 + int.from_bytes(blob[8:12], "little")  # past the CLUT block it declares
    body = bytearray(blob)
    body[pixel_block : pixel_block + 4] = (999).to_bytes(4, "little")
    assert parse(bytes(body)) is None


def test_parse_rejects_a_zero_dimension():
    blob = synth.tim(
        1,
        synth.pixel_block(0, 4, b""),
        clut=synth.clut_block(16, 1, synth.ramp(16)),
    )
    assert parse(blob) is None


def test_parse_rejects_a_truncated_tim():
    blob, _ = eight_bpp()
    assert parse(blob[:-2]) is None


def test_parse_exact_names_the_offset():
    with pytest.raises(TimError, match="no TIM at offset 0x10"):
        parse_exact(b"\x00" * 64, 0x10)


def test_palette_index_past_the_last_clut_is_refused_not_read_off_the_end():
    blob, _ = four_bpp(cluts=2)
    with pytest.raises(TimError, match="CLUT 2 out of range; this TIM has 2"):
        parse_exact(blob).palette_rgba(2)


def test_with_indices_refuses_the_wrong_number_of_pixels():
    blob, indices = four_bpp()
    with pytest.raises(TimError, match=r"8x2 \(16 pixels\) but 15 indices"):
        parse_exact(blob).with_indices(bytes(indices[:-1]))


def test_with_indices_refuses_an_index_the_depth_cannot_hold():
    """A 4bpp texture never becomes an 8bpp one: the archive slot is the size it is."""
    blob, indices = four_bpp()
    edited = list(indices)
    edited[0] = 16
    with pytest.raises(TimError, match=r"index 16 does not fit 4bpp"):
        parse_exact(blob).with_indices(bytes(edited))


def test_with_indices_refuses_an_index_past_a_short_clut():
    blob, indices = four_bpp(colours=4)
    edited = [0] * len(indices)
    edited[0] = 9
    with pytest.raises(OffPalette, match=r"index 9 is past this TIM's 4-colour CLUT"):
        parse_exact(blob).with_indices(bytes(edited))


def test_with_indices_allows_an_index_past_the_clut_the_original_itself_used():
    blob = synth.tim(
        0,
        synth.pixel_block(2, 1, synth.image_4bpp(8, 1, [15, 0, 0, 0, 0, 0, 0, 0])),
        clut=synth.clut_block(4, 1, synth.ramp(4)),
    )
    original = parse_exact(blob)
    assert original.with_indices(original.indices()).serialise() == blob


def test_indices_refuses_a_depth_the_disc_does_not_have():
    blob = synth.tim(2, synth.pixel_block(4, 2, bytes(16)))
    tim = parse_exact(blob)
    assert tim.bpp == 16 and tim.width == 4
    assert tim.serialise() == blob
    with pytest.raises(TimError, match="16bpp TIMs carry no palette indices"):
        tim.indices()


def test_a_tim_with_no_clut_refuses_to_hand_out_a_palette():
    blob = synth.tim(1, synth.pixel_block(4, 2, bytes(16)))
    with pytest.raises(TimError, match="carries no CLUT"):
        parse_exact(blob).palette_rgba()


# --- mapping colours back onto the palette ----------------------------------------------


def test_indices_from_rgba_round_trips_an_untouched_image():
    blob, indices = four_bpp()
    tim = parse_exact(blob)
    assert list(indices_from_rgba(tim, tim.decode_rgba())) == indices


def test_indices_from_rgba_refuses_a_colour_the_clut_lacks():
    blob, _ = four_bpp()
    tim = parse_exact(blob)
    rgba = bytearray(tim.decode_rgba())
    rgba[0:4] = bytes([1, 2, 3, 255])
    with pytest.raises(OffPalette, match=r"1 pixels in 1 colours are not in CLUT 0.*#010203ff x1"):
        indices_from_rgba(tim, bytes(rgba))


def test_indices_from_rgba_refuses_the_wrong_size():
    blob, _ = four_bpp()
    tim = parse_exact(blob)
    with pytest.raises(TimError, match=r"8x2 \(64 RGBA bytes\) but 60 were given"):
        indices_from_rgba(tim, tim.decode_rgba()[:-4])


def duplicate_colour_tim():
    """Entries 1 and 2 hold the same red; the pixels are a blue and the *higher* red.

    The disc's common shape (2,473 of its (texture, CLUT) pairs hold duplicates) and the
    one that tells the two rules apart: only the higher duplicate is in use, so keeping
    what is there and looking a colour up give different answers.
    """
    blob = synth.tim(
        1,
        synth.pixel_block(1, 1, bytes([3, 2])),
        clut=synth.clut_block(4, 1, [0x0000, 0x001F, 0x001F, 0x7C00]),
    )
    tim = parse_exact(blob)
    assert list(tim.indices()) == [3, 2]
    assert tim.palette_rgba()[1] == tim.palette_rgba()[2], "the fixture has no duplicate"
    assert tim.palette_rgba()[3] != tim.palette_rgba()[2], "pixel 0 is already the red"
    return tim


def test_a_pixel_whose_colour_did_not_change_keeps_its_own_entry():
    """The harm: an RGBA save re-points a pixel the artist never touched.

    Colour is not a faithful key for an index — 2,473 (texture, CLUT) pairs on this disc
    hold duplicates — so a colour-keyed lookup answers pixel 2 here with entry 1, which
    is a patch over an unedited pixel and, where the two differ in STP, a blend the
    console stops doing.
    """
    tim = duplicate_colour_tim()
    assert list(indices_from_rgba(tim, tim.decode_rgba())) == [3, 2]


def test_a_recoloured_pixel_takes_the_lower_of_two_equal_entries():
    """The lookup still runs where the colour *did* change: pixel 0 goes blue -> red."""
    tim = duplicate_colour_tim()
    rgba = bytearray(tim.decode_rgba())
    rgba[0:4] = bytes(tim.palette_rgba()[2])  # the red both entry 1 and entry 2 hold
    assert list(indices_from_rgba(tim, bytes(rgba))) == [1, 2]


def test_nearest_indices_reports_what_it_moved():
    blob = synth.tim(
        1,
        synth.pixel_block(1, 1, bytes([0, 1])),
        clut=synth.clut_block(2, 1, [0x0000, 0x7FFF]),
    )
    tim = parse_exact(blob)
    idx, report = nearest_indices(tim, bytes([0, 0, 0, 0, 200, 200, 200, 255]))
    assert list(idx) == [0, 1]
    assert report.approximated == 1
    assert report.worst == 55 * 3
    assert "approximated" in report.describe()


def test_nearest_indices_leaves_an_exact_colour_alone():
    blob, _ = four_bpp()
    tim = parse_exact(blob)
    idx, report = nearest_indices(tim, tim.decode_rgba())
    assert idx == tim.indices()
    assert report.approximated == 0
    assert report.describe() == "every colour was already in the palette"


def test_nearest_indices_never_turns_an_opaque_pixel_transparent():
    blob = synth.tim(
        1,
        synth.pixel_block(1, 1, bytes([0, 1])),
        clut=synth.clut_block(2, 1, [0x0000, 0x7FFF]),
    )
    tim = parse_exact(blob)
    idx, _ = nearest_indices(tim, bytes([0, 0, 0, 255, 0, 0, 0, 255]))
    assert list(idx) == [1, 1]


def test_nearest_indices_refuses_transparency_a_palette_cannot_express():
    blob = synth.tim(
        1,
        synth.pixel_block(1, 1, bytes([0, 1])),
        clut=synth.clut_block(2, 1, [0x7FFF, 0x001F]),
    )
    tim = parse_exact(blob)
    with pytest.raises(OffPalette, match="no transparent entry"):
        nearest_indices(tim, bytes([0, 0, 0, 0, 0, 0, 0, 255]))
