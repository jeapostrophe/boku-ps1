"""The PPF3 writer and reader, on synthetic images. No disc needed.

Two kinds of check live here, and it matters which is which. A few -- the 64-bit offset,
the `FILE_ID.DIZ` trailer -- lay out patch bytes by hand and read them, so nothing of ours
is on both sides. **Most of the rest run our writer into our reader**, which cannot catch
a mistake the two share: a format we speak consistently and nobody else does. That is what
`tests/test_real_patch.py` is for, where Icarus/Paradox's own `makeppf3` and `applyppf3`
and retro-trainer's Rust applier get a vote.

Where a check pins a number from `reference/repos/ppf/ppfdev/PPF3.txt`, the number is
written out here and the module's constant is asserted equal to it. Taking the expected
value *from* the constant would make the check pass for whatever the module happened to
say -- measured twice while writing these.
"""

from __future__ import annotations

import random

import pytest

from boku.ppf import (
    BLOCKCHECK_OFFSET_BIN,
    BLOCKCHECK_SIZE,
    HEADER_SIZE,
    MAX_RECORD_SIZE,
    PpfError,
    apply_ppf,
    make_ppf,
    read_ppf,
)

# Big enough to hold the blockcheck window that starts at 0x9320.
IMAGE_SIZE = BLOCKCHECK_OFFSET_BIN + BLOCKCHECK_SIZE + 4096


def synthetic(seed: int = 1, size: int = IMAGE_SIZE) -> bytes:
    return random.Random(seed).randbytes(size)


