"""The event VM, against blocks this test assembled itself.

The decoder's whole value is that it advances by the **opcode size table** and refuses
every disagreement with the size byte. `research/event-scripts.md`'s `--selftest` proved
that by mis-sizing one opcode at a time and watching hundreds of events fail; the same
idea works on one synthesized block, and needs no disc.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from boku.archive import MAP_DIR_INDEX
from boku.events import (
    CHARACTERS,
    OPS,
    Block,
    EventError,
    decode_code,
    fmt_cond,
    load_events,
    parse_block_table,
    parse_cond,
    trigger_kind,
    uses_day,
)
from tests import synth_archive as synth

WAT = 0x1B
ANM = 0x12
JMP = 0x03
JMPE = 0x05
XAMSG = 0x0D
SELECT = 0x21
END = 0x15


def straight_code() -> bytes:
    return (
        synth.instruction(WAT, 2, b"\x0a\x00")
        + synth.instruction(ANM, 3, b"\x01\x00\x02\x00")
        + synth.instruction(XAMSG, 4, b"\x01\x71\x00\x00\x00")
        + synth.instruction(END, 1)
    )


# --- the bytecode walker -----------------------------------------------------------------


def test_a_straight_run_decodes_to_one_instruction_per_size_byte():
    decoded = decode_code(straight_code())
    assert [i.name for i in decoded.values()] == ["WAT", "ANM", "XAMSG", "END"]
    assert sorted(decoded) == [0, 4, 10, 18]


def test_an_opcode_whose_size_byte_disagrees_with_the_table_is_refused():
    """The desync gate: this is what `--selftest` broke on purpose, 599 events at a time."""
    wrong = dict(OPS)
    wrong[ANM] = ("ANM", 2)
    with pytest.raises(EventError, match="size byte 3, table 2"):
        decode_code(straight_code(), wrong)


def test_an_opcode_the_table_does_not_size_is_refused_rather_than_skipped():
    without_wat = {op: v for op, v in OPS.items() if op != WAT}
    with pytest.raises(EventError, match="not in table"):
        decode_code(straight_code(), without_wat)


def test_code_that_never_reaches_end_is_refused():
    with pytest.raises(EventError, match="without END"):
        decode_code(synth.instruction(WAT, 2, b"\x0a\x00"))


def test_data_after_end_is_refused_beyond_the_4_byte_pad():
    assert len(decode_code(synth.instruction(END, 1) + bytes(2))) == 1
    with pytest.raises(EventError, match="bytes after END"):
        decode_code(synth.instruction(END, 1) + bytes(4))


def test_a_jump_that_misses_an_instruction_boundary_is_refused():
    """A jump into the middle of an instruction means the size table is wrong somewhere."""
    good = synth.instruction(JMP, 2, b"\x02\x00") + synth.instruction(END, 1) + bytes(2)
    assert decode_code(good)[0].name == "JMP"
    bad = synth.instruction(JMP, 2, b"\x01\x00") + synth.instruction(END, 1) + bytes(2)
    with pytest.raises(EventError, match="not an instruction boundary"):
        decode_code(bad)


# --- the block -----------------------------------------------------------------------------


def test_a_block_hands_back_each_entry_bounded_by_the_next_live_offset():
    text = synth.words(0x100, 0x101, synth.END)
    data = synth.block(
        [synth.cast([(0, 3)]), synth.condition(), straight_code(), synth.voice_key(), text]
    )
    block = Block(data)
    assert block.n == 5
    assert block.message_count == 1
    assert not block.is_stub
    assert block.entry(2) == straight_code()
    assert block.entry(3) == synth.voice_key()
    assert block.entry(4)[: len(text)] == text


def test_a_two_entry_block_is_a_stub_and_carries_no_message():
    block = Block(synth.block([synth.cast([]), synth.condition()]))
    assert block.is_stub
    assert block.message_count == 0
    assert block.entry(2) is None, "a stub has no bytecode entry to read"


def test_a_null_entry_reads_as_absent_rather_than_as_an_empty_slice():
    block = Block(synth.block([synth.cast([]), synth.condition(), straight_code(), None, None]))
    assert block.entry(3) is None
    assert block.entry_span(3) is None


# --- writing a block back out (what `PIPE-03` stands on) ---------------------------------------


def a_block() -> bytes:
    return synth.block(
        [
            synth.cast([(0, 3)]),
            synth.condition(),
            straight_code(),
            synth.voice_key(),
            synth.words(0x100, 0x101, synth.END),
            None,
            synth.words(0x102, synth.END),
        ]
    )


def test_a_block_is_laid_out_again_from_its_entries_with_the_offsets_recomputed():
    data = a_block()
    assert Block(data).serialise() == data


def test_replacing_a_message_with_its_own_bytes_changes_nothing():
    block = Block(a_block())
    assert block.replace_entry(4, block.entries[4]).serialise() == block.serialise()


def test_a_longer_message_moves_every_later_offset_and_nothing_else():
    """The one thing a reinserter does, and the reason offsets are recomputed rather
    than replayed: a message that grows by four bytes moves entries 5 and 6, and only
    those, by four bytes."""
    block = Block(a_block())
    grown = block.replace_entry(4, block.entries[4] + synth.words(0x103, 0x104))
    assert grown.offsets[:5] == block.offsets[:5]
    assert grown.offsets[5] == 0, "a null entry stays null"
    assert grown.offsets[6] == block.offsets[6] + 4
    assert [grown.entry(i) for i in (0, 1, 2, 3, 6)] == [block.entry(i) for i in (0, 1, 2, 3, 6)]
    assert len(grown.serialise()) == len(block.serialise()) + 4


def test_an_entry_that_is_not_there_cannot_be_replaced():
    block = Block(a_block())
    with pytest.raises(EventError, match="null"):
        block.replace_entry(5, b"\x00\x00")


def test_a_map_packs_block_table_chains_its_blocks_and_writes_them_back():
    blocks = [(171, a_block()), (4032, a_block())]
    raw = synth.child1(blocks)
    table = parse_block_table(raw, "a map")
    assert [ident for ident, _data in table.blocks] == [171, 4032]
    assert table.offset_of(1) == table.offset_of(0) + len(blocks[0][1])
    assert table.serialise() == raw


def test_a_block_table_whose_offsets_do_not_chain_is_refused():
    raw = bytearray(synth.child1([(171, a_block()), (4032, a_block())]))
    raw[16:20] = (0x400).to_bytes(4, "little")  # the second record's offset field
    with pytest.raises(EventError, match="!= chain"):
        parse_block_table(bytes(raw), "a map")


def test_a_longer_block_moves_the_offsets_of_the_blocks_after_it():
    table = parse_block_table(synth.child1([(171, a_block()), (4032, a_block())]), "a map")
    grown = table.replace(0, table.blocks[0][1] + bytes(8))
    assert grown.offset_of(0) == table.offset_of(0)
    assert grown.offset_of(1) == table.offset_of(1) + 8
    assert len(grown.serialise()) == len(table.serialise()) + 8


# --- condition trees --------------------------------------------------------------------------


def test_a_flat_condition_node_parses_to_its_operator_and_value():
    tree, end = parse_cond(synth.cond_node(10, 0, 5, 0, 19), 0)  # hour >= 19
    assert tree == ("hour", "hour", ">=", 19)
    assert end == 8
    assert fmt_cond(tree) == "hour>=19"
    assert uses_day(tree) is False


def test_a_group_holds_its_children_inline_after_it():
    raw = (
        synth.cond_node(0, 0, 0, 2)  # AND of two
        + synth.cond_node(10, 0, 5, 0, 19)  # hour >= 19
        + synth.cond_node(11, 0, 3, 0, 5)  # day != 5
    )
    tree, end = parse_cond(raw, 0)
    assert end == 24
    assert fmt_cond(tree) == "(hour>=19 & day!=5)"
    assert uses_day(tree) is True


def test_a_flag_node_says_whether_it_is_global_or_the_events_own_local_flag():
    assert fmt_cond(parse_cond(synth.cond_node(9, 72, 5, 1, 1), 0)[0]) == "flag[72]>=1"
    assert fmt_cond(parse_cond(synth.cond_node(9, 0, 2, 0, 0), 0)[0]) == "lflag==0"


def test_an_unknown_node_kind_is_refused_rather_than_guessed():
    with pytest.raises(EventError, match="unknown condition node kind"):
        parse_cond(synth.cond_node(12, 0, 2, 0, 0), 0)


# --- placement triggers --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flags", "kind"),
    [(0x80, "auto"), (0x60, "talk"), (0x40, "near"), (0x20, "examine"), (0x00, "zone")],
)
def test_the_trigger_flags_name_the_four_ways_an_event_starts(flags: int, kind: str):
    assert trigger_kind(flags) == kind


def test_the_character_table_covers_the_slots_the_speakers_use():
    assert CHARACTERS[0] == "BOKU"
    assert set(CHARACTERS) == set(range(11))


# --- the duplication model, asserted across copies ----------------------------------------------


class FakeArchive:
    """The surface `iter_blocks` reads: members with a `dir_index`, and their bytes."""

    def __init__(self, members: list[tuple[int, str, bytes]]) -> None:
        self.members = [_FakeMember(i, d, n) for i, (d, n, _b) in enumerate(members)]
        self._blobs = {n: b for _d, n, b in members}

    def blob(self, member) -> bytes:
        return self._blobs[member.short_name]


@dataclass
class _FakeMember:
    index: int
    dir_index: int
    short_name: str

    @property
    def name(self) -> str:
        return f"\\_DATA\\{self.short_name}"


def map_member(name: str, blocks: list[tuple[int, bytes]]) -> tuple[int, str, bytes]:
    return (MAP_DIR_INDEX, name, synth.map_pack(blocks, []))


def test_two_copies_of_one_event_that_disagree_in_entries_0_to_2_are_refused():
    other = synth.block([synth.cast([(1, 1)]), synth.condition(), straight_code()])
    archive = FakeArchive(
        [map_member("M_A.BIN", [(171, a_block())]), map_member("M_B.BIN", [(171, other)])]
    )
    with pytest.raises(EventError, match="copies differ in entries 0-2"):
        load_events(archive)


def test_two_copies_that_agree_in_entries_0_to_2_but_hold_different_message_counts_are_refused():
    """`n` is part of the signature, so this is a named refusal rather than an `IndexError`.

    The block kept below has one message where the other has two; the bytecode of both
    names message 1, so whichever copy `load_events` happened to keep decided whether
    `sc.messages[1]` existed at all.
    """
    entries = [synth.cast([(0, 3)]), synth.condition(), straight_code(), synth.voice_key()]
    one = synth.block([*entries, synth.words(0x100, synth.END)])
    two = synth.block(
        [*entries, synth.words(0x100, synth.END), synth.voice_key(), synth.words(0x101, synth.END)]
    )
    assert Block(one).message_count != Block(two).message_count
    archive = FakeArchive(
        [map_member("M_A.BIN", [(171, one)]), map_member("M_B.BIN", [(171, two)])]
    )
    with pytest.raises(EventError, match="copies differ in entries 0-2"):
        load_events(archive)
