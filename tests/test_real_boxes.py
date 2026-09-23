"""`research/data/text-boxes.tsv` against the contributor's disc (`PLAN TXT-07`).

The table's pen positions and pitches were read off the code; this reads them off again,
from the bytes, so a row copied wrong is a failure here rather than a translation refused
by a box that is not where the game draws. The frame edges (`right`) are screenshot
measurements and are checked only where the code also carries them (the help box).
"""

from __future__ import annotations

import struct

import pytest

from boku.archive import Archive
from boku.boxes import EVERY_ITEM, box_for, load_boxes
from boku.extract import SCRIPT_DIR_NAME
from boku.script_store import load_store

HELP, CARD = "exe@80029B20", "exe@8003D5F0"


def word(archive: Archive, ram: int, overlay: str | None = None) -> int:
    raw = archive.overlay_bytes(overlay, ram, 4) if overlay else archive.exe_bytes(ram, 4)
    return struct.unpack("<I", raw)[0]


def pens(prefix: str, items) -> dict[int, int]:
    """`{item: x}` for the items given, each through `box_for` as the build resolves it."""
    return {i: box_for(f"{prefix}.{i}").x for i in items}


@pytest.fixture(scope="module")
def known_ids(disc_dir) -> set[str]:
    lines = load_store(disc_dir / SCRIPT_DIR_NAME).lines
    return set(lines) | {line_id.rpartition(".")[0] + EVERY_ITEM for line_id in lines}


def test_every_row_names_a_line_or_an_array_the_extract_knows(known_ids):
    assert set(load_boxes()) - known_ids == set()


def test_the_help_screen_s_pens_are_g_help_pos_and_help_draw_s_literals(archive):
    """Lines 0-12 sit at `g_help_pos` (0x80029904, a byte pair each); the pad-type button
    labels 13-21 at `addiu a1,zero,x` literals in `help_draw`, one per call."""
    table = {i: archive.exe_bytes(0x80029904 + 2 * i, 1)[0] for i in range(13)}
    literal_sites = {
        13: 0x80035708,
        14: 0x80035718,
        15: 0x8003572C,
        19: 0x80035730,
        20: 0x80035740,
        21: 0x80035750,
    }
    for line, site in literal_sites.items():
        found = word(archive, site)
        assert found >> 16 == 0x2405, f"0x{site:08X} is not `addiu a1,zero,imm`"
        table[line] = found & 0xFFFF
    # Pad types 0 and 1 draw lines 13+3t .. 15+3t from the same three calls.
    table |= {16: table[13], 17: table[14], 18: table[15]}
    assert pens(HELP, range(22)) == table


def test_the_help_screen_s_right_column_ends_at_the_box_less_the_stock_margin(archive):
    """Lines 4-12 (the right column and the two bottom lines) end where the help box
    (`g_select_rect[6]`) ends less the margin the stock lines keep on the left."""
    x, _, w, _ = struct.unpack("<4h", archive.exe_bytes(0x80028E44 + 6 * 8, 8))
    margin = min(pens(HELP, range(13)).values()) - x
    right = {i: box_for(f"{HELP}.{i}").right for i in range(4, 13)}
    assert right == dict.fromkeys(range(4, 13), x + w - margin)


def test_the_card_messages_pens_are_the_ones_g_mc_msg_chooses(archive):
    """`mc_msg_draw` (TITLE 0x8007CB54) starts every line of a message at 0x4A when the
    record's layout is 5 or 6 and at 0x22 otherwise; a record is `{lines, layout, line[3]}`
    at `g_mc_msg` (TITLE 0x800814C0), 32 of them."""
    table = archive.overlay_bytes("TITLE.OVL", 0x800814C0, 5 * 32)
    drawn: dict[int, set[int]] = {}
    for record in range(32):
        count, layout, *lines = table[5 * record : 5 * record + 5]
        for line in lines[:count]:
            drawn.setdefault(line, set()).add(0x4A if 5 <= layout < 7 else 0x22)
    assert all(len(xs) == 1 for xs in drawn.values()), "an item drawn at two pens"
    assert pens(CARD, drawn) == {line: xs.pop() for line, xs in drawn.items()}


def test_the_bag_and_extras_pens_are_their_drawers_literals(archive):
    """Descriptions and captions: `bag_draw` hands `text_draw_h` x = 0xB8 (`addiu
    a1,zero,0xb8`, 0x80041850); summer memories: `extras_draw` starts every label at
    `addiu s1,zero,0x28` (TITLE 0x80080708)."""
    desc = word(archive, 0x80041850)
    extras = word(archive, 0x80080708, "TITLE.OVL")
    assert desc >> 16 == 0x2405 and extras >> 16 == 0x2411, "not the literals these rows cite"
    for prefix in ("exe@80046398", "exe@80046614"):
        assert box_for(f"{prefix}.0").x == desc & 0xFFFF
    assert set(pens("exe@8003DA00", range(5)).values()) == {extras & 0xFFFF}


def test_every_row_s_pitch_is_its_walker_s_stock_step(archive):
    """`pitch` is what the stock sheet is measured at on that surface, so it is the literal
    the walker steps by -- read from the `addiu reg,reg,step` each walker holds."""

    def step(ram: int, overlay: str | None = None) -> int:
        found = word(archive, ram, overlay)
        assert found >> 26 == 0x09, f"0x{ram:08X} is not an addiu"
        return found & 0xFFFF

    walkers = {
        HELP: step(0x800353B0),  # text_draw_right
        CARD: step(0x8007CDD8, "TITLE.OVL"),  # mc_msg_draw
        "exe@8003D9BC": step(0x8007FBC4, "TITLE.OVL"),  # config_draw
        "exe@80046214": step(0x80043848),  # text_draw_line_h
        "exe@80046398": step(0x800438B8),  # text_draw_h
        "exe@80046614": step(0x800438B8),
        "exe@8003DA00": step(0x80080790, "TITLE.OVL"),  # extras_draw
    }
    help_line = step(0x80035490)  # help_line_draw: lines 19, 20
    # Letter-spaced lines add a second addiu after the step: config line 1, extras 0 and 3.
    config_extra = step(0x8007FBD4, "TITLE.OVL")  # addiu s0,v1,4
    extras_extra = step(0x800807A8, "TITLE.OVL")  # addiu s1,v1,4
    special = {
        f"{HELP}.19": help_line,
        f"{HELP}.20": help_line,
        "exe@8003D9BC.1": walkers["exe@8003D9BC"] + config_extra,
        "exe@8003DA00.0": walkers["exe@8003DA00"] + extras_extra,
        "exe@8003DA00.3": walkers["exe@8003DA00"] + extras_extra,
    }
    for line_id, box in load_boxes().items():
        wanted = special.get(line_id, walkers.get(line_id.rpartition(".")[0]))
        assert box.pitch == wanted, line_id
