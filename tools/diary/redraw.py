#!/usr/bin/env python3
"""Prototype of the PROGRAMMATIC path for the 94 picture-diary pages (PLAN `GFX-02`).

`GFX-02` has to choose, per texture category, between an image model redrawing a texture in
English and a Claude-drawn subtitle composited on top. The diary is the third option and over
half the work: its prose sits in ruled *vertical* columns on flat paper under the crayon
drawing, so a program can blank that panel, draw horizontal rules and typeset the English —
no image model, no colour decision, and the entry text lives in the translation files.

This script is that option, end to end for one page: export the page TIM through
`boku.textures`, measure the panel from the pixels, rebuild it, typeset an English entry in
either of two 1-bit faces, and hand the result back through `boku.textures` so the edit
becomes verified byte edits and (with `build`) a patched image.

It is a **prototype under `tools/`**, so it takes two liberties the package does not: it runs
under `uv run --no-project --with pillow` (Pillow is used only to scale and stack the
comparison sheet — every pixel that reaches a TIM is written by this file), and its measured
geometry is stated as constants that `measure` re-derives from the disc and checks.

Nothing it writes is committed: every output is a diary page's own pixels, so it lands under
the gitignored `work/diary/` and `build/diary/` (README principle 2).

    uv run --no-project --with pillow python tools/diary/redraw.py measure
    uv run --no-project --with pillow python tools/diary/redraw.py render --page 001
    uv run --no-project --with pillow python tools/diary/redraw.py compare --page 001
    uv run --no-project --with pillow python tools/diary/redraw.py build --page 001
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from boku.archive import Archive  # noqa: E402
from boku.diary import (  # noqa: E402
    INK_ROWS,
    LINE_PITCH,
    PAGE_H,
    PAGE_W,
    PANEL,
    Redraw,
    diary_pages,
    line_tops,
    measure_page,
    redraw_page,
)
from boku.textures import Texture, inventory, patches_for, to_png  # noqa: E402
from boku.typeset import FONT_SHEET_ID, Face, GameFace, Glyph  # noqa: E402

WORK_DIR = REPO_ROOT / "work/diary"
BUILD_DIR = REPO_ROOT / "build/diary"
DISC_DIR = REPO_ROOT / "disc"
GALMURI_BDF = REPO_ROOT / "reference/fonts/galmuri/Galmuri9.bdf"

# --- the two 1-bit faces -----------------------------------------------------------------


@dataclass(frozen=True)
class BdfChar:
    """One BDF character: its bounding box, its advance and its rows of hex."""

    width: int
    height: int
    off_x: int
    """Left bearing. It cancels here, because every glyph is re-aligned to its own ink."""
    off_y: int
    advance: int
    """The BDF's own `DWIDTH`. Only the space uses it; see `Face.advance`."""
    hex_rows: tuple[str, ...]


