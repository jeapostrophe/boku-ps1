#!/usr/bin/env python3
"""Pull VRAM out of a PCSX-Redux save state — the headless route to raw VRAM.

Under -no-ui the emulator's web server never listens and Lua has no VRAM accessor, but
PCSX.createSaveState() serialises the whole machine as protobuf, and the GPU message
carries VRAM as one bytes field of exactly 0x100000 (src/core/sstate.h: `GPUVRam`,
FixedBytes<0x00100000>). This walks the wire format generically and takes the first
length-delimited field of that size, so it needs no schema.

    sstate_vram.py STATE [STATE...] [--rect X,Y,W,H] [--png DIR]

Prints sha256 of the rect (default 768,0,64,256 — the font page) for each state; with
--png writes the rect as a 15-bit-direct PNG (a CLUT page viewed as direct colour is
false-colour, but identical bytes give identical pictures, which is the question).
Output is game data: keep it under work/.
"""

import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

VRAM_BYTES = 0x100000


def varint(b: bytes, i: int):
    v = s = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return v, i


def find_vram(b: bytes, depth: int = 0):
    i = 0
    n = len(b)
    try:
        while i < n:
            key, i = varint(b, i)
            wt = key & 7
            if wt == 0:
                _, i = varint(b, i)
            elif wt == 1:
                i += 8
            elif wt == 5:
                i += 4
            elif wt == 2:
                ln, i = varint(b, i)
                if i + ln > n:
                    return None
                if ln == VRAM_BYTES:
                    return b[i : i + ln]
                if ln > VRAM_BYTES and depth < 4:
                    r = find_vram(b[i : i + ln], depth + 1)
                    if r is not None:
                        return r
                i += ln
            else:
                return None
    except IndexError:
        return None
    return None


def png(w, h, rows):
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("states", nargs="+", type=Path)
    ap.add_argument("--rect", default="768,0,64,256")
    ap.add_argument("--png", type=Path)
    a = ap.parse_args()
    x, y, w, h = (int(v) for v in a.rect.split(","))
    lut = [(v << 3) | (v >> 2) for v in range(32)]
    for p in a.states:
        raw = p.read_bytes()
        if raw[:2] in (b"\x78\x9c", b"\x78\xda", b"\x78\x01"):
            raw = zlib.decompress(raw)
        vram = find_vram(raw)
        if vram is None:
            print(f"{p}: no {VRAM_BYTES}-byte field found", file=sys.stderr)
            return 1
        rect = b"".join(
            vram[((y + r) * 1024 + x) * 2 : ((y + r) * 1024 + x + w) * 2] for r in range(h)
        )
        nonzero = sum(1 for v in rect if v)
        print(f"{hashlib.sha256(rect).hexdigest()[:16]}  nonzero={nonzero:6d}  {p.name}")
        if a.png:
            a.png.mkdir(parents=True, exist_ok=True)
            rows = []
            for r in range(h):
                words = struct.unpack_from(f"<{w}H", rect, r * w * 2)
                rows.append(
                    b"".join(
                        bytes((lut[v & 31], lut[(v >> 5) & 31], lut[(v >> 10) & 31])) for v in words
                    )
                )
            (a.png / f"vram-{p.stem}-{x}-{y}-{w}x{h}.png").write_bytes(png(w, h, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
