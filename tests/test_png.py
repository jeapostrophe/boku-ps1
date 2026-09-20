"""`boku.png`, checked against a PNG library that is not ours wherever one is reachable.

A writer and a reader that are wrong in the same way round-trip perfectly, so the
round-trip tests here are never the whole gate: macOS `sips` (libpng) both reads what we
write and writes what we read, and `tests/synth_png.py` builds the filtered scanlines our
writer never produces.
"""

from __future__ import annotations

import struct
import zlib

import pytest

from boku import png
from tests import synth_png as synth

needs_sips = pytest.mark.skipif(synth.SIPS is None, reason="no sips on this machine")

PALETTE = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (16, 32, 48), (0, 0, 0)]


def checkerboard(width, height, colours):
    return bytes((x * 3 + y * 5) % colours for y in range(height) for x in range(width))


# --- the writer and the reader agree ----------------------------------------------------


@pytest.mark.parametrize("depth,colours", [(1, 2), (2, 4), (4, 16), (8, 256)])
@pytest.mark.parametrize("width", [12, 13])
def test_indexed_round_trips_at_every_palette_depth(depth, colours, width):
    """Both widths on purpose: an even one takes the packer's fast path, an odd one does not,
    and a width that does not fill its last byte is the case that loses a column."""
    height = 5
    palette = [(i, 255 - i, (i * 7) % 256) for i in range(colours)]
    indices = checkerboard(width, height, colours)
    got = png.read(png.write_indexed(width, height, indices, palette, bit_depth=depth))
    assert (got.width, got.height, got.bit_depth, got.colour_type) == (width, height, depth, 3)
    assert got.indices == indices
    assert list(got.palette) == palette


@pytest.mark.parametrize("width", [4, 5])
def test_a_sub_byte_row_puts_the_first_pixel_in_the_most_significant_bits(width):
    """Read straight off the IDAT: our own reader cannot vouch for our own packing order.

    PNG packs left to right from the high end of the byte; a TIM packs 4bpp the other way
    round, and the two conventions meet in this writer.
    """
    indices = bytes([1, 2, 3, 4, 5][:width])
    data = png.write_indexed(width, 1, indices, [(i, i, i) for i in range(16)], bit_depth=4)
    body = data[data.index(b"IDAT") + 4 :]
    raw = zlib.decompressobj().decompress(body)
    assert raw[0] == 0  # filter type
    assert raw[1] == 0x12 and raw[2] == 0x34
    if width == 5:
        assert raw[3] == 0x50  # the odd pixel is in the high nibble, the low one is padding


def test_palette_order_is_preserved_even_when_two_entries_are_the_same_colour():
    """The TIM CLUT this mirrors may hold duplicates; an index must not be re-pointed."""
    palette = [(9, 9, 9), (9, 9, 9), (1, 2, 3)]
    indices = bytes([0, 1, 2, 1])
    got = png.read(png.write_indexed(4, 1, indices, palette))
    assert got.indices == indices
    assert list(got.palette) == palette


def test_trns_round_trips_and_trailing_opaque_entries_are_dropped():
    palette = PALETTE[:4]
    alpha = [0, 255, 255, 255]
    data = png.write_indexed(4, 1, bytes([0, 1, 2, 3]), palette, alpha)
    assert data.count(b"tRNS") == 1
    body = data[data.index(b"tRNS") + 4 :]
    assert body[:1] == b"\x00"  # one entry written, not four
    got = png.read(data)
    assert list(got.alpha) == alpha
    assert got.rgba[:4] == bytes([255, 0, 0, 0])


def test_an_all_opaque_trns_writes_no_chunk_at_all():
    data = png.write_indexed(2, 1, bytes([0, 1]), PALETTE[:2], [255, 255])
    assert b"tRNS" not in data
    assert list(png.read(data).alpha) == [255, 255]


def test_rgba_round_trips():
    rgba = bytes(range(256)) * 4
    got = png.read(png.write_rgba(16, 16, rgba))
    assert (got.colour_type, got.bit_depth) == (6, 8)
    assert got.rgba == rgba
    assert got.indices is None


def test_the_default_bit_depth_is_the_smallest_that_addresses_the_palette():
    assert png.read(png.write_indexed(1, 1, b"\x00", PALETTE[:2])).bit_depth == 1
    assert png.read(png.write_indexed(1, 1, b"\x00", PALETTE[:3])).bit_depth == 2
    assert png.read(png.write_indexed(1, 1, b"\x00", PALETTE[:5])).bit_depth == 4


# --- filters, which our writer never produces -------------------------------------------


@pytest.mark.parametrize("kind", [0, 1, 2, 3, 4])
def test_reader_unfilters_every_png_filter_type(kind):
    width, height = 9, 7
    rows = [
        bytes((x * 13 + y * 29 + c * 7) % 256 for x in range(width) for c in range(3))
        for y in range(height)
    ]
    expected = b"".join(
        bytes(row[x * 3 : x * 3 + 3]) + b"\xff" for row in rows for x in range(width)
    )
    assert png.read(synth.rgb_png(width, height, rows, kind)).rgba == expected


