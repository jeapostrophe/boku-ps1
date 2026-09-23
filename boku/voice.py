"""Speech with no text on the disc: the voice-only clips and the voiced movies (PLAN `VO-01`,
`FMV-02`).

    ./make.sh voice-only --tsv          regenerate research/data/voice-only.tsv only
    ./make.sh voice-only                ... and decode every clip to work/voice/clips/*.wav
    ./make.sh voice-only --transcribe   ... and run Whisper over them, and over the voiced
                                        movies' audio, into work/voice/

A voice-only clip is an `XA` instruction (`research/event-scripts.md` § Opcode table): it
plays a voice key and names a message whose text entry is null. The table has one row per
`XA` instruction, which is one row per null-text message -- each is named by exactly one
`XA` and nothing else (`research/text-format.md`) -- plus one row per `g_xa_clips` record
(`BOKU_XA.XCH`, `XCH.nn`), the clips native code plays.

A key names sectors of `__STR/BOKU_XA.XAM`, a 16-way interleave: the clip is the sectors
from `start` to `end` inclusive whose subheader carries the key's file and channel.
`channel_sectors` picks those out of the raw span, and ffmpeg's `psxstr` demuxer decodes
them (`research/tooling-setup.md` § XA, which is also the home of the Whisper install).

**Everything under `work/voice/` is the game's audio or a transcript of it, and is never
tracked** (CLAUDE.md § "This repo is public"). The tracked table carries ids, sector
numbers and our own English words about each clip; no Japanese.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import accumulate, pairwise
from pathlib import Path

from boku import REPO_ROOT
from boku.archive import DEFAULT_DISC_DIR, Archive, ArchiveError
from boku.disc import RAW_SECTOR_SIZE, SUBHEADER_OFFSET, SUBMODE_AUDIO, DiscError, DiscImage
from boku.events import (
    OP_XA,
    TEXT_OPS,
    VOICE_KEY_SIZE,
    Block,
    EventError,
    EventWorld,
    decode_voice_key,
)
from boku.extract import SCRIPT_DIR_NAME
from boku.movies import (
    DEFAULT_IMAGE,
    FPS,
    MOVIES_TSV,
    SECTORS_PER_FRAME,
    iki_entries,
    slice_movie,
)
from boku.script_store import StoreMissing, load_store

VOICE_TSV = REPO_ROOT / "research" / "data" / "voice-only.tsv"
DEFAULT_OUT_DIR = REPO_ROOT / "work" / "voice"
XAM_PATH = "/__STR/BOKU_XA.XAM"

INTERLEAVE = 16
"""`BOKU_XA.XAM` is 16-way interleaved: `start % 16 == channel` for every key, and a clip's
own sectors are 16 apart (`research/event-scripts.md` § Voice key)."""

XA_RATE = 37_800
SAMPLES_PER_SECTOR = 4032
"""4-bit mono (coding byte 0): 18 sound groups x 224 samples a sector. Measured, not assumed:
ffmpeg decodes E0184.2's 39 sectors to 4.160 s = 39 x 4032 / 37800."""

TSV_HEADER_COMMENT = """\
# The voice-only clips: one row per `XA` instruction -- a voice played with no text on the
# screen -- then one per `g_xa_clips` record (`XCH.nn`), which native code plays. Generated
# by `./make.sh voice-only --tsv`; research/voice-only.md says where each column comes from
# and how the rows reconcile with the counts quoted elsewhere.
#
# said and notes are the only hand-written columns, and a regeneration carries them across
# unchanged by line_id. said is `wordless` or an English gist of what is said -- never the
# Japanese, which lives only in work/voice/ (CLAUDE.md).
"""

COLUMNS = (
    "line_id",
    "node",
    "day",
    "speaker",
    "slot",
    "xa_file",
    "channel",
    "start",
    "end",
    "sectors",
    "seconds",
    "copies",
    "same_clip_as",
    "said",
    "notes",
)
HAND_COLUMNS = ("said", "notes")


