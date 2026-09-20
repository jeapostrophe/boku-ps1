"""The extractor against the real dump: the four gates `PIPE-01` has to pass.

1. **The port reproduces the tracked research tables byte for byte.** Those five TSVs were
   written by independent scratch code while the formats were being decoded
   (`work/rec01`, `rec03`, `rec05`, `rec06`). Two implementations of the same reading
   agreeing over 12,000 rows is evidence neither is inventing anything.
2. **Every extracted line re-encodes to its original bytes** through the glyph table. That
   pins the encoder `PIPE-03` will reinsert with: a decode that loses an id, or spells one
   the sheet draws twice, fails here rather than in a patched image.
3. **The ids partition the disc.** Every id unique, every physical site in exactly one
   logical line, and the counts the research notes quote — read *out of the notes*, not
   retyped here, so a note and the code cannot drift together.
4. **The self-checks the research scripts ran stay gates**: the archive tiles exactly, the
   heuristic scan and the structural walk explain each other in both directions, and no
   logical line has copies that differ in bytes.

Every test here skips without an import (`conftest.py`).
"""

from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from boku import REPO_ROOT
from boku.archive import (
    EV_DIR_INDEX,
    MAP_DIR_INDEX,
    SUB_ARCHIVES,
    Archive,
    build_members,
    parse_pack,
)
from boku.arrays import read_code_labels, read_save_title, walk_all
from boku.events import Block, EventWorld, map_block_table
from boku.extract import INDEX_NAME, build, write
from boku.glyphs import GlyphTable
from boku.research import (
    DATA_DIR,
    JPSXDEC_IDX,
    MEMBERS_TSV_NAME,
    TSV_NAMES,
    ResearchRefused,
    write_all,
    write_members_tsv,
)
from boku.sites import glyph_count, reconcile

RESEARCH = REPO_ROOT / "research"


def quoted_numbers(note: str, pattern: str) -> tuple[int, ...]:
    """Read a sentence of a research note and return the numbers it quotes.

    The notes are the source of truth for what the disc holds; copying their numbers into
    this file would make the gate measure the typing instead.
    """
    text = (RESEARCH / note).read_text(encoding="utf-8")
    match = re.search(pattern, text)
    assert match is not None, f"{note} no longer holds the sentence {pattern!r}"
    return tuple(int(g.replace(",", "")) for g in match.groups())


@pytest.fixture(scope="session")
def extracted(archive: Archive, event_world: EventWorld, walk_reader):
    return build(archive, world=event_world, result=walk_reader)


# --- gate 1: the tracked research tables ---------------------------------------------------


def test_the_port_regenerates_every_tracked_research_table_byte_for_byte(
    archive: Archive, event_world: EventWorld, tmp_path: Path
):
    """Four of the five tables need nothing but the import, so four of them always run.

    The member map alone needs psyouloveme's jPSXdec index, which lives under the
    gitignored `reference/`. Skipping the whole gate when it is absent — which is a
    contributor's first run — left this test covering nothing at all.
    """
    expected = [n for n in TSV_NAMES if n != MEMBERS_TSV_NAME or JPSXDEC_IDX.is_file()]
    written = write_all(archive, tmp_path, world=event_world)
    assert [p.name for p in written] == expected
    assert len(written) >= 4, "the four tables that need no reference/ always regenerate"
    for path in written:
        tracked = DATA_DIR / path.name
        assert path.read_bytes() == tracked.read_bytes(), (
            f"{path.name} differs from the tracked copy; the port and "
            f"work/{'rec01' if 'members' in path.name else 'rec0x'} disagree"
        )


def test_the_member_map_is_not_written_at_all_without_the_jpsxdec_index(
    archive: Archive, tmp_path: Path
):
    """It used to be written with `jpsxdec_tims` zeroed in every row, over the tracked copy."""
    with pytest.raises(ResearchRefused, match="jpsxdec_tims"):
        write_members_tsv(archive, tmp_path / MEMBERS_TSV_NAME, tmp_path / "absent.idx")
    assert not (tmp_path / MEMBERS_TSV_NAME).exists()


