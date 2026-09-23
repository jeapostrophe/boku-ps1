"""A synthetic `disc/script/` store, so the translation lints and the packets have gates
that need no disc.

The shape is `boku.extract`'s -- `index.json`, `lines.jsonl`, `scenes/E*.json`. It is a
*fixture*, not a second implementation of the store: nothing here proves a real
`disc/script/` looks like this, and until something does, `./make.sh lint-translation` and
`./make.sh packet` against a contributor's own import are what shows that it does.
Nothing here is the game's text: every
Japanese cell is drawn from `research/data/glyph-table.tsv` at build time, so a fixture
cannot quietly contain a quoted line, and the one intensifier a test needs comes from
`boku.lint.SOURCE_INTENSIFIERS` rather than being retyped beside it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

from boku.glyphs import GlyphTable

HIRAGANA = ("぀", "ゟ")
"""The block filler cells are taken from, so a fixture is readable as "some Japanese"."""


def filler(table: GlyphTable, cells: int, skip: int = 0) -> str:
    """`cells` characters the sheet draws, from the glyph table itself.

    Derived, never typed: a fixture that quoted the disc would be both a licence problem
    and a test that passes because two copies of one string agree.
    """
    candidates = [
        character
        for character in sorted(table.from_character)
        if HIRAGANA[0] <= character <= HIRAGANA[1]
    ]
    if len(candidates) < skip + 1:
        raise AssertionError("the glyph table draws no hiragana; the fixture cannot be built")
    return candidates[skip % len(candidates)] * cells


def _message_text(pages: list[list[str]], waits: list[int]) -> str:
    """Token text in `GlyphTable.decode`'s own spelling: `{NL}` columns, `{PAGE:p}` pages."""
    out: list[str] = []
    for number, page in enumerate(pages):
        if number:
            out.append(f"{{PAGE:{waits[number - 1]}}}")
        out.append("{NL}".join(page))
    out.append("{END}")
    return "".join(out)


