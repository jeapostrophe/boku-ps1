# The text renderer — from a message id to pixels (PLAN `TXT-01`, static half)

Read from the code of `SCPS_100.88` and the seven overlays; nothing here was run. **Measured** =
read in the disassembly/decompilation of this dump; *hypothesis* = inferred, and says so. RAM
addresses throughout (EXE file offset = RAM − `0x8000F800`; overlay file offset = RAM −
`0x80079A08`); names are ours and are listed in
[`symbols/text-renderer.symbols.tsv`](symbols/text-renderer.symbols.tsv). The font sheet and
`glyph_draw`'s texel arithmetic are in [font.md](font.md); the text words and event blocks in
[text-format.md](text-format.md). Scratch and scripts: `work/txt01/` (`d` disassembles, `x` lists
`jal` sites in the EXE + all overlays, `rf` lists `lui`-pair references to an address range,
`dc`/`dco` decompile through a private Ghidra project).

## Answers first

* **Direction is an argument, and for dialogue it is a constant at the call site.**
  `dialog_open(x, y, vertical, text)` (`0x8002BD30`) stores `vertical << 4` into `g_text_flags`
  bit `0x10`. It is the *only* writer of that bit in the EXE and all overlays (`text_reset`
  clears the whole word). It has two callers and both pass the literal `1`:
  `msg_open` (`0x8002CFCC: addiu a2,zero,1`) and the ant-count message (`0x80032078`). No table,
  no script operand, no per-box field. Origin `(297, 22)` is a pair of literals beside it.
* **Nothing else goes through that walker.** Every other surface calls `glyph_draw` from its own
  loop with its own hard-coded advance. 26 surfaces (table below): **4 vertical** — dialogue,
  SELECT choices, and the insect book's two walkers in `HHON.OVL`; 20 already horizontal at a
  fixed 12 px (one at 10, one at 14/16); 2 are one-glyph-per-row lists. `sysmsg_draw` also takes
  a direction argument, and every call site read passes horizontal.
* **The dialogue "box" is not a box**: it is a 60-px-wide full-height strip down the right edge
  (`dialog_panel_draw`), sized for exactly 3 columns. Horizontal text cannot go "inside the same
  box"; the strip has to be redrawn as a band (three immediates and one data word).
* **There is no page logic in code.** No glyph cap, no column cap, no wrap. A page is whatever
  lies before the next `0x8002`/`0x8000`; "3 × 16" is an authoring convention that fits the strip.
  The whole page is re-emitted every frame; there is no typewriter effect.
* **The advance is two literals in `dialog_draw`** (`addiu s1,s1,0xd` / `addiu s2,s2,0xe`), not a
  function return and not a table. A per-glyph advance fits **in place** in the 9 instruction
  slots the direction test occupies — no trampoline needed for the advance itself.

## 1. Data structures

### `g_text` — the text context, `0x800359E0`, `0x18` bytes (measured)

Statics in BSS, zeroed by being in the file's zero region; `text_reset` (`0x8002BC5C`) initialises
it and is called from `event_state_reset`, the `select_open`/`select_run_ptr` exits, and two
other sites (`0x8002FB70`, `0x80041F34`). Every reference in the EXE and overlays was enumerated (`rf 800359e0 800359f8`): all
accesses to `+0…+0x14` are inside `0x8002BA44…0x8002BF90` plus four flag *reads* in the event
code. **No overlay touches it.**

| off | RAM | type | name | |
|---|---|---|---|---|
| +0 | `0x800359E0` | `u8[3]` | `g_text_rgb` | sprite colour of the glyph; `0x10` dark (default) or `0x7C` light |
| +3 | `0x800359E3` | `u8` | `g_text_wait_armed` | page timer already loaded for this page |
| +4 | `0x800359E4` | `u32` | `g_text_flags` | `1` page ended on `0x8002` (more follows) · `2` message ended (`0x8000`) · `4` light text, dark shadow `(0x18,0x18,0x14)` instead of `(0x4C,0x4C,0x48)` · `8` advance requested · **`0x10` vertical** |
| +8 | `0x800359E8` | `s16,s16` | `g_text_origin` | pen origin x, y |
| +0xC | `0x800359EC` | `u16*` | `g_text_page` | first word of the page on screen; `NULL` = no dialogue |
| +0x10 | `0x800359F0` | `u16*` | `g_text_next` | first word after the page's terminator |
| +0x14 | `0x800359F4` | `s16` | `g_text_wait` | frames until the page turns itself |
| +0x16 | `0x800359F6` | `u8` | `g_voice_active` | set to 1 by `event_begin`; cleared when the XA clip ends (`0x8002B6EC`) or the player skips it (`0x8002D4DC`) |

