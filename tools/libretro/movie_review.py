#!/usr/bin/env python3
"""The movie subtitles as a viewer meets them, for review (PLAN `FMV-03`).

    ./make.sh movie-review                       # every movie with cues, from build/days
    ./make.sh movie-review M60 --image build/days/image.cue --out work/movie-review

For each movie with cues in `translation/movies.txt`, on Beetle PSX with the built image:
a shot of each cue at its first, middle and last frame, and a 15 fps MP4 of the stretch the
cues cover with the movie's own narration under it; then `work/movie-review/index.html`,
one page with every shot, each cue's English and its timing against the reviewed transcript
(`boku.movie_timing`). Everything written is under `--out` (gitignored `work/`): shots of
the game and its audio never leave it.

How a movie other than the opening is played: from a state saved at the title (frame 3000
of a cold boot), `g_movie_table`'s entry for the opening (id 23) is given that movie's name
pointer and stop frame (`--poke`, the values from `boku.movie_block.movie_names` and
`research/data/movies.tsv`), and the boot's presses start it where the opening would play
(`research/movies.md` § 8). Which STR frame a Beetle frame shows is read from the hook's
`movie_sub_frame_no` (its address from the build's `edits.json`): a first pass samples it
every `SAMPLE` frames, the shots are aimed by interpolating those samples, and each shot is
labelled from the number read at that very frame, never the one aimed at
(`research/movies.md` § 10 has what the number says about the picture on screen).

Needs BOKU_LIBRETRO_CORE / BOKU_LIBRETRO_SYSTEM (run_core.py), ffmpeg, the import, and a
build whose `edits.json` carries the movie hooks.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import struct
import subprocess
import sys
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

import run_core  # noqa: E402 -- beside this file

from boku import movie_timing  # noqa: E402
from boku.archive import DEFAULT_DISC_DIR, EXE_NAME  # noqa: E402
from boku.disc import DiscImage  # noqa: E402
from boku.movie_block import (  # noqa: E402
    MOVIE_ENTRY_FRAMES,
    MOVIE_ENTRY_SIZE,
    MOVIE_TABLE,
    movie_names,
)
from boku.movie_cues import CUE_FILE, CueRow, read, read_movie_lengths  # noqa: E402
from boku.movie_timing import DEFAULT_SEGMENTS  # noqa: E402
from boku.movies import FPS  # noqa: E402
from boku.voice import MOVIE_AUDIO_LEAD, decode_movie_audio  # noqa: E402

OPENING = 23
"""The `MOVIE` id the boot plays (`research/movies.md` § 1): its entry is the one rewritten."""
TITLE_STATE_AT = 3000
PRESSES = [
    f"{int(frame) - TITLE_STATE_AT}:{rest}"
    for frame, rest in (
        spec.split(":", 1) for spec in run_core.read_press_file(HERE / "boot-to-dialogue.press")[:2]
    )
]
"""`boot-to-dialogue.press`'s first two presses (the title's START, the menu's CIRCLE; its
third skips the movie), counted from the title state instead of from power-on."""
SAMPLE = 100
VIDEO_STEP = 4
"""Beetle frames per shot of the video: the player shows a STR frame for about 4 vsyncs."""
PAD = 30
"""STR frames of picture before the first cue and after the last in the video."""
SHOWN = 1
"""The hook's number minus the STR frame on screen at the same vsync, to within a vsync."""
INSIDE = 1
"""STR frames inside a cue's first and last at which those two shots are aimed: the number
turns mid-frame and the picture flips a vsync or two later, so a shot at the very edge can
show the frame beside it (measured on M60: aimed at the first, it showed no text)."""
BEFORE_STOP = 2
"""STR frames before a movie's stop frame that are the last on screen: the player ends the
movie as the hook's number reaches the stop frame, and a shot aimed there is black (measured
on M120 and M260, whose last cues run to the stop frame)."""


def entry_pokes(name: int, frames: int, at: int = 1) -> list[str]:
    """`--poke`s that make the opening's table entry play the movie named `name`."""
    entry = MOVIE_TABLE + MOVIE_ENTRY_SIZE * OPENING
    return [
        f"{at}:{entry:08X}={struct.pack('<I', name).hex()}",
        f"{at}:{entry + MOVIE_ENTRY_FRAMES:08X}={struct.pack('<I', frames).hex()}",
    ]


