"""`TXT-05` + `PIPE-03`/`PIPE-04` together, on the real dump and the real days build.

The two halves that used to be separate artefacts meet here: `tools/vwf/build_prototype.py`
assembles the renderer and writes its byte edits, and `boku build` applies them beside a
translation that *grows*. What is asked of that pair:

1. **The edit set describes this dump.** Every `old` range it carries is what the image
   holds, checked before the 660 MB copy exists -- which is the only thing standing
   between a stale `edits.json` and a corrupted executable.
2. **The renderer and the translation do not write over each other.** A rebuilt member's
   edit covers its whole byte range, so a font-sheet or overlay patch aimed inside one
   would be silently lost; the build's own `check_disjoint` is asserted to have run.
3. **The built image says what it is.** The filesystem is unchanged, the length is
   unchanged, every written sector carries fresh EDC/ECC, and the renderer's new bytes
   are really there.
4. **Every line came back.** The built image is read again through the game's own
   addressing -- `g_cd_dir` and the `.SEC` records, which a relocation rewrites -- and
   every line the build says it wrote holds the words it laid out, at **every copy**,
   while every line it did not write is byte-identical to the import.

Everything skips cleanly without `disc/` or without `build/days/`; the repo ships neither.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boku import exchange_notebook
from boku.archive import ARCHIVE_NAME, EXE_LOAD_BIAS, EXE_NAME, Archive, overlay_read_end_of
from boku.arrays import (
    ARRAYS,
    CODE_LABELS,
    SAVE_TITLE_LINE_ID,
    SAVE_TITLE_PARTS_ADDR,
    CodeLabel,
    locate,
    read_code_labels,
)
from boku.build import (
    EditSet,
    check_before_writing,
    check_resident,
    load_edit_set,
    verify_written_sectors,
)
from boku.code_text import BANNERS, DATE_LABELS, drawer_of, lay_out_code_label
from boku.disc import DiscImage
from boku.glyphs import words_of
from boku.importer import IMAGE_SIZE
from boku.insect_box import is_copy
from boku.reinsert import check_disjoint
from boku.relocate import MOVIE_BLOCK_RESERVE
from boku.sites import RESIDENT_BLOCK_ADDRS, Walk, resident_block_at
from boku.translation import SampleScenes
from tests.test_real_reinsert import FILESYSTEM_ENTRIES, read_back

REPO_ROOT = Path(__file__).resolve().parent.parent
EDITS = REPO_ROOT / "build" / "vwf" / "edits.json"
DAYS_DIR = REPO_ROOT / "build" / "days"

BUILD_COMMAND = "./make.sh build-days"
ARRAYS_TXT = REPO_ROOT / "translation" / "days" / "arrays.txt"

CODE_LABEL_IDS = frozenset(CodeLabel(image, fn, (), (), "").line_id for image, fn, _ in CODE_LABELS)
PLACED_IN_CODE = CODE_LABEL_IDS | {SAVE_TITLE_LINE_ID}
"""Written lines with no text site: `boku.code_text` places them, and the tests below read
them back through the code that draws them."""


@pytest.fixture(scope="module")
def edit_set() -> EditSet:
    if not EDITS.is_file():
        pytest.skip(
            f"no {EDITS.relative_to(REPO_ROOT)}: run "
            f"`uv run python tools/vwf/build_prototype.py --edits-only` (it needs armips). "
            f"The repo ships no built font."
        )
    return load_edit_set(EDITS)


@pytest.fixture(scope="module")
def days_manifest() -> dict:
    manifest = DAYS_DIR / "manifest.json"
    if not manifest.is_file():
        pytest.skip(f"no {manifest.relative_to(REPO_ROOT)}: run `{BUILD_COMMAND}` first")
    return json.loads(manifest.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def days_image() -> Path:
    image = DAYS_DIR / "image.img"
    if not image.is_file():
        pytest.skip(f"no {image.relative_to(REPO_ROOT)}: run `{BUILD_COMMAND}` first")
    return image


@pytest.fixture(scope="module")
def days_read_back(days_image: Path) -> tuple[Archive, Walk]:
    """The built image walked again, as if it were an import of its own."""
    return read_back(days_image)


# --- the edit set against the dump ---------------------------------------------------------------


def test_every_old_range_the_renderer_patch_carries_is_what_the_image_holds(
    edit_set: EditSet, real_image: Path, tmp_path
):
    """`verify_edits`, run over the renderer patch with nothing written.

    This is the check that makes the font build and the image build safe to be separate
    programs: the edit set names the bytes it expects, so a patch assembled against a
    different dump, or one already applied, is a refusal here and not a boot loop.
    """
    check_before_writing(real_image, tmp_path / "out", edit_set.edits, what="vwf-verify")


def test_no_executable_byte_the_renderer_patch_writes_is_under_an_overlay_load(
    edit_set: EditSet, archive: Archive
):
    """Resident means below the overlay region (research/text-renderer.md § 6): a table in
    the heap raise was zeroed by the first bug-sumo match. `check_resident` refuses the
    whole region only because the furthest load reaches past the executable's end, which
    is asserted here rather than assumed."""
    assert overlay_read_end_of(archive.exe) >= EXE_LOAD_BIAS + len(archive.exe)
    check_resident(edit_set.edits)


def test_the_renderer_patch_writes_only_the_two_files_a_patch_may_write(edit_set: EditSet):
    assert {edit.file for edit in edit_set.edits} <= {EXE_NAME, ARCHIVE_NAME}
    check_disjoint(list(edit_set.edits))


def test_the_patch_installs_the_font_its_own_cell_map_measures(edit_set: EditSet):
    """The widths English is wrapped to are the bytes the executable will step by.

    Not a comparison of two copies of one number: the advance table is read back **out of
    the `SCPS_100.88` edits themselves**, at the file offset its own `table.ram` implies,
    so a misplaced `vwf_advance` symbol, a short table or an edit that does not reach it
    fails here. Measuring English in one font and drawing it in another is invisible
    until it is on screen.
    """
    from boku.archive import EXE_LOAD_BIAS

    table = int(edit_set.document["table"]["ram"], 16) - EXE_LOAD_BIAS
    installed: dict[int, int] = {}
    for edit in edit_set.edits:
        if edit.file == EXE_NAME:
            installed.update(dict(enumerate(edit.new, start=edit.offset)))
    encoder = edit_set.encoder
    for character, cell in encoder.cells.items():
        glyph, advance = cell
        assert installed.get(table + glyph) == advance, (
            f"{character!r} advances {advance} px in the cell map, and the table this "
            f"patch installs says {installed.get(table + glyph)} at cell {glyph}"
        )


def test_a_patch_and_a_relocation_are_measured_in_the_same_frame(archive: Archive):
    """The guard is only real if `Archive.base_lba` and a `SectorEdit`'s `lba` agree.

    Both numbers are taken from the archive itself rather than chosen: the member's own
    `lba` is what a relocation reports, and `base_lba + offset // SECTOR` is what the
    guard computes from the patch. Asserting they are equal is the whole content of the
    check — if `relocate` ever emitted a `BOKU.BIN`-relative LBA, the guard would go
    permanently silent and a hand-written fixture would not notice.
    """
    from boku.archive import SECTOR
    from boku.build import check_no_sector_clash
    from boku.reinsert import ByteEdit
    from boku.relocate import SectorEdit

    member = archive.member("ONMEM.BIN")
    assert archive.base_lba + member.offset // SECTOR == member.lba, (
        "the guard's arithmetic and the member's own LBA are in different frames"
    )
    patch = ByteEdit(
        file=ARCHIVE_NAME,
        offset=member.offset,
        old=bytes(4),
        new=b"\1\1\1\1",
        reason="VWF font sheet",
    )
    moved = SectorEdit(
        lba=member.lba,
        old=bytes(SECTOR),
        new=b"\2" * SECTOR,
        reason=f"{member.short_name} moved",
    )
    with pytest.raises(Exception, match="a relocation also writes"):
        check_no_sector_clash([patch], [moved], archive)
    # One sector past the patch's own, and the same pair is not a clash -- which is what
    # says the comparison is about this sector and not about BOKU.BIN in general.
    clear = SectorEdit(
        lba=member.lba + 1, old=bytes(SECTOR), new=b"\2" * SECTOR, reason="something else"
    )
    check_no_sector_clash([patch], [clear], archive)


def test_asking_for_a_vwf_build_and_giving_it_nothing_applies_nothing(
    real_image: Path, disc_dir: Path, tmp_path
):
    """The null build stays null: no translation and no patches means no edit at all.

    The byte-identical *image* is pinned, more strongly and over the same `write_image`
    call, by `tests/test_trial.py::test_asking_for_nothing_produces_a_byte_identical_image`
    and `tests/test_real_reinsert.py::test_the_round_trip_build_reproduces_the_image_byte_for_byte`,
    which diff every sector; repeating the 660 MB copy and its two digests here would buy
    nothing. What is new in this unit, and what this asserts, is that the `--vwf` path
    adds no edit when it was not asked for.
    """
    from boku.build import build

    result = build(
        source=real_image,
        out_dir=tmp_path / "null",
        disc_dir=disc_dir,
        name="null",
        dry_run=True,
    )
    assert result.binary_patches == ()
    assert result.plan is None
    assert not (tmp_path / "null").exists()


# --- what the days build wrote --------------------------------------------------------------------


def test_the_days_build_applied_the_renderer_patch_and_a_translation(days_manifest: dict):
    assert days_manifest["encoder"].startswith("cell map"), days_manifest["encoder"]
    assert days_manifest["binary_patches"], "no renderer patch went into this image"
    assert days_manifest["lines_written"], "no line went into this image"
    assert days_manifest["members_rebuilt"], "nothing grew; --skip-unfitted dropped everything"


def test_the_built_image_is_the_same_length_and_the_same_filesystem(days_image: Path):
    """`PIPE-04`: every LBA stays where it is, because the XA behind `BOKU.BIN` is addressed
    directly and PPF cannot grow an image."""
    assert days_image.stat().st_size == IMAGE_SIZE
    with DiscImage(days_image) as opened:
        assert len(list(opened.walk())) == FILESYSTEM_ENTRIES


def test_every_sector_the_days_build_wrote_carries_the_right_edc_and_ecc(
    days_image: Path, days_manifest: dict
):
    from boku.build import SectorRecord

    records = [
        SectorRecord(
            lba=row["lba"],
            file=row["file"],
            offset=int(row["offset"], 16),
            old_sha1=row["old_sha1"],
            new_sha1=row["new_sha1"],
        )
        for row in days_manifest["sectors"]
    ]
    assert records, "the manifest lists no sector; this gate would pass over nothing"
    assert verify_written_sectors(days_image, records) == []


def test_the_renderer_patch_is_really_in_the_built_image(
    days_image: Path, days_read_back: tuple[Archive, Walk], archive: Archive, edit_set: EditSet
):
    """The `new` bytes, read back out of the image: the executable's through its own
    filesystem, an overlay's through the member it patches, wherever the build put that
    member (one grown by an overlay tail moves)."""
    built, _ = days_read_back
    with DiscImage(days_image) as opened:
        entries = {entry.name: entry for entry in opened.walk() if not entry.is_dir}
        for edit in edit_set.edits:
            member = archive.owner(edit.offset) if edit.file == ARCHIVE_NAME else None
            if member is None:
                entry = entries[edit.file]
                found = opened.read_file_bytes(entry.lba, edit.offset, len(edit.new))
            else:
                at = edit.offset - member.offset
                found = built.blob(built.member(member.short_name))[at : at + len(edit.new)]
            assert found == edit.new, f"{edit.reason} is not in the built image"


def test_the_days_build_carries_the_movie_block_where_no_relocation_went(
    days_image: Path, days_manifest: dict, edit_set: EditSet
):
    """`FMV-04`: the edit set's one sector write -- the cue block the movie hooks read -- is
    in the image at the LBA the executable was assembled to read, and not one relocated
    member was given a sector of its reserve."""
    (block,) = edit_set.sectors
    assert [(row["lba"], row["sectors"]) for row in days_manifest["sector_patches"]] == [
        (block.lba, block.sectors)
    ]
    assert days_manifest["relocations"], "nothing relocated; the reserve was never at risk"
    for moved in days_manifest["relocations"]:
        home = range(moved["to_lba"], moved["to_lba"] + moved["sectors"])
        assert not set(home) & set(range(MOVIE_BLOCK_RESERVE.start, MOVIE_BLOCK_RESERVE.end)), (
            f"{moved['member']} was placed at {moved['to_lba']}, inside the movie block's reserve"
        )
    with DiscImage(days_image) as opened:
        assert opened.read_form1_span(block.lba, block.sectors) == block.new


# --- every line, at every copy ------------------------------------------------------------------


def test_every_written_line_reads_back_as_the_words_the_build_laid_out(
    days_read_back: tuple[Archive, Walk], days_manifest: dict, archive: Archive, walk_reader
):
    """The gate this whole unit exists for, and it is read through the game's addressing.

    `read_back` resolves members from the built image the way `cd_load_sync` does -- the
    `g_cd_dir` words and the `.SEC` records, both of which a relocation rewrites -- so a
    member written to the right sectors but addressed from the wrong ones fails here. A
    line is checked at **every** physical copy: which copy the game reaches is not known
    statically, and a half-written line is the one defect the id scheme cannot survive.
    """
    built, built_walk = days_read_back
    written = set(days_manifest["lines_written"])
    assert written, "nothing was written; this gate would pass over nothing"
    changed = 0
    for line_id in sorted(written - PLACED_IN_CODE):
        if exchange_notebook.is_variant(line_id):
            continue  # no text site: read back through its drawer, tests/test_real_sumo_text.py
        sites = built_walk.by_line.get(line_id)
        assert sites, f"{line_id} is not a line of the built image"
        if line_id in walk_reader.voice_only:
            # A subtitle (PLAN VO-02) fills an entry the import leaves null, at every copy.
            assert len(sites) == len(walk_reader.voice_only[line_id]), (
                f"{line_id}'s subtitle reached {len(sites)} of "
                f"{len(walk_reader.voice_only[line_id])} copies"
            )
            was = set()
        else:
            was = {
                words_of(walk_reader.raw(archive, site)) for site in walk_reader.by_line[line_id]
            }
        now = {words_of(built_walk.raw(built, site)) for site in sites}
        assert len(now) == 1, f"{line_id}'s copies disagree in the built image"
        if now != was:
            changed += 1
    assert changed > len(written) // 2, (
        f"only {changed} of {len(written)} written lines differ from the Japanese; the "
        f"translation did not reach the image"
    )


def test_every_line_the_build_did_not_write_is_byte_identical_to_the_import(
    days_read_back: tuple[Archive, Walk], days_manifest: dict, archive: Archive, walk_reader
):
    """Nothing is cut and nothing is collateral: a refused line stays exactly Japanese.

    A rebuilt member re-packs every entry around the one that grew, so "the line I did not
    translate is untouched" is a claim about the *packer*, not about restraint.
    """
    built, built_walk = days_read_back
    written = set(days_manifest["lines_written"])
    untouched = [line_id for line_id in walk_reader.by_line if line_id not in written]
    assert untouched, "every line was written; this gate would pass over nothing"
    for line_id in untouched:
        was = [walk_reader.raw(archive, site) for site in walk_reader.by_line[line_id]]
        sites = built_walk.by_line.get(line_id)
        assert sites, f"{line_id} went missing from the built image"
        assert [built_walk.raw(built, site) for site in sites] == was, (
            f"{line_id} was not translated and its bytes moved anyway"
        )


def test_the_build_and_the_lint_read_the_same_marks_off_every_message(
    archive: Archive, walk_reader, disc_dir: Path
):
    """One rule, two representations of the bytes — held against each other.

    `boku.layout.original_marks` is what dresses the English, and the build and the lint
    reach it over different bytes: the build over the words the walk holds, the lint over
    what `boku.script_store.original_bytes` reconstructs from the decoded store. Every
    mark they disagree about is a run the build inserts and the lint does not charge (or
    the reverse), which is a page refused by one gate and passed by the other — silently,
    with both green. That is measured here over the whole script rather than assumed from
    `GlyphTable.encode` being `decode`'s inverse.
    """
    from boku.extract import SCRIPT_DIR_NAME
    from boku.glyphs import GlyphTable
    from boku.layout import original_marks
    from boku.script_store import load_store, original_bytes

    store = load_store(Path(disc_dir) / SCRIPT_DIR_NAME)
    table = GlyphTable.load()
    checked = 0
    seen: set[tuple[str, str, bool]] = set()
    for line_id, sites in walk_reader.by_line.items():
        record = store.lines.get(line_id)
        if record is None or not sites[0].kind.startswith("MSG"):
            continue
        ours = original_marks(walk_reader.raw(archive, sites[0]), table)
        theirs = original_marks(original_bytes(record, table), table)
        assert ours == theirs, f"{line_id}: the build reads {ours} and the lint reads {theirs}"
        checked += 1
        seen.add((ours.opening, ours.closing, ours.labelled))
    assert checked > 1000, f"only {checked} messages compared; this gate would prove little"
    # A labelled line, a bare opening and a closing mark all really occur, so the equality
    # above is over all three runs the build inserts and not over one constant answer.
    assert any(shape[2] for shape in seen), "no message is labelled; the gate is vacuous"
    assert any(shape[0] and not shape[2] for shape in seen), "no message opens bare"
    assert any(shape[1] for shape in seen), "no message closes; the closer is never charged"


def test_every_refused_line_says_which_member_and_by_how_much(days_manifest: dict):
    """A refusal is never a silent drop: it names the container and the numbers.

    README § "Who this is for" -- space problems are solved with engineering, and the
    first step is knowing which container is out of room and by how many bytes.
    """
    for line_id, problems in days_manifest["lines_refused"].items():
        assert problems, f"{line_id} was refused with no reason given"
        assert any(character.isdigit() for character in problems[0]), (
            f"{line_id}: {problems[0]!r} carries no numbers"
        )


def test_every_moved_array_is_found_where_its_readers_now_point(
    days_read_back: tuple[Archive, Walk], days_manifest: dict
):
    """`PLAN PIPE-07`: a grown array is written somewhere new and its `lui` pairs rewritten.
    The read-back walks each array from its anchor pair in the *built* code, so every
    other read-back gate here sees a moved array where the game will, and this one says
    they really moved -- not that the walk quietly read the old Japanese at the old address."""
    built, _ = days_read_back
    moved = days_manifest["arrays_moved"]
    assert moved, "the build moved no array; nothing here would be checked"
    catalogue = {array.line_id_prefix: array for array in ARRAYS}
    blocks = {f"exe@{ram:08X}": ram for ram in RESIDENT_BLOCK_ADDRS}
    hooked = {*DATE_LABELS, *BANNERS, exchange_notebook.UNIT}
    elsewhere = 0
    for entry in moved:
        to = int(entry["to"], 16)
        if entry["array"] in hooked:
            # hooked at its drawer's entry: lui t0 / j / addiu
            banner = BANNERS.get(entry["array"])
            if entry["array"] == exchange_notebook.UNIT:
                image, function = exchange_notebook.NOTEBOOK
            else:
                image, function = banner.drawer if banner else drawer_of(entry["array"])
            hook = built.image_bytes(image, function, 12)
            high = int.from_bytes(hook[0:4], "little") & 0xFFFF
            low = int.from_bytes(hook[8:12], "little") & 0xFFFF
            assert ((high << 16) + (low - 0x10000 if low & 0x8000 else low)) & 0xFFFFFFFF == to
            continue
        if is_copy(entry["array"]):  # the notebook's own pair: tests/test_insect_box.py
            continue
        if entry["array"] == SAVE_TITLE_LINE_ID:  # a pointer table, not a lui pair
            pointer = built.overlay_bytes("TITLE.OVL", SAVE_TITLE_PARTS_ADDR, 4)
            assert int.from_bytes(pointer, "little") == to, entry
            continue  # a pointer table, so it says nothing about lui pairs
        elif entry["array"] in blocks:  # an event block the executable holds
            retail = blocks[entry["array"]]
            assert resident_block_at(built, retail) == to, entry
        else:
            array = catalogue[entry["array"]]
            retail = array.ram
            tail = entry["tail"]  # an overlay's member name, or None for resident room
            image = tail.removesuffix(".OVL").lower() if tail else "exe"
            assert locate(built, array) == (image, to), entry
        elsewhere += to != retail  # a repack that still fits may be written where it was
    assert elsewhere, "every 'moved' array stayed put; the pairs were never exercised"


def test_every_written_code_label_is_drawn_from_its_new_immediates(
    days_read_back: tuple[Archive, Walk], days_manifest: dict, archive: Archive, edit_set: EditSet
):
    """`PLAN PIPE-07`: a label the code assembles from `addiu a0` immediates is placed by
    rewriting them (`boku.code_text`); read back through the same disassembly the extract
    uses, every written label's glyphs changed and every site of one drawn glyph agrees --
    two branches that load the same glyph were both rewritten."""
    built, _ = days_read_back
    written = set(days_manifest["lines_written"])
    before = {label.line_id: label for label in read_code_labels(archive)}
    after = {label.line_id: label for label in read_code_labels(built)}
    placed = [line for line in written if line in before and line not in DATE_LABELS]
    assert placed, "no code label was written; nothing here would be checked"
    # A label whose English spells its own glyphs keeps them (`/31 %`, the paren), so not
    # every one changes -- but one that draws new letters must (`W L`).
    assert any(before[line].glyph_ids != after[line].glyph_ids for line in placed)
    rows = {entry.line_id: entry for entry in SampleScenes.from_paths([ARRAYS_TXT])}
    for line in placed:
        label = after[line]
        wanted = lay_out_code_label(
            line, before[line].runs, " ".join(rows[line].pages), edit_set.encoder
        ).words
        assert label.glyph_ids == wanted, f"{line} draws {label.glyph_ids}, laid out {wanted}"
        for draw, glyph in enumerate(label.glyph_ids):
            loads = {
                value
                for (_, value), fed in zip(label.sites, label.draws, strict=True)
                if fed == draw
            }
            assert loads == {glyph}, f"{line}: glyph {draw} is loaded as {sorted(loads)}"
