"""`PIPE-05`'s round-trip gate and `PIPE-03`'s limits, on the real dump.

**The standing gate**: import -> extract -> reinsert **every** line with its own original
words -> build, and the image comes back byte for byte. That is not a null build with the
reinserter switched off: every text-bearing member is taken apart and put back together —
message entry, block offset table, child-1 table, pack table, `.SEC` index — and the
comparison with the bytes on the disc is what says the path loses nothing.
`test_perturbing_one_line_breaks_the_round_trip` is that gate made red on purpose,
`ENG-1`, at the narrowest condition there is: one glyph of one line.

Everything here skips cleanly on a checkout with no `disc/` — the repo ships none of the
game.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.archive import EV_DIR_INDEX, MAP_DIR_INDEX, SECTOR, Archive
from boku.build import ARENA_FILE, BuildRefused, build, verify_written_sectors
from boku.disc import DiscImage
from boku.glyphs import END_WORD, NEWLINE_WORD, PAD_WORD, GlyphTable, words_of
from boku.layout import StockEncoder, lay_out_array
from boku.reinsert import (
    EVENT_BLOCK_LIMIT,
    ByteEdit,
    ReinsertRefused,
    map_head_room,
    plan,
    sector_head_room,
)
from boku.relocate import PREFIX_FILLER, TAIL_FILLER, Run, unclaimed_runs
from boku.sites import walk as walk_sites
from boku.translation import PreEncoded, SampleScenes

TIGHTEST_MAP = "M_H06001.BIN"
TIGHTEST_MAP_HEAD_ROOM = 2664
"""`research/loading-and-memory.md` § "The short answer for the reinserter", computed by
`work/rec06/mapstats2.py`. Reproducing it is how this port says it ported the formula and
not just some formula."""

NEWLINES_ON_THE_DISC = 6010
"""`research/text-format.md`: "The same blank follows **every** `0x8001` inside a message
(6,010 of 6,010)"."""

FILESYSTEM_ENTRIES = 30
"""What `DiscImage.walk` finds on the retail disc; a build may not add or lose one."""


@pytest.fixture(scope="module")
def original_words(archive: Archive, walk_reader) -> dict[str, tuple[int, ...]]:
    """Every logical line with the words that are on the disc now."""
    return {
        line_id: words_of(walk_reader.raw(archive, sites[0]))
        for line_id, sites in walk_reader.by_line.items()
    }


def read_back(image: Path) -> tuple[Archive, object]:
    """The two files pulled out of a built image, walked as if they were an import.

    The archive is read back over a span that **starts at the arena** — `PIPE-03`
    relocates a member into the filler before `BOKU.BIN`, which is below the file's own
    extent, so reading only the file would drop every member that moved and, with a
    rebased container, every member the container holds. The filler sectors a build did
    not write are still zero-filled Form 2 and read as their 2,048 zero bytes
    (`DiscImage.read_form1_span`).
    """
    with DiscImage(image) as opened:
        entries = list(opened.walk())
        files = {entry.name: entry for entry in entries if not entry.is_dir}
        exe = opened.read_file(files["SCPS_100.88"].lba, files["SCPS_100.88"].size)
        archive_entry = files["BOKU.BIN"]
        end = archive_entry.lba + (archive_entry.size + SECTOR - 1) // SECTOR
        assert archive_entry.lba == PREFIX_FILLER.end, "the arena is not against BOKU.BIN"
        boku = opened.read_form1_span(PREFIX_FILLER.start, end - PREFIX_FILLER.start)
    assert len(entries) == FILESYSTEM_ENTRIES, "the build added or lost a filesystem entry"
    built = Archive.from_bytes(exe, boku, source=str(image), base_lba=PREFIX_FILLER.start)
    built.require_clean()
    return built, walk_sites(built)


# --- the round trip ------------------------------------------------------------------------


