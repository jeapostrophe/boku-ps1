"""`research/data/voice-only.tsv` against the disc it was generated from. Skips without one.

The regeneration diff is the gate on the table; the other two tests are the reconciliation
`research/voice-only.md` quotes, each counted by a walk that does not go through
`boku.voice` -- so the table cannot agree with itself and call that a check.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from boku.archive import Archive
from boku.disc import RAW_SECTOR_SIZE, DiscImage
from boku.events import Block, EventWorld, iter_blocks
from boku.voice import (
    VOICE_TSV,
    XAM_PATH,
    all_nodes,
    channel_sectors,
    main_voice,
    voice_nodes,
)


def test_tracked_voice_only_tsv_is_what_this_import_generates(
    disc_dir: Path, tmp_path: Path
) -> None:
    """Copied in first, because the hand columns are carried across a regeneration."""
    out = tmp_path / VOICE_TSV.name
    shutil.copyfile(VOICE_TSV, out)
    status = main_voice(
        disc_dir,
        tmp_path / "no-image",
        tmp_path / "unused",
        tsv_only=True,
        tsv_path=out,
        transcribe_too=False,
    )
    assert status == 0
    assert out.read_text(encoding="utf-8") == VOICE_TSV.read_text(encoding="utf-8"), (
        f"{VOICE_TSV.name} is not what this import generates today: run "
        f"`./make.sh voice-only --tsv`"
    )


def test_the_rows_are_every_null_text_entry_on_the_disc(
    archive: Archive, event_world: EventWorld
) -> None:
    """One row per null-text message, and `copies` summed is every physical null entry.

    Counted straight off the stored blocks: a null text entry is an odd entry >= 4 whose
    offset is 0. That is the figure `research/text-format.md` quotes for the XA opcode.
    """
    physical = 0
    distinct = set()
    for inst in iter_blocks(archive):
        block = Block(inst.data)
        for i in range(block.message_count):
            if block.offsets[4 + 2 * i] == 0:
                physical += 1
                distinct.add(f"E{inst.event_id:04d}.{i}")
    nodes = voice_nodes(event_world)
    assert sorted(n.line_id for n in nodes) == sorted(distinct)
    assert sum(n.copies for n in nodes) == physical


def test_every_key_names_exactly_its_own_sectors_on_the_image(
    real_image: Path, archive: Archive, event_world: EventWorld
) -> None:
    """The channel filter against the image, for the event keys and `g_xa_clips` both: a
    key whose span held a sector too few or too many of its channel would decode a clip
    cut short or spliced with its neighbour."""
    nodes = all_nodes(archive, event_world)
    with DiscImage(real_image) as image:
        xam = next(e for e in image.walk() if e.path == XAM_PATH)
        for node in {n.clip: n for n in nodes}.values():
            raw = image.read_raw(xam.lba + node.start, node.end - node.start + 1)
            got = len(channel_sectors(raw, file_no=node.file, channel=node.channel))
            assert got == node.sectors * RAW_SECTOR_SIZE, node.line_id
