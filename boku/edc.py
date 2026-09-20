"""EDC and ECC for Mode 2 sectors: the arithmetic a write to the image has to redo.

A sector's error detection and correction fields are a function of its own bytes, so
changing one user-data byte invalidates 4 bytes of EDC and, in Form 1, 276 bytes of ECC.
Emulators ignore both; a real drive does not, which is why a patch that skips this works
everywhere except on hardware (`research/ps1-translation-practice.md` §1.3).

The rules, from psx-spx via that note::

    Mode 2 Form 1                      Mode 2 Form 2
    000h 0Ch  sync                     000h 0Ch  sync
    00Ch 4    header (M, S, F, mode)   00Ch 4    header
    010h 4    subheader                010h 4    subheader
    014h 4    copy of the subheader    014h 4    copy of the subheader
    018h 800h user data (2048)         018h 914h user data (2324)
    818h 4    EDC over 010h..817h      92Ch 4    EDC over 010h..92Bh, or zero
    81Ch 114h ECC P then Q

* **EDC** is a reflected CRC-32 with polynomial `0xD8018001`, initial value zero and no
  final inversion, stored little-endian. It covers the subheader and the user data -- not
  the sync pattern and not the header.
* **ECC** is two Reed-Solomon parity passes over GF(2**8) with the field polynomial
  `0x11D`, and it is computed **with the 4-byte header zeroed**. That is the Form 1 quirk
  that breaks hand-written implementations: the header bytes participate as zeroes, then
  the real header is restored. The Q pass covers the P parity as well as the data, so P
  must exist before Q is computed.
* A Form 2 sector's EDC is optional. Where a disc stores zero there, zero is what it
  means, and rewriting such a sector must leave it zero rather than "fix" it.

The algorithm is Reed-Solomon as the Yellow Book defines it; the reference C is
`mkpsxiso/src/mkpsxiso/edcecc.cpp`, itself from Neill Corlett's ecmtools (GPL, so read,
never pasted -- this project is MIT). The structure below is not that C: the per-byte
loops are rewritten as whole-vector operations (`bytes.translate` for the GF multiply,
big-integer XOR for the accumulation) because a byte-at-a-time Python port is two orders
of magnitude too slow to sweep a 280,000-sector image.
"""

from __future__ import annotations

from dataclasses import dataclass

EDC_POLYNOMIAL = 0xD8018001
"""Reflected CRC-32 polynomial. Normal form is 0x8001801B."""

ECC_FIELD_POLYNOMIAL = 0x11D
"""x**8 + x**4 + x**3 + x**2 + 1 -- the GF(2**8) modulus the ECC passes work in."""

HEADER_OFFSET = 0x0C
HEADER_SIZE = 4
MODE_OFFSET = HEADER_OFFSET + 3
"""The header's fourth byte: the sector's mode. `boku.disc` documents the whole layout."""
SECTOR_MODE = 2
"""The only mode this module's offsets describe, and this disc's only mode."""
EDC_COVERAGE_START = 0x10
"""EDC covers from the subheader; the sync pattern and the header are outside it."""

FORM1_EDC_OFFSET = 0x818
FORM2_EDC_OFFSET = 0x92C
EDC_SIZE = 4

ECC_OFFSET = 0x81C
ECC_SIZE = 276
ECC_P_SIZE = 172
ECC_Q_SIZE = 104

_P_MAJOR, _P_MINOR, _P_MAJOR_MULT, _P_MINOR_INC = 86, 24, 2, 86
_Q_MAJOR, _Q_MINOR, _Q_MAJOR_MULT, _Q_MINOR_INC = 52, 43, 86, 88
_P_SPAN = _P_MAJOR * _P_MINOR  # 2064: zeroed header, subheader twice, user data, EDC
_Q_SPAN = _Q_MAJOR * _Q_MINOR  # 2236: all of that plus the 172 bytes of P parity