def test_reinserting_every_line_with_its_own_words_changes_no_byte(
    archive: Archive, walk_reader, original_words
):
    """`PIPE-05`: the whole rebuild path runs, and the disc comes back unchanged."""
    the_plan = plan(archive, walk_reader, original_words)
    assert the_plan.sites_written == len(walk_reader.sites)
    assert the_plan.members_rebuilt, "no member was rebuilt; this gate would pass over nothing"
    assert the_plan.growth == {}
    assert the_plan.edits == (), [edit.reason for edit in the_plan.edits]


def test_the_round_trip_build_reproduces_the_image_byte_for_byte(
    real_image: Path, disc_dir: Path, original_words, tmp_path_factory
):
    result = build(
        source=real_image,
        out_dir=tmp_path_factory.mktemp("round-trip"),
        disc_dir=disc_dir,
        translation=PreEncoded(original_words),
        name="round-trip",
    )
    assert result.refused_lines == []
    assert len(result.plan.members_rebuilt) > 600, "the rebuild did not reach the whole disc"
    # The null re-layout: every member asked for the size it already has, so nothing is
    # planned to move and not one sector outside a file is written (`boku.relocate`).
    assert result.plan.layout.unchanged
    assert result.plan.sectors == ()
    assert result.written.sectors == []
    assert result.written.source_sha1 == result.written.result_sha1
    assert result.written.image.read_bytes() == real_image.read_bytes()


def test_perturbing_one_line_breaks_the_round_trip(archive: Archive, walk_reader, original_words):
    """The red receipt, at the narrowest condition: one glyph of one line.

    The gate above passes over 6,000 sites and 600 members, so "it came back identical"
    has to be able to fail for the reason it is about. One word of one message is changed
    and the plan has to name that member and nothing else.
    """
    line_id = next(k for k, v in original_words.items() if len(v) > 2)
    site = walk_reader.by_line[line_id][0]
    perturbed = dict(original_words)
    perturbed[line_id] = (original_words[line_id][0] ^ 1, *original_words[line_id][1:])
    the_plan = plan(archive, walk_reader, perturbed)
    assert {edit.reason.split()[0] for edit in the_plan.edits} == {
        s.member for s in walk_reader.by_line[line_id]
    }
    assert the_plan.growth == {}, "a same-length change moves no member"
    assert site.member in the_plan.edits[0].reason


# --- one line, grown, at every copy ----------------------------------------------------------


@pytest.fixture(scope="module")
def grown(real_image: Path, disc_dir: Path, original_words, tmp_path_factory):
    """Build with one real line a few words longer, at all 19 of its physical copies."""
    # A line with many copies is the interesting one: the fan-out is what a reinserter
    # gets wrong. The test below asserts this one really has the fan-out and the room.
    line_id = GROWN_LINE
    words = dict(original_words)
    extra = words_of(GlyphTable.load().encode_english(" HELLO THERE FRIEND"))
    words[line_id] = (*original_words[line_id][:-1], *extra, END_WORD)
    result = build(
        source=real_image,
        out_dir=tmp_path_factory.mktemp("grown"),
        disc_dir=disc_dir,
        translation=PreEncoded(words),
        name="grow-one-line",
    )
    return result, line_id, words[line_id]


GROWN_LINE = "E0670.0"
"""Nineteen physical copies, and every member holding one has room: a test asserts both."""


def test_the_line_chosen_for_the_growth_gate_really_does_fan_out(archive: Archive, walk_reader):
    sites = walk_reader.by_line[GROWN_LINE]
    assert len(sites) > 10, "a one-copy line would not exercise the duplication model"
    for site in sites:
        member = archive.member(site.member)
        assert sector_head_room(member) > 64


