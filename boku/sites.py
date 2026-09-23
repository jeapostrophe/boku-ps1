"""The structural walk: every physical text site on the disc, and what it belongs to.

`research/text-format.md` § "Reconciliation — the gate" is what this module implements.
The walk is *structural*: it reaches a message because a block's offset table points at it
and a bytecode operand names it, never because the bytes looked like text. The heuristic
`scan_text` below is kept only so the two can be reconciled — each has to explain the
other, in both directions.

**Physical site vs logical line.** A site is a byte range in one member. A logical line is
what a translator writes once: `E<event id>.<message index>` for event text, and
`<file>@<offset>.<item>` for a code-file array (`boku.arrays`). One logical line has 1 to
26 sites, because an event block is copied into every map variant where it can fire, and
**all of its copies must be byte-identical** — `Walk.conflicts` is that invariant checked,
not assumed.

The array half of the walk comes in two partitions, because the research did the work
twice and the second time was better:

* `"reader"` (the default, `REC-06`) — one string per item as the *reader* indexes it.
  This is what `lines.jsonl` is keyed by, and the only one whose ids mean anything.
* `"rec03"` — the earlier enumeration, which merged five separately indexed arrays into
  one 103-line array and could not see the five arrays that hold no control word. It is
  kept so `research/data/text-sites.tsv` keeps reproducing byte for byte.
"""

from __future__ import annotations

import hashlib
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from boku.archive import (
    DEFAULT_DISC_DIR,
    EXE_LOAD_BIAS,
    EXE_NAME,
    OVERLAY_LOAD_ADDRESS,
    Archive,
    parse_pack,
    tim_length,
)
from boku.arrays import SelectTables, legacy_spans, walk_all
from boku.events import OP_MSG, OP_SELECT, OP_XA, OP_XAMSG, Block, BlockInstance, Ins, iter_blocks
from boku.glyphs import END_WORD, NEWLINE_WORD, PAGE_WORD, iter_tokens, words_of
from boku.pointers import resolve_at

RESIDENT_BLOCK_ANCHORS = {0x80029920: 0x80019E3C, 0x80029A40: 0x80019E4C, 0x80029A8C: 0x80019E50}
"""Each block's retail address -> the `lui` in `0x80019DEC` (the system-event chooser) its
address is built from. A build may move a block whose message grew (`boku.array_relocate`),
so the walk reads the address from here, as the game does, and names the lines by the
retail address."""

RESIDENT_BLOCK_ADDRS = tuple(RESIDENT_BLOCK_ANCHORS)
"""Three event blocks compiled into the executable, chosen for system events
(`research/text-format.md` § "Blocks in the executable"). They have no length field, so
each is read with room to spare and its last entry parsed to its own terminator."""

RESIDENT_BLOCK_HEADROOM = 0x400


def resident_line_id(ram: int, index: int) -> str:
    """`exe@80029920.0`: message `index` of the resident block whose retail address is `ram`."""
    return f"exe@{ram:08X}.{index}"


def resident_block_at(archive: Archive, ram: int) -> int:
    """Where the chooser's pair says the resident block first found at `ram` now is."""
    lui = RESIDENT_BLOCK_ANCHORS[ram]
    return resolve_at(archive.exe_bytes, lui)


LINE_KEY_LENGTH = 12
"""`REC-03` keys a line by the first 12 hex digits of the SHA-1 of its bytes."""


def line_key_of(raw: bytes) -> str:
    return hashlib.sha1(raw).hexdigest()[:LINE_KEY_LENGTH]


class SiteError(Exception):
    """An import whose structural walk does not hold: a problem, or copies that differ."""


