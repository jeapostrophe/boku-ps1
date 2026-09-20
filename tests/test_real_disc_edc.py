"""The EDC/ECC gate: every sector of the real disc, recomputed from its own bytes.

This is the only check that can say the *algorithm* is right rather than merely
self-consistent. A press of SCPS-10088 is 280,170 sectors of ground truth written by
Sony's own mastering tools, so recomputing each sector's EDC (and, in Form 1, its 276
ECC bytes) from its header, subheader and data and getting the stored bytes back is the
whole proof. Nothing here hard-codes a count or a digest: the assertions cross the
sectors against each other and against the image's own length.

It needs the contributor's own dump and skips cleanly without one (see `conftest.py`).
The sweep takes about a minute -- one pass over 660 MB with the arithmetic in
`boku.edc`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from boku import edc
from boku.disc import FIRST_VOLUME_DESCRIPTOR_LBA, DiscImage
from tests.rules import slow_ecc

SWEEP_CHUNK_SECTORS = 256


@pytest.fixture(scope="session")
def sweep(real_image: Path) -> Counter:
    """Recompute EDC and ECC for every sector, counting what each one turned out to be."""
    counts: Counter = Counter()
    with real_image.open("rb") as handle:
        lba = 0
        while raw := handle.read(SWEEP_CHUNK_SECTORS * edc.RAW_SECTOR_SIZE):
            for i in range(len(raw) // edc.RAW_SECTOR_SIZE):
                start = i * edc.RAW_SECTOR_SIZE
                check = edc.check_sector(raw[start : start + edc.RAW_SECTOR_SIZE], lba + i)
                if check.form == 1:
                    counts["form1"] += 1
                    counts["form1_edc_mismatch"] += check.edc_stored != check.edc_computed
                    counts["form1_ecc_mismatch"] += not check.ecc_ok
                elif check.edc_omitted:
                    counts["form2_without_edc"] += 1
                else:
                    counts["form2_with_edc"] += 1
                    counts["form2_edc_mismatch"] += check.edc_stored != check.edc_computed
            lba += len(raw) // edc.RAW_SECTOR_SIZE
    counts["sectors"] = lba
    return counts


def test_every_form1_sector_reproduces_its_own_edc_and_ecc(sweep: Counter, real_image: Path):
    """The gate `PIPE-04` rests on: our arithmetic is the mastering tool's arithmetic."""
    assert sweep["form1"] > 0
    assert sweep["form1_edc_mismatch"] == 0, f"{sweep['form1_edc_mismatch']} Form 1 EDC mismatches"
    assert sweep["form1_ecc_mismatch"] == 0, f"{sweep['form1_ecc_mismatch']} Form 1 ECC mismatches"


def test_every_form2_sector_that_carries_an_edc_reproduces_it(sweep: Counter):
    """Form 2's EDC is optional. Where this disc wrote one, it has to come back out.

    The measurement, recorded here because it decides how a Form 2 write must behave:
    on this press *every* Form 2 sector carries an EDC, so `form2_without_edc` is zero.
    `boku.edc.rebuild` still preserves a zero -- `test_edc.py` pins that path, since the
    disc cannot.
    """
    assert sweep["form2_with_edc"] > 0
    assert sweep["form2_edc_mismatch"] == 0, f"{sweep['form2_edc_mismatch']} Form 2 EDC mismatches"


def test_the_sweep_saw_every_sector_of_the_image(sweep: Counter, real_image: Path):
    """No sector fell through the classification, and none was read twice."""
    assert sweep["sectors"] == real_image.stat().st_size // edc.RAW_SECTOR_SIZE
    assert sweep["form1"] + sweep["form2_with_edc"] + sweep["form2_without_edc"] == sweep["sectors"]


def test_the_ecc_is_computed_with_the_header_zeroed_and_the_disc_says_so(real_image: Path):
    """The rule `research/ps1-translation-practice.md` §1.3 calls the Form 1 quirk.

    An implementation that let the sector's address into the ECC would still be
    self-consistent -- it would verify everything it wrote. Only the disc can tell the
    two apart, so this computes the parity both ways on real sectors and requires the
    zeroed-header answer to match and the other to miss. It is the disc-side half of
    `test_edc.py`'s `..._header_is_outside_both_fields_...`, and it is what makes that
    gate's failure mean something.

    `slow_ecc` is the transcription in `tests/rules.py`, not `boku.edc`, so the two ways
    differ only in the header and in nothing else.
    """
    with DiscImage(real_image) as image:
        # Sampled from the disc rather than listed: the volume descriptor, then the first
        # sector of each file the filesystem knows about, which spreads the sample across
        # the executable, the archive and the streaming media at the far end of the image.
        lbas = [FIRST_VOLUME_DESCRIPTOR_LBA] + [
            entry.lba for entry in image.walk() if not entry.is_dir and entry.size
        ]
        form1 = [raw for lba in lbas if edc.check_sector(raw := image.read_raw(lba), lba).form == 1]
    assert len(form1) >= 5, f"only {len(form1)} of {len(lbas)} sampled sectors are Form 1"
    for raw in form1:
        stored = raw[edc.ECC_OFFSET : edc.ECC_OFFSET + edc.ECC_SIZE]
        assert slow_ecc(raw, zero_header=True) == stored
        assert slow_ecc(raw, zero_header=False) != stored
