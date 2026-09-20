# The font and the glyph table (PLAN `REC-04`, static half of `TXT-02`)

Measured on the dump identified in [disc-recon.md](disc-recon.md) unless marked *hypothesis*.
RAM addresses are in `SCPS_100.88` (file offset = RAM − `0x8000F800`); symbol names are ours.
The table is [`data/glyph-table.tsv`](data/glyph-table.tsv). Everything else regenerates with
`python3 work/rec04/build.py` (stdlib; `--sheets` under `uv run --no-project --with pillow` adds
the labelled contact sheets).

## Where the font is

**One sheet: `ONMEM.BIN` (directory index 153), pack child 2** — a 4bpp TIM, 252×224 pixels
(63×224 VRAM words), with a 16×8 CLUT. It is not a 16-colour image: it is **four independent
1bpp sheets, one per bit of the 4-bit pixel**. The CLUT rows are the plane selectors — row *k*
(0–3) is `0x8000` (opaque black) where bit *k* of the index is set and `0` elsewhere; rows 4–7
are the same masks in `0xFFFF` (white). Drawing with CLUT row 4+*k* shows plane *k* alone.

| | |
|---|---|
| cell | 12×12, no gutter |
| columns | 21 (21 × 12 = 252) |
| rows per plane | 18 (216 px; the last 8 pixel rows of the TIM are zero) |
| slots | 21 × 4 × 18 = **1512** |
| inked | ids 1…1487; id 0 is blank (the space); **1488…1511 are blank (24 free slots)** |
| id → cell | `col = id % 21`, `plane = (id / 21) % 4`, `row = id / 84` |

So the planes interleave per sheet row: ids 0–20 are row 0 of plane 0, 21–41 row 0 of plane 1,
… 84–104 row 1 of plane 0. **Ids above 1023 need no second sheet or paging** — the PSP port's
1024-per-sheet limit is that port's, not this engine's; here one formula covers 0…1511.

The only other font path is the BIOS kanji font, and it is a developer fatal-error printer:
`sjis_panic_print(x, y, sjis)` (`0x8002CA0C`) walks a Shift-JIS string through `Krom2RawAdd`
(`0x8004A55C`), `LoadImage`s each 16×16 glyph straight into the display area and stalls 600
frames. Its one caller (`0x8001A07C`) passes the "event buffer over" message at `0x80011738`.
`Krom2RawAdd`'s other caller is in the function at `0x80049FE4` — **not read** (*hypothesis:*
the memory-card file title, which the BIOS requires in Shift-JIS). All glyph-id text goes
through `glyph_draw`. `NUMBER.TIM` (144×10, 4bpp) and the
digits inside other TIMs are graphics, not part of this font (*not examined further*).

## How it reaches VRAM

`boot_load_resident` (`0x8001218C`, [boku-bin.md](boku-bin.md)) loads `ONMEM.BIN` with
`file_load(153, buf)` and calls **`onmem_init` (`0x80012088`)**, which reads the pack's child
offsets and calls

`tim_upload(child2, &{x=0x300, y=0, clut_x=0x100, clut_y=0x100})` — **`tim_upload`
`0x80014C98`** `(u8 *tim, s16 rect[4])`: `LoadImage` of the CLUT block to `(rect[2], rect[3])`
with the TIM's own CLUT w/h, then `LoadImage` of the pixel block to `(rect[0], rect[1])` with
the TIM's own w/h. The TIM header's own coordinates (all zero here) are ignored. 41 call sites
(EXE 16, overlays 25) — it is the game's general TIM uploader.

Result: **pixels at VRAM (768, 0)–(830, 223), CLUT at (256, 256)–(271, 263)**. `onmem_init`
returns the address of child 2 as the next free byte, so the TIM is overwritten in RAM by the
next load — after boot the font exists only in VRAM. *Hypothesis:* nothing re-uploads it or
overwrites that region; the other 40 `tim_upload` sites' rects were not read.

`onmem_init` also uploads child 3 (48×88, 4bpp, 3 CLUTs — not font) with `tim_upload` to
(608, 256), CLUT (624, 256); passes child 0 (64 bytes) with the same coordinates to `0x8002A500`
(not read); keeps child 1 at `0x800258B8`; and hands children 1 and 4 to `0x8001C7BC` (sound).

To replace the font a patch changes child 2 of `ONMEM.BIN` in place (same size: no directory
change). To extend it: 24 blank slots exist already; the TIM could grow to 252 rows (21 sheet
rows, 1764 slots) before `v` overflows a byte — but that needs VRAM rows 224…251 under the
sheet to be free, which is unverified, and a larger `ONMEM.BIN` child.

## The draw code

