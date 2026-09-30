#!/usr/bin/env python3
"""The epilogues' subtitles as a viewer meets them, measured on Beetle PSX (PLAN `VO-09`).

    ./make.sh epilogue-review                    # all five endings, from build/days
    ./make.sh epilogue-review 2 3 --image build/days/image.cue --out work/epilogue-review

For each ending, `ENDOTI` is entered by hand from the first dialogue of a new game (the five
words `mode_set` writes, and the ending in `0x80035F42`) and sampled every frame: its state
and counter, the XA status and the text page. From that: when each subtitle page was up,
what `ENDOTI` was showing, and when the production card came. A second run shoots each page
at its middle frame and the card's first frames. `index.html` under `--out` lists it beside
what `boku.clip_subs` predicted for `translation/clips.txt` -- the numbers the reader draws
and the lint judges -- and the tool exits 1 when a page was up with the card, or a page's
start or end is more than `TOLERANCE` vsyncs off its prediction.

Everything written is under `--out` (gitignored `work/`): shots of the game never leave it.
Needs Beetle's core and BIOS (emulator_paths.py) and the import.
"""

from __future__ import annotations

import argparse
import html
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

import run_core  # noqa: E402 -- beside this file

from boku import clip_subs, epilogue  # noqa: E402
from boku.archive import DEFAULT_DISC_DIR, Archive  # noqa: E402
from boku.lint import DEFAULT_CELLS, make_encoder  # noqa: E402
from boku.movie_block import BLOCK_MAX_SECTORS, BLOCK_RAM  # noqa: E402
from boku.packets import PacketRefused, check_destination  # noqa: E402
from boku.voice import VSYNC_HZ, xch_nodes  # noqa: E402

DIALOGUE_AT = 6499
"""A frame of `boot-to-dialogue.press`'s first dialogue, where the state is saved."""
ENDOTI_MODE = 0x10
MODE_SET = ["0x800237E5=05", "0x800237E0=10", "0x800237E4=10", "0x80024728=01000000",
            "0x800258E0=f4791180"]  # fmt: skip
"""`mode_set(0x10)` by hand, as `tests/test_real_texture_text_beetle.py` `DIARY_MODE` enters
the diary: the mode before, the mode twice, the "changed" word, and level A's arena base
(`research/loading-and-memory.md`)."""
ENDING = 0x80035F42
PEEKS = {
    "mode": (0x800237E0, 1),
    "state": (epilogue.STATE, 1),
    "count": (epilogue.COUNTER, 4),
    "busy": (0x800359D8, 4),
    "page": (0x800359EC, 4),
    "panel": (0x8002911E, 1),
}
"""The game mode, `ENDOTI`'s state and counter, the XA status, `g_text_page` and
`g_dlgbox_visible` (research/event-scripts.md § Native clips, § The epilogue's clock)."""
START_BUDGET = 400
"""Frames `ENDOTI` may take from the pokes to its clip: its loads, the block, the seek."""
BLOCK = range(BLOCK_RAM, BLOCK_RAM + BLOCK_MAX_SECTORS * 2048)
TOLERANCE = 4
"""Vsyncs a page may start or end off its prediction."""
BLINK = 2
"""A "page" up for no longer than this is the empty one a timed last page gives way to."""


@dataclass(frozen=True)
class Seen:
    """One page as it was on the screen: frames of the run, `end` the first without it."""

    start: int
    end: int
    state: int
    """`ENDOTI`'s state when it went."""


@dataclass(frozen=True)
class Measured:
    ending: int
    opened: int
    """The first frame with a subtitle page up; every time below counts from it."""
    pages: list[Seen]
    card: int | None
    """The first frame of the production card."""
    left: int | None
    """The first frame out of `ENDOTI`."""
    rows: list[dict[str, int]]


def run(image: Path, work: Path, frames: int, extra: list[str]) -> None:
    status = run_core.main(
        [str(image), "--work", str(work), "--frames", str(frames), "--quiet", *extra]
    )
    if status != run_core.EXIT_OK:
        raise SystemExit(f"epilogue-review: run_core exited {status} in {work}")


def enter(ending: int) -> list[str]:
    return [f"--poke=1:{poke}" for poke in [*MODE_SET, f"{ENDING:#x}={ending:02x}"]]


def read_peeks(path: Path) -> list[dict[str, int]]:
    rows = []
    for line in path.read_text(encoding="ascii").splitlines():
        frame, *cols = line.split("\t")
        row = {
            key: int.from_bytes(bytes.fromhex(col), "little")
            for key, col in zip(PEEKS, cols, strict=True)
        }
        rows.append({"frame": int(frame), **row})
    return rows


