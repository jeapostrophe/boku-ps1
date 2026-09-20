"""EDC and ECC, checked without a disc.

`boku.edc` is fast because it rewrites the documented byte-at-a-time loops as whole-vector
operations. That optimisation is what these tests exist to catch: each one compares the
shipped code against a transcription of the rules in
`research/ps1-translation-practice.md` §1.3, written here from the documented constants
and sharing no table, loop or constant with the module under test. The rules themselves
are pinned against the disc in `test_real_disc_edc.py`, which is the only place the
algorithm as a whole can be proved right.
"""

from __future__ import annotations

import pytest

from boku import edc
from boku.disc import DiscError, DiscWriter
from tests.rules import slow_ecc, slow_edc, some_data
from tests.synth import SUBMODE_DATA, SUBMODE_FORM2, File, build_image, raw_sector

# --- material ---------------------------------------------------------------------------


@pytest.fixture
def form1() -> bytes:
    return edc.rebuild(raw_sector(4321, some_data(7)))


# --- the module against the rules ---------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_table_driven_edc_agrees_with_the_polynomial_it_claims(seed: int):
    """Eight bytes a step and eight tables, versus one bit a step and none."""
    data = some_data(seed, 2056)
    assert edc.edc(data) == slow_edc(data)


def test_the_edc_of_a_partial_block_agrees_too():
    """2332 bytes -- Form 2's coverage -- is not a multiple of eight, so the tail runs."""
    data = some_data(11, 2332)
    assert len(data) % 8 != 0
    assert edc.edc(data) == slow_edc(data)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_vectorised_ecc_agrees_with_the_loops_the_rules_describe(seed: int):
    raw = raw_sector(1000 + seed, some_data(seed))
    assert edc.ecc(raw) == slow_ecc(raw)


# --- what a rebuild guarantees -------------------------------------------------------------


def test_a_rebuilt_sector_checks_out_and_rebuilding_again_changes_nothing(form1: bytes):
    """The fixed point a write depends on: patch, rebuild, and the sector is consistent."""
    assert edc.check_sector(form1).ok
    assert edc.rebuild(form1) == form1


def test_a_sector_whose_header_does_not_say_mode_2_is_refused(form1: bytes):
    """Every offset in `boku.edc` is Mode 2's, and a Mode 1 sector keeps none of them there.

    Mode 1 stores 2048 user bytes from 0x10, its EDC at 0x810, eight reserved zero bytes,
    then ECC computed over the *real* header. Rebuilding one as Mode 2 leaves the live
    EDC at 0x810 stale, writes four bytes into the reserved gap, and produces ECC valid
    for neither mode -- a sector that passes every check this project makes and fails in
    a drive. So the mode byte has to be read, and the harm here is shown as well as the
    refusal: the bytes the old code would have moved are named.
    """
    mode1 = bytearray(form1)
    mode1[edc.MODE_OFFSET] = 1
    with pytest.raises(ValueError, match="mode 1"):
        edc.rebuild(bytes(mode1))
    with pytest.raises(ValueError, match="mode 1"):
        edc.check_sector(bytes(mode1))
    with pytest.raises(ValueError, match="mode 1"):
        edc.set_form1_data(bytes(mode1), some_data(3))


def test_a_sector_whose_edc_or_ecc_is_stale_is_reported_as_stale(form1: bytes):
    """The checker has to be able to say no, or the disc sweep proves nothing."""
    stale = bytearray(form1)
    stale[edc.USER_DATA_OFFSET] ^= 0x01
    check = edc.check_sector(bytes(stale))
    assert check.edc_stored != check.edc_computed
    assert check.ecc_ok is False
    assert not check.ok


def test_one_changed_user_byte_moves_both_the_edc_and_the_ecc(form1: bytes):
    """Neither field may be insensitive to the data it protects."""
    nudged = bytes([form1[edc.USER_DATA_OFFSET] ^ 0x80]) + some_data(7)[1:]
    other = edc.set_form1_data(form1, nudged)
    assert (
        other[edc.FORM1_EDC_OFFSET : edc.FORM1_EDC_OFFSET + 4]
        != form1[edc.FORM1_EDC_OFFSET : edc.FORM1_EDC_OFFSET + 4]
    )
    assert other[edc.ECC_OFFSET :] != form1[edc.ECC_OFFSET :]


def test_the_header_is_outside_both_fields_and_the_subheader_is_inside_both(form1: bytes):
    """The Form 1 quirk, disc-free: ECC is computed with the 4-byte header zeroed.

    So moving a sector to another address leaves its EDC and ECC alone, while touching
    the subheader moves both. An implementation that forgot to zero the header would
    still be self-consistent -- only the disc can catch that (`test_real_disc_edc.py`) --
    but one that let the header *into* the computation fails right here.
    """
    moved = bytearray(form1)
    moved[edc.HEADER_OFFSET : edc.HEADER_OFFSET + 3] = b"\x11\x22\x33"
    assert edc.rebuild(bytes(moved))[edc.FORM1_EDC_OFFSET :] == form1[edc.FORM1_EDC_OFFSET :]

    relabelled = bytearray(form1)
    relabelled[edc.EDC_COVERAGE_START + 1] ^= 0x01  # the channel, in both subheader copies
    relabelled[edc.EDC_COVERAGE_START + 5] ^= 0x01
    assert edc.rebuild(bytes(relabelled))[edc.FORM1_EDC_OFFSET :] != form1[edc.FORM1_EDC_OFFSET :]


