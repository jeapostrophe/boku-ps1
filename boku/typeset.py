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
    """`CELL` rows, top of the cell first; each a tuple of x offsets."""


class Face:
    """A 1-bit typeface set into a `CELL`-row line box: glyphs, advances, measurement.

    The one space is U+0020 and `\\n` is `wrap`'s forced break. Any other whitespace -- a
    tab, a no-break or an ideographic space an IME slips in -- has no drawing and is
    reported by `missing`, because setting it at zero width runs two words together."""

    name: ClassVar[str] = "?"
    space: int = SPACE

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
        the sheet's only dash is a full-width minus, `research/font-candidates.md` § 1),
        plus the apostrophe."""
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

    def glyph(self, ch: str) -> Glyph | None:
        if ch not in self._cache:
            glyph_id = self.cells.get(ch)
            found = None
            if glyph_id is not None:
                bits = self._bits(glyph_id)
                inked = [c for r in range(CELL) for c in range(CELL) if bits[r][c]]
                if inked:
                    left, right = min(inked), max(inked)
                    found = Glyph(
                        width=right - left + 1,
                        rows=tuple(
                            tuple(c - left for c in range(left, right + 1) if bits[r][c])
                            for r in range(CELL)
                        ),
                    )
            self._cache[ch] = found
        return self._cache[ch]


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
    "FONT_SHEET_ID",
    "Face",
    "GameFace",
    "Glyph",
    "TypesetError",
    "wrap",
]
