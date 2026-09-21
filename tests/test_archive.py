"""The archive layer, against layouts this test laid out itself (`tests/synth_archive.py`).

Nothing here needs a disc. What it checks is that the containers `research/boku-bin.md`
describes are parsed the way it describes them, and — more to the point — that the
*rejections* work: `parse_pack` has to say no to the 100 MB of model, image and sound data
it is asked about while the member map is built, or the map's `signature` column becomes
noise and `zero_sector_notes` attributes sectors to leaves that do not exist.
"""

from __future__ import annotations

import pytest

from boku.archive import (
    BOKU_BIN_LBA,
    SECTOR,
    ArchiveError,
    build_members,
    dir_arrays,
    entropy,
    parse_offtab,
    parse_pack,
    parse_sec_ev,
    parse_sec_m,
    read_exe_dir,
    sniff,
    tim_length,
)
from boku.tim import parse
from tests import synth_archive as synth

# --- the directory in the executable ---------------------------------------------------


def test_the_directory_is_found_from_its_count_word_not_from_a_stored_address():
    builder = synth.ExeBuilder()
    entries = [
        ("\\SCPS_100.88", 21, 0x7F800),
        ("\\_DATA", 1046, 0x4800),
        ("\\_DATA\\A.BIN", 1055, 100),
    ]
    builder.directory(entries)
    read = read_exe_dir(builder.build())
    assert [(e.name, e.lba, e.size) for e in read] == entries
    assert [e.index for e in read] == [0, 1, 2]
    assert read[2].sectors == 1


def test_a_count_that_cannot_be_this_game_is_refused_rather_than_parsed():
    builder = synth.ExeBuilder()
    builder.put(synth.DIR_COUNT_ADDR, (9999999).to_bytes(4, "little"))
    with pytest.raises(ArchiveError, match="not this game's directory"):
        read_exe_dir(builder.build())


# --- packs, offset tables, TIMs --------------------------------------------------------


def test_a_pack_round_trips_through_its_own_chain():
    children = [b"a" * 10, None, b"bc" * 7]
    blob = synth.pack(children)
    parsed = parse_pack(blob)
    assert parsed is not None
    assert [size for _off, size in parsed.entries] == [10, 0, 14]
    assert [blob[o : o + s] for o, s in parsed.entries if s] == [b"a" * 10, b"bc" * 7]
    assert parsed.children == (b"a" * 10, None, b"bc" * 7)
    # And back out again, offsets recomputed: `PIPE-03` rewrites these when text grows.
    assert parsed.serialise() == blob


def test_a_sec_index_keeps_the_fields_our_record_name_does_not_carry():
    """`M_FILES.SEC` has an 8-byte padded name and a trailing junk halfword; both used to
    be dropped, so a rebuilt index could not be byte-identical."""
    blob = synth.sec_m([("A01000", 4096, 0), ("A01001", 2048, 2)])
    index = parse_sec_m(blob)
    assert index.records[0].name_field == b"A01000\0\0"
    assert index.records[0].junk == 0x4934
    assert index.serialise() == blob


def test_an_ev_index_round_trips_including_whatever_pad_follows_its_records():
    blob = synth.sec_ev([(171, 44, 3), (6, 100, 0)]) + bytes(6)
    index = parse_sec_ev(blob)
    assert index.tail == bytes(6)
    assert index.serialise() == blob


@pytest.mark.parametrize(
    ("what", "blob"),
    [
        ("too short", b"\x01\x00\x00\x00"),
        ("count of zero", (0).to_bytes(4, "little") + bytes(16)),
        ("all entries null", (2).to_bytes(4, "little") + bytes(16)),
        (
            "first offset not the header end",
            (1).to_bytes(4, "little") + b"\x20\x00\x00\x00\x04\x00\x00\x00" + bytes(32),
        ),
        (
            "runs past the blob",
            (1).to_bytes(4, "little") + b"\x0c\x00\x00\x00\xff\x00\x00\x00" + bytes(8),
        ),
    ],
)
def test_something_that_is_not_a_pack_is_rejected(what: str, blob: bytes):
    assert parse_pack(blob) is None, what


def test_an_offset_table_needs_its_first_live_offset_to_be_the_header_end():
    good = (2).to_bytes(4, "little") + b"\x0c\x00\x00\x00\x10\x00\x00\x00" + bytes(8)
    assert parse_offtab(good) == [12, 16]
    bad = (2).to_bytes(4, "little") + b"\x10\x00\x00\x00\x0c\x00\x00\x00" + bytes(8)
    assert parse_offtab(bad) is None


