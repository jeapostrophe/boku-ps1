# The dialogue renderer patch, prototyped (PLAN `TXT-05`; measurements for `TXT-07`)

A working proportional, horizontal dialogue renderer: armips source applied to a copy of the
contributor's image, booted headlessly on PCSX-Redux and on Beetle PSX, and looked at.
**Measured** = read off a build or a screenshot made on 2026-09-20 with the tools named here;
the screenshots are the game's pixels, so they stay in the gitignored `work/txt05/` and are
described, not shown. Scope is the **dialogue surface only** — `msg_open` → `dialog_open` →
`dialog_draw` → `glyph_draw`, plus the ant-count message, the one other caller of `dialog_open`.
Engine facts are cited from their homes: [text-renderer.md](text-renderer.md) (the walker, the
9 slots, free space), [renderer-runtime.md](renderer-runtime.md) (what the emulator confirmed),
[font.md](font.md) (the sheet), [font-candidates.md](font-candidates.md) (advance models, free
cells, the mock-ups this is compared with).

Nothing here takes `TXT-03` or `TXT-06` from Jay: pen, band, line pitch and glyph gap are build
arguments, and the typeface is an input file.

## Build and look

```sh
uv run python tools/vwf/build_prototype.py     # -> build/vwf/image.cue, manifest.json, files/
tools/vwf/shoot.sh                             # both emulators -> work/txt05/shots/*.png
```

`build_prototype.py --help` lists the layout arguments (`--pen-x --pen-y --line-pitch --band-y
--band-h --gap`), `--font FILE`, `--lines FILE` and `--asm FILE`. It needs armips
([tooling-setup.md](tooling-setup.md)); `shoot.sh` needs the emulator variables documented there.
The build reads the import under `disc/` and never writes there.

| tracked file | what it is |
|---|---|
| `asm/dialogue.asm` | the patch; every site carries the retail instructions as an `ORIGINAL` block |
| `tools/vwf/build_prototype.py` | sheet rebuild, advance table, armips, text, image writes, manifest |
| `tools/vwf/placeholder-glyphs.txt` | seven placeholder cells (space `' " - ( ) ~`) and the glyph-file format |
| `tools/vwf/prototype-lines.tsv` | which sample line or layout fixture goes over which arrival-sequence line |
| `tools/vwf/shoot.sh` | the two headless runs and the frames worth keeping |

## Design

**The advance lives in the nine slots, in place; no trampoline.** `dialog_draw` spends
`0x8002BF5C…0x8002BF7C` re-reading `g_text_flags` to choose `y += 13` or `x += 14`. With every
caller horizontal that test is dead, and nine instructions are exactly enough for a table lookup
**once the R3000's load delay is respected** — which the 8-instruction sketch in
[text-renderer.md](text-renderer.md) § 4b does not (it uses `v0` in the instruction after
`lhu v0`, and `v1` straight after `lbu v1`). The version that fits fetches the table byte
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

**The table lives in the heap-raise gap**, `0x8008F3A4…0x8008F7FF` (1,116 bytes, already inside
the file, above every overlay): one data word moves the heap's first byte to `0x8008F800`. Chosen
over the dead-code islands because it is the only candidate whose deadness was *measured* with
write-breakpoints rather than inferred from missing references ([renderer-runtime.md](renderer-runtime.md)
§ Q5), it is one contiguous `.area`, and it costs nothing but 1.1 KB of heap. This build's table is
**793 bytes** (`vwf_advance` = `0x8008F3A4`); the gap is free again from `vwf_free` =
`0x8008F6C0` (320 bytes). The islands stay untouched for the hooks the other surfaces will need.

**No cell the Japanese script draws is touched.** [font-candidates.md](font-candidates.md) § 7
accepted re-aligning Latin cells in place as "cosmetic" for the ten letters, the digits and the
punctuation untranslated lines use. That is avoidable, so the build avoids it: an English
character keeps its own cell only when that cell is in the free list of
[font-candidates.md](font-candidates.md) § 1 (parsed from that file, not copied); every other
character — `A B C L M P T X Z z`, the digits, `. : ? ! / + %`, and the seven glyphs the sheet
lacks — is drawn into a free cell. 87 characters: 53 in place, 34 in free cells (the junk symbols
`゛ ‘ ’ ± ÷ ￥ → ← ↑`, nine unused kana, then unused kanji from 292 up to 792, which is what makes
the table 793 long). Table entries for every other id are 14. A build-time gate walks all text
sites of the import and refuses if any of them draws a cell about to change. Consequences:
untranslated dialogue, the code-drawn digits (`52 + n`) and the 20 fixed-pitch surfaces look
exactly as they did, and **the English space is its own blank cell** (id 10, advance 4) — id 0
stays the 14-px Japanese space and indent cell. The inserter must therefore encode English through
the character map the build emits (`manifest.json` → `cells`), not through NFKC of
`data/glyph-table.tsv`.

