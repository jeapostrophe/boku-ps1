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

import struct

import pytest

from boku.archive import EV_DIR_INDEX, MAP_DIR_INDEX, SECTOR, Archive, parse_pack
from boku.events import Block, parse_block_table
from boku.glyphs import END_WORD, NEWLINE_WORD, PAD_WORD, words_of
from boku.reinsert import (
    EVENT_BLOCK_LIMIT,
    MAP_WORK_AREA_END,
    ByteEdit,
    ReinsertRefused,
    map_head_room,
    map_work_records,
    plan,
    sector_head_room,
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


def test_a_member_that_outgrows_its_sectors_is_refused_and_says_how_far_over():
    """Growth past a member's own sectors means moving every later member: out of scope."""
    archive = a_disc_with_one_line()
    member = archive.member("M_A01000.BIN")
    slack = sector_head_room(member)
    assert 0 < slack < SECTOR
    assert map_head_room(archive.blob(member)) > slack, "the work area would bind first"
    result = walk(archive)

    def attempt(glyphs: int) -> None:
        plan(archive, result, {"E0171.0": (0x100,) * glyphs + (END_WORD,)})

    biggest = largest_that_fits(attempt)
    with pytest.raises(ReinsertRefused, match="4 over, from") as raised:
        attempt(biggest + 1)
    assert "moving every later member" in str(raised.value)
    assert "E0171.0" in str(raised.value)


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
