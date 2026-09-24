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
| 20 summer-memories labels (`TITLE.OVL`) | **labels 0–4 done, proven on both emulators** (2026-09-23, a "finished" card: § "Screens behind a save"); label 5 (the dinner-quiz rate, walker 20a) proven on both emulators, forced: § "Screens behind a save" |
| 5 the controls-help screen (START in free roam) | **done, proven on both emulators** (2026-09-22) |
| 12 item names and descriptions (the bag, △ then ○) | **done, proven on both emulators** — descriptions wrapped to their box (2026-09-23, items poked into the bag: § "Screens behind a save"; five lines at a 12-px pitch since 2026-09-24, Beetle); captions and fishing messages seen on Beetle (2026-09-24); kite names ride the same walkers, run instruction by instruction in `tests/test_real_walkers.py` but not reached on screen |
| 2 SELECT menus (`select_draw`) | **done, proven on PCSX-Redux** (`E0112.1`, pad-driven: § "SELECT on screen"); **not reached on Beetle** — the route needs a RAM poke, § "Reaching the living room" |
| 3, 4 the insect book's two walkers (`HHON.OVL`) | **installed, seen on Beetle** (2026-09-24): English in rows, Japanese in its columns (§ "The `HHON` walkers") |
| the other fixed-pitch surfaces | site table with a decision each: § "The fixed-pitch surfaces" |

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
| `asm/walkers.asm` | the executable's fixed-pitch walkers (help screen, items) and the island every walker's step body lives in |
| `tools/vwf/build_prototype.py` | sheet rebuild, advance table, armips over the executable and the overlays, text, image writes, manifest |
| `tools/vwf/placeholder-glyphs.txt` | eight placeholder cells (space `' " - ( ) ~ —`) and the glyph-file format |
| `tools/vwf/prototype-lines.tsv` | which sample line or fixture goes over which site: dialogue, selects, array items |
| `tools/vwf/reach-select.lua` | PCSX-Redux driver that reaches `E0112.1` from free roam (a map poke, § "Reaching the living room"), drives the select with the pad and reports `select_open` / `select_draw` |
| `tools/vwf/shoot.sh` | the headless runs and the frames worth keeping |
| `tools/vwf/shoot-menus.sh` | the card check, the controls-help screen and the item menu on both emulators (free roam reached by playing the arrival sequence out); `ISLAND_WATCH=1` arms `island-watch.lua` |

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
become a `jal` to a body that adds `vwf_advance[id]` instead. `ra` is free at every one
(every walker saved its own and `jal glyph_draw` clobbers it each glyph); the bodies write only
`at`, `t8` and `t9`, so whatever the delay slot loaded — the next `a0`, a loop constant in `v0` —
survives. The lookup itself is one routine per stock pitch (`vwf_width_12`, `vwf_width_10`):
a body keeps its caller's `ra` in `t8`, calls it with the id load in the `jal`'s delay slot,
and returns through `t8` — five to eight words a body instead of twelve to fifteen.
**A cell that is not English keeps the surface's own stock pitch** (12, or 10 on the help
screen's one 10-px line): the table holds the dialogue's 14 for every such cell, and
`vwf_lookup_at stock` turns a 14, or an id past the table, into `stock`; the build refuses an
English advance of 14 so the two meanings cannot meet (`place_font`). Until 2026-09-22 the
`TITLE` bodies took the table's 14 for Japanese too, and the card-check screen's untranslated
second line was drawn 32 px wider than stock; it is now pixel-identical to the retail frame
on Beetle.
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

