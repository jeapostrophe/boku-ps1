"""`VO-02` on the real dump: the voice-only slots, and a subtitle planned into one.

Skips cleanly with no `disc/` -- the repo ships none of the game.
"""

from __future__ import annotations

from boku.archive import Archive
from boku.events import OP_XA, TEXT_OPS, Block, iter_blocks
from boku.glyphs import END_WORD
from boku.reinsert import plan
from boku.sites import Walk, iter_instructions


def test_every_null_text_entry_on_the_disc_is_a_voice_only_slot_and_nothing_else_is(
    archive: Archive, walk_reader: Walk
):
    """Counted from the blocks directly, not through `voice_only_entries`: every entry pair
    with a key and a null text, in every block copy, and whether an `XA` names it."""
    expected = set()
    named_by_other = []
    for inst in iter_blocks(archive):
        block = Block(inst.data)
        if block.n < 3:
            continue
        span = block.entry_span(2)
        ops: dict[int, set[int]] = {}
        for i in iter_instructions(block.data[span[0] : span[1]]):
            if i.op in TEXT_OPS:
                ops.setdefault(i.message_index, set()).add(i.op)
        for index in range((block.n - 3) // 2):
            if block.entry_span(3 + 2 * index) and block.entry_span(4 + 2 * index) is None:
                expected.add((inst.member.short_name, inst.table, f"E{inst.event_id:04d}.{index}"))
                if ops.get(index) != {OP_XA}:
                    named_by_other.append((inst.member.short_name, index, ops.get(index)))
    found = {
        (site.member, site.table, site.line_id)
        for sites in walk_reader.voice_only.values()
        for site in sites
    }
    assert named_by_other == [], "a null text named by something other than XA"
    assert found == expected
    assert len(found) > 100, "the disc has hundreds; an empty walk would pass the equality"


def test_a_subtitle_on_the_futon_clip_is_planned_into_every_copy_of_E0184(
    archive: Archive, walk_reader: Walk
):
    """`E0184.2` is the day-1 clip the emulator proof uses (research/event-scripts.md
    § Voice-only entries)."""
    copies = walk_reader.voice_only["E0184.2"]
    the_plan = plan(archive, walk_reader, {"E0184.2": (0x30, 0x31, END_WORD)})
    assert sorted(the_plan.members_rebuilt) == sorted({site.member for site in copies})
    assert the_plan.sites_written == len(copies)