class BdfFace(Face):
    """A BDF bitmap font, read at its own pixels — no rasteriser, no hinting.

    Galmuri9 ships a BDF beside its TTFs, so the prototype compares the game's glyphs with
    the *designed* pixels of the candidate rather than with one rasteriser's opinion of them.
    """

    def __init__(self, path: Path, name: str) -> None:
        self.name = name
        self._chars, self._ascent = self._parse(path)
        self._cache: dict[str, Glyph | None] = {}
        space = self._chars.get(32)
        self.space = space.advance if space else 4

    @staticmethod
    def _parse(path: Path) -> tuple[dict[int, BdfChar], int]:
        """The characters, and the font's own `FONT_ASCENT`.

        The ascent is read out of the file rather than typed beside it. Taking the *cap*
        height for it instead silently deletes the top row of every accented capital, and
        `Face.missing` cannot see that, because the glyph is present — it is just short.
        """
        chars: dict[int, BdfChar] = {}
        ascent = None
        code = advance = None
        bbx: tuple[int, int, int, int] | None = None
        rows: list[str] | None = None
        for raw in path.read_text(encoding="latin-1").splitlines():
            line = raw.strip()
            if line.startswith("FONT_ASCENT"):
                ascent = int(line.split()[1])
            elif line.startswith("ENCODING"):
                code = int(line.split()[1])
            elif line.startswith("DWIDTH"):
                advance = int(line.split()[1])
            elif line.startswith("BBX"):
                w, h, ox, oy = (int(v) for v in line.split()[1:5])
                bbx = (w, h, ox, oy)
            elif line == "BITMAP":
                rows = []
            elif line == "ENDCHAR":
                if code is not None and bbx is not None and rows is not None:
                    chars[code] = BdfChar(*bbx, advance if advance is not None else bbx[0],
                                          tuple(rows))  # fmt: skip
                code = advance = None
                bbx = rows = None
            elif rows is not None:
                rows.append(line)
        if ascent is None:
            raise SystemExit(f"{path} declares no FONT_ASCENT, so a baseline cannot be placed")
        return chars, ascent

    def glyph(self, ch: str) -> Glyph | None:
        if ch in self._cache:
            return self._cache[ch]
        entry = self._chars.get(ord(ch))
        found = None
        if entry is not None and entry.width and entry.height:
            rows: list[tuple[int, ...]] = [() for _ in range(INK_ROWS)]
            for i, hex_row in enumerate(entry.hex_rows[: entry.height]):
                # BDF rows run top-down; the top one sits `off_y + height - 1` above the
                # baseline, and the baseline is `ascent` rows down the line's ink band.
                y = self._ascent - (entry.off_y + entry.height - 1 - i) - 1
                if not hex_row:
                    continue
                if not 0 <= y < INK_ROWS:
                    raise SystemExit(
                        f"{self.name}: U+{ord(ch):04X} has ink on row {y} of a {INK_ROWS}-row "
                        f"band. Dropping it would shorten the glyph silently."
                    )
                bits = int(hex_row, 16)
                span = len(hex_row) * 4
                rows[y] = tuple(
                    entry.off_x + c for c in range(entry.width) if (bits >> (span - 1 - c)) & 1
                )
            inked = [c for r in rows for c in r]
            if inked:
                left = min(inked)
                found = Glyph(
                    width=max(inked) - left + 1,
                    rows=tuple(tuple(c - left for c in r) for r in rows),
                )
        self._cache[ch] = found
        return found


def galmuri_face() -> BdfFace:
    """Galmuri9 at its native size: cap 9, x-height 6, 12 rows of ink
    (`research/font-candidates.md` § 4), which is `INK_ROWS` with nothing to spare. The
    ascent comes from the file's own `FONT_ASCENT`, 11, not from the cap height."""
    if not GALMURI_BDF.is_file():
        raise SystemExit(
            f"{GALMURI_BDF} is not there. `reference/fonts/` is gitignored; refetch it as "
            f"`reference/fonts/SOURCES.md` records."
        )
    return BdfFace(GALMURI_BDF, name="galmuri9")


# --- typesetting -------------------------------------------------------------------------


# --- the redraw --------------------------------------------------------------------------


# --- entry text ----------------------------------------------------------------------------

PLACEHOLDER = (
    "Mom is having a baby soon, so things at home are hectic! "
    "I am going to stay at my uncle's house out in the country. "
    "I wonder if there will be lots of fun things to do?"
)
"""PLACEHOLDER, not a translation: a paraphrase of `NIKKI_001`'s columns, set when the page
has no entry in `translation/textures/diary.txt` (where the entries live, keyed by page id),
so the prototype always sets a real sentence's worth of English."""


def entry_text(page: str, given: Path | None) -> tuple[str, bool]:
    """The English to set, and whether it is the placeholder: `given`, else the page's
    entry in `translation/textures/diary.txt`, else the placeholder."""
    if given is not None:
        return given.read_text(encoding="utf-8").strip(), False
    from boku.texture_text import read_entries

    tracked = read_entries().get(f"nikki@NIKKI_{page}")
    if tracked is not None:
        return tracked.text, False
    return PLACEHOLDER, True


# --- verbs ------------------------------------------------------------------------------------


def load(disc: Path):
    return inventory(Archive(disc))


