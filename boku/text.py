"""Where the game's text physically lives, and how English is spelled in its font.

Two committed tables under `research/data/` describe every byte of Japanese on the disc,
and this module turns them into something a writer can aim at:

* `text-sites.tsv` (`REC-03`) -- one row per *physical* text site: the member that holds
  it, its offset inside that member, its byte size, the slack after it, what kind of
  reader consumes it, and `line_key`, the SHA-1 prefix of the site's own bytes. Sites
  that share a `line_key` are copies of one logical line; the disc has 6,183 sites and
  2,426 distinct lines, one of them repeated 53 times.
* `boku-bin-members.tsv` (`REC-01`) -- where each member starts inside `BOKU.BIN`.

Nothing here trusts those tables. `line_key` is a hash of the very bytes a site claims,
so `check_placement` re-reads each site from the contributor's own image and refuses
when the hash disagrees: a table that has drifted from the disc cannot silently aim a write at
the wrong offset. That check is why this module reads the committed tables instead of
re-running `REC-03`'s structural walk -- the walk's output is verifiable against the
source of truth, so re-deriving it would add code without adding a gate.

Text itself is 16-bit glyph indices into the font sheet, little-endian, with `0x8000`
ending a message and `0x8001` breaking a line (`research/text-format.md`). The glyph
sheet's Latin letters are full-width, so `research/data/glyph-table.tsv`'s `character`
column maps back to ASCII under NFKC normalisation and that is how English is encoded --
derived from the table rather than transcribed from it.
"""

from __future__ import annotations

import csv
import hashlib
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITES_TSV = REPO_ROOT / "research/data/text-sites.tsv"
MEMBERS_TSV = REPO_ROOT / "research/data/boku-bin-members.tsv"
GLYPH_TSV = REPO_ROOT / "research/data/glyph-table.tsv"

EXE_NAME = "SCPS_100.88"
ARCHIVE_NAME = "BOKU.BIN"

END_WORD = 0x8000
"""Ends a message. Everything after it inside the same site is never read."""
NEWLINE_WORD = 0x8001
PAD_WORD = 0x0000
"""The blank cell, glyph 0. What this module writes after `END_WORD` to fill a site."""

LINE_KEY_LENGTH = 12
"""`REC-03` keys a line by the first 12 hex digits of the SHA-1 of its bytes."""

MESSAGE_KINDS = ("MSG", "MSG+XA")
"""Sites a terminator can be written into early; `boku.trial._check_writable` says why."""


class TextError(Exception):
    """A site, a line id or a string this module cannot honour."""


def line_key_of(raw: bytes) -> str:
    return hashlib.sha1(raw).hexdigest()[:LINE_KEY_LENGTH]


@dataclass(frozen=True)
class TextSite:
    """One physical text site, as `research/data/text-sites.tsv` records it."""

    member: str
    container: str
    table: int
    block_id: int
    index: int
    offset: int
    """Byte offset inside `member` -- inside the EXE file for `SCPS_100.88`."""
    size: int
    slack: int
    kind: str
    line_key: str

    @property
    def in_exe(self) -> bool:
        return self.member == EXE_NAME

    @property
    def is_event_message(self) -> bool:
        """An event-script message: what the dialogue box draws, and what `TXT-04` needs."""
        return self.container == "ev" and self.kind in MESSAGE_KINDS

    @property
    def site_id(self) -> str:
        """A name that picks out this one site. Event messages read `E0112.0` (`TXT-04`'s).

        Everything else reads `M_H02001.BIN:c1:0:171.0` -- member, container, table,
        then the same `block.index` the event form ends in. Both numbers are in there
        for a reason. **Table**, because without it the name is not unique: a member's
        `c1` container holds several tables and their indices restart, so 2,365 of the
        disc's 6,183 sites shared a name with another site and `copies_of` answered with
        whichever row the table listed first. **Block**, because for a map-resident
        script it is the event id `research/data/scenes.tsv` uses -- the opening line of
        the game is `E0171` there and `M_H02001.BIN:c1:0:171.0` here, and an id that
        dropped it would make that impossible to see. `SiteIndex` refuses a collision
        outright, so uniqueness has a second guard.
        """
        if self.container == "ev":
            return f"E{self.block_id:04d}.{self.index}"
        return f"{self.member}:{self.container}:{self.table}:{self.block_id}.{self.index}"