def aim(samples: list[tuple[int, int]], frame: int) -> int:
    """The Beetle frame at which the hook's number should read `frame`, by linear
    interpolation between the two samples around it -- or past the first or last pair, at
    their rate, for a frame the samples do not bracket (the first `SAMPLE` frames of a movie).
    Every shot is labelled with what it showed, so an extrapolated aim is honest either way."""
    pairs = [pair for pair in pairwise(sorted(samples)) if pair[1][1] > pair[0][1]]
    if not pairs:
        raise ValueError(f"the samples {samples} show no movie playing")
    chosen = next(
        (pair for pair in pairs if pair[0][1] <= frame <= pair[1][1]),
        pairs[0] if frame < pairs[0][0][1] else pairs[-1],
    )
    (f0, n0), (f1, n1) = chosen
    return max(1, f0 + round(Fraction(frame - n0, n1 - n0) * (f1 - f0)))


def run(image: Path, work: Path, frames: int, extra: list[str]) -> None:
    status = run_core.main(
        [str(image), "--work", str(work), "--frames", str(frames), "--quiet", *extra]
    )
    if status:
        raise SystemExit(f"movie-review: run_core exited {status} ({work})")


def word(ram: Path, address: int) -> int:
    return struct.unpack_from("<I", ram.read_bytes(), run_core.ram_offset(address, 4))[0]


def review_movie(args, movie: str, cues: list[CueRow], names, lengths, sub_frame_no, state):
    out = args.out / movie
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    pokes = [] if movie == "M27" else entry_pokes(names[movie], lengths[movie])
    common = ["--state-in", str(state), *[f"--press={p}" for p in PRESSES]]
    common += [f"--poke={p}" for p in pokes]
    budget = 2600 + 5 * lengths[movie]

    # Pass 1: where each STR frame falls.
    probe = out / "probe"
    run(
        args.image,
        probe,
        budget,
        common + [f"--ram-out={f}:s{f}" for f in range(SAMPLE, budget + 1, SAMPLE)],
    )
    samples = []
    for f in range(SAMPLE, budget + 1, SAMPLE):
        path = probe / f"s{f}.ram"
        n = word(path, sub_frame_no)
        if 1 <= n < lengths[movie]:  # the number stops at the stop frame: no rate there
            samples.append((f, n))
        path.unlink()
    if len(samples) < 2:
        raise SystemExit(f"movie-review: {movie} never played in {budget} frames ({probe})")

    # Pass 2: the shots.
    wanted: dict[int, str] = {}
    for cue in cues:
        for tag, n in (
            ("first", cue.start + INSIDE),
            ("middle", (cue.start + cue.end) // 2),
            ("last", min(cue.end - INSIDE, lengths[movie] - BEFORE_STOP)),
        ):
            wanted[aim(samples, n + SHOWN)] = f"{cue.start}-{tag}"
    first = max(1, cues[0].start - PAD)
    last = min(lengths[movie] - BEFORE_STOP, cues[-1].end + PAD)
    video_from, video_to = aim(samples, first + SHOWN), aim(samples, last + SHOWN)
    extra = [f"--shot={f}:{name}" for f, name in wanted.items()]
    extra += [f"--ram-out={f}:{name}" for f, name in wanted.items()]
    extra += [f"--shot-every={VIDEO_STEP}", f"--shot-from={video_from}", f"--shot-to={video_to}"]
    shots = out / "shots"
    run(args.image, shots, video_to + 1, common + extra)
    seen = {}
    for name in wanted.values():
        ram = shots / f"{name}.ram"
        seen[name] = word(ram, sub_frame_no) - SHOWN
        ram.unlink()

    sequence = {int(p.stem.split("-")[1]): p for p in shots.glob("frame-*.png")}
    sequence |= {f: shots / f"{name}.png" for f, name in wanted.items()}
    frames = [sequence[f] for f in sorted(sequence) if video_from <= f <= video_to]
    video = make_video(args, movie, frames, first, last, out)
    return {"shots": seen, "video": video}


def make_video(args, movie, frames: list[Path], first: int, last: int, out: Path) -> Path | None:
    """`frames` (Beetle shots, in order, spanning STR frames `first`..`last`) as a 15 fps
    MP4 with the movie's narration from the same point; the unnamed shots are deleted."""
    if not frames or shutil.which("ffmpeg") is None:
        return None
    listing = out / "frames.txt"
    rate = Fraction(len(frames) * FPS, last - first + 1)
    listing.write_text(
        "".join(f"file '{p.resolve()}'\nduration {1 / float(rate):.6f}\n" for p in frames)
    )
    with DiscImage(args.source) as image:
        (audio,) = decode_movie_audio(image, [movie], args.out / "audio")
    offset = float(Fraction(first - 1, FPS) - MOVIE_AUDIO_LEAD)
    video = out / f"{movie}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-ss", f"{max(0.0, offset):.3f}", "-t", f"{(last - first + 1) / FPS:.3f}",
            "-i", str(audio),
            "-vf", "scale=640:480:flags=neighbor,format=yuv420p",
            "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-shortest", str(video),
        ],
        check=True,
    )  # fmt: skip
    for p in frames:
        if p.stem.startswith("frame-"):
            p.unlink()
    return video