# --- gate 2: the decode/encode round trip ---------------------------------------------------


def test_every_site_on_the_disc_re_encodes_to_its_own_bytes(archive: Archive, walk_reader):
    """The property `PIPE-03`'s encoder rests on, over every site, not a sample."""
    table = GlyphTable.load()
    assert len(walk_reader.sites) > 6000, "a walk this small would make the sweep vacuous"
    for site in walk_reader.sites:
        raw = walk_reader.raw(archive, site)
        assert table.encode(table.decode(raw)) == raw, site.line_id


# --- gate 3: the ids partition the disc --------------------------------------------------------


def test_the_research_walk_matches_the_counts_the_note_quotes(archive: Archive, walk_rec03):
    sites, logical, events, arrays, distinct, glyphs, physical = quoted_numbers(
        "text-format.md",
        r"\*\*([\d,]+) physical sites = ([\d,]+) logical lines\*\* \(([\d,]+) event lines \+\s+"
        r"([\d,]+) array lines\),\s+([\d,]+) distinct byte strings, ([\d,]+) glyphs in "
        r"logical lines \(([\d,]+) physical\)",
    )
    result = walk_rec03
    assert len(result.sites) == sites
    assert len(result.by_line) == logical
    assert sum(1 for k in result.by_line if k.startswith("E")) == events
    assert sum(1 for k in result.by_line if not k.startswith("E")) == arrays
    assert sum(glyph_count(result.raw(archive, s[0])) for s in result.by_line.values()) == glyphs
    assert sum(glyph_count(result.raw(archive, s)) for s in result.sites) == physical
    # The note quotes this one too, and the gate used to parse it and drop it on the floor.
    assert len({result.raw(archive, s[0]) for s in result.by_line.values()}) == distinct


def test_every_id_is_unique_and_every_site_belongs_to_exactly_one_of_them(extracted):
    result = extracted.walk
    ids = [line["id"] for line in extracted.lines]
    assert len(ids) == len(set(ids))
    assert sum(len(v) for v in result.by_line.values()) == len(result.sites)
    placed = {(s.file, s.absolute) for s in result.sites}
    assert len(placed) == len(result.sites), "two sites start at one byte"
    assert set(result.by_line) <= set(ids)


def test_the_extracted_partition_is_the_research_one_plus_the_arrays_it_could_not_see(
    archive: Archive, walk_reader, walk_rec03
):
    """`REC-06` split five arrays out of one and found five more with no control word.

    Stated in *bytes*, not in counts, so a third partition that happened to have the right
    totals could not pass. The two walks must cover the same bytes except that the refined
    one gains the five raw arrays and drops the alignment pad words that sat between the
    arrays `REC-03` had merged into one -- and those dropped bytes must be zero, which is
    what makes them pad rather than text somebody lost.
    """

    def covered(sites) -> set[tuple[str, int]]:
        return {(s.file, b) for s in sites for b in range(s.absolute, s.absolute + s.size)}

    reader = walk_reader
    rec03 = walk_rec03
    raw_arrays = [w for w in walk_all(archive) if w.array.shape == "R"]
    assert len(raw_arrays) == 5, "the five arrays with no control word in them"
    assert len(reader.sites) == len(rec03.sites) + sum(len(w.strings) for w in raw_arrays)

    refined = covered(reader.sites)
    earlier = covered(rec03.sites)
    raw_bytes = covered(s for s in reader.sites if s.kind == "ARR-R")
    assert raw_bytes <= refined and not raw_bytes & earlier
    dropped = earlier - refined
    assert refined == (earlier - dropped) | raw_bytes
    assert len(dropped) == 4, "two alignment pad words, one before each of two arrays"
    for file_tag, offset in sorted(dropped):
        source = archive.exe if file_tag == "EXE" else archive.boku
        assert source[offset] == 0, (file_tag, hex(offset))


