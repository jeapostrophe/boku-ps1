"""PsyQ TIM images: parse, serialise, decode and re-encode (PLAN `GFX-01`).

The census of what is actually on this disc — every TIM 4bpp/16 or 8bpp/256 with a CLUT,
the CLUT block's VRAM origin non-zero in 758 of them, 488 images carrying several CLUTs —
is `research/textures.md`; it is not repeated here. What this module adds is the property
that census tooling did not need: **a parse that loses nothing**, so that
`parse(b).serialise() == b` for every TIM on the disc and an edit can be written back into
the archive as a few changed bytes.

The layout::

    u32 magic  = 0x10
    u32 flags  : bits 0..2 pmode (0=4bpp, 1=8bpp, 2=16bpp, 3=24bpp), bit 3 = CLUT present
    if CLUT:   u32 block_bytes (incl. these 12), u16 vram_x, u16 vram_y,
               u16 colours, u16 cluts, then colours*cluts u16 entries
    pixels:    u32 block_bytes (incl. these 12), u16 vram_x, u16 vram_y,
               u16 w, u16 h, then w*h u16 of packed pixel data

`w` counts **16-bit VRAM units**, not pixels, so the image width is `w*4` at 4bpp and `w*2`
at 8bpp — and a 4bpp image whose artist-intended width is not a multiple of four cannot say
so: the TIM records only the padded width, and that is the width this module reports and
round-trips.

A colour is 16-bit ABGR1555: bits 0..4 R, 5..9 G, 10..14 B, bit 15 STP. `0x0000` is fully
transparent. STP on a non-zero colour asks the GPU to blend rather than replace, which is
not something RGBA can carry, so `decode_rgba` renders such a pixel opaque and
`decode_stp` hands back the bit beside it; nothing here ever drops it, because the CLUT is
carried through an edit word for word.

Editing rules, which exist because a texture on this disc is shared: `with_indices` changes
pixels and nothing else — not the depth, not the dimensions, not either VRAM origin, not
one byte of any CLUT. Mapping an artist's colours onto the palette is `indices_from_rgba`,
which refuses a colour the CLUT does not contain; `nearest_indices` is the explicit
opt-in that approximates instead, and reports the error it introduced.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass, replace

MAGIC = 0x10
CLUT_FLAG = 0x8
PMODE_BPP = {0: 4, 1: 8, 2: 16, 3: 24}
INDEXED_BPP = (4, 8)


class TimError(Exception):
    """A TIM cannot be built, or cannot be re-encoded the way it was asked for."""


class OffPalette(TimError):
    """An edited image uses a colour that is not in the TIM's CLUT."""


def rgba_of_word(word: int) -> tuple[int, int, int, int]:
    """ABGR1555 to 8-bit RGBA. `0x0000` is the transparent colour, everything else opaque."""
    if word == 0:
        return (0, 0, 0, 0)
    r = word & 0x1F
    g = (word >> 5) & 0x1F
    b = (word >> 10) & 0x1F
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 255)


def stp_of_word(word: int) -> int:
    """The semi-transparency bit, which RGBA has nowhere to put."""
    return (word >> 15) & 1


def word_of_rgb(r: int, g: int, b: int, stp: int = 0) -> int:
    """8-bit RGB to ABGR1555, rounding to nearest. The inverse of `rgba_of_word` is lossy."""
    return (
        min(31, (r + 4) >> 3)
        | min(31, (g + 4) >> 3) << 5
        | min(31, (b + 4) >> 3) << 10
        | (stp & 1) << 15
    )


