"""Unit tests for the pure functions of `tools/libretro/run_core.py` (PLAN `ENV-05`).

`tools/` is not a Python package (CLAUDE.md keeps it that way; `boku/` is the only
package), so the module under test is loaded by file path with `importlib`, exactly as
ENV-05 asks, rather than restructuring `tools/`.

Every expected value here is computed independently of `run_core.py`'s own code:
- The RGB565 / 0RGB1555 bit layouts come from `~/Dev/retro-trainer/dist/libretro.h`
  (read-only, quoted in the docstrings below), not from `run_core.PIXEL_FORMATS` or
  `run_core.LUT5`/`LUT6` -- this file has its own `_expand5`/`_expand6`, and a test that
  used the module's own tables would just be checking the tables against themselves.
- The XRGB8888 pixel bytes are hand-built native-endian words, and the expected RGB
  triples are the R/G/B values chosen when building them.
- The PNG bytes are decoded by an independent reader (`_decode_png` below) written
  against the PNG spec with `zlib` + `struct`, not by calling anything in run_core.py.

These two pixel formats have never actually run on this project (`research/tooling-setup.md`
"Beetle PSX, headless": the core build here only ever selects XRGB8888), which is exactly
why ENV-05 asks for them to be tested independently rather than trusted.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import types
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_CORE_PATH = REPO_ROOT / "tools" / "libretro" / "run_core.py"


def _load_run_core():
    # run_core imports emulator_paths from beside itself, as it does when run as a script.
    sys.path.insert(0, str(RUN_CORE_PATH.parent))
    spec = importlib.util.spec_from_file_location("run_core_under_test", RUN_CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


run_core = _load_run_core()


# --- independent 5/6 -> 8 bit expansion, from libretro.h's documented bit layout ----------
#
# libretro.h `enum retro_pixel_format`:
#   RETRO_PIXEL_FORMAT_0RGB1555 = 0  "0RGB1555, native endian. The most significant bit
#       must be set to 0."  -> 1 ignored bit, then R[14:10], G[9:5], B[4:0], 5 bits each.
#   RETRO_PIXEL_FORMAT_RGB565   = 2  "RGB565, native endian." -> R[15:11] (5 bits),
#       G[10:5] (6 bits), B[4:0] (5 bits).
#
# The rule asserted here is bit replication -- the top bits of the N-bit field repeat
# into the vacated low bits of the 8-bit output, so the channel's max value (all-ones)
# expands to 255 rather than to 248/252 (a plain left-shift) or landing a few values shy
# of 255 (a floating-point v/max*255 scale). This is the rule `run_core.py`'s LUT5/LUT6
# use (`(v << 3) | (v >> 2)` and `(v << 2) | (v >> 4)`); the formulas below are written
# fresh, not imported from the module.
def _expand5(v: int) -> int:
    return (v << 3) | (v >> 2)


def _expand6(v: int) -> int:
    return (v << 2) | (v >> 4)


def test_expand_helpers_match_documented_corner_cases():
    # Sanity check on the independent helpers themselves, against the worked example the
    # task gave: RGB565 0xF800 -> (255, 0, 0), i.e. a 5-bit channel at its max expands to
    # 255, not 248 (plain shift) or some other rounding.
    assert _expand5(0b11111) == 255
    assert _expand5(0) == 0
    assert _expand6(0b111111) == 255
    assert _expand6(0) == 0


# --- to_rgb_rows: XRGB8888 --------------------------------------------------------------


def test_to_rgb_rows_xrgb8888_reads_native_endian_bgrx_bytes_and_respects_pitch():
    # XRGB8888, native endian, X ignored: a little-endian machine's in-memory byte order
    # for one pixel is [B, G, R, X]. Two pixels per row, 4 bytes of padding the row's
    # actual content never occupies -- to_rgb_rows must skip that padding by pitch, not
    # read it as pixel data.
    def pixel_bytes(r: int, g: int, b: int, x: int) -> bytes:
        return bytes([b, g, r, x])

    row0 = pixel_bytes(10, 20, 30, 99) + pixel_bytes(200, 150, 50, 0) + b"\xff\xff\xff\xff"
    row1 = pixel_bytes(0, 0, 0, 1) + pixel_bytes(255, 255, 255, 2) + b"\x11\x22\x33\x44"
    pixels = row0 + row1
    assert len(row0) == 12  # width(2)*4 + 4 bytes padding = pitch 12

    rows = run_core.to_rgb_rows(pixels, run_core.PIXEL_XRGB8888, width=2, height=2, pitch=12)

    assert rows == [
        bytes([10, 20, 30, 200, 150, 50]),
        bytes([0, 0, 0, 255, 255, 255]),
    ]


# --- to_rgb_rows: RGB565 ------------------------------------------------------------------


def test_to_rgb_rows_rgb565_matches_documented_bit_layout_with_padded_pitch():
    # R[15:11] G[10:5] B[4:0]. 0x5405 is not a corner value on purpose: it is chosen so a
    # naive v*255//max scale would disagree with bit-replication, which is the rule this
    # asserts.  R=0b01010=10, G=0b100000=32, B=0b00101=5.
    mid = (10 << 11) | (32 << 5) | 5
    assert mid == 0x5405

    words = [0xF800, 0x0000, 0xFFFF, mid]  # red, black, white, "mid"
    pixels = struct.pack("<2H", words[0], words[1]) + b"\xaa\xaa"  # row0: pitch has padding
    pixels += struct.pack("<2H", words[2], words[3]) + b"\xbb\xbb"  # row1

    rows = run_core.to_rgb_rows(pixels, run_core.PIXEL_RGB565, width=2, height=2, pitch=6)

    expected_row0 = bytes([255, 0, 0]) + bytes([0, 0, 0])
    expected_row1 = bytes([255, 255, 255]) + bytes([_expand5(10), _expand6(32), _expand5(5)])
    assert rows == [expected_row0, expected_row1]


# --- to_rgb_rows: 0RGB1555 -----------------------------------------------------------------


def test_to_rgb_rows_0rgb1555_matches_documented_bit_layout_and_ignores_bit15():
    # 1 ignored bit, then R[14:10] G[9:5] B[4:0], 5 bits each.
    red = 0b11111 << 10
    green = 0b11111 << 5
    blue = 0b11111
    # R=9 G=17 B=3, deliberately not a corner value, with the documented-ignored bit 15
    # forced to 1 on the second copy to prove it really is ignored (masked out by shift
    # + 0x1F in run_core.py, not by relying on the core to zero it).
    mid_r, mid_g, mid_b = 9, 17, 3
    mid = (mid_r << 10) | (mid_g << 5) | mid_b
    mid_bit15_set = mid | (1 << 15)
    assert mid != mid_bit15_set

    words = [red, green, blue, mid, mid_bit15_set]
    pixels = struct.pack("<5H", *words)

    rows = run_core.to_rgb_rows(pixels, run_core.PIXEL_0RGB1555, width=5, height=1, pitch=10)

    mid_expected = bytes([_expand5(mid_r), _expand5(mid_g), _expand5(mid_b)])
    expected = (
        bytes([255, 0, 0])
        + bytes([0, 255, 0])
        + bytes([0, 0, 255])
        + mid_expected
        + mid_expected  # bit 15 must not change the result
    )
    assert rows == [expected]


# --- parse_press ----------------------------------------------------------------------


def test_parse_press_valid_default_and_explicit_hold():
    assert run_core.parse_press("10:CROSS") == (10, run_core.BUTTONS["CROSS"], 14)
    assert run_core.parse_press("10:cross:3") == (10, run_core.BUTTONS["CROSS"], 12)
    assert run_core.parse_press("1:START:1") == (1, run_core.BUTTONS["START"], 1)


@pytest.mark.parametrize(
    "spec,match",
    [
        ("10", "wants FRAME:BUTTON"),
        ("10:CROSS:3:4", "wants FRAME:BUTTON"),
        ("abc:CROSS", r"abc:CROSS"),  # the bad spec is echoed back in the error
        ("10:FOOBAR", "unknown button"),
        ("0:CROSS", "start at 1"),
        ("10:CROSS:0", "start at 1"),
    ],
)
def test_parse_press_malformed(spec, match):
    with pytest.raises(run_core.UsageError, match=match):
        run_core.parse_press(spec)


# --- parse_frame / parse_at -------------------------------------------------------------


def test_parse_at_valid_defaults_name_to_the_frame_number():
    assert run_core.parse_at("15", "--shot") == (15, "frame-00015")
    assert run_core.parse_at("15:boss", "--shot") == (15, "boss")


@pytest.mark.parametrize("spec", ["0", "-1", "abc", ""])
def test_parse_at_malformed(spec):
    with pytest.raises(run_core.UsageError):
        run_core.parse_at(spec, "--shot")


# --- parse_assert ------------------------------------------------------------------------


def test_parse_assert_valid_default_and_explicit_colours():
    assert run_core.parse_assert("42") == (42, run_core.DEFAULT_ASSERT_COLOURS)
    assert run_core.parse_assert("42:250") == (42, 250)


@pytest.mark.parametrize("spec", ["42:abc", "0:50", "abc:50"])
def test_parse_assert_malformed(spec):
    with pytest.raises(run_core.UsageError):
        run_core.parse_assert(spec)


# --- parse_poke: RAM addresses in any of the three mirrors (PLAN ENV-06) -----------------


def test_parse_poke_accepts_every_ram_mirror_at_the_same_offset():
    # The PS1 maps its 2 MB of RAM at 0x00000000 (KUSEG), 0x80000000 (KSEG0) and 0xA0000000
    # (KSEG1); byte 0x28FA0 of the SYSTEM_RAM buffer is all three.
    for addr in (0x00028FA0, 0x80028FA0, 0xA0028FA0):
        assert run_core.parse_poke(f"7:{addr:08X}=1432") == (7, addr, b"\x14\x32")
        assert run_core.ram_offset(addr, 2) == 0x28FA0


@pytest.mark.parametrize(
    "spec",
    [
        "7:80028FA0",  # no bytes
        "7:80028FA0=",  # empty bytes
        "7:80028FA0=1",  # odd hex
        "0:80028FA0=00",  # frame 0
        "7:801FFFFF=0000",  # runs one byte past the end of RAM
        "7:1F801070=00",  # an I/O register, not RAM
        "7:C0000000=00",  # KSEG2
    ],
)
def test_parse_poke_malformed(spec):
    with pytest.raises(run_core.UsageError):
        run_core.parse_poke(spec)


# --- parse_peek: what --peek samples (PLAN VO-07) ------------------------------------------


def test_parse_peek_reads_a_hex_address_and_a_decimal_length_into_a_ram_offset():
    assert run_core.parse_peek("800359EC:4") == (0x359EC, 4)
    assert run_core.parse_peek("801FFFFC:4") == (0x1FFFFC, 4)  # the last word of RAM


@pytest.mark.parametrize("spec", ["800359EC", "800359EC:", "800359EC:0", "801FFFFD:4", "zz:4"])
def test_parse_peek_malformed(spec):
    with pytest.raises(run_core.UsageError):
        run_core.parse_peek(spec)


# --- schedule_presses: out-of-order frames merge correctly -------------------------------


def test_schedule_presses_merges_overlapping_out_of_order_specs():
    # The second spec starts earlier than the end of the first and is listed after a
    # later-starting spec -- schedule_presses must not assume its inputs arrive sorted.
    args = types.SimpleNamespace(press=["20:CROSS:2", "12:SQUARE:1", "10:START:5"], press_file=None)
    held = run_core.schedule_presses(args)

    cross, square, start = (
        run_core.BUTTONS["CROSS"],
        run_core.BUTTONS["SQUARE"],
        run_core.BUTTONS["START"],
    )
    assert held[10] == frozenset({start})
    assert held[14] == frozenset({start})  # last frame of the 10:START:5 hold
    assert held[12] == frozenset({square, start})  # overlaps the START hold
    assert held[20] == frozenset({cross})
    assert held[21] == frozenset({cross})
    assert 15 not in held  # nothing scheduled there


# --- read_press_file ----------------------------------------------------------------------


def test_read_press_file_strips_comments_and_blank_lines(tmp_path):
    path = tmp_path / "schedule.press"
    path.write_text("# a comment line\n\n10:CROSS\n   \n15:SQUARE:3  # trailing comment\n")
    assert run_core.read_press_file(path) == ["10:CROSS", "15:SQUARE:3"]


# --- png(): independent PNG reader ------------------------------------------------------


def _decode_png(data: bytes) -> tuple[int, int, list[bytes]]:
    """An independent PNG reader: zlib + struct against the spec, no run_core.py code.

    Handles just enough of the format for run_core.png()'s own output: one IHDR (8-bit,
    truecolor, no interlace), any number of IDAT chunks concatenated before inflating, and
    filter type 0 (`None`) on every scanline -- which is the only filter run_core.png()
    ever writes (`b"\\0" + row`).
    """
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "bad PNG signature"
    pos = 8
    width = height = None
    idat = b""
    saw_ihdr = saw_iend = False
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        pos += 4
        tag = data[pos : pos + 4]
        pos += 4
        chunk = data[pos : pos + length]
        pos += length
        (crc,) = struct.unpack_from(">I", data, pos)
        pos += 4
        assert zlib.crc32(tag + chunk) == crc, f"bad CRC on {tag!r} chunk"
        if tag == b"IHDR":
            width, height, depth, colortype, compression, filt, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
            assert (depth, colortype, compression, filt, interlace) == (8, 2, 0, 0, 0), (
                "expected 8-bit truecolour, no interlace"
            )
            saw_ihdr = True
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            saw_iend = True
            break
    assert saw_ihdr and width is not None and height is not None
    assert saw_iend

    raw = zlib.decompress(idat)
    stride = width * 3
    rows = []
    pos = 0
    for _ in range(height):
        filter_type = raw[pos]
        pos += 1
        assert filter_type == 0, f"unsupported PNG filter type {filter_type} (only 0 handled)"
        rows.append(bytes(raw[pos : pos + stride]))
        pos += stride
    assert pos == len(raw)
    return width, height, rows


def test_scale_rows_repeats_every_pixel_across_and_down():
    red, green, blue = b"\xff\x00\x00", b"\x00\xff\x00", b"\x00\x00\xff"
    rows = [red + green, blue + red]
    assert run_core.scale_rows(rows, 1) == rows
    assert run_core.scale_rows(rows, 2) == [
        red + red + green + green,
        red + red + green + green,
        blue + blue + red + red,
        blue + blue + red + red,
    ]
    assert run_core.scale_rows([red + green], 3) == [red * 3 + green * 3] * 3


def test_png_round_trips_through_an_independent_decoder():
    width, height = 3, 2
    rows = [
        bytes([255, 0, 0, 0, 255, 0, 0, 0, 255]),  # red, green, blue
        bytes([0, 0, 0, 128, 128, 128, 255, 255, 255]),  # black, grey, white
    ]

    data = run_core.png(width, height, rows)
    decoded_width, decoded_height, decoded_rows = _decode_png(data)

    assert (decoded_width, decoded_height) == (width, height)
    assert decoded_rows == rows


def test_png_round_trips_output_of_to_rgb_rows():
    # End to end for one of the never-run formats: bytes from to_rgb_rows(RGB565, ...)
    # written by png() and read back by the independent decoder.
    words = [0xF800, 0x07E0, 0x001F, 0xFFFF]
    pixels = struct.pack("<4H", *words)
    rows = run_core.to_rgb_rows(pixels, run_core.PIXEL_RGB565, width=4, height=1, pitch=8)

    data = run_core.png(4, 1, rows)
    decoded_width, decoded_height, decoded_rows = _decode_png(data)

    assert (decoded_width, decoded_height) == (4, 1)
    assert decoded_rows == rows
    assert decoded_rows == [bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255])]


def test_memcard_beside_state_in_is_refused_before_anything_loads(tmp_path, capsys):
    # A Beetle state carries its own card, so the pair would silently swap the card back.
    status = run_core.main([str(tmp_path / "x.cue"), "--memcard", "c.mcd", "--state-in", "s.state"])
    assert status == run_core.EXIT_USAGE
    assert "--state-in" in capsys.readouterr().err


def test_the_captured_audio_is_a_wav_an_independent_reader_opens(tmp_path):
    """`--audio-out`: stereo 16-bit frames as the core hands them over, at its rate."""
    import wave

    pcm = struct.pack("<8h", 1, -1, 2, -2, 3, -3, 32767, -32768)
    path = tmp_path / "audio.wav"
    path.write_bytes(run_core.wav(44100, pcm))
    with wave.open(str(path)) as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (2, 2, 44100)
        assert audio.getnframes() == 4
        assert audio.readframes(4) == pcm