def load_sites(path: Path = SITES_TSV) -> list[TextSite]:
    """Every row of `text-sites.tsv`, in file order."""
    if not path.is_file():
        raise TextError(f"{path} is missing; it is committed, so this checkout is incomplete")
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            TextSite(
                member=row["member"],
                container=row["container"],
                table=int(row["table"]),
                block_id=int(row["block_id"]),
                index=int(row["index"]),
                offset=int(row["offset"], 16),
                size=int(row["size"]),
                slack=int(row["slack"]),
                kind=row["kind"],
                line_key=row["line_key"],
            )
            for row in csv.DictReader(handle, delimiter="\t")
        ]


def load_member_offsets(path: Path = MEMBERS_TSV) -> dict[str, int]:
    """Member base name -> its byte offset inside `BOKU.BIN`.

    The base names are unique across the archive's 1,302 members (checked here rather
    than assumed, since the whole offset resolution hangs off it).
    """
    if not path.is_file():
        raise TextError(f"{path} is missing; it is committed, so this checkout is incomplete")
    offsets: dict[str, int] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            name = row["name"].rsplit("\\", 1)[-1]
            if name in offsets:
                raise TextError(f"{path}: two members are named {name}")
            offsets[name] = int(row["offset"], 16)
    return offsets


# --- the glyph sheet ------------------------------------------------------------------


