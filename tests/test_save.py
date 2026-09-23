"""`boku.save` (PLAN `ENV-06`): the memory-card save, against the game's own code and a real card.

Three sources of truth, none of them this module's own constants:

* the executable and `TITLE.OVL` of the import (skips without one) -- the save-region list,
  the ending chooser's thresholds and star bytes are decoded from the instructions and tables
  the game runs, so a retyped constant that drifts from the disc is caught;
* a card the game itself wrote (`$BOKU_SAMPLE_CARD`, default `work/saves/sample.mcd`; skips
  without one -- any save of this game in slot 1): reading it and writing it back must give
  the game's own bytes;
* for the synthetic tests, sums and offsets recomputed here from the documented layout
  (research/save-format.md), never by calling the function under test.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

from boku import REPO_ROOT, sumo
from boku import save as S

SAMPLE_CARD = Path(os.environ.get("BOKU_SAMPLE_CARD", REPO_ROOT / "work" / "saves" / "sample.mcd"))

REGIONS = (S.Region(0x80001000, 20), S.Region(0x80002000, 7), S.Region(0x80003000, 5))


def _body(fill: int = 0) -> S.SaveBody:
    return S.SaveBody(REGIONS, bytes((fill + i) & 0xFF for i in range(32)))


# --- synthetic -----------------------------------------------------------------------------


def test_body_maps_ram_addresses_across_regions():
    body = _body()
    # Region 2 starts after 20 + 7 bytes of the body.
    assert body.read(0x80003001, 2) == bytes([28, 29])
    body.write(0x80002006, b"\xaa")
    assert body.data[26] == 0xAA


def test_body_refuses_an_address_that_straddles_two_regions():
    with pytest.raises(S.SaveError, match="not inside one saved region"):
        _body().read(0x80001012, 4)  # the last 2 bytes of region 0 and 2 beyond it


def test_packed_body_carries_its_own_sum_and_size():
    packed = _body(fill=0x90).packed()
    stored_sum, size = struct.unpack_from("<II", packed, 0)
    assert size == 32
    assert stored_sum == sum(packed[4:])  # the sum field itself counts as zero
    assert S.SaveBody.unpack(REGIONS, packed).data[8:] == _body(fill=0x90).data[8:]


def test_unpack_refuses_what_save_verify_refuses():
    packed = bytearray(_body().packed())
    packed[20] ^= 1
    with pytest.raises(S.SaveError, match="sum"):
        S.SaveBody.unpack(REGIONS, bytes(packed))
    packed = bytearray(_body().packed())
    packed[4] = 31
    with pytest.raises(S.SaveError, match="size field is 31"):
        S.SaveBody.unpack(REGIONS, bytes(packed))


def test_title_numbers_have_no_leading_zero():
    parts, digits = ("P", "Q", "R"), tuple("abcdefghij")
    assert S.build_title(parts, digits, 1, 5) == b"PbQfR"
    assert S.build_title(parts, digits, 1, 31) == b"PbQdbR"


def test_star_mask_uses_bits_one_up_and_never_bit_zero():
    assert S.star_mask(0) == 0
    assert S.star_mask(1) == 0b10
    assert S.star_mask(15) == 0xFFFE
    with pytest.raises(S.SaveError):
        S.star_mask(16)


def test_card_directory_names_the_save_and_every_frame_checks():
    tables = S.GameTables(REGIONS, "BIXXXX-00000-", b"\0" * 0x1A0, ("t",), tuple("0123456789"))
    save = bytes([ord("S"), ord("C")]) + bytes(S.BLOCK - 2)
    card = S.write_card({3: save}, tables)
    assert len(card) == 128 * 1024
    for f in range(64):
        frame = card[f * 128 : (f + 1) * 128]
        if f != 63:
            x = 0
            for b in frame[:127]:
                x ^= b
            assert frame[127] == x, f"frame {f}'s check byte"
    assert card[128:132] == b"\x51\0\0\0" and card[138:152] == b"BIXXXX-00000-3"
    assert card[256:260] == b"\xa0\0\0\0"
    assert S.read_card(card, tables) == {3: save}


# --- against the import --------------------------------------------------------------------


def _mips(word: int) -> tuple[int, int, int, int]:
    """(opcode, rs, rt, signed immediate) of an I-type instruction."""
    imm = word & 0xFFFF
    return word >> 26, (word >> 21) & 31, (word >> 16) & 31, imm - 0x10000 if imm & 0x8000 else imm


ENDING_PICK = 0x8002E848
ENDING_PICK_BYTES = 164


def _ending_pick(archive):
    """The chooser's star bytes (low, high) and its (threshold, epilogue) ladder, decoded from
    `ending_pick`'s own instructions: `lbu` from g_flags, then `slti count, t` tests in order,
    each band's value an `addiu v0, zero, k` (or `sb zero`) in the same order."""
    words = struct.unpack(
        f"<{ENDING_PICK_BYTES // 4}I", archive.exe_bytes(ENDING_PICK, ENDING_PICK_BYTES)
    )
    loads, thresholds, values = [], [], []
    for w in words:
        op, rs, rt, imm = _mips(w)
        if op == 0x24:  # lbu
            loads.append((rt, imm))
        elif op == 0x0A and rs == 4:  # slti v0, a0, imm
            thresholds.append(imm)
        elif op == 0x09 and rs == 0 and rt == 2:  # addiu v0, zero, k
            values.append(imm)
        elif op == 0x28 and rt == 0:  # sb zero, ...
            values.append(0)
    return loads, thresholds, values


