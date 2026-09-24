"""English set in the game's own 12x12 glyphs, into a texture's palette indices.

The programmatic texture path (`research/textures-plan.md` path **P**) blanks a flat panel
and typesets English with the glyphs the game already draws its dialogue in, so a rebuilt
texture uses no colour the original did not and no pixel a program did not place. This
module is the typesetting half: a 1-bit face decoded from the one glyph sheet on the disc,
measured and set proportionally. What a given texture does with it — which rectangle,
which palette entries, an outline or a rule — is `boku.texture_text`'s.

The sheet is four interleaved 1bpp planes, not a 16-colour image: bit *k* of a 4-bit pixel
is plane *k*, and `id -> (col, plane, row)` is `research/font.md`'s formula. The cells are
proportional drawings with 1-5 px of left bearing, so a glyph is re-aligned to its own ink
and given `ink + 1` of advance — the "re-aligned" variant `research/font-candidates.md`
measured, not the engine's fixed 14 px pitch.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import ClassVar

from boku.glyphs import GlyphTable
from boku.tim import Tim

FONT_SHEET_ID = "_DATA_ONMEM.BIN__004aa0"
"""The one glyph sheet on the disc (`research/font.md`): `ONMEM.BIN` child 2."""

CELL = 12
"""A glyph cell is 12x12; row 0 is the top of the cell, and Latin capitals sit on rows 1-9
with descenders to row 11."""

SPACE = 4
"""The advance of a space, in pixels."""

APOSTROPHE = "\u2019"
"""The sheet draws the typographic apostrophe, so `'` is set with that cell. NFKC does not
fold U+2019 to ASCII, which is why `GlyphTable.to_glyph` does not already carry it."""


class TypesetError(Exception):
    """A string this face cannot set, or cannot set in the room it was given."""


@dataclass(frozen=True)
class Glyph:
    """A 1-bit glyph as rows of set-pixel x offsets, already left-aligned to its ink."""

    width: int
    """Ink width. The advance is this plus one column of air."""
    rows: tuple[tuple[int, ...], ...]
    """The face's `cell` rows, top of the cell first; each a tuple of x offsets."""


class Face:
    """A 1-bit typeface set into a `cell`-row line box: glyphs, advances, measurement.

    The one space is U+0020 and `\\n` is `wrap`'s forced break. Any other whitespace -- a
    tab, a no-break or an ideographic space an IME slips in -- has no drawing and is
    reported by `missing`, because setting it at zero width runs two words together."""

    name: ClassVar[str] = "?"
    space: int = SPACE
    cell: int = CELL
    """Rows in a glyph's cell: the line box one line of this face is set in."""
    pitch: int = CELL + 1
    """Rows from one line's cell to the next's when lines are stacked."""

    def glyph(self, ch: str) -> Glyph | None:
        raise NotImplementedError

    def advance(self, ch: str) -> int:
        if ch == " ":
            return self.space
        g = self.glyph(ch)
        return (g.width + 1) if g else 0

    def missing(self, text: str) -> list[str]:
        """Characters of `text` this face has no drawing for, sorted, without repeats."""
        return sorted({c for c in text if c not in " \n" and self.glyph(c) is None})

    def measure(self, text: str) -> int:
        """Ink width of `text` set on one line: every advance, less the trailing air."""
        return max(0, sum(self.advance(c) for c in text) - 1)

    def ink(self, text: str) -> set[tuple[int, int]]:
        """The (x, y) pixels `text` inks, with the first glyph's ink at x = 0, cell row y.

        Refuses a character the face cannot draw rather than skipping it.
        """
        absent = self.missing(text)
        if absent:
            raise TypesetError(
                f"the {self.name} face has no drawing for {''.join(absent)!r} in {text!r}"
            )
        out: set[tuple[int, int]] = set()
        x = 0
        for ch in text:
            g = self.glyph(ch)
            if g is not None:
                for y, xs in enumerate(g.rows):
                    out.update((x + dx, y) for dx in xs)
            x += self.advance(ch)
        return out