@dataclass(frozen=True)
class Site:
    """One physical text site: a byte range of one file, and what named it."""

    file: str
    """`"EXE"` or `"BOKU"` — which of the import's two files holds these bytes."""
    member: str
    """The archive member's leaf name, or `SCPS_100.88` for the executable."""
    container: str
    """`"c1"`, `"ev"`, `"exe-block"`, or `"array@0x<offset>"`."""
    table: int
    block_id: int
    index: int
    offset: int
    """Byte offset inside `member` (inside the EXE file when `member` is the executable)."""
    size: int
    slack: int
    """Bytes of build-tool pad between the text and the end of its block entry (0 or 2)."""
    kind: str
    """`MSG`, `SEL<type>.<variant>`, or `ARR-<shape>`, with `+XA` when a voice key exists."""
    line_id: str
    """The logical line this copy belongs to."""
    absolute: int
    """Byte offset inside the file named by `file`, for reading the bytes back."""

    @property
    def is_message(self) -> bool:
        """An event-script message — what the dialogue box draws, and what `TXT-04` needs."""
        return self.container in ("c1", "ev") and self.kind.startswith("MSG")


@dataclass
class Walk:
    """Every site on the disc, grouped into logical lines, with the problems found."""

    sites: list[Site] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    by_line: dict[str, list[Site]] = field(default_factory=dict)
    voice_only: dict[str, list[Site]] = field(default_factory=dict)
    """Every copy of every voice-only entry -- a voice key named only by `XA`, its text offset
    null: the slot `VO-02` writes a subtitle into. Kept out of `by_line` because no reader
    reaches it and the tables never list it. Each is a `MSG+XA` site of `size` 0 whose
    `offset`/`absolute` point at the entry's voice key, which times the subtitle."""

    def raw(self, archive: Archive, site: Site) -> bytes:
        source = archive.exe if site.file == "EXE" else archive.boku
        return source[site.absolute : site.absolute + site.size]

    def conflicts(self, archive: Archive) -> list[str]:
        """Logical ids whose physical copies are not byte-identical. Must be empty."""
        bad = []
        for line_id, sites in self.by_line.items():
            if len({self.raw(archive, s) for s in sites}) > 1:
                bad.append(line_id)
        return sorted(bad)


# --- reading one block --------------------------------------------------------------------


def iter_instructions(code: bytes):
    """Walk a code entry by its **size byte**, stopping at the zero-size 4-byte pad.

    This is `REC-03`'s lenient walker, and it is deliberately not `boku.events`'s, which
    advances by the opcode size table and refuses every disagreement. Running both over
    every block instance on the disc and getting the same message operands is a check on
    the size table (`research/text-format.md` § Reconciliation); collapsing them into one
    would throw that away. It yields the same `Ins` the strict walker does, so an operand
    is named the same way on both sides of that check.
    """
    p = 0
    while p + 2 <= len(code):
        n = code[p + 1]
        if n == 0:
            return
        yield Ins(p, code[p], code[p : p + 2 * n])
        p += 2 * n


def _message_extent(blk: bytes, o: int, limit: int) -> int | None:
    """Bytes of an `END`-terminated message at `o`, or `None` if it does not terminate."""
    for token in iter_tokens(blk[o : limit - (limit - o) % 2]):
        if token.word == END_WORD:
            return token.end
    return None


def _select_extent(blk: bytes, o: int, limit: int, lines: int) -> int | None:
    """Bytes of a select: `lines` lines, each ended by any bit-15 word, and no `END`.

    Words, not `iter_tokens`: in a select *every* bit-15 word ends a line, so `0x8002`
    would end one rather than take a parameter. Reading it as a page break here would
    silently lengthen the site by the word after it.
    """
    got = 0
    for i, w in enumerate(words_of(blk[o : limit - (limit - o) % 2])):
        if w & 0x8000:
            got += 1
            if got == lines:
                return 2 * (i + 1)
    return None


