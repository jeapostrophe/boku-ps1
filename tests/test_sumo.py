"""`boku.sumo` and the bug-sumo save (PLAN `ENV-08`).

The stat tables come from the import's `MUSI.OVL` (skips without one); whether the game computes
the same fighter from a generated cage is `tests/test_real_sumo_bout.py`'s, on Beetle.
"""

from __future__ import annotations

import re
import struct

import pytest

from boku import REPO_ROOT, sumo, voice
from boku import save as S

REGIONS = (S.Region(0x80025908, 20), S.Region(S.G_FLAGS, 256), S.Region(S.G_CLOCK, 16),
           S.Region(sumo.CAGE, sumo.RECORD * sumo.CAGE_SLOTS),
           S.Region(sumo.STAGE - 2, 5))  # fmt: skip
"""The saved regions a sumo save touches, as `g_save_regions` has them."""


@pytest.fixture(scope="module")
def tables(archive) -> sumo.SumoTables:
    return sumo.SumoTables.read(archive)


def test_species_rows_follow_the_games_type_split():
    # sumo_species: types below 0x1F are rows type - 0x17, the rest type - 0x30.
    assert [sumo.species(t) for t in (23, 30, 56, 60)] == [0, 7, 8, 12]
    with pytest.raises(ValueError):
        sumo.species(31)


def test_max_size_is_the_last_size_before_a_byte_stat_wraps(tables):
    for kind in sumo.TYPES.values():
        size = tables.max_size(kind)
        assert all(0 < s < 256 for s in (tables.stats(kind, size).strength,
                                          *tables.stats(kind, size).defence)), kind  # fmt: skip
        if size < 255:
            row = tables.base[sumo.species(kind)][1:]
            diff = size + 1 - tables.typical[sumo.species(kind)]
            assert any(sumo.scaled(b, diff) >> 4 > 255 for b in row), kind


def test_training_raises_hp_by_a_tenth_of_its_byte_in_percent():
    assert sumo.bout_hp(1000, 250) == 1250
    assert sumo.bout_hp(1000, 9) == 1000


def test_a_smaller_bug_loses_the_same_percentage(tables):
    kind = sumo.TYPES["saw"]
    typical = tables.typical[sumo.species(kind)]
    base = tables.stats(kind, typical)
    assert tables.stats(kind, typical - 5).hp < base.hp < tables.stats(kind, typical + 5).hp


def test_record_places_each_field_where_the_cage_screen_reads_it():
    # Measured on Beetle: a record 1b 44 03 02 04 01 0e 03 showed "BIG! saw stag 4, caught
    # August 1, 68 mm, 14 wins 3 losses" (research/sumo.md).
    bug = sumo.Bug(0x1B, 0x44, number=4, day=1, wins=14, losses=3, training=250)
    assert bug.record()[:2] == bytes([0x1B, 0x44])
    assert bug.record()[4:9] == bytes([4, 1, 14, 3, 250])
    assert len(bug.record()) == sumo.RECORD


def _condition(event: str) -> str:
    for line in (REPO_ROOT / "research" / "data" / "scenes.tsv").read_text().splitlines():
        cells = line.split("\t")
        if cells[0] == event:
            return cells[9]
    raise AssertionError(event)


def _holds(condition: str, day: int, hour: int, flags: dict[int, int]) -> bool:
    expr = condition.replace("&", " and ").replace("|", " or ")
    expr = re.sub(r"flag\[(\d+)\]", lambda m: f"flags.get({m.group(1)}, 0)", expr)
    return eval(expr, {}, {"day": day, "hour": hour, "flags": flags})


def test_the_sumo_save_meets_the_desk_events_condition(tables):
    """E4025 (the secret base's desk, the only way into mode 7) must hold on the morning the
    sumo save wakes on -- its condition read from the tracked scene table."""
    entry = _entry("sumo-maxed-cage")
    morning = 7
    assert _holds(_condition("E4025"), entry.saved_day + 1, morning, dict(entry.flags))
    assert 0 < len(entry.cage) <= sumo.CAGE_SLOTS