def test_star_bytes_are_the_ones_ending_pick_reads(archive):
    loads, _, _ = _ending_pick(archive)
    # lbu $3, hi($2); lbu $2, lo($2); then $3 << 8 | $2.
    assert [(rt, off) for rt, off in loads] == [(3, S.STAR_FLAGS[1]), (2, S.STAR_FLAGS[0])]


def test_epilogue_for_matches_ending_pick_for_every_count(archive):
    _, thresholds, values = _ending_pick(archive)
    assert len(values) == len(thresholds) + 1

    def game(count: int) -> int:
        for t, v in zip(thresholds, values, strict=False):
            if count >= t:
                return v
        return values[-1]

    for count in range(17):
        mask = (1 << count) - 1
        assert S.epilogue_for(mask) == game(count), f"{count} stars"


def test_regions_are_the_list_the_game_walks(archive):
    tables = S.GameTables.read(archive)
    for addr, n in ((S.G_CLOCK, 3), (S.G_FLAGS, 256), (S.PLAY_TIMER, 4), (S.SUMMARY_FLAG, 1)):
        assert any(r.addr <= addr and addr + n <= r.addr + r.length for r in tables.regions), hex(
            addr
        )
    assert S.build_title(tables.title_parts, tables.title_digits, 1, 31)  # fits the header


# --- against a card the game wrote ---------------------------------------------------------


@pytest.fixture(scope="module")
def sample_card() -> bytes:
    if not SAMPLE_CARD.is_file():
        pytest.skip(
            f"no sample card at {SAMPLE_CARD}: copy any memory card holding this game's save "
            f"in slot 1 there (or set BOKU_SAMPLE_CARD). Cards hold the game's icon, so none "
            f"is tracked."
        )
    return SAMPLE_CARD.read_bytes()


def test_rebuilding_the_games_own_save_gives_its_bytes(archive, sample_card):
    tables = S.GameTables.read(archive)
    original = S.read_card(sample_card, tables)[1]
    assert struct.unpack_from("<I", original, S.BODY + 4)[0] == tables.body_size
    body = S.body_of(original, tables)
    mine = S.build_save_file(tables, body, 1)
    # Header, title and icon; then the body. Between them sit the summary -- whose play
    # counter the game copies from a TITLE.OVL variable a frame apart from the body's -- and
    # bytes save_build never initialises.
    assert mine[: S.SUMMARY] == original[: S.SUMMARY]
    assert mine[S.SUMMARY + 8 : S.SUMMARY + 10] == original[S.SUMMARY + 8 : S.SUMMARY + 10]
    end = S.BODY + tables.body_size
    assert mine[S.BODY : end] == original[S.BODY : end]


