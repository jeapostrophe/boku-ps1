"""The font sheet's glyph table: bytes on the disc <-> readable text (`research/font.md`).

Text is 16-bit little-endian words. Bit 15 clear is a glyph id into the one 1,512-slot
sheet; bit 15 set is a control word, and only three of them occur in the whole game
(`research/text-format.md`):

| word | token | |
|---|---|---|
| `0x8000` | `{END}` | ends a message |
| `0x8001` | `{NL}` | newline — a new column, since dialogue is vertical |
| `0x8002 p` | `{PAGE:p}` | page break; `p` is the frame countdown that turns the page |

`decode` turns a site's bytes into that token text and `encode` turns it back, byte for
byte. The round trip has to be exact, because it is what pins the encoder `PIPE-03` will
reinsert with. So an id whose character the sheet draws twice — `research/font.md` § "The
glyph table and how it was verified" names those cells — and an id with no character at
all decode to `{G:<id>}`, not to something that comes back as the other id.
"""

from __future__ import annotations

import csv
import hashlib
import re
import struct
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from boku import REPO_ROOT

GLYPH_TSV = REPO_ROOT / "research/data/glyph-table.tsv"

END_WORD = 0x8000
"""Ends a message. Everything after it inside the same site is never read."""
NEWLINE_WORD = 0x8001
PAGE_WORD = 0x8002
PAD_WORD = 0x0000
"""The blank cell, glyph 0 — what a rewritten site is filled out with after its `END`."""

SHEET_SLOTS = 1512
"""Cells on the one font sheet, ids 0-1511 (`research/font.md`): 21 x 4 x 18."""

_TOKEN_RE = re.compile(r"\{(END|NL|PAGE:\d+|G:\d+|C:[0-9A-F]{4})\}")


class TextError(Exception):
    """A site, a line id or a string the glyph sheet cannot honour."""


