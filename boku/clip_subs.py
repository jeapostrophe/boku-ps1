"""`translation/clips.txt`: subtitles for the clips native code plays (`g_xa_clips`, `XCH.nn`).

The format is `translation/README.md` § "clips.txt" -- a day file's rows keyed `XCH.nn`, read
by the day files' own loader (`boku.translation.SampleScenes`). This module is the one place
that turns those rows into what the executable draws: dialogue words, paged against the
clip's length exactly as a `(voice only)` event row is (`boku.layout.lay_out_subtitle`), for
`boku.movie_block`'s clip section. The image build (`tools/vwf/build_prototype.py`) and the
lint (`boku lint`) both come through `lay_out_clips`, so a row the lint passes is one the
build writes as measured.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from boku import REPO_ROOT
from boku.layout import DIALOGUE_BAND, BoxSpec, Encoder, lay_out_subtitle
from boku.translation import SampleScenes, TranslationEntry
from boku.voice import VoiceNode, sector_ticks

CLIP_FILE = REPO_ROOT / "translation" / "clips.txt"
CLIP_ID = re.compile(r"XCH\.(\d{2})")
OUTSIDE_SUMO = frozenset({34, *range(41, 46)})
"""The clips known to play outside bug sumo: the bedtime clip in movie mode and the five
epilogues in `ENDOTI` (research/event-scripts.md § Native clips). Every other clip is laid
out for bug sumo's pen, which is the safe side: a clip laid out narrower than its mode needs
is only shorter lines."""
SUMO_PEN_INDENT = 42
"""Pixels bug sumo's subtitle pen starts right of the dialogue pen (`asm/voice.asm`,
`voice_sub_show`): clear of Boku's 44 x 44 portrait at (18, 161), which a bout draws in
front of the band's first line (research/sumo.md § Subtitles)."""


def clip_box(index: int, box: BoxSpec = DIALOGUE_BAND) -> BoxSpec:
    """The box clip `index` is laid out in: `box`, or in bug sumo `box` less the indent."""
    if index in OUTSIDE_SUMO:
        return box
    return replace(
        box,
        width=box.width - SUMO_PEN_INDENT,
        guarded_width=max(box.guarded_width - SUMO_PEN_INDENT, 0),
        name=f"{box.name} in bug sumo",
    )


@dataclass(frozen=True)
class ClipProblem:
    line_id: str
    origin: str
    message: str


def read(path: Path = CLIP_FILE) -> tuple[list[TranslationEntry], list[str]]:
    """The rows that carry English, and what the loader could not read. A missing file is
    no rows: a checkout that has not started on the clips builds as before."""
    if not Path(path).is_file():
        return [], []
    source = SampleScenes.from_paths([Path(path)])
    return list(source), list(source.problems)


def lay_out_clips(
    entries: Sequence[TranslationEntry],
    clips: Sequence[VoiceNode],
    encoder: Encoder,
    box: BoxSpec = DIALOGUE_BAND,
) -> tuple[dict[int, tuple[int, ...]], list[ClipProblem]]:
    """Each row's words, by clip index, and every problem: an id that is not `XCH.nn` for a
    clip of `clips` (`boku.voice.xch_nodes`), a menu row, or what the band cannot draw."""
    words: dict[int, tuple[int, ...]] = {}
    problems: list[ClipProblem] = []
    for entry in entries:
        match = CLIP_ID.fullmatch(entry.line_id)
        if not match or int(match[1]) >= len(clips):
            problems.append(
                ClipProblem(
                    entry.line_id,
                    entry.origin,
                    f"not a clip: ids are XCH.00-XCH.{len(clips) - 1:02d}, the records of "
                    f"BOKU_XA.XCH (research/data/voice-only.tsv)",
                )
            )
            continue
        if entry.is_select:
            problems.append(ClipProblem(entry.line_id, entry.origin, "a clip is not a menu"))
            continue
        index = int(match[1])
        ticks = sector_ticks(clips[index].sectors)
        laid = lay_out_subtitle(entry.line_id, entry.pages, ticks, encoder, clip_box(index, box))
        problems += [ClipProblem(entry.line_id, entry.origin, p) for p in laid.problems]
        if not laid.problems:
            words[index] = laid.words
    return words, problems