def test_set_form1_data_keeps_everything_but_the_user_data(form1: bytes):
    written = edc.set_form1_data(form1, some_data(99))
    assert written[: edc.USER_DATA_OFFSET] == form1[: edc.USER_DATA_OFFSET]
    assert written[edc.USER_DATA_OFFSET : edc.USER_DATA_OFFSET + 2048] == some_data(99)
    assert edc.check_sector(written).ok


def test_set_form1_data_refuses_a_form2_sector_and_a_wrong_length():
    form2 = raw_sector(50, some_data(3, 2324), submode=SUBMODE_DATA | SUBMODE_FORM2)
    with pytest.raises(ValueError, match="Form 2"):
        edc.set_form1_data(form2, some_data(3))
    with pytest.raises(ValueError, match="2048"):
        edc.set_form1_data(raw_sector(50, some_data(3)), some_data(3, 2047))


# --- Form 2: the optional field ------------------------------------------------------------


def test_a_form2_sector_that_stores_no_edc_keeps_none():
    """Zero there means "omitted", not "wrong"; rewriting must not invent a value.

    This disc stores an EDC in all 113,436 of its Form 2 sectors, so nothing on it
    exercises this path -- which is exactly why it is pinned here.
    """
    form2 = raw_sector(60, some_data(5, 2324), submode=SUBMODE_DATA | SUBMODE_FORM2)
    assert form2[edc.FORM2_EDC_OFFSET : edc.FORM2_EDC_OFFSET + 4] == bytes(4)
    assert edc.rebuild(form2) == form2
    assert edc.check_sector(form2).edc_omitted
    assert edc.check_sector(form2).ok


def test_a_form2_sector_that_stores_an_edc_gets_a_fresh_one():
    form2 = bytearray(raw_sector(61, some_data(6, 2324), submode=SUBMODE_DATA | SUBMODE_FORM2))
    form2[edc.FORM2_EDC_OFFSET : edc.FORM2_EDC_OFFSET + 4] = b"\xde\xad\xbe\xef"
    rebuilt = edc.rebuild(bytes(form2))
    assert rebuilt[edc.FORM2_EDC_OFFSET : edc.FORM2_EDC_OFFSET + 4] == slow_edc(
        bytes(form2)[0x10 : edc.FORM2_EDC_OFFSET]
    ).to_bytes(4, "little")
    # Form 2 carries no ECC: 0x81C onwards is still user data, and the EDC is the last
    # four bytes of the sector, so nothing outside those four bytes may move.
    assert rebuilt[: edc.FORM2_EDC_OFFSET] == bytes(form2)[: edc.FORM2_EDC_OFFSET]
    assert edc.FORM2_EDC_OFFSET + 4 == edc.RAW_SECTOR_SIZE
    assert edc.check_sector(rebuilt).ok


# --- the file-level writer ------------------------------------------------------------------


