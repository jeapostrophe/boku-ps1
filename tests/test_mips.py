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