def walk_block(
    block: Block,
    select_lines,
    problems: list[str],
    where: str,
    voice_only: list[tuple[int, int]] | None = None,
) -> list[tuple[int, int, int, str, int, bool]]:
    """`(index, offset, size, kind, slack, voiced)` for every text entry of one block, and
    into `voice_only` `(index, offset of its key)` for each voice-only one (`Walk.voice_only`).

    Every structural claim is checked here rather than downstream: the header size, the
    odd entry count, the 12-byte voice keys, that each message operand is in range, that
    each message is named exactly one way, and that the pad after a text is 0 or 2 bytes.
    """
    k = block.n
    if block.offsets[0] != 4 + 4 * k:
        problems.append(f"{where}: first offset != header size")
    if k < 3:
        return []
    if k % 2 == 0:
        problems.append(f"{where}: even entry count {k}")
    refs: dict[int, set] = defaultdict(set)
    code_span = block.entry_span(2)
    code = block.data[code_span[0] : code_span[1]] if code_span else b""
    for i in iter_instructions(code):
        if i.op in (OP_XAMSG, OP_MSG):
            refs[i.message_index].add("MSG")
        elif i.op == OP_XA:
            refs[i.message_index].add("XA")
        elif i.op == OP_SELECT:
            refs[i.message_index].add(("SEL", i.select_type, i.select_variant))
    pairs = (k - 3) // 2
    for i in sorted(set(refs) - set(range(pairs))):
        problems.append(f"{where}: bytecode names message {i} of {pairs}")
    out = []
    for i in range(pairs):
        key_span = block.entry_span(3 + 2 * i)
        text_span = block.entry_span(4 + 2 * i)
        named = refs.get(i, set())
        if key_span and key_span[1] - key_span[0] != 12:
            problems.append(f"{where}: key {i} is {key_span[1] - key_span[0]} bytes")
        if text_span is None:
            if named - {"XA"}:
                problems.append(f"{where}: null text {i} referenced as {named}")
            elif named and key_span and voice_only is not None:
                voice_only.append((i, key_span[0]))
            continue
        if named == {"XA"}:
            named = {"MSG"}  # a voice-only entry a build gave a subtitle (VO-02)
        named -= {"XA"}
        if len(named) > 1:
            problems.append(f"{where}: message {i} referenced two ways {named}")
        select = next((x for x in named if x != "MSG"), None)
        to, limit = text_span
        if select:
            lines = select_lines(select[1], select[2])
            size = _select_extent(block.data, to, limit, lines)
            kind = f"SEL{select[1]}.{select[2]}"
        else:
            size = _message_extent(block.data, to, limit)
            kind = "MSG"
            if not named:
                problems.append(f"{where}: message {i} is named by no MSG/XAMSG/SELECT opcode")
        if size is None:
            problems.append(f"{where}: message {i} ({kind}) does not terminate inside its entry")
            continue
        slack = limit - to - size
        if slack not in (0, 2) and "exe-block" not in where:
            problems.append(f"{where}: message {i} slack {slack}")
        out.append((i, to, size, kind, slack, bool(key_span)))
    return out


def _block_site(inst: BlockInstance, i: int, to: int, size: int, slack: int, kind: str) -> Site:
    """Message `i` of a block in `BOKU.BIN`, `to` bytes into the block."""
    return Site(
        file="BOKU",
        member=inst.member.short_name,
        container=inst.container,
        table=inst.table,
        block_id=inst.event_id,
        index=i,
        offset=inst.offset_in_member + to,
        size=size,
        slack=slack,
        kind=kind,
        line_id=f"E{inst.event_id:04d}.{i}",
        absolute=inst.member.offset + inst.offset_in_member + to,
    )


# --- the whole disc --------------------------------------------------------------------------


