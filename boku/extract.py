"""`boku extract` — the whole Japanese script, decoded out of your own import.

It reads only `disc/` and writes only `disc/script/`, both gitignored: the repo ships none
of the game (README principle 2), and a translation is keyed by **line id**, never by the
Japanese (principle 3). This is the step that makes those ids exist.

What comes out, designed for two readers — the agents that translate (`TRN-02`) and the
scene reader that displays the result (`TRN-06`):

* `lines.jsonl` — one record per **logical line**: its id, what kind it is, who says it,
  the decoded Japanese with control words as tokens, the page and column layout, every
  physical site it occupies, and the capacity facts a translator has to respect.
* `scenes/E<id>.json` — one per event: where and when it fires, its cast, its flow graph
  with symbolic branch conditions, and its hand-overs to other events.
* `arrays.json` — the code-file arrays, the functions that draw a label from immediate
  glyph ids, and the Shift-JIS save title.
* `index.json` — counts, the SHA-1s of everything it read, the tool version and the hash
  of the glyph table it was decoded with.

**The zero-conflict invariant is asserted, not assumed.** An event block is copied into
every map variant where it can fire, and every copy of a given (event, message index) must
be byte-identical — `research/text-format.md` § "The duplication model" counts them. The
extract fails, naming the id, if a dump ever disagrees; without that a reinserter could
write one copy of a line and leave another.

Output is deterministic: the same import gives byte-identical files across runs and across
`PYTHONHASHSEED` values. Every set is sorted before it is written.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boku import __version__
from boku.archive import Archive, ArchiveError
from boku.arrays import (
    SAVE_TITLE_BYTES,
    ArrayError,
    describe_label,
    read_code_labels,
    read_save_title,
    walk_all,
)
from boku.events import (
    NATIVE,
    OP_MAP,
    OP_MOVIE,
    OP_PROG,
    OP_SELECT,
    OP_XAMSG,
    EventError,
    EventWorld,
    Scene,
    fmt_cond,
    s16,
)
from boku.glyphs import GlyphTable, TextError
from boku.research import JPSXDEC_IDX, ResearchRefused, missing_tables, write_all
from boku.sites import Site, SiteError, Walk, glyph_count, load, page_structure, page_waits
from boku.staging import StagingRefused, staged_inside

SCRIPT_DIR_NAME = "script"
"""`disc/script/` — written by this step, read by everything downstream, never committed."""

FORMAT = 1
"""Bumped when a consumer would have to change. `index.json` carries it."""


class ExtractRefused(Exception):
    """The extract will not proceed, or the disc contradicts the format notes."""


# --- one logical line ---------------------------------------------------------------------


def _sort_key(line_id: str) -> tuple:
    """Order ids so `E0171.2` comes before `E0171.10` and arrays group by their prefix."""
    if line_id.startswith("E") and "." in line_id:
        head, tail = line_id.split(".", 1)
        if head[1:].isdigit() and tail.isdigit():
            return (0, int(head[1:]), int(tail))
    prefix, _, tail = line_id.partition(".")
    return (1, prefix, int(tail) if tail.isdigit() else -1)


def _layout(raw: bytes) -> dict[str, Any]:
    """Pages, columns and the page timings — the shape the dialogue box has to hold."""
    pages = page_structure(raw)
    waits = page_waits(raw)
    return {
        "pages": pages,
        "page_waits": waits,
        "columns": sum(len(p) for p in pages),
        "longest_column": max((c for p in pages for c in p), default=0),
    }


def _site_record(archive: Archive, site: Site) -> dict[str, Any]:
    member = archive.member(site.member) if site.file == "BOKU" else None
    return {
        "member": site.member,
        "container": site.container,
        "table": site.table,
        "offset": f"0x{site.offset:x}",
        "size": site.size,
        "slack": site.slack,
        "member_sector_slack": member.sector_slack if member else None,
    }


def _kind_of(site_kind: str) -> tuple[str, bool, tuple[int, int] | None]:
    """`(kind, voiced, select shape)` from the walk's site kind — one place decides this."""
    voiced = site_kind.endswith("+XA")
    head = site_kind[: -3 if voiced else None]
    if head.startswith("SEL"):
        select_type, variant = head[3:].split(".")
        return "SELECT", voiced, (int(select_type), int(variant))
    if head.startswith("ARR-"):
        return f"array-{head[4:]}", False, None
    return ("XAMSG" if voiced else "MSG"), voiced, None


