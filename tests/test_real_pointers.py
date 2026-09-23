"""`boku.pointers` over the real executable and overlays (`PLAN PIPE-07`).

A moved array is only as safe as the list of instructions that addressed it: one missed
low half and the game reads the old bytes. Two independent derivations are held
against the scan here -- a count per array from a separate register-tracking pass over
the same code (2026-09-23, `work/pipe07/ram/arrayrefs.txt`, corrected by disassembly
where it missed `item_menu_draw`'s third description use at `0x80041818`), and a sweep
of every `addiu`/`ori` whose low half is an array start, whatever built its high half.
"""

from __future__ import annotations

import pytest

from boku.archive import Archive
from boku.array_relocate import images
from boku.arrays import ANCHORS, ARRAYS, locate, walk_all
from boku.pointers import scan

USES = {
    "exe@80029AFC": 1,
    "exe@80029B20": 2,
    "exe@80036750": 1,
    "exe@8003D2E0": 1,
    "exe@8003D5F0": 3,
    "exe@8003D9BC": 2,
    "exe@8003DA00": 4,
    "exe@8003DA4C": 2,
    "exe@80046158": 2,
    "exe@80046178": 1,
    "exe@800461BC": 1,
    "exe@800461CC": 1,
    "exe@80046214": 2,
    "exe@800462C8": 1,
    "exe@800462E4": 1,
    "exe@80046314": 1,
    "exe@80046334": 1,
    "exe@80046364": 1,
    "exe@8004636C": 1,
    "exe@8004637C": 1,
    "exe@80046384": 1,
    "exe@80046390": 1,
    "exe@80046398": 3,
    "exe@80046614": 1,
    "hhon@5328": 2,
    "hhon@6874": 1,
    "musi@2C": 4,
}
"""Low halves per array start, from the independent pass. The seven arrays it did not
cover (`musi@4`, `musi@348`, `musi@358`, `tako@4`, `tako@440`, `zukan@32E8`,
`title@7A78`) are held by the sweep below instead."""

UNRELATED_LOW_HALVES = {("title", 0x8007A400)}
"""`addiu a2, a2, 0x9AFC` in `TITLE.OVL`: its own `0x80079AFC`, which shares the ant
message's low half by coincidence."""


def _images(archive: Archive) -> dict[str, tuple[bytes, int]]:
    return {name: (code, base) for name, code, base, _, _ in images(archive)}


@pytest.fixture(scope="module")
def uses_by_array(archive: Archive) -> dict[str, list[tuple[str, int, int]]]:
    starts = {(w.image, w.start): w.array for w in walk_all(archive)}
    out: dict[str, list[tuple[str, int, int]]] = {}
    for image, (code, base) in _images(archive).items():
        for pair in scan(code, base):
            for use in pair.uses:
                array = starts.get((image, use.target)) or starts.get(("exe", use.target))
                if array is not None:
                    out.setdefault(array.line_id_prefix, []).append((image, pair.ram, use.ram))
    return out


def test_every_anchor_reads_back_the_catalogue_s_own_address(archive: Archive):
    for array in ARRAYS:
        if array.line_id_prefix in ANCHORS:
            assert locate(archive, array) == (array.image, array.ram), array.line_id_prefix


def test_every_array_has_an_anchor_among_its_uses(uses_by_array):
    for prefix, anchor in ANCHORS.items():
        luis = {(image, lui) for image, lui, _ in uses_by_array.get(prefix, [])}
        assert anchor in luis, f"{prefix}'s anchor is not one of its pairs: {sorted(luis)}"


def test_the_scan_finds_as_many_uses_as_the_independent_pass(uses_by_array):
    counted = {prefix: len(uses_by_array.get(prefix, [])) for prefix in USES}
    assert counted == USES


def test_no_low_half_of_an_array_start_goes_unattributed(archive: Archive, uses_by_array):
    """Whatever built the high half: a use the path-follower missed shows up here."""
    seen = {(image, ram) for uses in uses_by_array.values() for image, _, ram in uses}
    starts = {(w.image, w.start): w.array for w in walk_all(archive)}
    unseen = []
    for image, (code, base) in _images(archive).items():
        for offset in range(0, len(code) - 3, 4):
            word = int.from_bytes(code[offset : offset + 4], "little")
            if word >> 26 not in (0x09, 0x0D):
                continue
            ram = base + offset
            for (where, start), array in starts.items():
                if where not in ("exe", image) or word & 0xFFFF != start & 0xFFFF:
                    continue
                if (image, ram) not in seen and (image, ram) not in UNRELATED_LOW_HALVES:
                    unseen.append(f"{image} 0x{ram:08X} -> {array.line_id_prefix}")
    assert unseen == []