class GameFace(Face):
    """The game's own dialogue glyphs, decoded from the sheet in the contributor's import."""

    name = "game"

    def __init__(self, sheet: Tim, cells: dict[str, int]) -> None:
        self._indices = sheet.indices()
        self._width = sheet.width
        self.cells = cells
        """Character -> glyph id: ASCII through `GlyphTable.to_glyph` (which has no hyphen:
        the sheet's only dash is a full-width minus, `research/font-candidates.md` § 1; the
        face draws its own, `HYPHEN_WIDTH`), plus the apostrophe."""
        self._cache: dict[str, Glyph | None] = {}

    @classmethod
    def from_sheet(cls, sheet: Tim, table: GlyphTable | None = None) -> GameFace:
        table = table or GlyphTable.load()
        cells = dict(table.to_glyph)
        if APOSTROPHE in table.from_character:
            cells["'"] = table.from_character[APOSTROPHE]
        cells.pop(" ", None)  # a space is an advance, not a cell
        return cls(sheet, cells)

    def _bits(self, glyph_id: int) -> list[list[int]]:
        col, plane, row = glyph_id % 21, (glyph_id // 21) % 4, glyph_id // 84
        x0, y0 = col * CELL, row * CELL
        idx, w = self._indices, self._width
        return [
            [(idx[(y0 + r) * w + x0 + c] >> plane) & 1 for c in range(CELL)] for r in range(CELL)
        ]

    HYPHEN_WIDTH = 4
    """Our hyphen's ink: the sheet has none (its only dash is the full-width minus), so one is
    drawn on the row of `e`'s crossbar, narrower than `e` (PLAN TRN-04: "Moe-neechan")."""

    def _hyphen(self) -> Glyph | None:
        e = self.glyph("e")
        if e is None:
            return None
        crossbar = max(range(len(e.rows)), key=lambda r: len(e.rows[r]))
        span = tuple(range(self.HYPHEN_WIDTH))
        return Glyph(self.HYPHEN_WIDTH, tuple(span if r == crossbar else () for r in range(CELL)))

    LOWERED = ".,:;"
    """Marks the sheet draws a row high (it was drawn for vertical writing), so that in a
    line they float: the face moves each down until the period stands on the baseline of `n`.
    `!` and `?` already stand on it and are left as drawn."""

    def _lowered(self, ch: str) -> Glyph | None:
        g, n, period = self._from_sheet(ch), self._from_sheet("n"), self._from_sheet(".")
        if g is None or n is None or period is None:
            return g

        def bottom(glyph: Glyph) -> int:
            return max(r for r, xs in enumerate(glyph.rows) if xs)

        drop = bottom(n) - bottom(period)
        rows = ((),) * drop + g.rows[: CELL - drop]
        if sum(map(len, rows)) != sum(map(len, g.rows)):
            raise TypesetError(f"lowering {ch!r} by {drop} rows would push it out of its cell")
        return Glyph(g.width, rows)

    def glyph(self, ch: str) -> Glyph | None:
        if ch not in self._cache:
            if ch == "-" and ch not in self.cells:
                self._cache[ch] = self._hyphen()
            elif ch in self.LOWERED:
                self._cache[ch] = self._lowered(ch)
            else:
                self._cache[ch] = self._from_sheet(ch)
        return self._cache[ch]

    def _from_sheet(self, ch: str) -> Glyph | None:
        glyph_id = self.cells.get(ch)
        if glyph_id is None:
            return None
        bits = self._bits(glyph_id)
        inked = [c for r in range(CELL) for c in range(CELL) if bits[r][c]]
        if not inked:
            return None
        left, right = min(inked), max(inked)
        return Glyph(
            width=right - left + 1,
            rows=tuple(
                tuple(c - left for c in range(left, right + 1) if bits[r][c]) for r in range(CELL)
            ),
        )


FACES_DIR = Path(__file__).parent / "faces"
"""The pixel faces drawn for this project, one `<slug>.txt` each (MIT, as the tools)."""


class PixelFace(Face):
    """A face of our own pixels, read from a face file: `name`, `cell`, `pitch` and `space`
    header lines, then one block per glyph -- `== c` and the glyph's rows from the top of the
    cell, `#` ink and `.` air. Rows past the last given are blank; the glyph's width is its
    longest row, so a glyph carries its own side bearing. `#` lines before the header and
    blank lines are notes. The typographic apostrophe is set with `'`."""

    def __init__(self, name: str, cell: int, pitch: int, space: int, glyphs: dict[str, Glyph]):
        self.name = name  # type: ignore[misc]
        self.cell, self.pitch, self.space = cell, pitch, space
        self._glyphs = glyphs

    def glyph(self, ch: str) -> Glyph | None:
        return self._glyphs.get("'" if ch == APOSTROPHE else ch)

    @classmethod
    def load(cls, path: Path) -> PixelFace:
        header: dict[str, str] = {}
        drawn: dict[str, list[str]] = {}
        first_line: dict[str, int] = {}
        current: str | None = None
        name = Path(path).name
        for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            at = f"{name}:{number}"
            if line.startswith("== "):
                current = line[3:]
                if len(current) != 1:
                    raise TypesetError(f"{at}: a glyph is one character, not {current!r}")
                if current in drawn:
                    raise TypesetError(f"{at}: {current!r} is drawn twice (first at line "
                                       f"{first_line[current]})")  # fmt: skip
                drawn[current], first_line[current] = [], number
            elif not line.strip() or (current is None and line.startswith("#")):
                continue
            elif current is None:
                key, _, value = line.partition(" ")
                header[key] = value.strip()
            else:
                if set(line) - {"#", "."}:
                    raise TypesetError(f"{at}: a glyph row is only '#' and '.', not {line!r}")
                drawn[current].append(line)
        missing = [k for k in ("name", "cell", "pitch", "space") if k not in header]
        if missing:
            raise TypesetError(f"{name}: no {', '.join(missing)} header")
        cell = int(header["cell"])
        glyphs = {}
        for ch, rows in drawn.items():
            if not rows:
                raise TypesetError(f"{name}:{first_line[ch]}: {ch!r} has no rows")
            if len(rows) > cell:
                raise TypesetError(
                    f"{name}:{first_line[ch]}: {ch!r} is {len(rows)} rows, taller than its "
                    f"cell of {cell}"
                )
            rows = rows + [""] * (cell - len(rows))
            glyphs[ch] = Glyph(
                width=max(len(r) for r in rows),
                rows=tuple(tuple(x for x, c in enumerate(r) if c == "#") for r in rows),
            )
        return cls(header["name"], cell, int(header["pitch"]), int(header["space"]), glyphs)


@cache
def pixel_face(slug: str) -> PixelFace:
    """The tracked face `boku/faces/<slug>.txt` (`bean`, `sprout`)."""
    return PixelFace.load(FACES_DIR / f"{slug}.txt")


def face_named(slug: str, game: Face) -> Face:
    """`game` for "game", else the tracked face `slug` -- how a recipe's `face` field reads."""
    return game if slug == "game" else pixel_face(slug)


def wrap(text: str, face: Face, width: int) -> list[str]:
    """Greedy word wrap at `width` pixels, in `face`'s own advances. `\\n` forces a break.

    A single word wider than `width` is left on a line of its own; the caller's fit check
    is what refuses it (nothing is cut to fit, README).
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}" if current else word
            if current and face.measure(trial) > width:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return lines


__all__ = [
    "CELL",
    "FACES_DIR",
    "FONT_SHEET_ID",
    "Face",
    "GameFace",
    "Glyph",
    "PixelFace",
    "TypesetError",
    "face_named",
    "pixel_face",
    "wrap",
]