@dataclass
class Extract:
    """Everything the extractor derived, before it is written out."""

    archive: Archive
    world: EventWorld
    table: GlyphTable
    walk: Walk
    arrays: list
    code_labels: list
    save_title: Any
    lines: list[dict[str, Any]]
    counts: dict[str, int]


def build(
    archive: Archive,
    table: GlyphTable | None = None,
    world: EventWorld | None = None,
    result: Walk | None = None,
) -> Extract:
    """Decode the whole script. Raises rather than writing a half-true extract.

    `world` and `result` are parameters so a caller that has already decoded the disc —
    the test suite's session fixtures — hands them in rather than walking it again.
    """
    table = table if table is not None else GlyphTable.load()
    _archive, result = load(archive=archive, result=result)
    world = world if world is not None else EventWorld(archive, table)

    walked_arrays = walk_all(archive)
    by_prefix = {w.array.line_id_prefix: w for w in walked_arrays}
    lines: list[dict[str, Any]] = []
    for line_id in sorted(result.by_line, key=_sort_key):
        sites = result.by_line[line_id]
        raw = result.raw(archive, sites[0])
        record = _base_record(archive, table, line_id, sites, raw)
        if line_id.startswith("E") and sites[0].container in ("c1", "ev"):
            _fill_event_fields(world, record, line_id)
        elif sites[0].container.startswith("array@"):
            _fill_array_fields(by_prefix, record, line_id)
        elif sites[0].container == "exe-block":
            record["capacity"]["note"] = (
                "an event block compiled into the executable, chosen by 0x80019DEC for "
                "system events; the build moves the whole block when a message grows "
                "(boku.array_relocate), so the English is not held to these bytes"
            )
        lines.append(record)

    code_labels = read_code_labels(archive)
    for label in code_labels:
        lines.append(
            {
                "id": label.line_id,
                "kind": "code-label",
                "text": describe_label(label, table),
                "glyphs": len(label.glyph_ids),
                "glyph_ids": list(label.glyph_ids),
                "runs": [list(run) for run in label.runs],
                "function": f"0x{label.function:08X}",
                "purpose": label.purpose,
                "sites": [],
                "capacity": {
                    "bytes": None,
                    "note": "assembled from instruction immediates; translating it is a "
                    "code patch, not a data rewrite",
                },
            }
        )
    save_title = title = read_save_title(archive)
    lines.append(
        {
            "id": title.line_id,
            "kind": "sjis-title",
            "text": "".join(title.parts),
            "glyphs": 0,
            "parts": list(title.parts),
            "digits": list(title.digits),
            "part_offsets": [f"0x{o:x}" for o in title.part_offsets],
            "sites": [],
            "capacity": {
                "bytes": SAVE_TITLE_BYTES,
                "note": "Shift-JIS in the memory card's SC header; the BIOS draws "
                "full-width characters, so at most 32 of them",
            },
        }
    )

    counts = _counts(archive, result, world, walked_arrays, lines)
    return Extract(
        archive, world, table, result, walked_arrays, code_labels, save_title, lines, counts
    )


def _base_record(
    archive: Archive, table: GlyphTable, line_id: str, sites: list[Site], raw: bytes
) -> dict[str, Any]:
    kind, voiced, select = _kind_of(sites[0].kind)
    placed = sorted(sites, key=lambda s: (s.member, s.offset))
    record: dict[str, Any] = {
        "id": line_id,
        "kind": kind,
        "text": table.decode(raw),
        "glyphs": glyph_count(raw),
        "voiced": voiced,
        "layout": _layout(raw),
        "sites": [_site_record(archive, s) for s in placed],
        "capacity": {
            "bytes": sites[0].size,
            "copies": len(sites),
            "min_member_sector_slack": min(
                (archive.member(s.member).sector_slack for s in sites if s.file == "BOKU"),
                default=None,
            ),
        },
    }
    if select is not None:
        record["select"] = {"type": select[0], "variant": select[1]}
    return record