**The font is a build input.** A glyph file is `glyph U+XXXX advance N` plus twelve rows of
twelve `.`/`#`, ink starting at column 0 (`tools/vwf/placeholder-glyphs.txt` is one). With no
`--font`, glyphs are the game's own Latin cells read from the contributor's `ONMEM.BIN`, shifted
to column 0, advance = ink width + `--gap` (1), plus the placeholder file. With `--font`, that file
supplies every glyph; cell allocation, table and asm are unchanged. A baker for an OFL face
(`TXT-06`) only has to write that format. The rebuilt sheet (`build/vwf/files/font-sheet.tim`) is
disc-derived and never tracked.

**`ORIGINAL=1` checks the comments.** Each site in `asm/dialogue.asm` has two arms: the patch,
and the instructions the retail file holds there. The build assembles the `ORIGINAL` arm first and
refuses unless the executable comes back byte-identical, so a wrong "stock:" line is a build
error, not a stale comment. Made red on purpose: `0x16` → `0x17` at `msg_open` reports "first
difference at RAM 0x8002CFC8". Other gates made red the same way: a 1,200-byte table ("Area at
8008f3a4 overflowed by 84 bytes"), an English line larger than its site, a page count that
differs from the original's, a free list that wrongly includes id 4.

## The patched sites

21 words of `SCPS_100.88` plus the table, in eight `.area`s (the newline pitch is an area whose
default leaves its word unchanged). RAM addresses; file = RAM −
`0x8000F800`.

| RAM | function | stock | patched |
|---|---|---|---|
| `0x8002CFC4`–`CC` | `msg_open` | `addiu a0,zero,0x129` · `addiu a1,zero,0x16` · `addiu a2,zero,1` | `PEN_X` (24) · `PEN_Y` (176) · `0` = horizontal |
| `0x8003206C`, `74`, `78` | ant-count message | the same three literals (`0x80032070 addiu v0,v0,0x34` between them is restated unchanged) | the same three values |
| `0x8002911C` | `g_dlgbox_x` (`s16`) | 260 | −5: tile 330 wide, fade off-screen |
| `0x8002EA34`, `38`, `44`, `48` | `dialog_panel_draw` | `addiu s1,zero,0xF0` · `sh zero,0xA(s0)` · `addiu v0,v1,5` · `sh v0,8(s0)` | `addiu s1,zero,BAND_H` · `sh zero,8(s0)` · `addiu v0,zero,BAND_Y` · `sh v0,0xA(s0)` — `band2` |
| `0x8002BF48` | `dialog_draw`, newline | `addiu s1,s1,0xD` | `addiu s1,s1,LINE_PITCH` (13: unchanged bytes by default) |
| `0x8002BF5C`–`7C` | `dialog_draw`, advance | `lui v0,0x8003` · `lw v0,0x59E4(v0)` · `nop` · `andi v0,v0,0x10` · `beqz v0,+3` · `nop` · `j 0x8002BF80` · `addiu s1,s1,0xD` · `addiu s2,s2,0xE` | the nine instructions above |
| `0x80068AF0` | heap bump pointer, initial value | `0x8008F3A4` | `0x8008F800` |
| `0x8008F3A4`… | (zeros) | | `vwf_advance`: `u8` per glyph id, `TABLE_IDS` entries |

`g_text_flags & 0x10` still selects the newline rule at `0x8002BF1C`, but no longer the advance: a
caller passing `vertical = 1` would now draw garbage. The two callers patched above are the only
ones in any image ([text-renderer.md](text-renderer.md) § "Answers first").

On the disc the build changed 17 sectors: 7 of the executable, 6 of the font TIM (`ONMEM.BIN`
child 2 starts at `BOKU.BIN + 0x5F94AA0`), 4 of text. Every range is compared with the import's
bytes before it is replaced, every text site is re-hashed (`boku.text.check_placement`), every
written sector gets fresh EDC/ECC and is re-verified, and `manifest.json` lists them.

## What is on the disc, and why those lines

The prototype writes **in place**, so a site takes whichever sample line fits its bytes and has
its page count; the English is from `translation/samples/` but is not the translation of these
sites. `E0171.0` (44 bytes) holds 21 characters — "Whoa, that's amazing!" fits exactly, no label.
Arrival-sequence sites are 22–152 bytes for 1–2 pages, so the longest real page possible is 41
characters; wrap, overflow, line count, digits and the new punctuation are exercised by three
labelled fixtures. `E0177.0` and everything from `E0179` on are left Japanese on purpose.

## What the screenshots show

