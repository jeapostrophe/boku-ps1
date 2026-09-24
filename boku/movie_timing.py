"""The movie cues against the speech and song they subtitle: timing rules, a retimer (`FMV-03`).

`translation/movies.txt` (`boku.movie_cues`) says what each cue reads and over which frames;
the voice lane's reviewed transcripts (`work/voice/reviewed/<movie>.ja.tsv`, never tracked:
Japanese) say when each spoken segment -- narration, or the sung theme -- is heard, in the
same 1-based STR frames. This module holds the rules a cue's timing must pass against them
and `retime`, which moves cue boundaries -- never text -- to pass them where it can. Only the
columns `start_frame`, `end_frame` and `kind` of a transcript are read; its Japanese never
leaves `work/`.

A cue belongs to the spoken segment it overlaps most. One segment may carry several cues
(one sentence, two English cues); then the rules on onset and end bind its first and last
cue, and `retime` may move the boundaries between its cues by up to `REACH` frames.

Reading beats sync (Jay, 2026-09-24, on `M27@1221`: "out of sync with the audio is fine"): a
cue's start or end may leave its speech by up to `DRIFT` frames past the onset and end rules
when a cue needs those frames to be read -- `problems` accepts such a boundary only if putting
it back in sync would leave a cue over `MAX_CPS` or under `MIN_FRAMES`, and `retime` drifts as
few frames as reading needs.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from boku import REPO_ROOT
from boku.layout import SPEECH_MARKS
from boku.movie_cues import LINE_BREAK, CueRow, Problem
from boku.movies import FPS

DEFAULT_SEGMENTS = REPO_ROOT / "work" / "voice" / "reviewed"
"""Where the voice lane writes the reviewed transcripts, `<movie>.ja.tsv` (never tracked)."""
ONSET = 7
"""Frames a segment's first cue may start before or after its speech: 0.5 s, rounded down."""
MIN_FRAMES = 23
"""Frames a cue stays on screen at least: 1.5 s, rounded up."""
MAX_CPS = 17
"""Characters a second a viewer is asked to read, at most."""
END_SLACK = 1
"""Frames a segment's last cue may end before its speech ends: abutting segments share the
boundary frame, and the hook already changes a cue up to a frame early (research/movies.md § 7)."""
LINGER = 30
"""Frames a segment's last cue may stay after its speech: 2 s."""
DRIFT = 30
"""Frames past the onset and end rules (and past `LINGER`) a boundary may leave its speech when
a cue needs them to be read: 2 s."""
REACH = 60
"""How far `retime` looks either side of a boundary between two cues of one segment."""
EDGE = 2
"""What a frame moved at a chain's outer edge costs `retime` against one moved between two of
its cues: the edges sit on the speech, the splits only on the text."""


SUBTITLED_KINDS = frozenset({"narration", "song"})
"""The transcript `kind`s a cue subtitles: the song is sung and subtitled too (FMV-02)."""
NARRATION = "narration"
"""The `kind` of the adult Boku's narration, whose cues take `NARRATION_MARKS` (FMV-07)."""
NARRATION_MARKS = ("『", SPEECH_MARKS["『"])
"""What the dialogue draws around narration (`boku.layout.SPEECH_MARKS`); each narrated cue
opens and closes with them, which no one reads, so `characters` does not count them."""


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    kind: str = NARRATION


def read_segments(path: Path) -> list[Segment]:
    """The subtitled segments of a reviewed transcript (`SUBTITLED_KINDS`), in order."""
    with Path(path).open(encoding="utf-8") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        return [
            Segment(int(row["start_frame"]), int(row["end_frame"]), row["kind"])
            for row in rows
            if row["kind"] in SUBTITLED_KINDS
        ]


def characters(text: str) -> int:
    """What a viewer reads: the text with the translator's line breaks as one space and
    without the narration marks."""
    unmarked = "".join(c for c in text if c not in NARRATION_MARKS)
    return len(" ".join(part.strip() for part in unmarked.split(LINE_BREAK)))