@dataclass
class SynthStore:
    """A store under `root`, built one line and one scene at a time."""

    root: Path
    table: GlyphTable
    lines: list[dict] = field(default_factory=list)
    scenes: list[dict] = field(default_factory=list)

    @classmethod
    def new(cls, root: Path) -> SynthStore:
        return cls(root=Path(root), table=GlyphTable.load())

    # --- lines ---------------------------------------------------------------------------

    def message(
        self,
        line_id: str,
        columns: list[list[int]],
        *,
        voiced: bool,
        speaker: str = "OJI",
        slot: int = 1,
        label: bool = True,
        prefix: str = "",
        marks: tuple[str, str] = ("", ""),
    ) -> dict:
        """One `XAMSG`/`MSG` line. `columns` gives the cell count of each column of each
        page, and the cells themselves come from the glyph table.

        `label` writes the inline `<speaker>「` the Japanese opens a labelled message
        with; `marks` writes a pair of its own (an opener before the first column, a closer
        after the last), which is what `boku.layout.original_marks` reads; `prefix` puts a
        caller's own word (a source intensifier, say) at the head of the first column.
        """
        pages = [
            [filler(self.table, cells, skip=index) for index, cells in enumerate(page)]
            for page in columns
        ]
        pages[0][0] = f"{prefix}{pages[0][0]}"
        if label:
            pages[0][0] = f"{filler(self.table, 2, skip=3)}「{pages[0][0]}"
        opening, closing = marks
        pages[0][0] = f"{opening}{pages[0][0]}"
        pages[-1][-1] = f"{pages[-1][-1]}{closing}"
        waits = [90 + number for number in range(len(pages) - 1)]
        text = _message_text(pages, waits)
        size = len(self.table.encode(text))
        record = {
            "id": line_id,
            "kind": "XAMSG" if voiced else "MSG",
            "text": text,
            "glyphs": sum(len(column) for page in pages for column in page),
            "voiced": voiced,
            "layout": {
                "pages": [[len(column) for column in page] for page in pages],
                "page_waits": waits,
                "columns": sum(len(page) for page in pages),
                "longest_column": max(len(column) for page in pages for column in page),
            },
            "sites": [
                {
                    "member": "M_SYNTH0.BIN",
                    "container": "c1",
                    "table": 0,
                    "offset": "0x100",
                    "size": size,
                    "slack": 0,
                    "member_sector_slack": 2048,
                }
            ],
            "capacity": {
                "bytes": size,
                "copies": 1,
                "min_member_sector_slack": 2048,
                "pages": len(pages),
                "pages_fixed_by_voice": voiced,
            },
            "event": line_id.split(".", 1)[0],
            "index": int(line_id.rsplit(".", 1)[1]),
            "speaker": {
                "label": speaker,
                "slot": slot,
                "slot_name": speaker,
                "inline_label": speaker,
            },
            "nodes": [f"{line_id}@0"],
        }
        if voiced:
            record["voice"] = {
                "clip": "9001_00",
                "start": 0,
                "end": 400,
                "channel": 0,
                "file": 2,
            }
        self.lines.append(record)
        return record

    def select(self, line_id: str, options: int, prompts: int = 0, cells: int = 3) -> dict:
        columns = [filler(self.table, cells, skip=index) for index in range(options + prompts)]
        text = "".join(f"{column}{{NL}}" for column in columns)
        size = len(self.table.encode(text))
        record = {
            "id": line_id,
            "kind": "SELECT",
            "text": text,
            "glyphs": cells * (options + prompts),
            "voiced": False,
            "layout": {
                "pages": [[len(column) for column in columns] + [0]],
                "page_waits": [],
                "columns": len(columns) + 1,
                "longest_column": cells,
            },
            "sites": [
                {
                    "member": "M_SYNTH0.BIN",
                    "container": "c1",
                    "table": 0,
                    "offset": "0x200",
                    "size": size,
                    "slack": 0,
                    "member_sector_slack": 2048,
                }
            ],
            "capacity": {
                "bytes": size,
                "copies": 1,
                "min_member_sector_slack": 2048,
                "select_lines_fixed": options,
                "pages": 1,
                "pages_fixed_by_voice": False,
            },
            "select": {
                "type": 3,
                "variant": 1,
                "lines": options + prompts,
                "prompt_lines": prompts,
            },
            "event": line_id.split(".", 1)[0],
            "index": int(line_id.rsplit(".", 1)[1]),
            "speaker": {
                "label": "SELECT",
                "slot": None,
                "slot_name": None,
                "inline_label": "CONT",
            },
            "nodes": [f"{line_id}@0"],
        }
        self.lines.append(record)
        return record

    def array_item(self, line_id: str, cells: int = 4) -> dict:
        """One code-file array item: cells then a single `{END}`, and no slack at all."""
        text = f"{filler(self.table, cells, skip=5)}{{END}}"
        size = len(self.table.encode(text))
        record = {
            "id": line_id,
            "kind": "array-E",
            "text": text,
            "glyphs": cells,
            "voiced": False,
            "layout": {
                "pages": [[cells]],
                "page_waits": [],
                "columns": 1,
                "longest_column": cells,
            },
            "sites": [
                {
                    "member": "SCPS_100.88",
                    "container": "array@0x1000",
                    "table": 0,
                    "offset": "0x1000",
                    "size": size,
                    "slack": 0,
                    "member_sector_slack": None,
                }
            ],
            "capacity": {
                "bytes": size,
                "copies": 1,
                "min_member_sector_slack": None,
                "note": "an array item is followed by the next symbol",
            },
            "array": line_id.rsplit(".", 1)[0],
            "index": int(line_id.rsplit(".", 1)[1]),
            "reader": "synth_draw 0x80000000",
            "purpose": "a synthetic array item",
        }
        self.lines.append(record)
        return record

    def select_array(
        self, line_id: str, lines: int = 3, cells: int = 3, purpose: str = "a synthetic menu"
    ) -> dict:
        """A code-file select (an **S** array): `lines` rows each ended by `{NL}`, opened by
        `select_open_ptr` and so drawn as a select box. One id, as the extract gives it."""
        columns = [filler(self.table, cells, skip=index) for index in range(lines)]
        record = self.array_item(f"{line_id}.0", cells=cells)
        text = "".join(f"{column}{{NL}}" for column in columns)
        size = len(self.table.encode(text))
        record.update(
            id=line_id,
            kind="array-S",
            text=text,
            glyphs=cells * lines,
            layout={
                "pages": [[cells] * lines + [0]],
                "page_waits": [],
                "columns": lines + 1,
                "longest_column": cells,
            },
            array=line_id,
            index=0,
            purpose=purpose,
        )
        record["sites"][0]["size"] = record["capacity"]["bytes"] = size
        return record

    def code_label(self, line_id: str, cells: int = 4) -> dict:
        """A label assembled from instruction immediates: no text site, no byte size."""
        record = {
            "id": line_id,
            "kind": "code-label",
            "text": filler(self.table, cells, skip=6),
            "glyphs": cells,
            "runs": [list(range(0x100, 0x100 + cells))],
            "function": "0x80000000",
            "purpose": "synth_label_draw: a synthetic label",
            "sites": [],
            "capacity": {"bytes": None, "note": "assembled from instruction immediates"},
        }
        self.lines.append(record)
        return record

    def save_title(self, line_id: str = "title@sjis:188") -> dict:
        """The Shift-JIS save title: no text site; `boku.code_text` places it."""
        record = {
            "id": line_id,
            "kind": "sjis-title",
            "text": "",
            "glyphs": 0,
            "sites": [],
            "capacity": {"bytes": 64, "note": "the SC header's title"},
        }
        self.lines.append(record)
        return record

    # --- scenes --------------------------------------------------------------------------

    def scene(
        self,
        event: str,
        line_ids: list[str],
        *,
        day: int | None = 1,
        voice_only: list[str] | None = None,
        quiz: dict | None = None,
    ) -> dict:
        reached = [*line_ids, *(voice_only or [])]
        nodes = []
        for index, line_id in enumerate(reached):
            record = next((r for r in self.lines if r["id"] == line_id), None)
            nodes.append(
                {
                    "node": f"{line_id}@{index}",
                    "pc": 16 * index,
                    "opcode": "SELECT" if record and "select" in record else "XAMSG",
                    "speaker": (record or {}).get("speaker", {}).get("label", "BOKU"),
                    "line": line_id,
                    "slot": (record or {}).get("speaker", {}).get("slot", 0),
                }
            )
        edges = [{"from": "ENTRY", "to": nodes[0]["node"], "condition": ""}] if nodes else []
        for left, right in pairwise(nodes):
            edges.append({"from": left["node"], "to": right["node"], "condition": ""})
        if nodes:
            edges.append({"from": nodes[-1]["node"], "to": "END", "condition": "lflag>=1"})
        scene = {
            "event": event,
            "id": int(event[1:]),
            "copies": 1,
            "in_ev": False,
            "when": {"day": day, "meal_hour": 18, "condition": "(hour==18)"},
            "where": {
                "maps": ["G02111"],
                "bases": ["G02"],
                "time_slots": "1",
                "triggers": {"auto": 1},
            },
            "cast": [{"slot": 0, "model": 7}, {"slot": 1, "model": 6}],
            "actors": {"0": [7], "1": [6]},
            "lines": list(line_ids),
            "play_order": [node["node"] for node in nodes],
            "nodes": nodes,
            "edges": edges,
            "handovers": [{"kind": "MAP", "map": "G13", "event": None, "reachable": True}],
            "speaker_mismatches": [],
            "conditions_summarised": False,
        }
        if quiz is not None:
            scene["dinner_quiz"] = quiz
        self.scenes.append(scene)
        return scene

    # --- writing it out --------------------------------------------------------------------

    def write(self) -> Path:
        script = self.root / "script"
        (script / "scenes").mkdir(parents=True, exist_ok=True)
        (script / "index.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "tool": "tests.synth_script",
                    "sources": {},
                    "glyph_table_sha1": self.table.source_sha1,
                    "counts": {"logical_lines": len(self.lines), "events": len(self.scenes)},
                    "scenes": len(self.scenes),
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        (script / "lines.jsonl").write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in self.lines),
            encoding="utf-8",
        )
        for scene in self.scenes:
            (script / "scenes" / f"{scene['event']}.json").write_text(
                json.dumps(scene, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        return script


def write_translation(path: Path, rows: list[tuple[str, str, str]], header: str = "") -> Path:
    """A translation file in the provisional format: `id <TAB> speaker <TAB> English`."""
    lines = [f"# {header}"] if header else []
    lines += ["\t".join(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
