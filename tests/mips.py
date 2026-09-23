"""A small R3000A interpreter, for running the game's own text walkers under test.

Enough of MIPS I to execute the executable's and overlays' drawing loops and the hook
bodies `asm/` adds to them, with the two R3000 rules that hand-written patches get wrong:
**the branch delay slot** (the instruction after a jump or branch always runs) and **the
load delay slot** (the instruction after a load still sees the register's old value). A
hook that reads a register its caller loaded in the jal's delay slot, one instruction too
early, is a real defect on the console and on Beetle; this reproduces it rather than
papering over it.

`glyph_draw` is not run: `Machine.call` stops at it, records `(a0, a1, a2)` -- the glyph id
and the pen -- and returns to the caller the way a real call would, with every register
the calling convention lets it clobber overwritten by garbage. So a walker that relied on a
temporary surviving the draw fails here too.

Not modelled: coprocessors, exceptions, overflow traps (`add`/`addi` behave as `addu`), the
cache, timing. An instruction outside the subset is an error, never a silent no-op, and so
is writing a register in the delay slot of a load to it: which value survives is not
documented, so a patch that does it is refused rather than given either answer.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from boku.arrays import GLYPH_DRAW

RAM_BASE = 0x80000000
RAM_SIZE = 0x200000
STOP = 0x80000000
"""The return address `call` plants: reaching it ends the call."""


CLOBBERED = (1, 2, 3, 4, 5, 6, 7, *range(8, 16), 24, 25)
"""at, v0, v1, a0-a3, t0-t9: what a called function may leave changed."""

POISON = 0xDEADBEEF


class MipsError(Exception):
    pass


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


@dataclass
class Machine:
    """Main RAM and 32 registers; images are copied in at their load addresses."""

    ram: bytearray = field(default_factory=lambda: bytearray(RAM_SIZE))
    regs: list[int] = field(default_factory=lambda: [0] * 32)
    draws: list[tuple[int, int, int]] = field(default_factory=list)
    stubs: dict[int, list[tuple[int, ...]]] = field(default_factory=dict)
    """Functions not run but recorded like `glyph_draw`: address -> the calls made to it,
    each `(a0, a1, a2, a3, [sp+16], [sp+20])` -- the o32 fifth and sixth arguments."""
    hi: int = 0
    lo: int = 0
    _written: int | None = None
    _pending: tuple[int, int] | None = None

    def load(self, address: int, blob: bytes) -> None:
        start = address - RAM_BASE
        self.ram[start : start + len(blob)] = blob

    def _offset(self, address: int, size: int) -> int:
        offset = (address & 0x1FFFFFFF) - (RAM_BASE & 0x1FFFFFFF)
        if not 0 <= offset <= RAM_SIZE - size:
            raise MipsError(f"access to 0x{address:08X} is outside main RAM")
        if offset % size:
            raise MipsError(f"unaligned {size}-byte access at 0x{address:08X}")
        return offset

    def read(self, address: int, size: int) -> int:
        offset = self._offset(address, size)
        return int.from_bytes(self.ram[offset : offset + size], "little")

    def write(self, address: int, size: int, value: int) -> None:
        offset = self._offset(address, size)
        self.ram[offset : offset + size] = (value & ((1 << (8 * size)) - 1)).to_bytes(
            size, "little"
        )

    def halfwords(self, address: int, words: list[int]) -> int:
        """Store `words` as u16s at `address`; returns the address, for chaining."""
        self.load(address, struct.pack(f"<{len(words)}H", *words))
        return address

    def call(
        self,
        function: int,
        *arguments: int,
        registers: dict[int, int] | None = None,
        limit: int = 200_000,
    ) -> int:
        """Run `function` until it returns; `a0..a3` from `arguments`, `sp` near the top of
        RAM, any other register from `registers`. Returns `v0`."""
        for number, value in enumerate(arguments):
            self.regs[4 + number] = value & 0xFFFFFFFF
        for number, value in (registers or {}).items():
            self.regs[number] = value & 0xFFFFFFFF
        self.regs[29] = 0x801FFF00
        self.regs[31] = STOP
        pc, next_pc = function, function + 4
        pending: tuple[int, int] | None = None
        for _ in range(limit):
            if (pc in (STOP, GLYPH_DRAW) or pc in self.stubs) and pending is not None:
                self.regs[pending[0]], pending = pending[1], None
            if pc == STOP:
                return self.regs[2]
            if pc in self.stubs:
                sp = self.regs[29]
                self.stubs[pc].append(
                    (*self.regs[4:8], self.read(sp + 16, 4), self.read(sp + 20, 4))
                )
                for number in CLOBBERED:
                    self.regs[number] = POISON
                pc, next_pc = self.regs[31], self.regs[31] + 4
                continue
            if pc == GLYPH_DRAW:
                self.draws.append((_s32(self.regs[4]), _s32(self.regs[5]), _s32(self.regs[6])))
                for number in CLOBBERED:
                    self.regs[number] = POISON
                pc, next_pc = self.regs[31], self.regs[31] + 4
                continue
            word = self.read(pc, 4)
            self._written = None
            self._pending = pending
            target, load = self._step(word, pc, next_pc)
            merges = word >> 26 in (0x22, 0x26)  # lwl/lwr combine with the load before them
            if pending is not None and not (merges and load and load[0] == pending[0]):
                if self._written == pending[0] or (load and load[0] == pending[0]):
                    raise MipsError(
                        f"0x{pc:08X} writes ${pending[0]} in the load delay slot of a load to "
                        f"it; which value wins is not documented (psx-spx), so it is refused"
                    )
                self.regs[pending[0]] = pending[1]
            pending = load
            self.regs[0] = 0
            pc, next_pc = next_pc, target
        raise MipsError(f"0x{function:08X} did not return in {limit} instructions")

    def _step(self, w: int, pc: int, next_pc: int) -> tuple[int, tuple[int, int] | None]:
        """Execute one instruction; returns (the pc after the next one, a pending load)."""
        r = self.regs
        op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        rd, sa, funct = (w >> 11) & 31, (w >> 6) & 31, w & 63
        imm, simm = w & 0xFFFF, _s16(w & 0xFFFF)
        after = next_pc + 4
        branch = (next_pc + (simm << 2)) & 0xFFFFFFFF

        def set_(number: int, value: int) -> None:
            self._written = number
            if number:
                r[number] = value & 0xFFFFFFFF

        if op == 0:
            if funct == 0x00:
                set_(rd, r[rt] << sa)
            elif funct == 0x02:
                set_(rd, r[rt] >> sa)
            elif funct == 0x03:
                set_(rd, _s32(r[rt]) >> sa)
            elif funct == 0x04:
                set_(rd, r[rt] << (r[rs] & 31))
            elif funct == 0x06:
                set_(rd, r[rt] >> (r[rs] & 31))
            elif funct == 0x07:
                set_(rd, _s32(r[rt]) >> (r[rs] & 31))
            elif funct == 0x08:
                return r[rs], None
            elif funct == 0x09:
                target = r[rs]
                set_(rd, after)
                return target, None
            elif funct == 0x10:
                set_(rd, self.hi)
            elif funct == 0x12:
                set_(rd, self.lo)
            elif funct in (0x18, 0x19):
                a, b = (_s32(r[rs]), _s32(r[rt])) if funct == 0x18 else (r[rs], r[rt])
                product = (a * b) & 0xFFFFFFFFFFFFFFFF
                self.hi, self.lo = product >> 32, product & 0xFFFFFFFF
            elif funct in (0x1A, 0x1B):
                a, b = (_s32(r[rs]), _s32(r[rt])) if funct == 0x1A else (r[rs], r[rt])
                if b == 0:
                    raise MipsError(f"0x{pc:08X} divides by zero; the result is not modelled")
                quotient = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
                self.lo, self.hi = quotient & 0xFFFFFFFF, (a - quotient * b) & 0xFFFFFFFF
            elif funct in (0x20, 0x21):
                set_(rd, r[rs] + r[rt])
            elif funct in (0x22, 0x23):
                set_(rd, r[rs] - r[rt])
            elif funct == 0x24:
                set_(rd, r[rs] & r[rt])
            elif funct == 0x25:
                set_(rd, r[rs] | r[rt])
            elif funct == 0x26:
                set_(rd, r[rs] ^ r[rt])
            elif funct == 0x27:
                set_(rd, ~(r[rs] | r[rt]))
            elif funct == 0x2A:
                set_(rd, int(_s32(r[rs]) < _s32(r[rt])))
            elif funct == 0x2B:
                set_(rd, int(r[rs] < r[rt]))
            else:
                raise MipsError(f"0x{pc:08X}: SPECIAL funct 0x{funct:02X} is not modelled")
        elif op == 1:
            taken = _s32(r[rs]) < 0 if rt in (0x00, 0x10) else _s32(r[rs]) >= 0
            if rt in (0x10, 0x11):
                set_(31, after)
            elif rt not in (0x00, 0x01):
                raise MipsError(f"0x{pc:08X}: REGIMM 0x{rt:02X} is not modelled")
            return (branch if taken else after), None
        elif op in (2, 3):
            if op == 3:
                set_(31, after)
            return (next_pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2), None
        elif op in (4, 5, 6, 7):
            a = _s32(r[rs])
            taken = {
                4: r[rs] == r[rt],
                5: r[rs] != r[rt],
                6: a <= 0,
                7: a > 0,
            }[op]
            return (branch if taken else after), None
        elif op in (8, 9):
            set_(rt, r[rs] + simm)
        elif op == 0x0A:
            set_(rt, int(_s32(r[rs]) < simm))
        elif op == 0x0B:
            set_(rt, int(r[rs] < (simm & 0xFFFFFFFF)))
        elif op == 0x0C:
            set_(rt, r[rs] & imm)
        elif op == 0x0D:
            set_(rt, r[rs] | imm)
        elif op == 0x0E:
            set_(rt, r[rs] ^ imm)
        elif op == 0x0F:
            set_(rt, imm << 16)
        elif op in (0x20, 0x21, 0x23, 0x24, 0x25):
            address = (r[rs] + simm) & 0xFFFFFFFF
            size = {0x20: 1, 0x21: 2, 0x23: 4, 0x24: 1, 0x25: 2}[op]
            value = self.read(address, size)
            if op == 0x20 and value & 0x80:
                value -= 0x100
            elif op == 0x21 and value & 0x8000:
                value -= 0x10000
            return after, ((rt, value & 0xFFFFFFFF) if rt else None)
        elif op in (0x22, 0x26):
            # lwl / lwr, little-endian: the aligned word's bytes merged into rt. A pending
            # load of rt is forwarded, which is what lets the pair run back to back.
            address = (r[rs] + simm) & 0xFFFFFFFF
            word = self.read(address & ~3, 4)
            shift = 8 * (address & 3)
            old = self._pending[1] if self._pending and self._pending[0] == rt else r[rt]
            if op == 0x22:
                value = (old & (0x00FFFFFF >> shift)) | (word << (24 - shift))
            else:
                value = (old & ~(0xFFFFFFFF >> shift)) | (word >> shift)
            return after, ((rt, value & 0xFFFFFFFF) if rt else None)
        elif op in (0x2A, 0x2E):
            # swl / swr, little-endian.
            address = (r[rs] + simm) & 0xFFFFFFFF
            aligned, shift = address & ~3, 8 * (address & 3)
            word = self.read(aligned, 4)
            if op == 0x2A:
                word = (word & ~(0xFFFFFFFF >> (24 - shift))) | (r[rt] >> (24 - shift))
            else:
                word = (word & ~((0xFFFFFFFF << shift) & 0xFFFFFFFF)) | (r[rt] << shift)
            self.write(aligned, 4, word)
        elif op in (0x28, 0x29, 0x2B):
            address = (r[rs] + simm) & 0xFFFFFFFF
            self.write(address, {0x28: 1, 0x29: 2, 0x2B: 4}[op], r[rt])
        else:
            raise MipsError(f"0x{pc:08X}: opcode 0x{op:02X} is not modelled")
        return after, None