def rate(text: str, start: int, end: int) -> Fraction:
    """Characters a second for `text` shown from frame `start` to `end`, both shown."""
    return Fraction(characters(text) * FPS, end - start + 1)


def strained(text: str, start: int, end: int) -> bool:
    """Whether `text` over frames `start`-`end` is too short on screen or too fast to read."""
    return end - start + 1 < MIN_FRAMES or rate(text, start, end) > MAX_CPS


def assign(cues: Sequence[CueRow], segments: Sequence[Segment]) -> list[int | None]:
    """Per cue, the index of the segment it overlaps most, or None if it overlaps none."""
    out: list[int | None] = []
    for cue in cues:
        overlaps = [
            (min(cue.end, seg.end) - max(cue.start, seg.start), -n)
            for n, seg in enumerate(segments)
        ]
        best, negative = max(overlaps, default=(-1, 0))
        out.append(-negative if best >= 0 else None)
    return out


def problems(
    cues: Sequence[CueRow], segments: Sequence[Segment], length: int | None = None
) -> list[Problem]:
    """Every timing rule each cue of one movie breaks; and spoken segments no cue covers."""
    cues = sorted(cues, key=lambda cue: cue.start)
    owner = assign(cues, segments)
    found: list[Problem] = []
    opening, closing = NARRATION_MARKS

    def say(cue: CueRow, check: str, message: str) -> None:
        found.append(Problem(cue.line, cue.key, check, message))

    for n, cue in enumerate(cues):
        if n and cue.start <= cues[n - 1].end:
            say(cue, "cue-overlap", f"starts at {cue.start}, inside {cues[n - 1].key}")
        frames = cue.end - cue.start + 1
        if frames < MIN_FRAMES:
            say(cue, "cue-short", f"{frames} frames on screen; at least {MIN_FRAMES} (1.5 s)")
        cps = rate(cue.text, cue.start, cue.end)
        if cps > MAX_CPS:
            say(cue, "cue-fast", f"{float(cps):.1f} characters a second; at most {MAX_CPS}")
        seg_index = owner[n]
        if seg_index is None:
            say(cue, "cue-unspoken", "overlaps no spoken segment")
            continue
        seg = segments[seg_index]
        marks = sum(cue.text.count(mark) for mark in NARRATION_MARKS)
        wrapped = marks == 2 and cue.text.startswith(opening) and cue.text.endswith(closing)
        if not (wrapped if seg.kind == NARRATION else marks == 0):
            say(
                cue,
                "cue-marks",
                f"{seg.kind} at {seg.start}: "
                + ("wrap it in 『 』" if seg.kind == NARRATION else "no 『 』"),
            )
        mine = [m for m, index in enumerate(owner) if index == seg_index]
        before = cues[n - 1] if n and cues[n - 1].end + 1 == cue.start else None
        after = cues[n + 1] if n + 1 < len(cues) and cues[n + 1].start == cue.end + 1 else None
        lead = cue.start - seg.start
        # Off its speech is allowed if back in the window it would strain a cue: this one if it
        # starts early, the one before if it starts late.
        held = abs(lead) <= ONSET + DRIFT and (
            strained(cue.text, seg.start - ONSET, cue.end)
            if lead < 0
            else before is not None and strained(before.text, before.start, seg.start + ONSET - 1)
        )
        if n == mine[0] and abs(lead) > ONSET and not held:
            say(
                cue,
                "cue-onset",
                f"starts {lead:+d} frames from the speech at {seg.start}; within {ONSET} (0.5 s)",
            )
        limit = seg.end - END_SLACK
        held = (
            cue.end >= limit - DRIFT
            and after is not None
            and strained(after.text, limit + 1, after.end)
        )
        if n == mine[-1] and cue.end < limit and not held:
            say(cue, "cue-early-end", f"ends at {cue.end}, before the speech ends at {seg.end}")
    covered = set(owner)
    for n, seg in enumerate(segments):
        if n not in covered and (length is None or seg.start <= length):
            found.append(
                Problem(0, f"@{seg.start}", "speech-uncued", f"spoken {seg.start}-{seg.end}")
            )
    return found


