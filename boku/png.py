"""A PNG reader and writer in the standard library alone (PLAN `GFX-01`).

The runtime here is stdlib-only on purpose (`pyproject.toml`), so the texture pipeline
cannot reach for Pillow. It needs two things that between them are a small fraction of
PNG: write an **indexed** image, because an exported texture whose palette is the TIM's
CLUT re-imports without a single colour decision; and read back whatever an artist's tool
saved, which means all five scanline filters, every palette bit depth, `tRNS`, and the
truecolour types a paint program reaches for when it flattens.

What is deliberately not here: interlacing (Adam7), which is refused with a message rather
than half-decoded, and writing anything but filter 0 — the reader has to handle a
stranger's filters, the writer never has to produce them.

Spec: PNG 1.2 / ISO 15948. Chunk CRCs are checked on the way in; a texture that silently
decodes to the wrong pixels would propagate into 2,607 places (`research/textures.md`).
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

SIGNATURE = b"\x89PNG\r\n\x1a\n"

GREY, RGB, PALETTE, GREY_ALPHA, RGBA = 0, 2, 3, 4, 6
_CHANNELS = {GREY: 1, RGB: 3, PALETTE: 1, GREY_ALPHA: 2, RGBA: 4}
_ALLOWED_DEPTHS = {
    GREY: (1, 2, 4, 8, 16),
    RGB: (8, 16),
    PALETTE: (1, 2, 4, 8),
    GREY_ALPHA: (8, 16),
    RGBA: (8, 16),
}


class PngError(Exception):
    """A PNG cannot be read, or cannot be written as asked."""


# --- writing ----------------------------------------------------------------------------


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def _pack_rows(width: int, height: int, samples: bytes, depth: int) -> bytes:
    """Scanlines with a leading filter byte of 0, sub-byte samples packed MSB first.

    MSB first means the *first* pixel of a 4-bit pair lands in the *high* nibble — the
    opposite of a 4bpp TIM, which is the one place these two formats disagree.
    """
    if depth == 8:
        rows: list[bytes] = [samples[y * width : (y + 1) * width] for y in range(height)]
    elif depth == 4 and width % 2 == 0:
        rows = [
            bytes(
                hi << 4 | lo
                for hi, lo in zip(
                    samples[y * width : (y + 1) * width : 2],
                    samples[y * width + 1 : (y + 1) * width : 2],
                    strict=True,
                )
            )
            for y in range(height)
        ]
    else:
        per_byte = 8 // depth
        stride = (width + per_byte - 1) // per_byte
        rows = []
        for y in range(height):
            row = bytearray(stride)
            for x, value in enumerate(samples[y * width : (y + 1) * width]):
                row[x // per_byte] |= value << (8 - depth * (x % per_byte + 1))
            rows.append(bytes(row))
    return b"".join(b"\x00" + row for row in rows)


def write_indexed(
    width: int,
    height: int,
    indices: bytes,
    palette: list[tuple[int, int, int]],
    alpha: list[int] | None = None,
    bit_depth: int | None = None,
) -> bytes:
    """An indexed PNG: `indices` is one byte per pixel, row by row.

    `bit_depth` defaults to the smallest that addresses the palette; a texture export
    passes the TIM's own depth so that what the artist opens has the shape of what the
    console draws. `alpha` is one 0..255 value per palette entry and becomes `tRNS`, with
    trailing opaque entries dropped as the spec allows.
    """
    if not palette:
        raise PngError("an indexed PNG needs at least one palette entry")
    if len(palette) > 256:
        raise PngError(f"an indexed PNG holds at most 256 colours, got {len(palette)}")
    if len(indices) != width * height:
        raise PngError(f"{width}x{height} needs {width * height} indices, got {len(indices)}")
    depth = bit_depth if bit_depth is not None else _smallest_depth(len(palette))
    if depth not in _ALLOWED_DEPTHS[PALETTE]:
        raise PngError(f"an indexed PNG cannot be {depth}-bit; PNG allows 1, 2, 4 or 8")
    if len(palette) > 1 << depth:
        raise PngError(f"{len(palette)} colours do not fit a {depth}-bit palette")
    over = [v for v in indices if v >= len(palette)]
    if over:
        raise PngError(f"index {max(over)} is past the {len(palette)}-colour palette")
    chunks = [
        _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, PALETTE, 0, 0, 0)),
        _chunk(b"PLTE", b"".join(bytes(c) for c in palette)),
    ]
    if alpha is not None:
        if len(alpha) != len(palette):
            raise PngError(f"tRNS has {len(alpha)} entries for {len(palette)} colours")
        trimmed = bytes(alpha).rstrip(b"\xff")
        if trimmed:
            chunks.append(_chunk(b"tRNS", trimmed))
    raw = _pack_rows(width, height, indices, depth)
    chunks.append(_chunk(b"IDAT", zlib.compress(raw, 9)))
    chunks.append(_chunk(b"IEND", b""))
    return SIGNATURE + b"".join(chunks)


def write_rgba(width: int, height: int, rgba: bytes) -> bytes:
    """An 8-bit RGBA PNG. For looking at something; the lossless path is `write_indexed`."""
    if len(rgba) != width * height * 4:
        raise PngError(f"{width}x{height} needs {width * height * 4} RGBA bytes, got {len(rgba)}")
    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride : (y + 1) * stride] for y in range(height))
    return SIGNATURE + b"".join(
        [
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, RGBA, 0, 0, 0)),
            _chunk(b"IDAT", zlib.compress(raw, 9)),
            _chunk(b"IEND", b""),
        ]
    )


def _smallest_depth(colours: int) -> int:
    return next(d for d in (1, 2, 4, 8) if colours <= 1 << d)


# --- reading ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Png:
    """A decoded PNG.

    An indexed one keeps its `indices` and builds RGBA only when asked: the texture
    importer wants indices, and turning 40 million palette entries into pixels on the way
    past would be most of the cost of an export gate that never looks at them.
    """

    width: int
    height: int
    bit_depth: int
    colour_type: int
    palette: tuple[tuple[int, int, int], ...] = ()
    alpha: tuple[int, ...] = ()
    """One value per palette entry, `tRNS` padded out with 255. Empty when there is no palette."""
    indices: bytes | None = None
    truecolour: bytes = b""
    """RGBA of a non-indexed PNG, already decoded. Read it through `rgba`, not directly."""

    @property
    def is_indexed(self) -> bool:
        return self.colour_type == PALETTE

    @property
    def rgba(self) -> bytes:
        """`width * height * 4` bytes, whatever the PNG's colour type."""
        if self.indices is None:
            return self.truecolour
        table = [bytes(c) + bytes([a]) for c, a in zip(self.palette, self.alpha, strict=True)]
        return b"".join(map(table.__getitem__, self.indices))