def test_growing_one_line_rewrites_every_copy_and_leaves_the_rest_of_the_game_alone(
    grown, original_words, walk_reader
):
    result, line_id, new_words = grown
    assert result.refused_lines == []
    assert set(result.plan.growth) == {s.member for s in walk_reader.by_line[line_id]}, (
        "the members that grew are not exactly the ones holding a copy of the line"
    )
    assert len(result.plan.members_rebuilt) > 600, "the other members were not rebuilt"
    built, built_walk = read_back(result.written.image)

    assert built_walk.problems == [], built_walk.problems[:3]
    assert built_walk.conflicts(built) == [], "the copies of some line no longer agree"
    assert set(built_walk.by_line) == set(original_words), "a line id appeared or vanished"

    now = {k: words_of(built_walk.raw(built, s[0])) for k, s in built_walk.by_line.items()}
    assert now[line_id] == new_words
    for site in built_walk.by_line[line_id]:
        assert words_of(built_walk.raw(built, site)) == new_words, f"{site.member} was missed"
    changed = sorted(k for k in now if now[k] != original_words[k])
    assert changed == [line_id]


def test_every_sector_the_growth_wrote_carries_its_own_edc_and_ecc(grown):
    result = grown[0]
    assert result.written.sectors, "nothing was written; there is no gate here"
    assert verify_written_sectors(result.written.image, result.written.sectors) == []


# --- members grown out of their sectors, built, and read back ----------------------------------

RELOCATED_MAPS = (TIGHTEST_MAP, "M_G16101.BIN")
"""The map with the least work-area head room, and the one `research/relocation.md`
§ "Does it fit?" puts furthest over its sectors under the full-translation estimate. That
these two are the ones the growth below actually pushes out is asserted, not assumed."""

RELOCATION_GLYPHS = 16
"""Glyphs added to every line of the two maps: enough to push both past their sectors and
not enough to reach `map_commit`'s `0x6400` work area. Which is checked — the test below
reads both bounds off the disc, so a future import that narrows the window fails rather
than quietly testing something else."""


@pytest.fixture(scope="module")
def relocating(real_image: Path, disc_dir: Path, archive: Archive, walk_reader, original_words,
                tmp_path_factory):
    """Grow every line of the two maps until they no longer fit, and build the image."""
    words = dict(original_words)
    for name in RELOCATED_MAPS:
        for line_id in sorted({s.line_id for s in walk_reader.sites if s.member == name}):
            words[line_id] = (
                *original_words[line_id][:-1],
                *([0x100] * RELOCATION_GLYPHS),
                END_WORD,
            )
    result = build(
        source=real_image,
        out_dir=tmp_path_factory.mktemp("relocating"),
        disc_dir=disc_dir,
        translation=PreEncoded(words),
        name="relocate",
    )
    return result, words


def test_the_growth_that_forces_a_relocation_is_inside_the_work_area_window(
    archive: Archive, relocating
):
    """The growth has to sit in `(sector slack, work-area head room)` for both maps.

    Below the slack nothing moves and the gate proves nothing; above the head room
    `map_commit`'s `0x6400` test would refuse first and the gate would prove something
    else. Both bounds are read off the disc, so a future import that narrows the window
    fails here instead of turning the gate vacuous.
    """
    result, _words = relocating
    for name in RELOCATED_MAPS:
        member = archive.member(name)
        grown_by = result.plan.growth[name]
        assert sector_head_room(member) < grown_by < map_head_room(archive.blob(member)), name