def _fill_event_fields(world: EventWorld, record: dict[str, Any], line_id: str) -> None:
    # Not `line_id[1:5]`: that silently truncates an event id of more than four digits.
    event_id, index = (int(part) for part in line_id[1:].split(".", 1))
    sc = world.scenes[event_id]
    record["event"] = sc.event.name
    record["index"] = index
    naming = sc.named.get(index, [])
    ordered = [p for p in sc.play_order() if p in naming] or sorted(naming)
    if ordered:
        label, slot = world.speaker(sc, ordered[0])
    else:
        # Opened by native code with a day-computed index (the dinner quiz); no opcode
        # names it, so the inline label is all there is.
        label, slot = world.label_of(sc.messages[index][1]), None
    record["speaker"] = {
        "label": label,
        "slot": slot,
        "slot_name": world.slot_name(slot),
        "inline_label": world.label_of(sc.messages[index][1]),
    }
    record["nodes"] = [sc.node_id(p) for p in ordered]
    key = world.voice_key(sc.messages[index][0])
    if key is not None:
        clip = next((sc.ins[p].clip for p in ordered if sc.ins[p].op == OP_XAMSG), None)
        record["voice"] = {"clip": clip, **key}
    if record["kind"] == "SELECT":
        select_type, variant = record["select"]["type"], record["select"]["variant"]
        lines, prompt = world.select_shape(select_type, variant)
        record["select"].update({"lines": lines, "prompt_lines": prompt})
        record["capacity"]["select_lines_fixed"] = lines
    # A page break in a voiced message carries the frame countdown that turns the page by
    # itself, so the page count is fixed by the recording and a translation may not add or
    # remove one (`research/text-format.md`).
    record["capacity"]["pages"] = len(record["layout"]["pages"])
    record["capacity"]["pages_fixed_by_voice"] = bool(record["layout"]["page_waits"])


def _fill_array_fields(arrays: dict, record: dict[str, Any], line_id: str) -> None:
    prefix = line_id.split(".")[0]
    walked = arrays[prefix]
    record["array"] = prefix
    record["index"] = int(line_id.split(".")[1]) if "." in line_id else 0
    record["reader"] = walked.array.reader
    record["purpose"] = walked.array.purpose
    record["capacity"]["note"] = (
        "an array item is followed by the next symbol: growth means relocating the array "
        "and patching its lui/addiu pairs (research/text-format.md)"
    )
    if walked.array.shape == "R":
        record["capacity"]["cells_fixed"] = walked.array.spec[1]


def _counts(
    archive: Archive,
    result: Walk,
    world: EventWorld,
    walked_arrays: list,
    lines: list[dict[str, Any]],
) -> dict[str, int]:
    by_kind = Counter(line["kind"] for line in lines)
    return {
        "physical_sites": len(result.sites),
        "logical_lines": len(result.by_line),
        "glyphs_in_logical_lines": sum(
            glyph_count(result.raw(archive, sites[0])) for sites in result.by_line.values()
        ),
        "glyphs_physical": sum(glyph_count(result.raw(archive, s)) for s in result.sites),
        "records": len(lines),
        "events": len(world.events),
        "arrays": len(walked_arrays),
        "speaker_mismatches": sum(len(sc.mismatches) for sc in world.scenes.values()),
        **{f"kind_{k}": v for k, v in sorted(by_kind.items())},
    }


# --- scenes ---------------------------------------------------------------------------------