There is **no** pen position in memory (it lives in `s1`/`s2` for the duration of one
`dialog_draw`), no shadow switch, no pitch field, no glyph-width field, no box rectangle. Pitch
(13 / 14) and cell size (12) are instruction immediates. `g_text_layer` (`0x80028E3C`, `u32`,
normally 1) is the ordering-table slot glyphs go to.

### Primitive memory (measured in `sys_init` `0x80011E80`)

Bump-allocated from `g_heap_base`: two ordering tables of `0x2000` entries and **two primitive
buffers of `0x130B0` (78,000) bytes**, one per frame, shared by the whole scene. `glyph_draw`
takes 60 bytes per glyph (3 × `SPRT`) from `g_prim_next` (`0x800258F0`) with **no bounds check**.
A full Japanese page is 48 glyphs = 2.9 KB; three 40-character English lines are 7.2 KB.
Whether the 3D scene leaves that headroom is an emulator question (§8 Q4).

### Dialogue strip (measured in `dialog_panel_draw` `0x8002E964`)

`g_dlgbox_x` (`0x8002911C`, `s16` **260**, never written) · `g_dlgbox_visible` (`0x8002911E`) ·
`g_dlgbox_level` (`0x80036541`, 0…6) · `g_dlgbox_fade` (`0x80029120`, 7 × `{s16 brightness, s16
semitrans+1}` = 0, 10, 25, 50, 112, 168 semi-transparent, then **224 opaque**). It draws a
`TILE` at `x = g_dlgbox_x + 5`, `y = 0`, `w = 0x145 − g_dlgbox_x` (65), `h = 0xF0`, and a 5-px
gouraud fade to its left, into `g_ot[2]`, under a `DR_TPAGE` with abr 1. *Hypothesis from the
numbers:* on screen it is a pale paper strip with dark text; `msg_open` raises it, the event
code lowers it 30 frames after the last message (`0x8003636C`).

### SELECT geometry (measured)

`layout = g_select_base[type−1] + variant − 1` (`0x80028F6C`, `u8`: 0, 1, 3, 6, 10, 11).
`g_select_lines[layout]` (`0x80028F74`) = 2 2 4 3 5 3 3 3 3 3 2 3; `g_select_first[layout]`
(`0x80028F80`, leading prompt lines) = 0 0 0 0 0 1 0 0 1 1 0 1. `g_select_pos` (`0x80028E7C`):
per layout five `{s16 x, s16 y}` **column tops**, e.g. layout 0 = (166,80) (142,80) — columns 24 px
apart, right to left. `g_select_rect` (`0x80028E44`, by `type−1`): (120,56,80,96) (120,40,80,144)
(104,40,112,152) (104,24,112,192) (216,120,80,96) (208,56,96,168) (32,28,256,192 — the controls
help). The cursor sprite goes at line origin `(−2, −0x18)`, i.e. *above* the column.

## 2. From a message id to pixels

1. Bytecode `MSG`/`XAMSG` (`g_ev_ops`, [text-format.md](text-format.md)) → **`msg_open(msg)`**
   `0x8002CF9C`: `text = g_ev_block + *(u32*)(g_ev_block + 0x14 + 8·msg)`; if the offset is 0,
   nothing; else `dialog_open(0x129, 0x16, 1, text)` and `dialog_panel_show()`. `XAMSG` first
   calls `msg_voice_start(msg)` (`0x8002CF14`) on the 12-byte key at `+0x10 + 8·msg`.
2. **`dialog_open`**: origin, `g_text_page = g_text_next = text`, `g_text_wait = 0`,
   `wait_armed = 0`, flags = `(flags & ~0x10) | (vertical << 4) | 1`.