def test_a_tim_is_measured_by_its_own_block_lengths():
    pixels = b"\x00" * (4 * 3 * 2)
    tim = (
        (0x10).to_bytes(4, "little")
        + (2).to_bytes(4, "little")
        + (12 + len(pixels)).to_bytes(4, "little")
        + (0).to_bytes(2, "little") * 2
        + (4).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
        + pixels
    )
    assert tim_length(tim) == len(tim)
    assert sniff(tim) == "TIM"
    assert tim_length(tim[:-2]) is None, "a truncated pixel block is not a TIM"


def test_a_clut_block_that_declares_no_palette_is_not_a_tim():
    """The harm: `sites.py` asks this whether a scan hit is "inside a texture".

    62 four-aligned candidates in `M_FILES.BIN`'s map packs declare a CLUT block with
    `colours`/`cluts` of zero — a shape the PsyQ format cannot mean and `tim.parse`
    refuses — and a looser answer here turns each into a fictitious texture span that
    explains away whatever text sites fall inside it.
    """
    pixels = b"\x00" * (4 * 3 * 2)
    empty_clut = (12).to_bytes(4, "little") + (0).to_bytes(2, "little") * 4
    body = (
        (12 + len(pixels)).to_bytes(4, "little")
        + (0).to_bytes(2, "little") * 2
        + (4).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
        + pixels
    )
    blob = (0x10).to_bytes(4, "little") + (0x9).to_bytes(4, "little") + empty_clut + body
    assert parse(blob) is None, "the fixture is not the shape this test is about"
    assert tim_length(blob) is None
    assert sniff(blob) != "TIM"


def test_entropy_separates_a_constant_block_from_a_varied_one():
    assert entropy(b"\x00" * 1024) == 0.0
    assert entropy(bytes(range(256)) * 4) == pytest.approx(8.0)


# --- the member map and its tiling gate -------------------------------------------------


def _two_members() -> tuple[bytes, bytes]:
    ev_records = [(6, 100, 0), (10, 200, 1)]
    ev_bin = bytes(SECTOR) + bytes(SECTOR)
    blob, entries = synth.archive_of(
        [
            ("\\_DATA", bytes(SECTOR)),
            ("\\_DATA\\EV.BIN", ev_bin),
            ("\\_DATA\\EV.SEC", synth.sec_ev(ev_records)),
        ]
    )
    builder = synth.ExeBuilder()
    builder.directory(entries)
    return builder.build(), blob


def test_a_sub_archive_expands_into_one_member_per_record():
    exe, blob = _two_members()
    members, problems, gaps = build_members(exe, blob)
    assert (problems, gaps) == ([], [])
    assert [m.short_name for m in members] == ["_DATA", "EV0006.BIN", "EV0010.BIN", "EV.SEC"]
    assert [m.offset for m in members] == [0, SECTOR, 2 * SECTOR, 3 * SECTOR]
    assert [m.sub_index for m in members] == [None, 0, 1, None]


def test_a_member_the_directory_has_stopped_pointing_at_is_a_problem():
    """A drifted directory leaves live bytes claimed by nobody, and that is the gate.

    `PIPE-03` relocates members, so "every member starts where the last one ended" is no
    longer true of a built archive — the sectors a relocation vacates are a hole. What
    stays true is that a hole is **zero**: the build clears what it moves out of. So a
    hole with bytes in it is the drift this used to catch, and a hole without is the
    normal shape of a relocated image.

    Moving `EV.SEC`'s entry also costs the records it holds, so the archive this builds is
    a larger breakage than the hole alone — the hole is what is asserted, because it is
    the part that stays true when the drifted entry is an ordinary member.
    """
    exe, blob = _two_members()
    _members, problems, gaps = build_members(exe, blob)
    assert (problems, gaps) == ([], [])
    shifted = bytearray(exe)
    # Move EV.SEC's own directory entry one sector later, leaving its bytes behind.
    sec = next(e for e in read_exe_dir(exe) if e.name.endswith("EV.SEC"))
    off = dir_arrays(exe).lba_offset(sec.index)
    shifted[off : off + 4] = (sec.lba + 1).to_bytes(4, "little")
    _members, problems, gaps = build_members(bytes(shifted), blob + bytes(SECTOR))
    assert gaps and gaps[0][0] > BOKU_BIN_LBA, "the hole was not reported"
    assert any("belong to no member and are not zero" in p for p in problems)