@needs_sips
@pytest.mark.parametrize("kind", [0, 1, 2, 3, 4])
def test_libpng_agrees_with_our_reader_on_every_filter_type(kind, tmp_path):
    """Pins `synth_png.filtered`, so a shared mistake in the test's encoder cannot pass."""
    width, height = 9, 7
    rows = [
        bytes((x * 13 + y * 29 + c * 7) % 256 for x in range(width) for c in range(3))
        for y in range(height)
    ]
    data = synth.rgb_png(width, height, rows, kind)
    assert png.read(synth.sips_reencode(data, tmp_path, f"f{kind}")).rgba == png.read(data).rgba


# --- an independent library reads what we write, and we read what it writes --------------


@needs_sips
def test_sips_reads_our_indexed_png_the_way_we_meant_it(tmp_path):
    data = png.write_indexed(7, 5, checkerboard(7, 5, 4), PALETTE[:4], [0, 255, 255, 255], 4)
    props = synth.sips_properties(
        data, tmp_path, "pixelWidth", "pixelHeight", "hasAlpha", "bitsPerSample"
    )
    assert props["pixelWidth"] == "7"
    assert props["pixelHeight"] == "5"
    assert props["hasAlpha"] == "yes"
    assert props["bitsPerSample"] == "4"


@needs_sips
def test_our_pixels_survive_a_trip_through_libpng(tmp_path):
    """libpng is the ground truth here, not our own reader.

    Comparing our reader against our reader would pass with the writer and the reader
    wrong in the same direction, which is precisely the mistake a 4-bit packing order
    invites; so the expectation is built from the palette and the indices directly.
    """
    width, height = 40, 24
    palette = [(i * 9 % 256, i * 5 % 256, i * 3 % 256) for i in range(16)]
    indices = checkerboard(width, height, 16)
    expected = b"".join(bytes(palette[i]) + b"\xff" for i in indices)
    data = png.write_indexed(width, height, indices, palette, bit_depth=4)
    assert png.read(synth.sips_reencode(data, tmp_path)).rgba == expected
    assert png.read(data).rgba == expected


# --- the other colour types an artist's tool might save ---------------------------------


def test_reads_greyscale_and_grey_alpha():
    grey = synth.assemble(2, 1, 8, 0, synth.filtered([bytes([10, 200])], 0, 1))
    assert png.read(grey).rgba == bytes([10, 10, 10, 255, 200, 200, 200, 255])
    ga = synth.assemble(2, 1, 8, 4, synth.filtered([bytes([10, 128, 200, 0])], 0, 2))
    assert png.read(ga).rgba == bytes([10, 10, 10, 128, 200, 200, 200, 0])


def test_reads_a_colour_key_trns_on_a_truecolour_png():
    rows = [bytes([1, 2, 3, 9, 9, 9])]
    trns = synth.chunk(b"tRNS", struct.pack(">3H", 9, 9, 9))
    data = synth.assemble(2, 1, 8, 2, synth.filtered(rows, 0, 3), extra=trns)
    assert png.read(data).rgba == bytes([1, 2, 3, 255, 9, 9, 9, 0])


def test_reads_sixteen_bit_samples_by_taking_the_high_byte():
    rows = [struct.pack(">6H", 0x1234, 0x5678, 0x9ABC, 0, 0, 0xFFFF)]
    data = synth.assemble(2, 1, 16, 2, synth.filtered(rows, 0, 6))
    assert png.read(data).rgba == bytes([0x12, 0x56, 0x9A, 255, 0, 0, 0xFF, 255])


def test_reads_a_png_split_across_several_idat_chunks():
    rows = [bytes([1, 2, 3, 4, 5, 6])]
    raw = zlib.compress(synth.filtered(rows, 0, 3))
    half = len(raw) // 2
    data = (
        synth.SIGNATURE
        + synth.chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
        + synth.chunk(b"IDAT", raw[:half])
        + synth.chunk(b"IDAT", raw[half:])
        + synth.chunk(b"IEND", b"")
    )
    assert png.read(data).rgba == bytes([1, 2, 3, 255, 4, 5, 6, 255])


def test_ancillary_chunks_are_skipped():
    rows = [bytes([1, 2, 3])]
    extra = synth.chunk(b"gAMA", struct.pack(">I", 45455)) + synth.chunk(b"tEXt", b"who\x00us")
    data = synth.assemble(1, 1, 8, 2, synth.filtered(rows, 0, 3), extra=extra)
    assert png.read(data).rgba == bytes([1, 2, 3, 255])


# --- refusals ---------------------------------------------------------------------------


def test_reader_refuses_something_that_is_not_a_png():
    with pytest.raises(png.PngError, match="signature is missing"):
        png.read(b"GIF89a" + bytes(64))


def test_reader_refuses_a_chunk_whose_crc_does_not_match():
    data = bytearray(png.write_indexed(2, 1, b"\x00\x01", PALETTE[:2]))
    data[-5] ^= 0xFF  # a byte of IEND's CRC
    with pytest.raises(png.PngError, match="fails its CRC"):
        png.read(bytes(data))