3. Every frame **`event_update`** (`0x8002D23C`) calls `text_set_light(0)` then
   **`dialog_draw`** (`0x8002BDA8`; `text_draw_step` `0x8002BDB0` is its third instruction, not a
   second entry — nothing jumps there):
   * if `g_text_wait != 0` and `g_voice_active`: decrement; on reaching 0 → `dialog_next_page`.
   * if flag `8`: clear it; if flag `2` (message had ended) → `g_text_page = NULL`, flags
     `&= ~3`, return (dialogue closed); else if flag `1` → `g_text_page = g_text_next`.
   * `x = origin.x, y = origin.y, p = g_text_page`; loop: word `< 0x8000` →
     `glyph_draw(word, x, y)` then **vertical: `y += 13`; horizontal: `x += 14`**. `0x8001` →
     vertical: `y = origin.y, x −= 14`; horizontal: `x = origin.x, y += 13`. `0x8000` → flags
     `= (flags & ~3) | 2`, stop. `0x8002` → skip its operand, flags `= (flags & ~3) | 1`, and if
     `!wait_armed` { `g_text_wait = operand; wait_armed = 1` }, stop. Any other `0x80xx` →
     skipped. Then `g_text_next = p`, `text_emit_tpage()`.
   * The `0x0000` after every `0x8001` and `0x8002 p` is an ordinary glyph: id 0, the blank cell,
     drawn (3 sprites of blank texels) and advanced over. It indents continuation columns by one
     cell. Removing it from English text is safe for the renderer.
4. **Page turn / voice sync.** The operand of `0x8002` is a frame count that only runs while
   `g_voice_active`; it is the whole synchronisation — the XA clip is started once per message and
   the text pages flip on timers authored to match it. Pad (`0x80072766`): while `g_voice_active`, only bit `0x20` acts and it **stops the clip**
   (`0x8002B560`, `g_voice_active = 0`, further conditions at `0x8002D488…0x8002D4CC`); once it is
   inactive, bit `0x20` or `0x40` calls `dialog_next_page`. If flags
   `& 3`, `dialog_cursor_draw` (`0x8002BFB0`) draws the arrow at `(0x10A + wobble, 0xDC/0xDF)`.
   **Consequence for translation:** an English message may have a different number of pages than
   the Japanese one, but each page's operand is *how long that page stays up while the voice
   plays* — the reinserter must re-author them (sum ≈ the original sum), not copy them.
5. **`glyph_draw(id, x, y)`** `0x8002BA2C` — [font.md](font.md). Three 12×12 `SPRT`s at
   `(x,y)`, `(x+1,y)`, `(x,y+1)`; `w`/`h` are the literal `0xC` (`0x8002BB4C`). No clipping, no
   range check on `id`.

## 3. Text surfaces — the `TXT-05` site list (measured unless marked)

All 58 `glyph_draw` `jal` sites grouped by function (`work/txt01/callers.py`); no pointer to
`glyph_draw`, `dialog_open`, `select_draw` or `text_draw_h` exists as a data word or `lui` pair in
any image. **V** = vertical, **H** = horizontal, adv = glyph advance / line step in px.