class VoiceError(Exception):
    """Something this step cannot do, for a reason the message states in full."""


def own_sectors(start: int, end: int, where: str) -> int:
    """A clip's own sectors, `start` and `end` included (a key with `end == start` still
    plays one)."""
    span = end - start
    if span < 0 or span % INTERLEAVE:
        raise VoiceError(
            f"{where}: key {start}..{end} is not a whole number of "
            f"{INTERLEAVE}-sector channel strides"
        )
    return span // INTERLEAVE + 1


# --- subtitle timing (VO-02) ------------------------------------------------------------------

TICK_HZ = 30
"""`event_update` runs every other vsync, and a page's `0x8002` operand counts its calls
(`research/renderer-runtime.md` § Q7)."""

SEEK_TICKS = 11
"""What the first page waits beyond its share: the text is up the tick the `XA` opcode
runs, the voice only once the drive has seeked (measured once, `research/event-scripts.md`
§ Voice-only entries)."""


def clip_ticks(key: bytes) -> int:
    """How many event ticks the clip a 12-byte voice key names plays for."""
    k = decode_voice_key(key)
    sectors = own_sectors(k["start"], k["end"], "a voice key")
    return round(sectors * SAMPLES_PER_SECTOR * TICK_HZ / XA_RATE)


def subtitle_waits(pages: Sequence[str], ticks: int) -> list[int]:
    """The `0x8002` operand after each page but the last: its share of the clip.

    Pages share the clip in proportion to their length in characters -- the only measure of
    how long a line takes to say that a translation carries -- and the first also covers
    `SEEK_TICKS`. The last page needs no timer: the subtitle closes when the clip stops.
    Every wait is at least 1, because `dialog_draw` never counts a zero down.
    """
    weights = [max(1, len(page)) for page in pages]
    bounds = [round(ticks * shown / sum(weights)) for shown in accumulate(weights, initial=0)]
    waits = [end - begin for begin, end in pairwise(bounds[:-1])]
    if waits:
        waits[0] += SEEK_TICKS
    return [max(1, wait) for wait in waits]


# --- the inventory ------------------------------------------------------------------------------


@dataclass(frozen=True)
class VoiceNode:
    """One `XA` instruction and the clip its key names."""

    line_id: str
    node: str
    scene: int | None
    """The event id whose `XA` this is; `None` for a `g_xa_clips` record."""
    day: int | None
    speaker: str
    slot: int | None
    """The mouth-flap operand; `None` for a `g_xa_clips` record, which has none."""
    file: int
    channel: int
    start: int
    end: int
    copies: int
    """Physical block copies holding this null entry -- the same event stored in several map
    variants. Summed over the event rows it is the count of null-text entries on the disc."""

    @property
    def sectors(self) -> int:
        return own_sectors(self.start, self.end, self.line_id)

    @property
    def seconds(self) -> float:
        return self.sectors * SAMPLES_PER_SECTOR / XA_RATE

    @property
    def clip(self) -> str:
        """The clip's file name: several lines play one key, and it is decoded once. The
        channel is `start % INTERLEAVE`, so file, start and end are the whole key."""
        return f"xa{self.file}-{self.start:05d}-{self.end:05d}"


def voice_nodes(world: EventWorld) -> list[VoiceNode]:
    """Every `XA` instruction on the disc, in event and program order."""
    out: list[VoiceNode] = []
    for sc in world.scenes.values():
        xas = [p for p in sorted(sc.ins) if sc.ins[p].op == OP_XA]
        if not xas:
            continue
        copies = sum(1 for inst in sc.event.instances if not Block(inst.data).is_stub)
        day = world.when(sc)[0]
        for p in xas:
            i = sc.ins[p]
            raw_key, text = sc.messages[i.message_index]
            key = world.voice_key(raw_key)
            line_id = f"E{sc.id:04d}.{i.message_index}"
            if key is None or text is not None:
                raise VoiceError(
                    f"{line_id}: an XA names a message with "
                    f"{'no voice key' if key is None else 'text'} -- research/text-format.md "
                    f"says every XA names a keyed, null-text message"
                )
            speaker, _slot = world.speaker(sc, p)
            out.append(
                VoiceNode(
                    line_id=line_id,
                    node=sc.node_id(p),
                    scene=sc.id,
                    day=day,
                    speaker=speaker,
                    slot=i.slot,
                    file=key["file"],
                    channel=key["channel"],
                    start=key["start"],
                    end=key["end"],
                    copies=copies,
                )
            )
    return out


