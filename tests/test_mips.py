"""`tests.mips`: the two delay-slot rules the walker tests depend on."""

from __future__ import annotations

import struct

import pytest

from tests.mips import Machine, MipsError

CODE, DATA = 0x80010000, 0x80100000
JR_RA, NOP = 0x03E00008, 0


def run(*words: int) -> Machine:
    m = Machine()
    m.load(CODE, struct.pack(f"<{len(words)}I", *words))
    m.halfwords(DATA, [7])
    m.call(CODE, DATA)
    return m


def test_the_instruction_after_a_load_sees_the_old_value():
    # lhu v0,0(a0); addu v1,v0,zero; addu a1,v0,zero; jr ra; nop
    m = run(0x94820000, 0x00401821, 0x00402821, JR_RA, NOP)
    assert m.regs[3] == 0, "the load-delay slot read the new value"
    assert m.regs[5] == 7


def test_the_instruction_after_a_branch_always_runs():
    # beq zero,zero,+2; addiu v0,zero,5; addiu v0,zero,9 (skipped); jr ra; nop
    m = run(0x10000002, 0x24020005, 0x24020009, JR_RA, NOP)
    assert m.regs[2] == 5


def test_writing_the_loaded_register_in_its_delay_slot_is_refused():
    # lhu v0,0(a0); addiu v0,zero,1 -- undocumented on the R3000A, so no answer is given
    with pytest.raises(MipsError, match="load delay slot"):
        run(0x94820000, 0x24020001, JR_RA, NOP)


@pytest.mark.parametrize("offset", [0, 1, 2, 3])
def test_lwl_lwr_and_swl_swr_move_a_word_at_every_alignment(offset):
    """The pair at each byte offset, the aligned one (lwl 3 / lwr 0 on a word boundary)
    being what TITLE's card drawer runs to copy its tables to the stack."""
    m = Machine()
    m.load(DATA, bytes(range(0x10, 0x30)))
    code = [0x88880003, 0x98880000, 0, 0xA8A80003, 0xB8A80000, JR_RA, NOP]
    m.load(CODE, struct.pack(f"<{len(code)}I", *code))
    m.call(CODE, DATA + offset, DATA + 16 + (3 - offset))
    want = bytes(range(0x10 + offset, 0x14 + offset))
    assert m.regs[8] == int.from_bytes(want, "little")
    start = DATA - 0x80000000 + 16 + (3 - offset)
    assert bytes(m.ram[start : start + 4]) == want


def test_an_unaligned_word_moves_through_lwl_lwr_swl_swr():
    """The compiler's unaligned copy (TITLE's card drawers copy tables to the stack this way):
    lwl 3(a0) / lwr 0(a0) back to back -- the second merges with the first's pending load --
    then swl 3(a1) / swr 0(a1)."""
    m = Machine()
    m.load(DATA, bytes(range(0x10, 0x20)))
    # a0 = DATA+1, a1 = DATA+9; lwl t0,3(a0); lwr t0,0(a0); nop; swl t0,3(a1); swr t0,0(a1)
    code = [0x88880003, 0x98880000, 0, 0xA8A80003, 0xB8A80000, JR_RA, NOP]
    m.load(CODE, struct.pack(f"<{len(code)}I", *code))
    m.call(CODE, DATA + 1, DATA + 9)
    assert m.regs[8] == int.from_bytes(bytes(range(0x11, 0x15)), "little")
    assert bytes(m.ram[DATA - 0x80000000 + 9 : DATA - 0x80000000 + 13]) == bytes(range(0x11, 0x15))


@pytest.mark.parametrize(
    ("funct", "a", "b", "quotient", "remainder"),
    [(0x1B, 31, 10, 3, 1), (0x1A, -7, 2, -3, -1), (0x1A, 7, -2, -3, 1)],
)
def test_div_and_divu_leave_the_quotient_in_lo_and_the_remainder_in_hi(
    funct, a, b, quotient, remainder
):
    """Truncation toward zero, as the R3000 does (`asm/labels.asm` splits a day in two)."""
    m = Machine()
    # div(u) a0,a1; mflo v0; mfhi v1; jr ra; nop
    m.load(
        CODE, struct.pack("<5I", (4 << 21) | (5 << 16) | funct, 0x00001012, 0x00001810, JR_RA, NOP)
    )
    m.call(CODE, a & 0xFFFFFFFF, b & 0xFFFFFFFF)
    assert (m.regs[2], m.regs[3]) == (quotient & 0xFFFFFFFF, remainder & 0xFFFFFFFF)