| RAM | our name | what it does |
|---|---|---|
| `0x8002BA2C` | `glyph_draw(u32 id, s16 x, s16 y)` | `q = id / 21` (multiply by `0x86186187`); `u = (id − 21q) × 12`; `v = (id / 84) × 12`; `clut = 0x4010 + (((q & 3) + 4) << 6)` = CLUT at (256, 260 + plane). Emits **three 12×12 `SPRT`s** (`SetSprt` `0x80066530`, `AddPrim` `0x800560FC`) into the OT slot `g_ot[g_text_layer]` (`*0x8002593C + 4 × *0x80028E3C`): the glyph at (x, y) in the colour at `g_text_rgb` (`0x800359E0`, 3 bytes), and two shadow copies at (x+1, y) and (x, y+1) in (0x4C,0x4C,0x48), or (0x18,0x18,0x14) when `g_text_flags & 4`. Primitives come from the bump pointer `g_prim_next` (`0x800258F0`). 58 call sites: EXE 23, `TITLE.OVL` 28, `MUSI.OVL` 5, `TAKO.OVL` 1, `HHON.OVL` 1. |
| `0x8002B9FC` | `glyph_draw_layer(id, x, y, layer)` | sets `g_text_layer`, calls `glyph_draw`, restores layer 1. One caller (`HHON.OVL`). |
| `0x8002B95C` | `text_emit_tpage` | `SetDrawTPage(prim, 0, 1, 0x4C)` into the same OT slot — texture page 12 = VRAM (768, 0), 4bpp, abr 2. Called after a string is drawn, so it executes before the sprites. |
| `0x8002BDB0` | `text_draw_step` | the string walker. Reads `u16`s from the cursor; `< 0x8000` → `glyph_draw`; `0x80xx`: low byte 0 = end, 1 = newline, 2 = wait (next `u16` → `0x800359F4`), anything else skipped. |

`text_draw_step` state, all at `0x800359E0…`: `+0` rgb, `+3` wait-armed flag, `+4`
`g_text_flags` (u32), `+8`/`+0xA` origin x/y (s16), `+0xC` string start, `+0x10` cursor,
`+0x14` wait counter.

**The walker already has a horizontal mode.** `g_text_flags & 0x10` set = vertical: each glyph
`y += 13`, newline `y = origin_y; x −= 14`. Clear = horizontal: each glyph `x += 14`, newline
`x = origin_x; y += 13`. Which callers set the bit was not read — that is `TXT-01`.

Glyph ids passed as immediates (not from strings): 343 日, 440 月, 344, 503, 543, 605, 618,
898, 1004, 1209, 14 in the EXE; 1456, 15, 40, 343, 440 and digits (`52 + n`) in `TITLE.OVL`
(`work/rec04/direct_ids.py`). 12 `TITLE.OVL` sites pass `52 + n`; 23 more compute the id.

## The glyph table and how it was verified

Order (measured): id 0 space; 1–51 punctuation and symbols; 52–61 digits; 62–87 `Ａ–Ｚ`; 88–113
`ａ–ｚ`; 114–194 hiragana (no ゐ ゑ); 195–278 katakana (no ヰ ヱ; ends ヴ ヵ ヶ); 279–1473 kanji
in order of first need by the script writers — neighbours often spell a word (簡単, 掃除, 冒険,
洞窟, 郵便, 反芻, 財閥), which is itself a check; 1474–1487 specials (`SEL`+`ECT`, a dashed rule,
two-cell △ and ○ button glyphs, □, △, and at 1456 a narrow `）`).

Method: every one of the 1487 inked cells was rendered 5–10× beside a candidate character and
compared by eye (`work/rec04/contact.py`). Candidates for 0–278 came from Shift-JIS collation;
for 279–1023 from the PSP port's table, used locally as a cross-check only; **1024–1487 (464
glyphs) were read from the pixels with no candidate**, then every glyph the text uses was
checked in a decoded context window (`ctx2.py`), which caught six misreadings (斧, 璧, 検, 鉢,
衛, 敏) and confirmed the rest.

* The PSP table decodes PS1 text for ids < 1024 **except nine entries**, where the PS1 pixels
  (and, where used, the context) say otherwise: 373 暑, 394 赤, 411 基, 547 待, 608 房, 678 土,
  699 丈, 822 予, 828 伸. Marked in the TSV's notes.
* The Korean PSP patch's table is no help above 1023: those slots hold its Hangul.
* Confidence: every entry is `verified-visually` (and every text-used kanji context-checked)
  except three `inferred-from-order`: 1300 稜, 1346 芻, 1437 閥 — shape plus neighbour, no context. None left `unknown`. The weakest class is **the 466 kanji/special glyphs no
  scanned text uses**: read once from 12×12 pixels with nothing to confirm them. An error there
  cannot affect extraction of the text we found, but would surface if `REC-03` finds more text.
