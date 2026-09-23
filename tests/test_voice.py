"""`boku.voice` -- the clip arithmetic, the channel filter, the table merge, the ASR reader.

No disc needed. Each case sits at the narrowest input that shows its harm:

* the channel filter against a slice where the clip's own channel is interleaved with a
  neighbour's audio AND a video sector on the same channel number, because either one
  kept would splice another voice into the clip and still decode to plausible audio;
* the frame arithmetic at the frame boundaries, because a cue one frame early or late is
  the off-by-one a 1-based header number invites;
* the merge against a table whose hand column is already filled, because a regeneration
  that blanks it destroys the listening pass.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from boku.disc import RAW_SECTOR_SIZE, SUBHEADER_OFFSET
from boku.voice import (
    COLUMNS,
    INTERLEAVE,
    VoiceError,
    VoiceNode,
    build_tsv,
    channel_sectors,
    header_frame,
    parse_whisper_json,
    parse_xch,
    read_hand_columns,
)


def _node(line_id: str = "E0184.2", start: int = 88372, end: int = 88980, **kw) -> VoiceNode:
    fields = dict(
        line_id=line_id,
        node=f"{line_id}@9E",
        scene=int(line_id[1:5]),
        day=1,
        speaker="VOICE",
        slot=255,
        file=2,
        channel=start % INTERLEAVE,
        start=start,
        end=end,
        copies=1,
    )
    fields.update(kw)
    return VoiceNode(**fields)


def test_a_clip_is_its_own_channels_sectors_first_to_last_inclusive() -> None:
    """E0184.2's key spans 88372..88980 on channel 4: 39 of its own sectors, and ffmpeg
    decoded exactly 4.16 s from them (measured 2026-09-22, research/tooling-setup.md § XA)."""
    node = _node()
    assert node.sectors == 39
    assert node.seconds == pytest.approx(4.16, abs=1e-9)


def test_a_zero_length_key_is_one_sector_not_zero() -> None:
    """Three keys on the disc have end == start; the player still reads that one sector."""
    assert _node(start=88936, end=88936).sectors == 1


def test_a_key_whose_span_is_not_whole_channel_strides_is_refused() -> None:
    with pytest.raises(VoiceError, match="16"):
        _ = _node(start=100, end=117).sectors


def _sector(file_no: int, channel: int, submode: int, tag: int) -> bytes:
    raw = bytearray(RAW_SECTOR_SIZE)
    raw[SUBHEADER_OFFSET : SUBHEADER_OFFSET + 4] = bytes([file_no, channel, submode, 0])
    raw[100] = tag
    return bytes(raw)


def test_the_channel_filter_keeps_only_this_files_audio_on_this_channel() -> None:
    audio, video = 0x64, 0x62  # real-time|form2|audio, real-time|form2|video
    sectors = [
        _sector(2, 4, audio, 1),  # ours
        _sector(3, 4, audio, 2),  # same channel, the other XA file
        _sector(2, 5, audio, 3),  # same file, the neighbouring channel
        _sector(2, 4, video, 4),  # same file and channel, not audio
        _sector(2, 4, audio, 5),  # ours
    ]
    kept = channel_sectors(b"".join(sectors), file_no=2, channel=4)
    assert len(kept) == 2 * RAW_SECTOR_SIZE
    assert [kept[100], kept[RAW_SECTOR_SIZE + 100]] == [1, 5]


@pytest.mark.parametrize(
    ("ms", "frame"),
    # Audio t = 0 is extent sector 7, 7/150 s after frame 1 appears, so frame 2 is on
    # screen from 20 ms; at 820 ms (frame 14 begins) float seconds x 15 floors a frame early.
    [(0, 1), (19, 1), (20, 2), (819, 13), (820, 14)],
)
def test_the_header_frame_at_a_time_counts_from_the_extent_and_is_one_based(
    ms: int, frame: int
) -> None:
    """research/movies.md § 1: STR header frame numbers start at 1 for the first slot."""
    assert header_frame(ms) == frame


def test_a_regeneration_keeps_the_hand_columns_by_line_id() -> None:
    first = build_tsv([_node("E0184.2"), _node("E0202.6", start=88726, end=89190)])
    lines = first.splitlines()
    said = COLUMNS.index("said")
    for n, line in enumerate(lines):
        if line.startswith("E0202.6\t"):
            cells = line.split("\t")
            cells[said] = "a sigh"
            lines[n] = "\t".join(cells)
    again = build_tsv(
        [_node("E0202.6", start=88726, end=89190), _node("E0184.2")], previous="\n".join(lines)
    )
    kept = read_hand_columns(again)
    assert kept["E0202.6"]["said"] == "a sigh"
    assert kept["E0184.2"]["said"] == ""


def test_a_row_with_a_tab_typed_into_a_hand_column_is_refused() -> None:
    table = build_tsv([_node()])
    broken = table.rstrip("\n") + "\textra\n"
    with pytest.raises(VoiceError, match="columns"):
        read_hand_columns(broken)


def test_rows_sharing_one_clip_name_each_other() -> None:
    shared = [_node("E1203.2", start=87733, end=88789), _node("E1203.3", start=87733, end=88789)]
    rows = {
        line.split("\t")[0]: line.split("\t")
        for line in build_tsv(shared).splitlines()
        if line.startswith("E")
    }
    same = COLUMNS.index("same_clip_as")
    assert rows["E1203.2"][same] == "E1203.3"
    assert rows["E1203.3"][same] == "E1203.2"


def test_whisper_segments_carry_seconds_and_one_based_frames() -> None:
    """The shape `whisper-cli -oj` writes: offsets in milliseconds."""
    doc = {
        "transcription": [
            {"offsets": {"from": 0, "to": 1990}, "text": " あ"},
            {"offsets": {"from": 2000, "to": 4000}, "text": "い "},
        ]
    }
    segments = parse_whisper_json(json.dumps(doc))
    assert [(s.start, s.end, s.text) for s in segments] == [(0.0, 1.99, "あ"), (2.0, 4.0, "い")]
    assert [(s.start_frame, s.end_frame) for s in segments] == [(1, 31), (31, 61)]
    boundary = parse_whisper_json(
        json.dumps({"transcription": [{"offsets": {"from": 820, "to": 820}, "text": "x"}]})
    )
    assert boundary[0].start_frame == 14


def test_a_g_xa_clips_record_reads_as_the_event_key_layout() -> None:
    """`BOKU_XA.XCH` is `u32 count` then 12-byte keys; `slot` is None, as it has no speaker."""
    blob = struct.pack("<I", 2) + struct.pack("<IIBBH", 1144, 1304, 8, 3, 0)
    blob += struct.pack("<IIBBH", 89010, 93250, 2, 3, 0)
    nodes = parse_xch(blob)
    assert [(n.line_id, n.start, n.end, n.channel, n.file, n.slot) for n in nodes] == [
        ("XCH.00", 1144, 1304, 8, 3, None),
        ("XCH.01", 89010, 93250, 2, 3, None),
    ]


def test_a_g_xa_clips_blob_whose_size_disagrees_with_its_count_is_refused() -> None:
    with pytest.raises(VoiceError, match="12-byte"):
        parse_xch(struct.pack("<I", 2) + bytes(12))


def test_a_failed_decode_leaves_no_wav_behind(tmp_path, monkeypatch) -> None:
    """The decoders skip a WAV that exists, so a half-written one would never be redone."""
    import boku.voice as voice

    def dies_midway(command: list[str], what: str) -> str:
        Path(command[-1]).write_bytes(b"RIFF half")
        raise VoiceError("ffmpeg died")

    monkeypatch.setattr(voice, "_run", dies_midway)
    monkeypatch.setattr(voice, "_ffmpeg", lambda: "ffmpeg")
    out = tmp_path / "xa00001-00017.wav"
    with pytest.raises(VoiceError):
        voice.xa_to_wav(b"\0" * RAW_SECTOR_SIZE, out, tmp_path)
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_out_inside_the_repo_but_outside_work_is_refused(tmp_path, capsys) -> None:
    """work/voice holds the game's audio and Japanese; anywhere else in the repo is tracked."""
    from boku import REPO_ROOT
    from boku.voice import main_voice

    status = main_voice(
        tmp_path,
        tmp_path / "no-image",
        REPO_ROOT / "research" / "voice-out",
        tsv_only=False,
        tsv_path=tmp_path / "v.tsv",
        transcribe_too=False,
    )
    assert status == 2
    assert "not under work/" in capsys.readouterr().err
    assert not (REPO_ROOT / "research" / "voice-out").exists()
    assert not (tmp_path / "v.tsv").exists()


def test_a_movie_whose_audio_starts_elsewhere_is_refused() -> None:
    """Every cue frame assumes audio t = 0 is extent sector 7; one sector off shifts cues."""
    from boku.voice import MOVIE_AUDIO_SECTOR, _check_audio_lead

    def extent(first_audio: int) -> bytes:
        return b"".join(_sector(1, 1, 0x64 if k == first_audio else 0x62, 0) for k in range(10))

    _check_audio_lead("M00", extent(MOVIE_AUDIO_SECTOR))
    with pytest.raises(VoiceError, match="first audio sector is 6"):
        _check_audio_lead("M00", extent(MOVIE_AUDIO_SECTOR - 1))
