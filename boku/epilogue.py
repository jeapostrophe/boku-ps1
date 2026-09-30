"""What the screen shows while an epilogue's clip plays (PLAN `VO-09`).

`ENDOTI` plays `XCH.41 + n` for ending `n` and steps its pictures on a counter of its own,
one a vsync, against four thresholds it holds per ending (`research/event-scripts.md` § The
epilogue's clock): the first still, the second, then the production card on black, then the
hand-over to the save prompt. A subtitle page that is still up when the second still gives
way to the card sits under a picture it does not belong to, so the clip subtitles are laid
out against these numbers (`boku.clip_subs`), and the reader draws each page over the
picture it meets (`boku.reader`). They are read from the contributor's own `ENDOTI.OVL`,
never retyped here.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from boku.archive import Archive, ArchiveError


class EpilogueError(Exception):
    """An `ENDOTI.OVL` that is not the one this module was written against."""


OVERLAY = "ENDOTI.OVL"
STATE = 0x8007A120
COUNTER = 0x8007A124
"""`ENDOTI`'s state byte and its `u32` counter, for a tool that watches it run."""
THRESHOLDS = 0x8007A0C4
"""`ENDOTI`'s table: per ending, four `u32` counts (its update indexes it by
`0x80035F42 << 4`)."""
ENDINGS = 5
FIRST_CLIP = 41
"""`ENDOTI`'s start plays clip `0x29 + n` (`0x80079BE4`)."""
FADE = 16
"""Vsyncs each of `ENDOTI`'s fades takes (the `0x10` it passes `0x80013EA4`)."""
HAND_OVER = 120
"""Vsyncs from the last threshold to the mode change (`0x80079F60`: `+ 0x78`)."""
OPENS_AT = 1
"""What the counter reads on the first frame the subtitle is up: `ENDOTI`'s start plays the
clip, and the update that follows counts one (measured on Beetle)."""
FIRST_STILL, BLACK, SECOND_STILL, CARD = (
    "the first still",
    "black",
    "the second still",
    "the production card",
)
"""What `ENDOTI` has on the screen, in order."""
SHOWN_IN_STATE = {0: FIRST_STILL, 1: BLACK, 2: SECOND_STILL, 4: CARD}
"""By the state byte; nothing enters state 3."""
LEAD = 5
"""Vsyncs from the subtitle's opening to the first sample of the clip's audio: the drive is
already at the clip when `xa_play` is called (measured on Beetle, stock and patched:
`research/event-scripts.md` § The epilogue's clock)."""


@dataclass(frozen=True)
class Picture:
    """One ending's thresholds, as vsyncs after its subtitle opens."""

    ending: int
    first_out: int
    """The first still starts to fade out; it is gone `FADE` later."""
    second_in: int
    """The second still starts to fade in."""
    card: int
    """The second still gives way, at once, to the production card on black."""
    card_out: int
    """The card starts to fade out."""

    @property
    def end(self) -> int:
        """The game leaves `ENDOTI`, and whatever subtitle is up comes down."""
        return self.card_out + HAND_OVER

    @property
    def phases(self) -> tuple[tuple[str, int, int], ...]:
        """`(what is on screen, from, to)` over the whole epilogue, fades included in the
        picture they belong to; between the stills the screen is black."""
        return (
            (FIRST_STILL, 0, self.first_out + FADE),
            (BLACK, self.first_out + FADE, self.second_in),
            (SECOND_STILL, self.second_in, self.card),
            (CARD, self.card, self.end),
        )

    def showing(self, at: int) -> str:
        """What is on screen `at` vsyncs after the subtitle opens."""
        return next((name for name, _, to in self.phases if at < to), CARD)


def pictures(archive: Archive) -> dict[int, Picture]:
    """Each epilogue clip's picture, by clip index (`XCH.nn`)."""
    try:
        raw = archive.overlay_bytes(OVERLAY, THRESHOLDS, ENDINGS * 16)
    except ArchiveError as error:
        raise EpilogueError(str(error)) from error
    if len(raw) != ENDINGS * 16:
        raise EpilogueError(f"{OVERLAY} ends before its table at 0x{THRESHOLDS:08X}")
    out = {}
    for ending in range(ENDINGS):
        counts = struct.unpack_from("<4I", raw, ending * 16)
        if list(counts) != sorted(counts):
            raise EpilogueError(
                f"{OVERLAY} at 0x{THRESHOLDS:08X}: ending {ending}'s thresholds {counts} do "
                f"not rise; this is not the table research/event-scripts.md describes"
            )
        out[FIRST_CLIP + ending] = Picture(ending, *(count - OPENS_AT for count in counts))
    return out
