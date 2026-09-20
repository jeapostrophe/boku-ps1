# The text renderer at run time (PLAN `TXT-01`, emulator half)

What [text-renderer.md](text-renderer.md) § 8 asked the emulator, answered by running the retail
image headlessly in PCSX-Redux (build `e3e051ca`, `-interpreter -debugger -no-ui`, BIOS SCPH-5500)
from Lua on 2026-09-20. **Measured** = printed by a script under `tools/redux/` in a run whose
log is in the gitignored `work/txt01-emu/`; *hypothesis* says so. Frames are GPU vsyncs (60 Hz)
from process start unless "state-relative". Screenshots are the game's pixels and stay in
`work/txt01-emu/shots/`; they are described here, not shown. Symbols:
[`symbols/text-renderer.symbols.tsv`](symbols/text-renderer.symbols.tsv).

How to run anything below: `tools/redux/run-txt01.sh <script.lua>` (wraps `run-headless.sh`;
sets `REDUX_BIOS` to its documented default and the scratch directory). `drive.lua` is the
general driver — load a save state, play a pad script, arm probes (`BOKU_PROBE=dialog,voice,pad,
prim,dbg,heap,heapraise`), shoot frames, save a state; `trial-pokes.lua` is the in-RAM trial;
`shot2png.py` and `sstate_vram.py` turn the dumps into PNGs. The emulator runs at roughly 130–190
emulated frames per wall-clock second here, so a cold boot to the first dialogue is about a minute.

## Q0 — the executable IS identity-loaded at `0x80010000`. The old alarm was a too-early sample

`q0-exe-load.lua`, cold boot:

* RAM `0x80010000…` first equals the file's bytes at **frame 720**, with the PC in BIOS ROM
  (`0xBFC0D9E0`) — the BIOS copying the EXE in. Before that, the address range belongs to the
  **BIOS shell**, which runs from RAM at `0x8003xxxx–0x8005xxxx` while the logo plays.
* The PC reaches the header's entry `0x80049154` **182,548 times before the EXE is loaded** (first
  at frame 90; the bytes under it are `06 00 40 16 …`, shell code) and **exactly once with the EXE
  under it, at frame 835** (`07 80 02 3c 70 26 42 24` = the file). The earlier note's "entry
  breakpoint fires at frame 90" was the shell; its frame-300 samples predate the load by 420
  frames.
* Whole-range compare `0x80010000…0x8008F7FF` against file `0x800…` at frame 840: **0 mismatching
  bytes in the image** (`…0x80072670`), 4 in BSS (already written by `start`), 0 in the overlay
  area and the heap gap. `glyph_draw` `0x8002BA2C` reads `21 38 80 00` as the static pass expects.

Every address in text-renderer.md and the symbol TSVs is a run-time address. No relocation, no
second `LoadExec`, no overlay over the EXE's image.

## Reaching the first dialogue — `tools/redux/boot-to-dialogue.lua`

| frame | input / event |
|---|---|
| ~720 / 835 | EXE in RAM / entry reached |
| ~2250 | title screen up (SCEI, Contrail, Millennium Kitchen logos before it cannot be hurried by this script) |
| 2430 | **START** 5 frames → menu; the cursor is already on the first entry (start from the beginning) |
| 2600 | **○** 5 frames → memory-card check screen (horizontal system text in a wooden frame), then the intro FMV from ~3400 |
| 3600 | **START** 5 frames → FMV skipped; map `H02001` loads (game mode byte `0x800237E0`: 2 title, `0x0F` card check, `0x0E` movie, 5 field) |
| 3817 | `event_begin` |
| 3979–3980 | `msg_open(0)` → `dialog_open` |

The script exits 0 when `dialog_open` fires with the expected literals, 3 if it has not by frame
4600 (made red on purpose with `BOKU_FRAMES=3000`), and leaves save state `first-dialogue`.
Pad overrides work under `-no-ui` with no controller configured.

## Q1 — `dialog_open` arguments; the opening event is **`E0171`**, first line **`E0171.0`**

Measured at `0x8002BD30`, 15 hits over the arrival sequence: always `a0 = 297, a1 = 22, a2 = 1`,
`ra = 0x8002CFD8` (`msg_open`), `a3 = g_ev_block + *(g_ev_block + 0x14 + 8·msg)`; `msg_open`
always called from `0x8002F4FC` (`XAMSG`). No other caller appeared.