def write(tmp_path, name: str, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def images(tmp_path, edits: dict[int, int], *, size: int = IMAGE_SIZE):
    """An original and a modified copy, differing at every byte of each `offset: length`.

    The replacement is the original complemented rather than something chosen here, so
    that "the run is 300 bytes long" is true of the images. Writing literal bytes instead
    is how the first draft of these tests was wrong: over pseudo-random filler a literal
    occasionally *matches*, and a matching byte splits the run into two records -- which
    is exactly right, and not what the test meant to be measuring.
    """
    original = synthetic(size=size)
    modified = bytearray(original)
    for offset, length in edits.items():
        modified[offset : offset + length] = bytes(
            b ^ 0xFF for b in original[offset : offset + length]
        )
    return (
        write(tmp_path, "original.img", original),
        write(tmp_path, "modified.img", bytes(modified)),
    )


def span(path, offset: int, length: int) -> bytes:
    return path.read_bytes()[offset : offset + length]


def test_refuses_images_of_different_length(tmp_path):
    """PPF overwrites in place; it has no way to say "the image is now longer"."""
    original = write(tmp_path, "original.img", synthetic())
    modified = write(tmp_path, "modified.img", synthetic() + b"tail")
    with pytest.raises(PpfError, match="same length"):
        make_ppf(original, modified, "test")


def test_refuses_identical_images(tmp_path):
    """A patch with no records makes `applyppf3`'s `do {...} while(count!=0)` run once on
    garbage, so an empty patch is worse than no patch."""
    original = write(tmp_path, "original.img", synthetic())
    modified = write(tmp_path, "modified.img", synthetic())
    with pytest.raises(PpfError, match="identical"):
        make_ppf(original, modified, "test")


def test_splits_a_long_run_at_255_bytes(tmp_path):
    """`zz` is one unsigned byte, so no record may carry more than 255.

    255 is written out rather than taken from `MAX_RECORD_SIZE`: building the expectation
    from the module's own constant leaves this green at any value under 256, which is
    every wrong value that is not caught by `bytes([len(chunk)])` raising.
    """
    spec_maximum = 255
    assert spec_maximum == MAX_RECORD_SIZE

    original, modified = images(tmp_path, {0x2000: 300})
    patch = read_ppf(make_ppf(original, modified, "test"))

    assert [(record.offset, len(record.data)) for record in patch.records] == [
        (0x2000, spec_maximum),
        (0x2000 + spec_maximum, 300 - spec_maximum),
    ]
    assert b"".join(record.data for record in patch.records) == span(modified, 0x2000, 300)


def test_offset_field_is_eight_bytes_little_endian(tmp_path):
    """ "Be careful! Endian format is Intel!" -- and the field is 64 bit, not 32."""
    offset = 0x00A1B2C3
    original, modified = images(tmp_path, {offset: 3}, size=offset + 4096)
    raw = make_ppf(original, modified, "test")

    first_record = raw[HEADER_SIZE + BLOCKCHECK_SIZE :]
    assert first_record[:8] == offset.to_bytes(8, "little")
    assert first_record[8] == 3


def test_reads_an_offset_above_four_gigabytes():
    """The reader must not truncate to 32 bits -- PPF3 addresses up to 2**63-1."""
    offset = 0x1_0000_0002
    raw = (
        b"PPF30"
        + bytes([2])
        + b"x".ljust(50)
        + bytes([0, 0, 0, 0])
        + offset.to_bytes(8, "little")
        + bytes([1])
        + b"!"
    )
    (record,) = read_ppf(raw).records
    assert record.offset == offset


def test_blockcheck_is_the_kilobyte_at_0x9320_of_the_original(tmp_path):
    """0x9320 is written out here, not taken from the module.

    `PPF3.txt`: "If Imagetype = 0x00 then its data starting from 0x9320." Deriving the
    expected window from `BLOCKCHECK_OFFSET_BIN` would make this test pass for whatever
    the module happened to say -- measured: moving the constant to 0x9300 left the first
    draft of this test green. What that offset *means* is checked against the real disc's
    geometry in `tests/test_real_patch.py`.
    """
    spec_offset = 0x9320
    assert spec_offset == BLOCKCHECK_OFFSET_BIN

    original, modified = images(tmp_path, {0x2000: 1})
    raw = make_ppf(original, modified, "test")

    expected = original.read_bytes()[spec_offset : spec_offset + BLOCKCHECK_SIZE]
    assert raw[57] == 1
    assert raw[HEADER_SIZE : HEADER_SIZE + BLOCKCHECK_SIZE] == expected
    assert read_ppf(raw).blockcheck == expected


def test_description_is_fifty_bytes_and_survives_the_round_trip(tmp_path):
    original, modified = images(tmp_path, {0x2000: 1})
    raw = make_ppf(original, modified, "boku-ps1 trial")

    assert len(raw[6:56]) == 50
    assert read_ppf(raw).description == "boku-ps1 trial"
    with pytest.raises(PpfError, match="50"):
        make_ppf(original, modified, "x" * 51)


def test_a_run_crossing_the_read_chunk_boundary_stays_one_record(tmp_path):
    """The diff streams the images; a difference that straddles two reads is still one
    difference, and splitting it there would be an artefact of our buffer size."""
    original, modified = images(tmp_path, {4094: 4})
    patch = read_ppf(make_ppf(original, modified, "test", chunk_size=4096))

    assert [(record.offset, record.data) for record in patch.records] == [
        (4094, span(modified, 4094, 4))
    ]


def test_output_is_deterministic(tmp_path):
    original, modified = images(tmp_path, {0x2000: 400, 0x5000: 1})
    assert make_ppf(original, modified, "test") == make_ppf(original, modified, "test")


def test_apply_reproduces_the_modified_image_and_leaves_the_original_alone(tmp_path):
    original, modified = images(tmp_path, {0x40: 2, 0x2000: 300})
    before = original.read_bytes()
    out = tmp_path / "out.img"

    apply_ppf(original, make_ppf(original, modified, "test"), out)

    assert out.read_bytes() == modified.read_bytes()
    assert original.read_bytes() == before


def test_apply_refuses_a_blockcheck_mismatch_and_writes_nothing(tmp_path):
    """Stock appliers prompt and carry on; ours refuses. The byte moved is inside the
    1 KiB window, which is the only thing the blockcheck can see."""
    original, modified = images(tmp_path, {0x2000: 1})
    raw = make_ppf(original, modified, "test")

    other = bytearray(original.read_bytes())
    other[BLOCKCHECK_OFFSET_BIN + 5] ^= 0xFF
    wrong = write(tmp_path, "wrong.img", bytes(other))
    out = tmp_path / "out.img"

    with pytest.raises(PpfError, match="blockcheck"):
        apply_ppf(wrong, raw, out)
    assert not out.exists()


def test_apply_refuses_a_record_past_the_end_of_the_image(tmp_path):
    original, modified = images(tmp_path, {0x2000: 1})
    raw = bytearray(make_ppf(original, modified, "test"))
    # Move the record's offset to the last byte of the image and leave its length alone:
    # changing the length would shift every record after it and the reader would call the
    # patch truncated before the offset was ever looked at.
    record = HEADER_SIZE + BLOCKCHECK_SIZE
    raw[record : record + 8] = IMAGE_SIZE.to_bytes(8, "little")

    with pytest.raises(PpfError, match="past the end"):
        apply_ppf(original, bytes(raw), tmp_path / "out.img")


def test_a_record_ending_exactly_at_the_last_byte_is_allowed(tmp_path):
    """The bound is `offset + len > size`, and the only place `>` and `>=` differ is a
    record that ends on the final byte -- which a real patch to the last sector of an
    image produces."""
    original, modified = images(tmp_path, {IMAGE_SIZE - 4: 4})
    out = tmp_path / "out.img"

    apply_ppf(original, make_ppf(original, modified, "test"), out)
    assert out.read_bytes() == modified.read_bytes()


def test_a_run_at_offset_zero_is_one_record_at_zero(tmp_path):
    """Offset 0 is the value a `if start:` test would swallow; the writer must use
    `is not None`."""
    original, modified = images(tmp_path, {0: 4})
    patch = read_ppf(make_ppf(original, modified, "test"))

    assert [(record.offset, len(record.data)) for record in patch.records] == [(0, 4)]


def test_apply_refuses_to_write_over_the_image_it_is_patching(tmp_path):
    """Opening the original read-only does not save it: the result is renamed into place
    at the end, so naming the dump as `--out` destroys it on the SUCCESS path."""
    original, modified = images(tmp_path, {0x2000: 4})
    before = original.read_bytes()
    raw = make_ppf(original, modified, "test")

    with pytest.raises(PpfError, match="destroy"):
        apply_ppf(original, raw, original)
    assert original.read_bytes() == before


def test_apply_refuses_a_patch_that_carries_no_blockcheck(tmp_path):
    """Nothing to check is not the same as checking and passing, so it is not silent."""
    original, modified = images(tmp_path, {0x2000: 1})
    raw = make_ppf(original, modified, "test", blockcheck=False)

    assert raw[57] == 0
    with pytest.raises(PpfError, match="no blockcheck"):
        apply_ppf(original, raw, tmp_path / "out.img")
    apply_ppf(original, raw, tmp_path / "out.img", verify_blockcheck=False)
    assert (tmp_path / "out.img").read_bytes() == modified.read_bytes()


def test_undo_data_is_the_original_bytes_and_is_off_by_default(tmp_path):
    original, modified = images(tmp_path, {0x2000: 3})
    plain = read_ppf(make_ppf(original, modified, "test"))
    with_undo = read_ppf(make_ppf(original, modified, "test", undo=True))

    assert plain.undo is False
    assert [record.undo for record in plain.records] == [None]
    assert with_undo.undo is True
    (record,) = with_undo.records
    assert record.data == span(modified, 0x2000, 3)
    assert record.undo == span(original, 0x2000, 3)

    apply_ppf(original, make_ppf(original, modified, "test", undo=True), tmp_path / "out.img")
    assert (tmp_path / "out.img").read_bytes() == modified.read_bytes()


def test_we_emit_no_file_id_trailer_but_can_read_one(tmp_path):
    """The trailer sits *after* the records, and an applier that stops at EOF instead of
    looking for it -- retro-trainer's `apply_ppf` is one -- reads `@BEGIN_FILE_ID.DIZ` as
    a record and fails. So we read them and never write one."""
    original, modified = images(tmp_path, {0x2000: 3})
    raw = make_ppf(original, modified, "test")
    assert read_ppf(raw).file_id is None

    note = b"a note"
    with_id = (
        raw + b"@BEGIN_FILE_ID.DIZ" + note + b"@END_FILE_ID.DIZ" + len(note).to_bytes(2, "little")
    )
    patch = read_ppf(with_id)
    assert patch.file_id == "a note"
    assert [record.data for record in patch.records] == [span(modified, 0x2000, 3)]


def test_touched_ranges_are_exactly_what_changed(tmp_path):
    edits = {0x40: 2, 0x2000: 300}
    original, modified = images(tmp_path, edits)
    patch = read_ppf(make_ppf(original, modified, "test"))

    touched = {
        offset
        for start, length in patch.touched_ranges()
        for offset in range(start, start + length)
    }
    expected = {
        offset for start, length in edits.items() for offset in range(start, start + length)
    }
    assert touched == expected


def test_reader_refuses_a_truncated_record(tmp_path):
    original, modified = images(tmp_path, {0x2000: 3})
    with pytest.raises(PpfError, match="truncated"):
        read_ppf(make_ppf(original, modified, "test")[:-1])


def test_reader_refuses_a_file_that_is_not_ppf3():
    with pytest.raises(PpfError, match="PPF30"):
        read_ppf(b"PPF20" + bytes([1]) + b" " * 50 + bytes(1028))