def consistent_image(children: list) -> bytes:
    """`synth.build_image`, with every sector's EDC/ECC made right.

    `synth` leaves both zero, which a reader does not care about. A *writer* test does:
    on an image that starts out inconsistent, "writing the same bytes back changes
    nothing" would be false for a reason that has nothing to do with the writer.
    """
    raw = bytearray(build_image(children))
    for lba in range(len(raw) // edc.RAW_SECTOR_SIZE):
        start = lba * edc.RAW_SECTOR_SIZE
        raw[start : start + edc.RAW_SECTOR_SIZE] = edc.rebuild(
            bytes(raw[start : start + edc.RAW_SECTOR_SIZE])
        )
    return bytes(raw)


@pytest.fixture
def written_image(tmp_path):
    """A four-sector file in a synthetic image, so the writer needs no disc."""
    content = b"".join(some_data(i, 2048) for i in range(4))
    path = tmp_path / "image.img"
    path.write_bytes(consistent_image([File("DATA.BIN", content)]))
    return path, content


def test_write_file_bytes_spans_sectors_and_touches_nothing_else(written_image):
    path, content = written_image
    before = path.read_bytes()
    with DiscWriter(path) as writer:
        entry = next(e for e in writer.walk() if e.path == "/DATA.BIN")
        # A range that starts inside one sector and ends inside the next.
        writes = writer.write_file_bytes(
            entry.lba, 2048 - 3, b"\x01\x02\x03\x04\x05\x06", file_size=entry.size
        )
        assert [write.lba for write in writes] == [entry.lba, entry.lba + 1]
        patched = writer.read_file_bytes(entry.lba, 0, len(content))
    expected = bytearray(content)
    expected[2045:2051] = b"\x01\x02\x03\x04\x05\x06"
    assert patched == bytes(expected)

    after = path.read_bytes()
    changed = {
        lba
        for lba in range(len(after) // 2352)
        if after[lba * 2352 : (lba + 1) * 2352] != before[lba * 2352 : (lba + 1) * 2352]
    }
    assert changed == {entry.lba, entry.lba + 1}
    for lba in changed:
        raw = after[lba * 2352 : (lba + 1) * 2352]
        assert raw[:24] == before[lba * 2352 : lba * 2352 + 24], "structure was rewritten"
        assert edc.check_sector(raw, lba).ok


def test_writing_the_same_bytes_back_writes_nothing(written_image):
    """What the null round trip rests on: an unchanged build is byte-identical."""
    path, content = written_image
    before = path.read_bytes()
    with DiscWriter(path) as writer:
        entry = next(e for e in writer.walk() if e.path == "/DATA.BIN")
        assert writer.write_file_bytes(entry.lba, 17, content[17:4000], file_size=entry.size) == []
    assert path.read_bytes() == before


def test_the_writer_refuses_a_form2_sector(tmp_path):
    path = tmp_path / "image.img"
    path.write_bytes(consistent_image([File("AUDIO.XA", some_data(1, 2324) * 2, form=2)]))
    with DiscWriter(path) as writer:
        entry = next(e for e in writer.walk() if e.path == "/AUDIO.XA")
        with pytest.raises(DiscError, match="Form 2"):
            writer.write_file_bytes(entry.lba, 0, b"nope", file_size=entry.size)


def test_a_write_that_runs_past_the_files_own_extent_is_refused(written_image):
    """The file ends where its directory record says, and the next file starts there.

    `write_file_bytes` is aimed at a text site by offset; without the extent it cannot
    tell a site that reaches the last byte of a file from one that reaches one byte past
    it, and that byte belongs to whatever the layout put next. The size is the only thing
    that makes the difference visible, so it is required rather than optional.
    """
    path, content = written_image
    before = path.read_bytes()
    with DiscWriter(path) as writer:
        entry = next(e for e in writer.walk() if e.path == "/DATA.BIN")
        assert entry.size == len(content)
        # The narrowest case: the last byte of the file, plus one.
        with pytest.raises(DiscError, match="past the file's own extent"):
            writer.write_file_bytes(entry.lba, entry.size - 1, b"\x01\x02", file_size=entry.size)
        # And the last byte alone is still allowed.
        assert writer.write_file_bytes(entry.lba, entry.size - 1, b"\x01", file_size=entry.size)
    assert path.read_bytes()[: entry.lba * 2352] == before[: entry.lba * 2352]


def test_a_write_whose_range_reaches_a_form2_sector_writes_none_of_it(tmp_path):
    """The refusal has to come before the first sector is written, not at the bad one.

    A range that crosses sectors is written one sector at a time, so a Form 2 sector in
    the middle used to stop the loop with the sectors before it already patched: an image
    that is neither the old one nor the new one, and no way back. The synthetic file here
    is three Form 1 sectors with its middle sector turned into Form 2 -- the shape a
    mis-resolved offset into a real-time extent would have.
    """
    path = tmp_path / "image.img"
    raw = bytearray(consistent_image([File("DATA.BIN", some_data(5, 2048 * 3))]))
    path.write_bytes(bytes(raw))
    with DiscWriter(path) as writer:
        entry = next(e for e in writer.walk() if e.path == "/DATA.BIN")
    start = (entry.lba + 1) * 2352
    middle = bytearray(raw[start : start + 2352])
    middle[18] = SUBMODE_FORM2 | SUBMODE_DATA
    middle[22] = middle[18]
    raw[start : start + 2352] = edc.rebuild(bytes(middle))
    path.write_bytes(bytes(raw))
    before = path.read_bytes()
    with DiscWriter(path) as writer, pytest.raises(DiscError, match="Form 2"):
        writer.write_file_bytes(entry.lba, 0, b"\xaa" * (2048 * 2 + 1), file_size=entry.size)
    assert path.read_bytes() == before, (
        "the sectors before the Form 2 one were written before it was noticed: the image "
        "is now neither the old one nor the new one"
    )


def test_reading_zero_bytes_reads_nothing_rather_than_a_sector(written_image):
    """`length=0` used to read one whole sector to return nothing -- and to fail at the
    end of the image, where the site's own last byte is."""
    path, content = written_image
    with DiscWriter(path) as writer:
        entry = next(e for e in writer.walk() if e.path == "/DATA.BIN")
        assert writer.read_file_bytes(entry.lba, 0, 0) == b""
        assert writer.read_file_bytes(entry.lba, len(content), 0) == b""