def retime(cues: Sequence[CueRow], segments: Sequence[Segment], length: int) -> list[CueRow]:
    """The same cues with boundaries moved, text untouched, to pass `problems` where they can.

    Cues that abut stay abutting (one boundary moves for both); the others move alone. Each
    boundary may take any frame its rules allow -- a segment's first cue within `ONSET` of the
    speech, its last cue from `END_SLACK` before the speech's end to `LINGER` after it, either
    of those up to `DRIFT` further, never into the next cue, a boundary inside one segment
    within `REACH` -- and the choice minimises, in order, the worst reading rate over
    `MAX_CPS`, the summed excess over it (so a chain whose worst cue cannot be fixed still
    fixes the others), the number of cues under `MIN_FRAMES`, the frames drifted past the
    onset and end rules, then the frames moved (`EDGE` times over at a chain's outer edges).
    A chain its rules leave no room to fix is returned as that minimum placed it, and
    `problems` still names what is left.
    """
    cues = sorted(cues, key=lambda cue: cue.start)
    owner = assign(cues, segments)
    out: list[CueRow] = []
    chain: list[int] = []
    for n in range(len(cues)):
        chain.append(n)
        if n + 1 == len(cues) or cues[n + 1].start > cues[n].end + 1:
            # Bounded by the previous chain as retimed, not as it was: two chains moving
            # toward each other would otherwise overlap.
            before = out[-1].end if out else 0
            out += _retime_chain(cues, owner, segments, chain, length, before)
            chain = []
    return out


def _window(low: int, high: int) -> range:
    return range(low, high + 1) if low <= high else range(0)


def _retime_chain(cues, owner, segments, chain, length, before) -> list[CueRow]:
    last = cues[chain[-1]]
    after = min((c.start for c in cues if c.start > last.end), default=length + 1)

    def first_of(n: int) -> bool:
        return owner[n] is not None and all(owner[m] != owner[n] for m in range(n))

    def last_of(n: int) -> bool:
        return owner[n] is not None and all(owner[m] != owner[n] for m in range(n + 1, len(cues)))

    # Boundary k is the first frame of chain cue k; boundary len(chain) is one past the last.
    # Where it ends a segment's last cue or starts a segment's first, it may leave the rule
    # `problems` checks there (early end, onset) by up to DRIFT, each frame counted in `drift`.
    options: list[range] = []
    rules: list[list[tuple[int, int]]] = []
    for k in range(len(chain) + 1):
        prev = chain[k - 1] if k else None
        nxt = chain[k] if k < len(chain) else None
        original = cues[nxt].start if nxt is not None else last.end + 1
        low = before + 1 if prev is None else cues[prev].start + 1
        high = after if nxt is None else cues[nxt].end
        mine: list[tuple[int, int]] = []
        if nxt is not None and first_of(nxt):
            seg = segments[owner[nxt]]
            mine.append((seg.start - ONSET, seg.start + ONSET))
        if prev is not None and last_of(prev):
            seg = segments[owner[prev]]
            mine.append((seg.end - END_SLACK + 1, high))
            if nxt is None or not first_of(nxt):
                # LINGER caps a hold only where no next cue's onset decides the boundary.
                high = min(high, seg.end + LINGER + 1 + DRIFT)
        if mine:
            low = max(low, *(rule_low - DRIFT for rule_low, _ in mine))
            high = min(high, *(rule_high + DRIFT for _, rule_high in mine))
        elif prev is None or nxt is None:
            low = high = original
        else:
            low, high = max(low, original - REACH), min(high, original + REACH)
        options.append(_window(low, high) or _window(original, original))
        rules.append(mine)

    def drift(k: int, b: int) -> int:
        return sum(max(0, rule_low - b, b - rule_high) for rule_low, rule_high in rules[k])

    def cost_of(k: int, start: int, stop: int) -> tuple[Fraction, int]:
        cue = cues[chain[k]]
        if stop <= start:
            return Fraction(10**9), 1
        return max(Fraction(0), rate(cue.text, start, stop - 1) - MAX_CPS), int(
            stop - start < MIN_FRAMES
        )

    originals = [cues[n].start for n in chain] + [last.end + 1]
    # best[b] for boundary k: (worst excess, summed excess, short cues, frames drifted,
    # frames moved, path)
    best = {
        b: (Fraction(0), Fraction(0), 0, drift(0, b), EDGE * abs(b - originals[0]), [b])
        for b in options[0]
    }
    for k in range(1, len(chain) + 1):
        nxt = {}
        for b in options[k]:
            candidates = []
            for a, (worst, total, short, drifted, moved, path) in best.items():
                excess, is_short = cost_of(k - 1, a, b)
                candidates.append(
                    (
                        max(worst, excess),
                        total + excess,
                        short + is_short,
                        drifted + drift(k, b),
                        moved + (EDGE if k == len(chain) else 1) * abs(b - originals[k]),
                        [*path, b],
                    )
                )
            if candidates:
                nxt[b] = min(candidates, key=lambda c: c[:5])
        best = nxt
    path = min(best.values(), key=lambda c: c[:5])[5]
    return [replace(cues[n], start=path[k], end=path[k + 1] - 1) for k, n in enumerate(chain)]