# Sector geometry, defined here because this is the module every other one imports, and
# imported from `boku.disc` rather than restated there -- whose docstring is the prose
# home for what the layout means (`DOC-3`: one fact, one home).
RAW_SECTOR_SIZE = 2352
FORM1_DATA_SIZE = 2048
FORM2_DATA_SIZE = 2324
USER_DATA_OFFSET = 0x18


# --- EDC: a reflected CRC-32, eight bytes per step ------------------------------------


def _edc_tables() -> list[list[int]]:
    """`slice-by-8` tables: `t[k][i]` is the residue of byte `i` shifted `k` bytes on."""
    first = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ (EDC_POLYNOMIAL if crc & 1 else 0)
        first.append(crc)
    tables = [first]
    for _ in range(7):
        previous = tables[-1]
        tables.append([(value >> 8) ^ first[value & 0xFF] for value in previous])
    return tables


_T0, _T1, _T2, _T3, _T4, _T5, _T6, _T7 = _edc_tables()


def edc(data: bytes) -> int:
    """The CD-ROM EDC of `data`: CRC-32/`0xD8018001`, initial 0, no final inversion."""
    crc = 0
    whole = len(data) & ~7
    for i in range(0, whole, 8):
        low = crc ^ int.from_bytes(data[i : i + 4], "little")
        high = int.from_bytes(data[i + 4 : i + 8], "little")
        crc = (
            _T7[low & 0xFF]
            ^ _T6[(low >> 8) & 0xFF]
            ^ _T5[(low >> 16) & 0xFF]
            ^ _T4[low >> 24]
            ^ _T3[high & 0xFF]
            ^ _T2[(high >> 8) & 0xFF]
            ^ _T1[(high >> 16) & 0xFF]
            ^ _T0[high >> 24]
        )
    for byte in data[whole:]:
        crc = (crc >> 8) ^ _T0[(crc ^ byte) & 0xFF]
    return crc


# --- ECC: two Reed-Solomon parity passes over GF(2**8) --------------------------------


def _gf_tables() -> tuple[list[bytes], bytes]:
    """`multiply[e]` is a translate table for "times x**e"; `unfold` inverts `y -> y ^ x*y`.

    `unfold` is ecmtools' `ecc_b_lut`: the map ``i -> i ^ (x * i)`` is a bijection because
    ``1 + x`` is not zero in this field, and the parity step needs its inverse.
    """
    times_x = bytearray(256)
    unfold = bytearray(256)
    for i in range(256):
        shifted = (i << 1) ^ (ECC_FIELD_POLYNOMIAL if i & 0x80 else 0)
        times_x[i] = shifted & 0xFF
        unfold[i ^ (shifted & 0xFF)] = i
    highest = max(_P_MINOR, _Q_MINOR)
    multiply = [bytes(range(256))]
    for _ in range(highest):
        multiply.append(bytes(times_x[value] for value in multiply[-1]))
    return multiply, bytes(unfold)


_MULTIPLY, _UNFOLD = _gf_tables()
_TIMES_X = _MULTIPLY[1]


def _parity(gathers: list[bytes], width: int) -> tuple[bytes, bytes]:
    """One ECC pass over `gathers` (`minor_count` vectors of `width` bytes each).

    ecmtools accumulates ``a = f(a ^ t); b ^= t`` byte by byte, where ``f`` is the GF
    multiply by x. Unrolled, ``a`` is ``sum(x**(n-k) * t[k])`` -- so each vector can be
    multiplied by its own constant and exclusive-ored in one operation, which is what
    makes this fast enough to sweep a disc. The result is ecmtools' two halves:
    ``dest[major]`` and ``dest[major + major_count]``.
    """
    minor = len(gathers)
    accumulator = 0
    total = 0
    for k, gather in enumerate(gathers):
        accumulator ^= int.from_bytes(gather.translate(_MULTIPLY[minor - k]), "big")
        total ^= int.from_bytes(gather, "big")
    folded = accumulator.to_bytes(width, "big").translate(_TIMES_X)
    first = (int.from_bytes(folded, "big") ^ total).to_bytes(width, "big").translate(_UNFOLD)
    second = (int.from_bytes(first, "big") ^ total).to_bytes(width, "big")
    return first, second


