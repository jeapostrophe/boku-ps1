"""`PIPE-03`'s rebuild, on archives this test lays out itself.

The bottom-up rewrite list of `research/text-format.md` is five nested containers deep —
message bytes, block offsets, the child-1 table, the pack table, the `.SEC` index — and a
mistake at any level is invisible until a map does not load in an emulator. So the
archives here are **built** by `tests/synth_archive.py` and **read back** by the package's
own parsers: a bug shared between the two would have to be written twice, in opposite
directions, and the identity case (reinsert a line with its own words) has to come back
byte for byte.

The three measured limits get a test each, at the shape that makes them bind rather than
at a comfortable distance from it; `tests/test_real_reinsert.py` runs the same refusals
against the tightest map and the largest `EV` member on the real disc.
"""

from __future__ import annotations

import re
import struct
from dataclasses import replace

import pytest

from boku import relocate
from boku.archive import (
    EV_DIR_INDEX,
    MAP_DIR_INDEX,
    SECTOR,
    SUB_ARCHIVES,
    Archive,
    dir_arrays,
    parse_pack,
)
from boku.events import Block, parse_block_table
from boku.glyphs import END_WORD, NEWLINE_WORD, PAD_WORD, words_of
from boku.reinsert import (
    EVENT_BLOCK_LIMIT,
    MAP_WORK_AREA_END,
    ByteEdit,
    ReinsertRefused,
    directory_edits,
    map_head_room,
    map_work_records,
    plan,
    sector_head_room,
)
from boku.relocate import (
    PREFIX_FILLER,
    RelocationRefused,
    Run,
    capacity,
    check_placements,
    plan_layout,
)
from boku.sites import walk as walk_all_sites
from tests import synth_archive as synth


def walk(archive: Archive):
    """The structural walk of a synthetic archive, whose executable holds no text."""
    return walk_all_sites(archive, code_files=False)


XAMSG, SELECT, END_OP = 0x0D, 0x21, 0x15
PAD = b"\xcd\xcd"
"""Two bytes of the build-tool's uninitialised memory, as 2,881 real entries carry."""


# --- laying out a whole synthetic disc ---------------------------------------------------------


def code_naming(count: int, select_at: int | None = None) -> bytes:
    """Bytecode that names message 0…`count-1`, so the walk finds each of them."""
    out = b""
    for index in range(count):
        if index == select_at:
            out += synth.instruction(SELECT, 3, bytes([3, 1, index, 0]))
        else:
            out += synth.instruction(XAMSG, 4, bytes([1, 0x71, index, 0, 0]))
    return out + synth.instruction(END_OP, 1)


def a_block(messages: list[bytes], select_at: int | None = None) -> bytes:
    """An event block carrying `messages`, each with a voice key, as the disc's blocks are."""
    entries: list[bytes | None] = [
        synth.cast([(0, 1)]),
        synth.condition(),
        code_naming(len(messages), select_at),
    ]
    for text in messages:
        entries += [synth.voice_key(), text]
    return synth.block(entries)


def map_child0(placements: int = 0, work_records: int = 0) -> bytes:
    """Child 0 as `map_child0_parse` reads it, down to the animated-object count.

    `map_work_records` walks exactly this shape, so the count it finds is the one written
    here rather than a number typed into both places.
    """
    return (
        synth.placements([(0x80, 0, 1)] * placements)
        + bytes(0x14)
        + (0).to_bytes(4, "little")
        + bytes([work_records])
        + bytes(3)
    )


def map_pack(blocks: list[tuple[int, bytes]], *, work_records: int = 0, filler: int = 0) -> bytes:
    """A seven-child map pack. `filler` pads child 5, which is what pushes child 6 out."""
    return synth.pack(
        [
            map_child0(work_records=work_records),
            synth.child1(blocks),
            b"\0\0\0\0",
            None,
            None,
            bytes(filler) if filler else b"\0\0\0\0",
            b"\0\0\0\0",  # child 6: the background TIM, whose offset `map_commit` tests
        ]
    )


def exe_with(entries: list[tuple[str, int, int]]) -> bytes:
    """A `SCPS_100.88` holding `g_cd_dir` and the three select-shape tables."""
    builder = synth.ExeBuilder()
    builder.directory(entries)
    builder.select_tables(base=bytes([1]), lines=bytes([3]), first=bytes([1]))
    return builder.build()