@dataclass(frozen=True)
class Clut:
    """One CLUT block: its VRAM placement and every palette in it, as raw 16-bit words.

    The words are kept raw rather than as RGBA because the STP bit and the difference
    between `0x0000` and an opaque black `0x8000` both have to survive a round trip, and
    neither survives a conversion to colours.
    """

    x: int
    y: int
    colours: int
    count: int
    """How many palettes the block holds; up to 21 on this disc."""
    words: tuple[int, ...]
    """`colours * count` entries, palette 0 first."""
    padding: bytes = b""
    """Bytes the block declares beyond its entries. Empty in every TIM on the disc."""

    def __post_init__(self) -> None:
        if self.colours <= 0 or self.count <= 0:
            raise TimError(
                f"a CLUT block needs colours and cluts > 0, got {self.colours}x{self.count}"
            )
        if len(self.words) != self.colours * self.count:
            raise TimError(
                f"CLUT declares {self.count} palettes of {self.colours} colours "
                f"({self.colours * self.count} words) but carries {len(self.words)}"
            )

    @property
    def block_bytes(self) -> int:
        return 12 + len(self.words) * 2 + len(self.padding)

    def palette(self, index: int = 0) -> tuple[int, ...]:
        """Palette `index`, as raw words.

        Past the last palette the words run into the pixel block's header and make a
        plausible-looking but fictitious palette, so this refuses rather than slices.
        """
        if not 0 <= index < self.count:
            raise TimError(f"CLUT {index} out of range; this TIM has {self.count}")
        return self.words[index * self.colours : (index + 1) * self.colours]

    def serialise(self) -> bytes:
        return (
            struct.pack("<IHHHH", self.block_bytes, self.x, self.y, self.colours, self.count)
            + struct.pack(f"<{len(self.words)}H", *self.words)
            + self.padding
        )