def test_two_real_maps_grown_past_their_sectors_move_and_re_extract_correctly(
    archive: Archive, relocating, original_words, real_image: Path
):
    """`PIPE-03`'s hard half on the real disc, end to end.

    Build with two maps grown out of their sectors, then read the built image back as if
    it were an import: every line correct at every copy, every member that did *not* grow
    byte-identical, the `.SEC` records and `g_cd_dir` agreeing with where the bytes went,
    and the image still exactly as long as it was.
    """
    result, words = relocating
    assert result.refused_lines == []
    moved = {p.member for p in result.plan.relocations}
    assert set(RELOCATED_MAPS) <= moved, f"neither target moved; {sorted(moved)}"
    assert moved == {
        name for name, delta in result.plan.growth.items()
        if archive.member(name).size + delta > archive.member(name).sectors * SECTOR
    }, "a member moved that did not have to, or one that had to did not"
    for placement in result.plan.relocations:
        assert PREFIX_FILLER.start <= placement.lba
        assert placement.lba + placement.sectors <= PREFIX_FILLER.end

    built, built_walk = read_back(result.written.image)
    assert built_walk.problems == [], built_walk.problems[:3]
    assert built_walk.conflicts(built) == [], "the copies of some line no longer agree"
    assert set(built_walk.by_line) == set(original_words), "a line id appeared or vanished"

    # Where the bytes went: the built archive's own directory and `.SEC` records, read
    # back through the parsers, have to put each moved member exactly where the plan did.
    for placement in result.plan.relocations:
        assert built.member(placement.member).lba == placement.lba, placement.member
        assert built.member(placement.member).size == placement.size, placement.member

    now = {k: words_of(built_walk.raw(built, s[0])) for k, s in built_walk.by_line.items()}
    for line_id, expected in words.items():
        for site in built_walk.by_line[line_id]:
            assert words_of(built_walk.raw(built, site)) == expected, f"{line_id} @ {site.member}"
    assert {k for k in now if now[k] != original_words[k]} == {
        k for k in words if words[k] != original_words[k]
    }

    # "Every other member" is derived from the plan's own edits rather than from the list
    # of members that grew: the two `.SEC` indexes are rewritten in place (new sizes, new
    # sector fields) without changing length, and they are exactly the kind of collateral
    # a growth-keyed comparison would not see.
    rewritten = {placement.member for placement in result.plan.relocations}
    for edit in result.plan.edits:
        if edit.file != "BOKU.BIN":
            continue
        owner = archive.owner(edit.offset)
        assert owner is not None, edit.reason
        rewritten.add(owner.short_name)
    assert set(result.plan.growth) <= rewritten
    untouched = [m for m in archive.members if m.short_name not in rewritten]
    assert len(untouched) > 600, "almost nothing was left alone; this comparison is empty"
    for member in untouched:
        assert built.blob(built.member(member.short_name)) == archive.blob(member), (
            f"{member.short_name} changed and nothing asked it to"
        )

    assert verify_written_sectors(result.written.image, result.written.sectors) == []
    assert result.written.image.stat().st_size == real_image.stat().st_size


def test_the_manifest_says_which_file_each_relocated_sector_belongs_to(relocating):
    """A relocation writes two runs, and only one of them is outside a file.

    The member's new home is in the arena, which belongs to no file; the sectors it leaves
    are inside `BOKU.BIN` and the manifest has to say so, because `boku trial` checks an
    image diff against the manifest row by row. Both sets come from the placements.
    """
    result, _words = relocating
    where = {record.lba: record.file for record in result.written.sectors}
    named = {ARENA_FILE: 0, "BOKU.BIN": 0}
    for placement in result.plan.relocations:
        for lba, expected in [
            *((lba, ARENA_FILE) for lba in range(placement.lba, placement.lba + placement.sectors)),
            *(
                (lba, "BOKU.BIN")
                for lba in range(placement.old_lba, placement.old_lba + placement.old_sectors)
            ),
        ]:
            # A sector the build wrote back to the bytes it already held is not in the
            # manifest at all (`Ledger.records`) — a vacated sector that was zero padding
            # already is the usual case.
            if lba in where:
                assert where[lba] == expected, lba
                named[expected] += 1
    assert min(named.values()) > 0, f"one of the two runs is missing from the manifest: {named}"
    assert set(where.values()) == {ARENA_FILE, "BOKU.BIN", "SCPS_100.88"}


# --- the measured limits, on the members they actually bind on ---------------------------------