def walk(archive: Archive, array_partition: str = "reader", *, code_files: bool = True) -> Walk:
    """Every physical text site, in the order `research/data/text-sites.tsv` lists them.

    `code_files=False` leaves out the executable's three resident blocks and the code-file
    arrays, walking only the event containers in `BOKU.BIN`. It exists for the disc-free
    tests, whose archives have no executable text in them at all — every real walk keeps
    it on, and `load` below has no switch for it.
    """
    if array_partition not in ("reader", "rec03"):
        raise ValueError(f"unknown array partition {array_partition!r}")
    result = Walk()
    result.problems += archive.problems
    select_lines = SelectTables(archive)

    def add(site: Site) -> None:
        result.sites.append(site)
        result.by_line.setdefault(site.line_id, []).append(site)

    for inst in iter_blocks(archive):
        block = Block(inst.data)
        where = f"{inst.member.short_name} {inst.container}[{inst.table}] id {inst.event_id}"
        voice_only: list[tuple[int, int]] = []
        entries = walk_block(block, select_lines, result.problems, where, voice_only)
        for i, to, size, kind, slack, voiced in entries:
            add(_block_site(inst, i, to, size, slack, kind + ("+XA" if voiced else "")))
        for i, key_at in voice_only:
            slot = _block_site(inst, i, key_at, 0, 0, "MSG+XA")
            result.voice_only.setdefault(slot.line_id, []).append(slot)

    if not code_files:
        return result

    for ram in RESIDENT_BLOCK_ADDRS:
        fo = resident_block_at(archive, ram) - EXE_LOAD_BIAS
        (k,) = struct.unpack_from("<I", archive.exe, fo)
        offsets = struct.unpack_from(f"<{k}I", archive.exe, fo + 4)
        block = Block(archive.exe[fo : fo + max(offsets) + RESIDENT_BLOCK_HEADROOM])
        where = f"{EXE_NAME} exe-block[0] id -1"
        for i, to, size, kind, _slack, voiced in walk_block(
            block, select_lines, result.problems, where
        ):
            add(
                Site(
                    file="EXE",
                    member=EXE_NAME,
                    container="exe-block",
                    table=0,
                    block_id=-1,
                    index=i,
                    offset=fo + to,
                    size=size,
                    slack=0,
                    kind=kind + ("+XA" if voiced else ""),
                    line_id=resident_line_id(ram, i),
                    absolute=fo + to,
                )
            )

    if array_partition == "reader":
        _add_reader_arrays(archive, add)
    else:
        _add_rec03_arrays(archive, add, result.problems)
    return result


def _image_base(archive: Archive, image: str) -> tuple[int, int, str, str]:
    """`(RAM bias, archive offset, file tag, file name)` for `"exe"` or an overlay stem."""
    if image == "exe":
        return EXE_LOAD_BIAS, 0, "EXE", EXE_NAME
    member = archive.member(f"{image.upper()}.OVL")
    return OVERLAY_LOAD_ADDRESS, member.offset, "BOKU", member.short_name


def _add_reader_arrays(archive: Archive, add) -> None:
    """One site per translatable string, as `research/text-outside-events.md` defines them."""
    for walked in walk_all(archive):
        array = walked.array
        bias, member_offset, file_tag, file_name = _image_base(archive, walked.image)
        container = f"array@{array.file_offset:#x}"
        for i, (start, end) in enumerate(walked.strings):
            file_offset = start - bias
            add(
                Site(
                    file=file_tag,
                    member=file_name,
                    container=container,
                    table=0,
                    block_id=0,
                    index=i,
                    offset=file_offset,
                    size=end - start,
                    slack=0,
                    kind=f"ARR-{array.shape}",
                    line_id=walked.line_ids[i],
                    absolute=member_offset + file_offset,
                )
            )


def _add_rec03_arrays(archive: Archive, add, problems: list[str]) -> None:
    """`REC-03`'s partition, kept so the tracked TSV keeps reproducing."""
    for span in legacy_spans(archive):
        bias, member_offset, file_tag, file_name = _image_base(archive, span.image)
        start, end = span.start - bias, span.end - bias
        source = archive.exe if span.image == "exe" else archive.boku[member_offset:]
        container = f"array@{start:#x}"
        if span.shape == "S":
            items = [(start, end)]
        else:
            items = []
            p = start
            while p < end:
                q = p
                while q < end:
                    (w,) = struct.unpack_from("<H", source, q)
                    q += 2
                    if w == PAGE_WORD and span.shape == "E":
                        q += 2
                    elif (w == END_WORD) if span.shape == "E" else (w & 0x8000):
                        break
                items.append((p, q))
                p = q
        (last,) = struct.unpack_from("<H", source, end - 2)
        if not last & 0x8000:
            problems.append(f"{span.image} array {span.start:#x}: does not end on a control word")
        if span.shape == "E" and last != END_WORD:
            problems.append(f"{span.image} array {span.start:#x}: E array not END-terminated")
        prefix = f"exe@{span.start:08X}" if span.image == "exe" else f"{span.image}@{start:X}"
        for i, (p, q) in enumerate(items):
            add(
                Site(
                    file=file_tag,
                    member=file_name,
                    container=container,
                    table=0,
                    block_id=0,
                    index=i,
                    offset=p,
                    size=q - p,
                    slack=0,
                    kind=f"ARR-{span.shape}",
                    line_id=f"{prefix}.{i}",
                    absolute=member_offset + p,
                )
            )