@dataclass(frozen=True)
class GlyphTable:
    """`research/data/glyph-table.tsv`, in both directions, plus the ASCII map for English.

    * `characters` — glyph id -> the character that cell draws, for ids the table names.
    * `unambiguous` — the subset that is one character naming exactly one id, so decoding
      to it and encoding back returns the same id. Everything else decodes as `{G:<id>}`:
      the doubled cells, and the seven whose `character` column is a bracketed
      description rather than a character (`[SEL]`, `[△L]`, the dashed rule — halves of
      two-cell button glyphs, none of which any text uses).
    * `to_glyph` — ASCII -> glyph id, derived by NFKC-normalising the full-width cells
      rather than transcribed, so it cannot drift from the table. Where two cells
      normalise alike the lower id wins, which keeps the map inside the punctuation block
      at the head of the sheet; choosing per writing direction is `TXT-05`'s job.
    """

    characters: dict[int, str]
    unambiguous: dict[int, str]
    to_glyph: dict[str, int]
    from_character: dict[str, int]
    """`unambiguous` inverted — the map `encode` spells plain text with."""
    source_sha1: str
    """SHA-1 of the table file, so an extract says which table it was decoded with."""

    @classmethod
    def load(cls, path: Path = GLYPH_TSV) -> GlyphTable:
        if not path.is_file():
            raise TextError(f"{path} is missing; it is committed, so this checkout is incomplete")
        raw = path.read_bytes()
        characters: dict[int, str] = {}
        ascii_map: dict[str, int] = {}
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                drawn = row["character"]
                if not drawn:
                    continue
                index = int(row["index"])
                characters[index] = drawn
                plain = unicodedata.normalize("NFKC", drawn)
                ascii_like = len(plain) == 1 and 0x20 <= ord(plain) < 0x7F
                if ascii_like and (plain not in ascii_map or index < ascii_map[plain]):
                    ascii_map[plain] = index
        owners: dict[str, list[int]] = {}
        for index, drawn in characters.items():
            owners.setdefault(drawn, []).append(index)
        unambiguous = {
            index: drawn
            for index, drawn in characters.items()
            if len(drawn) == 1 and len(owners[drawn]) == 1 and drawn not in "{}"
        }
        return cls(
            characters=characters,
            unambiguous=unambiguous,
            to_glyph=ascii_map,
            from_character={drawn: index for index, drawn in unambiguous.items()},
            source_sha1=hashlib.sha1(raw).hexdigest(),
        )

    # --- reading the disc ----------------------------------------------------------------

    def decode(self, raw: bytes) -> str:
        """A site's bytes as readable text with control words written as tokens.

        `encode` is its exact inverse for every byte string of an even length, which is
        the property gate (2) checks over all 6,000-odd sites.
        """
        out: list[str] = []
        for token in iter_tokens(raw):
            if token.word == END_WORD:
                out.append("{END}")
            elif token.word == NEWLINE_WORD:
                out.append("{NL}")
            elif token.word == PAGE_WORD:
                if token.param is None:
                    raise TextError("a page break at the end of a site has no parameter")
                out.append(f"{{PAGE:{token.param}}}")
            elif token.is_control:
                out.append(f"{{C:{token.word:04X}}}")
            else:
                out.append(self.unambiguous.get(token.word) or f"{{G:{token.word}}}")
        return "".join(out)

    def encode(self, text: str) -> bytes:
        """Token text back to bytes. The inverse of `decode`; raises on anything unknown."""
        out = bytearray()
        pos = 0
        for match in _TOKEN_RE.finditer(text):
            out += self._plain(text[pos : match.start()])
            token = match.group(1)
            if token == "END":
                out += END_WORD.to_bytes(2, "little")
            elif token == "NL":
                out += NEWLINE_WORD.to_bytes(2, "little")
            elif token.startswith("PAGE:"):
                out += PAGE_WORD.to_bytes(2, "little")
                out += _u16(int(token[5:]), token)
            elif token.startswith("G:"):
                out += _u16(int(token[2:]), token)
            else:
                out += _u16(int(token[2:], 16), token)
            pos = match.end()
        out += self._plain(text[pos:])
        return bytes(out)

    def _plain(self, run: str) -> bytes:
        out = bytearray()
        for character in run:
            index = self.from_character.get(character)
            if index is None:
                raise TextError(f"the font sheet draws no cell for {character!r}")
            out += index.to_bytes(2, "little")
        return bytes(out)

    # --- writing English -----------------------------------------------------------------
    #
    # `encode` above and `encode_english` below are different jobs and must not be
    # confused: `encode` is the exact inverse of `decode` over the sheet's own cells, and
    # `encode_english` spells ASCII with the full-width Latin cells, which is what a
    # translation is written in until `TXT-05` decides what the sheet becomes.

    def unencodable(self, text: str) -> list[str]:
        """The characters of `text` this font cannot draw, in order, without repeats."""
        return unencodable_by(self.to_glyph.__contains__, text)

    def encode_english(self, text: str) -> bytes:
        """`text` as glyph words, `\\n` becoming `0x8001`. No terminator.

        Raises `TextError` naming every character the sheet has no cell for, rather than
        substituting one: a silent substitution is how a trial proves the wrong thing.
        """
        missing = self.unencodable(text)
        if missing:
            raise TextError(
                f"the font sheet draws no cell for {''.join(missing)!r} "
                f"(research/data/glyph-table.tsv); {text!r} cannot be encoded"
            )
        words = bytearray()
        for character in text:
            value = NEWLINE_WORD if character == "\n" else self.to_glyph[character]
            words += value.to_bytes(2, "little")
        return bytes(words)

    def message(self, text: str, size: int) -> bytes:
        """`text` as a complete `size`-byte replacement for a message site.

        The glyph words, `0x8000`, then `0x0000` to the original length. The site keeps
        its byte size because the image is patched in place (`PIPE-04`), and the filler is
        never read: a message reader stops at the first `0x8000`.
        """
        if size % 2:
            raise TextError(f"a text site is a whole number of 16-bit words; {size} is not")
        body = self.encode_english(text) + END_WORD.to_bytes(2, "little")
        if len(body) > size:
            raise TextError(
                f"{text!r} encodes to {len(body)} bytes and the site holds {size}; "
                f"nothing is cut to fit (README), so the trial refuses"
            )
        return body + PAD_WORD.to_bytes(2, "little") * ((size - len(body)) // 2)


def unencodable_by(has_cell, text: str) -> list[str]:
    """Characters `text` needs that `has_cell` says no to, in order, without repeats.

    `has_cell` is a predicate rather than a table so that the stock sheet and
    `boku.layout`'s encoders — which can be a cell map from a font build — answer the
    question the same way. A newline is never a cell: it is the control word `0x8001`.
    """
    missing: list[str] = []
    for character in text:
        if character != "\n" and not has_cell(character) and character not in missing:
            missing.append(character)
    return missing


def words_to_bytes(words) -> bytes:
    """Little-endian `u16`s — the inverse of `words_of`, refusing a value that is not one."""
    for word in words:
        if not 0 <= word <= 0xFFFF:
            raise TextError(f"{word} is not a 16-bit text word")
    return struct.pack(f"<{len(words)}H", *words)


def _u16(value: int, token: str) -> bytes:
    if not 0 <= value <= 0xFFFF:
        raise TextError(f"{{{token}}} is not a 16-bit word")
    return value.to_bytes(2, "little")


def words_of(raw: bytes) -> tuple[int, ...]:
    """A byte string as little-endian `u16`s, refusing an odd length rather than truncating."""
    if len(raw) % 2:
        raise TextError(f"text is a whole number of 16-bit words; {len(raw)} bytes is not")
    return struct.unpack_from(f"<{len(raw) // 2}H", raw)


class Token(NamedTuple):
    """One word of a text site, with a page break's parameter attached rather than loose.

    Every reader of this format has to know that `0x8002` swallows the word after it;
    before `iter_tokens` existed each of them re-implemented that step, and a page break's
    countdown was counted as a drawn cell in some of them and not in others.
    """

    word: int
    param: int | None
    """The frame countdown of a page break, `None` for everything else. It is also `None`
    for a page break that is the last word of a site — a truncation `decode` refuses and
    the extent walkers report, so this walk stays total."""
    end: int
    """Byte offset inside the site one past this token, the parameter included."""

    @property
    def is_control(self) -> bool:
        return bool(self.word & 0x8000)

    @property
    def is_glyph(self) -> bool:
        """A drawn cell. Glyph 0 is the blank cell and is still a cell."""
        return not self.word & 0x8000


def iter_tokens(raw: bytes) -> Iterator[Token]:
    """The words of a site, one token per *drawn or acted-on* word."""
    words = words_of(raw)
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        if word == PAGE_WORD and i < len(words):
            param = words[i]
            i += 1
            yield Token(word, param, 2 * i)
        elif word == PAGE_WORD:
            yield Token(word, None, 2 * i)
        else:
            yield Token(word, None, 2 * i)