def _ecc_p(span: bytes) -> bytes:
    """The 172 P bytes over the 2064-byte span starting at the (zeroed) header.

    Major `m` walks `span[m], span[m + 86], ...` 24 times, which never wraps, so each
    step is one contiguous 86-byte row.
    """
    rows = [span[i : i + _P_MAJOR] for i in range(0, _P_SPAN, _P_MAJOR)]
    first, second = _parity(rows, _P_MAJOR)
    return first + second


def _ecc_q(span: bytes) -> bytes:
    """The 104 Q bytes over the 2236-byte span: the P span plus P's own parity.

    Major `m` starts at ``(m >> 1) * 86 + (m & 1)`` and steps by 88 modulo 2236, which
    does wrap. Because 2236 is exactly 86 * 26, index ``86 * j + c`` reduces to
    ``86 * ((j + c // 86) % 26) + c % 86`` -- so every gather is one of the 86 strided
    columns of the span, rotated. Even and odd majors are accumulated as separate
    26-wide vectors and interleaved at the end.
    """
    columns = [span[c::_P_MAJOR] for c in range(_P_MAJOR)]
    half = _Q_MAJOR // 2
    evens: list[bytes] = []
    odds: list[bytes] = []
    for k in range(_Q_MINOR):
        start = (_Q_MINOR_INC * k) % _Q_SPAN
        for offset, out in ((start, evens), ((start + 1) % _Q_SPAN, odds)):
            column = columns[offset % _P_MAJOR]
            rotation = offset // _P_MAJOR
            out.append(column[rotation:] + column[:rotation])
    even_first, even_second = _parity(evens, half)
    odd_first, odd_second = _parity(odds, half)
    out = bytearray(ECC_Q_SIZE)
    out[0:_Q_MAJOR:2] = even_first
    out[1:_Q_MAJOR:2] = odd_first
    out[_Q_MAJOR::2] = even_second
    out[_Q_MAJOR + 1 :: 2] = odd_second
    return bytes(out)


def ecc(raw: bytes) -> bytes:
    """The 276 ECC bytes a Form 1 sector should carry, given its first 0x81C bytes.

    Only `raw[0x10:0x81C]` is read: the header is zeroed per the Form 1 rule and the sync
    pattern is outside the computation entirely, so a caller need not have either right.
    """
    span = bytes(HEADER_SIZE) + raw[EDC_COVERAGE_START:ECC_OFFSET]
    if len(span) != _P_SPAN:
        raise ValueError(f"ECC needs {ECC_OFFSET} bytes of sector, got {len(raw)}")
    parity_p = _ecc_p(span)
    return parity_p + _ecc_q(span + parity_p)


# --- sector-level operations ----------------------------------------------------------


def _form_of(raw: bytes) -> int:
    return 2 if raw[EDC_COVERAGE_START + 2] & 0x20 else 1


def _require_mode2(raw: bytes) -> None:
    """Refuse a sector whose header does not say Mode 2.

    Every offset in this module is Mode 2's. Mode 1 keeps its user data at 0x10, its EDC
    at 0x810 and computes ECC over the *real* header rather than a zeroed one, so
    rebuilding a Mode 1 sector here would leave the live EDC stale, write four bytes into
    the reserved gap at 0x814, and produce ECC that is valid for neither mode -- all
    without an error. This disc is Mode 2 throughout (`boku.disc`), so a sector that says
    otherwise is a mis-sized image or a bad offset, and both should be loud.
    """
    mode = raw[MODE_OFFSET]
    if mode != SECTOR_MODE:
        raise ValueError(
            f"sector header says mode {mode}, and every EDC/ECC offset here is Mode "
            f"{SECTOR_MODE}'s; refusing rather than writing a field where that mode does "
            f"not keep one"
        )