def test_the_card_frames_match_the_games_card(archive, sample_card):
    tables = S.GameTables.read(archive)
    saves = S.read_card(sample_card, tables)
    mine = S.write_card(saves, tables)
    # Frame 63 (write test) holds whatever the writer left there; every other frame of the
    # directory block must agree.
    assert mine[: 63 * 128] == sample_card[: 63 * 128]


def test_an_edited_save_reads_back_with_the_edit(archive, sample_card):
    tables = S.GameTables.read(archive)
    base = S.body_of(S.read_card(sample_card, tables)[1], tables)
    entry = S.CorpusEntry("x", 30, stars=S.star_mask(8), flags=((42, 7),))
    card = S.write_card({1: S.build_save_file(tables, S.edited_body(base, entry), 1)}, tables)
    back = S.body_of(S.read_card(card, tables)[1], tables)
    assert back.clock == (30, *S.BEDTIME)
    assert back.stars == S.star_mask(8) and back.flag(42) == 7


# --- the command line refuses what it would otherwise drop or misread (review 2026-09-22) ---


def _parser():
    import argparse

    return S.add_arguments(argparse.ArgumentParser())


def test_stars_and_stars_mask_cannot_both_be_given():
    with pytest.raises(SystemExit):
        _parser().parse_args(["--base", "b", "--out", "o", "--stars", "15", "--stars-mask", "2"])


@pytest.mark.parametrize("slot", ["0", "16", "100"])
def test_slot_must_be_one_the_card_can_hold(slot):
    with pytest.raises(SystemExit):
        _parser().parse_args(["--base", "b", "--out", "o", "--slot", slot])


def test_poke_refuses_empty_bytes():
    base = ["--base", "b", "--out", "o"]
    for bad in ("80028FA0=", "80028FA0", "zz=00"):
        with pytest.raises(SystemExit):
            _parser().parse_args([*base, "--poke", bad])


def test_body_addresses_work_in_every_ram_mirror():
    # The run_core --poke spelling: KUSEG, KSEG0 and KSEG1 name the same RAM byte.
    for addr in (0x00002001, 0x80002001, 0xA0002001):
        body = _body()
        body.write(addr, b"\xee")
        assert body.data[21] == 0xEE, hex(addr)
    with pytest.raises(S.SaveError, match="not main RAM"):
        _body().write(0x1F801070, b"\x00")


def test_write_card_refuses_a_slot_the_game_cannot_list():
    tables = S.GameTables(REGIONS, "P-", b"", ("t",), tuple("0123456789"))
    with pytest.raises(S.SaveError, match="slot 16"):
        S.write_card({16: bytes(S.BLOCK)}, tables)


def test_a_write_into_the_bodys_sum_and_size_is_refused():
    with pytest.raises(S.SaveError, match="sum and size"):
        _body().write(0x80001004, b"\x01")
    _body().write(0x80001008, b"\x01")  # the first byte packing keeps


def test_load_base_refuses_a_file_that_is_neither_card_nor_ram(tmp_path):
    odd = tmp_path / "x.gme"
    odd.write_bytes(bytes(134_976))
    tables = S.GameTables(REGIONS, "P-", b"", ("t",), tuple("0123456789"))
    with pytest.raises(S.SaveError, match="134976 bytes"):
        S.load_base(odd, tables, 1)


_SUMO = S.SumoTables(((40, 40, 40, 40),) * 13, (50,) * 13)
"""Every species alike: base stats 40, typical size 50."""


def _synthetic_tables() -> S.GameTables:
    regions = (S.Region(0x80025908, 20), S.Region(S.G_FLAGS, 256), S.Region(S.G_CLOCK, 16),
               S.Region(sumo.CAGE, sumo.RECORD * sumo.CAGE_SLOTS))  # fmt: skip
    return S.GameTables(regions, "P-", b"", ("a", "b", "c"), tuple("0123456789"), _SUMO)