| # | image · function | text source | dir · adv | direction comes from | geometry comes from |
|---|---|---|---|---|---|
| 1 | EXE `dialog_draw` `0x8002BDA8` | event `MSG`/`XAMSG`; ant-count array `0x80029AFC`; the 3 resident blocks | **V** 13 / 14 | literal `1` at `0x8002CFCC` and `0x80032078` → flag `0x10` | literals `0x129`,`0x16` at `0x8002CFC4/C8` and `0x8003206C/74`; strip from `g_dlgbox_x` + literals |
| 2 | EXE `select_draw` `0x8002C234` | event `SELECT` (`select_open`) and 8 native `select_run_ptr` sites: EXE `0x8003F02C/F0B0/F1E4` (insect cage), `TAKO 0x8007F55C`, `MUSI 0x8007EF0C`, `HHON 0x8007C988` (EXE array `0x80046158`) and `0x8007D23C`, `ZUKAN 0x8007B07C` | **V** 12 / table | hard-coded: `addiu s0,s0,0xc` on the y register at `0x8002C2D0` | `g_select_pos`, `g_select_rect`; cursor offset literals `0x8002C3D4/DC` |
| 3 | `HHON hhon_text_draw_v` `0x8007C278` | insect book entries `+0x5328` | **V** 12 / 14 | hard-coded (`0x8007C2D8`, `0x8007C2E4/EC`) | literals: (0x100,0x2C) or (0x124,0x26); continuation columns restart at y `0x20` |
| 4 | `HHON hhon_text_scroll_v` `0x8007C1C4` | same, scrolling, via `glyph_draw_layer` | **V** 12 / 14 | hard-coded | literals (0x32,0x110−s) / (0x5A,0xFE−s) |
| 5 | EXE `help_screen_draw` `0x80035674` | `g_help_text` `0x80029B20` | H 12 right-aligned (`text_draw_right`) ×4, H **10** (`help_line_draw`) ×2 | hard-coded | literals; rect 7 |
| 6 | EXE `date_label_draw` `0x80037544` (callers: EXE `cage_hud_draw`, `MUSI`, `HHON`) | immediates `0x21F 0x382 … 0x1B8 … 0x157` + sprite digits | H, offsets `+0xD +0x25 +0x3A/0x41` | hard-coded | args |
| 7 | EXE `date_label_draw_b` `0x80037698` | immediates `0x3EC 0x158 0x1F7 0x25D 0x1B8 0x157` | H | — | **unreferenced** |
| 8 | EXE `count_label_draw` `0x800377F8` (EXE, `MUSI` ×2, `HHON`) | immediates `0x26A`, `0x4B9` + digits | H; x shifts by digit count | hard-coded | args |
| 9 | EXE `sysmsg_draw` `0x800379EC` via `sysmsg_line_draw` `0x80037BA8` | `g_sysmsg_text` `0x8003D2E0` (insect names, system words) | **arg**: `a3 = 0` H 12 at all 11 sites (EXE `0x8003FF90`, `MUSI` ×9, `HHON 0x8007C464`; `a3` not traced at `MUSI 0x8008E8AC/EC7C`) — V 12 if non-zero | 5th parameter | args; lowers glyph ids in a 3-entry list (`0x80036700`) by (−2,+2), maps id 13 → 14 |
| 10 | EXE `mc_slot_labels_draw` `0x8003A7A4` | 3 ids from `0x80036750` | one glyph per row, x `0x9A`, rows 28 px | — | literals |
| 11 | EXE `sys_title_draw` `0x8003C5EC` | line *n* of `0x8003DA4C` | H 12 | hard-coded | (0x88 or 0x82, 0x48) |
| 12 | EXE `item_menu_draw` `0x800416E8` | item names `0x80046214` (`text_draw_line_h`, x `0x28`); descriptions / captions `0x80046398`, `0x80046614` (`text_draw_h` at `0xB8,0x7E`) | H 12 / 16 | hard-coded | literals |
| 13 | EXE `kite_menu_draw` `0x80041FE4` | kite names `0x800461CC` | H 12 | hard-coded | x `0x30` |
| 14 | EXE fishing `0x80043EF8…0x80043FF0` | `0x800462C8…0x80046390` | H 12 / 16 | hard-coded | literals |
| 15 | `TITLE title_date_draw` `0x8007BB60` | immediates + `0x34 + digit` | H | hard-coded | args |
| 16 | `TITLE title_slot_digits_draw` `0x8007C8EC` | digits, `0x5B0` | H | hard-coded | literals |
| 17 | `TITLE title_mc_message_draw` `0x8007CB54` | **EXE array at `0x8003D5F0`**, ≤ 3 lines chosen by the 5-byte table `0x800814C0` | H 12, rows +16 | hard-coded | x `0x22`/`0x4A`, y by class |
| 18 | `TITLE title_mc_glyphs_draw` `0x8007CF7C` | 5 ids at `0x80081480` | H 12 (one 0x30 gap) | hard-coded | literals |
| 19 | `TITLE title_config_draw` `0x8007FA94` | **EXE array at `0x8003D9BC`**, 5 lines | H 12 (line 1: 16) | hard-coded | x `0x28`, y `0x50 + 0x18·i` |
| 20 | `TITLE` `0x800803D8`, `0x80080680` | **EXE array at `0x8003DA00`** | H 12 | hard-coded | literals |
| 21 | `TITLE title_stats_draw` `0x80080484` | digits + immediates `0xF 0x37 0x35 0x28` | H | hard-coded | literals |
| 22 | `TAKO` `0x8007C684` | 4 ids | one glyph per row, x `0x9A` | — | literals |
| 23 | `MUSI` `0x8007C604` | ids at `0x80079D50` | H 12 | hard-coded | (0x78, 0x9C) |
| 24 | `MUSI` `0x8007EDB0` | ids at `0x80079D60` | H 16 / 12 | hard-coded | literals |
| 25 | `MUSI musi_move_name_draw` `0x80084F64` | `MUSI +0x2C` move names | H 12 | hard-coded | (0x8C, 0xA0/0xB4) |
| 26 | `MUSI` `0x800850D8` | same array | H 12 | hard-coded | y `0x68` |