def form1_edc(raw: bytes) -> int:
    return edc(raw[EDC_COVERAGE_START:FORM1_EDC_OFFSET])


def form2_edc(raw: bytes) -> int:
    return edc(raw[EDC_COVERAGE_START:FORM2_EDC_OFFSET])


def rebuild(raw: bytes) -> bytes:
    """`raw` with its EDC and (Form 1 only) ECC regenerated from its own bytes.

    The sync pattern, header and subheader are carried through untouched; the form is
    read from the subheader the sector already has. A Form 2 sector whose stored EDC is
    zero keeps a zero EDC -- the field is optional there, and a disc that leaves it out
    means it (see `SectorCheck.edc_omitted`).
    """
    if len(raw) != RAW_SECTOR_SIZE:
        raise ValueError(f"a raw sector is {RAW_SECTOR_SIZE} bytes, got {len(raw)}")
    _require_mode2(raw)
    out = bytearray(raw)
    if _form_of(raw) == 2:
        if raw[FORM2_EDC_OFFSET : FORM2_EDC_OFFSET + EDC_SIZE] == bytes(EDC_SIZE):
            return bytes(out)
        value = form2_edc(raw)
        out[FORM2_EDC_OFFSET : FORM2_EDC_OFFSET + EDC_SIZE] = value.to_bytes(EDC_SIZE, "little")
        return bytes(out)
    out[FORM1_EDC_OFFSET : FORM1_EDC_OFFSET + EDC_SIZE] = form1_edc(raw).to_bytes(
        EDC_SIZE, "little"
    )
    out[ECC_OFFSET : ECC_OFFSET + ECC_SIZE] = ecc(bytes(out))
    return bytes(out)


def set_form1_data(raw: bytes, data: bytes) -> bytes:
    """`raw` carrying `data` as its 2048 user bytes, with EDC and ECC regenerated."""
    if len(data) != FORM1_DATA_SIZE:
        raise ValueError(f"Form 1 user data is {FORM1_DATA_SIZE} bytes, got {len(data)}")
    if _form_of(raw) != 1:
        raise ValueError("sector's subheader says Form 2; its user data is 2324 bytes")
    out = bytearray(raw)
    out[USER_DATA_OFFSET : USER_DATA_OFFSET + FORM1_DATA_SIZE] = data
    return rebuild(bytes(out))


@dataclass(frozen=True)
class SectorCheck:
    """What a stored sector's EDC/ECC say versus what its own bytes imply."""

    lba: int
    form: int
    edc_stored: bytes
    edc_computed: bytes
    ecc_ok: bool | None
    """None for Form 2, which carries no ECC."""

    @property
    def edc_omitted(self) -> bool:
        """A Form 2 sector that stores zero: the field is optional there."""
        return self.form == 2 and self.edc_stored == bytes(EDC_SIZE)

    @property
    def ok(self) -> bool:
        if self.edc_omitted:
            return True
        return self.edc_stored == self.edc_computed and self.ecc_ok is not False


def check_sector(raw: bytes, lba: int = -1) -> SectorCheck:
    """Recompute a sector's EDC (and ECC) and report them beside what it stores."""
    if len(raw) != RAW_SECTOR_SIZE:
        raise ValueError(f"a raw sector is {RAW_SECTOR_SIZE} bytes, got {len(raw)}")
    _require_mode2(raw)
    form = _form_of(raw)
    if form == 2:
        stored = raw[FORM2_EDC_OFFSET : FORM2_EDC_OFFSET + EDC_SIZE]
        return SectorCheck(lba, 2, stored, form2_edc(raw).to_bytes(EDC_SIZE, "little"), None)
    stored = raw[FORM1_EDC_OFFSET : FORM1_EDC_OFFSET + EDC_SIZE]
    computed = form1_edc(raw).to_bytes(EDC_SIZE, "little")
    return SectorCheck(
        lba, 1, stored, computed, ecc(raw) == raw[ECC_OFFSET : ECC_OFFSET + ECC_SIZE]
    )