XCH_MEMBER = "BOKU_XA.XCH"


def xch_nodes(archive: Archive) -> list[VoiceNode]:
    """`g_xa_clips`: the clips native code plays by index (`research/loading-and-memory.md`).
    The minigame's voices, the first night's narration and the five epilogues are here
    (`research/voice-only.md`)."""
    return parse_xch(archive.blob(archive.member(XCH_MEMBER)))


def parse_xch(blob: bytes) -> list[VoiceNode]:
    """`u32 count`, then `count` 12-byte keys in the event voice key's layout."""
    (count,) = struct.unpack_from("<I", blob, 0)
    if len(blob) != 4 + VOICE_KEY_SIZE * count:
        raise VoiceError(
            f"{XCH_MEMBER} is {len(blob)} bytes; a u32 count of {count} and {count} "
            f"{VOICE_KEY_SIZE}-byte records would be {4 + VOICE_KEY_SIZE * count}"
        )
    out = []
    for index in range(count):
        at = 4 + VOICE_KEY_SIZE * index
        key = decode_voice_key(blob[at : at + VOICE_KEY_SIZE])
        out.append(
            VoiceNode(
                line_id=f"XCH.{index:02d}",
                node=f"{XCH_MEMBER}[{index}]",
                scene=None,
                day=None,
                speaker="-",
                slot=None,
                copies=1,
                **key,
            )
        )
    return out


def all_nodes(archive: Archive, world: EventWorld) -> list[VoiceNode]:
    """The table's rows: every event `XA`, then every `g_xa_clips` record."""
    return voice_nodes(world) + xch_nodes(archive)


# --- research/data/voice-only.tsv ---------------------------------------------------------------


def read_hand_columns(tsv: str) -> dict[str, dict[str, str]]:
    """The hand-written columns of an existing table, by line id -- what a regeneration keeps."""
    rows = [line for line in tsv.splitlines() if line and not line.startswith("#")]
    if not rows:
        return {}
    header = rows[0].split("\t")
    kept: dict[str, dict[str, str]] = {}
    for row in rows[1:]:
        fields = row.split("\t")
        if len(fields) != len(header):
            # A tab typed into `said` would shift `notes` off the row, and the next
            # regeneration would drop it without a word.
            raise VoiceError(
                f"{VOICE_TSV.name}: a row has {len(fields)} columns and the header has "
                f"{len(header)} -- a tab in a hand-written column, most likely. The row "
                f"starts {row[:60]!r}"
            )
        by_name = dict(zip(header, fields, strict=True))
        kept[by_name["line_id"]] = {c: by_name.get(c, "") for c in HAND_COLUMNS}
    return kept