def test_no_map_on_this_disc_reaches_the_work_area_before_it_reaches_its_sectors(
    archive: Archive,
):
    """A finding, pinned: `map_commit`'s `0x6400` test is not the limit that binds first.

    Every one of the 555 map packs has **less** slack to the end of its own sectors than
    it has head room before child 6 passes the work area — `M_H06001`, the tightest map in
    `research/loading-and-memory.md`, has 2,664 bytes of head room and 1,656 of slack. So
    a single member's growth always runs into `PIPE-03`'s sector refusal first, and the
    four mechanisms in that note's § "Making room" are a *second* problem, behind moving
    members. If a future import ever breaks this, the work-area refusal starts mattering
    and this test says so; it is covered on synthetic packs in `tests/test_reinsert.py`,
    which is the only place it can be reached.
    """
    rooms = [
        (map_head_room(archive.blob(member)), sector_head_room(member), member.short_name)
        for member in archive.members
        if member.dir_index == MAP_DIR_INDEX
    ]
    assert rooms
    binds_first = [row for row in rooms if row[0] < row[1]]
    assert binds_first == [], binds_first[:5]
    tightest = min(rooms, key=lambda row: row[0])
    assert (tightest[2], tightest[0]) == (TIGHTEST_MAP, TIGHTEST_MAP_HEAD_ROOM)


def test_an_ev_member_refuses_a_block_past_the_event_buffer(
    archive: Archive, walk_reader, original_words
):
    """The `0x4000` buffer `ev_list_step` panics over, asked for on a real `EV.BIN` member."""
    member = next(m for m in archive.members if m.dir_index == EV_DIR_INDEX and m.size > 3000)
    line_id = next(s.line_id for s in walk_reader.sites if s.member == member.short_name)
    words = dict(original_words)
    words[line_id] = (*original_words[line_id][:-1], *([0x100] * EVENT_BLOCK_LIMIT), END_WORD)
    with pytest.raises(ReinsertRefused, match="event buffer over") as raised:
        plan(archive, walk_reader, words)
    assert f"{EVENT_BLOCK_LIMIT}-byte buffer" in str(raised.value)