**The table lives in the PC-host island**, `0x8005CD44…0x8005DCF8` (4,020 bytes of dead
PC file-server code; who owns which region, and why the heap-raise gap it first lived in is not
resident — `MUSI.OVL`'s load zeroes it — is [text-renderer.md](text-renderer.md) § 6). Layout
of the (c2) build (`edits.json` → `gap`): `vwf_advance` **812 bytes** first, then
`vwf_select_xmax/ymax` and the bodies `vwf_select_advance` and `vwf_select_box`; free again
from `vwf_free` — the table is as long as the highest cell any English character was
given, so it grows with the free-cell allocation, not with the font. **The walkers' step
bodies live in the walker island**, the second part of `dbg_font_init` `0x800221CC…0x80022494`
(712 bytes, [text-renderer.md](text-renderer.md) § 6 candidate 2): `asm/vwf.asm` splits it at
`DEBUG_FONT_SPLIT` (`0x800222EC`) — the movie loader below ([movies.md](movies.md) § 8, 288
bytes, 228 used), the walkers above (424 bytes; 276 used by the shared lookup and eight bodies on
2026-09-23) —
and each half is an `.area`, so outgrowing one is a build error; the build prints where the
walker half's free space starts. The 620 bytes at `0x80012E04` are the movie hooks'.
Deadness is measured on one path: an execution breakpoint over the whole of `dbg_font_init` logged **0 hits** on the stock disc on PCSX-Redux through the title and card check,
the arrival sequence into free roam (14,000 frames from the first line), the help screen and
the item menu, while a control breakpoint on `glyph_draw` logged about 69,000
(`tools/vwf/island-watch.lua`, which `ISLAND_WATCH=1 tools/vwf/shoot-menus.sh
disc/image.cue` arms). It is not assembled under `ORIGINAL` (dead retail code has no stock
claim to check), and the manifest carries it as one SHA-1 (`walker_island`).

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

**The hand points right.** The select's hand is drawn by `0x80042B64` from `ONMEM.BIN`'s
sprite table (child 0, `{u, v, w in VRAM units, h}` on the 48 × 88 4bpp UI sheet, child 3;
the loader fixes up the page and CLUT). That drawer picks **sprite 0** — 24 × 16 at (0, 56),
the game's own right-pointing hand, the one the title menu and the file list show — when its
`a3` is non-zero, and **sprite 1** — 16 × 24 at (0, 32), pointing down — when it is 0; the
retail select passes 0 (`move a3, zero` at `0x8002C3D0`). The patch passes
`SEL_CURSOR_SIDE` = 1 there (`asm/select.asm`), so the rows get sprite 0 and `SEL_CURSOR_DX`
is −26 (its width + 2). Round 2 first did this by turning sprite 1 a quarter turn in the
sheet at build time; sprite 1 is shared, so every hand the game points **down** at a button
— the settings and load screens' もどる — pointed sideways at nothing (Jay, DuckStation,
2026-09-23). Nothing in `ONMEM.BIN`'s table or sheet is edited now, so every other hand is
the retail one (`tests/test_vwf_prototype.py` pins both). Proven on Beetle 2026-09-23: the
`E0112.1` select with the right-pointing hand on Yes and on No, and the settings and load
screens' hand over もどる pointing down as stock (`work/menus/`, reached with the pokes in
§ "Reaching the living room"). `--cursor down` passes 0 and keeps the stock hand, and
`sel_cursor_dx` follows the hand's width (−18) unless `--sel-cursor-dx` says otherwise.

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
**The stack elsewhere** (2026-09-23, Beetle, `tools/vwf/stack-watch.sh`: a sentinel from
level C up, the lowest changed byte — from C + 0x6000 for the scenarios that can change map):
free-roam walking 0x228 bytes deep, the controls-help
screen none past the fill's top, the insect box forced open (hub, notebook page, grid) 0x350,
the kite game 0x348, `MUSI` forced 0x320 (not a sumo depth: the screen shows the room
again before a bout, though the end state is still mode 7 with `g_arena_cur` at B), mode 15 forced (which runs on into the evening's dinner scene rather than a save
screen) **0xFB0 — 4,016 bytes, the same event-path depth as the arrival sequence** — and the
**item menu 0x3DC8, 15,816 bytes**. Walking and the dinner scene also write exactly `[C, C +
0x6000)`: `bg_swap_in`'s scratch on a map change, a separate run below the stack's.
The three left (2026-09-24, Beetle, a sentinel from C + `0x6000`): **a real save** — the
diary's bedtime prompt (0x308 deep) → Yes → the diary page → the card's own screens to "Save
complete" and "Continue the game?" — **0xFB0**, the same 4,016 bytes, reached on the diary
page (what the frames there hold is pixel data, a local buffer); **a sumo bout** — from
`./make.sh sumo-bout`'s state, the gong, a whole fight won and the next opponent up —
**0x2E8**, and leaving for the field writes `SUB.TIM` up to `STACK_REACH` (`asm/arena.asm`,
not the stack); **fishing** — casting, reeling, the catch title and its dismissal — nothing
below `0x801FFF00`, because the field runs on the scratchpad (below).

