"""`TXT-04`'s build, against the real dump: the four things the trial has to be.

1. every sector it wrote carries EDC and ECC that match its own bytes;
2. the image differs from its source *only* in the sectors the manifest names, and inside
   those only below the EDC -- no sync pattern, header or subheader was rewritten;
3. the filesystem still reads the same, so nothing moved;
4. asking for no change produces a byte-identical image.

Three builds, one copy of the image each. They skip without a dump (`conftest.py`).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from boku import trial as trial_module
from boku.arrays import ArrayError
from boku.disc import RAW_SECTOR_SIZE, USER_DATA_OFFSET, DiscImage
from boku.events import EventError
from boku.text import MESSAGE_KINDS, GlyphTable, SiteError, TextError
from boku.trial import (
    BAND_PATCH,
    RENDERER_PATCH,
    TRIAL_TEXT,
    TrialRefused,
    build_trial,
    main_trial,
    patch_words,
    verify_written_sectors,
)

TRIAL_LINE = "E0006.0"
"""Any event message with room for the 26 bytes of "Hello, Boku!"; a test checks it has."""


@pytest.fixture(scope="module")
def patched(real_image: Path, tmp_path_factory):
    """One build with everything asked for: the words, the band, markers, and one line."""
    return build_trial(
        source=real_image,
        out_dir=tmp_path_factory.mktemp("trial"),
        line=TRIAL_LINE,
        markers=True,
    )


@pytest.fixture(scope="module")
def manifest(patched) -> dict:
    return json.loads(patched.manifest.read_text(encoding="utf-8"))


def differing_sectors(left: Path, right: Path) -> dict[int, tuple[bytes, bytes]]:
    """Every sector where two images differ, as (old, new) raw bytes."""
    out: dict[int, tuple[bytes, bytes]] = {}
    chunk = 512 * RAW_SECTOR_SIZE
    with left.open("rb") as a, right.open("rb") as b:
        lba = 0
        while (block_a := a.read(chunk)) and (block_b := b.read(chunk)):
            assert len(block_a) == len(block_b), "the trial changed the image's length"
            if block_a != block_b:
                for i in range(len(block_a) // RAW_SECTOR_SIZE):
                    start = i * RAW_SECTOR_SIZE
                    one = block_a[start : start + RAW_SECTOR_SIZE]
                    other = block_b[start : start + RAW_SECTOR_SIZE]
                    if one != other:
                        out[lba + i] = (one, other)
            lba += len(block_a) // RAW_SECTOR_SIZE
    return out


# --- gate 1 -------------------------------------------------------------------------------


def test_every_sector_the_build_wrote_carries_the_right_edc_and_ecc(patched):
    assert patched.sectors, "the build wrote nothing; there is no gate here"
    assert verify_written_sectors(patched.image, patched.sectors) == []


# --- gate 2 -------------------------------------------------------------------------------


def test_the_image_differs_only_where_the_manifest_says_and_only_below_the_edc(
    patched, manifest, real_image: Path
):
    """Both directions: no undeclared sector moved, and no declared sector stayed put.

    `PIPE-04` keeps every LBA where it was, so a sector's first 24 bytes -- sync pattern,
    address header and the subheader written twice -- must come through untouched; only
    user data and the fields computed from it may move.
    """
    differing = differing_sectors(real_image, patched.image)
    assert set(differing) == {record.lba for record in patched.sectors}
    assert set(differing) == {record["lba"] for record in manifest["sectors"]}
    for lba, (old, new) in differing.items():
        assert old[:USER_DATA_OFFSET] == new[:USER_DATA_OFFSET], f"sector {lba} was restructured"
        assert old[USER_DATA_OFFSET:] != new[USER_DATA_OFFSET:]


def test_the_manifest_records_what_each_sector_was_and_became(patched, manifest, real_image: Path):
    differing = differing_sectors(real_image, patched.image)
    for record in manifest["sectors"]:
        old, new = differing[record["lba"]]
        assert record["old_sha1"] == hashlib.sha1(old).hexdigest()
        assert record["new_sha1"] == hashlib.sha1(new).hexdigest()
        assert record["file"] in ("SCPS_100.88", "BOKU.BIN")
    assert manifest["source_sha1"] != manifest["result_sha1"]


# --- gate 3 -------------------------------------------------------------------------------


def test_the_filesystem_reads_exactly_the_same_after_the_build(patched, real_image: Path):
    def listing(path: Path):
        with DiscImage(path) as image:
            return [(e.path, e.lba, e.size, e.is_dir, e.flags) for e in image.walk()]

    before = listing(real_image)
    assert before, "walking the source found nothing"
    assert listing(patched.image) == before


# --- gate 4 -------------------------------------------------------------------------------


def test_asking_for_nothing_produces_a_byte_identical_image(real_image: Path, tmp_path_factory):
    result = build_trial(
        source=real_image, out_dir=tmp_path_factory.mktemp("null"), renderer_patch=False
    )
    assert result.sectors == []
    assert result.source_sha1 == result.result_sha1
    assert differing_sectors(real_image, result.image) == {}
    assert json.loads(result.manifest.read_text(encoding="utf-8"))["sectors"] == []


# --- what the build actually wrote -----------------------------------------------------------


def test_every_patched_word_moved_and_nothing_around_it_did(patched, real_image: Path):
    """The old bytes were there, the new ones are, and no neighbouring instruction moved.

    The window is each word plus sixteen bytes either side, and what may differ inside it
    is derived from the patch itself -- only the bytes where old and new disagree, which
    for the direction word is one byte of the four.
    """
    words = patched.words
    assert len(words) == len(RENDERER_PATCH) + len(BAND_PATCH)
    with DiscImage(real_image) as source, DiscImage(patched.image) as trial:
        lba = next(e.lba for e in trial.walk() if e.path == "/SCPS_100.88")
        for word in words:
            assert source.read_file_bytes(lba, word.file_offset, len(word.old)) == word.old
            assert trial.read_file_bytes(lba, word.file_offset, len(word.new)) == word.new
        changed: set[int] = set()
        for word in words:
            low = word.file_offset - 16
            span = len(word.old) + 32
            before = source.read_file_bytes(lba, low, span)
            after = trial.read_file_bytes(lba, low, span)
            changed |= {low + i for i in range(span) if before[i] != after[i]}
    assert changed == {
        word.file_offset + i
        for word in words
        for i in range(len(word.old))
        if word.old[i] != word.new[i]
    }


def test_the_band_replaces_the_text_origin_rather_than_adding_a_second_one():
    """Two words may not both write `SCPS_100.88`+0x1d7c8; the second would be refused."""
    without = patch_words(renderer_patch=True, band=False)
    with_band = patch_words(renderer_patch=True, band=True)
    assert without == RENDERER_PATCH
    assert patch_words(renderer_patch=False, band=False) == ()
    offsets = [word.file_offset for word in with_band]
    assert len(offsets) == len(set(offsets)), offsets
    assert set(offsets) == {word.file_offset for word in RENDERER_PATCH} | {
        word.file_offset for word in BAND_PATCH
    }
    # Only the first baseline differs between the two, and it moves into the band.
    assert [word for word in with_band if word not in without] == [
        word for word in with_band if word.file_offset == 0x1D7C8
    ] + list(BAND_PATCH)


def test_a_band_without_the_renderer_patch_is_refused(real_image: Path, tmp_path_factory):
    out = tmp_path_factory.mktemp("band-alone")
    with pytest.raises(TrialRefused, match="--no-band"):
        build_trial(source=real_image, out_dir=out, renderer_patch=False, band=True)
    assert not (out / "image.img").exists()


def test_building_over_an_already_patched_image_is_refused(patched, tmp_path_factory):
    """The old bytes are gone, so the recipe no longer describes this image."""
    with pytest.raises(TrialRefused, match="already patched"):
        build_trial(source=patched.image, out_dir=tmp_path_factory.mktemp("again"))


def test_every_physical_copy_of_the_chosen_line_now_reads_the_english(patched, site_index):
    glyphs = GlyphTable.load()
    copies = site_index.copies_of(TRIAL_LINE)
    assert len(copies) > 1, f"{TRIAL_LINE} has one copy; pick a line that exercises the fan-out"
    assert patched.line_copies == len(copies)
    with DiscImage(patched.image) as image:
        lbas = {entry.name: entry.lba for entry in image.walk() if not entry.is_dir}
        for placed in copies:
            found = image.read_file_bytes(
                lbas[placed.file_name], placed.file_offset, placed.site.size
            )
            assert found == glyphs.message(TRIAL_TEXT, placed.site.size)


def test_the_markers_tag_the_event_messages_that_can_hold_their_own_id(patched, site_index):
    glyphs = GlyphTable.load()
    events = list(site_index.event_messages())
    claimed = {(copy.file_name, copy.file_offset) for copy in site_index.copies_of(TRIAL_LINE)}
    assert patched.markers_written + patched.markers_too_small + patched.markers_superseded == len(
        events
    )
    assert patched.markers_written > 1000

    def fits(entry) -> bool:
        """Ask the one authority on what fits, rather than restating its arithmetic here.

        `GlyphTable.message` decides whether a string plus its terminator fits a site.
        A copy of that rule in the build loop and a second copy here would agree with
        each other and with nothing else; both call it instead.
        """
        try:
            glyphs.message(entry.line_id, entry.site.size)
        except TextError:
            return False
        return True

    superseded = [e for e in events if (e.file_name, e.file_offset) in claimed]
    too_small = [e for e in events if e not in superseded and not fits(e)]
    assert 0 < len(too_small) < len(events), "a marker run with no rejects gates nothing"
    assert patched.markers_too_small == len(too_small)
    assert patched.markers_superseded == len(superseded)

    chosen = next(e for e in events if fits(e) and e not in superseded)
    with DiscImage(patched.image) as image:
        lbas = {entry.name: entry.lba for entry in image.walk() if not entry.is_dir}
        found = image.read_file_bytes(lbas[chosen.file_name], chosen.file_offset, chosen.site.size)
    assert found == glyphs.message(chosen.line_id, chosen.site.size)


def test_a_line_that_is_not_a_message_is_refused_before_anything_is_copied(
    real_image: Path, tmp_path_factory, site_index
):
    """An array item is delimited by its terminator, so an early one would move its neighbours.

    The site is picked out of the walk rather than named here, so this stays true as the
    walk changes.
    """
    array_site = next(e for e in site_index.placed if e.site.kind not in MESSAGE_KINDS)
    out = tmp_path_factory.mktemp("refused")
    with pytest.raises(TrialRefused, match="only message sites"):
        build_trial(source=real_image, out_dir=out, line=array_site.line_id)
    assert not (out / "image.img").exists(), "the image was copied before the refusal"


# --- what a refusal and a crash leave behind ---------------------------------------------


def test_a_failure_part_way_through_leaves_the_previous_build_whole(
    real_image: Path, tmp_path_factory, monkeypatch
):
    """The harm: this run's half-patched image beside the last run's manifest.

    The build writes the EXE words first and the text sites after, so a failure between
    them used to leave `image.img` patched, `manifest.json` describing the *previous*
    build, and no way to tell from the directory which was which -- while every gate that
    reads the manifest still passed. The failure is injected at exactly that point.
    """
    out = tmp_path_factory.mktemp("atomic")
    first = build_trial(source=real_image, out_dir=out, band=False)
    kept = json.loads(first.manifest.read_text(encoding="utf-8"))

    def explode(*args, **kwargs):
        raise RuntimeError("disc went away mid-build")

    monkeypatch.setattr(trial_module, "_write_site", explode)
    with pytest.raises(RuntimeError, match="mid-build"):
        build_trial(source=real_image, out_dir=out, line=TRIAL_LINE)

    after = json.loads(first.manifest.read_text(encoding="utf-8"))
    assert after == kept, "the manifest is not the one describing the image beside it"
    assert trial_module.sha1_of(first.image) == kept["result_sha1"]
    leftovers = [p.name for p in out.parent.iterdir() if p.name.startswith(f".{out.name}.")]
    assert leftovers == [], "the staging directory was left behind"


def test_the_trial_refuses_to_write_where_the_import_lives(real_image: Path, tmp_path_factory):
    """`boku trial --out disc` would overwrite the one file a contributor cannot rebuild."""
    source_dir = real_image.resolve().parent
    with pytest.raises(TrialRefused, match="holds the image this build reads"):
        build_trial(source=real_image, out_dir=source_dir)
    with pytest.raises(TrialRefused, match="holds the image this build reads"):
        build_trial(source=real_image, out_dir=source_dir / "trial")
    with pytest.raises(TrialRefused, match="contains"):
        build_trial(source=real_image, out_dir=source_dir.parent)
    assert not (source_dir / "trial").exists()


def test_the_import_guard_does_not_rest_on_the_caller_having_resolved_the_path(tmp_path):
    """Two spellings of one directory are not relative to each other until both resolve.

    This is how the guard first failed: `/tmp` is a symlink to `/private/tmp` on macOS,
    so `--out /tmp/x/trial` against a source under `/private/tmp/x` looked unrelated and
    the build was allowed. Nothing here touches a real image -- the check reads paths.
    """
    (tmp_path / "real").mkdir()
    source = tmp_path / "real" / "image.img"
    source.write_bytes(b"")
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(TrialRefused, match="holds the image this build reads"):
        trial_module._check_out_dir(link / "trial", source)


def test_an_out_dir_that_is_not_a_previous_trial_is_refused(real_image: Path, tmp_path_factory):
    """The import step's rule, reused: a directory with someone's files in it stays theirs."""
    out = tmp_path_factory.mktemp("someone-elses")
    (out / "thesis.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(TrialRefused, match="not a previous trial"):
        build_trial(source=real_image, out_dir=out)
    assert (out / "thesis.txt").read_text(encoding="utf-8") == "mine"


def test_the_command_prints_a_sentence_where_it_used_to_raise(
    real_image: Path, tmp_path_factory, monkeypatch, capsys
):
    """A refusal and an OSError both reach the contributor as one line, not a traceback."""
    into_the_import = real_image.resolve().parent
    assert main_trial(str(real_image), into_the_import, None, TRIAL_TEXT, False, True, None) == 1
    assert "boku trial:" in capsys.readouterr().out

    def same_file(*args, **kwargs):
        raise shutil.SameFileError("'a' and 'b' are the same file")

    monkeypatch.setattr(trial_module.shutil, "copyfile", same_file)
    out = tmp_path_factory.mktemp("oserror")
    assert main_trial(str(real_image), out, None, TRIAL_TEXT, False, True, None) == 1
    assert "are the same file" in capsys.readouterr().out


# --- what a refusal looks like to the caller ------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        EventError("E0171 copies differ in entries 0-2"),
        ArrayError("exe@80046214: the walk ran off the end of SCPS_100.88"),
        SiteError("3 logical lines have physical copies that differ in bytes"),
    ],
)
def test_a_refusal_from_the_walk_is_a_sentence_and_not_a_traceback(error, tmp_path, monkeypatch):
    """`--line` walks the whole import, so it can refuse for any reason `boku extract` can.

    `main_trial` caught only the archive's and the glyph sheet's exceptions, so a block
    that did not decode or an array whose reader and bytes disagreed reached the
    contributor as a traceback.
    """

    def refuse(_disc_dir):
        raise error

    monkeypatch.setattr(trial_module.SiteIndex, "from_disc", staticmethod(refuse))
    # The source gets a directory of its own: `--out` beside the image is refused before
    # the walk is ever reached, which would leave this test proving nothing.
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "image.img"
    source.write_bytes(bytes(RAW_SECTOR_SIZE))
    printed: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a))))
    out = tmp_path / "out"
    assert trial_module.main_trial(str(source), out, "E0171.0", "x", False, True, None) == 1
    assert printed and printed[0].startswith("boku trial: ")
    assert str(error) in printed[0], printed
    assert not out.exists()