# --- gate 4: the research scripts' self-checks, as tests ------------------------------------------


def test_the_archive_tiles_exactly_as_the_note_measured(archive: Archive):
    covered, total = quoted_numbers("boku-bin.md", r"top level covers ([\d,]+) of ([\d,]+) sectors")
    (members,) = quoted_numbers(
        "boku-bin.md", r"`data/boku-bin-members\.tsv`: ([\d,]+) leaf members"
    )
    _built, problems = build_members(archive.exe, archive.boku)
    assert problems == []
    assert len(archive.members) == members
    assert sum(m.sectors for m in archive.members) == covered == total
    assert total == len(archive.boku) // 2048


def test_no_logical_line_has_copies_that_differ_in_bytes(archive: Archive, extracted):
    """The invariant the whole id scheme rests on: one id, one set of bytes."""
    assert extracted.walk.conflicts(archive) == []
    repeated = [k for k, v in extracted.walk.by_line.items() if len(v) > 1]
    assert len(repeated) > 500, "with nothing duplicated this gate would prove nothing"


def test_the_heuristic_scan_and_the_structural_walk_explain_each_other(
    archive: Archive, walk_rec03
):
    """`research/text-format.md` § Reconciliation, in both directions, with nothing left over."""
    table = reconcile(archive, walk_rec03)
    assert table["UNEXPLAINED scan hit"] == 0
    assert table["UNEXPLAINED structural site"] == 0
    assert table["same END, exact"] > 1000, "a reconciliation that matched nothing is vacuous"


def test_every_event_decodes_with_no_desync(event_world: EventWorld):
    """Every event walked by the opcode size table, every jump landing on an instruction."""
    (events,) = quoted_numbers("event-scripts.md", r"\* ([\d,]+) events, every one with bytecode")
    assert len(event_world.scenes) == events
    assert all(sc.ins for sc in event_world.scenes.values())
    assert all(sc.ins[max(sc.ins)].name == "END" for sc in event_world.scenes.values())


def test_the_speaker_label_and_the_actor_slot_disagree_as_often_as_the_note_measured(
    event_world: EventWorld, extracted
):
    """And the list is built once: reading a speaker used to *append* to it every time.

    The extract asks for a speaker once per line, the scene document once per node and
    `--research-tsv` once more, so the count doubled and trebled with the number of
    readers — which is how nothing could ever be said about it.
    """
    lines, voiced = quoted_numbers(
        "event-scripts.md", r"Label and slot disagree in ([\d,]+) of ([\d,]+) voiced lines"
    )
    assert voiced > 1000, "a note quoting a handful of voiced lines would make this vacuous"
    before = extracted.counts["speaker_mismatches"]
    assert before == lines
    for sc in event_world.scenes.values():
        for p in sc.play_order():
            event_world.speaker(sc, p)
    assert sum(len(sc.mismatches) for sc in event_world.scenes.values()) == before


# --- what the extract writes ---------------------------------------------------------------------


# --- every container on the disc parses back to its own bytes -------------------------------


def test_every_container_on_the_disc_re_serialises_to_the_bytes_it_was_parsed_from(
    archive: Archive,
):
    """`PIPE-03` rewrites these tables when a translation grows, so the reading must be
    lossless *before* anything is asked to grow.

    Offsets are recomputed from the parsed parts rather than replayed, so this says the
    chains hold as well as that no byte is dropped: a `.SEC` record's trailing `u16` and
    name padding, a pack's alignment gaps and tail, and an event block's entry order.
    """
    counts: Counter[str] = Counter()

    for container, (sec_name, parse) in sorted(SUB_ARCHIVES.items()):
        blob = archive.blob(archive.member(sec_name))
        assert parse(blob).serialise() == blob, sec_name
        counts["sec"] += 1
        assert parse(blob).records, container

    def packs(blob: bytes, where: str, depth: int = 0) -> None:
        pack = parse_pack(blob)
        if pack is None or depth >= 6:
            return
        assert pack.serialise() == blob, where
        counts["pack"] += 1
        for i, child in enumerate(pack.children):
            if child:
                packs(child, f"{where}/{i}", depth + 1)

    for member in archive.members:
        packs(archive.blob(member), member.short_name)

    for member in archive.members:
        if member.dir_index == MAP_DIR_INDEX:
            base, table = map_block_table(archive, member)
            child1 = archive.blob(member)[base : base + len(table.serialise())]
            assert table.serialise() == child1, member.short_name
            counts["child1"] += 1
            for ident, data in table.blocks:
                assert Block(data).serialise() == data, (member.short_name, ident)
                counts["block"] += 1
        elif member.dir_index == EV_DIR_INDEX:  # one bare block each
            blob = archive.blob(member)
            assert Block(blob).serialise() == blob, member.short_name
            counts["block"] += 1

    assert counts["sec"] == 4
    assert counts["pack"] > 500, counts
    assert counts["child1"] > 100, counts
    assert counts["block"] > 2000, counts


