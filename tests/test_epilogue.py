"""`boku.epilogue`: what `ENDOTI` shows while an epilogue's clip plays (PLAN `VO-09`)."""

from __future__ import annotations

from itertools import pairwise

from boku import epilogue
from boku.voice import SAMPLES_PER_SECTOR, VSYNC_HZ, XA_RATE, xch_nodes

PICTURE = epilogue.Picture(ending=0, first_out=600, second_in=690, card=1290, card_out=1590)


def test_a_pictures_phases_tile_the_epilogue_from_its_opening_to_the_hand_over():
    phases = PICTURE.phases
    assert [name for name, _, _ in phases] == [
        epilogue.FIRST_STILL,
        epilogue.BLACK,
        epilogue.SECOND_STILL,
        epilogue.CARD,
    ]
    assert phases[0][1] == 0 and phases[-1][2] == PICTURE.end == 1590 + epilogue.HAND_OVER
    assert all(before[2] == after[1] for before, after in pairwise(phases))


def test_what_is_showing_changes_on_the_thresholds_vsync():
    assert PICTURE.showing(0) == epilogue.FIRST_STILL
    assert PICTURE.showing(600 + epilogue.FADE - 1) == epilogue.FIRST_STILL
    assert PICTURE.showing(600 + epilogue.FADE) == epilogue.BLACK
    assert PICTURE.showing(1289) == epilogue.SECOND_STILL
    assert PICTURE.showing(1290) == epilogue.CARD
    assert PICTURE.showing(10**6) == epilogue.CARD


def test_the_discs_table_gives_every_epilogue_clip_a_picture_its_clip_covers(archive):
    """`ENDOTI.OVL`'s own thresholds: one picture per epilogue clip, the card inside the
    clip and the hand-over near its end -- which is how a wrong address would show."""
    pictures = epilogue.pictures(archive)
    clips = xch_nodes(archive)
    assert sorted(pictures) == list(
        range(epilogue.FIRST_CLIP, epilogue.FIRST_CLIP + epilogue.ENDINGS)
    )
    for clip, picture in pictures.items():
        assert picture.ending == clip - epilogue.FIRST_CLIP
        assert 0 < picture.first_out < picture.second_in < picture.card < picture.card_out
        length = clips[clip].sectors * SAMPLES_PER_SECTOR * VSYNC_HZ / XA_RATE
        assert picture.card < length
        assert abs(picture.end - length) < VSYNC_HZ, "the game leaves as the clip ends"