def scene_document(world: EventWorld, sc: Scene) -> dict[str, Any]:
    """One event as `TRN-02` needs it: where, when, who, and the graph in play order."""
    event = sc.event
    maps = sorted({m[2:8] for m in event.members if m.startswith("M_")})
    day, meal = world.when(sc)
    order = sc.play_order() if sc.ins else []
    nodes = []
    for p in order:
        i = sc.ins[p]
        label, slot = world.speaker(sc, p)
        node: dict[str, Any] = {
            "node": sc.node_id(p),
            "pc": p,
            "opcode": i.name,
            "speaker": label,
        }
        if i.op in (OP_MAP, OP_MOVIE):
            node["hands_over_to"] = sc.chain_token(i)
        elif i.op == OP_PROG:
            node["native"] = NATIVE[s16(i.b, 2)]
        else:
            node["line"] = f"E{sc.id:04d}.{i.message_index}"
            if slot is not None:
                node["slot"] = slot
            if i.op == OP_SELECT:
                lines, prompt = world.select_shape(i.select_type, i.select_variant)
                node["select"] = {
                    "type": i.select_type,
                    "variant": i.select_variant,
                    "lines": lines,
                    "prompt_lines": prompt,
                    "options": lines - prompt,
                    "cancellable": i.select_cancellable,
                }
        nodes.append(node)
    edges = [
        {"from": "ENTRY", "to": sc.node_id(dst), "condition": condition}
        for dst, condition in sc.entry_edges.items()
    ] + [
        {"from": sc.node_id(src), "to": sc.node_id(dst), "condition": condition}
        for src, dst, condition in sc.edges
        if src in sc.reach
    ]
    document: dict[str, Any] = {
        "event": event.name,
        "id": sc.id,
        "copies": len(event.members),
        "in_ev": any(m.startswith("EV") for m in event.members),
        "when": {
            "day": day,
            "meal_hour": meal,
            "condition": fmt_cond(sc.condition) if sc.condition else None,
        },
        "where": {
            "maps": maps,
            "bases": sorted({m[:3] for m in maps}),
            "time_slots": "".join(sorted({m[3] for m in maps})),
            "triggers": dict(
                sorted(Counter(p.label for p in world.placements.get(sc.id, [])).items())
            ),
        },
        "cast": [{"slot": slot, "model": model} for slot, model in sc.cast],
        "actors": {str(k): sorted(v) for k, v in sorted(sc.slots.items())},
        "lines": [
            f"E{sc.id:04d}.{mi}" for mi in range(sc.message_count) if sc.messages[mi][1] is not None
        ],
        "play_order": [sc.node_id(p) for p in order],
        "nodes": nodes,
        "edges": edges,
        "handovers": [
            {"kind": kind, "map": m, "event": f"E{n:04d}" if n > 0 else None, "reachable": r}
            for kind, m, n, r in sc.chain
        ],
        "speaker_mismatches": [
            {"node": node, "inline_label": label, "slot_name": who}
            for node, label, who in sc.mismatches
        ],
        "conditions_summarised": sc.complex,
    }
    quiz = world.dinner_quiz(sc)
    if quiz is not None:
        document["dinner_quiz"] = quiz
    return document


# --- writing ----------------------------------------------------------------------------------


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


INDEX_NAME = "index.json"
"""The completeness marker. It is written into the staging directory last and renamed
into place last, so a `disc/script/` holding it holds everything its counts describe.
Before that ordering was explicit the swap renamed in `sorted()` order, and an interrupt
between `index.json` and `lines.jsonl` left a complete-looking index over no script."""