* Three characters occur twice by design: `）` 22 (vertical form) / 1456, `□` 46 / 1484,
  `△` 47 / 1487.

## Which ids the text uses

`work/rec04/usage.py` re-runs `REC-01`'s line heuristic with the ceiling raised to 1511 over
map-pack child 1, `EV` records, the overlays and the EXE: 6,018 candidate lines, 2,257
distinct. That scan sweeps up script bytecode (`0x21B`, `0x514`, `0x312`… decode as 鍵, 稜, 薩
and sit right before text), so `usage2.py` keeps only lines that start with a speaker label or
`「`/`『`, continuation lines ending `」`/`』`, `HHON.OVL`, and the EXE's item/photo/diary
strings (file `0x1A230…0x37146`; the "text" `REC-01` saw near file `0x60CAA` is noise).

* **924 ids are used by clean text, 203 of them above 1023**; 4 more only by code (15, 40,
  1209, 1456). Highest real id in text: 1472 帽. The raw scan's id 1500 is bytecode.
* **559 inked glyphs are never used** by anything found: 80 of ids 1–113, 13 kana, 466
  kanji/specials. With the 24 blank cells that is **583 slots that could be repurposed** — an
  upper bound until `REC-03` walks the script structurally (strings shorter than 3 glyphs,
  text in formats the heuristic cannot see, and the 23 computed-id draw sites are not counted).

## What the font offers English (`TXT-02`)

Present: `Ａ–Ｚ`, `ａ–ｚ`, `０–９`, and `， ． ・ ： ； ？ ！ ＿ ― ／ ‘ ’ ＋ − ± × ÷ ＝ ＜ ＞ ￥ ％ ＃ ＆ ＊ ＠`
plus ○ □ △ and arrows. **Absent:** straight or double quotes (`"` `“` `”`), a horizontal `（`,
hyphen distinct from `−`, `~` in horizontal form. **Drawn for vertical writing** (rotated or
placed top-right), so wrong in a horizontal line: `、 。 ー 〜 … （ ） 「 」 『 』 【 】` — English
should use `， ．` (ids 3, 4, bottom-left) and needs new quote/paren glyphs.

All Latin glyphs are proportional drawings inside full-width 12×12 cells — there is no
half-width set and no width table. Ink widths in pixels (`metrics.py`):

| set | widths |
|---|---|
| caps | 7–9, mean 7.8 (`Ｉ` 1, `Ｊ` 6; `Ａ Ｍ Ｔ Ｖ Ｗ Ｙ` 9) — rows 1–9 |
| lowercase | mean 5.6: `ｉ ｌ` 1, `ｊ` 2, `ｆ ｒ ｔ` 4, most 6, `ｇ ｏ ｖ ｙ` 7, `ｍ ｗ` 9 — x-height rows 4–9, ascenders from row 0, descenders to row 10 |
| digits | 7 (`１` 4, `４` 8) — rows 1–9 |
| kana / kanji | mean 9.6 / 11.0 |

Ink starts 1–5 px from the cell's left edge, so a variable-width renderer needs a per-glyph
left offset as well as a width (or a redrawn, left-aligned sheet).

Workable? At the engine's fixed 14-px pitch a 320-px line holds 22 characters — not workable.
With per-glyph advances (mean lowercase ink 5.6 + 1 px gap) about 45 characters fit in 300 px
at a 13-px line pitch, which is ordinary for a PS1 translation. The glyphs are 1bpp with a
two-copy drop shadow, legible but plain; whether to keep them or redraw is `TXT-03`/`TXT-06`.
The lowercase letters and every capital but `Ｔ` are unused by the Japanese text, so they can be
redrawn or re-spaced without touching untranslated lines.

## Open doubts

* Whether VRAM (768…831, 0…255) is exclusively the font's for the whole game, and whether rows
  224…255 there are free — needs an emulator VRAM view.
* `MDLTIM.RTM` TIM headers name (768, 0) and (640, 0); if its loader honours them they would
  collide with the font. *Hypothesis:* it relocates, as `tim_upload` does. Not read.
* What the second `Krom2RawAdd` user at `0x80049FE4` draws.
* The 23 `glyph_draw` sites with computed ids, and who sets `g_text_flags & 0x10` (`TXT-01`).
* PsyQ identities `SetSprt`, `AddPrim`, `SetDrawTPage`, `LoadImage` are from the Ghidra
  signature export in `symbols/`, except `SetSprt`, recognised from its body.