def measure(ending: int, rows: list[dict[str, int]]) -> Measured:
    """What the samples say happened. A page is a run of frames with one page pointer inside
    the subtitle block; the one-frame empty page after a timed last page is not one."""
    inside = [r for r in rows if r["mode"] == ENDOTI_MODE]
    runs: list[list[dict[str, int]]] = []
    for row in inside:
        if row["page"] not in BLOCK:
            continue
        if (
            runs
            and runs[-1][-1]["page"] == row["page"]
            and runs[-1][-1]["frame"] == row["frame"] - 1
        ):
            runs[-1].append(row)
        else:
            runs.append([row])
    pages = [
        Seen(run[0]["frame"], run[-1]["frame"] + 1, run[-1]["state"])
        for run in runs
        if len(run) > BLINK
    ]
    if not pages:
        raise SystemExit(
            f"epilogue-review: ending {ending} showed no subtitle: is the image patched?"
        )
    started = pages[0].start
    card = next(
        (
            r["frame"]
            for r in inside
            if r["frame"] >= started and epilogue.SHOWN_IN_STATE.get(r["state"]) == epilogue.CARD
        ),
        None,
    )
    left = next(
        (r["frame"] for r in rows if r["frame"] > started and r["mode"] != ENDOTI_MODE), None
    )
    return Measured(ending, started, pages, card, left, rows)