Both emulators, same image (`799e4536…`), frames in `work/txt05/shots/` (`beetle-*` are
320×240 native; `redux-seq-*` are PCSX-Redux's downscaled capture, state-relative frame numbers).
The two agree in every frame compared.

* **Proportional spacing is right.** "Boku: Okay, Uncle. I understand." and "I would never, ever
  do a thing like that." read as set type: `i`/`l` take 2 px, `m`/`w` 10, no collisions, no
  floating letters. Measured on Beetle, the wrapped line "Aunt: What syrup do you like on your
  shaved" has ink from x = 24 to x = **291**; the build predicted 269 px of advance, i.e. last
  ink at 24 + 269 − 2 = 291. **Exact.**
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
  (c2)): same glyphs, same band, same pen, and the same widths to the pixel —
  `fonts.game_font('realigned').width()` gives 269 / 228 / 127 for the three lines the build
  measured at 269 / 228 / 127. Differences: the real frame has the pencil (not in the mock-ups);
  the placeholder punctuation was redrawn, so `' " - ( ) ~` differ by a pixel or two; and one thing
  the mock-up also shows but does not call out — **`...` reads as a short dash**, because each
  2-px dot's shadow fills the 1-px gap to the next. A font-metric matter (`.` advance 3 → 4), left
  alone here because the typeface is `TXT-06`'s.

Most informative frames: `beetle-E0174.0-wrapped.png`, `beetle-E0175.0-overflow.png`,
`beetle-E0171.1-page1-arrow.png`, `beetle-E0177.2-five-lines.png`, `beetle-E0182-japanese.png`,
`redux-seq-01720.png`.

## Measurements for `TXT-07` (dialogue, `band2` at Y = 168, H = 72, pen (24, 176), pitch 13)

* **Band**: rows 168–239, the full 320 px, flat (224,224,224) on Beetle.
* **Usable width**: 272 px with the left margin mirrored (what the builder wraps to); 296 px to
  the screen edge.
* **Characters per line**: the sample lines written average **5.85 px per character → 46 per
  272-px line**; the fullest real line is 43 characters in 269 px. (Mock-up estimate: 43.6
  wrapped.)
* **Lines per page**: line *n* has ink rows 177 + 13(n−1) … +9 for caps, +1 for the shadow.
  **Four lines are clean** (last shadow row 225). A fifth draws completely (ink 229–237, shadow
  238) but sits on the bottom edge, inside any CRT's overscan. The pencil occupies x ≥ 267 on rows
  220–229, so **a fourth or fifth line must end before x ≈ 262** on any page that can show it;
  three lines never meet it.
* **A line that is too long is clipped at the right screen edge, silently.** The 56-character
  fixture (345 px) draws to x = 319 and the rest is simply not there: no wrap, no wrap-around to
  the left, nothing else disturbed. The engine has no wrap logic, so the inserter must break
  lines and a lint must measure them in pixels with this table.
* **Primitive cost** is unchanged per glyph (3 × `SPRT`); the longest page here is 56 glyphs.

## Not done

* **SELECT menus** (`select_draw`): still vertical, fixed 12; needs a real hook (no spare slots).
* **The `HHON` walkers** (two vertical walkers in the overlay).
* **The 20 fixed-pitch surfaces and the arrays behind them**: untouched, and still pixel-identical
  because no Japanese cell moved. When they are translated they will use the left-aligned English
  cells at a fixed 12-px step and look gappy until each gets its own advance.
* **Kerning, bearings, glyphs wider than 12**: none; the nine slots are full.
* **Text that grows**: everything is written in place; relocating and re-lengthening text is the
  pipeline's (`PIPE-04`), and re-authoring the `0x8002` operands is the inserter's.
* **The speaker label** is inline plain text here ("Boku: "); how it is drawn is undecided.
* **The translucent band and the 46-row band** are reachable (`--band-y 194 --band-h 46 --pen-y
  198`; the fade entry is two data words not in the asm) but were not shot.
* `make.sh` has no verb for this; the build lives outside `boku/` while that package is in flux.

## Open risks

* The heap gap was watched through boot, title and the arrival sequence only
  ([renderer-runtime.md](renderer-runtime.md) § Q5): `MUSI`/`HHON`/`ZUKAN`/`TAKO`, a save and a full
  day are unwatched. A write into the table would show as wrong spacing, not a crash.
* The free-cell list covers text sites, arrays and known code immediates; the build's own gate
  re-checks only text sites. The 23 computed-id `glyph_draw` sites ([font.md](font.md)) are
  covered by neither.
* Free-roam, menus and sumo were not sampled for primitive-buffer headroom (§ Q4).
* Confirmed on emulators only; EDC/ECC is regenerated and self-checked, but no disc was burned.