`BUMPER`, `ENDOTI` and `ZUKAN` draw no glyphs themselves (`ZUKAN` only runs a SELECT). The diary
(`NIKKI`) has no glyph path at all: its pages are TIMs. Digits next to labels are sprites from
`number_draw` / `number_draw_b` (`0x800400F8`, `0x800402D8`), not font glyphs. The inline walkers
of surfaces 9, 17, 19, 20, 25, 26 are copies of one source routine (same special-glyph nudge).

**Corrections this makes to [text-format.md](text-format.md):** the system-message array is
referenced from more than `0x80037C84` — `TITLE.OVL` holds `lui`/`addiu` pairs to three addresses
*inside* it (`0x8007CC04/CE08/CEA8` → `0x8003D5F0`; `0x8007FAE8` → `0x8003D9BC`;
`0x800803EC/0x8008068C` → `0x8003DA00`), the EXE one to `0x8003DA4C` (`0x8003C60C`), and
`HHON 0x8007C97C` points at the EXE cage select `0x80046158`. Relocating or re-lengthening that
array means patching an overlay too. `ZUKAN`'s select is read at `0x8007B07C`, `TAKO`'s at
`0x8007F55C`, `MUSI`'s at `0x8007EF0C` and its move names at `0x80084F64`/`0x800850D8`.
All seven overlays load at `*g_overlay_base` = `0x80079A08` — measured at all 8 `file_load` sites.

## 4. Making dialogue horizontal

### 4a. The minimal patch set (no new code)

| RAM | file | now | becomes | effect |
|---|---|---|---|---|
| `0x8002CFCC` | `0x1D7CC` | `01 00 06 24` `addiu a2,zero,1` | `00 00 06 24` | every event message opens horizontal |
| `0x8002CFC4` | `0x1D7C4` | `29 01 04 24` `addiu a0,zero,0x129` | `addiu a0,zero,X0` | left margin |
| `0x8002CFC8` | `0x1D7C8` | `16 00 05 24` `addiu a1,zero,0x16` | `addiu a1,zero,Y0` | first baseline |
| `0x80032078`, `0x8003206C`, `0x80032074` | `0x22878`… | same three | same | the ant-count message |
| `0x8002911C` | `0x1991C` | `04 01` (260) | `FB FF` (−5) | strip starts at x 0 (fade falls off-screen) |
| `0x8002EA38` | `0x1F238` | `0A 00 00 A6` `sh zero,0xA(s0)` | `sh s1,0xA(s0)` = `0A 00 11 A6` | strip y = the value in `s1` |
| `0x8002EA34` | `0x1F234` | `F0 00 11 24` `addiu s1,zero,0xF0` | `addiu s1,zero,H` | strip y **and** h (so y = h = 120 without new code; a free choice needs 2 more instructions) |
| `0x8002C078`, `0x8002C088`, `0x8002C0E8` | | `addiu s1,s1,0x10A`; `0xDC`; `0xDF` | new position | next-page arrow |

Capacity with the engine as it is (14 px pitch, 13 px lines): a 320-px line with 16-px margins is
**20 glyphs**; 3 lines in the height the Japanese columns used horizontally is not meaningful —
the band's height is ours to choose. Line pitch is the literal at `0x8002BF48`
(`addiu s1,s1,0xd`), glyph pitch at `0x8002BF7C` (`addiu s2,s2,0xe`); setting the latter to 8
is the family's "one constant" experiment and needs no table.

### 4b. The VWF hook point

After `jal glyph_draw` (`0x8002BF54`, delay slot `move a2,s1`) come **nine instructions,
`0x8002BF5C…0x8002BF7C`**, that reload the flags, test bit `0x10` and add 13 to `s1` or 14 to
`s2`, falling into `0x8002BF80: addiu s0,s0,2`. Live there: `s0` = pointer to the word just drawn
(not yet advanced), `s1` = y, `s2` = x, `s3` = stop flag; `glyph_draw` preserves `s0–s7`, `fp`;
`v0 v1 a0–a3 t0` are dead. Once vertical mode is abandoned those nine slots hold the whole
advance with no trampoline:

