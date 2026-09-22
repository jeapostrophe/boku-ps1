# The renderer patch, prototyped (PLAN `TXT-05`; measurements for `TXT-07`)

A working proportional, horizontal text renderer: armips source applied to a copy of the
contributor's image, booted headlessly on PCSX-Redux and on Beetle PSX, and looked at.
**Measured** = read off a build or a screenshot made on 2026-09-20 with the tools named here;
the screenshots are the game's pixels, so they stay in the gitignored `work/txt05/` and are
described, not shown. Engine facts are cited from their homes: [text-renderer.md](text-renderer.md)
(the walkers, the 9 slots, free space), [renderer-runtime.md](renderer-runtime.md) (what the
emulator confirmed), [font.md](font.md) (the sheet), [font-candidates.md](font-candidates.md)
(advance models, free cells, the mock-ups this is compared with), [text-outside-events.md](text-outside-events.md)
(the arrays behind the other surfaces).

Nothing here takes `TXT-03` or `TXT-06` from Jay: pen, band, line pitch, glyph gap and the
select geometry are build arguments, and the typeface is an input file.

**Surfaces, in the order a player meets them** (numbers are [text-renderer.md](text-renderer.md) § 3's):

| surface | state |
|---|---|
| 1 dialogue (`dialog_draw`) | **done, proven on both emulators** |
| 17 memory-card messages, 19 config labels (`TITLE.OVL` walkers) | **done, proven on both emulators** |
| 20 extras labels (`TITLE.OVL`) | patched and assembled against the retail bytes; the screen needs a save file, so not shot |
| 2 SELECT menus (`select_draw`) | **done, proven on PCSX-Redux** (`E0112.1`, pad-driven: § "SELECT on screen"); **not reached on Beetle** — the route needs a RAM poke, § "Reaching the living room" |
| 3, 4 the insect book's two walkers (`HHON.OVL`) | **documented only**, not patched: § "The `HHON` walkers" |
| the other 17 fixed-pitch surfaces | site table with a decision each: § "The fixed-pitch surfaces" |

## Build and look

```sh
./make.sh build-days                           # edits.json, then translation/days -> build/days/
uv run python tools/vwf/build_prototype.py     # -> build/vwf/image.cue, manifest.json, files/
tools/vwf/shoot.sh                             # both emulators -> work/txt05/shots/*.png
```

`./make.sh build-days` is the real pipeline (2026-09-20): `build_prototype.py --edits-only`
assembles the patch and rebuilds the sheet into `build/vwf/edits.json`, and `boku build
--vwf` applies those edits beside the reinserter, laying every line out in the band's
pixels with its speaker label and marks (§ "The speaker label"), growing members and
relocating them (`PIPE-03`). The second form is the older in-place prototype: sample
lines written where the Japanese sat, no growth (`--days translation/days` writes only the
lines that fit their sites, § "The reviewed translation, in place"). It is kept for looking
at the renderer in isolation, not for producing the translated image.

`build_prototype.py --help` lists the layout arguments (`--pen-x --pen-y --line-pitch --band-y
--band-h --gap`, and for selects `--sel-x --sel-y --sel-pitch --sel-pad --sel-cursor-dx
--sel-cursor-dy`), `--font FILE`, `--lines FILE` and `--asm FILE`. It needs armips
([tooling-setup.md](tooling-setup.md)); `shoot.sh` needs the emulator variables documented there.
The build reads the import under `disc/` and never writes there.

| tracked file | what it is |
|---|---|
| `asm/vwf.asm` | the file armips assembles: opens the executable, includes the surfaces, holds the free space (table, variables, hook bodies), then opens `TITLE.OVL` |
| `asm/dialogue.asm` | the dialogue surface; every site carries the retail instructions as an `ORIGINAL` block |
| `asm/select.asm` | SELECT menus: the two hooks, cursor, pad, and the two geometry tables |
| `asm/title.asm` | the three `TITLE.OVL` walkers, routed through the width table |
| `tools/vwf/build_prototype.py` | sheet rebuild, advance table, armips over the executable and the overlays, text, image writes, manifest |
| `tools/vwf/placeholder-glyphs.txt` | eight placeholder cells (space `' " - ( ) ~ —`) and the glyph-file format |
| `tools/vwf/prototype-lines.tsv` | which sample line or fixture goes over which site: dialogue, selects, array items |
| `tools/vwf/reach-select.lua` | PCSX-Redux driver that reaches `E0112.1` from free roam (a map poke, § "Reaching the living room"), drives the select with the pad and reports `select_open` / `select_draw` |
| `tools/vwf/shoot.sh` | the headless runs and the frames worth keeping |

## Design

### Dialogue: the advance lives in the nine slots, in place

`dialog_draw` spends `0x8002BF5C…0x8002BF7C` re-reading `g_text_flags` to choose `y += 13` or
`x += 14`. With every caller horizontal that test is dead, and nine instructions are exactly
enough for a table lookup **once the R3000's load delay is respected** — which the 8-instruction
sketch in [text-renderer.md](text-renderer.md) § 4b does not (it uses `v0` in the instruction
after `lhu v0`, and `v1` straight after `lbu v1`). The version that fits fetches the table byte
unconditionally and puts the range test in its delay slot:

```
lhu   v0, 0(s0)               ; glyph id just drawn
lui   v1, hi(vwf_advance)     ; (load delay of v0)
addu  v1, v1, v0
lbu   v1, lo(vwf_advance)(v1)
sltiu at, v0, TABLE_IDS       ; (load delay of v1)
bnez  at, advance
nop
addiu v1, zero, 14            ; ids past the table keep the stock pitch
advance: addu s2, s2, v1      ; falls into 0x8002BF80  addiu s0,s0,2
```

The unconditional fetch is safe: a glyph word is below `0x8000`, so the address is at most
`vwf_advance + 0x7FFF`, inside main RAM. All nine slots are used; anything more (a bearing, kerning)
needs a jump out.

### Every other surface: one `jal` per walker, bodies in the free space

The other walkers have no dead instructions to spend, but each has one thing the dialogue loop
lacks: the pen step is a lone `addiu pen,pen,12` whose next instruction is not a branch, so it can
become a `jal` to a ten-word body that adds `vwf_advance[id]` instead. `ra` is free at every one
(every walker saved its own and `jal glyph_draw` clobbers it each glyph); the bodies write only
`at` and `t9`, so whatever the delay slot loaded — the next `a0`, a loop constant in `v0` — survives.
Where the step itself sits in a branch delay slot (`text_draw_line_h`, the extras walkers) the
`jal` takes the pointer step's slot instead and the body steps the pointer too. One macro,
`vwf_lookup_at`, is the lookup; a body is that plus its add. The bodies are named by what they
touch: `vwf_step_s5_s0` is "pen `s5`, id at `-2(s0)`".

### SELECT: columns become rows, measured every frame

Stock `select_draw` (`0x8002C234`) draws each option down a column whose top is
`g_select_pos[layout][line]`, steps `y += 12` (`0x8002C2D0`), and `select_box_draw` draws a
50 %-black tile from `g_select_rect[type − 1]`; the cursor sprite sits 24 px *above* the column
and the pad maps LEFT/RIGHT (or, with four or more options, a two-column scheme) onto the cursor
([text-renderer.md](text-renderer.md) § 1, § 4c). The patch (`asm/select.asm`):

* **Rows.** `g_select_pos` is rewritten so every layout is the same five row origins,
  `(SEL_X, SEL_Y + i · SEL_PITCH)`; a layout with *n* lines reads the first *n* (a prompt line,
  where the layout has one, is row 0). The step becomes `jal vwf_select_advance`, whose delay slot
  is the stock `lhu a0,0(s1)`: the body adds the table advance to `s2` (x) and leaves `s0` (y).
* **The box hugs the text.** The body also records the pen's furthest x and the last row's y in
  two words of the free space (`vwf_select_xmax`, `vwf_select_ymax`). `select_box_draw` runs after
  `select_draw` in both runners (the event op at `0x8002D0E0…E8` and `select_run_ptr` at
  `0x8002D158…60`), so its `lhu` of the table's w and h becomes `jal vwf_select_box`, which returns
  `w = xmax + SEL_PAD − rect.x`, `h = ymax + 12 + SEL_PAD − rect.y` and zeroes `xmax`. A caller
  that never measured — the controls-help screen draws the type-7 box without `select_draw` — gets
  the table's w and h, because `xmax` is 0 then. `g_select_rect` entries 0–5 hold the corner:
  `SEL_PAD` left of the cursor and above the first row; entry 6 is untouched.
* **Cursor and pad.** The cursor's two immediates become `SEL_CURSOR_DX/DY` from the row origin.
  In `select_cursor_update` the "fewer than four options" test becomes always-true (one word:
  `slti v0,s1,4` → `addiu v0,zero,1`), so the two-column block never runs, and that block's two
  masks are re-keyed: DOWN (`0x4000`) = +1, UP (`0x1000`) = −1. Clamping at both ends is stock.
* **Text.** A select site's English is one option per line; the line count must equal the
  layout's (`encode_select` counts the stock `0x8001`s), and no option may be wider than
  `select_width` = from `SEL_X` to the pen's right margin (the engine clips at the screen edge).

Sixteen executable words plus the two tables (240 + 48 bytes), and two bodies in the free space.
The eight native menus (`select_run_ptr`: the insect cage, `TAKO`, `MUSI`, `HHON` ×2, `ZUKAN`)
use the same three routines and the same tables, so they change with it; their texts are the S
arrays of [text-outside-events.md](text-outside-events.md).

### The free space

**The table lives in the heap-raise gap**, `0x8008F3A4…0x8008F7FF` (1,116 bytes, already inside
the file, above every overlay): one data word moves the heap's first byte to `0x8008F800`. Chosen
over the dead-code islands because it is the only candidate whose deadness was *measured* with
write-breakpoints rather than inferred from missing references ([renderer-runtime.md](renderer-runtime.md)
§ Q5), it is one contiguous `.area`, and it costs nothing but 1.1 KB of heap. Layout of the
(c2) build (`edits.json` → `gap`): `vwf_advance` **812 bytes** at `0x8008F3A4`;
`vwf_select_xmax/ymax` at `0x8008F6D0`; `vwf_select_advance`, `vwf_step_s5_s0`,
`vwf_step_v1_s0_s1`, `vwf_step_s1_s0_next`, `vwf_select_box` from `0x8008F6D8`; free again
from `vwf_free` = `0x8008F7DC` — **36 bytes**, which is not a whole body. The table is as
long as the highest cell any English character was given, so it grows with the free-cell
allocation, not with the font. The surfaces still to hook (§ "The
fixed-pitch surfaces") need five to seven, about 240 bytes, so the next home is the 620-byte
island at `0x80012E04` ([text-renderer.md](text-renderer.md) § 6 candidate 2), whose deadness is
inferred, not measured — a write-breakpoint run like Q5's should precede it.

### The ruled band, the advance model, and what fits (Jay, 2026-09-20)

`TXT-03`/`TXT-06`/`TXT-07` were ruled on 2026-09-20 and are the build's defaults
(`Layout` in `build_prototype.py`): **the smallest band** — 37 rows from y = 203, pen
(24, 205), line pitch 11, **three lines** — **translucent** (`g_dlgbox_fade[6]` := entry 5's
(168, additive) in place of (224, opaque): one data site in `asm/dialogue.asm`), **the game's
own sheet** as the typeface, and advance model **(c2)**: each Latin glyph re-aligned to
column 0 with the table advance its ink width + the gap (a 2-px-or-narrower ink gets one
more, for the shadow). Jay ranked (c1) — the glyph left at its native bearing, advance to
the ink's right edge — above it on looks and gave the lint the casting vote, and under this
band (c1) needs a fourth line on far more pages than (c2) does (`PLAN TXT-07` for the
counts, from `work/txt05b/lint-c1-3lines.txt` and `lint-c2-3lines.txt`); the band stays at
37 rows, so (c2) is what the build installs and `--advance-model c1` stays available.

Measured on the (c1) build: the Latin cells' advances are `i l` 8, `a n` 9, `A U` 11 — the
bearings the sheet centres its glyphs with become white space between letters, so set text
reads loose (`work/txt05b/shots/01…`); **682 of 751 lines written, 69 left Japanese**
(`build/days/manifest.json` → `lines_refused`), none for bytes or a page count.

Under either model **a character whose native cell the Japanese script draws is copied
into a free cell** rather than kept where it is (`place_font`): the sheet and the advance
table are both indexed by cell id and the hooked renderer reads them for a still-Japanese
page too, so a kept cell hands that page an English width. Measured on this dump before the
gate went in: 26 such cells under (c1) (the digits, `A B C L M P T X Z z`, `. : ? ! / +`)
and one under (c2) (`/`).

Under *this* band the pencil was left stock at x ≥ 267, rows 220–229, crossing lines 2
*and* 3 (cells 216–227, 227–238), so `DIALOGUE_BAND` guarded both at 238 px. **That is no
longer the geometry**: § Round 2 moves the band up and the pencil with it, into the band's
last 11 rows (`asm/dialogue.asm` `PENCIL_Y`), where it crosses **line 3 only** — which is
the guard in force (`boku.layout.DIALOGUE_BAND`, `guarded_from` 3).

### Round 2 (2026-09-20): the display's visible rows, the marks' bearings, the hand

**The band was partly off screen.** The video setup (`0x800124EC`, mode 1's init from the
table at `0x80023810`) calls `SetDefDispEnv(disp0, 0, 0x110, 320, 240)` and
`SetDefDispEnv(disp1, 0, 0, 320, 240)` — a double buffer at VRAM y 272 / 0 — and
`PutDispEnv` programs the vertical display range as `Y1 = screen.y + 0x10`,
`Y2 = Y1 + (screen.h or 0xF0)` (`0x80053E74…98`), i.e. scanlines 16–255 for framebuffer
rows 0–239 — the full frame. Beetle's `retro_run` output (what RetroArch shows at its
default) is all 240 rows, which is why nothing was seen; **DuckStation's default crop shows
about 232 rows** — observed, not derived: in Jay's screenshot row 0 is intact and the third
line (cells 227–238 then) is cut at about row 232 by the eye. The original keeps its text
above row 200 (13-px rows from y = 22, longest page to 188) and only the next-page marker
reaches 230. **The band is now Y = 191, H = 37, pen (24, 193), pitch 11**: cells at 193,
204, 215, last ink row 225, shadow 226 — inside DuckStation's crop, and no lower than the
game's own marker reached. H and the pitch are unchanged. The marker moves with it: it is
two 20 × 8 sprites at the same x (266 ± 3 wobble, sine table `0x8006B080`) — the green
pencil (stock y 220, `0x8002C088`) and its grey shadow (223, `0x8002C0E8`), stock rows
220–230 — both at `asm/dialogue.asm`'s `PENCIL_Y` = the band's last 11 rows (217–227), so
they cross line 3 only, at x 263–269 and beyond, and `DIALOGUE_BAND` guards only that line. The select rows move above the band —
`SEL_Y` 126, `SEL_PITCH` 11, so a five-row layout's box ends at 188 — because the band
and a select are on screen together (Jay's screenshot). Lint under (c2) with this
geometry: **4 pages need a 4th line** (`E0771.0`, `E0772.1`, `E0773.2`, `E4028.11`), 0 rows
over width — the same four as before; the build lays out 757 of 761 lines.

**The marks.** `「`/`『` carry a 2-px left bearing inside their cells (advance 7 / 8) and
`」`/`』` carry none, so a line ends at them (advance 4 / 6). Every one of them is its
rightmost inked column **+ 2**, which is what `load_glyph_file` now insists on in place of
ink at column 0: the renderer draws each glyph twice, one column apart, so the ink's shadow
lands on `ink + 1` and the next glyph may not start before `ink + 2`. Both `game_font`
models hit that bound exactly. `』` shipped at 5 until the rule was measured and drew its
shadow under the next glyph. `Uncle 「Text」` (`work/txt05b/shots/r2/02`).

**The hand points right.** The select cursor is ONMEM.BIN sprite 1 — 16 × 24 at (0, 32) on
the 48 × 88 4bpp UI sheet (child 3), drawn by `0x80042B64` from the record in child 0
(`{u, v, w in VRAM units, h}`; the loader fixes up the page and CLUT). `build_prototype.py`
`cursor_edits` turns the cell a quarter turn counter-clockwise in place, pads the rows it
left transparent, and sets the record to 24 × 16; `SEL_CURSOR_DX` is −26. **What makes the
turn safe is the record table, not the pixels**: index 0 of this sheet's CLUT is opaque
white and index 1 transparent, so the padding beside the hand reads as `0` and no pixel
test tells it from art — the check is that no other record reaches either the cell being
vacated or the one being claimed (records 0/2/3/4 are at v 56, 0, 72, 80, and only the hand
touches rows 32–55). No new art: the pixels are the original's, turned, and stay in the
gitignored `edits.json`. `--cursor down` keeps the stock sprite, and `sel_cursor_dx`
follows the hand's width (−18) unless `--sel-cursor-dx` says otherwise.

**The title screens are Japanese renderer text, not plates.** Card check ("checking the
memory card / do not remove"), "no file" and the four config labels are `TITLE.OVL`'s array
sites (`title@…` ids in `disc/script/lines.jsonl`), drawn by the hooked walkers 17 and 19 at
the stock pitch because `translation/days` carries no rows for them; the prototype's
fixtures ("Checking card", "No file here", "Message / Tone / Pad / Rumble") are in
`tools/vwf/prototype-lines.tsv`. Plates: the 設定 title, the 音声＋字幕 panel, もどる
(`GFX-03`).

**`H06001` loaded.** EVVER's `H06` records are `{name, u32 day mask (bit 0 = day 1), set,
suffix}`: `01` on day 15 morning, `02` days 16–30, else `00` — a `--day 15 --hour 10` poke
and two `H06` requests load it. On this build its child 6 is at **`0x6858`**, past `0x6400`,
and it draws (`shots/r2/06`); a test image with its day 5–7 lines padded puts child 6 at
**`0x7814`** (956 bytes under `0x7C00`) and also draws (`shots/r2/07`; the load takes ~1,000
frames to fade in). The raised bound holds; the retail one would have trapped both.

**Reaching the evening.** The clock advances only on the game's own transitions and an
hour poke past 17:00 is snapped back to 17:00 on day 1 until the dinner call runs; `A19`
requested at 17:00 runs `E0190` and dinner with ○, leaving 19:04 in `G02200`, from which a
`G01` request loads `G01200`.

### Round 3 (2026-09-21): the punctuation, the band's depth, the select box

**Punctuation (`TXT-08`).** The sheet has horizontal `．` `，` `：` `；` (glyph-table.tsv;
the vertical `、` `。` are cells 1–2), drawn as 2 × 2 dots on rows 7–8 — a row *above* the
Latin baseline (letters end on row 9, descenders reach 10) — which is the floating full
stop Jay saw. Its `？`/`！` end in a 1 × 2 dot (column 5, rows 8–9). Measured against the
harvest candidates: Ark Pixel 12 and Galmuri set `.` and `:` as 1 × 1 dots and `'` as a
1 × 3 tick, lighter than the sheet, so a redraw to the sheet's weight matches better than
any harvest, and every cell in `tools/vwf/placeholder-glyphs.txt` is drawn for this
project (its header says so; where a mark has one way to be drawn — a 2 × 2 dot, a
mirrored paren — the drawing may coincide with the sheet's; no harvested cell, hence no
licence to record). Changed: `.` `,` `:` `;` redrawn on the baseline (rows 8–9, 2 × 2 like
the sheet's `．`/`：`, comma and semicolon with a one-pixel tail) in free cells so the
sheet's own cells stay for Japanese; `'` and `"` become the comma's shape raised to rows
1–4 (advance 4 / 7). The 1-px `- — ( ) ~` already match the sheet's strokes. Loader rule
unchanged: advance ≥ ink + 2.

**The band's depth — a premise refuted, nothing patched.** Round 2 reported Boku's
close-up head drawn over the band in the evening living room (`shots/r2/12`). Measured on
the pixels, that was a misreading of a zoom cut across the band's top edge: the hair above
row 191 is dark (80, 48, 40) and inside the band it is washed (224, 192, 184) — the head was
behind the band all along, and a round-3 build that moved the band into the text's slot
gave pixel-identical frames (`shots/r3/04`). The order, recorded so nobody re-derives it:
the OT is cleared reversed (`ClearOTagR` called at `0x80011CB4`) and drawn from its far end
to slot 0 (`DrawOTag` called at `0x80012748`), so a lower slot is in front; within a slot
`AddPrim` puts a later primitive at the head, drawn first. The strip's tile, fade and
`DR_TPAGE` go to `g_ot[2]` (`dialog_panel_draw`, `addiu a0,a0,8` at `0x8002EA40`,
`0x8002EAC0`, `0x8002EB00`), every glyph to `g_ot[g_text_layer]` = slot 1 (`0x80028E3C`),
and `event_update` calls `dialog_draw` (`0x8002D3B4`) before `dialog_panel_draw`
(`0x8002D3BC`). Walked on PCSX-Redux at the first line (`tools/vwf/ot-walk.lua`): slot 2
holds the panel's tpage (abr 1), fade and tile (0, 191, 330 × 37, colour 168); slot 1 the
font tpage and the glyph sprites; slot 0 a 2 × 1 VRAM copy and a nop; slot 3 empty. The
stock layout stays: moving the band to slot 1 would put it in front of any slot-1
primitive added after `event_update` (the other `glyph_draw` callers draw there), an
exposure the stock order does not have. Two traps from the attempt, recorded: a site
`.org`'d inside another block's `.area` is silently overwritten by whichever block armips
assembles last while `ORIGINAL=1` stays green (`tests/test_asm_layout.py` now refuses
overlapping sites); and a flattened translucent band is easy to misread as absent in a
thumbnail — rows 191–227 read 184–248 against 32–80 outside.

**The select box.** `g_select_rect`'s w and h are only what `vwf_select_box` returns when
`select_draw` measured nothing — every select measures, so the drawn box is `xmax + pad`
wide and `ymax + cell + pad` tall from the corner. The literals are now derived anyway:
`SEL_BOX_H = 4·SEL_PITCH + 12 + 2·SEL_PAD` (the five-row layout) and `SEL_BOX_W` = the widest
option plus both pads and the cursor. The only ≥ 4-option selects in days 1–7 are `E0404.6`/`.7`
(day 4 dinner, an auto event the poked entry does not fire), so the largest reachable is the
three-line `E0022` (prompt + 2, the living-room bookshelf), reached by walking into its zone.

### The speaker label (`TXT-05`'s "label design", decided 2026-09-20)

**Form: the original's**, `Uncle「…」` — the label, then the corner brackets in horizontal
form. Style guide § 9 (Q7) makes that the default and leaves 「」-vs-quotes to the band; the
brackets win because the charter translates rather than localises (the marks are the
original's signature), `Uncle "…"` reads as a citation, and `Uncle: ` drops the marks the
ruling kept. Cost is the same as `: `: the brackets are drawn 4–5 px wide (advance 5; `『』`
6) against `:` + space at 8 px, for two extra bytes a message. The sheet's own `「」『』`
are vertical forms and lie on their sides horizontally (renderer-runtime.md § Q2), so the
four are new placeholder glyphs in free cells (`tools/vwf/placeholder-glyphs.txt`).

**Mechanism: the inserter, not the renderer.** `boku.layout.original_marks` reads what the
Japanese drew — `「` after the first cell means a label, at the first cell a bare examine or
chorus line, `『` narration, and the closing mark is the last cell before the end, absent
(a split utterance) or, when it does not close the mark that opened the message, a refusal
rather than a mark the inserter invented — and `boku.layout.lay_out_message` puts
`<speaker>` + the opening mark
in front of page 1's first word and the closing mark after the last page's last word, as
text. The renderer draws them like any other cells; the wrap measures them on the lines
they really occupy; a speaker outside style guide § 9's list is a refusal, not a misspelling
on screen; a chorus keeps the original's bare `「…」` (the slot-12 chorus is unlabelled on
the disc); narration is `『…』` with no label. A renderer hook would have needed a slot →
name table and a draw call in the 52 free bytes, and the slot disagrees with the label in
11 lines. **Bytes**: label glyphs + 2 per copy — `Uncle「…」` 14, `Boku「…」` 12, `Shirabe「…」`
18. The build that added them grew 312 members by 154,048 bytes in all and left **550 of
765 arena sectors** (the previous build, without labels but with the four-line band, 511:
the shorter pages of a three-line band, refused, cost more than the labels).

`boku lint` charges `speaker + 「` on line 1 (`label_allowance`), which is now exact for a
labelled line because the cell map carries the bracket's real advance (it charged a 14-px
fallback before). Not charged by the lint: the closing mark on the last line, and the bare
marks of an unlabelled line — the build measures both, so a line the lint passes can be
refused by up to 6 px on those lines (`work/txt05b/shots/03`, `04` show page 1 without and
page 2 with the closing mark).

### The map work area (`PIPE-03`; research/loading-and-memory.md § "Making room" 2)

`M_H06001` was 628 bytes over `0x6400` with days 1–7 alone. The constant is **four
instructions at three sites** — `boot_load_resident`'s bumps for A (`0x80012350`) and B
(`0x80012370`), `map_commit`'s test `slti v0,v0,0x6401` (`0x80017748`) and swap length
(`0x800177E0`) — all raised together to `0x6400 + MAP_AREA_EXTRA` in `asm/arena.asm`,
default **`0x1800`** (`--map-area-extra`), i.e. `0x7C00`. Every other buffer address is
bump-derived (the model pool, `g_bg_clut_save`, `g_bg_save`), the only other `0x6400`
immediate in the executable is the sound work buffer, and no overlay holds one (scanned).
`edits.json` records `map_work_area_end` and `boku build` hands it to the reinserter
(`plan(work_area_end=)`), so the build refuses at the engine's real limit.

**What it costs, measured**: the fixed arena ends 2 × `0x1800` = 12,288 bytes higher, under
the level-C arena, `bg_swap_in`'s `0x6000` scratch and the stack. `tools/vwf/stack-probe.lua`
on PCSX-Redux, retail layout, arrival sequence + free roam (14,000 frames): stack low-water
**`0x801FF040`**, 4,016 bytes below the top, the level-C bump pointer never moved, and the
gap from the scratch's end to that mark was **20,044 bytes**. The same on Beetle with the
patched image, a sentinel poked into a save state (`tools/vwf/state_poke.py --fill/--scan`)
over free roam, two map requests and the SELECT: low-water `0x801FF040` again. So 20,044 −
1,116 (heap raise) − 12,288 leaves **6,640 bytes** past the measured depth; `arena.asm`
refuses a raise that leaves less than 1.5 × the measured depth. Read back from the Beetle
state: `g_map_load` `0x801B5A50`, `g_bg_clut_save` = B + `0x7C00`, level C `0x801F7650`.

**Proven**: with the raise in, the arrival sequence, three map changes (`G14` → `G06` →
`G01`), the SELECT and the day-2 `H06000` scene (`E0220`, `work/txt05b/shots/08`) all run
on Beetle, and `M_H06001` itself — child 6 past `0x6400` — loads and draws (§ "Round 2").
**Not proven**: the stack in menus, sumo and fishing. Under the full-translation estimate six maps pass `0x6400` by up to 5,926 bytes
(`M_H06001`), inside this raise.

### No cell the Japanese script draws is touched

Under (c1) this is trivially so: no Latin cell is written at all, and only a cell whose
pixels change is gated. The rest of this section describes (c2), `--advance-model c2`.
[font-candidates.md](font-candidates.md) § 7 accepted re-aligning Latin cells in place as
"cosmetic" for the ten letters, the digits and the punctuation untranslated lines use. That is
avoidable, so the build avoids it: an English character keeps its own cell only when that cell is
in the free list of [font-candidates.md](font-candidates.md) § 1 (parsed from that file, not
copied); every other character — `A B C L M P T X Z z`, the digits, `. : ? ! / + %`, and the eight
glyphs the sheet lacks — is drawn into a free cell. 88 characters: 53 in place, 35 in free cells
(the junk symbols `゛ ‘ ’ ± ÷ ￥ → ← ↑`, nine unused kana, then unused kanji from 292 up to 794,
which is what makes the table 795 long). Table entries for every other id are 14. Consequences:
untranslated dialogue, the code-drawn digits (`52 + n`) and the fixed-pitch surfaces look exactly
as they did, and **the English space is its own blank cell** (id 10, advance 4) — id 0 stays the
14-px Japanese space and indent cell. The inserter must therefore encode English through the
character map the build emits (`manifest.json` → `cells`), not through NFKC of
`data/glyph-table.tsv`.

**Two gates refuse a cell that would change under something that draws it.** The first walks
every text site of the import — messages, selects, arrays — and refuses if any draws a cell about
to be redrawn. The second, `code_glyph_ids`, covers what no site can show: it scans every `jal
glyph_draw` / `glyph_draw_layer` in the executable and the four drawing overlays and resolves
the `a0` each passes — an immediate (`addiu/ori a0,zero,n`), or the digit pattern `addiu a0,r,0x34`
(ten ids), plus `sysmsg_draw`'s 13 → 14 remap. On this image that is 25 ids: 13, 14, 15, 40,
52–61, 343, 344, 440, 503, 543, 605, 618, 898, 1004, 1209, 1456 — the same list
[font.md](font.md) § "The draw code" was read from by hand, now derived from the bytes. Made red
on purpose: with 1209 pretended free the *text* gate already refuses (an array draws it); with
**40** (`％`, only `TITLE`'s `extras_numbers_draw` draws it) the text gate passes and the code gate
refuses with "code on this disc draws them by id". The nudge tables (`0x80036700`, `TITLE
0x80079BD4`, `MUSI 0x8007A8B8`) shift glyphs, they do not choose them, so they add nothing.

### The font is a build input

A glyph file is `glyph U+XXXX advance N` plus twelve rows of twelve `.`/`#`, ink starting at
column 0 (`tools/vwf/placeholder-glyphs.txt` is one). With no `--font`, glyphs are the game's own
Latin cells read from the contributor's `ONMEM.BIN`, shifted to column 0, advance = ink width +
`--gap` (1), **plus one more when the ink is 2 px or narrower** — the shadow is a copy at x + 1,
and at ink + gap it filled the gap between two dots, so `...` read as a dash (the blemish the
first build recorded; § "What the screenshots show"). Now `.` `,` `:` `;` advance 4 and `i l ! ' |
I` 3. **Proven on the current build**: `beetle-E0171.3.png` ("Boku: ...Huh?", `E0650.16` over
`E0171.3`) shows three separate dots, each with its own shadow and a paper column between —
zoomed 4× to check. With `--font`, that file supplies every glyph and advance; cell
allocation, table and asm are unchanged. A baker for an OFL face (`TXT-06`) only has to write that format. The rebuilt sheet
(`build/vwf/files/font-sheet.tim`) is disc-derived and never tracked.

### `ORIGINAL=1` checks the comments

Each site has two arms: the patch, and the instructions the retail file holds there. The build
assembles the `ORIGINAL` arm first over a copy of the executable **and of every drawing overlay**
and refuses unless each comes back byte-identical, so a wrong "stock:" line is a build error,
not a stale comment. Made red on purpose: `0x16` → `0x17` at `msg_open` reports "first difference
at RAM 0x8002CFC8". Other gates made red the same way: a 1,200-byte table ("Area at 8008f3a4
overflowed by 84 bytes"), an English line larger than its site, a page count that differs from the
original's, a select with the wrong line count, a free list that wrongly includes id 4.

## The patched sites

RAM addresses; executable file offset = RAM − `0x8000F800`, overlay file offset = RAM −
`0x80079A08`. Every site is an armips `.area`.

**Dialogue** (`asm/dialogue.asm`, 21 words):

| RAM | function | stock | patched |
|---|---|---|---|
| `0x8002CFC4`–`CC` | `msg_open` | `addiu a0,zero,0x129` · `addiu a1,zero,0x16` · `addiu a2,zero,1` | `PEN_X` (24) · `PEN_Y` (176) · `0` = horizontal |
| `0x8003206C`, `74`, `78` | ant-count message | the same three literals (`0x80032070 addiu v0,v0,0x34` between them is restated unchanged) | the same three values |
| `0x8002911C` | `g_dlgbox_x` (`s16`) | 260 | −5: tile 330 wide, fade off-screen |
| `0x8002EA34`, `38`, `44`, `48` | `dialog_panel_draw` | `addiu s1,zero,0xF0` · `sh zero,0xA(s0)` · `addiu v0,v1,5` · `sh v0,8(s0)` | `addiu s1,zero,BAND_H` · `sh zero,8(s0)` · `addiu v0,zero,BAND_Y` · `sh v0,0xA(s0)` — `band2` |
| `0x8002BF48` | `dialog_draw`, newline | `addiu s1,s1,0xD` | `addiu s1,s1,LINE_PITCH` (13: unchanged bytes by default) |
| `0x80029138` | `g_dlgbox_fade[6]` (data) | `224, 1` (opaque) | `BAND_BRIGHTNESS, BAND_BLEND` (168, 2: additive, the translucent look) |
| `0x8002BF5C`–`7C` | `dialog_draw`, advance | `lui v0,0x8003` · `lw v0,0x59E4(v0)` · `nop` · `andi v0,v0,0x10` · `beqz v0,+3` · `nop` · `j 0x8002BF80` · `addiu s1,s1,0xD` · `addiu s2,s2,0xE` | the nine instructions above |

`g_text_flags & 0x10` still selects the newline rule at `0x8002BF1C`, but no longer the advance: a
caller passing `vertical = 1` would now draw garbage. The two callers patched above are the only
ones in any image ([text-renderer.md](text-renderer.md) § "Answers first").

**SELECT** (`asm/select.asm`):

| RAM | function | stock | patched |
|---|---|---|---|
| `0x8002C2D0` | `select_draw`, step | `addiu s0,s0,0xC` (y += 12) | `jal vwf_select_advance` (delay slot `lhu a0,0(s1)` kept) |
| `0x8002C1D0`, `DC` | `select_box_draw` | `lhu v0,4(s1)` (w) · `lhu v0,6(s1)` (h) | `jal vwf_select_box` · `move v0,v1` |
| `0x8002C3D4`, `DC` | `select_cursor_update`, sprite | `addiu a1,a1,-2` · `addiu a2,a2,-0x18` | `SEL_CURSOR_DX` (−18) · `SEL_CURSOR_DY` (−2) |
| `0x8002C3E0` | `select_cursor_update`, pad | `slti v0,s1,4` | `addiu v0,zero,1` |
| `0x8002C3F4`, `FC` | `select_cursor_update`, pad | `andi v0,v1,0x8000` (LEFT +1) · `andi v0,v1,0x2000` (RIGHT −1) | `0x4000` (DOWN +1) · `0x1000` (UP −1) |
| `0x80028E7C`… | `g_select_pos`, 12 × 5 × `{s16 x, s16 y}` | column tops ([text-renderer.md](text-renderer.md) § 1) | `(SEL_X, SEL_Y + i · SEL_PITCH)` ×5 per layout |
| `0x80028E44`… | `g_select_rect[0..5]` | `(120,56,80,96)` … `(208,56,96,168)` | `(SEL_X + SEL_CURSOR_DX − SEL_PAD, SEL_Y − SEL_PAD, 80, 40)` |

**Map work area** (`asm/arena.asm`): `0x80012350`, `0x80012370` `addiu s0,s0,0x6400` → `MAP_AREA`;
`0x80017748` `slti v0,v0,0x6401` → `MAP_AREA + 1`; `0x800177E0` `addiu a2,zero,0x6400` → `MAP_AREA`.

**`TITLE.OVL`** (`asm/title.asm`; the `.OVL` is a member of `BOKU.BIN` at `0x6533000`):

| RAM | walker | stock | patched |
|---|---|---|---|
| `0x8007CDD8` | 17, memory-card messages (pen `s5`) | `addiu s5,s5,0xC` | `jal vwf_step_s5_s0` |
| `0x8007FBC4`, `D4` | 19, config labels (pen `s0` via `v1`, ids at `s1`) | `addiu v1,s0,0xC` · `addiu s0,v1,4` (line 1 letter-spaced) | `jal vwf_step_v1_s0_s1` · `move s0,v1` |
| `0x8008045C`, `68` | 20a, extras label 5 (pen `s1`) | `addiu s0,s0,2` · `addiu s1,s1,0xC` (in a branch delay slot) | `jal vwf_step_s1_s0_next` · `nop` |
| `0x80080790`, `A8`, `B0` | 20b, extras labels 0–4 | `addiu v1,s1,0xC` (next is a branch) · `addiu s1,v1,4` (lines 0, 3) · `addiu s0,s0,2` | `move v1,s1` · `move s1,v1` · `jal vwf_step_s1_s0_next` |

**Free space**: `0x80068AF0` heap bump pointer `0x8008F3A4` → `0x8008F800`; `0x8008F3A4…` the
table, variables and bodies listed above.

On the disc this build changed 36 sectors: 7 of the executable, 6 of the font TIM (`ONMEM.BIN`
child 2 starts at `BOKU.BIN + 0x5F94AA0`), 3 of `TITLE.OVL`, and the text (dialogue in the map
packs, the selects, the three EXE arrays). Every range is compared with the import's bytes before
it is replaced, every text site is re-hashed against the walk, every written sector gets fresh
EDC/ECC and is re-verified, and `manifest.json` lists them.

## What is on the disc, and why those lines

The prototype writes **in place**, so a site takes whichever sample line or fixture fits its
bytes and has its page count; the English is a reviewed line from `translation/days/` (the
sample scenes moved there; the loader reads both directories) but is not the
translation of these sites. `E0171.0` (44 bytes) holds 21 characters — "Whoa, that's amazing!"
fits exactly, no label. Arrival-sequence sites are 22–152 bytes for 1–2 pages, so the longest
real page possible is 41 characters; wrap, overflow, line count, digits and the new punctuation
are exercised by three labelled fixtures. `E0177.0` and everything from `E0179` on are left
Japanese on purpose.

Selects: `E0112.1` and `E0202.3` are the game's plain yes/no (14 bytes: "Yes"/"No" fits
exactly); `E0022.0` (48 bytes, prompt + 2) and `E0020.0` (36 bytes) take short fixtures.
`E0176.0` (34 bytes) takes `E0114.2`, the shortest one-page day-1 line that fits.

### The reviewed translation, in place (`--days translation/days`)

`build/vwf-days/` is the same patch with `translation/days/*.txt` (days 1–7 and
`shared.txt`, 764 lines) in place of the sample lines, read through the provisional loader
`boku.translation.SampleScenes` — the same reader `boku build` uses, so the two agree on what a
row means. Measured on this build: **67 lines fit their sites and are written; 697 do not
and stay Japanese**, every one for the same reason — the English needs more bytes than the
site holds (typically 2–2.5×: `E0171.0` 106 for 44, `E0171.1` 324 for 152) — none for a page
count, an option count or a missing glyph (the day files' em dash `—` is now the eighth
placeholder cell; before it, 22 lines were refused for the glyph). The 67 are the short
ones: `E0112.1` "Yes / No", `E0140.0` "H-hello.", `E0140.6` "Huh?", `E0107.0` "Huh...?".
The list is `manifest.json` → `unfitted`, one entry per line with the numbers, and the
summary prints it; nothing is shortened. **So the translation cannot be seen in the game
from an in-place build**, and the number that matters for `PIPE-03`/`PIPE-04` is that 91 %
of the reviewed lines need the container to grow. Array
items keep their word count — the readers count terminators to find item *n* — so an item's
spare words are English spaces before its terminator (zeros after it were drawn as 14-px
Japanese spaces at the head of the next item: measured, the config screen's "Rumble" came out
42 px to the right until this was fixed). Memory-card messages 0, 1, 4, 6 and the five config
labels are fixtures cut to the stock bytes ("Tone" for サウンド: 10 bytes is four glyphs).

## What the screenshots show

Both emulators, same image, frames in `work/txt05/shots/` (`beetle-*` are 320×240 native;
`redux-*` are PCSX-Redux's capture, state-relative or boot-relative frame numbers). The two agree
in every frame compared.

### Dialogue

* **Proportional spacing is right.** "Boku: Okay, Uncle. I understand." and "I would never, ever
  do a thing like that." read as set type: `i`/`l` take 3 px now, `m`/`w` 10, no collisions, no
  floating letters. Measured on Beetle in the first build, the wrapped line "Aunt: What syrup do
  you like on your shaved" had ink from x = 24 to x = **291** against a predicted 269 px of
  advance, i.e. last ink at 24 + 269 − 2 = 291. **Exact.**
* **Shadows intact**: each glyph has its grey copy right and below; nothing clipped, because ink
  starts at column 0 and the widest ink (`/`, `_`) is 11 px, inside the 12-px sprite.
* **Wrap and indent**: the builder's break lands "ice?" on line 2 at x = 24 — no indent, since
  English omits the `0x0000` the Japanese puts after each `0x8001`. Line pitch 13: ink rows
  177–186, 190–198.
* **No sheet garbage.** The four planes share nibbles, and the rebuild only flips the target
  plane's bit: the Japanese pages that follow (`E0177.0`, `E0181`, `E0182`) draw every kana, kanji,
  `？` and bracket as before, at the 14-px pitch with the one-cell indent. (Their brackets lie on
  their sides — that is the vertical-form glyph in a horizontal line, as
  [renderer-runtime.md](renderer-runtime.md) § Q2 already recorded, and not this patch.)
* **The next-page marker is a small green pencil**, not an arrow, drawn at x 267–285, y 220–229 —
  inside the band, bottom right, after ○ cancels auto-advance. It clears lines 1–3 entirely.
* **Pages still turn on their timers** and the last page closes with the clip; the whole sequence
  plays hands-off with the operands untouched.
* **Compared with the mock-ups** (`work/txt06/out/font-game-realigned.png`, `DECIDE.png` § A row
  (c2)): same glyphs, same band, same pen, and the same widths to the pixel in the first build
  (`fonts.game_font('realigned').width()` 269 / 228 / 127 for the three lines measured at 269 /
  228 / 127). Differences: the real frame has the pencil (not in the mock-ups); the placeholder
  punctuation was redrawn, so `' " - ( ) ~` differ by a pixel or two; and, in the first build,
  **`...` read as a short dash**, because each 2-px dot's shadow filled the 1-px gap to the next —
  the narrow-ink rule above is the fix, and it widens lines with many `i l . ,` by a pixel each.

Most informative frames: `beetle-E0174.0-wrapped.png`, `beetle-E0175.0-overflow.png`,
`beetle-E0171.1-page1-arrow.png`, `beetle-E0177.2-five-lines.png`, `beetle-E0182-japanese.png`,
`redux-seq-01720.png`.

### `TITLE.OVL`: the card-check, continue and config screens

Reached from a cold boot (Beetle: START at 3300, then CIRCLE at 3600 for the card check, or DOWN
×1 / ×3 and CIRCLE for continue / config; Redux: START at 2430, the same presses from 2700).

* **Card check** (`beetle-title-card-check.png`, `redux-title-card-check.png`): "Checking card"
  set proportionally at (36, 160) in the wooden frame, dark text with shadow, over the stock
  second line `【メモリーカードを抜かないで下さい】` still at its 12-px pitch — one walker, two
  pitches, keyed on the id. Surface 17's hook is right.
* **Continue with no card** (`beetle-title-no-file.png`, `redux-title-no-file.png`): "No file
  here" (message 4) proportional, the `!` book icon above. The extras entry shows the same
  message, so surface 20's screen is not reachable without a save.
* **Config** (`beetle-title-config.png`, `redux-title-config.png`): "Message / Tone / Pad /
  Rumble" at x = 40 and "On" at the stock line-4 x of 88, all proportional, hand cursor on line
  0; the right-hand panel (`音声＋字幕` …) is a texture. Line 1's stock 16-px letter-spacing is
  gone — with proportional glyphs it read as a mistake.

### SELECT on screen (PCSX-Redux; `reach-select.lua`, frames state-relative)

`E0112` — the uncle's veranda question, day 1, 15:00–17:59 in the living room `G01` — is the
first SELECT a player meets, and the only one in the afternoon's free hour. Reached as
§ "Reaching the living room" says; then ○ at the uncle (`dialog_open(24, 176, 0)` fires),
○ again to cancel the clip, ○ to turn the page, and `select_open(msg 1, type 1, variant 1)`
fires with `select_draw` every frame after it. Frames in `work/txt05/shots/`:

* **`redux-E0112.0-line.png`**: the uncle's line, Japanese (its English is 106 bytes for a
  44-byte site), drawn horizontally in the band at the stock 14-px pitch — the untranslated
  path through the patched `dialog_draw`, in a scene the arrival sequence never showed.
* **`redux-select-E0112.1-yes.png`**: **two rows**, "Yes" at (48, 174) and "No" at (48, 187)
  — `SEL_X`, `SEL_Y`, `SEL_PITCH` 13 — proportional (`Y` 8 px, `e` 6, `s` 5; "Yes" is 19 px
  wide, "No" 13), the **hand cursor beside the row** at x ≈ 30 on "Yes" (`SEL_CURSOR_DX` −18,
  `DY` −2 puts its top two rows above the cell), and the **box hugging the text**: the 50 %
  tile runs from x = 24 (`SEL_X + SEL_CURSOR_DX − SEL_PAD`) to about x = 73 (`xmax` 67 + pad
  6) and from y = 168 to about 205 (`ymax` 187 + 12 + 6) — the stock table would have drawn
  80 × 96 at (120, 56). No line of the dialogue band under it: the band had closed.
* **`redux-select-E0112.1-no-after-DOWN.png`**: after DOWN, the cursor sits beside "No";
  the rows and the box are unchanged. **`…-yes-after-UP.png`**: UP puts it back. **The pad is
  re-keyed**, as § "Cursor and pad" says; LEFT/RIGHT do nothing.
* **`redux-E0112.2-after-select.png`**: ○ on "No" closes the select and the next line
  (`E0112.2`, Japanese) opens in the band — the event continues, `flag_set(255, cursor)`
  took the answer.

Not measured: a select with a prompt line (`g_select_first`), a five-row layout, and the
eight native menus. `select_width` (248 px) was not exercised — both options are short.

## Measurements for `TXT-07`

**The ruled band** (Y = 203, H = 37, pen (24, 205), pitch 11; Beetle, 2026-09-20): three
lines, cells at rows 205, 216, 227, the last shadow row 239 inside the band; 272 usable px;
the pencil (x ≥ 267, rows 220–229) crosses lines 2 and 3, so both end before x ≈ 262;
`Father「My son will be in your care for the / summer vacation.」` style pages set in three
lines at (c1) widths (`work/txt05b/shots/`). Everything below was measured on the earlier
72-row band and still holds for widths and clipping.

### The 72-row band (Y = 168, H = 72, pen (24, 176), pitch 13)

* **Band**: rows 168–239, the full 320 px, flat (224,224,224) on Beetle.
* **Usable width**: 272 px with the left margin mirrored (what the builder wraps to); 296 px to
  the screen edge.
* **Characters per line**: the sample lines written average **5.85 px per character → 46 per
  272-px line** in the first build; the narrow-ink rule adds a pixel to each `i l . , : ; ! '`, so
  a line heavy in them loses one or two characters. The fullest real line is 43 characters in
  269 px. (Mock-up estimate: 43.6 wrapped.)
* **Lines per page**: line *n* has ink rows 177 + 13(n−1) … +9 for caps, +1 for the shadow.
  **Four lines are clean** (last shadow row 225). A fifth draws completely (ink 229–237, shadow
  238) but sits on the bottom edge, inside any CRT's overscan. The pencil occupies x ≥ 267 on rows
  220–229, so **a fourth or fifth line must end before x ≈ 262** on any page that can show it;
  three lines never meet it.
* **A line that is too long is clipped at the right screen edge, silently.** The 56-character
  fixture (345 px) draws to x = 319 and the rest is simply not there: no wrap, no wrap-around to
  the left, nothing else disturbed. The engine has no wrap logic, so the inserter must break
  lines and a lint must measure them in pixels with this table.
* **Selects**: a row may take `select_width` = 320 − 24 − `SEL_X` = **248 px** at the default
  `SEL_X` 48 (the box is measured, so nothing else caps it); five rows at pitch 13 from y = 174
  end at row 238.
* **Primitive cost** is unchanged per glyph (3 × `SPRT`); the longest page here is 56 glyphs.

## The fixed-pitch surfaces

Every horizontal surface of [text-renderer.md](text-renderer.md) § 3 rows 5–26, read again at
the instruction level (2026-09-20, `work/txt01/d`; the R3000 rules: one load-delay slot, one
branch-delay slot; every function here saves `ra`). Decision: **A** = route through the width
table with a `jal` hook; **B** = keep the fixed pitch; **C** = untouched, the surface never draws
Latin from the re-aligned range (immediates, digits, one-glyph rows). Status: **proven** = on
screen on both emulators; **assembled** = in `asm/` and checked against the retail bytes, screen
not reached; **table** = this row is the whole specification.

| # | image · function | step instruction (stock) | pen · id | decision | status |
|---|---|---|---|---|---|
| 5a | EXE `text_draw_right` `0x80035360` — not right-aligned: a count pass steps `s2 += 12` per glyph, then the draw pass walks the line backwards, `s2 −= 12` before each draw, so glyph 0 lands at x | `0x8003539C addiu s1,s1,1` (count; id at `-2(s0)`, delay slot `lh v0,0(s0)`) · `0x800353B0 addiu s2,s2,0xC` (branch delay slot) · `0x800353C0 addiu s2,s2,-0xC` (draw; id at `0(s0)`, delay slot `lh a0,0(s0)`) | `s2` · `s0` | **A**: `539C → jal` {`s2 += w[-2(s0)]; s1 += 1`}, `53B0 → nop`, `53C0 → jal` {`s2 −= w[0(s0)]`}; the bodies must not write `v0`/`a0` | table |
| 5b | EXE `help_line_draw` `0x80035448` (pitch 10) | `0x80035490 addiu s1,s1,0xA`; delay slot `addiu s0,s0,2` so the id is at `-2(s0)` in the body | `s1` · `-2(s0)` | **A**, body = `vwf_step_s1_s0` (pen `s1`, id `-2(s0)`) | table |
| 6 | EXE `date_label_draw` `0x80037544` | none: five immediates at `x, x+0xD, x+0x25, x+0x3A/0x41` plus sprite digits | — | **C**; a translation re-points the ids and re-tunes the literals | table |
| 7 | `date_label_draw_b` | unreferenced | — | **C** | table |
| 8 | EXE `count_label_draw` `0x800377F8` | none: `0x26A`, `0x4B9` at offsets chosen by digit count | — | **C** | table |
| 9 | EXE `sysmsg_draw` `0x800379EC` (insect names, system words; wrapper `sysmsg_line_draw` `0x80037BA8`) | `0x80037B20 addiu s3,s3,0xC` (delay slot `lhu a0,0(s0)`); `0x80037B3C addiu s2,s2,1` is the glyph count, **returned in `v0`** | `s3` · `-2(s0)` | **A with a contract change**: body `s3 += w; s2 += w` and `0x80037B3C → nop`, so the return value becomes the pixel width; then the five consumers of `12 × count` must take it as pixels — EXE `cage_hud_draw` `0x8003FF98…A0` (`sll/addu/sll` → `move v1,v0` + nops), `HHON 0x8007C46C…74` (same), `MUSI 0x8007D474…7C`, and the two right-aligning `8 − n` blocks `MUSI 0x8007D918…30` and `0x8007D874…8C` (the latter through `sllv … s5`, whose `s5` is not settled statically — an emulator question before it is patched). The vertical path (`a3 ≠ 0`) has no traced caller | table (blocked on reach: the cage HUD needs a caught insect) |
| 10 | EXE `mc_slot_labels_draw` `0x8003A7A4` — really the fortune result (`大吉！` …), three glyphs stacked vertically at x `0x9A` | rows, not a pen | — | **C** | table |
| 11 | EXE `sys_title_draw` `0x8003C5EC` (fish names `0x8003DA4C`) | `0x8003C6A0 addiu s1,s1,0xC` (delay slot `lhu a0,0(s0)`) | `s1` · `-2(s0)` | **A**, body `vwf_step_s1_s0` | table |
| 12a | EXE `text_draw_line_h` `0x800437F4` (item names, kite names, fishing at x `0x28`/`0xB2`) | `0x80043848 addiu s1,s1,0xC` is a branch delay slot; `0x80043834 addiu s0,s0,2` is the hook site, with `lhu v0,0(s0)` in its delay slot loading the *current* id | `s1` · `0(s0)` | **A**: `43834 → jal` {`s1 += w[0(s0)]; s0 += 2; lhu v0,0(s0)`}, `43848 → nop` | table |
| 12b | EXE `text_draw_h` `0x80043864` (item descriptions and captions at (0xB8, 0x7E), newline `s2 += 16`) | same shape: `0x800438A4 addiu s0,s0,2` (delay slot `lhu v1,0(s0)`, also the newline operand), `0x800438B8 addiu s1,s1,0xC` in a branch delay slot | `s1` · `0(s0)` | **A**: as 12a with `v1` reloaded; one body can serve both by reloading `v0` and `v1` | table |
| 13, 14 | `kite_menu_draw`, the fishing drawers | draw through 12a/12b | | with 12 | |
| 15 | `TITLE 0x8007BB60` (save date) | none: `0x3C` at `s1`, `0x1B8` at `+0xC`, digits, `0x157` at `+0x30` | — | **C** | table |
| 16 | `TITLE 0x8007C8EC` (slot digits, `0x5B0`) | none | — | **C** | table |
| 17 | `TITLE 0x8007CB54` (memory-card messages; `0x8007CC4C` is inside it, not a second walker) | `0x8007CDD8 addiu s5,s5,0xC` | `s5` · `-2(s0)` | **A** | **proven** |
| 18 | `TITLE 0x8007CF7C` (card-screen yes/no, 5 raw glyphs at `0x80081480`) | `0x8007D050 addiu s1,s1,0xC`; after glyph index 1 (`0x8007D03C addiu v0,zero,1`) the step is `+0x30` (`0x8007D04C`) — the word gap | `s1` · `lh 2·s0(s4)` | **B** for now: "Yes"/"No" is 3 + 2 glyphs, so the split index and the gap literal change with the text; a hook would need the index-based id fetch | table |
| 19 | `TITLE 0x8007FA94` (config) | `0x8007FBC4 addiu v1,s0,0xC` | `v1 = s0 +` · `-2(s1)` | **A** | **proven** |
| 20a | `TITLE 0x800803D8` (extras label 5) | `0x80080468` in a branch delay slot; hook at `0x8008045C addiu s0,s0,2` | `s1` · `-2(s0)` | **A** | assembled |
| 20b | `TITLE 0x80080680` (extras labels 0–4) | `0x80080790 addiu v1,s1,0xC` is followed by a branch; hook at `0x800807B0 addiu s0,s0,2`; lines 0 and 3 letter-spaced by `0x800807A8` | `s1` · `-2(s0)` | **A** | assembled |
| 21 | `TITLE 0x80080484` (extras numbers `／ 3 1 ％`) | none | — | **C** | table |
| 22 | `TAKO 0x8007C684` (crash banner, 4 glyphs stacked vertically) | rows | — | **C** | table |
| 23 | `MUSI 0x8007C604` (button hint, 7 glyphs, bound `slti 7`) | x recomputed from the index: `0x8007C700 sll a1,a1,2` + `addiu a1,a1,0x78` | index | **B**: the glyph count is a code constant; hooking means recomputing x as a prefix sum | table |
| 24 | `MUSI 0x8007EDB0` (strength labels, 3 rows × 3 cells) | x from the index at 16 px (`0x8007EE1C`) and 12 px (`0x8007EE78`), bounds `slti 2`/`3` | index | **B**: the row stride and bounds fix the cell count, so a translation rewrites the array and the bounds anyway | table |
| 25 | `MUSI 0x80084F64` (move names) | `0x800850A0 addiu s1,s1,0xC` (delay slot `lhu a0,0(s0)`) | `s1` · `-2(s0)` | **A**, body `vwf_step_s1_s0` | table (sumo is days of play away) |
| 26 | `MUSI 0x800850D8` (move names, second list) | `0x80085208 addiu s1,s1,0xC` (delay slot `lhu a3,0(s0)`) | `s1` · `-2(s0)` | **A**, the same body | table |

Counts: **A** 12 surfaces (5a, 5b, 9, 11, 12a, 12b, 17, 19, 20a, 20b, 25, 26; 13 and 14 ride on
12), of which 2 proven and 2 assembled; **B** 3 (18, 23, 24); **C** 8 (6, 7, 8, 10, 15, 16, 21,
22). The "six copies of one walker" are not register-identical — pens `s3`, `s5`, `v1`+`s0`,
`v1`+`s1`, `s1`, `s1`; id pointers `s0` or `s1` — so the bodies are per shape: `vwf_step_s1_s0`
serves four surfaces (5b, 11, 25, 26), the three in `asm/vwf.asm` serve `TITLE`, and 5a, 9, 12
need one each. Every body is ten words; with 52 bytes left in the gap the next ones go to the
`0x80012E04` island (§ "The free space").

## Reaching the living room (why the SELECT proof is Redux-only)

Measured 2026-09-20 on this build, reading RAM from `tools/vwf/reach-select.lua` and its
throwaway ancestors, while looking for a pad-only route from the end of the arrival sequence
to `E0112`:

* **The field is tank-controlled** (the game's own controls screen, SELECT at the title:
  UP walks forward, LEFT/RIGHT turn, DOWN turns about, ○ talks / examines, ✕ runs, △/□ the
  sub-screen). A turn is **44 angle units per frame** (4096 = a full turn; `actor + 0x10`),
  a walk **≈ 7.3 units per frame**. The previous attempt at this route held screen directions
  and never left the room for that reason.
* **Actors**: `g_actors` `0x80027778` is a `u32` pointer per slot (Boku 0, the uncle 1 …);
  an actor is `{s32 x @0, y @4, z @8}` in 1/16 units and `s16 angle @0x10`. **Talk** needs
  Boku facing the actor within ±0x155 (≈ 30°): `0x80031424` compares the bearing between two
  actors (`0x800351D0`) with Boku's angle; a ○ from 542 units away, facing him, opened
  nothing, one from ≈ 240 units did.
* **The room is sealed.** The live map's exit list is `*0x80026BE8` → `{u32 count, then
  0x2C-byte records: four `(s16 x, s16 z)` corners at 4-byte spacing, a centre at +0x20/+0x24,
  the target's base name at +0x28}`, scanned every field frame by `0x800208A4` (containment
  test `0x800209A8`, then `map_go` `0x80017954`). **`G14100` has one record → `G13`;
  `G13100` has one record → `G14`.** Boku's room on day 1 at 15:34 has no walkable exit, on
  either emulator; every heading from both halves, and every wall-following pair of legs,
  came back to the other half (the sweeps are in `work/txt05/sweep*/`). The examine zones
  (`*0x80026BFC`, 36-byte records) list four for `G14`; walking into zone 0 — `E0001`'s
  window narration, `examine:z0` — stops 7 units short of it at the desk, and ○ there, at
  twelve headings, opened nothing. Whatever opens the door (a flag, `E0001`, the clock) was
  not found; `G01103` itself has six exits (`G02`, `G17`, three to `G06`, `G10`), so the rest
  of the house is walkable once out.
* **The route used instead** performs the map change the `MAP` opcode performs: `map_request`
  `0x80017A04` copies the base name to `0x80026C48`, points `0x80026BD0` at the request block
  `0x80026C20`, sets `0x80024728 = 1` and bit 1 of `0x80024714`; `0x80017A5C` then calls
  `map_go`, which sets bit 0. Writing those words from Lua in free roam loads `G01103` (the
  variant the clock picks: 15:34, so `E0112`'s hour test already holds), spawns Boku at
  (−163, 1531) facing 0 and the uncle at (−484, 1035), and the clock, the events and the
  talk are the game's. From there: RIGHT 8 frames (angle 352, bearing to the uncle 374), UP
  50, ○. `shoot.sh` runs it; `reach-select.lua` prints every exit record of every map it
  enters, which is the tool for finding the real route.
* **Beetle** has no RAM access, so the same proof there needs either that route or a test
  image whose arrival sequence ends with `MAP:G01` — one operand of `E0186`'s bytecode — which
  was not built. The SELECT code path is identical on both (the patch is the same bytes; the
  dialogue and TITLE hooks agree on both to the pixel), so the risk left is Beetle-specific
  drawing of the 50 % tile, not the logic.

## The `HHON` walkers

**Documented only; not patched.** `HHON.OVL` is the insect box, which in play needs the
insect-collecting kit (`E0107`, day 1 evening at the desk) and then a caught insect — the
sub-screen (△) reached from free roam on this route is the item menu (`item_menu_draw`,
surface 12: the desk, the calendar, the radio-calisthenics card), not the box. On Redux it is
reached without any of that by `tools/redux/book-pokes.lua`, which performs `mode_set` from Lua
(`GFX-05`; the walkers' measured screens are text-renderer.md § 3, rows 3–4). The two
walkers are [text-renderer.md](text-renderer.md) § 4c's: each swaps which register takes
`+0xC` and turns `x −= 0xE; y = 0x20` into `y += pitch; x = left` — four immediates or
registers each plus new origins — and their texts are the `HHON` arrays of
[text-outside-events.md](text-outside-events.md). Decision **A** (route the step through the
width table with a `jal` body) once the hook site's registers are read; the free space for
the bodies is § "The free space"'s next island.

## Not done

* **The extras screen** (surface 20) needs a save file. **`HHON`** is documented, not
  patched. **The twelve other A-decision surfaces** of § "The fixed-pitch surfaces" are a
  table, not code. (SELECT on Beetle was reached on 2026-09-20 through the day-1 living-room
  route, `work/txt05b/shots/06`.)
* **Kerning, bearings, glyphs wider than 12**: none; the dialogue's nine slots are full and the
  bodies add only the table byte.
* **Text that grows**: everything is written in place — which is why `--days` writes 67 lines
  of 764 (§ "The reviewed translation, in place"); relocating and re-lengthening text is the
  pipeline's (`PIPE-03`/`PIPE-04`), and re-authoring the `0x8002` operands is the inserter's.
  The space-padding of array items is a consequence of writing in place and goes away with it.
* **The speaker label** is done in the pipeline build (§ "The speaker label"); the
  prototype's own `--days --label` path still writes the older "Boku: " form.
* **`H06001`** — the one pack whose child 6 passes `0x6400` — was not loaded in an emulator
  (§ "The map work area"); the raise is proven not to break the maps that were.
* **The 46-row band** is reachable (`--band-y 194 --band-h 46 --pen-y 198`) but was not
  shot; the translucent 37-row band is the default and is what every shot under
  `work/txt05b/shots/` shows.

## Open risks

* The heap gap was watched through boot, title and the arrival sequence only
  ([renderer-runtime.md](renderer-runtime.md) § Q5): `MUSI`/`HHON`/`ZUKAN`/`TAKO`, a save and a full
  day are unwatched. A write into the table would show as wrong spacing, not a crash; a write
  into the hook bodies would crash.
* `vwf_select_xmax` is consumed by the first `select_box_draw` after a `select_draw`. Both
  runners keep that order; a third caller drawing the box first would see 0 and get the table's
  80 × 40.
* Free-roam, menus and sumo were not sampled for primitive-buffer headroom (§ Q4), nor for
  stack depth under the raised work area (§ "The map work area": 6,640 bytes past the
  measured 4,016).
* Confirmed on emulators only; EDC/ECC is regenerated and self-checked, but no disc was burned.