@dataclass(frozen=True)
class Tim:
    """A parsed TIM. Every field the file carries is here, so `serialise` is exact."""

    flags: int
    """The whole flags word, not just the depth: reserved bits round-trip too."""
    x: int
    y: int
    stride_words: int
    """The pixel block's `w`, in 16-bit VRAM units. `width` is the pixel count."""
    height: int
    data: bytes
    """`stride_words * height * 2` raw bytes of packed pixels."""
    clut: Clut | None = None
    padding: bytes = b""
    """Bytes the pixel block declares beyond `data`. Empty in every TIM on the disc."""

    def __post_init__(self) -> None:
        if self.flags & ~0xF:
            raise TimError(f"TIM flags 0x{self.flags:x} set bits outside the low nibble")
        if self.pmode not in PMODE_BPP:
            raise TimError(f"TIM pmode {self.pmode} is not one of {sorted(PMODE_BPP)}")
        if (self.clut is not None) != bool(self.flags & CLUT_FLAG):
            raise TimError(
                f"flags 0x{self.flags:x} and clut={self.clut is not None} disagree about "
                f"whether this TIM has a CLUT block"
            )
        want = self.stride_words * self.height * 2
        if len(self.data) != want:
            raise TimError(
                f"pixel block is {self.stride_words}x{self.height} 16-bit units "
                f"({want} bytes) but carries {len(self.data)}"
            )

    @property
    def pmode(self) -> int:
        return self.flags & 7

    @property
    def bpp(self) -> int:
        return PMODE_BPP[self.pmode]

    @property
    def width(self) -> int:
        """Pixels across. At 4bpp this is always a multiple of four — see the module docstring."""
        if self.bpp == 24:
            if self.stride_words * 2 % 3:
                raise TimError(f"24bpp stride {self.stride_words} is not a whole number of pixels")
            return self.stride_words * 2 // 3
        return self.stride_words * (16 // self.bpp)

    @property
    def row_bytes(self) -> int:
        return self.stride_words * 2

    @property
    def length(self) -> int:
        """Byte length of the serialised TIM."""
        return (
            8
            + (self.clut.block_bytes if self.clut else 0)
            + 12
            + len(self.data)
            + len(self.padding)
        )

    def serialise(self) -> bytes:
        return (
            struct.pack("<II", MAGIC, self.flags)
            + (self.clut.serialise() if self.clut else b"")
            + struct.pack(
                "<IHHHH",
                12 + len(self.data) + len(self.padding),
                self.x,
                self.y,
                self.stride_words,
                self.height,
            )
            + self.data
            + self.padding
        )

    # --- indexed pixels ------------------------------------------------------------

    def _require_indexed(self) -> int:
        if self.bpp not in INDEXED_BPP:
            raise TimError(
                f"{self.bpp}bpp TIMs carry no palette indices. The disc holds none "
                f"(research/textures.md), so this path is deliberately unwritten."
            )
        return self.bpp

    def indices(self) -> bytes:
        """One byte per pixel, `width * height` of them, row by row.

        At 4bpp the low nibble of a byte is the left-hand pixel; that order is confirmed
        by the glyph sheet and the UI buttons coming out legible (research/textures.md).
        """
        bpp = self._require_indexed()
        if bpp == 8:
            return self.data
        out = bytearray(self.width * self.height)
        out[0::2] = bytes(v & 0xF for v in self.data)
        out[1::2] = bytes(v >> 4 for v in self.data)
        return bytes(out)

    def highest_index(self) -> int:
        """The largest palette index the image uses, without building the index array."""
        bpp = self._require_indexed()
        if not self.data:
            return 0
        if bpp == 8:
            return max(self.data)
        return max(self.data.translate(_NIBBLE_MAX))

    def with_indices(self, indices: bytes) -> Tim:
        """A copy with new pixels and *nothing else* changed.

        Depth, dimensions, both VRAM origins and every CLUT byte are carried over
        untouched, which is what makes an edit safe to write into all 2,607 places a
        texture is stored. An index the CLUT cannot address is refused, unless the
        original image already used it: a TIM is allowed to index past its own palette,
        and an edit is never the thing that makes an image unrepresentable. No image on
        this disc does it — every CLUT is exactly 16 or 256 wide — so the carve-out is
        for a format that permits it, not for a measured case.
        """
        bpp = self._require_indexed()
        want = self.width * self.height
        if len(indices) != want:
            raise TimError(
                f"this TIM is {self.width}x{self.height} ({want} pixels) but {len(indices)} "
                f"indices were given"
            )
        limit = 1 << bpp
        over = {v for v in indices if v >= limit}
        if over:
            raise TimError(
                f"index {min(over)} does not fit {bpp}bpp (0..{limit - 1}); the depth of a "
                f"texture is never changed"
            )
        if self.clut is not None:
            allowed = self.clut.colours
            unusable = {v for v in indices if v >= allowed} - set(self.indices())
            if unusable:
                raise OffPalette(
                    f"index {min(unusable)} is past this TIM's {allowed}-colour CLUT and the "
                    f"original did not use it"
                )
        if bpp == 8:
            return replace(self, data=bytes(indices))
        packed = bytes(lo | hi << 4 for lo, hi in zip(indices[0::2], indices[1::2], strict=True))
        return replace(self, data=packed)

    # --- colour --------------------------------------------------------------------

    def _palette(self, index: int) -> tuple[int, ...]:
        if self.clut is None:
            raise TimError("this TIM carries no CLUT")
        return self.clut.palette(index)

    def palette_rgba(self, index: int = 0) -> list[tuple[int, int, int, int]]:
        return [rgba_of_word(w) for w in self._palette(index)]

    def palette_stp(self, index: int = 0) -> list[int]:
        """The STP bit of each palette entry — the side channel RGBA cannot carry."""
        return [stp_of_word(w) for w in self._palette(index)]

    def decode_rgba(self, index: int = 0) -> bytes:
        """`width * height * 4` bytes of RGBA, through palette `index`."""
        pal = self.palette_rgba(index)
        pal = _padded(pal, 1 << self._require_indexed(), (255, 0, 255, 255))
        table = [bytes(c) for c in pal]
        return b"".join(map(table.__getitem__, self.indices()))

    def decode_stp(self, index: int = 0) -> bytes:
        """One byte per pixel: the STP bit of the colour that pixel resolves to."""
        stp = _padded(self.palette_stp(index), 1 << self._require_indexed(), 0)
        return bytes(map(stp.__getitem__, self.indices()))


_NIBBLE_MAX = bytes(max(v >> 4, v & 0xF) for v in range(256))


def _padded(values: list, length: int, filler) -> list:
    """Pad a palette out to the depth's full range, for a CLUT shorter than `2**bpp`."""
    return values + [filler] * (length - len(values)) if len(values) < length else values


# --- parsing --------------------------------------------------------------------------


def parse(b: bytes, offset: int = 0) -> Tim | None:
    """Parse the TIM at `b[offset:]`, or return `None` when that is not a well-formed one.

    `None` rather than an exception because the enumerator in `boku.textures` parses at
    every 4-aligned occurrence of the magic word and most of them are not TIMs. The
    acceptance test that does the work is the pixel block's declared size having to equal
    `12 + w*h*2` exactly (or that rounded up to a word), which random data does not
    satisfy.
    """
    if len(b) - offset < 20:
        return None
    magic, flags = struct.unpack_from("<II", b, offset)
    if magic != MAGIC or flags & ~0xF or (flags & 7) > 3:
        return None
    p = offset + 8
    clut = None
    if flags & CLUT_FLAG:
        (block,) = struct.unpack_from("<I", b, p)
        if block < 12 or p + block > len(b):
            return None
        x, y, colours, count = struct.unpack_from("<HHHH", b, p + 4)
        if colours == 0 or count == 0 or 12 + colours * count * 2 > block:
            return None
        n = colours * count
        words = struct.unpack_from(f"<{n}H", b, p + 12)
        clut = Clut(x, y, colours, count, words, bytes(b[p + 12 + n * 2 : p + block]))
        p += block
    if len(b) - p < 12:
        return None
    block, x, y, w, h = struct.unpack_from("<IHHHH", b, p)
    pixels = w * h * 2
    if block not in (12 + pixels, 12 + ((pixels + 3) & ~3)):
        return None
    if p + block > len(b) or w == 0 or h == 0:
        return None
    data = bytes(b[p + 12 : p + 12 + pixels])
    return Tim(flags, x, y, w, h, data, clut, bytes(b[p + 12 + pixels : p + block]))


def parse_exact(b: bytes, offset: int = 0) -> Tim:
    """`parse`, but raising — for a caller that already knows there is a TIM here."""
    tim = parse(b, offset)
    if tim is None:
        raise TimError(f"no TIM at offset 0x{offset:x}")
    return tim


# --- mapping an edited image back onto the palette ------------------------------------

_MATCH_BLOCK = 4096
"""Pixels compared at a time. A block that is identical is skipped without a Python loop,
which is what keeps an 824-image gate over 64M pixels to seconds rather than minutes."""


def _recoloured(tim: Tim, rgba: bytes, clut: int) -> Iterator[int]:
    """Pixel positions whose RGBA is *not* the colour the TIM already renders there.

    Everywhere else the answer is the index that is already stored, so the caller never
    has to choose between two palette entries holding the same colour.
    """
    was = tim.decode_rgba(clut)
    pixels = len(rgba) // 4
    for start in range(0, pixels, _MATCH_BLOCK):
        stop = min(start + _MATCH_BLOCK, pixels)
        if rgba[start * 4 : stop * 4] == was[start * 4 : stop * 4]:
            continue
        for i in range(start, stop):
            if rgba[i * 4 : i * 4 + 4] == was[i * 4 : i * 4 + 4]:
                continue
            if rgba[i * 4 + 3] == 0 and was[i * 4 + 3] == 0:
                continue  # both fully transparent; an editor's junk RGB is not a recolour
            yield i


def indices_from_rgba(tim: Tim, rgba: bytes, clut: int = 0) -> bytes:
    """Map RGBA pixels onto palette entries, refusing any colour the CLUT lacks.

    This is the default path on purpose: silently approximating an artist's colour is how
    a shared palette drifts. **A pixel whose colour is still the colour it already had
    keeps its own index**, whatever else in the palette holds that colour: 2,473 of this
    disc's (texture, CLUT) pairs carry duplicate colours, and a lookup keyed on colour
    alone answers an untouched pixel with some other entry — re-pointing 6.1M indices
    across 455 images and flipping 38,937 STP bits on a round trip that changed nothing.
    Only a pixel the artist actually recoloured is looked up, and there the lower of two
    equal entries wins.
    """
    want = tim.width * tim.height * 4
    if len(rgba) != want:
        raise TimError(
            f"this TIM is {tim.width}x{tim.height} ({want} RGBA bytes) but {len(rgba)} were given"
        )
    lookup: dict[tuple[int, ...], int] = {}
    for i, colour in enumerate(tim.palette_rgba(clut)):
        lookup.setdefault(colour, i)
    out = bytearray(tim.indices())
    missing: dict[tuple[int, ...], int] = {}
    for i in _recoloured(tim, rgba, clut):
        px = tuple(rgba[i * 4 : i * 4 + 4])
        if px[3] == 0:
            px = (0, 0, 0, 0)
        found = lookup.get(px)
        if found is None:
            missing[px] = missing.get(px, 0) + 1
        else:
            out[i] = found
    if missing:
        worst = sorted(missing.items(), key=lambda kv: -kv[1])[:5]
        shown = ", ".join(f"#{r:02x}{g:02x}{b:02x}{a:02x} x{n}" for (r, g, b, a), n in worst)
        raise OffPalette(
            f"{sum(missing.values())} pixels in {len(missing)} colours are not in CLUT {clut} "
            f"of this TIM: {shown}. Keep to the exported palette, or ask for nearest-entry "
            f"mapping and accept the error it reports."
        )
    return bytes(out)


@dataclass(frozen=True)
class Quantisation:
    """What `nearest_indices` had to change, so the caller can decide whether to accept it."""

    pixels: int
    approximated: int
    """Pixels whose colour was not in the palette."""
    worst: int
    """Largest distance moved, as the sum of the three channel differences (0..765)."""
    mean: float
    """Mean distance over the approximated pixels."""
    examples: tuple[tuple[tuple[int, int, int, int], int, int], ...]
    """Up to five (source RGBA, chosen index, distance), worst first."""

    def describe(self) -> str:
        if not self.approximated:
            return "every colour was already in the palette"
        shown = ", ".join(
            f"#{r:02x}{g:02x}{b:02x}{a:02x}->{i} (d={d})" for (r, g, b, a), i, d in self.examples
        )
        return (
            f"{self.approximated} of {self.pixels} pixels approximated, worst distance "
            f"{self.worst}, mean {self.mean:.1f}: {shown}"
        )


def nearest_indices(tim: Tim, rgba: bytes, clut: int = 0) -> tuple[bytes, Quantisation]:
    """Map RGBA onto the palette by nearest entry, reporting the error introduced.

    A pixel still holding the colour it already had keeps its own index, exactly as in
    `indices_from_rgba` and for the same reason; only a recoloured one is approximated,
    so the report counts what the artist changed rather than what duplicate entries did.

    Transparency is not approximated: a fully transparent pixel needs a `0x0000` entry and
    an opaque one is never mapped onto one, because the two are different things to the
    GPU rather than nearby colours.
    """
    want = tim.width * tim.height * 4
    if len(rgba) != want:
        raise TimError(
            f"this TIM is {tim.width}x{tim.height} ({want} RGBA bytes) but {len(rgba)} were given"
        )
    palette = tim.palette_rgba(clut)
    opaque = [(i, c) for i, c in enumerate(palette) if c[3]]
    clear = next((i for i, c in enumerate(palette) if not c[3]), None)
    if not opaque:
        raise TimError(f"CLUT {clut} of this TIM holds no opaque colour to map onto")
    exact: dict[tuple[int, ...], int] = {}
    for i, colour in enumerate(palette):
        exact.setdefault(colour, i)
    cache: dict[tuple[int, ...], tuple[int, int]] = {}
    out = bytearray(tim.indices())
    moved: list[tuple[tuple[int, int, int, int], int, int]] = []
    for i in _recoloured(tim, rgba, clut):
        px = tuple(rgba[i * 4 : i * 4 + 4])
        if px[3] == 0:
            px = (0, 0, 0, 0)
        found = exact.get(px)
        if found is not None:
            out[i] = found
            continue
        if px[3] == 0:
            if clear is None:
                raise OffPalette(
                    f"the image has transparent pixels and CLUT {clut} has no transparent entry"
                )
            out[i] = clear
            continue
        hit = cache.get(px)
        if hit is None:
            best = min(opaque, key=lambda ic: _distance(px, ic[1]))
            hit = cache[px] = (best[0], _distance(px, best[1]))
        out[i] = hit[0]
        moved.append((px, hit[0], hit[1]))  # type: ignore[arg-type]
    worst = sorted(set(moved), key=lambda m: -m[2])[:5]
    return bytes(out), Quantisation(
        pixels=len(out),
        approximated=len(moved),
        worst=max((m[2] for m in moved), default=0),
        mean=(sum(m[2] for m in moved) / len(moved)) if moved else 0.0,
        examples=tuple(worst),
    )


def _distance(a: tuple[int, ...], b: tuple[int, int, int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
