"""PNGs assembled from the spec with `zlib` and `struct`, independently of `boku.png`.

`boku.png` writes filter 0 and nothing else, so nothing in it would ever exercise the four
filters an artist's tool will hand back. These build them, from the ISO 15948 formulas
rather than from the reader's inverse of them — and `tests/test_png.py` puts the result
through `sips` as well, so a mistake here and a matching mistake in the reader cannot pass
together (`~/.claude/CLAUDE.md` ENG-1).
"""

from __future__ import annotations

import struct
import subprocess
import zlib
from pathlib import Path
from shutil import which

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def filtered(rows: list[bytes], kind: int, step: int) -> bytes:
    """Filter each scanline with `kind`, the encoder side of PNG's five filter types."""
    out = bytearray()
    previous = bytes(len(rows[0]))
    for row in rows:
        encoded = bytearray(len(row))
        for i, value in enumerate(row):
            left = row[i - step] if i >= step else 0
            up = previous[i]
            upleft = previous[i - step] if i >= step else 0
            if kind == 0:
                encoded[i] = value
            elif kind == 1:
                encoded[i] = (value - left) & 0xFF
            elif kind == 2:
                encoded[i] = (value - up) & 0xFF
            elif kind == 3:
                encoded[i] = (value - ((left + up) >> 1)) & 0xFF
            else:
                encoded[i] = (value - paeth(left, up, upleft)) & 0xFF
        out += bytes([kind]) + encoded
        previous = row
    return bytes(out)


def assemble(
    width: int, height: int, depth: int, colour: int, idat: bytes, extra: bytes = b""
) -> bytes:
    return (
        SIGNATURE
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, 0))
        + extra
        + chunk(b"IDAT", zlib.compress(idat))
        + chunk(b"IEND", b"")
    )


def rgb_png(width: int, height: int, rows: list[bytes], kind: int) -> bytes:
    return assemble(width, height, 8, 2, filtered(rows, kind, 3))


SIPS = which("sips")


def sips_reencode(data: bytes, tmp_path: Path, name: str = "in") -> bytes:
    """Re-save a PNG through macOS `sips` (libpng), returning the bytes it wrote."""
    src = tmp_path / f"{name}.png"
    dst = tmp_path / f"{name}-sips.png"
    src.write_bytes(data)
    subprocess.run(
        [SIPS, "-s", "format", "png", str(src), "--out", str(dst)],
        check=True,
        capture_output=True,
    )
    return dst.read_bytes()


def sips_properties(data: bytes, tmp_path: Path, *keys: str) -> dict[str, str]:
    """What `sips` says about a PNG we wrote: an independent reader of our writer."""
    src = tmp_path / "probe.png"
    src.write_bytes(data)
    argv = [SIPS]
    for key in keys:
        argv += ["-g", key]
    argv.append(str(src))
    out = subprocess.run(argv, check=True, capture_output=True, text=True).stdout
    found = {}
    for line in out.splitlines():
        if ":" in line and line.startswith(" "):
            key, _, value = line.strip().partition(":")
            found[key] = value.strip()
    return found