def _stub_disc(monkeypatch) -> S.GameTables:
    """`main_save` reads the synthetic tables instead of an import."""
    tables = _synthetic_tables()
    monkeypatch.setattr(S.GameTables, "read", classmethod(lambda cls, archive: tables))
    monkeypatch.setattr(S, "Archive", lambda disc: None)
    return tables


def _cards() -> tuple[S.GameTables, dict[str, bytes]]:
    tables = _synthetic_tables()
    base = S.SaveBody(tables.regions, bytes(tables.body_size))
    return tables, {n: S.write_set(base, tables, e) for n, e in S.card_sets().items()}


def test_corpus_refuses_edit_switches_it_would_ignore(tmp_path, capsys, monkeypatch):
    base = tmp_path / "b.ram"
    base.write_bytes(bytes(S.RAM_BYTES))
    _stub_disc(monkeypatch)  # tables a corpus can be built over, so only the refusal stops it
    args = _parser().parse_args(
        ["--base", str(base), "--out", str(tmp_path / "c"), "--corpus", "--flag", "75=9"]
    )
    assert S.main_save(args) == 1
    assert "--corpus" in capsys.readouterr().out
    assert not (tmp_path / "c").exists()


# --- the finished-game marker and the DuckStation card set (PLAN ENV-07) -------------------

SUMMARY_SCAN = 0x8007B65C
SUMMARY_SCAN_BYTES = 0xD0


def _summary_scan(archive) -> tuple[int, int]:
    """(the day threshold, the RAM address it sets) from the card scan's own instructions:
    `lbu v, 8(summary)` (the summary's day), `sltiu v, v, K`, then `sb` of 1 at `0x8002 << 16
    + off` -- a summary whose day is >= K marks the card as holding a finished game."""
    words = struct.unpack(
        f"<{SUMMARY_SCAN_BYTES // 4}I",
        archive.overlay_bytes("TITLE.OVL", SUMMARY_SCAN, SUMMARY_SCAN_BYTES),
    )
    decoded = [_mips(w) for w in words]
    for i, (op, _rs, _rt, imm) in enumerate(decoded):
        if op == 0x24 and imm == 8 and decoded[i + 2][0] == 0x0B:  # lbu; nop; sltiu
            threshold, hi, one = decoded[i + 2][3], {}, {}
            for op2, rs2, rt2, imm2 in decoded[i + 3 : i + 9]:
                if op2 == 0x0F:  # lui rt, hi
                    hi[rt2] = imm2 & 0xFFFF
                elif op2 == 0x09 and rs2 == 0:  # addiu rt, zero, k
                    one[rt2] = imm2
                elif op2 == 0x28 and rs2 in hi and one.get(rt2) == 1:  # sb 1, off(lui)
                    return threshold, (hi[rs2] << 16) + imm2
    raise AssertionError("no day test in the summary scan")


def test_finished_day_is_the_one_the_card_scan_tests(archive):
    threshold, marks = _summary_scan(archive)
    assert threshold == S.FINISHED_DAY
    assert marks == S.SUMMARY_FLAG


def test_duckstation_cards_hold_every_corpus_morning_once(tmp_path):
    tables, written = _cards()
    corpus_mornings = [e.saved_day for e in S.corpus() if e.kind == "morning"]
    seen = []
    for name, card in written.items():
        if "morning" not in name:
            continue
        days = [
            S.body_of(save, tables).clock[0]
            for _, save in sorted(S.read_card(card, tables).items())
        ]
        assert days == sorted(days), f"{name}: the file list should read in day order"
        seen += days
    assert sorted(seen) == sorted(corpus_mornings)


def test_duckstation_endings_card_shows_each_star_count_as_playtime_hours():
    tables, cards = _cards()
    (endings,) = [card for name, card in cards.items() if "ending" in name]
    bands = set()
    for save in S.read_card(endings, tables).values():
        body = S.body_of(save, tables)
        counter = struct.unpack_from("<I", save, S.SUMMARY + 4)[0]
        # The file list's PLAYTIME: 60 ticks a second (measured, research/save-format.md).
        assert counter // (60 * 3600) == bin(body.stars).count("1")
        bands.add(S.epilogue_for(body.stars))
    assert bands == {0, 1, 2, 3, 4}