def test_replacing_a_message_keeps_every_other_byte_and_moves_only_the_offsets_after_it(
    archive: Archive,
):
    """The operation the reinserter is built on, over a real block from the disc."""
    member = next(m for m in archive.members if m.dir_index == MAP_DIR_INDEX)
    _base, table = map_block_table(archive, member)
    ident, data = next((i, d) for i, d in table.blocks if Block(d).message_count)
    block = Block(data)
    index = next(i for i in range(block.message_count) if block.message_text(i))
    entry = 4 + 2 * index

    assert block.replace_entry(entry, block.entries[entry]).serialise() == data, ident

    # Six more bytes of text is eight more bytes of entry: an entry is 4-aligned, and it
    # is the *padded* difference every later offset moves by.
    grown = block.replace_entry(entry, block.entries[entry] + bytes(6))
    assert grown.n == block.n
    assert grown.offsets[:entry] == block.offsets[:entry]
    for i in range(entry + 1, block.n):
        moved = block.offsets[i] + 8 if block.offsets[i] else 0
        assert grown.offsets[i] == moved, i
    for i in range(block.n):
        if i != entry:
            assert grown.entries[i] == block.entries[i], i
    assert grown.entries[entry] == block.entries[entry] + bytes(8)
    assert len(grown.serialise()) == len(data) + 8


def test_the_extract_writes_only_its_own_directory_and_reads_only_the_import(
    archive: Archive, extracted, tmp_path: Path
):
    script = tmp_path / "script"
    index = write(extracted, script)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["script"]
    assert sorted(p.name for p in script.iterdir()) == [
        "arrays.json",
        "index.json",
        "lines.jsonl",
        "scenes",
    ]
    assert index["counts"]["logical_lines"] == len(extracted.walk.by_line)
    assert len(list((script / "scenes").iterdir())) == len(extracted.world.scenes)
    assert index["glyph_table_sha1"] == extracted.table.source_sha1


def test_the_index_is_renamed_into_place_after_everything_it_indexes(
    extracted, tmp_path: Path, monkeypatch
):
    """`index.json` is the completeness marker, so it may never arrive first.

    The swap used to rename the staged entries in `sorted()` order, which puts
    `index.json` second of four: an interrupt or a full disc between it and `lines.jsonl`
    left `disc/script/` holding a complete-looking index — format, counts, source SHA-1s
    — over an extract that had already deleted the previous one.
    """
    script = tmp_path / "script"
    script.mkdir()
    (script / "stale.json").write_text("{}")
    seen: list[list[str]] = []
    real_rename = Path.rename

    def watched(self: Path, target):
        if self.parent.name == ".building":
            seen.append(sorted(p.name for p in script.iterdir() if p.name != ".building"))
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", watched)
    write(extracted, script)
    assert seen, "nothing was renamed into place"
    for published in seen[:-1]:
        assert INDEX_NAME not in published, published
    assert "stale.json" not in seen[0], "the previous extract is cleared before the swap"
    assert sorted(p.name for p in script.iterdir()) == [
        "arrays.json",
        INDEX_NAME,
        "lines.jsonl",
        "scenes",
    ]