@dataclass(frozen=True)
class GlyphTable:
    """ASCII -> glyph index, derived from `glyph-table.tsv`'s `character` column.

    The sheet's Latin letters, digits and much of its punctuation are full-width, so
    NFKC normalisation maps each cell back to the ASCII character it draws. Exactly one
    character is drawn twice: `)` is glyph 22 (rotated for vertical writing) and glyph
    1456 (the narrow horizontal form `TITLE.OVL` uses). The lower index wins here, which
    keeps the whole map inside the punctuation block at the head of the sheet; choosing
    per writing direction is the renderer work in `TXT-05`, not the trial's.
    """

    to_glyph: dict[str, int]

    @classmethod
    def load(cls, path: Path = GLYPH_TSV) -> GlyphTable:
        if not path.is_file():
            raise TextError(f"{path} is missing; it is committed, so this checkout is incomplete")
        mapping: dict[str, int] = {}
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                drawn = row["character"]
                if not drawn:
                    continue
                plain = unicodedata.normalize("NFKC", drawn)
                if len(plain) != 1 or not (0x20 <= ord(plain) < 0x7F):
                    continue
                index = int(row["index"])
                if plain not in mapping or index < mapping[plain]:
                    mapping[plain] = index
        return cls(to_glyph=mapping)

    def unencodable(self, text: str) -> list[str]:
        """The characters of `text` this font cannot draw, in order, without repeats."""
        missing: list[str] = []
        for character in text:
            if character != "\n" and character not in self.to_glyph and character not in missing:
                missing.append(character)
        return missing

    def encode(self, text: str) -> bytes:
        """`text` as glyph words, with `\\n` becoming `0x8001`. No terminator.

        Raises `TextError` naming every character the sheet has no cell for, rather than
        substituting one: a silent substitution is how a trial ends up proving the wrong
        thing.
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

        The result is the glyph words, `0x8000`, then `0x0000` to the original length.
        The site keeps its byte size because the image is patched in place (`PIPE-04`),
        and the filler is never read: a message reader stops at the first `0x8000`.
        """
        if size % 2:
            raise TextError(f"a text site is a whole number of 16-bit words; {size} is not")
        body = self.encode(text) + END_WORD.to_bytes(2, "little")
        if len(body) > size:
            raise TextError(
                f"{text!r} encodes to {len(body)} bytes and the site holds {size}; "
                f"nothing is cut to fit (README), so the trial refuses"
            )
        return body + PAD_WORD.to_bytes(2, "little") * ((size - len(body)) // 2)


# --- resolving a site to a place in a file --------------------------------------------


@dataclass(frozen=True)
class PlacedSite:
    """A site resolved to a byte range of a named file on the disc."""

    site: TextSite
    file_name: str
    file_offset: int

    @property
    def end(self) -> int:
        return self.file_offset + self.site.size


class SiteIndex:
    """`text-sites.tsv` placed into `SCPS_100.88` and `BOKU.BIN`, and grouped by line."""

    def __init__(
        self,
        sites: Iterable[TextSite] | None = None,
        member_offsets: dict[str, int] | None = None,
    ) -> None:
        self.sites = list(sites) if sites is not None else load_sites()
        offsets = member_offsets if member_offsets is not None else load_member_offsets()
        placed: list[PlacedSite] = []
        for site in self.sites:
            if site.in_exe:
                placed.append(PlacedSite(site, EXE_NAME, site.offset))
                continue
            if site.member not in offsets:
                raise TextError(
                    f"text-sites.tsv names member {site.member}, which is not in "
                    f"boku-bin-members.tsv"
                )
            placed.append(PlacedSite(site, ARCHIVE_NAME, offsets[site.member] + site.offset))
        self.placed = placed
        self._by_key: dict[str, list[PlacedSite]] = {}
        self._by_site_id: dict[str, PlacedSite] = {}
        for entry in placed:
            self._by_key.setdefault(entry.site.line_key, []).append(entry)
            site_id = entry.site.site_id
            clash = self._by_site_id.get(site_id)
            if clash is not None:
                raise TextError(
                    f"two text sites are both called {site_id}: {clash.file_name}"
                    f"+0x{clash.file_offset:x} and {entry.file_name}"
                    f"+0x{entry.file_offset:x}. A site id has to name one site, or "
                    f"`--line {site_id}` writes to whichever row came first."
                )
            self._by_site_id[site_id] = entry

    def __len__(self) -> int:
        return len(self.placed)

    @property
    def line_keys(self) -> list[str]:
        return list(self._by_key)

    def event_messages(self) -> Iterator[PlacedSite]:
        """Every event-script message site, in file order."""
        return (entry for entry in self.placed if entry.site.is_event_message)

    def copies_of(self, line: str) -> list[PlacedSite]:
        """Every physical copy of one logical line, named by `line_key` or by a site id.

        A site id such as `E0112.0` names one site; the line it holds is then looked up
        by `line_key`, so the answer is still *every* copy of that line -- which is what
        `TXT-04` overwrites.
        """
        if line in self._by_key:
            return list(self._by_key[line])
        entry = self._by_site_id.get(line)
        if entry is None:
            raise TextError(
                f"no text site is called {line!r}: give a 12-hex-digit line_key from "
                f"research/data/text-sites.tsv, or a site id such as E0112.0"
            )
        return list(self._by_key[entry.site.line_key])


def check_placement(entry: PlacedSite, raw: bytes) -> None:
    """Raise unless `raw` -- the bytes actually on the disc there -- hashes to `line_key`.

    This is the gate that makes a committed table safe to write from: it fails on a table
    that has drifted, on a mis-resolved member offset, and on an image that is not this
    game, all before a single byte is written.
    """
    if len(raw) != entry.site.size:
        raise TextError(
            f"{entry.site.site_id}: read {len(raw)} bytes at {entry.file_name}"
            f"+0x{entry.file_offset:x}, the site is {entry.site.size}"
        )
    found = line_key_of(raw)
    if found != entry.site.line_key:
        raise TextError(
            f"{entry.site.site_id}: {entry.file_name}+0x{entry.file_offset:x} hashes to "
            f"{found}, but research/data/text-sites.tsv says {entry.site.line_key}. The "
            f"table and this image disagree; nothing was written."
        )
