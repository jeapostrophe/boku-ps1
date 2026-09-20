"""Synthetic TIMs, built from the PsyQ layout with `struct` and nothing else.

Deliberately a second implementation of the format: `boku.tim` is not used to make the
fixtures it is measured against, so a parser and a serialiser that agree on a wrong layout
cannot both be green (`~/.claude/CLAUDE.md` ENG-1). The pixel bytes here are invented —
nothing on the disc is ever copied into the repo (CLAUDE.md § "This repo is public").
"""

from __future__ import annotations

import struct


def clut_block(
    colours: int, count: int, words, *, x: int = 0, y: int = 0, pad: bytes = b""
) -> bytes:
    """A CLUT block. `words` is `colours * count` raw ABGR1555 entries, palette 0 first."""
    assert len(words) == colours * count
    body = struct.pack(f"<{len(words)}H", *words)
    return struct.pack("<IHHHH", 12 + len(body) + len(pad), x, y, colours, count) + body + pad


def pixel_block(w: int, h: int, data: bytes, *, x: int = 0, y: int = 0, pad: bytes = b"") -> bytes:
    """A pixel block. `w` is the width in 16-bit VRAM units, so `data` is `w*h*2` bytes."""
    assert len(data) == w * h * 2
    return struct.pack("<IHHHH", 12 + len(data) + len(pad), x, y, w, h) + data + pad


def tim(pmode: int, pixels: bytes, *, clut: bytes | None = None, **kw) -> bytes:
    flags = pmode | (0x8 if clut is not None else 0)
    return struct.pack("<II", 0x10, flags) + (clut or b"") + pixels


def ramp(n: int) -> list[int]:
    """`n` distinct non-zero ABGR1555 words, entry 0 transparent — a usable little palette."""
    out = [0]
    for i in range(1, n):
        out.append((i & 0x1F) | ((i * 3) & 0x1F) << 5 | ((i * 7) & 0x1F) << 10)
    return out


def image_4bpp(width: int, height: int, indices: list[int]) -> bytes:
    """Pack 4bpp indices, low nibble first, into pixel-block bytes."""
    assert width % 4 == 0 and len(indices) == width * height
    return bytes(indices[i] | indices[i + 1] << 4 for i in range(0, len(indices), 2))
