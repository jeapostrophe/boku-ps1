"""Text sites, placed into the files of an import, and addressed by logical line id.

`boku.sites` walks the archive structurally and produces one `Site` per *physical* text
site, grouped into logical lines. This module places those sites into the two files a
patch actually writes — `SCPS_100.88` and `BOKU.BIN` — and answers the one question
`TXT-04` and `PIPE-03` ask: *given a line id, which byte ranges have to change?*

**The id is the logical line, and it names every copy.** `E0171.0` is the opening line of
the game; its sites are every map variant that embeds event 171, plus the `EV.BIN` member
when there is one. The earlier model keyed `E<id>.<index>` to `EV.BIN` alone and gave
map-resident copies a `M_H02001.BIN:c1:0:171.0` name of their own, which made the opening
line — a map-resident block with no `EV` copy — impossible to ask for by event id.

**What proves a write is safe lives in `boku.build.verify_edits` now.** The walk reads
`disc/files/`, which the import step extracted from the image; a build writes into the
image's own embedded copy of those files. The two are separate artifacts, so reading a
byte range back through the image and finding what the walk read there is a real
cross-check — it fails on a mis-resolved member offset, on an image that is not this game,
and on an import whose files no longer match the image they came from. This module used to
do that a site at a time against a hash; the builder does it over whole byte ranges,
including the rebuilt containers a hashed site could not see.

The glyph sheet moved to `boku.glyphs`; it is re-exported here because `GlyphTable` and
`TextError` are what a caller wanting "text" reaches for.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from boku.archive import ARCHIVE_NAME, DEFAULT_DISC_DIR, EXE_NAME, Archive
from boku.glyphs import END_WORD, NEWLINE_WORD, PAD_WORD, GlyphTable, TextError
from boku.sites import LINE_KEY_LENGTH, Site, SiteError, Walk, line_key_of, load

__all__ = [
    "ARCHIVE_NAME",
    "END_WORD",
    "EXE_NAME",
    "LINE_KEY_LENGTH",
    "MESSAGE_KINDS",
    "NEWLINE_WORD",
    "PAD_WORD",
    "GlyphTable",
    "PlacedSite",
    "Site",
    "SiteError",
    "SiteIndex",
    "TextError",
    "line_key_of",
]

MESSAGE_KINDS = ("MSG", "MSG+XA")
"""Sites a terminator can be written into early; `boku.trial._check_writable` says why."""


@dataclass(frozen=True)
class PlacedSite:
    """A site resolved to a byte range of a named file, with the hash of what is there."""

    site: Site
    file_name: str
    file_offset: int
    line_key: str
    """SHA-1 prefix of the bytes the walk read here. `SiteIndex.copies_of` groups sites
    by it, which is how `--line` accepts a `line_key` as well as a logical id."""

    @property
    def end(self) -> int:
        return self.file_offset + self.site.size

    @property
    def line_id(self) -> str:
        return self.site.line_id


class SiteIndex:
    """Every text site of one import, placed into its file and grouped by logical line."""

    def __init__(
        self, placed: Iterable[PlacedSite], *, archive: Archive | None, walk: Walk | None
    ) -> None:
        self.archive = archive
        """The import these sites were read out of, or `None` for an index built by hand.

        Keyword-only and without a default, so that "this index cannot rebuild anything"
        is a thing the caller **says**, rather than a thing it forgets to pass."""
        self.walk = walk
        """The structural walk they came from — what `boku.reinsert` needs to rebuild a
        container. It is kept rather than walked again because walking the whole archive
        is seconds of work over 109 MB, and a second walk could disagree with the first.
        Required, not optional: `boku.trial` reads it for every `--line`, so an index
        without one is an object that works until somebody asks it the one question a
        reinserter has."""
        self.placed = list(placed)
        self._by_line: dict[str, list[PlacedSite]] = {}
        self._by_key: dict[str, list[PlacedSite]] = {}
        seen: set[tuple[str, int]] = set()
        for entry in self.placed:
            where = (entry.file_name, entry.file_offset)
            if where in seen:
                raise TextError(
                    f"two text sites both start at {entry.file_name}"
                    f"+0x{entry.file_offset:x}; a site has to name one byte range"
                )
            seen.add(where)
            self._by_line.setdefault(entry.line_id, []).append(entry)
            self._by_key.setdefault(entry.line_key, []).append(entry)

    @classmethod
    def from_disc(cls, disc_dir: Path = DEFAULT_DISC_DIR) -> SiteIndex:
        """Walk a contributor's own import and place every site it finds."""
        archive, result = load(disc_dir)
        placed = []
        for site in result.sites:
            file_name = EXE_NAME if site.file == "EXE" else ARCHIVE_NAME
            placed.append(
                PlacedSite(site, file_name, site.absolute, line_key_of(result.raw(archive, site)))
            )
        return cls(placed, archive=archive, walk=result)

    def __len__(self) -> int:
        return len(self.placed)

    @property
    def line_ids(self) -> list[str]:
        return list(self._by_line)

    def event_messages(self) -> Iterator[PlacedSite]:
        """Every event-script message site — map-resident and `EV.BIN` alike, in file order."""
        return (entry for entry in self.placed if entry.site.is_message)

    def copies_of(self, line: str) -> list[PlacedSite]:
        """Every physical copy of one line, named by its id or by a 12-hex-digit `line_key`.

        A `line_key` groups sites whose *bytes* are equal, which is a coarser thing —
        `research/text-format.md` § Reconciliation counts how many byte strings this disc
        shares between logical lines (yes/no selects, repeated system lines). An id names
        exactly the copies of that one line, which is what a reinserter must rewrite.
        """
        if line in self._by_line:
            return list(self._by_line[line])
        if line in self._by_key:
            return list(self._by_key[line])
        raise TextError(
            f"no text site is called {line!r}: give a line id such as E0171.0 or "
            f"exe@80046214.3 (they are listed in disc/script/lines.jsonl), or a "
            f"{LINE_KEY_LENGTH}-hex-digit line_key"
        )