def synthetic_disc(
    maps: list[tuple[str, bytes]] = (),
    events: list[tuple[int, bytes]] = (),
) -> Archive:
    """An `Archive` over bytes, with `EV.BIN` and `M_FILES.BIN` at their real file numbers.

    The directory is padded with one-sector fillers so that the two sub-archives land on
    the indexes the package addresses them by (`EV_DIR_INDEX`, `MAP_DIR_INDEX`). That is
    not decoration: `boku.reinsert` decides whether a member is a bare block or a map pack
    from its file number, exactly as `boku.events.iter_blocks` does.
    """
    members: list[tuple[str, bytes]] = []

    def filler(upto: int) -> None:
        while len(members) < upto:
            members.append((f"\\_DATA\\F{len(members):03d}.BIN", bytes(16)))

    filler(EV_DIR_INDEX)
    ev_records = []
    ev_blob = b""
    for event_id, block in events:
        ev_records.append((event_id, len(block), len(ev_blob) // SECTOR))
        ev_blob += block + bytes(-len(block) % SECTOR)
    members.append(("\\_DATA\\EV.BIN", ev_blob))
    members.append(("\\_DATA\\EV.SEC", synth.sec_ev(ev_records)))
    filler(MAP_DIR_INDEX)
    map_records = []
    map_blob = b""
    for name, pack in maps:
        map_records.append((name, len(pack), len(map_blob) // SECTOR))
        map_blob += pack + bytes(-len(pack) % SECTOR)
    members.append(("\\_DATA\\M_FILES.BIN", map_blob))
    members.append(("\\_DATA\\M_FILES.SEC", synth.sec_m(map_records)))
    filler(MAP_DIR_INDEX + 2)
    blob, entries = synth.archive_of(members)
    archive = Archive.from_bytes(exe_with(entries), blob, source="synthetic")
    archive.require_clean()
    return archive


def message(*words: int) -> bytes:
    return synth.words(*words)


def a_disc_with_one_line(text=(0x100, 0x101, END_WORD), pad: bytes = PAD) -> Archive:
    block = a_block([text_bytes(text) + pad])
    return synthetic_disc(maps=[("A01000", map_pack([(171, block)]))])


def text_bytes(words) -> bytes:
    return synth.words(*words)


def words_for(archive: Archive) -> dict[str, tuple[int, ...]]:
    """Every line of an archive with its own words — the identity reinsertion."""
    result = walk(archive)
    assert result.problems == [], result.problems
    return {lid: words_of(result.raw(archive, s[0])) for lid, s in result.by_line.items()}


def rebuilt(archive: Archive, replacements, **kwargs) -> tuple[bytes, dict]:
    """Apply a plan's edits to the archive's bytes and hand back the new `BOKU.BIN`."""
    result = walk(archive)
    the_plan = plan(archive, result, replacements, **kwargs)
    blob = bytearray(archive.boku)
    for edit in the_plan.edits:
        assert edit.file == "BOKU.BIN", edit.reason
        assert blob[edit.offset : edit.end] == edit.old
        blob[edit.offset : edit.end] = edit.new
    return bytes(blob), the_plan


# --- the identity, which is the round-trip gate in miniature -----------------------------------


def test_reinserting_every_line_with_its_own_words_changes_nothing():
    archive = a_disc_with_one_line()
    result = walk(archive)
    the_plan = plan(archive, result, words_for(archive))
    assert the_plan.edits == ()
    assert the_plan.members_rebuilt, "no member was rebuilt; the gate would pass over nothing"
    assert the_plan.sites_written == len(result.sites)


def test_the_build_tool_pad_after_a_message_is_carried_back_rather_than_zeroed():
    """2,881 entries on the disc carry 2 bytes of uninitialised memory, 339 distinct values.

    Zeroing them is invisible in the game and fatal to the round-trip gate, which is the
    only thing that says the rebuild is lossless. The pad comes back when the new text
    needs a pad of the same length, and is zeroed when it does not — there is nothing to
    carry back then.
    """
    archive = a_disc_with_one_line()
    result = walk(archive)
    site = result.sites[0]
    same_length = plan(archive, result, {site.line_id: (0x200, 0x201, END_WORD)})
    blob = bytearray(archive.boku)
    for edit in same_length.edits:
        blob[edit.offset : edit.end] = edit.new
    assert PAD in bytes(blob), "the pad was zeroed by a same-length rewrite"

    two_shorter = plan(archive, result, {site.line_id: (0x200, END_WORD)})
    blob = bytearray(archive.boku)
    for edit in two_shorter.edits:
        blob[edit.offset : edit.end] = edit.new
    assert PAD not in bytes(blob), "a 4-aligned message needs no pad, so none is carried"


# --- growth, bottom up -------------------------------------------------------------------------


def test_a_longer_message_moves_the_entries_the_block_table_and_the_pack_table():
    """One line grows; four levels of offset follow it, and nothing else in the map moves."""
    keep = text_bytes((0x300, 0x301, 0x302, END_WORD))
    grow = text_bytes((0x100, 0x101, END_WORD)) + PAD
    block = a_block([grow, keep])
    archive = synthetic_disc(maps=[("A01000", map_pack([(171, block)]))])
    before = words_for(archive)
    member = archive.member("M_A01000.BIN")
    pack_before = parse_pack(archive.blob(member))

    longer = (0x100, 0x101, 0x102, 0x103, 0x104, 0x105, 0x106, END_WORD)
    blob, the_plan = rebuilt(archive, {"E0171.0": longer})
    assert the_plan.growth == {"M_A01000.BIN": 8}

    after = Archive.from_bytes(archive.exe, blob, source="rebuilt")
    # The `.SEC` size field moved with the member, so the member map still tiles exactly.
    after.require_clean()
    assert after.member("M_A01000.BIN").size == member.size + 8
    pack_after = parse_pack(after.blob(after.member("M_A01000.BIN")))
    assert [o for o, _s in pack_after.entries[2:]] == [
        o + 8 if o else 0 for o, _s in pack_before.entries[2:]
    ], "children after child 1 did not follow it"
    assert pack_after.entries[1][1] == pack_before.entries[1][1] + 8
    assert pack_after.children[0] == pack_before.children[0], "a sibling child changed"

    table = parse_block_table(
        after.blob(after.member("M_A01000.BIN"))[
            pack_after.entries[1][0] : pack_after.entries[1][0] + pack_after.entries[1][1]
        ],
        "rebuilt",
    )
    rebuilt_block = Block(table.blocks[0][1])
    assert rebuilt_block.entry(4) == text_bytes(longer), "8 words are 4-aligned: no pad"
    assert rebuilt_block.entry(6) == keep, "the later message entry's bytes changed"

    now = words_for(after)
    assert now["E0171.0"] == longer
    assert {k: v for k, v in now.items() if k != "E0171.0"} == {
        k: v for k, v in before.items() if k != "E0171.0"
    }


def test_every_physical_copy_of_a_line_is_rewritten():
    """The duplication model: one event, embedded in three maps, is one id and three sites."""
    block = a_block([text_bytes((0x100, END_WORD)) + PAD])
    archive = synthetic_disc(
        maps=[(name, map_pack([(171, block)])) for name in ("A01000", "A01001", "A01100")]
    )
    result = walk(archive)
    assert len(result.by_line["E0171.0"]) == 3
    blob, the_plan = rebuilt(archive, {"E0171.0": (0x200, 0x201, 0x202, END_WORD)})
    assert len(the_plan.members_rebuilt) == 3
    after = Archive.from_bytes(archive.exe, blob, source="rebuilt")
    after.require_clean()
    assert walk(after).conflicts(after) == [], "the copies no longer agree"
    assert words_for(after)["E0171.0"] == (0x200, 0x201, 0x202, END_WORD)


def test_an_ev_member_is_a_bare_block_and_its_size_lands_in_ev_sec():
    block = a_block([text_bytes((0x100, END_WORD)) + PAD])
    archive = synthetic_disc(events=[(6, block)])
    assert archive.member("EV0006.BIN").dir_index == EV_DIR_INDEX
    blob, the_plan = rebuilt(archive, {"E0006.0": (0x200, 0x201, 0x202, 0x203, END_WORD)})
    assert the_plan.growth == {"EV0006.BIN": 4}
    after = Archive.from_bytes(archive.exe, blob, source="rebuilt")
    after.require_clean()
    assert after.member("EV0006.BIN").size == archive.member("EV0006.BIN").size + 4
    assert words_for(after)["E0006.0"] == (0x200, 0x201, 0x202, 0x203, END_WORD)


# --- the three measured limits -----------------------------------------------------------------


def largest_that_fits(attempt) -> int:
    """The largest glyph count `attempt` accepts, found by doubling and then bisecting.

    Every limit here is tested **at** its boundary rather than a comfortable distance from
    it: the test finds the last size that is allowed and then asserts that one word more
    is refused *for the named reason*. A refusal that fired early, or one that fired for a
    different limit, fails.
    """
    high = 1
    while True:
        try:
            attempt(high)
        except ReinsertRefused:
            break
        high *= 2
    low = high // 2
    while low + 1 < high:
        middle = (low + high) // 2
        try:
            attempt(middle)
            low = middle
        except ReinsertRefused:
            high = middle
    return low


def test_a_block_that_outgrows_the_event_buffer_is_refused_with_its_numbers():
    """`ev_list_step` panics with "event buffer over" past `0x4000` bytes.

    The member starts within one sector of the buffer, so its sector allocation is not
    what stops the growth -- the `0x4000` test is, and the message has to say so.
    """
    block = a_block([text_bytes((0x100,) * 0x1F00 + (END_WORD,)) + PAD])
    archive = synthetic_disc(events=[(6, block)])
    member = archive.member("EV0006.BIN")
    assert member.sectors * SECTOR >= EVENT_BLOCK_LIMIT
    result = walk(archive)

    def attempt(glyphs: int) -> None:
        plan(archive, result, {"E0006.0": (0x100,) * glyphs + (END_WORD,)})

    biggest = largest_that_fits(attempt)
    with pytest.raises(ReinsertRefused, match="event buffer over") as raised:
        attempt(biggest + 1)
    assert f"{EVENT_BLOCK_LIMIT}-byte buffer" in str(raised.value)
    assert "4 bytes over" in str(raised.value), str(raised.value)


def test_a_map_whose_child_6_would_pass_the_work_area_is_refused():
    """`map_commit` breaks when the word at pack `+0x34` is past `0x6400`, less the work area.

    The head room is *computed* from the pack rather than typed: child 5 is padded until
    the map has 24 bytes of room, which is the number the refusal then has to report.
    """
    block = a_block([text_bytes((0x100, 0x101, END_WORD)) + PAD])
    sample = map_pack([(171, block)], work_records=2, filler=4)
    filler = 4 + map_head_room(sample) - 24
    archive = synthetic_disc(
        maps=[("A01000", map_pack([(171, block)], work_records=2, filler=filler))]
    )
    member = archive.member("M_A01000.BIN")
    assert map_head_room(archive.blob(member)) == 24
    assert sector_head_room(member) > 24, "the sector limit would bind first"
    result = walk(archive)

    def attempt(glyphs: int) -> None:
        plan(archive, result, {"E0171.0": (0x100,) * glyphs + (END_WORD,)})

    biggest = largest_that_fits(attempt)
    with pytest.raises(ReinsertRefused, match="4 bytes over, from 24 bytes of head room"):
        attempt(biggest + 1)


def test_a_raised_work_area_accepts_the_map_the_retail_limit_refuses():
    """`map_commit`'s limit is a patchable word, so the reinserter's copy has to move too.

    One pack and one line, planned three times: refused at the retail `MAP_WORK_AREA_END`,
    refused one byte short of what it needs, and planned when `work_area_end` is raised by
    exactly the overflow the refusal reported. Every number is taken from the pack and
    from the refusal -- the boundary by `largest_that_fits`, the shortfall out of the
    message -- so the test cannot agree with a stale constant. Without the seam, a build
    that raised the engine's limit in the executable would go on dropping lines that fit,
    and the receipt would look like a normal `--skip-unfitted` run.
    """
    block = a_block([text_bytes((0x100, 0x101, END_WORD)) + PAD])
    sample = map_pack([(171, block)], work_records=2, filler=4)
    filler = 4 + map_head_room(sample) - 24
    archive = synthetic_disc(
        maps=[("A01000", map_pack([(171, block)], work_records=2, filler=filler))]
    )
    member = archive.member("M_A01000.BIN")
    result = walk(archive)

    def attempt(glyphs: int, **kwargs) -> None:
        plan(archive, result, {"E0171.0": (0x100,) * glyphs + (END_WORD,)}, **kwargs)

    over = largest_that_fits(attempt) + 1
    with pytest.raises(ReinsertRefused, match=f"{MAP_WORK_AREA_END:#x} bytes less") as raised:
        attempt(over)
    shortfall = int(re.search(r"(\d+) bytes over", str(raised.value)).group(1))
    assert sector_head_room(member) > 24 + shortfall, "the sector limit would bind first"

    one_short = MAP_WORK_AREA_END + shortfall - 1
    with pytest.raises(ReinsertRefused, match=f"{one_short:#x} bytes less"):
        attempt(over, work_area_end=one_short)
    attempt(over, work_area_end=MAP_WORK_AREA_END + shortfall)


# --- relocation: what happens when a member outgrows its sectors -------------------------------


def relocated(archive: Archive, replacements, **kwargs) -> tuple[Archive, object]:
    """Apply a plan's byte *and* sector edits, and read the result back as an archive.

    The archive comes back over a span that starts at the arena — the filler before
    `BOKU.BIN`, which a relocated member lives in — exactly as `read_back` reads a built
    image in `tests/test_real_reinsert.py`. Without the wider span a relocated member
    would be addressed at a negative offset, which is the failure this reading exists to
    make impossible.
    """
    result = walk(archive)
    the_plan = plan(archive, result, replacements, **kwargs)
    prefix = bytes(PREFIX_FILLER.count * SECTOR)
    blob = bytearray(prefix + archive.boku)
    shift = len(prefix)
    for edit in the_plan.edits:
        if edit.file != "BOKU.BIN":
            continue
        assert blob[shift + edit.offset : shift + edit.end] == edit.old, edit.reason
        blob[shift + edit.offset : shift + edit.end] = edit.new
    exe = bytearray(archive.exe)
    for edit in the_plan.edits:
        if edit.file != "SCPS_100.88":
            continue
        assert exe[edit.offset : edit.end] == edit.old, edit.reason
        exe[edit.offset : edit.end] = edit.new
    for edit in the_plan.sectors:
        start = (edit.lba - PREFIX_FILLER.start) * SECTOR
        assert blob[start : start + len(edit.old)] == edit.old, edit.reason
        blob[start : start + len(edit.new)] = edit.new
    after = Archive.from_bytes(
        bytes(exe), bytes(blob), source="relocated", base_lba=PREFIX_FILLER.start
    )
    after.require_clean()
    return after, the_plan


def test_a_map_that_outgrows_its_sectors_moves_into_the_arena_and_still_reads_back():
    """The hard half of `PIPE-03`, at the boundary: one word more than the sectors hold.

    The member's `.SEC` record gets a new `sector`, the container is rebased because the
    arena is *below* it, every other record's field follows the rebase, and the line comes
    back out of the moved member.
    """
    archive = a_disc_with_one_line()
    member = archive.member("M_A01000.BIN")
    slack = sector_head_room(member)
    assert 0 < slack < SECTOR
    assert map_head_room(archive.blob(member)) > slack, "the work area would bind first"
    result = walk(archive)

    def attempt(glyphs: int) -> tuple[Archive, object]:
        return relocated(archive, {"E0171.0": (0x100,) * glyphs + (END_WORD,)})

    moves = smallest_that_moves(archive, result, "E0171.0")
    _after, stays = attempt(moves - 1)
    assert stays.relocations == (), "the member moved before it had to"

    words = (0x100,) * moves + (END_WORD,)
    after, moved = attempt(moves)
    (placement,) = moved.relocations
    assert placement.member == "M_A01000.BIN"
    assert placement.old_lba == member.lba
    assert placement.lba == PREFIX_FILLER.start, "the first relocation takes the first sector"
    assert placement.sectors == member.sectors + 1

    assert after.member("M_A01000.BIN").lba == placement.lba
    assert words_for(after)["E0171.0"] == words
    # Two holes and no others: the arena the placement did not take, and the sectors it
    # left — both derived from the placement, so a member laid over either shows up here.
    assert after.gaps == [
        (PREFIX_FILLER.start + placement.sectors, PREFIX_FILLER.count - placement.sectors),
        (member.lba, member.sectors),
    ]


def smallest_that_moves(archive: Archive, result, line_id: str) -> int:
    """The first glyph count at which the member holding `line_id` has to be relocated.

    `largest_that_fits` wants a refusal, so relocation is raised as one; a caller has to
    have ruled out the other limits binding first, or the bisection finds one of those.
    """

    def attempt(glyphs: int) -> None:
        if plan(archive, result, {line_id: (0x100,) * glyphs + (END_WORD,)}).relocations:
            raise ReinsertRefused("relocated")

    return largest_that_fits(attempt) + 1


def test_the_rebase_keeps_every_unmoved_member_exactly_where_it_was():
    """A container's `.SEC` `sector` is relative, so rebasing moves the origin, not the member.

    Two maps, one grown past its sectors: the other one's record has a different `sector`
    field afterwards and its bytes are at the same LBA. That is the whole reason rebasing
    is safe, and it is the part a reader has to take on trust unless it is asserted.
    """
    archive = a_disc_of_two_maps()
    before = {m.short_name: m.lba for m in archive.members}
    sectors_before = _sec_sectors(archive)
    result = walk(archive)
    words = (0x100,) * smallest_that_moves(archive, result, "E0171.0") + (END_WORD,)
    after, the_plan = relocated(archive, {"E0171.0": words})

    assert MAP_DIR_INDEX in the_plan.layout.bases, "the container was not rebased"
    assert the_plan.layout.bases[MAP_DIR_INDEX] == PREFIX_FILLER.start
    for member in after.members:
        if member.short_name == "M_A01000.BIN":
            continue
        assert member.lba == before[member.short_name], f"{member.short_name} moved"
    assert _sec_sectors(after)["M_A01001.BIN"] != sectors_before["M_A01001.BIN"], (
        "the unmoved map's record kept its old sector field, so the rebase did not reach it"
    )
    assert words_for(after)["E0172.0"] == (0x100, 0x101, END_WORD)


def _sec_sectors(archive: Archive) -> dict[str, int]:
    """Each map's `sector` field as `M_FILES.SEC` carries it, straight out of the bytes."""
    member = archive.member("M_FILES.SEC")
    sec_name, parse = SUB_ARCHIVES["M_FILES.BIN"]
    assert sec_name == "M_FILES.SEC"
    return {record.key: record.sector for record in parse(archive.blob(member)).records}


def test_a_top_level_member_relocates_by_its_two_directory_words():
    """The other addressing mode, exercised directly: `lba[i]` and `size[i]`, nothing else.

    No text-bearing member is top-level today (map packs and `EV` members are both inside
    a sub-archive), so the only way this path is covered is to ask the layout for it.
    """
    archive = a_disc_with_one_line()
    member = archive.member("F000.BIN")
    size = member.sectors * SECTOR + 1
    layout = plan_layout(archive, {member.short_name: size})
    (placement,) = layout.placements
    assert placement.lba == PREFIX_FILLER.start
    assert layout.bases == {}, "a top-level member needs no container rebased"

    arrays = dir_arrays(archive.exe)
    edits = {e.offset: e for e in directory_edits(archive, layout)}
    assert set(edits) == {
        arrays.lba_offset(member.dir_index),
        arrays.size_offset(member.dir_index),
    }
    assert edits[arrays.lba_offset(member.dir_index)].new == placement.lba.to_bytes(4, "little")
    assert edits[arrays.size_offset(member.dir_index)].new == size.to_bytes(4, "little")


def test_a_member_too_big_for_the_arena_is_refused_with_the_numbers():
    """The room is finite, and running out has to say so rather than overlap something."""
    archive = a_disc_with_one_line()
    member = archive.member("M_A01000.BIN")
    with pytest.raises(RelocationRefused, match="no run that long") as raised:
        plan_layout(archive, {member.short_name: (PREFIX_FILLER.count + 1) * SECTOR})
    assert str(PREFIX_FILLER.count) in str(raised.value)
    assert raised.value.member == member.short_name


def test_the_capacity_answer_separates_what_is_asked_for_from_what_is_net_new():
    """`Capacity.needed` is the whole allocation; `net` discounts the hole left behind.

    The gap between the two *is* the no-re-use policy, and the whole-translation answer
    turns on it (`research/relocation.md` § "Does it fit?"), so both are asserted against
    the member's own sector count rather than against each other.
    """
    archive = a_disc_with_one_line()
    member = archive.member("M_A01000.BIN")
    wanted = member.sectors * SECTOR + 1
    answer = capacity(
        archive, {m.short_name: m.size for m in archive.members} | {member.short_name: wanted}
    )
    assert answer.members == 1, "a member that still fits was counted"
    assert answer.needed == member.sectors + 1
    assert answer.vacated == member.sectors
    assert answer.net == 1
    assert answer.fits


def test_the_null_re_layout_moves_nothing_and_writes_nothing():
    """Gate 1: every member asked for exactly the size it already has."""
    archive = a_disc_with_one_line()
    layout = plan_layout(archive, {m.short_name: m.size for m in archive.members})
    assert layout.unchanged
    assert layout.placements == ()
    assert layout.free_after == layout.free_before == PREFIX_FILLER.count
    assert directory_edits(archive, layout) == []


# --- filling the runs a move vacates -----------------------------------------------------------


def a_map_of(event_id: int, sectors: int, slack: int) -> bytes:
    """A map pack that occupies exactly `sectors` sectors with `slack` bytes free at the end.

    Child 5 is padded to the size wanted, so the pack's own arithmetic decides the length
    and the fixture never has to know how big a block or a pack header is.
    """
    block = a_block([text_bytes((0x100, 0x101, END_WORD)) + PAD])
    bare = map_pack([(event_id, block)])
    filler = sectors * SECTOR - slack - len(bare) + len(parse_pack(bare).children[5])
    assert filler > 0, "the map is smaller than an empty pack; ask for more sectors"
    grown = map_pack([(event_id, block)], filler=filler)
    assert len(grown) == sectors * SECTOR - slack
    assert map_head_room(grown) > slack, "the work area would bind before the sectors do"
    return grown


SIX_MAPS = (8, 7, 8, 6, 8, 5)
"""Sector counts for `a_disc_of_six_maps`: three maps that will be grown (7, 6, 5) each
with a bigger neighbour whose hole can hold them once it has moved out itself."""

GROWN_MAPS = (1, 3, 5)
"""Which of the six are grown — the odd ones, so no two holes are adjacent."""

TINY_ARENA = [Run(PREFIX_FILLER.start, 8)]
"""Eight sectors: less than any two of the three placements together, so a layout that
fits inside it can only have come from re-using what the moves vacate."""

EIGHT_GLYPHS = (0x100,) * 8 + (END_WORD,)
"""18 bytes where 8 were, which is 10 more than `a_map_of`'s 8 bytes of slack: one sector
over, the narrowest growth that has to move at all."""


def a_disc_of_six_maps() -> Archive:
    """Six maps of `SIX_MAPS` sectors, one line each, laid out in that order."""
    return synthetic_disc(
        maps=[
            (f"A0{index}000", a_map_of(200 + index, sectors, slack=8))
            for index, sectors in enumerate(SIX_MAPS)
        ]
    )


def grow_six_maps() -> dict[str, tuple[int, ...]]:
    """`EIGHT_GLYPHS` for the line of each of `GROWN_MAPS`."""
    return {f"E0{200 + index}.0": EIGHT_GLYPHS for index in GROWN_MAPS}


def a_disc_of_two_maps() -> Archive:
    """Two maps, the second one's line a word longer than the first's."""
    block = a_block([text_bytes((0x100, END_WORD)) + PAD])
    big = a_block([text_bytes((0x100, 0x101, END_WORD)) + PAD])
    return synthetic_disc(
        maps=[("A01000", map_pack([(171, block)])), ("A01001", map_pack([(172, big)]))]
    )


def test_a_re_layout_fills_the_runs_its_moves_vacate_and_fits_where_a_bump_would_not():
    """Six maps, three of them grown one sector past their sectors, in a tiny arena.

    The arena here is **smaller than the smallest two placements together**, so an
    allocator that gave every moved member fresh arena sectors could not have produced
    this layout at all — the test asserts that, from the placements it got, rather than
    describing it. What makes it fit is that the first member out leaves a run the second
    one is then given, and so on down.

    Every line is then read back out of the built archive at the member's new home, which
    is the half a layout alone cannot show: the `.SEC` records, the container's rebase and
    the bytes all have to agree.
    """
    archive = a_disc_of_six_maps()
    was = {member.short_name: (member.lba, member.sectors) for member in archive.members}
    assert [was[f"M_A0{i}000.BIN"][1] for i in range(len(SIX_MAPS))] == list(SIX_MAPS)

    replacements = grow_six_maps()
    after, the_plan = relocated(archive, replacements, arena=TINY_ARENA)

    placements = {placement.member: placement for placement in the_plan.relocations}
    assert set(placements) == {f"M_A0{i}000.BIN" for i in GROWN_MAPS}
    for name, placement in placements.items():
        assert placement.sectors == was[name][1] + 1, f"{name} did not grow by one sector"
    wanted = sum(placement.sectors for placement in placements.values())
    assert wanted > sum(run.count for run in TINY_ARENA), (
        f"{wanted} sectors of placement into a {TINY_ARENA[0].count}-sector arena is what "
        f"a bump allocator would have had to find; this fixture does not test re-use"
    )

    re_used = {
        name: other
        for name, placement in placements.items()
        for other, run in ((o, p.vacated) for o, p in placements.items() if o != name)
        if run.contains(placement.home)
    }
    assert len(re_used) == len(GROWN_MAPS) - 1, f"only {re_used} landed in a vacated run"
    assert the_plan.layout.free_after == 0, "the arena was not spent down to the sector"

    for name, placement in placements.items():
        assert after.member(name).lba == placement.lba
        assert after.member(name).size == placement.size
    now = words_for(after)
    for line_id, words in replacements.items():
        assert now[line_id] == words, line_id
    # "Left alone" is derived from the plan's own edits, not from the list of members that
    # grew: `M_FILES.SEC` is rewritten in place for the new sizes and sector fields, and
    # that is exactly the collateral a growth-keyed comparison would not see.
    rewritten = set(placements) | {
        archive.owner(edit.offset).short_name
        for edit in the_plan.edits
        if edit.file == "BOKU.BIN" and archive.owner(edit.offset) is not None
    }
    untouched = [name for name in was if name not in rewritten]
    assert len(untouched) > len(SIX_MAPS) - len(GROWN_MAPS), "this comparison covers nothing"
    for name in untouched:
        assert after.member(name).lba == was[name][0], f"{name} moved and nothing asked it to"
        assert after.blob(after.member(name)) == archive.blob(archive.member(name))


def test_the_part_of_a_vacated_run_another_member_was_given_is_not_zeroed_over_it():
    """Re-use makes one member's old sectors another's new ones; only the rest is zeroed.

    Zeroing the whole vacated run would erase what was just written into it, and the two
    edits over one LBA are refused rather than ordered (`check_disjoint`). So the zeroing
    is what is *left* of the run — asserted here against the placements, sector by sector.
    """
    archive = a_disc_of_six_maps()
    the_plan = plan(archive, walk(archive), grow_six_maps(), arena=TINY_ARENA)

    written = {lba for edit in the_plan.sectors for lba in range(edit.lba, edit.end)}
    homes = {
        lba
        for placement in the_plan.relocations
        for lba in range(placement.lba, placement.lba + placement.sectors)
    }
    vacated = {
        lba
        for placement in the_plan.relocations
        for lba in range(placement.old_lba, placement.old_lba + placement.old_sectors)
    }
    assert homes & vacated, "no placement re-used a vacated sector; nothing is being tested"
    zeroed = {
        edit.lba + i for edit in the_plan.sectors if not any(edit.new) for i in range(edit.sectors)
    }
    assert zeroed == vacated - homes
    assert written >= homes | vacated


def test_a_layout_that_pairs_a_record_with_the_wrong_member_is_refused():
    """The permutation guard, moved to where the information still exists.

    Two records of one `.SEC` with their `sector` fields exchanged tile the container
    exactly, so coverage cannot see it and — once a member may be written into the run
    another record vacated — neither can sector order (`boku.archive._record_order`). What
    can still see it is the layout itself: a placement carries the member it is for *and*
    the record and LBA it came from, and those have to be the archive's own.
    """
    archive = a_disc_of_six_maps()
    sizes = {
        f"M_A0{index}000.BIN": archive.member(f"M_A0{index}000.BIN").sectors * SECTOR + 1
        for index in GROWN_MAPS
    }
    layout = plan_layout(archive, sizes, arena=TINY_ARENA)

    first, second = layout.placements[0], layout.placements[1]
    permuted = replace(
        layout,
        placements=(
            replace(first, member=second.member),
            replace(second, member=first.member),
            *layout.placements[2:],
        ),
    )
    with pytest.raises(RelocationRefused, match="disagree about which member this is"):
        check_placements(archive, permuted)


def test_a_member_map_that_does_not_answer_for_every_sec_record_is_refused(monkeypatch):
    """A `.SEC` is rewritten from the member map, so the two have to name the same members.

    Both the `size` and the `sector` of a record are looked up by its **name**, which is
    what makes a mis-pairing unrepresentable rather than merely detectable
    (`boku.relocate.sector_fields`). What is left to check is that the two sets of names
    agree at all — a record no member answers for would silently keep its old sector while
    everything around it moved, and a re-laid-out container is out of sector order anyway,
    so nothing downstream would see it. The disagreement is simulated by dropping one
    member from what `sector_fields` yields.
    """
    archive = a_disc_of_two_maps()
    result = walk(archive)
    words = (0x100,) * smallest_that_moves(archive, result, "E0171.0") + (END_WORD,)
    plan(archive, result, {"E0171.0": words})  # the same growth is fine as it stands

    straight = relocate.sector_fields

    def one_short(*args):
        rows = list(straight(*args))
        assert len(rows) > 1, "dropping the only record would yield nothing; nothing is tested"
        return iter(rows[:-1])

    monkeypatch.setattr("boku.reinsert.sector_fields", one_short)
    with pytest.raises(ReinsertRefused, match="does not describe the archive"):
        plan(archive, result, {"E0171.0": words})


def test_a_placement_over_a_member_that_is_staying_put_is_refused():
    """A hole is only a hole because its member left; anything else is a live member."""
    archive = a_disc_with_one_line()
    member = archive.member("M_A01000.BIN")
    layout = plan_layout(archive, {member.short_name: member.sectors * SECTOR + 1})
    (placement,) = layout.placements
    staying = archive.member("F000.BIN")
    over_it = replace(layout, placements=(replace(placement, lba=staying.lba),))
    with pytest.raises(RelocationRefused, match="does not free"):
        check_placements(archive, over_it)


def test_the_head_room_formula_is_the_one_the_research_computed():
    """`0x6400 - child6 - 12 per animated object`, with the count read out of child 0."""
    pack = map_pack([(171, a_block([text_bytes((0x100, END_WORD)) + PAD]))], work_records=3)
    (child6,) = struct.unpack_from("<I", pack, 4 + 8 * 6)
    assert map_work_records(parse_pack(pack).children[0]) == 3
    assert map_head_room(pack) == MAP_WORK_AREA_END - child6 - 36


# --- what the words themselves have to be ------------------------------------------------------


def test_a_message_whose_words_do_not_end_with_the_terminator_is_refused():
    archive = a_disc_with_one_line()
    result = walk(archive)
    with pytest.raises(ReinsertRefused, match="a message ends with"):
        plan(archive, result, {"E0171.0": (0x100, 0x101)})
    with pytest.raises(ReinsertRefused, match="unreachable bytes"):
        plan(archive, result, {"E0171.0": (0x100, END_WORD, 0x101, END_WORD)})


def test_a_select_may_not_change_the_line_count_the_executable_holds():
    """`L = g_select_lines[...]`; a translation changes a line's length, never the count."""
    lines = text_bytes((0x100, NEWLINE_WORD, 0x101, NEWLINE_WORD, 0x102, NEWLINE_WORD))
    block = a_block([lines], select_at=0)
    archive = synthetic_disc(maps=[("A01000", map_pack([(171, block)]))])
    result = walk(archive)
    assert result.sites[0].kind.startswith("SEL3.1")
    three = (0x200, NEWLINE_WORD, 0x201, NEWLINE_WORD, 0x202, NEWLINE_WORD)
    plan(archive, result, {"E0171.0": three})
    with pytest.raises(ReinsertRefused, match="draws 3 lines and these words end 2"):
        plan(archive, result, {"E0171.0": three[:4]})


def test_a_message_written_in_place_is_filled_out_after_its_terminator():
    """`TXT-04`'s rule: a message reader stops at the first `{END}`, so the filler follows it."""
    archive = a_disc_with_one_line()
    result = walk(archive)
    site = result.sites[0]
    shorter = plan(archive, result, {site.line_id: (0x200, END_WORD)}, in_place=True)
    (edit,) = shorter.edits
    assert edit.offset == site.absolute and len(edit.new) == site.size
    assert words_of(edit.new) == (0x200, END_WORD, PAD_WORD)
    with pytest.raises(ReinsertRefused, match="2 over"):
        plan(archive, result, {site.line_id: (0x200,) * 3 + (END_WORD,)}, in_place=True)


def test_a_select_written_in_place_is_filled_out_BEFORE_its_last_line_ends():
    """The other filler rule, and the reason there are two.

    A select has no terminator: every bit-15 word ends a line and the reader counts them.
    Filling *after* the last `{NL}` would add cells the box has no line for; the blanks go
    on the end of the last line instead. This is the branch a message fixture can never
    reach, so it gets a select of its own.
    """
    lines = text_bytes((0x100, NEWLINE_WORD, 0x101, NEWLINE_WORD, 0x102, NEWLINE_WORD))
    block = a_block([lines], select_at=0)
    archive = synthetic_disc(maps=[("A01000", map_pack([(171, block)]))])
    result = walk(archive)
    site = result.sites[0]
    assert site.kind.startswith("SEL")
    shorter = (0x200, NEWLINE_WORD, 0x201, NEWLINE_WORD, NEWLINE_WORD)
    (edit,) = plan(archive, result, {site.line_id: shorter}, in_place=True).edits
    assert len(edit.new) == site.size
    assert words_of(edit.new) == (
        0x200,
        NEWLINE_WORD,
        0x201,
        NEWLINE_WORD,
        PAD_WORD,
        NEWLINE_WORD,
    ), "the filler has to go before the last line's own terminator"


# --- the edits themselves ----------------------------------------------------------------------


def test_two_edits_over_one_byte_are_refused_rather_than_silently_ordered():
    with pytest.raises(ReinsertRefused, match="would be lost"):
        from boku.reinsert import check_disjoint

        check_disjoint(
            [
                ByteEdit("BOKU.BIN", 0, b"aaaa", b"bbbb", "first"),
                ByteEdit("BOKU.BIN", 2, b"aa", b"bb", "second"),
            ]
        )


def test_an_edit_may_not_change_a_file_length():
    with pytest.raises(ReinsertRefused, match="never changes a file's length"):
        ByteEdit("BOKU.BIN", 0, b"aaaa", b"bbb", "short")


def test_a_line_id_that_is_not_on_the_disc_is_refused():
    archive = a_disc_with_one_line()
    with pytest.raises(ReinsertRefused, match="no text site is called"):
        plan(archive, walk(archive), {"E9999.0": (END_WORD,)})