def build_tsv(nodes: list[VoiceNode], previous: str = "") -> str:
    """The whole table: derived columns regenerated, hand-written ones carried across."""
    kept = read_hand_columns(previous)
    by_clip: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        by_clip[node.clip].append(node.line_id)
    lines = [TSV_HEADER_COMMENT.rstrip("\n"), "\t".join(COLUMNS)]
    for node in nodes:
        hand = kept.get(node.line_id, {})
        others = [other for other in by_clip[node.clip] if other != node.line_id]
        lines.append(
            "\t".join(
                [
                    node.line_id,
                    node.node,
                    str(node.day or ""),
                    node.speaker,
                    "-" if node.slot is None else str(node.slot),
                    str(node.file),
                    str(node.channel),
                    str(node.start),
                    str(node.end),
                    str(node.sectors),
                    f"{node.seconds:.1f}",
                    str(node.copies),
                    ",".join(others) or "-",
                    hand.get("said", ""),
                    hand.get("notes", ""),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def write_tsv(nodes: list[VoiceNode], path: Path = VOICE_TSV) -> Path:
    previous = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(build_tsv(nodes, previous), encoding="utf-8")
    return path


# --- decoding -----------------------------------------------------------------------------------


def channel_sectors(raw: bytes, *, file_no: int, channel: int) -> bytes:
    """The raw sectors of `raw` that are audio of this XA file and channel, in order."""
    out = bytearray()
    for at in range(0, len(raw), RAW_SECTOR_SIZE):
        sub = raw[at + SUBHEADER_OFFSET : at + SUBHEADER_OFFSET + 3]
        if sub[0] == file_no and sub[1] == channel and sub[2] & SUBMODE_AUDIO:
            out += raw[at : at + RAW_SECTOR_SIZE]
    return bytes(out)


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise VoiceError("no ffmpeg on PATH: it decodes XA (research/tooling-setup.md § XA)")
    return found


def _run(command: list[str], what: str) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as missing:
        raise VoiceError(f"{what}: could not run {command[0]} -- {missing}") from None
    if result.returncode != 0:
        raise VoiceError(
            f"{what} failed (exit {result.returncode}):\n  {' '.join(command)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def _psxstr_to_wav(source: Path, out_path: Path) -> None:
    """Decode the first XA stream of raw sectors to a 16 kHz mono WAV -- what Whisper reads.

    Written under a temporary name and renamed: the decoders skip a WAV that is already
    there, so a half-written one left by a failed run would never be redone."""
    partial = out_path.with_name(f".{out_path.name}.part.wav")
    try:
        _run(
            [
                *(_ffmpeg(), "-v", "error", "-y", "-f", "psxstr", "-i", str(source)),
                *("-map", "0:a:0", "-ar", "16000", "-ac", "1", str(partial)),
            ],
            f"ffmpeg decode of {out_path.name}",
        )
        partial.replace(out_path)
    finally:
        partial.unlink(missing_ok=True)


def xa_to_wav(xa: bytes, out_path: Path, scratch: Path) -> None:
    """Raw XA sectors of one clip to a WAV."""
    source = scratch / f"{out_path.stem}.xa"
    source.write_bytes(xa)
    try:
        _psxstr_to_wav(source, out_path)
    finally:
        source.unlink(missing_ok=True)


def decode_clips(image: DiscImage, nodes: list[VoiceNode], out_dir: Path) -> list[Path]:
    """One WAV per distinct clip; a clip already decoded is left alone."""
    xam = next((e for e in image.walk() if e.path == XAM_PATH), None)
    if xam is None:
        raise VoiceError(f"no {XAM_PATH} on {image.path}: is this the right image?")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    with tempfile.TemporaryDirectory(prefix=".boku-voice-", dir=out_dir) as scratch:
        for node in nodes:
            if node.clip in written:
                continue
            path = out_dir / f"{node.clip}.wav"
            written[node.clip] = path
            if path.is_file():
                continue
            raw = image.read_raw(xam.lba + node.start, node.end - node.start + 1)
            xa = channel_sectors(raw, file_no=node.file, channel=node.channel)
            if len(xa) != node.sectors * RAW_SECTOR_SIZE:
                raise VoiceError(
                    f"{node.line_id}: the key names {node.sectors} sectors of file "
                    f"{node.file} channel {node.channel}, the image has "
                    f"{len(xa) // RAW_SECTOR_SIZE} there"
                )
            xa_to_wav(xa, path, Path(scratch))
    return list(written.values())


def voiced_movies(tsv: str) -> list[str]:
    """The movie files Jay's watch marked as having a voice (`what_it_shows` = `VOICE; ...`)."""
    rows = [line.split("\t") for line in tsv.splitlines() if line and not line.startswith("#")]
    header = rows[0]
    file_at, shows_at = header.index("file"), header.index("what_it_shows")
    return sorted({r[file_at] for r in rows[1:] if r[shows_at].startswith("VOICE")})


def decode_movie_audio(image: DiscImage, names: list[str], out_dir: Path) -> list[Path]:
    """Each voiced movie's XA audio as a 16 kHz mono WAV, whose t = 0 is `MOVIE_AUDIO_LEAD`
    after the extent's first sector; refused for a movie where that does not hold."""
    out_dir.mkdir(parents=True, exist_ok=True)
    by_name = {movie.name: movie for movie in iki_entries(image)}
    written = []
    with tempfile.TemporaryDirectory(prefix=".boku-voice-", dir=out_dir) as scratch:
        for name in names:
            path = out_dir / f"{name}.wav"
            written.append(path)
            if path.is_file():
                continue
            if name not in by_name:
                raise VoiceError(f"{MOVIES_TSV.name} names {name}, which is not on the image")
            raw = Path(scratch) / name
            slice_movie(image, by_name[name], raw)
            try:
                _check_audio_lead(name, raw.read_bytes())
                _psxstr_to_wav(raw, path)
            finally:
                raw.unlink(missing_ok=True)
    return written


def _check_audio_lead(name: str, raw: bytes) -> None:
    first = next(
        (
            k
            for k in range(len(raw) // RAW_SECTOR_SIZE)
            if raw[k * RAW_SECTOR_SIZE + SUBHEADER_OFFSET + 2] & SUBMODE_AUDIO
        ),
        None,
    )
    if first != MOVIE_AUDIO_SECTOR:
        raise VoiceError(
            f"{name}'s first audio sector is {first}, not {MOVIE_AUDIO_SECTOR}: its cue frames "
            f"would be computed from the wrong t = 0 (research/voice-only.md)"
        )


# --- transcription ------------------------------------------------------------------------------

WHISPER_MODEL_ENV = "BOKU_WHISPER_MODEL"
WHISPER_VAD_ENV = "BOKU_WHISPER_VAD"
DEFAULT_MODEL_DIR = Path.home() / "Dev/dist/whisper-models"
DEFAULT_WHISPER_MODEL = DEFAULT_MODEL_DIR / "ggml-large-v3.bin"
DEFAULT_WHISPER_VAD = DEFAULT_MODEL_DIR / "ggml-silero-v5.1.2.bin"


MOVIE_AUDIO_SECTOR = 7
"""A voiced movie's first audio sector, where ffmpeg's `psxstr` demuxer puts audio t = 0
(research/voice-only.md; `_check_audio_lead` refuses a movie where it differs)."""
MOVIE_AUDIO_LEAD = Fraction(MOVIE_AUDIO_SECTOR, FPS * SECTORS_PER_FRAME)
"""That sector's time from the extent's start, in seconds."""


def header_frame(ms: int) -> int:
    """The STR header frame on screen `ms` milliseconds into a movie's decoded audio.

    Slot j of the extent shows header frame j + 1 at 15 a second (research/movies.md § 1).
    Exact arithmetic: in floats, 820 ms lands a hair under frame 14's start and floors to 13."""
    return int((Fraction(ms, 1000) + MOVIE_AUDIO_LEAD) * FPS) + 1


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    text: str

    @property
    def start(self) -> float:
        return self.start_ms / 1000

    @property
    def end(self) -> float:
        return self.end_ms / 1000

    @property
    def start_frame(self) -> int:
        return header_frame(self.start_ms)

    @property
    def end_frame(self) -> int:
        return header_frame(self.end_ms)


def parse_whisper_json(text: str) -> list[Segment]:
    """`whisper-cli -oj`'s segments: offsets in milliseconds."""
    try:
        doc = json.loads(text)
        return [
            Segment(
                start_ms=int(seg["offsets"]["from"]),
                end_ms=int(seg["offsets"]["to"]),
                text=seg["text"].strip(),
            )
            for seg in doc["transcription"]
        ]
    except (ValueError, KeyError, TypeError) as bad:
        raise VoiceError(f"whisper-cli wrote JSON this reader does not know: {bad}") from None


def _model(env: str, default: Path) -> Path:
    chosen = os.environ.get(env)
    path = Path(chosen) if chosen else default
    if not path.is_file():
        raise VoiceError(
            f"no Whisper model at {path}: research/tooling-setup.md § XA says which one and "
            f"where it goes, or set ${env}"
        )
    return path


def transcribe(wav: Path, *, vad: bool) -> list[Segment]:
    """Japanese ASR of one WAV with whisper.cpp; the JSON is kept beside the WAV.

    `-mc 0` carries no text from one 30 s window into the next: with it on, large-v3 fell
    into repeating one line for the rest of a movie (measured on `M28`'s song). Both passes
    are wanted, because they fail differently (research/voice-only.md § The listening
    pass): without the Silero gate Whisper invents a stock line over a clip with no speech;
    with it, a shout under half a second is dropped.
    """
    whisper = shutil.which("whisper-cli")
    if whisper is None:
        raise VoiceError(
            "no whisper-cli on PATH: `brew install whisper.cpp` (research/tooling-setup.md § XA)"
        )
    stem = wav.with_suffix(".vad" if vad else "")
    command = [whisper, "-m", str(_model(WHISPER_MODEL_ENV, DEFAULT_WHISPER_MODEL))]
    command += ["-l", "ja", "-mc", "0", "-np", "-oj", "-of", str(stem), "-f", str(wav)]
    if vad:
        command += ["--vad", "-vm", str(_model(WHISPER_VAD_ENV, DEFAULT_WHISPER_VAD))]
    result = Path(f"{stem}.json")
    if not result.is_file():  # whisper-cli writes it only once it has finished
        _run(command, f"whisper-cli on {wav.name}")
    return parse_whisper_json(result.read_text(encoding="utf-8"))


def _context(
    order: list[tuple[str, str]], node: VoiceNode, lines: dict[str, str]
) -> tuple[str, str]:
    """The text lines just before and after this clip in its scene's play order, which is
    `(node id, line id)` pairs."""
    at = [node_id for node_id, _ in order].index(node.node)

    def text_near(step: int) -> str:
        k = at + step
        while 0 <= k < len(order):
            line_id = order[k][1]
            if lines.get(line_id):
                return f"{line_id} {lines[line_id]}"
            k += step
        return ""

    return text_near(-1), text_near(+1)


def _play_order(world: EventWorld, scene: int) -> list[tuple[str, str]]:
    sc = world.scenes[scene]
    return [
        (
            sc.node_id(p),
            f"E{scene:04d}.{sc.ins[p].message_index}" if sc.ins[p].op in TEXT_OPS else "",
        )
        for p in sc.play_order()
    ]


def write_listening_sheet(
    world: EventWorld,
    nodes: list[VoiceNode],
    asr: dict[str, tuple[str, str]],
    lines: dict[str, str],
    path: Path,
) -> Path:
    """One row per table row: both ASR passes beside the lines around the clip. Japanese --
    work/ only."""
    rows = ["line_id\tclip\tday\tspeaker\tseconds\tasr\tasr_vad\tbefore\tafter"]
    orders: dict[int, list[tuple[str, str]]] = {}
    for node in nodes:
        before = after = ""  # a g_xa_clips record belongs to no scene
        if node.scene is not None:
            if node.scene not in orders:
                orders[node.scene] = _play_order(world, node.scene)
            before, after = _context(orders[node.scene], node, lines)
        rows.append(
            "\t".join(
                [
                    node.line_id,
                    node.clip,
                    str(node.day or ""),
                    node.speaker,
                    f"{node.seconds:.1f}",
                    *asr.get(node.clip, ("", "")),
                    before,
                    after,
                ]
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def write_movie_transcript(segments: list[Segment], path: Path) -> Path:
    rows = ["start_s\tend_s\tstart_frame\tend_frame\tja"]
    rows += [
        f"{s.start:.2f}\t{s.end:.2f}\t{s.start_frame}\t{s.end_frame}\t{s.text}" for s in segments
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


# --- the command --------------------------------------------------------------------------------


def _refuse_tracked(out_dir: Path) -> None:
    """work/voice holds the game's audio and its Japanese: never anywhere tracked."""
    resolved = out_dir.resolve()
    work = (REPO_ROOT / "work").resolve()
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(work):
        raise VoiceError(f"--out {out_dir} is inside the repo but not under work/")


def main_voice(
    disc_dir: Path,
    source: Path,
    out_dir: Path,
    *,
    tsv_only: bool,
    tsv_path: Path,
    transcribe_too: bool,
) -> int:
    """The `boku voice-only` command body. Returns a process exit status."""
    try:
        _refuse_tracked(out_dir)
        archive = Archive(disc_dir)
        world = EventWorld(archive)
        nodes = all_nodes(archive, world)
        path = write_tsv(nodes, tsv_path)
        print(f"{path}: {len(nodes)} rows, {len({n.clip for n in nodes})} distinct clips")
        if tsv_only:
            return 0
        if not source.is_file():
            raise VoiceError(f"no image at {source}: run `./make.sh import` first")
        with DiscImage(source) as image:
            clips = decode_clips(image, nodes, out_dir / "clips")
            print(f"{len(clips)} clips in {out_dir / 'clips'}/")
            movies = decode_movie_audio(
                image, voiced_movies(MOVIES_TSV.read_text(encoding="utf-8")), out_dir / "movies"
            )
            print(f"{len(movies)} voiced movies' audio in {out_dir / 'movies'}/")
        if not transcribe_too:
            return 0
        asr = {
            wav.stem: tuple(
                " / ".join(s.text for s in transcribe(wav, vad=vad)) for vad in (False, True)
            )
            for wav in clips
        }
        sheet = write_listening_sheet(
            world,
            nodes,
            asr,
            {
                k: r.get("text") or ""
                for k, r in load_store(disc_dir / SCRIPT_DIR_NAME).lines.items()
            },
            out_dir / "voice-only.asr.tsv",
        )
        print(f"{sheet}: the ASR beside each clip's neighbouring lines")
        for wav in movies:
            for vad in (False, True):
                done = write_movie_transcript(
                    transcribe(wav, vad=vad), wav.with_suffix(".vad.asr.tsv" if vad else ".asr.tsv")
                )
                print(f"{done}: timed segments, frames 1-based at {FPS} fps")
        return 0
    except (
        VoiceError,
        DiscError,
        ArchiveError,
        EventError,
        OSError,
        ValueError,
        StoreMissing,
    ) as refusal:
        print(f"boku voice-only: refused: {refusal}", file=sys.stderr)
        return 2


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--disc",
        type=Path,
        default=DEFAULT_DISC_DIR,
        help=f"the import whose events are walked (default: {DEFAULT_DISC_DIR}/)",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=DEFAULT_IMAGE,
        help=f"raw image the audio is read from (default: {DEFAULT_IMAGE.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        metavar="DIR",
        help=(
            f"where the audio and transcripts go "
            f"(default: {DEFAULT_OUT_DIR.relative_to(REPO_ROOT)}/)"
        ),
    )
    parser.add_argument(
        "--tsv", action="store_true", help=f"only regenerate {VOICE_TSV.relative_to(REPO_ROOT)}"
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="also run whisper-cli (Japanese) over every clip and every voiced movie",
    )
    parser.set_defaults(
        run=lambda args: main_voice(
            args.disc,
            args.image,
            args.out,
            tsv_only=args.tsv,
            tsv_path=VOICE_TSV,
            transcribe_too=args.transcribe,
        )
    )
    return parser
