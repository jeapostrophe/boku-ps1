#!/usr/bin/env python3
"""Convert the .raw framebuffer dumps lib.lua's shot() writes into PNGs (stdlib only).

    tools/redux/shot2png.py work/txt01-emu/shots/*.raw      # writes NAME.png beside each
    tools/redux/shot2png.py --scale 2 --crop X,Y,W,H file.raw

Input: 16-byte header b"BOKUSHOT", u16 width, height, bpp (16 or 24), 0; then pixels.
16 bpp is the PS1's native word: bits 0-4 red, 5-9 green, 10-14 blue. Output PNGs are the
game's pixels — they stay under the gitignored work/.
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path


def decode(raw: bytes):
    if raw[:8] != b"BOKUSHOT":
        raise ValueError("not a BOKUSHOT file")
    w, h, bpp, _ = struct.unpack_from("<HHHH", raw, 8)
    px = raw[16:]
    rows = []
    if bpp == 16:
        if len(px) < w * h * 2:
            raise ValueError(f"short pixel data: {len(px)} < {w * h * 2}")
        words = struct.unpack_from(f"<{w * h}H", px)
        lut = [(v << 3) | (v >> 2) for v in range(32)]
        for y in range(h):
            row = bytearray()
            for v in words[y * w : (y + 1) * w]:
                row += bytes((lut[v & 31], lut[(v >> 5) & 31], lut[(v >> 10) & 31]))
            rows.append(bytes(row))
    else:
        if len(px) < w * h * 3:
            raise ValueError(f"short pixel data: {len(px)} < {w * h * 3}")
        for y in range(h):
            rows.append(px[y * w * 3 : (y + 1) * w * 3])
    return w, h, rows


def png(w: int, h: int, rows) -> bytes:
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    body = b"".join(b"\0" + r for r in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(body, 6))
        + chunk(b"IEND", b"")
    )


def sheet(files, out: Path, cols: int) -> int:
    """Tile shots with 2 px black gutters. The display mode changes between screens
    (640x478 BIOS, 640x480 logos, 320x240 game), so each cell is padded with black to the
    largest shot rather than scaled — pixels stay 1:1."""
    imgs = [decode(f.read_bytes()) for f in files]
    w = max(i[0] for i in imgs)
    h = max(i[1] for i in imgs)
    imgs = [
        (w, h, [r + b"\0" * ((w - iw) * 3) for r in rows] + [b"\0" * (w * 3)] * (h - ih))
        for iw, ih, rows in imgs
    ]
    n_rows = -(-len(imgs) // cols)
    gut = b"\0" * 6
    blank = b"\0" * (w * 3)
    rows = []
    for r in range(n_rows):
        cells = [imgs[i][2] if i < len(imgs) else None for i in range(r * cols, (r + 1) * cols)]
        for y in range(h):
            rows.append(gut.join(c[y] if c else blank for c in cells))
        rows.extend([b"\0" * len(rows[-1])] * 2)
    out.write_bytes(png(len(rows[0]) // 3, len(rows), rows))
    print(out, len(rows[0]) // 3, len(rows))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--crop", help="X,Y,W,H in source pixels")
    ap.add_argument("--suffix", default="", help="appended to the output stem")
    ap.add_argument(
        "--sheet",
        type=Path,
        help="write ONE contact sheet of all inputs (row-major, in argument order)",
    )
    ap.add_argument("--cols", type=int, default=4)
    a = ap.parse_args()
    if a.sheet:
        return sheet(a.files, a.sheet, a.cols)
    for f in a.files:
        w, h, rows = decode(f.read_bytes())
        if a.crop:
            x, y, cw, ch = (int(v) for v in a.crop.split(","))
            rows = [r[x * 3 : (x + cw) * 3] for r in rows[y : y + ch]]
            w, h = cw, len(rows)
        if a.scale > 1:
            s = a.scale
            rows = [
                b"".join(r[i : i + 3] * s for i in range(0, len(r), 3))
                for r in rows
                for _ in range(s)
            ]
            w, h = w * s, h * s
        out = f.with_name(f.stem + a.suffix + ".png")
        out.write_bytes(png(w, h, rows))
        print(out, w, h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