def load(
    disc_dir: Path = DEFAULT_DISC_DIR,
    array_partition: str = "reader",
    archive: Archive | None = None,
    result: Walk | None = None,
) -> tuple[Archive, Walk]:
    """Open an import, walk it, and refuse it unless the whole id scheme holds.

    One place decides what "a usable import" means — the archive tiles, the walk found no
    problem, and no logical line has physical copies that differ in bytes. `boku extract`
    and `boku.text.SiteIndex` each used to open, walk and check for themselves, and each
    raised a near-identical sentence under a different exception type.

    `archive` and `result` let a caller that has already opened or already walked this
    import hand that work in; the checks are the same either way.
    """
    archive = archive if archive is not None else Archive(disc_dir)
    archive.require_clean()
    if result is None:
        result = walk(archive, array_partition=array_partition)
    if result.problems:
        raise SiteError(
            f"the structural walk found {len(result.problems)} problems, first: "
            f"{result.problems[0]}"
        )
    conflicts = result.conflicts(archive)
    if conflicts:
        raise SiteError(
            f"{len(conflicts)} logical lines have physical copies that differ in bytes, "
            f"first {conflicts[0]}. research/text-format.md says there are none, so either "
            f"this dump is not SCPS-10088 or the id scheme is wrong; writing one copy of a "
            f"line would leave another behind."
        )
    return archive, result


# --- statistics and reconciliation -------------------------------------------------------------


def control_words(raw: bytes) -> Counter[int]:
    """The control words in a site, with a page break's parameter skipped, not counted."""
    return Counter(t.word for t in iter_tokens(raw) if t.is_control)


def glyph_count(raw: bytes) -> int:
    """Drawn cells: every non-control word except a page break's parameter."""
    return sum(1 for t in iter_tokens(raw) if t.is_glyph)


def page_structure(raw: bytes) -> list[list[int]]:
    """Glyphs per column, per page — the layout the box has to hold.

    A page break ends a page, a newline ends a column, and `END` ends both. What this
    disc's messages actually reach is in `research/text-format.md` § "The dialogue box".
    """
    pages: list[list[int]] = []
    columns: list[int] = []
    cur = 0
    for token in iter_tokens(raw):
        if token.word == NEWLINE_WORD:
            columns.append(cur)
            cur = 0
        elif token.word in (PAGE_WORD, END_WORD):
            columns.append(cur)
            pages.append(columns)
            columns, cur = [], 0
        elif token.is_glyph:
            cur += 1
    if columns or cur:
        columns.append(cur)
        pages.append(columns)
    return pages


def page_waits(raw: bytes) -> list[int]:
    """The frame countdown each page break carries — the voice timing a page is fixed to."""
    return [t.param for t in iter_tokens(raw) if t.word == PAGE_WORD and t.param is not None]


# --- the heuristic text scan (`research/boku-bin.md` § "Where the text is") --------------

GLYPH_SCAN_MAX = 0x4FF
"""The scan's glyph-id ceiling. Above it the run is cut, which is why it misses sites."""
SCAN_MIN_GLYPHS = 3
_END_WORD_RE = re.compile(re.escape(END_WORD.to_bytes(2, "little")))