def test_reader_refuses_an_interlaced_png():
    body = struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 1)
    data = (
        synth.SIGNATURE
        + synth.chunk(b"IHDR", body)
        + synth.chunk(b"IDAT", zlib.compress(synth.filtered([bytes(6)], 0, 3)))
        + synth.chunk(b"IEND", b"")
    )
    with pytest.raises(png.PngError, match="interlaced"):
        png.read(data)


def test_reader_refuses_an_unknown_filter_type():
    raw = bytearray(synth.filtered([bytes([1, 2, 3])], 0, 3))
    raw[0] = 5
    data = synth.assemble(1, 1, 8, 2, bytes(raw))
    with pytest.raises(png.PngError, match="filter 5; PNG defines 0 to 4"):
        png.read(data)


def test_reader_refuses_an_index_past_the_palette():
    plte = synth.chunk(b"PLTE", b"\x00\x00\x00\xff\xff\xff")
    data = synth.assemble(2, 1, 8, 3, synth.filtered([bytes([0, 7])], 0, 1), extra=plte)
    with pytest.raises(png.PngError, match="indexes entry 7 of a 2-colour PLTE"):
        png.read(data)


def test_reader_refuses_idat_that_is_the_wrong_length_for_the_header():
    plte = synth.chunk(b"PLTE", b"\x00\x00\x00\xff\xff\xff")
    data = synth.assemble(2, 4, 8, 3, synth.filtered([bytes([0, 1])], 0, 1), extra=plte)
    with pytest.raises(png.PngError, match="needs 12 filtered bytes, IDAT gave 3"):
        png.read(data)


def test_reader_refuses_an_indexed_png_with_no_palette():
    data = synth.assemble(2, 1, 8, 3, synth.filtered([bytes([0, 1])], 0, 1))
    with pytest.raises(png.PngError, match="no PLTE"):
        png.read(data)


def test_reader_refuses_an_unsupported_critical_chunk():
    plte = synth.chunk(b"PLTE", b"\x00\x00\x00") + synth.chunk(b"ZiPd", b"")
    data = synth.assemble(1, 1, 8, 3, synth.filtered([bytes([0])], 0, 1), extra=plte)
    with pytest.raises(png.PngError, match="unsupported critical chunk ZiPd"):
        png.read(data)


def test_reader_refuses_a_chunk_whose_body_arrived_but_whose_crc_is_cut_off():
    """The harm: `import_edits` catches `PngError` and names the file; nothing catches
    `struct.error`, so a PNG a copy or a download truncated by two bytes came out of the
    texture import as a traceback with no filename in it."""
    data = png.write_indexed(2, 1, b"\x00\x01", PALETTE[:2])
    idat = data.index(b"IDAT") - 4
    length = int.from_bytes(data[idat : idat + 4], "big")
    cut = data[: idat + 12 + length - 2]  # the whole IDAT body, two bytes of its CRC
    assert len(cut) - idat >= 12, "the fixture is short enough to be a truncated header"
    with pytest.raises(png.PngError, match="IDAT"):
        png.read(cut)


def test_reader_refuses_a_file_that_stops_before_iend():
    data = png.write_indexed(2, 1, b"\x00\x01", PALETTE[:2])
    with pytest.raises(png.PngError, match="truncated chunk header"):
        png.read(data[:-6])


def test_reader_refuses_trns_longer_than_the_palette():
    plte = synth.chunk(b"PLTE", b"\x00\x00\x00\xff\xff\xff")
    trns = synth.chunk(b"tRNS", b"\x00\x01\x02\x03")
    data = synth.assemble(2, 1, 8, 3, synth.filtered([bytes([0, 1])], 0, 1), extra=plte + trns)
    with pytest.raises(png.PngError, match="tRNS has 4 entries for a 2-colour PLTE"):
        png.read(data)


def test_writer_refuses_an_index_past_the_palette():
    with pytest.raises(png.PngError, match="index 4 is past the 2-colour palette"):
        png.write_indexed(2, 1, bytes([0, 4]), PALETTE[:2])


def test_writer_refuses_a_palette_too_big_for_the_asked_depth():
    with pytest.raises(png.PngError, match="do not fit a 2-bit palette"):
        png.write_indexed(1, 1, b"\x00", PALETTE[:5], bit_depth=2)


def test_writer_refuses_the_wrong_number_of_indices():
    with pytest.raises(png.PngError, match="3x2 needs 6 indices, got 5"):
        png.write_indexed(3, 2, bytes(5), PALETTE[:2])


def test_writer_refuses_a_depth_png_does_not_have():
    with pytest.raises(png.PngError, match="cannot be 3-bit"):
        png.write_indexed(1, 1, b"\x00", PALETTE[:2], bit_depth=3)


def test_writer_refuses_a_trns_that_does_not_match_the_palette():
    with pytest.raises(png.PngError, match="tRNS has 1 entries for 2 colours"):
        png.write_indexed(2, 1, bytes([0, 1]), PALETTE[:2], [0])