def test_the_sumo_saves_cage_is_written_where_the_game_reads_it(tables):
    regions = REGIONS
    base = S.SaveBody(regions, bytes(sum(r.length for r in regions)))
    entry = _entry("sumo-maxed-cage")
    cage = S.edited_body(base, entry, tables).read(sumo.CAGE, sumo.RECORD * sumo.CAGE_SLOTS)
    records = [cage[sumo.RECORD * i : sumo.RECORD * (i + 1)] for i in range(sumo.CAGE_SLOTS)]
    for (kind, _), record in zip(entry.cage, records, strict=False):
        # type, the largest size its species allows, full training, caught on the save's day
        assert (record[0], record[1], record[8]) == (kind, tables.max_size(kind), 250)
        assert record[5] == entry.saved_day
    assert all(r[0] == sumo.EMPTY for r in records[len(entry.cage) :])


def test_a_bug_past_its_max_size_is_predicted_with_the_wrapped_byte(tables):
    """The game stores STR and the DEFs as `(char)(v >> 4)`: past `max_size` they wrap."""
    kind = sumo.TYPES["giant"]
    over = tables.max_size(kind) + 1
    stats = tables.stats(kind, over)
    assert all(0 <= s < 256 for s in (stats.strength, *stats.defence))
    assert stats.strength < tables.stats(kind, over - 1).strength


@pytest.mark.parametrize("text", ["rhino:256", "rhino:-1"])
def test_a_size_that_is_not_a_byte_is_refused(text):
    with pytest.raises(ValueError):
        sumo.parse_bug(text)


def test_a_short_cage_marks_every_other_slot_empty():
    cage = sumo.cage_bytes([sumo.Bug(30, 60)])
    assert len(cage) == sumo.RECORD * sumo.CAGE_SLOTS
    assert [cage[sumo.RECORD * i] for i in range(sumo.CAGE_SLOTS)] == [30] + [sumo.EMPTY] * 9


def _entry(name: str) -> S.CorpusEntry:
    (entry,) = [e for e in S.corpus() if e.name == name]
    return entry


def test_the_mantis_save_opens_the_desk_and_no_secret_weapon_scene_preempts_it():
    """At the secret base the morning it wakes on, `E4025` (the desk) must hold, and neither
    `E1650` nor `E1750` -- the auto scenes of Guts's secret-weapon chain -- may fire first."""
    entry = _entry("sumo-mantis-ready")
    day, flags = entry.saved_day + 1, dict(entry.flags)
    assert _holds(_condition("E4025"), day, 7, flags)
    assert not _holds(_condition("E1650"), day, 7, flags)
    assert not _holds(_condition("E1750"), day, 7, flags)


def test_the_shortcut_save_opens_the_shortcut_and_does_not_replay_its_scene():
    entry = _entry("shortcut-open")
    day, flags = entry.saved_day + 1, dict(entry.flags)
    assert _holds(_condition("E4057"), day, 7, flags)  # A07's mouth of the shortcut -> E02
    assert not _holds(_condition("E1754"), day, 7, flags)


@pytest.mark.parametrize(
    ("name", "stage"),
    [("sumo-mantis-ready", sumo.STAGE_MANTIS), ("shortcut-open", sumo.STAGE_SHORTCUT)],
)
def test_the_story_saves_carry_their_sumo_stage_into_the_body(tables, name, stage):
    regions = REGIONS
    base = S.SaveBody(regions, bytes(sum(r.length for r in regions)))
    assert S.edited_body(base, _entry(name), tables).read(sumo.STAGE)[0] == stage


def test_a_loaded_key_is_taken_back_to_the_disc_key():
    """In RAM `start`/`end` carry the XAM's disc address and `+10` is 1 (measured: `E2405.0`'s
    disc key 66682..67498 played as 121099..121915 with the XAM at 54417)."""
    loaded = struct.pack("<IIBBH", 121099, 121915, 10, 2, voice.RELOCATED)
    want = {"start": 66682, "end": 67498, "channel": 10, "file": 2}
    assert voice.disc_key(loaded, 54417) == want
    unloaded = struct.pack("<IIBBH", 66682, 67498, 10, 2, 0)
    assert voice.disc_key(unloaded, 54417)["start"] == 66682