The first event is in map `H02001`, day 1, 14:00, auto-started, 11 block entries (= 4 messages),
lines father ×3 then Boku — which is `E0171` in [`data/scenes.tsv`](data/scenes.tsv) (day 1, `H02`,
`lflag==0`, `FATHER FATHER FATHER BOKU`, then `MAP:I32`). Identification is by map + day + entry
count + speakers, not by reading an id out of RAM (no run-time location for the id is documented).
With no input the chain autoplays: `E0171` (H02001, msgs 0–3) → `E0172` (I32000, sky pan, no
text) → `E0174` (H03000, 2) → `E0175` (I31000, 1) → H02001 (1) → I31000 (3) → H03000 (1) →
I31000 (1) → FMV → G13100 (1) → G14100 (Boku's room). `E0171.0` is one page, two columns, voiced:
the father's greeting to the household.

## Q3 — what vertical dialogue looks like (shots `t8-00450_x3.png`, `sheet-t8.png`)

* The strip is **opaque flat grey (231,231,231) from x = 265 to 319, full height 0–239**, with a
  5-px gradient at x = 260–264 into the scene. `g_dlgbox_level` = 6 while a message is up. It is
  not translucent at rest; the semi-transparent levels are only the 6-frame open/close fade.
* Text is near-black (24,24,24) with a grey (148,148,140) shadow right and below. Columns start at
  x = **297, 283, 269** (14 px), rows every **13 px** from y = 22; the longest page seen ran to
  y = 188. Continuation columns are indented one cell (glyph 0), as predicted.
* **The speaker label is inline text** — the name and an opening corner bracket are the first
  glyphs of the message. There is no portrait, name plate, clock or HUD anywhere on screen during
  these scenes; the only other dialogue furniture is the small green next-page arrow at the foot
  of the strip (~(266, 220)), drawn only once auto-advance has been cancelled.
* The scenes are **composed for the strip**: backgrounds are full 320 px, but in the close-up
  shots the rightmost character stands half under the strip and the action sits in the left
  260 px. Nothing of interest is ever at the right edge; plenty is at the bottom.

## Q2 — the in-RAM horizontal trial (`trial-pokes.lua`; no disc image touched)

Pokes applied from state `predlg` (7 frames before `E0171.0` opens). Each code poke asserts the
word it replaces; all matched.

1. **`horiz` only** (`sheet-trial.png` row 1): the three immediates work. Text runs left to right
   from (24, 132), 14-px pitch, 13-px lines, continuation lines indented one cell. With no band
   the dark text sits directly on the scenery and is **illegible**; the grey strip still occupies
   the right edge, empty.
2. **`horiz,band`** — text-renderer.md's band (y = h = 120): draws correctly, flat grey over the
   whole lower half. It **covers every character in the scene** (they stand at y ≈ 120–200).
   Legible, unusable.
3. **`band2` — a band with independent top and height in the same instruction slots** (new here):
   `0x8002EA34 addiu s1,zero,H` · `0x8002EA38 sh zero,8(s0)` (tile x = 0) · `0x8002EA44 addiu
   v0,zero,Y` · `0x8002EA48 sh v0,10(s0)` (tile y), with `g_dlgbox_x = −5` so w = 330 (clipped) and
   the gradient falls off-screen. With Y = 168, H = 72 and the pen at (24, 176): three lines fit
   with margin, the next-page arrow's stock position (266, 220) already lies inside the band, and
   the band draws cleanly (`sheet-trial2.png` row 1). It still hides the characters' legs and the
   smallest children entirely in the courtyard scene.
4. **Semi-transparent band** (`BOKU_BAND_LEVEL=4|5`: copy fade entry 4 or 5 over entry 6): the
   panel is additive white (abr 1), so the scene stays visible as a pale wash. At level 5
   (brightness 168) dark text is comfortably legible over grass, path and roof; at level 4 (112)
   it is legible but busy. This is the cheapest way to stop the band hiding the actors — two data
   words — and is a `[MINE: product]` look-and-feel choice.
5. **"Hello, Boku!"** over `E0171.0` (13 words, ids from `data/glyph-table.tsv`): at the stock
   14-px pitch it reads `H e l l o ,   B o k u !` — clean, legible, absurdly wide (12 glyphs =
   168 px; a 20-glyph line limit). With the advance literal at `0x8002BF7C` set to **8** it reads
   as a word, but **`H` collides with `e`** (the sheet's full-width capitals are ~9–10 px wide plus
   a 1-px shadow) while `l`, `,`, `!` float in too much space. One constant is not enough: the
   width table of § 4b is needed, and/or a redrawn Latin set. The message still closes when its clip ends.
6. Japanese drawn horizontally shows the sheet's **vertical-form punctuation**: corner brackets
   lie on their sides, the comma and small kana sit top-right. Irrelevant to English except that
   any punctuation reused from the sheet must be the horizontal forms (ids 3, 9 were fine).

Nothing else on screen moved or broke: no other text surface appeared in these scenes, and the
event sequence ran to the end with the pokes in.

## Q4 — primitive buffer

`g_prim_next − g_prim_buf[n]`, sampled every vsync across the whole arrival sequence (12,000
frames, 10 events, six maps, 3-D close-ups with five actors): **peak 53,288 of 78,000 bytes**, in
`I31000` with dialogue up; 52,280 in an independent run. Headroom ≈ 24.7 KB ≈ 410 glyphs. Three
40-glyph English lines (7.2 KB) fit with room to spare *in these scenes*. Caveats: a vsync sample
can land mid-build (the game runs at 30 Hz, so roughly every other sample is a finished frame);
free-roam, bug sumo and the menus were not sampled.

## Q5 — `0x8008F3A4…0x8008F7FF` is dead through boot, title and the arrival sequence

`BOKU_PROBE=heapraise`: at the real entry (frame 835) the script sets `*0x80068AF0 = 0x8008F800`,
fills the gap with a sentinel and arms 279 word write-breakpoints. Over 12,000 frames — title
overlay, memory-card check, two FMVs, six map loads, ten events — **0 write hits and 0 of 279
sentinel words changed**; the game ran normally on the smaller heap. The watch can fire: armed
from power-on without the raise it logs 1,953 hits (BIOS clear, load, `main`'s clear) — the red
run. **Correction to text-renderer.md § 6:** `0x80068AF0` is not a constant "base": it is the
**bump pointer itself** (`0x800C6160` by the end of the run). Raising its initial word still
works, for that reason. Not covered: `MUSI`/`HHON`/`ZUKAN`/`TAKO` overlays, a save, a full day.

## Q6 — `dbg_vprintf` / `dbg_printf`

Exec breakpoints on `0x800229A4` and `0x80022C38`: **0 hits** over the same 12,000 frames
(breakpoints demonstrably fire in this setup — `dialog_open` hit 15 times in the same run). A day
of play and sumo are not covered.

## Q7 — page turns, voice, and what the buttons do

* **The `0x8002` operand counts 30-Hz game ticks, not vsyncs**: operand 102 → the page turned 204
  vsyncs after it loaded; 72 → 144. Re-authored operands must be in 1/30 s.
* **The last page closes itself when the clip ends** — no press needed; `g_text_flags` goes
  `0x12 → 0` and the script proceeds. The whole arrival sequence plays hands-off.
* **`g_voice_active` is really "auto-advance still on"**, and **it is not cleared when a clip
  ends** (static claim refuted: a write-breakpoint on `0x800359F6` saw only two writers — the
  store of 1 in `event_begin` at `0x8002CDDC`, once per event, and the store of 0 at `0x8002D4DC`
  on ○). The first ○ during a voiced line stops the clip and clears it; the text stays. From then
  until the next `event_begin`, page timers load but **do not count**, messages no longer close
  themselves, and every page needs a press; the arrow appears. ✕ does nothing while it is 1.
* *Not measured:* the first press on an unvoiced `MSG` line (none occurs in the arrival sequence).

## Q9 — pad word `0x80072766`

Active-high, pressed = 1: **`0x20` = ○, `0x40` = ✕**, `0x10` = △, `0x80` = □ (one button at a
time, 3-frame presses; the word follows the press within 2 vsyncs). So: ○ stops the voice; ○ or ✕
turns the page.

## Q8 — the two `MUSI` call sites

Not attempted: bug sumo is days of play away from a new game and needs a captured insect; there is
no headless shortcut short of a memory-card save placed by hand.

## VRAM: the font page, via save states

Lua has no VRAM accessor and the web server does not listen under `-no-ui`, but
`PCSX.createSaveState()` serialises VRAM as one 1 MiB protobuf bytes field; `sstate_vram.py`
finds it without a schema. Compared at five moments — title screen, intro FMV, 7 frames before the
first line, first line on screen, Boku's room after two FMVs and six maps:

* **(768, 0)–(830, 223) — the glyph sheet — is byte-identical in all five** (sha-256 prefix
  `42be9b88dc66ad29`), and so is the CLUT at (256, 256)–(271, 263). Nothing re-uploads or
  overwrites it, including the FMV decoder and the title overlay.
* Rows 224–255 of the page are **not entirely free**: **row 240, x = 768–831, holds 64 non-zero
  15-bit words in every state** (someone's CLUT). Rows 224–239 and 241–255 were zero throughout.
  Column 831, rows 0–69, is also non-zero and constant (not the font's — the sheet is 63 words
  wide). [font.md](font.md)'s "rows 224…251 free?" is therefore: 224–239 yes as far as seen, 240
  no.
* *Not sampled:* the pause menu, item menu, insect book, sumo, diary.

## What cannot be done headlessly (as set up here)

Hearing anything — whether the clip for the next line still plays after auto-advance is
cancelled is inferred from `g_voice_active`, not heard. Anything needing hours of play (sumo,
fishing, the diary) without a prepared memory card. Raw VRAM is only available at save-state
granularity, not per primitive.