def review(args, ending: int, state: Path, picture: epilogue.Picture) -> Measured:
    work = args.out / f"OTI0{ending}"
    frames = START_BUDGET + picture.end + 2 * epilogue.FADE
    peeks = [f"--peek={address:08X}:{size}" for address, size in PEEKS.values()]
    run(args.image, work, frames, [f"--state-in={state}", *enter(ending), *peeks])
    seen = measure(ending, read_peeks(work / "peek.tsv"))
    shots = {}
    for number, page in enumerate(seen.pages, start=1):
        shots[(page.start + page.end) // 2] = f"OTI0{ending}-page-{number:02d}"
    shots[seen.pages[-1].end - 2] = f"OTI0{ending}-last-sentence"
    if seen.card is not None:
        shots[seen.card + epilogue.FADE] = f"OTI0{ending}-card"
        shots[seen.card - 2] = f"OTI0{ending}-before-card"
    extra = [f"--shot={frame}:shots/{name}" for frame, name in sorted(shots.items())]
    run(args.image, work, max(shots), [f"--state-in={state}", *enter(ending), *extra])
    return seen


def problems(seen: Measured, line: clip_subs.ClipLine | None) -> list[str]:
    found = []
    if seen.card is None:
        return ["the production card never came: lengthen the run"]
    for number, page in enumerate(seen.pages, start=1):
        if page.end >= seen.card:
            found.append(
                f"page {number} was up until {page.end - seen.opened}, and the production "
                f"card came at {seen.card - seen.opened}"
            )
    if line is None:
        return [*found, "translation/clips.txt gives this epilogue no row that lays out"]
    if len(line.pages) != len(seen.pages):
        return [*found, f"{len(seen.pages)} page(s) seen, {len(line.pages)} predicted"]
    for number, (page, want) in enumerate(zip(seen.pages, line.pages, strict=True), start=1):
        for what, got, predicted in (
            ("started", page.start - seen.opened, want.start),
            ("ended", page.end - seen.opened, want.end),
        ):
            if abs(got - predicted) > TOLERANCE:
                found.append(f"page {number} {what} at {got}, predicted {predicted}")
    if abs(seen.card - seen.opened - line.picture.card) > TOLERANCE:
        found.append(f"the card came at {seen.card - seen.opened}, predicted {line.picture.card}")
    return found


STYLE = """
body { background:#16181c; color:#e8e8e8; font:14px system-ui; margin:16px; }
table { border-collapse:collapse; margin:8px 0 28px; }
td, th { border:1px solid #444; padding:4px 8px; vertical-align:top; text-align:left; }
td.n { text-align:right; font-variant-numeric:tabular-nums; }
img { width:320px; image-rendering:pixelated; display:block; }
.bad { color:#ff6b6b; font-weight:600; } .ok { color:#7bd88f; }
.bar { position:relative; height:26px; background:#2a2d33; margin:6px 0; width:100%; }
.bar span { position:absolute; top:0; bottom:0; overflow:hidden; font-size:11px;
  line-height:26px; text-align:center; border-left:1px solid #16181c; box-sizing:border-box; }
.still { background:#35506b; } .black { background:#000; } .card { background:#6b3535; }
.page { background:#4b6b35; } .late { background:#c94f4f; }
"""


def seconds(vsyncs: int) -> str:
    return f"{float(vsyncs / VSYNC_HZ):.2f}"


def bar(spans: list[tuple[int, int, str, str]], total: int) -> str:
    cells = "".join(
        f'<span class="{kind}" style="left:{100 * start / total:.3f}%;'
        f'width:{100 * (end - start) / total:.3f}%" title="{html.escape(label)} '
        f'{seconds(start)}-{seconds(end)} s">{html.escape(label)}</span>'
        for start, end, kind, label in spans
        if end > start
    )
    return f'<div class="bar">{cells}</div>'


def section(seen: Measured, line: clip_subs.ClipLine | None, picture, found: list[str]) -> str:
    total = (seen.left or seen.rows[-1]["frame"]) - seen.opened
    card = seen.card - seen.opened if seen.card is not None else total
    shots = f"OTI0{seen.ending}/shots/OTI0{seen.ending}"
    kinds = {
        epilogue.FIRST_STILL: "still",
        epilogue.SECOND_STILL: "still",
        epilogue.BLACK: "black",
        epilogue.CARD: "card",
    }
    picture_bar = bar([(a, b, kinds[name], name) for name, a, b in picture.phases], total)
    page_bar = bar(
        [
            (
                p.start - seen.opened,
                p.end - seen.opened,
                "late" if p.end - seen.opened > card else "page",
                str(n),
            )
            for n, p in enumerate(seen.pages, start=1)
        ],
        total,
    )
    verdict = (
        "".join(f'<p class="bad">{html.escape(problem)}</p>' for problem in found)
        or '<p class="ok">every page as predicted, none with the production card</p>'
    )
    rows, shown = [], epilogue.SHOWN_IN_STATE
    for number, page in enumerate(seen.pages, start=1):
        want = line.pages[number - 1] if line and number <= len(line.pages) else None
        text = html.escape(want.text) if want else ""
        predicted = f"{seconds(want.start)}-{seconds(want.end)}" if want else ""
        start, end = page.start - seen.opened, page.end - seen.opened
        rows.append(
            f'<tr><td class="n">{number}</td><td>{text}</td>'
            f'<td class="n">{seconds(start)}-{seconds(end)}</td>'
            f'<td class="n">{seconds(end - start)}</td><td class="n">{predicted}</td>'
            f'<td class="{"bad" if end > card else ""}">{shown.get(page.state, page.state)}</td>'
            f'<td><img src="{shots}-page-{number:02d}.png"></td></tr>'
        )
    card_row = (
        f'<tr><td></td><td>{epilogue.CARD}</td><td class="n">{seconds(card)}</td><td></td>'
        f'<td class="n">{seconds(picture.card)}</td><td></td>'
        f'<td><img src="{shots}-card.png"></td></tr>'
    )
    return (
        f"<h2>OTI0{seen.ending} -- XCH.{epilogue.FIRST_CLIP + seen.ending}</h2>{verdict}"
        f"{picture_bar}{page_bar}"
        "<table><tr><th>page</th><th>English</th><th>up (s after the subtitle opens)</th>"
        "<th>for (s)</th><th>predicted</th><th>when it went, ENDOTI showed</th>"
        "<th>its middle frame</th></tr>"
        f"{''.join(rows)}{card_row}</table>"
    )


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "endings",
        nargs="*",
        type=int,
        choices=range(epilogue.ENDINGS),
        help="ending numbers (default: all)",
    )
    p.add_argument("--image", type=Path, default=REPO / "build" / "days" / "image.cue")
    p.add_argument("--cells", type=Path, default=DEFAULT_CELLS)
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC_DIR)
    p.add_argument("--clips", type=Path, default=clip_subs.CLIP_FILE)
    p.add_argument("--out", type=Path, default=REPO / "work" / "epilogue-review")
    args = p.parse_args(argv)
    try:
        args.out = check_destination(args.out, "The epilogue review")
    except PacketRefused as error:
        raise SystemExit(f"epilogue-review: {error}") from error

    archive = Archive(args.disc)
    pictures = epilogue.pictures(archive)
    entries, _ = clip_subs.read(args.clips)
    lines, _ = clip_subs.lay_out_lines(
        entries, xch_nodes(archive), make_encoder("cellmap", args.cells), pictures
    )
    by_clip = {line.index: line for line in lines}
    endings = args.endings or sorted(p.ending for p in pictures.values())

    boot = args.out / "boot"
    presses = f"--press-file={HERE / 'boot-to-dialogue.press'}"
    run(args.image, boot, DIALOGUE_AT, [presses, f"--state-out={DIALOGUE_AT}:dialogue"])
    sections, failed = [], False
    for ending in endings:
        clip = epilogue.FIRST_CLIP + ending
        line, picture = by_clip.get(clip), pictures[clip]
        seen = review(args, ending, boot / "dialogue.state", picture)
        found = problems(seen, line)
        failed |= bool(found)
        for problem in found:
            print(f"epilogue-review: OTI0{ending}: {problem}")
        sections.append(section(seen, line, picture, found))
    index = args.out / "index.html"
    index.write_text(
        f"<!doctype html><meta charset=utf-8><title>Epilogue review</title><style>{STYLE}</style>"
        f"<h1>The epilogues on Beetle PSX</h1><p>{html.escape(str(args.image))}</p>"
        + "".join(sections),
        encoding="utf-8",
    )
    print(f"epilogue-review: {index}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
