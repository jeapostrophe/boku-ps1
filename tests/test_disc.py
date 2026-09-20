"""Sector and ISO 9660 reading, against images the test builds itself (no disc needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from boku import disc
from boku.disc import DiscError, DiscImage
from tests import synth


def write_image(tmp_path: Path, children: list, name: str = "test.img") -> Path:
    path = tmp_path / name
    path.write_bytes(synth.build_image(children))
    return path


@pytest.fixture
def small_tree() -> list:
    """A layout with the three shapes that matter: partial last sector, empty, Form 2."""
    return [
        synth.File("HELLO.TXT", b"hello, natsuyasumi\n"),
        synth.File("BIG.BIN", bytes(range(256)) * 24),  # 6144 bytes: exactly 3 sectors
        synth.File("ODD.BIN", b"\xa5" * 5000),  # 3 sectors, last one part-full
        synth.File("EMPTY.DAT", b""),
        synth.Directory(
            "__STR",
            [
                synth.File("M00.IKI", b"\x11" * 7000, form=2, interleaved=True),
                synth.File("BOKU_XA.XAM", b"\x22" * 3000, form=2),
            ],
        ),
    ]


@pytest.mark.parametrize(
    "lba",
    # Both carries: frame -> second at 74/75, second -> minute at 4499/4500, and one
    # address past both (a real disc runs to ~280,000 sectors).
    [0, 1, 74, 75, 149, 150, 4499, 4500, 4574, 4575, 269_999],
)
def test_sector_header_address_decodes_to_the_sector_it_names(lba):
    """The BCD minute/second/frame in a header must decode back to that sector's LBA.

    This is the only independent check that a sector was read from where it was asked
    for; every offset in this reader is derived from it. It parses single synthesised
    sectors rather than reading an image, so no case can be skipped for being past the
    end of a small fixture.
    """
    assert disc.parse_sector(synth.raw_sector(lba, b""), lba).header_lba == lba


def test_form_and_data_size_follow_the_submode_bit(tmp_path, small_tree):
    image_path = write_image(tmp_path, small_tree)
    with DiscImage(image_path) as image:
        entries = {entry.path: entry for entry in image.walk()}
        form1 = image.read_sector(entries["/HELLO.TXT"].lba)
        form2 = image.read_sector(entries["/__STR/M00.IKI"].lba)
    assert form1.form == 1
    assert len(form1.data) == disc.FORM1_DATA_SIZE
    assert not form1.subheader.submode & disc.SUBMODE_FORM2
    assert form2.form == 2
    assert len(form2.data) == disc.FORM2_DATA_SIZE
    assert form2.subheader.is_audio


def test_walk_finds_exactly_the_tree_that_was_laid_out(tmp_path, small_tree):
    """Every entry, with its path, size and kind, against the layout the writer was given."""
    image_path = write_image(tmp_path, small_tree)
    expected = {
        "/HELLO.TXT": (False, len(small_tree[0].content)),
        "/BIG.BIN": (False, len(small_tree[1].content)),
        "/ODD.BIN": (False, len(small_tree[2].content)),
        "/EMPTY.DAT": (False, 0),
        "/__STR": (True, None),
        "/__STR/M00.IKI": (False, synth.recorded_size(small_tree[4].children[0])),
        "/__STR/BOKU_XA.XAM": (False, synth.recorded_size(small_tree[4].children[1])),
    }
    with DiscImage(image_path) as image:
        found = {entry.path: (entry.is_dir, entry.size) for entry in image.walk()}
    assert set(found) == set(expected)
    for path, (is_dir, size) in expected.items():
        assert found[path][0] is is_dir, path
        if size is not None:
            assert found[path][1] == size, path


def test_walk_crosses_a_directory_extent_that_spans_sectors(tmp_path):
    """A directory bigger than one sector must not stop at the first zero length byte."""
    many = [synth.File(f"F{index:04d}.BIN", bytes([index & 0xFF]) * 16) for index in range(120)]
    image_path = write_image(tmp_path, list(many))
    with DiscImage(image_path) as image:
        pvd = image.primary_volume_descriptor()
        found = [entry.path for entry in image.walk()]
    assert pvd.root_size > disc.FORM1_DATA_SIZE, "fixture no longer spans sectors"
    assert found == [f"/{entry.name}" for entry in many]


def test_read_file_returns_the_bytes_that_were_laid_out(tmp_path, small_tree):
    """Including a file whose last sector is only part full, and an empty one."""
    image_path = write_image(tmp_path, small_tree)
    with DiscImage(image_path) as image:
        entries = {entry.path: entry for entry in image.walk()}
        for source in small_tree[:4]:
            entry = entries[f"/{source.name}"]
            assert image.read_file(entry.lba, entry.size) == source.content, source.name


def test_read_file_refuses_form2_naming_the_sector(tmp_path, small_tree):
    """A cooked 2048-byte read of XA/STR data is garbage, so it must not silently happen."""
    image_path = write_image(tmp_path, small_tree)
    with DiscImage(image_path) as image:
        entry = next(e for e in image.walk() if e.path == "/__STR/M00.IKI")
        with pytest.raises(DiscError, match=r"Form 2"):
            image.read_file(entry.lba, entry.size)


def test_xa_attributes_carry_form_and_interleaving(tmp_path, small_tree):
    image_path = write_image(tmp_path, small_tree)
    with DiscImage(image_path) as image:
        entries = {entry.path: entry for entry in image.walk()}
    cooked = entries["/HELLO.TXT"].xa
    interleaved = entries["/__STR/M00.IKI"].xa
    assert cooked is not None and interleaved is not None
    assert cooked.form == 1 and not cooked.interleaved
    assert "form1" in cooked.flag_names()
    assert interleaved.form == 2 and interleaved.interleaved
    assert entries["/__STR"].xa is not None and entries["/__STR"].xa.directory


def test_a_damaged_sync_pattern_is_reported_with_the_sector(tmp_path, small_tree):
    image_path = write_image(tmp_path, small_tree)
    raw = bytearray(image_path.read_bytes())
    target = 20 * disc.RAW_SECTOR_SIZE
    raw[target : target + 12] = b"\x00" * 12
    image_path.write_bytes(raw)
    with DiscImage(image_path) as image, pytest.raises(DiscError, match=r"sector 20: sync"):
        image.read_sector(20)


def test_an_image_that_is_not_whole_sectors_is_refused(tmp_path, small_tree):
    image_path = write_image(tmp_path, small_tree)
    image_path.write_bytes(image_path.read_bytes() + b"\x00" * 7)
    with pytest.raises(DiscError, match=r"7 bytes over"):
        DiscImage(image_path)


def test_reading_past_the_end_of_the_image_is_refused(tmp_path, small_tree):
    image_path = write_image(tmp_path, small_tree)
    with DiscImage(image_path) as image, pytest.raises(DiscError, match=r"outside the image"):
        image.read_sector(image.sector_count)


def test_version_suffix_is_stripped_but_a_dotted_name_is_kept(tmp_path):
    """`SCPS_100.88;1` is a name with two dots and a version -- only the version goes."""
    image_path = write_image(tmp_path, [synth.File("SCPS_100.88", b"PS-X EXE")])
    with DiscImage(image_path) as image:
        names = [entry.name for entry in image.walk()]
    assert names == ["SCPS_100.88"]