def retimed_file(text: str, moved: Mapping[tuple[str, int], CueRow]) -> str:
    """`text`, a cue file, with the frames of each row in `moved` (keyed by movie and line
    number) replaced and every other byte kept: notes, order, the English."""
    lines = text.split("\n")
    for (movie, line), cue in moved.items():
        fields = lines[line - 1].split("\t")
        assert fields[0].strip() == movie, (movie, line, fields)
        fields[1], fields[2] = str(cue.start), str(cue.end)
        lines[line - 1] = "\t".join(fields)
    return "\n".join(lines)


def by_movie(rows: Iterable[CueRow]) -> dict[str, list[CueRow]]:
    """The rows grouped by movie file, each group in frame order."""
    out: dict[str, list[CueRow]] = {}
    for row in sorted(rows, key=lambda row: row.start):
        out.setdefault(row.movie, []).append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    """`./make.sh movie-timing [--write] [--segments DIR]`: every timing problem of the cue
    file; with `--write`, `retime`'s boundaries written back into it (frames only)."""
    import argparse

    from boku.movie_cues import CUE_FILE, read, read_movie_lengths

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--write", action="store_true", help="write the retimed frames back")
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--cues", type=Path, default=CUE_FILE)
    args = parser.parse_args(argv)
    rows, malformed = read(args.cues)
    if malformed:
        print(f"movie-timing: {args.cues}: {malformed[0]}")
        return 2
    lengths = read_movie_lengths()
    moved: dict[tuple[str, int], CueRow] = {}
    left = 0
    for movie, cues in sorted(by_movie(rows).items()):
        path = args.segments / f"{movie}.ja.tsv"
        if not path.is_file():
            print(f"{movie}: no reviewed transcript at {path}; not checked")
            continue
        segments = read_segments(path)
        fixed = retime(cues, segments, lengths[movie])
        for old, new in zip(cues, fixed, strict=True):
            if (old.start, old.end) != (new.start, new.end):
                moved[(movie, old.line)] = new
                print(f"{movie} line {old.line}: {old.start}-{old.end} -> {new.start}-{new.end}")
        found = problems(fixed if args.write else cues, segments, lengths[movie])
        left += len(found)
        for p in found:
            print(f"{movie} line {p.line} {p.key} {p.check}: {p.message}")
    if args.write and moved:
        args.cues.write_text(
            retimed_file(args.cues.read_text(encoding="utf-8"), moved), encoding="utf-8"
        )
        print(f"movie-timing: {len(moved)} cue(s) retimed in {args.cues}")
    print(f"movie-timing: {left} problem(s) {'left' if args.write else 'found'}")
    return 1 if left else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DRIFT",
    "END_SLACK",
    "LINGER",
    "MAX_CPS",
    "MIN_FRAMES",
    "NARRATION",
    "NARRATION_MARKS",
    "ONSET",
    "Segment",
    "assign",
    "by_movie",
    "characters",
    "problems",
    "rate",
    "read_segments",
    "retime",
    "retimed_file",
    "strained",
]