@pytest.fixture(scope="module")
def one_sector_over(archive: Archive, walk_reader, original_words):
    """The tightest text-bearing member, and the words that push it one sector past itself.

    The ten members with under 64 bytes of slack are where the full script will bind, so
    the member the relocation tests use is the one the translation will reach first.
    """
    tight = min(
        (
            archive.member(sites[0].member)
            for sites in walk_reader.by_line.values()
            if sites[0].container in ("c1", "ev")
        ),
        key=sector_head_room,
    )
    line_id = next(s.line_id for s in walk_reader.sites if s.member == tight.short_name)
    words = dict(original_words)
    words[line_id] = (
        *original_words[line_id][:-1],
        *([0x100] * ((sector_head_room(tight) + 4) // 2)),
        END_WORD,
    )
    return tight, words


def test_a_member_with_no_slack_moves_into_the_arena_instead_of_refusing(
    archive: Archive, walk_reader, one_sector_over
):
    """This used to be `PIPE-03`'s refusal — "moving every later member … which this unit
    does not do". Moving members is what this unit does, so the same growth on the same
    member now has to produce a placement, in the arena, one sector bigger than it was.
    """
    tight, words = one_sector_over
    the_plan = plan(archive, walk_reader, words)
    (placement,) = the_plan.relocations
    assert placement.member == tight.short_name
    assert placement.old_lba == tight.lba
    assert placement.sectors == tight.sectors + 1
    assert PREFIX_FILLER.start <= placement.lba < PREFIX_FILLER.end
    assert the_plan.layout.free_after == PREFIX_FILLER.count - placement.sectors


def test_a_growth_the_arena_cannot_hold_is_refused_with_the_numbers(
    archive: Archive, walk_reader, one_sector_over
):
    """What stays impossible: the filler is finite, and running out has to say so.

    No single member can reach 765 sectors on this disc — whichever of the two RAM limits
    binds for the member picked, it refuses long before then — so the arena is narrowed to
    one sector *less* than the placement needs, which is the boundary the refusal is
    about. Both numbers in the message come from the placement the full arena made, not
    from a count typed here.
    """
    tight, words = one_sector_over
    (placement,) = plan(archive, walk_reader, words).relocations
    short = [Run(PREFIX_FILLER.start, placement.sectors - 1)]
    with pytest.raises(ReinsertRefused, match="no run that long") as raised:
        plan(archive, walk_reader, words, arena=short)
    assert tight.short_name in str(raised.value)
    assert f"needs {placement.sectors} sectors" in str(raised.value)
    assert f"{placement.sectors - 1}-sector arena" in str(raised.value)


def test_the_arena_is_the_two_runs_the_disc_recon_measured(real_image: Path):
    """`PREFIX_FILLER` and `TAIL_FILLER` are pinned constants; the image is the source.

    `boku.relocate` allocates from a number written into the module so that a plan can be
    made without an image beside it. This is the one place the two are held together — if
    a future import has a different filesystem, the constants are wrong and this says so.
    """
    with DiscImage(real_image) as image:
        runs = unclaimed_runs(image)
    assert [(run.start, run.count) for run in runs] == [
        (PREFIX_FILLER.start, PREFIX_FILLER.count),
        (TAIL_FILLER.start, TAIL_FILLER.count),
    ]


# --- what the builder refuses before it copies 660 MB ---


def test_a_binary_patch_inside_a_rebuilt_member_is_refused_rather_than_silently_lost(
    real_image: Path, disc_dir: Path, original_words, walk_reader, tmp_path_factory
):
    """Two writes over one byte would make the image depend on the order they were applied.

    `plan` checks its own edits are disjoint; a caller's binary patches were not in that
    set. A rebuilt member's edit covers the member's whole byte range, so a patch aimed
    inside one verifies against the *source* image, is applied after the rebuild because
    its offset is larger, and lands where the growth has already moved things.
    """
    site = walk_reader.by_line[GROWN_LINE][0]
    member_start = site.absolute - site.offset
    inside = ByteEdit(
        "BOKU.BIN",
        member_start + 4,
        b"\x00" * 4,
        b"\x01" * 4,
        "a patch aimed inside a member that is about to be rebuilt",
    )
    words = dict(original_words)
    words[GROWN_LINE] = (*original_words[GROWN_LINE][:-1], 0x100, 0x100, END_WORD)
    with pytest.raises(ReinsertRefused, match="would be lost"):
        build(
            source=real_image,
            out_dir=tmp_path_factory.mktemp("overlap"),
            disc_dir=disc_dir,
            translation=PreEncoded(words),
            binary_patches=[inside],
            dry_run=True,
        )


def test_an_edit_that_runs_past_its_files_extent_is_refused_before_the_copy(
    real_image: Path, tmp_path_factory
):
    """`read_file_bytes` would read on into the next file, so only the *write* would notice.

    By then the 660 MB copy is done and earlier edits are already in the staging image.
    """
    out = tmp_path_factory.mktemp("overrun")
    with DiscImage(real_image) as image:
        archive_entry = next(e for e in image.walk() if e.name == "BOKU.BIN")
    over = ByteEdit(
        "BOKU.BIN",
        archive_entry.size - 2,
        bytes(4),
        bytes(4),
        "four bytes starting two from the end",
    )
    with pytest.raises(BuildRefused, match="past the file's own"):
        build(source=real_image, out_dir=out, binary_patches=[over])
    assert not (out / "image.img").exists(), "the image was copied before the refusal"


def test_a_dry_run_makes_the_same_refusals_the_real_build_would(real_image: Path):
    """A lint report that is green on an image the build would refuse is worse than none."""
    into_the_import = real_image.resolve().parent
    with pytest.raises(BuildRefused, match="holds the image this build reads"):
        build(source=real_image, out_dir=into_the_import, dry_run=True)
    with pytest.raises(BuildRefused, match="is not there"):
        build(source=Path("no-such-image.img"), out_dir=into_the_import / "x", dry_run=True)


# --- the claim behind the indent switch --------------------------------------------------------


# --- a real translation, with the stock font's limits showing ----------------------------------


def test_a_line_that_does_not_fit_is_left_alone_at_every_one_of_its_copies(
    real_image: Path, disc_dir: Path, original_words, walk_reader, tmp_path_factory
):
    """`--skip-unfitted` leaves a line in Japanese; it may never leave *half* a line.

    Dropping a line from one map and keeping it in another would break the invariant the
    whole id scheme rests on — that every copy of a logical line is byte-identical — and
    `Walk.conflicts` would only notice afterwards, in a shipped image. The three draft
    sample scenes are the fixture because the stock 14-px cells make plenty of them
    overflow, which is what gives this test something to skip.
    """
    source = SampleScenes.from_directory(REPO_ROOT / "translation" / "samples")
    result = build(
        source=real_image,
        out_dir=tmp_path_factory.mktemp("samples"),
        disc_dir=disc_dir,
        translation=source,
        skip_unfitted=True,
        name="samples",
    )
    assert result.written_lines, "nothing fit; this test would prove nothing"
    assert result.refused_lines, "everything fit; the skip path was never taken"

    built, built_walk = read_back(result.written.image)
    assert built_walk.problems == [], built_walk.problems[:3]
    assert built_walk.conflicts(built) == []
    now = {k: words_of(built_walk.raw(built, s[0])) for k, s in built_walk.by_line.items()}
    written = {line.line_id for line in result.written_lines}
    for line in result.refused_lines:
        assert now[line.line_id] == original_words[line.line_id], (
            f"{line.line_id} was refused and written anyway"
        )
    for line_id in written:
        for site in built_walk.by_line[line_id]:
            assert words_of(built_walk.raw(built, site)) == now[line_id]
    assert {k for k in now if now[k] != original_words[k]} == written


def test_a_real_array_item_is_rewritten_in_place_and_keeps_its_neighbours(
    archive: Archive, walk_reader, original_words
):
    """A code-file array has no slack, so the item keeps its byte length and its terminator.

    `REC-03` finds item *n + 1* by scanning past item *n*'s control word, so an item that
    moved its terminator would move every item after it — which is why the filler goes
    *before* it and growth is refused rather than absorbed.
    """
    encoder = StockEncoder.load()
    singles = [
        site
        for site in walk_reader.sites
        if site.kind.startswith("ARR")
        and [i for i, w in enumerate(words_of(walk_reader.raw(archive, site))) if w & 0x8000]
        == [site.size // 2 - 1]
    ]
    assert singles, "no single-line array item on the disc; this test covers nothing"
    site = max(singles, key=lambda s: s.size)
    original = walk_reader.raw(archive, site)
    laid = lay_out_array(site.line_id, "Beetle Net", original, encoder, site.size)
    assert laid.fits, laid.problems

    the_plan = plan(archive, walk_reader, {site.line_id: laid.words}, in_place=True)
    (edit,) = the_plan.edits
    assert edit.file == "SCPS_100.88"
    assert len(edit.new) == site.size == len(edit.old)
    assert words_of(edit.new)[-1] == words_of(original)[-1], "the item's terminator moved"
    assert edit.end <= site.absolute + site.size, "the write ran into the next item"

    too_long = dict(original_words)
    too_long[site.line_id] = (*([0x100] * (site.size // 2)), words_of(original)[-1])
    with pytest.raises(ReinsertRefused, match="over"):
        plan(archive, walk_reader, too_long, in_place=True)


def test_the_blank_cell_after_a_newline_is_the_authoring_tools_indent_not_a_guard(
    archive: Archive, walk_reader
):
    """`research/text-format.md`: the `0x0000` after every `0x8001` is a one-cell indent.

    `boku.layout` leaves it out of English by default, and that decision rests on this
    claim, so the claim is counted against the shipped data rather than quoted. The note
    says 6,010 of 6,010; reproducing both halves of that ratio is what says this walk and
    the research are looking at the same thing. *Why* it is an indent rather than a guard
    is not visible in the data at all — it is `dialog_draw` resuming at the word and
    handing it to `glyph_draw` like any other cell, read in the research.
    """
    followed = 0
    total = 0
    for site in walk_reader.sites:
        if not site.kind.startswith("MSG"):
            continue
        words = words_of(walk_reader.raw(archive, site))
        for index, word in enumerate(words[:-1]):
            if word == NEWLINE_WORD:
                total += 1
                followed += words[index + 1] == PAD_WORD
    assert (followed, total) == (NEWLINES_ON_THE_DISC, NEWLINES_ON_THE_DISC)