The item menu's depth is one frame: mode 4's update (`g_modes[4]`, `0x8004330C`) calls
`0x80042DDC`, which calls `0x80043608`, whose frame is `0x3CA8` bytes — a local buffer that a
49×79 VRAM rect at (910, 132) is copied through (`StoreImage` then `LoadImage`; Redux, a
breakpoint on the transfer setup `0x80054DDC`: `sp` `0x801FC288`, RAM `0x801FC2E8`). The
only other caller is `TAKO.OVL` (`0x8007F66C`, mode 6). Its bottom, `0x801FC228`, lies
inside the level-C scratch on this layout (above it on retail), but **the two never coexist**: the scratch is live only inside
`bg_swap_in` (`map_commit`, field mode 5), and this frame only inside modes 4 and 6, which are
level-B modes — `mode_set` puts `g_arena_cur` at B, and what they allocate from there ends
far below the frame (measured `g_arena_cur` at the end of each: the bag B itself, the insect
box `0x801C2F3C`, kite `0x801C4954`, 227,540 bytes under it; an overlay that allocated into
level C would need re-measuring). What must survive under it is `g_bg_save`, which ends at
C: 19,416 bytes below the frame on this layout, 32,820 on retail. `arena.asm`'s guard caps
the raise of C at 1,116 + 12,904 = 14,020 bytes, so the menu frame cannot reach C under any
raise the guard admits; the guard's binding constraint stays the field's 4,016.
Not measured: § "Not done". Under the full-translation estimate six maps pass `0x6400` by
up to 5,926 bytes
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
glyph_draw` / `glyph_draw_layer` in the executable and every overlay and resolves
the `a0` each passes — an immediate (`addiu/ori a0,zero,n`), or the digit pattern `addiu a0,r,0x34`
(ten ids), plus `sysmsg_draw`'s 13 → 14 remap. It follows every path back into the draw (branch
targets and delay slots; a return from a call, a jump-table entry or any other write to `a0`
makes the draw unresolved), so TITLE's save date, which sets its id twenty instructions early,
and `count_label_draw`'s two ids in branch delay slots are resolved. The 24 draws it cannot resolve
are each named with the arrays they walk, and checked against the site index, in
`tests/test_real_glyph_sites.py`, so a new computed-id draw fails a test. On this image that is 25 ids: 13, 14, 15, 40,
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
| `0x8002C3D0`, `D4`, `DC` | `select_cursor_update`, sprite | `move a3,zero` (sprite 1) · `addiu a1,a1,-2` · `addiu a2,a2,-0x18` | `addiu a3,zero,SEL_CURSOR_SIDE` · `SEL_CURSOR_DX` (−26) · `SEL_CURSOR_DY` (−2) |
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
| `0x8007D04C`, `50` | 18, the card screens' two answers (pen `s1`, id `lh 2·s0(s4)`) | `addiu s1,s1,0x30` (the gap, a jump's delay slot) · `addiu s1,s1,0xC` | `addiu s1,zero,0xAC` · `jal vwf_step_s1_answer`; SPLIT and COUNT (`0x8007D03C`, `64`) are the build's |
| `0x8008045C`, `68` | 20a, extras label 5 (pen `s1`) | `addiu s0,s0,2` · `addiu s1,s1,0xC` (in a branch delay slot) | `jal vwf_step_s1_s0_next` · `nop` |
| `0x80080790`, `A8`, `B0` | 20b, extras labels 0–4 | `addiu v1,s1,0xC` (next is a branch) · `addiu s1,v1,4` (lines 0, 3) · `addiu s0,s0,2` | `move v1,s1` · `move s1,v1` · `jal vwf_step_s1_s0_next` |

**Executable walkers** (`asm/walkers.asm`):

| RAM | walker | stock | patched |
|---|---|---|---|
| `0x8003539C`, `B0`, `C0` | 5a `text_draw_right` (help screen) | `addiu s1,s1,1` (count) · `addiu s2,s2,0xC` (delay slot) · `addiu s2,s2,-0xC` (draw) | `jal vwf_count_s2_s0` · `nop` · `jal vwf_back_s2_s0` |
| `0x80035490` | 5b `help_line_draw` | `addiu s1,s1,0xA` | `jal vwf_step_s1_s0_p10` |
| `0x80043834`, `48` | 12a `text_draw_line_h` (item, kite names; fishing) | `addiu s0,s0,2` · `addiu s1,s1,0xC` (delay slot) | `jal vwf_step_s1_s0_cur` · `nop` |
| `0x800438A4`, `B8` | 12b `text_draw_h` (descriptions, captions; fishing) | the same two | the same two |

**Free space**: `0x8005CD44…` (the PC-host island, [text-renderer.md](text-renderer.md) § 6) the
table, the select's variables and bodies; `0x80025120…` (the dead 8×8 font) the routines; `0x800222EC…0x80022494` (the upper part of `dbg_font_init`, dead)
the walker bodies.

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
  second line `【メモリーカードを抜かないで下さい】` — one walker, two pitches, keyed on the
  id. (This note first said that line kept its 12-px pitch; it was drawn at 14, 32 px wider
  than stock, until the 2026-09-22 walker bodies; now its pixels match the retail frame's.)
* **Continue with no card** (`beetle-title-no-file.png`, `redux-title-no-file.png`): "No file
  here" (message 4) proportional, the `!` book icon above. The extras entry shows the same
  message, so surface 20's screen is not reachable without a save.
* **Config** (`beetle-title-config.png`, `redux-title-config.png`): "Message / Tone / Pad /
  Rumble" at x = 40 and "On" at the stock line-4 x of 88, all proportional, hand cursor on line
  0; the right-hand panel (`音声＋字幕` …) is a texture. Line 1's stock 16-px letter-spacing is
  gone — with proportional glyphs it read as a mistake.

### The controls-help screen and the item menu (both emulators, `shoot-menus.sh`)

* **Help** (START in free roam): the fixtures "Move", "Up:Go", "Talk/Ex", "Jump/OK", "Skip
  VO" and the two bottom lines set proportionally at the pens of § "The fixed-pitch boxes";
  the untranslated lines (`左　右：向き`, `×：走る`, `△・□：サブ画面を表示` …) keep 12 px. Glyph
  0 of every line is at its stock x — `text_draw_right` is a left-align.
* **Items** (△, then ○ on the bag, day 1): "Exercise" in place of the radio-calisthenics
  card's name at x 40, proportional, the hand cursor beside it, the card's picture on the right as stock.
* **Card check**, rebuilt: the second line's ink map is identical to the retail frame's
  (compared column by column on Beetle), "Checking card" above it proportional.

The two emulators agree on all three.

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

### The fixed-pitch boxes

What an item of a menu array may hold is one row per line id (or `<array>.*`) in
[`data/text-boxes.tsv`](data/text-boxes.tsv): the x its walker starts it at and the column
`right` where its frame begins, the walker's stock `pitch` and the `lines` an item may take;
each line may advance `right − x` px, and a line's own row wins over its array's. `pitch`
is what the stock sheet — a font with no widths of its own — is measured at there (12; 10
on `help_line_draw`; 16 on the lines the stock walker letter-spaces). `lines` is more than 1
for an **E** item (`boku.layout.holds`), where `text_draw_h` breaks at `0x8001`, so the build
wraps the English to the box by pixels; and for the help screen's line 11, an **L** item
whose rows the build splits into items of their own (`boku.row_split`). Every other walker
draws one line. `boku.boxes` reads it; `boku lint` (`array-width`, `array-lines`), `boku build` and this
prototype's fixtures all refuse an item past it. Measured 2026-09-22 on Beetle screenshots of
the stock disc (frame edges) and read off the code (pens — `tests/test_real_boxes.py`
re-derives every pen from the game's bytes):

* **Controls help** (START, surface 5): 22 rows. Pens from `g_help_pos` (`0x80029904`) and
  `help_draw`'s literals. The screen is a diagram, not a box, so a line's room is its row:
  each box ends at or before the next pen on the same row for every pad type, or at 268
  (the help box `g_select_rect[6]` = 32…288, less the 20-px margin the retail lines keep)
  where the row is its own. `asm/walkers.asm` moves five pens and two labels so the English
  fits (each row's reason is its `basis`); `tests/test_real_boxes.py` checks the rows
  against the built game. The bottom sentence (lines 11-12, y 170 and 184, 14 px apart) needs
  three rows in English: the build splits line 11 in two (`boku.help_screen`,
  `boku.row_split`), its second row an item after the array's last, and moves line 12 to
  y 198; `asm/help_resident.asm`, called after `help_screen_draw`'s loop, draws that item
  at line 11's x where line 12 was, only when line 12 has moved. The help box runs to y 220.
  Seen on Beetle 2026-09-24.
* **Memory-card messages** (surface 17): pen 34, or 74 for the two lines layouts 5–6 draw
  (`g_mc_msg`); the panel's inner edge is 299. A record `{rows, layout, item[3]}` draws an
  item per row, 16 px apart, and the array is **L** (each item ends `0x8001`), so an item is
  one row. Every message is one row of at most 265 px: `.3` is worded to fit (Jay,
  2026-09-24, 245 px), seen on Beetle with a card whose 15 blocks are full, new game.
* **Config labels** (surface 19): pen 40 (line 4 at 84, moved from 88 by `asm/title.asm` so
  "(Vibration)" ends inside the frame); the left panel's frame at 149.
* **Item names** (surface 12, the bag): pen 40; the list panel's frame at 155.
* **Item descriptions** (surface 12, `text_draw_h`): retail pen (184, 126), three lines
  16 px apart; the white under the picture is rows 116–181 and the panel's inner edge is
  x 301. Jay's option c (2026-09-24): **five lines, 12 px apart, from y 118**
  (`asm/walkers.asm` `DESC_PEN_Y`, `DESC_LINE_STEP` — the newline in `text_draw_h` and the
  y both callers pass), so every line inks inside the white (a glyph at pen y inks rows
  y+1…y+12; `tests/test_real_boxes.py`). The build wraps the English to the box by pixels
  (`boku.layout.lay_out_array`), a `0x8001` at each break. Photo captions and the fishing
  messages (`fish_msg_draw`, the tackle box) use the same drawer and pen, so the same box;
  all three seen on Beetle (2026-09-24: five-line descriptions, a three-line caption,
  two- and three-line fishing messages — the tackle box opens from the desk, RIGHT from
  the bag, once `0x80035E52` is 1).
* **Summer-memories labels 0–4** (surface 20): pen 40 (`extras_draw`'s `addiu s1,zero,0x28`),
  the left panel's frame at 149, as the config screen's. **Label 5**, the quiz rate: pen 114
  (walker 20a's `addiu s1,zero,0x72`) in its popup, a tile at TITLE `0x80081AC4` that
  `asm/title.asm` widens to x 112…248.

Measured 2026-09-24 on Beetle (every row's `basis` says how):

* **Kite names** (surface 13, `kite_list_draw`): the list panel is the item list's (frame at
  155), but the names started at x 48, and "Carp-streamer Kite" (115 px) ran into the frame;
  `asm/walkers.asm` starts them at the item list's 40. Reached with `0x80047EC0` = 1 (the
  desk's kite gate), the kite count `0x80047EB0` and ids `0x80047EA8`, then △, UP, ○.
* **The tackle screen's words** (surface 14): "Tackle" and the record's heading at
  `fish_menu_draw`'s (40, 82) and (40, 170) in the list panel; the three fish words at
  `fish_word_draw`'s (178, 126) in the picture panel. The tackle screen opens from the desk
  (RIGHT from the bag) once `0x80035E52` (the rod) is 1.
* **The cage HUD** (surface 9, `cage_hud_draw`, the desk's Bug Cage): badge, name, gender
  icon and catch number on one row at y 26, starting at x 24, 49 (crown) or 61 (BIG!); the
  size right-aligned at y 45. The date, right-aligned on the name's row, was reached by the
  longest names' catch number ("Eyebrow Red Dragonfly", crown); `asm/walkers.asm` moves it a
  row below the size (y 64). Reached by writing an insect record into cage slot 0
  (`0x80045A10`: type, size, 0, gender, catch, day) and △, RIGHT, RIGHT, UP, ○.
* **The fish-catch title** (surface 11, `fish_name_draw`): a translucent panel x 112–207,
  y 56–119, the name on y 73; retail starts it at x 0x88 (0x82 for fish 1), which centres
  the Japanese on 154, and "Rainbow Trout" ran to 218. `asm/hud_resident.asm` centres any
  name on the panel's middle by its width. Fishing is `PROG 32` in the field (events
  `E0004`, `E4019`–`E4021`); reached by landing in A01 with `g_flags[10]` set, examining
  `E0004`'s spot, and writing the caught state into `0x8003E298` (+0 = 0x40, +9 = the fish,
  +0x11 = 1).

**The field's stack is the scratchpad.** Field mode's update (`g_modes[5]`, `0x80013770`)
moves sp to `0x1F8003E4`, the 1 KB scratchpad, and fishing runs there: sp was `0x1F8002C4`
inside the catch title's hook, and retail `fish_name_draw` reaches `0x1F8002BC` at its
deepest (Beetle probe, 2026-09-24). What else the field keeps in the scratchpad is not
mapped, so a hook called from field code takes no stack frame of its own: it keeps ra in a
register, as the walker bodies do.

### The banners

Two raw arrays are drawn a glyph per row down the middle of a tall panel: the fortune
(`exe@80036750`, four results of three cells, `fortune_draw`) and the kite crash (`tako@440`,
four cells, `tako_crash_draw`). English does not stack, so in English each is one line
centred on the retail column in a panel made wide and centred where the retail one was
(`boku.code_text.BANNERS` holds the geometry). `boku build` hooks the drawer's entry to
`asm/banners.asm` (as the date labels are hooked) only when the array is translated, writes
the items — each ended by `0x8000`, an untranslated one as its retail cells — anywhere
resident with the line's centre and y in front, and widens the panel in the same edits
(`fortune_panel_draw` reads its rect from `0x8003DA90`; `tako_panel_draw` builds it from four
`addiu v0,zero,n`). The
fortune routine still counts the three draws and leaves the count at `0x8003DD1D`, as the
retail drawer does. `tests/test_real_banners.py` runs both hooked drawers on the days
build; the box is `research/data/text-boxes.tsv`'s.

Proven with the real English by forcing each screen (`tools/vwf/shoot-menus.sh`, Beetle):
the crash by setting TAKO's state (`0x8003DE10`) to 2 while the kite flies, "Crashed!"
centred in the wide panel; the fortune — its event (`E0443`, map `A11`, `PROG 0`) was not
reached — by a trampoline that draws it every field frame, "Great Luck!" centred in the
panel. The same trampoline on Redux, from a breakpoint,
drew "Great Luck!" and "Terrible Luck!" in the `A11` shrine.

### Screens behind a save (2026-09-23)

Reached on both emulators with generated cards (`./make.sh saves`,
[save-format.md](save-format.md) § "Reaching the scenes other lanes asked for") and
`tools/vwf/shoot-menus.sh`:

* **"Load this file?"** (the day-5 card): the question is message 9 (surface 17, proportional
  as fixtures allow), with the card screen's two answers below it — surface 18, § "The
  card screens' two answers".
* **Summer memories** (a card whose day reads 31): labels 1, 3, 4 as the fixtures
  "Insects", "Item", "Ending", proportional at x 40; labels 0 and 2, untranslated, at the
  stock 12. Line 0's stock 16-px letter-spacing is dropped with the rest.
* **The bag with items** (free roam, △ then ○, then the list poked to items 1–3 once the bag
  is open: `run_core.py --poke`, or `tools/vwf/bag-items.lua` on Redux — the bag rebuilds
  the list as it opens, so a poke before that is lost): "Crackers", `斧`, "Bang" at 16-px
  rows, and item 2's description "Sharp. / Not for / kids." in three lines at (184, 126).

* **The quiz rate** (label 5, walker 20a, with the day count and percentage under it): a
  popup over the summer-memories menu that `0x80080810` draws only while the word
  `0x80025938` is 1 and toggles on a pad bit. The only store to that word by address in the
  executable or any overlay is a `sw zero` at `0x80011FF0` (`MUSI`, `TAKO`, `BUMPER` and
  `TITLE` only load it), so in retail the popup is probably unreachable; both the word and the
  popup's byte flag `0x800820DC` are written (`shoot-menus.sh`; `tools/vwf/word-pokes.lua`
  on Redux). "Quiz rate" set proportionally at (114, 80) on both emulators.
## The fixed-pitch surfaces

Every horizontal surface of [text-renderer.md](text-renderer.md) § 3 rows 5–26, read again at
the instruction level (2026-09-20, `work/txt01/d`; the R3000 rules: one load-delay slot, one
branch-delay slot; every function here saves `ra`). Decision: **A** = route through the width
table with a `jal` hook; **B** = keep the fixed pitch; **C** = untouched, the surface never draws
Latin from the re-aligned range (immediates, digits, one-glyph rows). Status: **proven** = on
screen on both emulators; **assembled** = in `asm/` and checked against the retail bytes, screen
not reached; **tested** = hooked, and the walker run instruction by instruction on the patched
executable (`tests/test_real_walkers.py`), screen not reached; **table** = this row is the whole
specification.

| # | image · function | step instruction (stock) | pen · id | decision | status |
|---|---|---|---|---|---|
| 5a | EXE `text_draw_right` `0x80035360` — not right-aligned: a count pass steps `s2 += 12` per glyph, then the draw pass walks the line backwards, `s2 −= 12` before each draw, so glyph 0 lands at x | `0x8003539C addiu s1,s1,1` (count; id at `-2(s0)`, delay slot `lh v0,0(s0)`) · `0x800353B0 addiu s2,s2,0xC` (branch delay slot) · `0x800353C0 addiu s2,s2,-0xC` (draw; id at `0(s0)`, delay slot `lh a0,0(s0)`) | `s2` · `s0` | **A**: `539C → jal` {`s2 += w[-2(s0)]; s1 += 1`}, `53B0 → nop`, `53C0 → jal` {`s2 −= w[0(s0)]`}; the bodies must not write `v0`/`a0` | **proven** |
| 5b | EXE `help_line_draw` `0x80035448` (pitch 10) | `0x80035490 addiu s1,s1,0xA`; delay slot `addiu s0,s0,2` so the id is at `-2(s0)` in the body | `s1` · `-2(s0)` | **A**, body `vwf_step_s1_s0_p10` (stock 10) | tested (only pad type 2, whose labels are `Ｌ２`/`Ｌ１`, draws it; the shots were pad type 0) |
| 6 | EXE `date_label_draw` `0x80037544` | none: five immediates at `x, x+0xD, x+0x25, x+0x3A/0x41` plus sprite digits | — | **C**; a translation re-points the ids and re-tunes the literals | table |
| 7 | `date_label_draw_b` | unreferenced | — | **C** | table |
| 8 | EXE `count_label_draw` `0x800377F8` | none: `0x26A`, `0x4B9` at offsets chosen by digit count | — | **C** | table |
| 9 | EXE `sysmsg_draw` `0x800379EC` (insect names, system words; wrapper `sysmsg_line_draw` `0x80037BA8`) | `0x80037B20 addiu s3,s3,0xC` (delay slot `lhu a0,0(s0)`); `0x80037B3C addiu s2,s2,1` is the glyph count, **returned in `v0`** | `s3` · `-2(s0)` | **A with the contract change, installed** (`asm/walkers.asm`): both passes add the glyph's width to `s2`, so the return value is pixels, and the five consumers take it — the cage HUD and HHON's label (`move v1,v0`), MUSI's stat line, and MUSI's two right-aligned names at `SUMO_FIELD − width` (the `sllv … s5` block: `s5` is 1, set at `0x8007D7C8`, so both were 12 × (8 − n); the count comes from drawing the name off screen at x 0x258 first). The down pass (`a3` ≠ 0) is left stock: no call in any image uses it. The cage HUD's date moves a row down, off the name's row (EXE `0x8003FFF8`, HHON `0x8007C4CC`) | **proven** on Beetle (the cage HUD, the insect box's copy and the bout's names, 2026-09-24) |
| 10 | EXE `fortune_draw` `0x8003A7A4` (the fortune result, three glyphs stacked vertically at x `0x9A` in a tall panel) | rows, not a pen | — | **banner**: hooked at its entry to `asm/banners.asm`'s `vwf_fortune_banner`, one centred line in a wide panel (§ "The banners") | **proven** (forced) |
| 11 | EXE `sys_title_draw` `0x8003C5EC` (fish names `0x8003DA4C`) | `0x8003C6A0 addiu s1,s1,0xC` (delay slot `lhu a0,0(s0)`); the pen, `0x8003C68C sll s2,v0,0x10` → `jal vwf_fish_title_x`, which centres the name in the catch panel by its width | `s1` · `-2(s0)` | **A**, body `vwf_step_s1_s0` | **proven** on Beetle (2026-09-24, forced catch) |
| 12a | EXE `text_draw_line_h` `0x800437F4` (item names, kite names, fishing at x `0x28`/`0xB2`) | `0x80043848 addiu s1,s1,0xC` is a branch delay slot; `0x80043834 addiu s0,s0,2` is the hook site, with `lhu v0,0(s0)` in its delay slot loading the *current* id | `s1` · `0(s0)` | **A**: `43834 → jal` {`s1 += w[0(s0)]; s0 += 2; lhu v0,0(s0)`}, `43848 → nop` | **proven** (item names) |
| 12b | EXE `text_draw_h` `0x80043864` (item descriptions and captions at (0xB8, 0x7E), newline `s2 += 16`; patched to (0xB8, 118) and 12, § "The fixed-pitch boxes") | same shape: `0x800438A4 addiu s0,s0,2` (delay slot `lhu v1,0(s0)`, also the newline operand), `0x800438B8 addiu s1,s1,0xC` in a branch delay slot | `s1` · `0(s0)` | **A**: as 12a with `v1` reloaded; one body, `vwf_step_s1_s0_cur`, serves both | **proven** (descriptions) |
| 13, 14 | `kite_menu_draw`, the fishing drawers | draw through 12a/12b | | with 12 | tested |
| 15 | `TITLE 0x8007BB60` (save date) | none: `0x3C` at `s1`, `0x1B8` at `+0xC`, digits, `0x157` at `+0x30` | — | **C** | table |
| 16 | `TITLE 0x8007C8EC` (slot digits, `0x5B0`) | none | — | **C** | table |
| 17 | `TITLE 0x8007CB54` (memory-card messages; `0x8007CC4C` is inside it, not a second walker) | `0x8007CDD8 addiu s5,s5,0xC` | `s5` · `-2(s0)` | **A** | **proven** |
| 18 | `TITLE 0x8007CF7C` (card-screen yes/no, 5 raw glyphs at `0x80081480`) | `0x8007D050 addiu s1,s1,0xC`; after glyph index 1 (`0x8007D03C addiu v0,zero,1`) the step is `+0x30` (`0x8007D04C`) — the word gap | `s1` · `lh 2·s0(s4)` | **A**, with the build: `0x8007D050 → jal vwf_step_s1_answer` (id fetched by index), the gap `0x8007D04C → addiu s1,zero,0xAC` (the second answer starts where the stock one did), and the split and count rewritten from the translation — § "The card screens' two answers" | **proven** |
| 19 | `TITLE 0x8007FA94` (config) | `0x8007FBC4 addiu v1,s0,0xC` | `v1 = s0 +` · `-2(s1)` | **A** | **proven** |
| 20a | `TITLE 0x800803D8` (extras label 5) | `0x80080468` in a branch delay slot; hook at `0x8008045C addiu s0,s0,2` | `s1` · `-2(s0)` | **A** | **proven** (forced) |
| 20b | `TITLE 0x80080680` (extras labels 0–4) | `0x80080790 addiu v1,s1,0xC` is followed by a branch; hook at `0x800807B0 addiu s0,s0,2`; lines 0 and 3 letter-spaced by `0x800807A8` | `s1` · `-2(s0)` | **A** | **proven** |
| 21 | `TITLE 0x80080484` (extras numbers `／ 3 1 ％`) | none | — | **C** | table |
| 22 | `TAKO 0x8007C684` (crash banner, 4 glyphs stacked vertically) | rows | — | **banner**: `vwf_crash_banner`, as row 10 | **proven** (forced) |
| 23 | `MUSI 0x8007C604` (button hint, 7 glyphs, bound `slti 7`) | x recomputed from the index: `0x8007C700 sll a1,a1,2` + `addiu a1,a1,0x78` | index | **banner**: `vwf_sumo_hint` (asm/musi_text.asm) centres the line and widens the board, hooked at the entry by the build | **proven** (Beetle) |
| 24 | `MUSI 0x8007EDB0` (strength labels, 3 rows × 3 cells) | x from the index at 16 px (`0x8007EE1C`) and 12 px (`0x8007EE78`), bounds `slti 2`/`3` | index | **banner**: `vwf_sumo_rank` centres each row on x 108, hooked at the entry | **proven** (Beetle) |
| 25 | `MUSI 0x80084F64` (move names) | `0x800850A0 addiu s1,s1,0xC` (delay slot `lhu a0,0(s0)`) | `s1` · `-2(s0)` | **A**, body `vwf_step_s1_s0` | tested; unreachable in retail (debug overlay only: sumo.md § The desk's text) |
| 26 | `MUSI 0x800850D8` (move names, second list) | `0x80085208 addiu s1,s1,0xC` (delay slot `lhu a3,0(s0)`) | `s1` · `-2(s0)` | **A**, the same body | tested; unreachable in retail (no caller) |

Counts: **A** 13 surfaces (5a, 5b, 9, 11, 12a, 12b, 17, 18, 19, 20a, 20b, 25, 26; 13 and 14
ride on 12), of which 8 proven (5a, 12a, 12b, 17, 18, 19, 20a, 20b), 5 tested (5b, 9, 11,
25, 26 -- the last two unreachable in retail); **banner** 2 (23, 24, proven on Beetle);
**C** 8 (6, 7, 8, 10, 15, 16, 21, 22). The "six copies of one walker" are not
register-identical — pens `s3`, `s5`, `v1`+`s0`, `v1`+`s1`, `s1`, `s1`; id pointers `s0` or
`s1` — so the bodies are per shape and per stock pitch (`asm/walkers.asm`, the walker island;
§ "The free space").

## The card screens' two answers (surface 18, 2026-09-23)

`title@7A78.0` is five raw glyphs, はい then いいえ, with no control word: the drawer
(`TITLE 0x8007CF7C`) draws glyphs 0…COUNT−1 from x 0x70, and after glyph SPLIT jumps to the
second answer. SPLIT (`addiu v0,zero,1` at `0x8007D03C`) and COUNT (`slti v0,v0,5` at
`0x8007D064`) are code constants, so how English divides the row is decided where the English
is: the translation writes it `Yes | No` (Jay's ruling via the orchestrator, 2026-09-23:
the translation files are the only interface between script and build), and `boku build`
lays both answers into the row's cells and rewrites the two words
(`boku.layout.ANSWER_PAIR`, `answer_pair_code`; `boku.build.answer_pair_patches`, each edit
checked against the retail word). The renderer patch (`asm/title.asm` surface 18) restates
neither: it routes the step through the table and starts the second answer at 0xAC, where
the stock one began, so the hand cursor, which the game places by answer, still points at
it. Untranslated, both constants keep their stock values and はい / いいえ draw exactly as
before. Each answer is measured in its span — the first up to 0xAC, the second up to the
card panel's edge (299) — and together they share the row's five cells.

Proven with the days build (the real `arrays.txt` row) on both emulators, "Load this
file?" with the day-5 card: "Yes" from x 112, "No" from 172, the cursor moved to "No" by
RIGHT and pointing at it.

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

`HHON.OVL` is the insect box
(mode 10). Its two walkers draw an item of `hhon@5328` — one entry per insect id, item 60
the unseen placeholder; an **E** array, so `0x8001` breaks a line — down columns right to
left (y += 12 a glyph; a break: x −= 14, back to the top):

| walker | screen | stock origin | the area the text sits on |
|---|---|---|---|
| `hhon_entry_draw` `0x8007C278` | the grid (`hhon_page_draw`): the entry of the insect under the cursor | columns from (0x124, 0x26); the placeholder from (0x100, 0x2C) | the cream panel at the right, x 214…310, y 12…172 (frame at 311) |
| `hhon_text_scroll_v` `0x8007C1C4` | the hub scrolled down to its notebook page: the entry of the insect in the selected cage slot | columns from x 0x5A (0x32 for the placeholder), y hanging from the scroll (54 at the page) | the page, x ~18…106 (then the specimen box), y 54 to the count digit near 160 |

**Installed (2026-09-24), Jay's layout** (`work/review/decisions.html` § 1): English is
drawn in rows, Japanese in its retail columns, chosen once per entry by its first glyph
(`asm/hhon.asm`, bodies in `asm/hhon_resident.asm`, the mode in `vwf_hhon_rows`). In an
English entry every cell steps x -- by its width, or the sheet's 12 for a cell with none,
such as the sex marks of "Miyama Stag Beetle ♂" -- and every break starts a row, an empty
one included. An untranslated entry is drawn exactly as retail draws it
(`tests/test_real_walkers.py` compares the two).

* **The grid** (option A): the whole entry, rows 11 px apart from (218, 16), 92 px wide to
  x 310 (`research/data/text-boxes.tsv`, 14 rows). The longest entry at that width is 14
  rows ("Chinese Peacock…"), whose last row inks to 171, above the panel's foot.
* **The notebook page**: what its 8 rows hold, 12 px apart from x 16 on the same 92 px
  (to 108; the paper shades from 110), ending with "..." when the entry goes on
  (`boku.insect_box.notebook_words`: the eighth row keeps what fits beside it). The full
  text is on the grid, one button away.
* **The bytes**: the English is about 2.5× the Japanese (13,700 bytes whole, 12,070 cut),
  so the build writes two copies into `HHON.OVL`'s tail (`boku.array_relocate`), and each
  screen's `lui` pair (`boku.insect_box.GRID_PAIR`, `NOTEBOOK_PAIR`) is pointed at its own.
  `HHON.OVL` grows from 27,660 bytes to 53,468 and moves on the disc.
* **Words wider than the line** ("Min-min-min-min,", "Tsukutsuku-boshi.", up to 113 px)
  break after a hyphen between two of their letters (`boku.layout.wrap`); a word that fits
  is never split.

Seen on Beetle (2026-09-24): entry 0 on both screens, entry 2 (13 rows on the grid, cut to 8
with "..." on the page) and entry 3 (14 rows).

**Reaching it.** In play the box needs a caught insect; poking the cage slot at
`0x80046F28` alone, live or through a card, drew nothing. Both emulators force it the way
`tools/redux/book-pokes.lua` does (`GFX-05`): `mode_set(10)` — the mode byte pair
`0x800237E0/E4`, the previous mode `0x800237E5`, the change flag `0x80024728`, and the arena
word `0x800258E0` from the mode's `g_modes` record, which the map-area raise moves, so it is
read from each image's RAM — with insect 0 given book state 2 (`0x8003DF92`; book-pokes.lua's
legend: 0 unseen, 1 seen, 2 caught) and put in cage slot 0. On Beetle the hub's pad works:
DOWN scrolls to the notebook page; the grid opens by writing its sub-state (`0x80080600` =
`0x11`) once the hub is up (○ on the specimen box did not open it). On Redux the pad does
not register in mode 10, so the scroll (`0x800805DC` = 200) and the grid are written too.
`tools/vwf/shoot-menus.sh` shoots both screens on both emulators.

The delete prompt (`hhon@6874`, "Delete it?") is sub-state `0x18` of the same word (the
state table at `0x8007E850`). The diary's bedtime prompt (`ZUKAN.OVL`'s `zukan@32E8`) is
reached by forcing mode 11 the same way and writing state 200 (`0xC8`) to `0x800459DC`;
both seen in English on Beetle, drawn from their overlays' tails.

## Not done

* **Summer memories' label 5** is proven only by forcing its popup, which retail probably
  never shows (§ "Screens behind a save", the quiz rate). **`HHON`** is seen on Beetle only
  (§ "The `HHON` walkers"). Surfaces 25 and 26 and the debug screen's names are unreachable
  in retail ([sumo.md](sumo.md) § The desk's text). (SELECT on Beetle was reached on
  2026-09-20 through the day-1 living-room route, `work/txt05b/shots/06`.)
* **Kerning, bearings, glyphs wider than 12**: none; the dialogue's nine slots are full and the
  bodies add only the table byte.
* **Text that grows**: everything is written in place — which is why `--days` writes 67 lines
  of 764 (§ "The reviewed translation, in place"); relocating and re-lengthening text is the
  pipeline's (`PIPE-03`/`PIPE-04`), and re-authoring the `0x8002` operands is the inserter's.
  The space-padding of array items is a consequence of writing in place and goes away with it.
* **The speaker label** is done in the pipeline build (§ "The speaker label"); the
  prototype's own `--days --label` path still writes the older "Boku: " form.
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
* Free-roam, menus and sumo were not sampled for primitive-buffer headroom (§ Q4). The stack
  was (§ "The map work area").
* Confirmed on emulators only; EDC/ECC is regenerated and self-checked, but no disc was burned.