def test_a_line_record_carries_what_a_translator_has_to_respect(archive: Archive, extracted):
    """Every capacity fact checked against a *second* source, never against its own maker.

    `capacity["pages"] == len(layout["pages"])` is the assignment that produced it, and
    three of the four assertions here were that shape; the record could have said
    anything. Pages come from the `{PAGE:` tokens of the decoded text instead, and the
    select's fixed line count from the bit-15 words actually on the disc — which is the
    one cross-check a SELECT has anywhere, since its *extent* is taken from the same
    executable table `select_lines_fixed` is read out of.
    """
    lines = {line["id"]: line for line in extracted.lines}
    voiced = next(v for v in lines.values() if v.get("voice") and v["layout"]["page_waits"])
    assert voiced["capacity"]["pages_fixed_by_voice"] is True
    assert voiced["capacity"]["pages"] == voiced["text"].count("{PAGE:") + 1
    assert voiced["capacity"]["pages"] > 1, "a one-page line would make the count vacuous"
    assert voiced["capacity"]["bytes"] == len(extracted.table.encode(voiced["text"]))
    assert voiced["speaker"]["label"]
    assert voiced["voice"]["clip"]

    select = next(v for v in lines.values() if v["kind"] == "SELECT")
    site = next(s for s in extracted.walk.by_line[select["id"]])
    words = struct.unpack_from(f"<{site.size // 2}H", extracted.walk.raw(archive, site))
    assert select["capacity"]["select_lines_fixed"] == sum(1 for w in words if w & 0x8000)


def test_a_scene_names_its_lines_and_every_edge_lands_on_a_node_of_that_scene(extracted):
    from boku.extract import scene_document

    for sc in extracted.world.scenes.values():
        document = scene_document(extracted.world, sc)
        nodes = {n["node"] for n in document["nodes"]} | {"END"}
        # The nodes come from a depth-first walk from the entry; the edges from every
        # instruction the reachability pass reached. Two derivations, so an edge landing
        # on something the play order never lists is a real disagreement.
        for edge in document["edges"]:
            assert edge["from"] in nodes | {"ENTRY"}, (document["event"], edge)
            assert edge["to"] in nodes, (document["event"], edge)


def test_the_lines_of_every_scene_exist_in_lines_jsonl(extracted):
    from boku.extract import scene_document

    known = {line["id"] for line in extracted.lines}
    for sc in extracted.world.scenes.values():
        for line_id in scene_document(extracted.world, sc)["lines"]:
            assert line_id in known, line_id


def test_the_dinner_quiz_maps_every_day_to_a_message_index(extracted):
    from boku.extract import scene_document

    quizzes = [
        scene_document(extracted.world, sc)["dinner_quiz"]
        for sc in extracted.world.scenes.values()
        if extracted.world.dinner_quiz(sc)
    ]
    assert quizzes, "PROG 15/16 events exist on this disc"
    quiz = next(q for q in quizzes if "quiz" in q)
    days = [row["day"] for row in quiz["quiz"]]
    assert days == list(range(1, 32))
    assert next(r["message"] for r in quiz["quiz"] if r["day"] == 15) == 0
    assert all(0 <= r["answer"] <= 2 for r in quiz["quiz"])


_ID_IN_NOTE = "0x([0-9A-Fa-f]+)`?(?:\\s*\u00d7(\\d+))?"
"""A glyph id in the note's table, with the `xN` site count the multiplication sign marks."""