```
lhu   v0, 0(s0)            ; glyph id just drawn
sltiu at, v0, N            ; table covers ids < N
beqz  at, +4               ; others keep the fixed pitch
addiu v1, zero, 14
lui   v1, %hi(width_tbl)
addu  v1, v1, v0
lbu   v1, %lo(width_tbl)(v1)
addu  s2, s2, v1           ; falls into 0x8002BF80
```

8 of 9 slots. The newline branch (`0x8002BF3C…48`) is already right for horizontal. What this does
**not** give: wrapping (do it at build time — the engine has none to fight), a per-glyph left
bearing (needs the x passed to `glyph_draw` adjusted *before* the call at `0x8002BF4C`, i.e. a
real hook — or a left-aligned redrawn sheet, which avoids it), and narrower sprites (the shadow
copies overlap the next cell by one pixel already, harmlessly). The width table for ids < 512 is
512 bytes; all 1,512 ids is 1,512 bytes (§6).

### 4c. SELECT and the insect book

`select_draw`: the step is one instruction — `0x8002C2D0 addiu s0,s0,0xc` (y) → `addiu
s2,s2,0xc` (`0C 00 52 26`); `s2` is reloaded per line from `g_select_pos`, so lines become rows
once that table is rewritten as row origins (12 layouts × ≤ 5 pairs), `g_select_rect` resized (7),
the cursor offset moved from above to the left (`0x8002C3D4 addiu a1,a1,-2`, `0x8002C3DC addiu
a2,a2,-0x18`), and the pad mapping in `select_cursor_update` revisited (`0x8002C3F4…0x8002C44C`:
left `0x8000` = +1, right `0x2000` = −1, and for ≥ 4 options left/right = ±2, up/down = ∓1 — it
encodes right-to-left columns). A VWF here needs a real hook: the loop has no spare slots.
`HHON`'s two walkers swap which register gets `+0xC` and turn `x −= 0xE; y = 0x20` into
`y += pitch; x = left` — four immediates/registers each, plus new origins.

## 5. The §4 checklist of [renderer-prior-art.md](renderer-prior-art.md), against this code