def write(extract: Extract, script_dir: Path) -> dict[str, Any]:
    """Write the script directory, building into a staging directory *inside* it first.

    The staging directory is inside `script_dir` rather than beside it because everything
    under `disc/` except `disc/script/` is the contributor's import, which this tool has
    no business writing to (`CLAUDE.md`). A failure before the swap therefore leaves the
    previous extract untouched; a failure during it leaves the run's files with
    `INDEX_NAME` missing, which is exactly "this extract is not complete".
    """
    script_dir = Path(script_dir)
    script_dir.mkdir(parents=True, exist_ok=True)
    index = {
        "format": FORMAT,
        "tool": f"boku {__version__}",
        "sources": _source_hashes(extract.archive),
        "glyph_table_sha1": extract.table.source_sha1,
        "counts": extract.counts,
        "scenes": len(extract.world.scenes),
    }
    with staged_inside(script_dir, suffix="building", marker=INDEX_NAME) as staging:
        (staging / "scenes").mkdir()
        with (staging / "lines.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for line in extract.lines:
                f.write(_dump(line) + "\n")

        for sc in extract.world.scenes.values():
            document = scene_document(extract.world, sc)
            (staging / "scenes" / f"E{sc.id:04d}.json").write_text(
                json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )

        arrays = {
            "arrays": [
                {
                    "id": w.array.line_id_prefix,
                    "file": w.array.file_name,
                    "file_offset": f"0x{w.array.file_offset:X}",
                    "ram_start": f"0x{w.array.ram:08X}",
                    "ram_end": f"0x{w.end:08X}",
                    "shape": w.array.shape,
                    "items": w.items,
                    "drawn_cells": w.drawn_cells,
                    "reader": w.array.reader,
                    "purpose": w.array.purpose,
                    "lines": list(w.line_ids),
                }
                for w in extract.arrays
            ],
            "code_labels": [
                {
                    "id": label.line_id,
                    "function": f"0x{label.function:08X}",
                    "image": label.image,
                    "runs": [list(run) for run in label.runs],
                    "sites": [f"0x{ram:08X}" for ram, _glyph in label.sites],
                    "purpose": label.purpose,
                }
                for label in extract.code_labels
            ],
            "save_title": {
                "id": extract.save_title.line_id,
                "parts": list(extract.save_title.parts),
                "digits": list(extract.save_title.digits),
                "bytes": SAVE_TITLE_BYTES,
            },
        }
        (staging / "arrays.json").write_text(
            json.dumps(arrays, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        (staging / INDEX_NAME).write_text(
            json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return index


def _source_hashes(archive: Archive) -> dict[str, str | None]:
    """SHA-1 of everything the extract was derived from, so a stale one is recognisable."""
    from boku.importer import sha1_of

    image = archive.disc_dir / "image.img"
    return {
        "SCPS_100.88": sha1_of(archive.exe_path),
        "BOKU.BIN": sha1_of(archive.archive_path),
        "image.img": sha1_of(image) if image.is_file() else None,
    }


def format_summary(index: dict[str, Any], script_dir: Path, seconds: float) -> str:
    counts = index["counts"]
    return "\n".join(
        [
            f"wrote {script_dir} in {seconds:.1f}s",
            f"  {counts['logical_lines']} logical lines over {counts['physical_sites']} "
            f"physical sites, {counts['glyphs_in_logical_lines']} glyphs",
            f"  {index['scenes']} scenes, {counts['arrays']} arrays, "
            f"{counts['records']} records in lines.jsonl",
            f"  glyph table {index['glyph_table_sha1'][:12]}",
        ]
    )


def main_extract(disc_dir: Path, research_tsv: Path | None = None) -> int:
    """`boku extract`. Writes `<disc>/script/`, and optionally regenerates the research tables."""
    import time

    started = time.monotonic()
    try:
        archive = Archive(disc_dir)
        extract = build(archive)
        index = write(extract, Path(disc_dir) / SCRIPT_DIR_NAME)
        if research_tsv is not None:
            for path in write_all(archive, research_tsv, world=extract.world):
                print(f"wrote {path}")
            for name in missing_tables():
                print(
                    f"did not write {name}: {JPSXDEC_IDX} is not there, and without it "
                    f"its jpsxdec_tims column would be zero in every row"
                )
    except (
        ArchiveError,
        ExtractRefused,
        SiteError,
        StagingRefused,
        EventError,
        ArrayError,
        TextError,
        ResearchRefused,
        OSError,
    ) as error:
        print(f"boku extract: {error}")
        return 1
    print(format_summary(index, Path(disc_dir) / SCRIPT_DIR_NAME, time.monotonic() - started))
    return 0
