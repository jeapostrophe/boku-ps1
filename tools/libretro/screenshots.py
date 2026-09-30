#!/usr/bin/env python3
"""The README's screenshots, shot on Beetle PSX from the built image (PLAN `DOC-02`).

    ./make.sh screenshots                 # build/days -> docs/screenshots/*.png
    ./make.sh screenshots --only diary --out work/screenshots

One screen of each kind the patch translates (`SHOTS`), from one cold boot of a new game: the
title menu, the opening movie, the first conversation and -- from a state kept at that
conversation -- the two encyclopedias and the picture diary, each entered with
`field.mode_set`. Each is the core's own frame, every pixel `SCALE` x `SCALE`.

Run it after what the screens show changes, and commit what it writes: the same build gives
the same bytes. `tests/test_docs.py` keeps `SHOTS`, the tracked files and the README's images
in step, and CLAUDE.md § "This repo is public" says why these pictures are tracked at all.

Needs Beetle's core and BIOS (emulator_paths.py) and a `./make.sh build-days` build: what is
shot is that build, whatever `translation/` says by now. Exit 0; 2 without the build; 11 if a
screen never came.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from field import (  # noqa: E402 -- beside this file, so on sys.path when run as a script
    BOOK_OPEN,
    DIARY_MODE,
    DIARY_OPEN,
    DIARY_PRESSES,
    INSECT_MODE,
    KITE_MODE,
    MODE_SET_AT,
    Game,
    StepError,
    mode_set,
    press_file,
)

from boku.movie_cues import CUE_FILE  # noqa: E402
from boku.movie_cues import read as read_cues  # noqa: E402

SCALE = 2
NEW_GAME = HERE / "boot-to-dialogue.press"
"""START at the title, ○ on "New Game", START to skip the opening: its comments give what is
on screen at each frame, which is where `TITLE_AT` and `CONVERSATION_AT` come from."""
TITLE_AT = 3599
MOVIE_STATE_AT = 5350
"""Inside the opening movie, before the press that skips it."""
MOVIE, MOVIE_FRAME = "M27", 1160
"""The opening, at an STR frame of the narrator's second sentence."""
CONVERSATION_AT = 5850
SHOTS = ("title", "movie", "conversation", "insect-book", "kite-book", "diary")
"""The files written, `<name>.png`, in the order the README shows them."""
BOOKS = {"insect-book": INSECT_MODE, "kite-book": KITE_MODE}


def movie_cue(movie: str, frame: int, cue_file: Path = CUE_FILE) -> str:
    """The English `cue_file` puts on screen at `frame` of `movie`; refuses a frame no cue
    covers with a frame to spare, so that a retimed subtitle is noticed here."""
    rows, problems = read_cues(cue_file)
    if problems:
        raise StepError(f"{cue_file} does not parse: {problems[0]}")
    for cue in rows:
        if cue.movie == movie and cue.start < frame < cue.end:
            return cue.text
    raise StepError(f"no cue of {movie} covers frame {frame}: choose another MOVIE_FRAME")


def movie_frame_counter(edits: Path) -> int:
    """The address of the movie hook's `movie_sub_frame_no`: the STR frame being shown."""
    try:
        island = json.loads(edits.read_text(encoding="utf-8"))["movie_subtitles"]["islands"][0]
        return int(island["symbols"]["movie_sub_frame_no"], 16)
    except (OSError, ValueError, LookupError) as exc:
        raise StepError(f"{edits} does not name the movie hook's frame counter: {exc!r}") from exc


def capture(image: Path, edits: Path, out: Path, work: Path, only: set[str]) -> None:
    presses = press_file(NEW_GAME)
    game = Game(image, None, work)

    def keep(name: str) -> None:
        if name in only:
            path = out / f"{name}.png"
            width, height = game.fe.screenshot(path, SCALE)
            print(f"screenshots: {path} ({width}x{height}, frame {game.frame})")

    def state(name: str) -> Path:
        path = work / f"{name}.state"
        if not game.fe.save_state(path):
            raise StepError(f"the core would not save a state at frame {game.frame}")
        return path

    def resume(path: Path, frame: int) -> None:
        if not game.fe.load_state(path):
            raise StepError(f"the core refused the state {path}")
        game.frame = frame

    game.play(presses, TITLE_AT)
    keep("title")
    if "movie" in only:
        print(f"screenshots: the movie frame shows {movie_cue(MOVIE, MOVIE_FRAME)!r}")
        counter = movie_frame_counter(edits)
        game.play(presses, MOVIE_STATE_AT)
        in_movie = state("movie")
        game.until(f"{MOVIE} frame {MOVIE_FRAME}", lambda: game.u32(counter) >= MOVIE_FRAME, 20000)
        keep("movie")
        resume(in_movie, MOVIE_STATE_AT)
    game.play(presses, CONVERSATION_AT)
    keep("conversation")
    game.play(presses, MODE_SET_AT - 1)
    conversation = state("conversation")
    for name, mode in BOOKS.items():
        if name in only:
            resume(conversation, MODE_SET_AT - 1)
            mode_set(game, mode)
            game.play({}, MODE_SET_AT + BOOK_OPEN)
            keep(name)
    if "diary" in only:
        resume(conversation, MODE_SET_AT - 1)
        mode_set(game, DIARY_MODE)
        for at in DIARY_PRESSES:
            game.play({}, MODE_SET_AT + at - 1)
            game.press("CIRCLE", 0)
        game.play({}, MODE_SET_AT + DIARY_OPEN)
        keep("diary")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--image", type=Path, default=REPO / "build" / "days" / "image.cue")
    p.add_argument("--edits", type=Path, default=REPO / "build" / "vwf" / "edits.json")
    p.add_argument("--out", type=Path, default=REPO / "docs" / "screenshots")
    p.add_argument("--work", type=Path, default=REPO / "work" / "screenshots")
    p.add_argument("--only", action="append", choices=SHOTS, help="repeatable; default all")
    args = p.parse_args(argv)
    if not args.image.is_file():
        print(f"screenshots: no {args.image}: run ./make.sh build-days", file=sys.stderr)
        return 2
    try:
        capture(args.image, args.edits, args.out, args.work, set(args.only or SHOTS))
    except StepError as exc:
        print(f"screenshots: {exc}", file=sys.stderr)
        return 11
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