def test_a_sec_whose_records_do_not_fill_its_container_is_a_zeroed_gap():
    """The other half of the rule above: an unclaimed run of zeros is reported, not refused."""
    ev_bin = bytes(3 * SECTOR)  # one sector more than the records account for
    blob, entries = synth.archive_of(
        [
            ("\\_DATA\\EV.BIN", ev_bin),
            ("\\_DATA\\EV.SEC", synth.sec_ev([(6, 100, 0), (10, 200, 1)])),
        ]
    )
    builder = synth.ExeBuilder()
    builder.directory(entries)
    _members, problems, gaps = build_members(builder.build(), blob)
    assert problems == []
    assert gaps == [(BOKU_BIN_LBA + 2, 1)]


def test_two_records_with_their_sectors_swapped_are_a_problem():
    """Coverage cannot see a permutation, and a permutation mis-aims every write.

    Two equal-sized records with their `sector` fields exchanged still cover every sector
    of the container exactly once, so the overlap and gap checks are both silent — and a
    rebuild would put `EV0006`'s English into `EV0010`'s bytes. The `.SEC` record order is
    what says which is which, and it is checked because of that.
    """
    ev_bin = bytes(2 * SECTOR)
    in_order = [(6, 100, 0), (10, 200, 1)]
    swapped = [(6, 100, 1), (10, 200, 0)]
    for records, wanted in ((in_order, False), (swapped, True)):
        blob, entries = synth.archive_of(
            [("\\_DATA\\EV.BIN", ev_bin), ("\\_DATA\\EV.SEC", synth.sec_ev(records))]
        )
        builder = synth.ExeBuilder()
        builder.directory(entries)
        _members, problems, gaps = build_members(builder.build(), blob)
        assert gaps == [], "the swap left a hole; then coverage would have caught it"
        assert any("records have been reordered" in p for p in problems) is wanted, problems


def test_a_record_that_moved_into_the_arena_is_a_relocation_not_a_reordering():
    """The one exception, and the line it is drawn on: below `BOKU.BIN` is the arena.

    `PIPE-03` relocates record 1 into the filler and rebases the container to match, which
    leaves the records out of order on purpose — record 1 below record 0 — and a zero hole
    where it used to be. Nothing here may be reported, or every built image is refused.
    """
    arena = 2
    base = BOKU_BIN_LBA - arena

    def laid_out(records):
        """`EV.BIN` + `EV.SEC` over the arena, with `EV.SEC` really holding `records`."""
        blob, entries = synth.archive_of(
            [
                ("\\_DATA\\EV.BIN", bytes(2 * SECTOR)),
                ("\\_DATA\\EV.SEC", synth.sec_ev(records)),
            ]
        )
        return bytes(arena * SECTOR) + blob, entries

    # Two passes: the records' `sector` fields are relative to the rebased container, so
    # the layout has to exist before they can be written. `sec_ev`'s length depends only
    # on the record count, so the second pass lands in exactly the same place.
    _blob, entries = laid_out([(6, 100, 0), (10, 200, 0)])
    ev_lba = next(lba for name, lba, _size in entries if name.endswith("EV.BIN"))
    # Record 0 stays in the archive; record 1 is in the arena and the container is rebased
    # to the arena's first sector, so both records count from `base`.
    blob, entries = laid_out([(6, 100, ev_lba - base), (10, 200, 0)])
    builder = synth.ExeBuilder()
    builder.directory(
        [(name, base if name.endswith("EV.BIN") else lba, size) for name, lba, size in entries]
    )
    members, problems, gaps = build_members(builder.build(), blob, base)
    assert [m.lba for m in members if m.sub_index is not None] == [ev_lba, base], (
        "the fixture did not put record 1 in the arena and record 0 in the archive"
    )
    assert any(lba < BOKU_BIN_LBA for lba, _count in gaps), "the arena was not read at all"
    assert not any("reordered" in p for p in problems), problems

    # The same two records with the out-of-order one left *inside* `BOKU.BIN` is the
    # permutation, and it is reported. The boundary is the whole rule.
    blob, entries = laid_out([(6, 100, 1), (10, 200, 0)])
    builder = synth.ExeBuilder()
    builder.directory(entries)
    _members, problems, _gaps = build_members(builder.build(), blob, base)
    assert any("reordered" in p for p in problems), problems


def test_a_map_record_is_named_after_its_name_field():
    records = parse_sec_m(synth.sec_m([("A01000", 4096, 0), ("A01001", 2048, 2)])).records
    assert [(r.key, r.sector, r.size) for r in records] == [
        ("M_A01000.BIN", 0, 4096),
        ("M_A01001.BIN", 2, 2048),
    ]


def test_an_ev_record_names_itself_after_its_event_id():
    assert parse_sec_ev(synth.sec_ev([(171, 44, 3)])).records[0].key == "EV0171.BIN"
