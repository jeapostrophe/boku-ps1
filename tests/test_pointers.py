"""`boku.pointers`: the `lui` pairs that build an array's address, found and rewritten.

The fixtures are hand-assembled MIPS words; each helper encodes one instruction from its
fields, so a test states the code it runs rather than a hex dump of it.
"""

from __future__ import annotations

import pytest

from boku.pointers import PointerError, repoint, resolve, scan

BASE = 0x80040000
ARRAY = 0x80046214
S2, V0, V1, A0, A1, RA = 18, 2, 3, 4, 5, 31


def lui(rt: int, imm: int) -> int:
    return (0x0F << 26) | (rt << 16) | imm


def addiu(rt: int, rs: int, imm: int) -> int:
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def lhu(rt: int, base: int, imm: int) -> int:
    return (0x25 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)


def addu(rd: int, rs: int, rt: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21


def j(target: int) -> int:
    return (0x02 << 26) | ((target >> 2) & 0x03FFFFFF)


def jal(target: int) -> int:
    return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)


def bne(rs: int, rt: int, offset: int) -> int:
    return (0x05 << 26) | (rs << 21) | (rt << 16) | (offset & 0xFFFF)


JR_RA = (RA << 21) | 0x08
NOP = 0


def hi(address: int) -> int:
    return ((address + 0x8000) >> 16) & 0xFFFF


def lo(address: int) -> int:
    return address & 0xFFFF


def code(*words: int) -> bytes:
    return b"".join(word.to_bytes(4, "little") for word in words)


def test_a_pair_is_the_lui_and_the_low_half_that_completes_it():
    image = code(lui(A0, hi(ARRAY)), addiu(A0, A0, lo(ARRAY)), JR_RA, NOP)
    (pair,) = scan(image, BASE)
    assert (pair.ram, [use.target for use in pair.uses]) == (BASE, [ARRAY])
    assert resolve(image, BASE, BASE) == ARRAY


def test_a_saved_register_is_followed_past_a_jump_to_the_block_a_branch_reaches():
    """`item_menu_draw`'s shape: `lui s2` before a loop whose two paths each add `%lo`,
    one in a `j`'s delay slot and one at the branch target after it. Both must move."""
    image = code(
        lui(S2, hi(ARRAY)),  # 0
        bne(V1, V0, 3),  # 1 -> 5
        NOP,  # 2
        j(BASE + 4 * 6),  # 3
        addiu(A0, S2, lo(ARRAY)),  # 4, the delay slot
        addiu(A0, S2, lo(ARRAY)),  # 5, the branch target
        JR_RA,  # 6
        NOP,
    )
    (pair,) = scan(image, BASE)
    assert [use.ram for use in pair.uses] == [BASE + 16, BASE + 20]


def test_an_indexed_load_off_an_addu_of_the_high_half_is_a_use():
    image = code(lui(V1, hi(ARRAY)), addu(V1, V1, V0), lhu(A0, V1, lo(ARRAY)), JR_RA, NOP)
    (pair,) = scan(image, BASE)
    assert [use.target for use in pair.uses] == [ARRAY]


def test_a_call_ends_what_a_temporary_register_carries():
    image = code(lui(V1, hi(ARRAY)), jal(BASE + 0x100), NOP, addiu(A0, V1, lo(ARRAY)), JR_RA, NOP)
    assert scan(image, BASE) == []


def test_a_move_carries_the_low_half_across_its_sign():
    """`%hi` rounds up when `%lo` is negative as a signed 16-bit value."""
    image = code(lui(A0, hi(ARRAY)), addiu(A0, A0, lo(ARRAY)), JR_RA, NOP)
    (pair,) = scan(image, BASE)
    new = 0x8005DB9C  # low half 0xDB9C is negative: the high half must be 0x8006
    words = repoint(pair, lambda target: new, image, BASE)
    assert words == {BASE: lui(A0, 0x8006), BASE + 4: addiu(A0, A0, 0xDB9C)}
    moved = code(words[BASE], words[BASE + 4], JR_RA, NOP)
    assert resolve(moved, BASE, BASE) == new


def test_a_lui_whose_uses_would_need_two_high_halves_is_refused():
    other = 0x80046398
    image = code(
        lui(S2, hi(ARRAY)),
        addiu(A0, S2, lo(ARRAY)),
        addiu(A1, S2, lo(other)),
        JR_RA,
        NOP,
    )
    (pair,) = scan(image, BASE)
    with pytest.raises(PointerError, match="different high halves"):
        repoint(pair, lambda target: 0x80025120 if target == ARRAY else target, image, BASE)


def test_a_lui_in_a_branch_delay_slot_is_completed_on_both_sides_of_the_branch():
    """`item_menu_draw`'s descriptions: `bne; lui a0` and an `addiu a0, a0, %lo` on the
    fall-through path that the taken path never runs, and another at the branch target."""
    image = code(
        bne(V1, V0, 4),  # 0 -> 5
        lui(A0, hi(ARRAY)),  # 1, the delay slot
        addiu(A0, A0, lo(ARRAY)),  # 2, fall-through: overwrites a0 on this path only
        JR_RA,  # 3
        NOP,  # 4
        addiu(A0, A0, lo(ARRAY)),  # 5, the branch target
        JR_RA,
        NOP,
    )
    (pair,) = scan(image, BASE)
    assert [use.ram for use in pair.uses] == [BASE + 8, BASE + 20]