def scan_text(boku: bytes) -> list[tuple[int, int]]:
    """`(start, end)` of every candidate line: a heuristic, kept only as a cross-check.

    At least `SCAN_MIN_GLYPHS` glyph ids in `1..GLYPH_SCAN_MAX`, `0x8001` and
    `0x8002 <param>` allowed inside, ended by `0x8000`, 2-aligned. The structural walk
    above is the real enumeration; this one exists so the two can be reconciled.
    """
    lines = []
    last_end = 0
    for m in _END_WORD_RE.finditer(boku):
        t = m.start()
        if t & 1:
            continue
        p = t
        glyphs = 0
        while p - 2 >= last_end:
            (v,) = struct.unpack_from("<H", boku, p - 2)
            if 1 <= v <= GLYPH_SCAN_MAX:
                glyphs += 1
            elif v in (NEWLINE_WORD, PAGE_WORD):
                pass
            elif p - 4 >= last_end and boku[p - 4 : p - 2] == PAGE_WORD.to_bytes(2, "little"):
                pass  # the parameter of a page break
            else:
                break
            p -= 2
        if glyphs >= SCAN_MIN_GLYPHS:
            lines.append((p, t + 2))
            last_end = t + 2
    return lines


KANA_IDS = range(0x72, 0x117)
"""Glyph ids 114 to 278: hiragana and katakana. A run with none is not Japanese text."""


def reconcile(archive: Archive, result: Walk) -> Counter[str]:
    """Explain the heuristic scan with the structural walk, in both directions.

    `research/text-format.md` § Reconciliation is this table. Two categories must stay
    empty: a scan hit that is neither structural nor demonstrable noise, and a structural
    site the scan could not see for a reason the scan itself explains.
    """
    out: Counter[str] = Counter()
    boku_sites = sorted((s for s in result.sites if s.file == "BOKU"), key=lambda s: s.absolute)
    ends = {s.absolute + s.size: s for s in boku_sites}
    hits = scan_text(archive.boku)
    seen: set[int] = set()
    for start, end in hits:
        site = ends.get(end)
        if site is not None:
            seen.add(site.absolute)
            if start == site.absolute:
                out["same END, exact"] += 1
            elif start > site.absolute:
                out["same END, scan started late"] += 1
            else:
                out["same END, scan overran backwards"] += 1
            continue
        if _inside_a_tim(archive, start):
            out["not structural, inside a TIM"] += 1
            continue
        glyphs = [w for w in words_of(archive.boku[start:end]) if w < 0x8000]
        kana = sum(1 for w in glyphs if w in KANA_IDS) / len(glyphs)
        if kana < 0.3 or len(glyphs) <= 3:
            out["not structural, judged noise"] += 1
        else:
            out["UNEXPLAINED scan hit"] += 1
    covered = [(a, b) for a, b in hits]
    for site in boku_sites:
        if site.absolute in seen:
            continue
        ws = words_of(result.raw(archive, site))
        if ws[-1] != END_WORD:
            out["missed: no END word (select or line list)"] += 1
            continue
        visible = 0
        p = len(ws) - 1
        while p > 0:
            v = ws[p - 1]
            if 1 <= v <= GLYPH_SCAN_MAX:
                visible += 1
            elif v in (NEWLINE_WORD, PAGE_WORD) or (p >= 2 and ws[p - 2] == PAGE_WORD):
                pass
            else:
                break
            p -= 1
        if visible < 3:
            out["missed: fewer than 3 scan-visible glyphs"] += 1
        elif any(a < site.absolute + site.size <= b for a, b in covered):
            out["missed: an overrunning hit consumed it"] += 1
        else:
            out["UNEXPLAINED structural site"] += 1
    return out


def _inside_a_tim(archive: Archive, offset: int) -> bool:
    """Whether a scan hit falls inside a TIM's pixel data, which is where the noise is."""
    member = archive.owner(offset)
    if member is None:
        return False
    b = archive.blob(member)
    rel = offset - member.offset
    for _ in range(4):
        pack = parse_pack(b)
        if not pack:
            break
        hit = next(((o, s) for o, s in pack.entries if o <= rel < o + s), None)
        if hit is None:
            break
        b = b[hit[0] : hit[0] + hit[1]]
        rel -= hit[0]
    for o in range(0, min(rel + 1, len(b)), 4):
        n = tim_length(b, o)
        if n and o <= rel < o + n:
            return True
    return False