| hazard | here (measured) |
|---|---|
| `strlen`-style centring / right-align | **Two sites.** `text_draw_right` `0x80035360` counts glyphs and draws backwards from `x_right` at 12 px (controls help, 4 calls). `cage_hud_draw` `0x8003FEA4` places the gender icon and size at `x + 12 × (glyph count returned by sysmsg_draw)`; `HHON 0x8007C464` and the `MUSI` name sites use the same return value (*callers' arithmetic not read in MUSI*). No PsyQ `strlen` is involved — text is `u16`. Nothing centres dialogue. |
| measurer must skip control codes | The only measurers stop at the first bit-15 word; none sees `0x8002`'s operand because those arrays contain none. |
| line caps in characters | **None** in any walker. `max_newlines`-style parameters do not exist. SELECT's line *count* is a table (`g_select_lines`), not a cap on length. |
| buffers sized by glyph count | None for text. Shared primitive buffer `0x130B0` bytes/frame, unchecked (§1). Event data: **EV members are read into a `0x4000`-byte per-slot buffer** (`g_ev_buf` `0x80027808`), bump-allocated in whole sectors; `ev_queue_load` `0x80019DEC` panics ("event buffer over", `sjis_panic_print`) when `cursor + sectors × 0x800 ≥ base + 0x4000`, and takes at most 10 events. This bounds EV growth before the sector does. |
| pre-measured text | `count_label_draw` and `date_label_draw` shift x by the number of *digits* (sprite digits 7–8 px); the label glyphs sit at literal offsets tuned to 12–13 px kanji (`+0xD`, `+0x25`, `+0x3A`). English labels need those literals re-tuned or the labels redrawn as one texture. |
| one hack per surface | §3: 26 surfaces. Glyph ids as immediates at surfaces 6, 7, 8, 10, 15, 16, 18, 21, 22, 23, 24 cannot be translated by editing text. |
| cell vs texel size | one literal each: `addiu s4,zero,0xc` (`0x8002BB4C`) is both w and h of all three sprites; u/v are `id`-derived × 12. Keep 12×12. |
| shadow doubles the packet | 3 sprites/glyph, 60 bytes, all at the same size; a VWF that only moves the pen touches none of them. |
| space width | id 0 is drawn like any glyph; its advance is whatever the table says — give it a real width. |
| default for ids outside the table | the hook above keeps 14 px. |
| duplicated assets | text duplication is [text-format.md](text-format.md)'s; on the code side the inline walkers are 6 copies of one routine across EXE/`TITLE`/`MUSI`. |

## 6. Free space for a patch

Layout (measured in `start` `0x80049154`, `main` `0x80022144`, `sys_init`): the PS-X header says
`t_addr 0x80010000`, `t_size 0x7F800`, but the program's real image ends at `0x8007266A`. From
there the file is zeros: BSS `0x80072670…0x80079A08` (cleared by `start`), then **the overlay
area `0x80079A08…0x8008F3A4`** (the file's zeros there are overwritten by whichever `.OVL` is
loaded; the largest, `MUSI`, ends at `0x8008F39A`), then the heap: `g_heap_base` (`0x80068AF0`)
= `0x8008F3A4`, and `main` zeroes `[g_heap_base, 0x801FFFC0)` before `sys_init` starts
bump-allocating OTs, primitive buffers and every loaded file from it. Stack at `0x801FFFF0`.
The zero runs *inside* the image (`0x800258B1`, `0x80035788`, `0x8003DB03`, `0x80046972`,
`0x80068CE5` …) are per-module BSS — `g_text` is in one — **not free**.

Candidates, cheapest first:

1. **Raise `g_heap_base`: `0x8008F3A4 → 0x8008F800`** (one word, file `0x592F0`). The 1,116 bytes
   `0x8008F3A4…0x8008F800` are already inside the file (`0x7FBA4…0x80000`), loaded by the BIOS,
   above every overlay, and after the change nothing clears or allocates them. Costs the heap
   1.1 KB. *Hypotheses to confirm (§8 Q5):* no overlay keeps BSS past `0x8008F3A4` (`MUSI`
   `lui 0x8009` references were checked — all resolve below its file end), and no map is within
   1.1 KB of exhausting RAM. Going further (heap base higher **and** a larger `t_size`) is the
   same mechanism plus a longer file, which moves `BOKU.BIN`'s LBA and therefore all of
   `g_cd_dir_lba` — avoid unless needed.
2. **Dead code, unreferenced by any `jal`, data word or `lui` pair in any image**
   (`work/txt01/dead.py`): `0x80012E04…0x80013070` — 620 contiguous bytes (`cd_dir_sectors_form2`,
   `0x80012E40`, `0x80012E64`, `cd_dir_search_file`, `cd_dir_find`, `0x80012FF8`);
   `dbg_font_init` `0x800221CC` — 712 bytes; `date_label_draw_b` `0x80037698` — 352;
   `0x80037414` — 272; `0x80043928` — 296; `0x8001CA64` 244, `0x8001CDF4` 192, `0x8001CC4C` 168.
   About 3.1 KB, in islands. (Function starts are heuristic — re-check each island's bounds when
   used.)
3. **The house debug printer** `0x80022494…0x80022D64` (~2 KB) plus its 8×8 font data at
   `0x80025120`: `dbg_printf` has 100 call sites, but `dbg_font_init` is never called and
   `dbg_putc` writes through the pointer it would have set (`0x80028C24`, NULL), so every site
   must already be unreachable in retail (*hypothesis*; `g_debug` `0x800237F0` is 0 in the file
   and its only `lui`-pair writer, `0x80020DBC` in the new-game reset `0x80020DA0`, stores zero). Stub `dbg_printf` to `jr ra`
   and the body is free — after §8 Q6.
4. `sjis_panic_print` (`0x8002CA0C`, ~0x140 bytes) — live on the "event buffer over" path, which
   a translation can actually reach (§5). Leave it.
5. **Not available:** PsyQ `FntLoad/FntOpen/FntPrint/FntFlush` are not linked (no signature
   match; the game has its own `dbg_*`). The PS-X header past `0x4C` is not loaded into RAM — it
   can hold nothing a running patch reads. `PCread/PCopen/PClseek` are referenced (PC-host file
   path); `PCcreat` (32 bytes) is not.
6. For *tables*: the font TIM's 24 blank cells and `ONMEM.BIN` growth are [font.md](font.md)'s.

## 7. The `TXT-04` trial — no new code

**Step A — three words in `SCPS_100.88`** (retail LBA 23; file offset *o* is user-data byte
`o mod 2048` of sector `23 + o div 2048`; regenerate that sector's EDC/ECC — all three are in
sector 81):

| file | old | new | |
|---|---|---|---|
| `0x1D7C4` | `29 01 04 24` | `18 00 04 24` | x = 24 |
| `0x1D7C8` | `16 00 05 24` | `84 00 05 24` | y = 132 |
| `0x1D7CC` | `01 00 06 24` | `00 00 06 24` | horizontal |

Optional backing band (sectors 85 and 74): `0x1F234: F0 00 11 24 → 78 00 11 24`,
`0x1F238: 0A 00 00 A6 → 0A 00 11 A6`, `0x1991C: 04 01 → FB FF` — the strip becomes the lower half
of the screen. **What shows it:** start a new game and reach the first line anyone speaks — it
must run left to right from (24, 132), Japanese, 14 px pitch, lines 13 px apart, first glyph of
each continuation line indented one cell; SELECT prompts stay vertical. That alone is the go/no-go
for "the flag works on hardware".

**Step B — English glyphs, in place.** Take that first line (or any line seen on screen), find
its sites with `python3 work/rec03/text_sites.py --dump`, and in **every** physical copy overwrite
the words from the start of the message with `Hello, Boku!` in the font's own full-width Latin:

`0045 005C 0063 0063 0066 0003 0000 003F 0066 0062 006C 0009 8000`
(69 Ｈ, 92 ｅ, 99 ｌ, 99 ｌ, 102 ｏ, 3 ，, 0 space, 63 Ｂ, 102 ｏ, 98 ｋ, 108 ｕ, 9 ！, END — 26
bytes; the site must be ≥ 26 bytes, no table edits). If the message is voiced it still plays.
The static side cannot name the opening event — that is `REC-05`'s — so Step B's target is chosen
from Step A's screen, not from this file.

## 8. Known unknowns — for the emulator

* **Q0.** [tooling-setup.md](tooling-setup.md) measured that RAM never matched the file. Every
  address here assumes identity load at `0x80010000`, and the file is self-consistent with that
  (every `lui` pair lands on the data it should). Break at `0x8002BA2C` during any dialogue: does
  it hit, and do the 4 bytes there read `21 38 80 00`? If not, nothing below can be trusted as
  written and the offset must be found first.
* **Q1.** Break at `0x8002BD30`: confirm `a0=0x129 a1=0x16 a2=1` and that `a3` points at the
  message. Count hits over ten minutes of play — any caller other than `0x8002CFD0`/`0x80032080`?
* **Q2.** With Step A applied: is the horizontal text legible where it lands, and does the
  one-cell indent appear after each newline (confirms id 0 is drawn blank)?
* **Q3.** Read `g_dlgbox_level` and the framebuffer during a line: is the strip the pale opaque
  band the fade table implies? Does anything else draw at x ≥ 260 during dialogue (portraits,
  the clock) that a bottom band would collide with?
* **Q4.** In the busiest scene with dialogue up, read `g_prim_next − g_prim_buf[frame]`
  (`0x800258F0`, `0x800258E8`): how far below `0x130B0` is the peak?
* **Q5.** With `g_heap_base` raised to `0x8008F800`: watch-write `0x8008F3A4…0x8008F7FF` through
  boot, a map change, bug sumo (`MUSI`) and a save. Any hit kills candidate 1.
* **Q6.** Break at `0x800229A4` (`dbg_vprintf`) and `0x80022C38` across boot, title, a day of play,
  sumo: never hit?
* **Q7.** Voiced line: watch `g_text_wait` and `g_voice_active`. Does the page turn exactly when the
  operand runs out; what happens to the last page when the clip ends first; and what does the
  first press do on an *unvoiced* message (`g_voice_active` is 1 from `event_begin` — *hypothesis:*
  the first press is consumed clearing it)?
* **Q8.** `MUSI 0x8008E8AC` / `0x8008EC7C`: value of `a3` at the `jal 0x80037BA8` (is any system
  message ever drawn vertically?).
* **Q9.** Pad bit names at `0x80072766` (`0x20`, `0x40`) — which buttons.