def _note_code_label_ids() -> dict[str, Counter[int]]:
    """The glyph ids `research/text-outside-events.md`'s label table quotes, per function.

    Parsed, never retyped: the note is the source of truth for what these functions draw,
    and a copy of its numbers in this file would pass exactly when the two drifted
    together. A cell reading ``0x5B0`` x4 means that id at four instruction sites.
    """
    text = (RESEARCH / "text-outside-events.md").read_text(encoding="utf-8")
    out: dict[str, Counter[int]] = {}
    for row in re.findall(r"^\s*\|\s*`(\w+_draw)`[^|]*\|([^|]*)\|", text, re.MULTILINE):
        function, cell = row
        ids: Counter[int] = Counter()
        for value, repeat in re.findall(_ID_IN_NOTE, cell):
            ids[int(value, 16)] += int(repeat) if repeat else 1
        if ids:
            out[function] = ids
    return out


def test_every_code_label_holds_exactly_the_glyph_ids_the_note_traced(archive: Archive):
    """The gate on `read_code_labels`, against the note's own table.

    Two of the six labels used to come out with a phantom character: a literal left in
    `a0` by an instruction that was not a glyph id: `extras_numbers_draw` picked up
    glyph 1 from an `addiu a0, zero, 1` fifty-eight instructions earlier, and
    `file_rows_draw` picked up glyph 74, the argument of its call to `save_date_draw`.
    Both would have been handed to a translator as part of the label.
    """
    expected = _note_code_label_ids()
    assert len(expected) == 6, f"the note's label table lists {sorted(expected)}"
    labels = {label.purpose.split(":")[0]: label for label in read_code_labels(archive)}
    assert set(labels) == set(expected)
    for function, ids in expected.items():
        label = labels[function]
        assert set(label.glyph_ids) == set(ids), (
            function,
            sorted(set(label.glyph_ids)),
            sorted(ids),
        )
        # Where the note counts the instruction sites, they are counted here too.
        for glyph, count in ids.items():
            if count > 1:
                assert sum(1 for _ram, g in label.sites if g == glyph) == count, function
        assert all(0 < g <= 0x5FF for g in label.glyph_ids), function


def test_the_code_labels_find_every_glyph_the_table_says_only_code_uses(archive: Archive):
    """`REC-04` marked four ids `used=code` from the other end; the scan has to reach them."""
    import csv

    with (RESEARCH / "data/glyph-table.tsv").open(encoding="utf-8", newline="") as handle:
        only_code = {
            int(r["index"]) for r in csv.DictReader(handle, delimiter="\t") if r["used"] == "code"
        }
    assert only_code, "a table with no code-only glyph would make this gate vacuous"
    found = {i for label in read_code_labels(archive) for i in label.glyph_ids}
    assert only_code <= found, sorted(only_code - found)


def test_the_save_title_is_read_out_of_its_two_pointer_tables(archive: Archive):
    title = read_save_title(archive)
    assert len(title.digits) == 10
    assert len(title.parts) == 3
    assert all(len(d) == 1 for d in title.digits), "the BIOS draws full-width digits"
    assert len(title.part_offsets) == len(title.parts)


# --- determinism ----------------------------------------------------------------------------------


def test_two_runs_under_different_hash_seeds_write_identical_bytes(disc_dir: Path, tmp_path: Path):
    """An earlier scratch script was not deterministic; the merge of branch conditions is greedy
    and its fixed point depends on iteration order, so everything it iterates is sorted."""
    runs = []
    for seed in ("0", "1"):
        root = tmp_path / f"seed{seed}"
        root.mkdir()
        (root / "files").symlink_to((disc_dir / "files").resolve())
        env = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run(
            [sys.executable, "-m", "boku", "extract", "--disc", str(root)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        runs.append(root / "script")
    for name in ("lines.jsonl", "arrays.json"):
        assert (runs[0] / name).read_bytes() == (runs[1] / name).read_bytes(), name
    scenes = sorted(p.name for p in (runs[0] / "scenes").iterdir())
    assert scenes == sorted(p.name for p in (runs[1] / "scenes").iterdir())
    for name in scenes:
        assert (runs[0] / "scenes" / name).read_bytes() == (runs[1] / "scenes" / name).read_bytes()
    first = json.loads((runs[0] / "index.json").read_text())
    assert first["counts"] == json.loads((runs[1] / "index.json").read_text())["counts"]
