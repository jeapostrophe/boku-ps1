"""EDC and ECC written the slow, literal way, as a second opinion for the fast module.

These are transcriptions of `research/ps1-translation-practice.md` §1.3 -- one bit or one
byte at a time, from the documented polynomials -- and they share no table, loop or
constant with `boku.edc`. `boku.edc` is the same arithmetic rearranged into whole-vector
operations so that a 280,000-sector sweep finishes; these are what say that rearranging
did not change the answer.

`slow_ecc`'s `zero_header` switch exists for one test: the Form 1 rule is that ECC is
computed with the 4-byte header zeroed, and the only way to show that the rule is real,
rather than an inherited habit, is to compute it the other way and watch the real disc
reject it (`test_real_disc_edc.py`).
"""

from __future__ import annotations

EDC_POLYNOMIAL = 0xD8018001
FIELD_POLYNOMIAL = 0x11D

HEADER_OFFSET = 0x0C
ECC_OFFSET = 0x81C
ECC_SIZE = 276
ECC_P_SIZE = 172


def slow_edc(data: bytes) -> int:
    """A reflected CRC-32, one bit at a time, straight from the polynomial."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (EDC_POLYNOMIAL if crc & 1 else 0)
    return crc


def _times_x(value: int) -> int:
    return ((value << 1) ^ (FIELD_POLYNOMIAL if value & 0x80 else 0)) & 0xFF


def slow_ecc(raw: bytes, *, zero_header: bool = True) -> bytes:
    """Both parity passes as the rules describe them: Q after P, header zeroed (or not).

    `span` is the sector from offset 0x0C on, which is what the passes address: the
    header, the subheader and its copy, the user data, the EDC, and then P's own output,
    which Q covers as well.
    """
    unfold = [0] * 256
    for i in range(256):
        unfold[i ^ _times_x(i)] = i
    header = bytes(4) if zero_header else raw[HEADER_OFFSET : HEADER_OFFSET + 4]
    span = bytearray(header) + bytearray(raw[HEADER_OFFSET + 4 : ECC_OFFSET])
    span += bytearray(ECC_P_SIZE)
    out = bytearray(ECC_SIZE)

    def pass_over(dest: int, major_count: int, minor_count: int, major_mult: int, inc: int) -> None:
        size = major_count * minor_count
        for major in range(major_count):
            index = (major >> 1) * major_mult + (major & 1)
            first = second = 0
            for _ in range(minor_count):
                byte = span[index]
                index = (index + inc) % size
                first ^= byte
                second ^= byte
                first = _times_x(first)
            first = unfold[_times_x(first) ^ second]
            out[dest + major] = first
            out[dest + major + major_count] = first ^ second

    pass_over(0, 86, 24, 2, 86)
    span[ECC_OFFSET - HEADER_OFFSET : ECC_OFFSET - HEADER_OFFSET + ECC_P_SIZE] = out[:ECC_P_SIZE]
    pass_over(ECC_P_SIZE, 52, 43, 86, 88)
    return bytes(out)


def some_data(seed: int, size: int = 2048) -> bytes:
    """A deterministic, non-repeating block. Not disc content; just varied bytes."""
    state = seed | 1
    out = bytearray(size)
    for i in range(size):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        out[i] = (state >> 16) & 0xFF
    return bytes(out)