def test_a_finished_save_never_shares_a_card_with_an_unfinished_one():
    """A New Game started from a card holding a finished save is a second playthrough
    (research/save-format.md § A finished game), so mornings must not share one."""
    tables, cards = _cards()
    finished_cards = 0
    for card in cards.values():
        days = [save[S.SUMMARY + 8] for save in S.read_card(card, tables).values()]
        done = [d >= S.FINISHED_DAY for d in days]
        assert all(done) or not any(done), days
        finished_cards += all(done)
    assert finished_cards == 1


def test_cards_switch_writes_the_duckstation_set(tmp_path, capsys, monkeypatch):
    base = tmp_path / "b.ram"
    base.write_bytes(bytes(S.RAM_BYTES))
    _stub_disc(monkeypatch)
    args = _parser().parse_args(["--base", str(base), "--out", str(tmp_path / "ds"), "--cards"])
    assert S.main_save(args) == 0, capsys.readouterr().out
    names = sorted(p.name for p in (tmp_path / "ds").glob("*.mcd"))
    assert names == sorted(S.card_sets())
    assert (tmp_path / "ds" / "INDEX.tsv").is_file()


def test_finished_saves_carry_their_epilogue_as_the_games_clear_save_does(archive, sample_card):
    """The game's own clear save (written after the ending) holds `ending_prepare`'s pick in
    g_flags[250], which Summer Memories' "ending" replays; a generated finished save must too."""
    tables = S.GameTables.read(archive)
    theirs = S.body_of(S.read_card(sample_card, tables)[1], tables)
    if theirs.clock[0] < S.FINISHED_DAY:
        pytest.skip("the sample card is not a finished game")
    assert theirs.flag(S.EPILOGUE_FLAG) == S.epilogue_for(theirs.stars)
    finished = [e for e in S.corpus() if e.finished]
    assert {S.epilogue_for(e.stars) for e in finished} == {0, 1, 2, 3, 4}
    base = S.SaveBody(tables.regions, bytes(tables.body_size))
    for e in finished:
        body = S.edited_body(base, e)
        assert body.flag(S.EPILOGUE_FLAG) == S.epilogue_for(body.stars), e.name


def test_an_explicit_epilogue_flag_survives_finishing():
    """An entry's own flags are applied after what finishing sets."""
    tables = _synthetic_tables()
    base = S.SaveBody(tables.regions, bytes(tables.body_size))
    mask = S.star_mask(15)
    other = (S.epilogue_for(mask) + 1) % 5
    entry = S.CorpusEntry("x", S.FINISHED_DAY, stars=mask, flags=((S.EPILOGUE_FLAG, other),))
    assert S.edited_body(base, entry).flag(S.EPILOGUE_FLAG) == other


def test_a_finished_base_with_a_new_star_mask_gets_that_masks_epilogue(tmp_path, monkeypatch):
    """A finished base re-edited with a new mask ends on that mask's epilogue."""
    tables = _stub_disc(monkeypatch)
    finished = tmp_path / "f.mcd"
    body = S.edited_body(
        S.SaveBody(tables.regions, bytes(tables.body_size)),
        S.CorpusEntry("f", S.FINISHED_DAY, stars=S.star_mask(15)),
    )
    finished.write_bytes(S.write_card({1: S.build_save_file(tables, body, 1)}, tables))
    out = tmp_path / "x.mcd"
    mask = S.star_mask(5)
    args = _parser().parse_args(
        ["--base", str(finished), "--out", str(out), "--stars-mask", hex(mask)]
    )
    assert S.main_save(args) == 0
    back = S.body_of(S.read_card(out.read_bytes(), tables)[1], tables)
    assert back.flag(S.EPILOGUE_FLAG) == S.epilogue_for(mask)