def read(data: bytes) -> Png:
    """Decode a PNG. Raises `PngError` with a reason rather than returning wrong pixels."""
    if not data.startswith(SIGNATURE):
        raise PngError("not a PNG: the 8-byte signature is missing")
    header: tuple[int, ...] | None = None
    palette: list[tuple[int, int, int]] = []
    trns = b""
    idat: list[bytes] = []
    pos = len(SIGNATURE)
    seen_end = False
    while pos < len(data):
        if len(data) - pos < 12:
            raise PngError(f"truncated chunk header at byte {pos}")
        (length,) = struct.unpack_from(">I", data, pos)
        kind = data[pos + 4 : pos + 8]
        if len(data) - pos < 12 + length:
            # The body *and* its four CRC bytes, in one test: a file cut off inside the
            # CRC has a complete body, and slicing it first left the CRC unpack to raise
            # `struct.error` past every caller that only catches `PngError`.
            raise PngError(
                f"chunk {kind.decode('latin-1')} at byte {pos} says {length} bytes and the "
                f"file has {len(data) - pos - 8} left for its body and CRC"
            )
        body = data[pos + 8 : pos + 8 + length]
        (stored,) = struct.unpack_from(">I", data, pos + 8 + length)
        if zlib.crc32(kind + body) != stored:
            raise PngError(f"chunk {kind.decode('latin-1')} at byte {pos} fails its CRC")
        pos += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            if length % 3:
                raise PngError(f"PLTE is {length} bytes, not a whole number of colours")
            palette = [tuple(body[i : i + 3]) for i in range(0, length, 3)]  # type: ignore[misc]
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            seen_end = True
            break
        elif not kind[0] & 0x20:
            raise PngError(f"unsupported critical chunk {kind.decode('latin-1')}")
    if header is None:
        raise PngError("no IHDR")
    if not seen_end:
        raise PngError("no IEND: the file is truncated")
    width, height, depth, colour, compression, filter_method, interlace = header
    if width == 0 or height == 0:
        raise PngError(f"IHDR says {width}x{height}")
    if colour not in _CHANNELS:
        raise PngError(f"colour type {colour} is not a PNG colour type")
    if depth not in _ALLOWED_DEPTHS[colour]:
        raise PngError(f"bit depth {depth} is not allowed for colour type {colour}")
    if compression or filter_method:
        raise PngError(f"unknown compression {compression} / filter method {filter_method}")
    if interlace:
        raise PngError(
            "this PNG is interlaced (Adam7); save it without interlacing. Decoding it "
            "half-way would hand back plausible wrong pixels."
        )
    if colour == PALETTE and not palette:
        raise PngError("an indexed PNG with no PLTE")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise PngError(f"IDAT does not inflate: {exc}") from None
    channels = _CHANNELS[colour]
    bits = channels * depth
    stride = (width * bits + 7) // 8
    lines = _unfilter(raw, width, height, stride, max(1, bits // 8))
    return _to_pixels(width, height, depth, colour, lines, palette, trns)


def _unfilter(raw: bytes, width: int, height: int, stride: int, step: int) -> list[bytearray]:
    want = (stride + 1) * height
    if len(raw) != want:
        raise PngError(f"{width}x{height} needs {want} filtered bytes, IDAT gave {len(raw)}")
    out: list[bytearray] = []
    previous = bytearray(stride)
    for y in range(height):
        base = y * (stride + 1)
        kind = raw[base]
        line = bytearray(raw[base + 1 : base + 1 + stride])
        if kind == 0:
            pass
        elif kind == 1:
            for i in range(step, stride):
                line[i] = (line[i] + line[i - step]) & 0xFF
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif kind == 3:
            for i in range(stride):
                left = line[i - step] if i >= step else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                left = line[i - step] if i >= step else 0
                up = previous[i]
                upleft = previous[i - step] if i >= step else 0
                line[i] = (line[i] + _paeth(left, up, upleft)) & 0xFF
        else:
            raise PngError(f"scanline {y} uses filter {kind}; PNG defines 0 to 4")
        out.append(line)
        previous = line
    return out


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _samples(line: bytearray, width: int, depth: int) -> list[int]:
    """One value per sample, unpacking sub-byte depths MSB first."""
    if depth == 8:
        return list(line[:width])
    if depth == 16:
        return [line[i * 2] for i in range(width)]  # the high byte is all an 8-bit pipeline wants
    per_byte = 8 // depth
    mask = (1 << depth) - 1
    return [(line[x // per_byte] >> (8 - depth * (x % per_byte + 1))) & mask for x in range(width)]


def _to_pixels(width, height, depth, colour, lines, palette, trns) -> Png:
    channels = _CHANNELS[colour]
    if colour == PALETTE:
        if len(trns) > len(palette):
            raise PngError(f"tRNS has {len(trns)} entries for a {len(palette)}-colour PLTE")
        alpha = list(trns) + [255] * (len(palette) - len(trns))
        indices = _indices(lines, width, depth)
        highest = max(indices, default=0)
        if highest >= len(palette):
            raise PngError(f"a pixel indexes entry {highest} of a {len(palette)}-colour PLTE")
        return Png(width, height, depth, colour, tuple(palette), tuple(alpha), indices)
    scale = 255 if depth == 1 else (85 if depth == 2 else (17 if depth == 4 else 1))
    key = _colour_key(colour, depth, trns)
    rgba = bytearray()
    for line in lines:
        values = _samples(line, width * channels, depth)
        for x in range(width):
            px = values[x * channels : (x + 1) * channels]
            raw_px = tuple(px)
            if depth < 8:
                px = [v * scale for v in px]
            if colour == GREY:
                out = (px[0], px[0], px[0], 0 if key == raw_px else 255)
            elif colour == GREY_ALPHA:
                out = (px[0], px[0], px[0], px[1])
            elif colour == RGB:
                out = (px[0], px[1], px[2], 0 if key == raw_px else 255)
            else:
                out = (px[0], px[1], px[2], px[3])
            rgba += bytes(out)
    return Png(width, height, depth, colour, truecolour=bytes(rgba))


_NIBBLES = [bytes([b >> 4, b & 0xF]) for b in range(256)]


def _indices(lines: list[bytearray], width: int, depth: int) -> bytes:
    """Palette indices, one byte each, row by row — the hot path of an 824-image export."""
    if depth == 8:
        return b"".join(bytes(line[:width]) for line in lines)
    if depth == 4:
        return b"".join(b"".join(map(_NIBBLES.__getitem__, line))[:width] for line in lines)
    return b"".join(bytes(_samples(line, width, depth)) for line in lines)


def _colour_key(colour: int, depth: int, trns: bytes) -> tuple[int, ...] | None:
    """The one fully transparent colour `tRNS` may name for a non-indexed image."""
    if not trns:
        return None
    n = 1 if colour == GREY else 3
    if colour not in (GREY, RGB) or len(trns) != n * 2:
        raise PngError(f"tRNS of {len(trns)} bytes is not valid for colour type {colour}")
    values = struct.unpack(f">{n}H", trns)
    return tuple(v >> 8 if depth == 16 else v for v in values)