def verb_measure(args) -> int:
    inv = load(args.disc)
    pages = diary_pages(inv)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    report = []
    disagree = []
    for key in sorted(pages):
        m = measure_page(pages[key])
        report.append(
            {
                "page": key,
                "top_edge_row": m.top_edge_row,
                "crayon_rows": list(m.crayon_rows),
                "background_fraction": {
                    str(k): round(v, 3) for k, v in m.background_fraction.items()
                },
                "rule_pairs": [list(p) for p in m.rule_pairs],
                "day_slot_clear": m.day_slot_clear,
                "date_ink_rows": list(m.date_ink_rows),
                "paper_rgb": pages[key].tim.palette_rgba(0)[m.colours.paper][:3],
                "rule_rgb": pages[key].tim.palette_rgba(0)[m.colours.rule][:3],
                "ink_rgb": pages[key].tim.palette_rgba(0)[m.colours.ink][:3],
                "notes": m.notes,
            }
        )
        if m.notes:
            disagree.append((key, m.notes))
    (WORK_DIR / "geometry.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"{len(pages)} diary pages measured -> {WORK_DIR / 'geometry.json'}")
    print(
        f"panel: x {PANEL.left}..{PANEL.right} (date column {PANEL.date_left}..239), paper "
        f"y {PANEL.top}..{PANEL.bottom}, repainted from y {PANEL.repaint_top}; "
        f"{len(PANEL.rule_pairs)} vertical rules, steps {sorted(set(PANEL.rule_steps()))}"
    )
    print(f"English lines that fit: {len(line_tops())} at pitch {LINE_PITCH}, tops {line_tops()}")
    edges = Counter(r["top_edge_row"] for r in report)
    print(f"drawn top edge of the ruled page, per page: {sorted(edges.items())}")
    same = len(pages) - len(disagree)
    print(f"pages whose panel matches the measured geometry exactly: {same}/{len(pages)}")
    for key, notes in disagree:
        print(f"  {key}: {'; '.join(notes)}")
    papers = Counter(tuple(r["paper_rgb"]) for r in report)
    inks = Counter(tuple(r["ink_rgb"]) for r in report)
    rules = Counter(tuple(r["rule_rgb"]) for r in report)
    print(f"paper colours: {papers.most_common(4)}")
    print(f"rule colours:  {rules.most_common(4)}")
    print(f"ink colours:   {inks.most_common(4)}")
    print(f"day-numeral slot blank on all pages: {all(r['day_slot_clear'] for r in report)}")
    return 0


def faces(inv) -> dict[str, Face]:
    return {"game": GameFace.from_sheet(inv.get(FONT_SHEET_ID).tim), "galmuri": galmuri_face()}


def render_one(texture: Texture, text: str, face: Face) -> Redraw:
    result = redraw_page(texture, text, face)
    if result.missing:
        print(f"  {face.name}: no glyph for {result.missing} — those characters are dropped")
    if result.overflow:
        print(
            f"  {face.name}: {len(result.overflow)} line(s) did not fit, first "
            f"{result.overflow[:2]} — nothing is cut to fit (README); give the entry less text"
        )
    return result


def verb_render(args) -> int:
    inv = load(args.disc)
    pages = diary_pages(inv)
    texture = pages[args.page]
    text, placeholder = entry_text(args.page, args.text)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    print(f"page {args.page} ({texture.id}), {texture.copies} occurrence(s)")
    if placeholder:
        print("  entry text: PLACEHOLDER -- translation/textures/diary.txt has no entry for it")
    (WORK_DIR / f"original-{args.page}.png").write_bytes(to_png(texture.tim))
    for name, face in faces(inv).items():
        result = render_one(texture, text, face)
        out = WORK_DIR / f"redraw-{args.page}-{name}.png"
        out.write_bytes(to_png(result.tim))
        print(f"  {name}: {len(result.lines)} lines -> {out}")
    return 0


def _scaled(png_bytes: bytes, scale: int):
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def verb_compare(args) -> int:
    from PIL import Image, ImageDraw

    inv = load(args.disc)
    texture = diary_pages(inv)[args.page]
    text, placeholder = entry_text(args.page, args.text)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    panels = [("original", to_png(texture.tim))]
    for name, face in faces(inv).items():
        panels.append((name, to_png(render_one(texture, text, face).tim)))

    pad, label = 8, 16
    ones = [_scaled(b, 1) for _, b in panels]
    threes = [_scaled(b, 3) for _, b in panels]
    w1, h1 = ones[0].size
    w3, h3 = threes[0].size
    width = pad + max(len(ones) * (w1 + pad), len(threes) * (w3 + pad))
    height = pad + label + h1 + pad + label + h3 + pad
    sheet = Image.new("RGB", (width, height), (32, 32, 36))
    draw = ImageDraw.Draw(sheet)
    y = pad
    for scale, images, cell_w, cell_h in ((1, ones, w1, h1), (3, threes, w3, h3)):
        x = pad
        for (name, _), img in zip(panels, images, strict=True):
            draw.text((x, y), f"{name} {scale}x", fill=(230, 230, 230))
            sheet.paste(img, (x, y + label))
            x += cell_w + pad
        y += label + cell_h + pad
    out = WORK_DIR / "COMPARE.png"
    sheet.save(out)
    print(f"{out}  ({'placeholder entry' if placeholder else 'entry from translation/'})")

    # The same three panels again, cropped to the ruled page and magnified. COMPARE.png at 3x
    # shows whether a redraw reads; only this shows whether a vertical rule survived the blank
    # or a glyph landed a row off, which is the pair of mistakes `measure` cannot see.
    zoom, top = 6, PANEL.top - 5
    crops = [
        _scaled(b, 1)
        .crop((0, top, PAGE_W, PAGE_H))
        .resize((PAGE_W * zoom, (PAGE_H - top) * zoom), Image.NEAREST)
        for _, b in panels
    ]
    cw, ch = crops[0].size
    strip = Image.new("RGB", (cw, len(crops) * (ch + label) + pad), (32, 32, 36))
    draw = ImageDraw.Draw(strip)
    for i, ((name, _), img) in enumerate(zip(panels, crops, strict=True)):
        y = i * (ch + label) + pad
        draw.text((pad, y - label // 2), f"{name} {zoom}x", fill=(230, 230, 230))
        strip.paste(img, (0, y + label // 2))
    zoom_out = WORK_DIR / "panel-zoom.png"
    strip.save(zoom_out)
    print(f"{zoom_out}  (the ruled page alone, rows {top}..{PAGE_H - 1} at {zoom}x)")
    return 0


def verb_build(args) -> int:
    from boku.build import build, verify_written_sectors

    inv = load(args.disc)
    texture = diary_pages(inv)[args.page]
    text, placeholder = entry_text(args.page, args.text)
    face = faces(inv)[args.face]
    result = render_one(texture, text, face)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    (WORK_DIR / f"redraw-{args.page}-{args.face}.png").write_bytes(to_png(result.tim))
    edits = patches_for(texture, result.tim)
    print(
        f"{len(edits)} byte edit(s), {sum(len(e.new) for e in edits)} bytes, "
        f"over {texture.copies} occurrence(s)" + ("  [placeholder entry]" if placeholder else "")
    )
    out = build(
        source=args.image,
        out_dir=BUILD_DIR,
        disc_dir=args.disc,
        translation=None,
        binary_patches=edits,
        name="diary",
    )
    if not out.written:
        print("no image was written")
        return 1
    print(f"image -> {out.written.image} ({len(out.written.sectors)} sectors rewritten)")
    # `build()` verifies every `old` before the first write; only `boku build`'s CLI re-reads
    # the *written* sectors afterwards. This is the prototype's own copy of that check, so a
    # sector written with a stale EDC/ECC cannot be reported as a clean build.
    bad = verify_written_sectors(out.written.image, out.written.sectors)
    if bad:
        print(f"{len(bad)} written sector(s) fail their own EDC/ECC: {bad[:8]}")
        return 1
    print(f"all {len(out.written.sectors)} written sectors pass their own EDC/ECC")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--disc", type=Path, default=DISC_DIR)
    sub = parser.add_subparsers(dest="verb", required=True)

    m = sub.add_parser("measure", help="re-derive the panel geometry from all 94 pages")
    m.set_defaults(run=verb_measure)

    for name, run, extra in (
        ("render", verb_render, False),
        ("compare", verb_compare, False),
        ("build", verb_build, True),
    ):
        p = sub.add_parser(name)
        p.add_argument("--page", default="001", help="diary page, e.g. 001")
        p.add_argument("--text", type=Path, default=None, help="file holding the English entry")
        if extra:
            p.add_argument("--face", choices=("game", "galmuri"), default="game")
            p.add_argument("--image", type=Path, default=REPO_ROOT / "disc/image.img")
        p.set_defaults(run=run)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