def page(results, rows_by_movie, segments, lengths, out: Path) -> Path:
    parts = [
        "<!doctype html><meta charset=utf-8><title>Movie subtitles, for review</title>",
        "<style>body{font:14px sans-serif;background:#111;color:#ddd;margin:16px}"
        "img{width:320px;image-rendering:pixelated;margin:2px}"
        ".bad{color:#f88}.cue{margin:18px 0}video{width:640px}</style>",
        "<h1>Movie subtitles, for review</h1>",
        f"<p>Built from <code>{html.escape(str(CUE_FILE.relative_to(REPO)))}</code>; timing rules: "
        f"<code>boku/movie_timing.py</code>. Shots are labelled with the STR frame the hook "
        f"had when Beetle drew them.</p>",
    ]
    for movie, result in results.items():
        cues = rows_by_movie[movie]
        found = movie_timing.problems(cues, segments.get(movie, []), lengths[movie])
        by_key: dict[str, list[str]] = {}
        for p in found:
            by_key.setdefault(p.key, []).append(f"{p.check}: {p.message}")
        parts.append(f"<h2>{movie}</h2>")
        if result["video"]:
            parts.append(f"<video controls src='{movie}/{result['video'].name}'></video>")
        for cue in cues:
            frames = cue.end - cue.start + 1
            rate = float(movie_timing.rate(cue.text, cue.start, cue.end))
            notes = by_key.get(cue.key, [])
            parts.append(
                f"<div class=cue><b>{cue.start}-{cue.end}</b> ({frames / FPS:.1f} s, "
                f"{rate:.1f} cps, {cue.position}) {html.escape(cue.text)}"
                + "".join(f"<div class=bad>{html.escape(n)}</div>" for n in notes)
                + "<br>"
            )
            for tag in ("first", "middle", "last"):
                name = f"{cue.start}-{tag}"
                shown = result["shots"].get(name, "?")
                parts.append(
                    f"<img src='{movie}/shots/{name}.png' title='{tag}: STR frame {shown}'>"
                )
            parts.append("</div>")
        for p in found:
            if p.check == "speech-uncued":
                parts.append(f"<div class=bad>{html.escape(p.key)} {html.escape(p.message)}</div>")
    index = out / "index.html"
    index.write_text("\n".join(parts), encoding="utf-8")
    return index


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("movies", nargs="*", help="movie files (default: every one with cues)")
    p.add_argument("--image", type=Path, default=REPO / "build" / "days" / "image.cue")
    p.add_argument("--edits", type=Path, default=REPO / "build" / "vwf" / "edits.json")
    p.add_argument("--source", type=Path, default=REPO / "disc" / "image.img", help="for the audio")
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC_DIR)
    p.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    p.add_argument("--out", type=Path, default=REPO / "work" / "movie-review")
    args = p.parse_args(argv)

    rows, problems = read()
    if problems:
        raise SystemExit(f"movie-review: {CUE_FILE.name} does not parse: {problems[0]}")
    rows_by_movie = movie_timing.by_movie(rows)
    movies = args.movies or sorted(rows_by_movie)
    lengths = read_movie_lengths()
    names = movie_names((args.disc / "files" / EXE_NAME).read_bytes())
    edits = json.loads(args.edits.read_text(encoding="utf-8"))
    sub_frame_no = int(edits["movie_subtitles"]["islands"][0]["symbols"]["movie_sub_frame_no"], 16)
    segments = {
        m: movie_timing.read_segments(args.segments / f"{m}.ja.tsv")
        for m in movies
        if (args.segments / f"{m}.ja.tsv").is_file()
    }
    args.out.mkdir(parents=True, exist_ok=True)
    title = args.out / "title"
    run(args.image, title, TITLE_STATE_AT, [f"--state-out={TITLE_STATE_AT}:title"])
    results = {}
    for movie in movies:
        print(f"movie-review: {movie}")
        results[movie] = review_movie(
            args, movie, rows_by_movie[movie], names, lengths, sub_frame_no, title / "title.state"
        )
    index = page(results, rows_by_movie, segments, lengths, args.out)
    print(f"movie-review: {index}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
