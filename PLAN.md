# boku-ps1 — Plan

The **live task list only** — open work, nothing else. What the project is:
[README.md](README.md). How it is built and laid out: [TECHNICAL.md](TECHNICAL.md). What has
been learned: [research/](research/). Rules for agents: [CLAUDE.md](CLAUDE.md). History of
completed work: git.

**Conventions.** Every item carries a stable id, assigned once, never renumbered, never reused;
cite items as `PLAN TXT-01`, never by line. An item names **who is harmed** if it is not done —
a player, a contributor, or a future agent reasoning from a false claim; no harmed party, no
item. Items that wait on a decision that is Jay's say so literally: `[MINE: product]`,
`[MINE: contract]`, `[MINE: dependency]`. Completed rows are marked `[x]` with what was actually
true, committed, and deleted at the next triage. A row is a lead, not a spec: re-derive its
claims against the disc and `HEAD` before working it. No time estimates — sections are ordered
by dependency, and the project's pace is set by top-tier model throughput (Opus 5.5 since 2026-09-22, `CLAUDE.md` § Model tiers), which Jay has accepted.

**Classes and ids spent so far:** `ENV-01`–`ENV-08` environment · `RSH-01`–`RSH-02` research ·
`REC-01`–`REC-08` recon of formats · `TXT-01`–`TXT-11` text renderer · `PIPE-01`–`PIPE-07`
pipeline · `TRN-01`–`TRN-10` translation · `GFX-01`–`GFX-10` textures · `FMV-01`–`FMV-06`
movies · `VO-01`–`VO-07` voice-over · `REL-01`–`REL-03` release.

**Dependency order.** `ENV` → `REC` and `TXT` (parallel; `TXT-04` is the project's go/no-go
trial) → `PIPE` → `TRN-08` → `TRN` → `GFX` → `REL`. `RSH` informs all of it and comes first.

---

## Research

- [x] **[RSH-01]** **Survey how PS1 fan translation is actually done, and adopt what fits.**
      DONE 2026-09-19: `research/ps1-translation-practice.md` (§0–§10, toolchain table,
      sixteen disc questions), with its conclusions folded into the rows below — in-place
      length-preserving patching (`PIPE-04`), xdelta + PPF (`PIPE-05`), PCSX-Redux + Ghidra
      (`ENV-03`, `ENV-04`), one renderer hack per text surface (`TXT-05`), AI disclosure
      (`REL-03`, README § "How the translation is made"). Where it recommends `.po` + Weblate
      keyed on Japanese `msgid`s it is superseded by TECHNICAL principles 2 and 3. Its unanswered
      sub-questions (DMCA history of translation patches, no$psx under CrossOver) are closed
      as *no*: nothing in the plan depends on either.
- [x] **[RSH-02]** **Primary sources read before `TXT-01`.** DONE 2026-09-20:
      `research/renderer-prior-art.md` — a method for finding a PS1 text renderer, the
      instruction-level cost of vertical→horizontal in the PS2 sequel and the PSP port, three
      VWF designs, the what-breaks checklist, Kendrit's PSP dialogue/event spec as a PS1
      hypothesis, and the text-lookup hijack. Read in full: Hilltop's MML2, Racing Lagoon and
      Ghidra videos, slowbeef `pnhack1/2/4/5`, the TraduSquare devlog, the four patch sources.
      Unreachable (404 / no Wayback capture): `pnhack3/6/7` — closed as *no*; reopen only if
      `TXT-05` ends up needing the lookup-hijack design.

## Environment

- [x] **[ENV-01]** **Scaffold the Python project.** DONE 2026-09-20: `uv` project (Python ≥ 3.12,
      stdlib-only runtime), package `boku` with a `boku` CLI, `pytest` + `ruff`, and `make.sh`
      (`import`, `test`, `lint`). Ruff is scoped to project code (`research/` Markdown quotes
      other projects' code and was being reformatted).
- [x] **[ENV-02]** **The import step.** DONE 2026-09-20: `boku import SOURCE [--out DIR]`
      (`boku/importer.py`, `boku/disc.py`) takes `.chd`/`.cue`/`.bin`/`.img` or `$BOKU_DISC`,
      refuses any image whose SHA-1 is not Redump's (checked against redump.org/disc/4890
      itself), guards case-insensitive path collisions and non-import `--out` directories, and
      writes `image.img`, `image.cue`, `manifest.json`, `files/`. 43 tests, each made red on
      purpose; 6 need the disc and skip without it. Measured along the way: `__STR` records are
      XA-*interleaved* (`0x2555`), `.IKI` files being Form 1 video with Form 2 audio between —
      so interleaved files are listed in the manifest, not extracted. Closed as *no*: a
      fallback for images lacking the CD-XA extension (we patch in place, so the image the
      tools re-read always has it; reopen if `PIPE-04` ever rebuilds the filesystem).
- [x] **[ENV-03]** **A PS1 emulator with a debugger on this Mac, and the Mode One core beside
      it.** DONE 2026-09-20 (`research/tooling-setup.md`). Debugger: PCSX-Redux with no window
      (`tools/redux/`) — Lua advances frames, reads RAM, sets breakpoints, dumps the
      framebuffer; needs `-debugger` for breakpoints, `-interpreter` under a retail BIOS, and
      a retail JP BIOS (OpenBIOS never reaches the game). Mode One's core: `tools/libretro/
      run_core.py`, a stdlib ctypes libretro frontend that boots any `.cue` on
      `mednafen_psx_libretro.dylib` with scripted input, PNG shots and save states, ~800 fps,
      byte-identical frames across cold boots; it refuses to run without a real BIOS because
      Beetle would silently fall back to its HLE BIOS. Also installed: armips,
      mkpsxiso/dumpsxiso 2.30, xdelta 3.2.0.
- [x] **[ENV-04]** **Disassembly project for `SCPS_100.88`.** DONE 2026-09-20: Ghidra 12.1.3
      with locally built arm64 natives and `ghidra_psx_ldr`; headless import detects **PsyQ
      4.6.0**, 1,542 functions, 792 named (417 by PsyQ signatures). The database is disposable
      (`work/ghidra/`); the durable artifact is `research/symbols/SCPS_100.88.symbols.tsv`,
      written and re-applied by `tools/ghidra/ExportSymbols.java` / `ImportSymbols.java`, which
      refuse a TSV whose program hash does not match. The setup note's closing claim that RAM
      never matches the file is unresolved and probably a too-early sample (the BIOS shell
      also runs from `0x8003xxxx`–`0x8004xxxx`); it is `TXT-01`'s question Q0.
- [x] **[ENV-05]** **Wire the emulator gates into `make.sh` and test the Beetle runner's pure
      code.** DONE 2026-09-20: `./make.sh smoke [image.cue]` runs both headless boots and names
      any missing prerequisite (emulator, `REDUX_BIOS`, `BOKU_LIBRETRO_CORE`/`_SYSTEM`) instead
      of skipping. `tests/test_run_core.py` covers `to_rgb_rows` for XRGB8888, RGB565 and
      0RGB1555 (expected values from libretro.h's bit layout, padded pitch included), the
      schedule parsers, and the PNG writer against an independent reader; the two unexercised
      pixel paths turned out correct.
- [x] **[ENV-06]** **The memory-card save format and a corpus of saves.** DONE 2026-09-22:
      `research/save-format.md`; `boku save`, `./make.sh save`/`saves`/`boot-save`; 30 mornings
      (Aug 2–31) + 5 ending-band cards, generated from a new game's RAM and never tracked (a
      card carries the game's icon and title strings). Proven on Beetle (day03, day25,
      ending-oti3-15stars, clock checked) and loaded on Redux (day25). The ★ → epilogue rule
      is decoded from `ending_pick` (13–15 `OTI03`, 10–12 `OTI01`, 7–9 `OTI00`, 4–6 `OTI02`,
      0–3 `OTI04`). The cards are date-correct but carry no earlier day's story flags;
      flag-gated scenes take `--flag`. Closed as *no*: branch-point saves with a real
      playthrough's flags — reopen when a lane cannot reach a scene with `--flag`.

- [x] **[ENV-07]** **Saves any contributor can play from.** DONE 2026-09-23:
      `./make.sh duckstation-cards` → `work/saves/duckstation/`: the mornings of August 2–31 on
      two cards, the five ending bands on August 31 (PLAYTIME shows the stars), five finished
      games; `boku save --finished`. The finished marker is decoded — the summary day is 31 or
      more (`0x8007B65C`) — which opens Summer Memories; a New Game from such a card is a
      second playthrough (`0x80025914`, `E0404`/`E1503`). August 31 has no evening: from its
      morning the day chains into the ending movie (~9,500 frames of ○). The DuckStation
      per-game shared-card route is in `research/save-format.md` and TECHNICAL.md (from source, not
      run). Proven on Beetle.
- [x] **[ENV-08]** **Bug sumo, the mantis, the shortcut and its well.** DONE 2026-09-23: the
      cage record and fighter formula (`research/sumo.md`, `boku/sumo.py`, `boku save --bug`)
      with a Beetle bout whose fighter matches the prediction; the mantis chain (stage
      `0x8003D27A`, flags 64/65/68/69/70); corpus saves `sumo-maxed-cage`, `sumo-mantis-ready`,
      `shortcut-open` (`boku-bug-sumo.mcd` slots 1–3); `./make.sh sumo-bout --mantis`,
      measured through `E1754` to `E02`; the shortcut's well is `E08`, and its second
      examination plays `E2405.0` — a voiced line with text, found by `./make.sh examine`.
- [x] **[ENV-09]** **The emulator verbs find Beetle without an environment variable.** DONE
      2026-09-25 (`02d56bf`): Jay's `./make.sh duckstation-cards` stopped at "run_core: no core".
      `tools/libretro/emulator_paths.py` resolves `BOKU_LIBRETRO_CORE` / `BOKU_LIBRETRO_SYSTEM` /
      `REDUX_BIOS` — a set variable wins (and must exist), else retro-trainer's `config/` under
      `$BOKU_MODE_ONE` or `~/Dev/retro-trainer`, else a message naming the variable, the path
      looked at and `research/tooling-setup.md` § "Where the emulator verbs find the core and the
      BIOS". Measured: Jay's command with all three unset writes the 5 cards; `./make.sh smoke`
      passes both gates unset. Harmed (was): Jay and every contributor making saves.
- [x] **[REC-01]** **`BOKU.BIN`'s directory.** DONE 2026-09-20: `research/boku-bin.md` +
      `research/data/boku-bin-members.tsv` (regenerated by `work/rec01/build_map.py`). The
      directory is only in the executable — `g_cd_dir` → parallel `lba[]` (absolute disc LBAs),
      `size[]`, `name[]`, 305 entries, no flags — and `BOKU.BIN` is a raw sector range of the
      dev CD image: 275 sector-padded files plus two zeroed directory placeholders. `EV`,
      `H_FILES`, `M_FILES`, `NIKKI` are sub-archives indexed by sibling `.SEC` members; 1,302
      leaf members tile all 53,371 sectors exactly; all 2,606 jPSXdec TIMs fall inside one
      member each; nothing is compressed. Text: 5,553 candidate lines but only **2,078
      distinct strings**, in map packs' child 1 (4,119), `EV` scripts (1,341), `HHON.OVL` (58)
      and the executable itself. Seven members are **code overlays**. What it left open is in
      `REC-02` (unknown members, the `NIKKI.SEC` consumer) and `REC-03`/`REC-05`.
- [x] **[REC-02]** **What `REC-01` left unexplained in the containers.** DONE 2026-09-20:
      `research/loading-and-memory.md` + `research/symbols/loading.symbols.tsv`. The ten unknown
      members, the two `g_cd_dir` words and the executable's nine computed-index loads are
      identified. Map-pack siblings refer to child 1 **by event id only**, so growing text
      means rewriting the pack table and nothing else inside the pack. RAM is a fixed bump
      arena laid out once at boot, and it is full: a map pack loads at `0x801B3DF4` and
      `map_commit` traps if child 6 starts past `0x6400` (tightest map `M_H06001`: 2,664 bytes
      of head room; median 12,624); `EV` members share one `0x4000` buffer, up to 10 per map;
      overlays load at `0x80079A08`–`0x8008F3A4` (`MUSI.OVL` has 10 bytes free), and a load writes whole sectors, up to `0x8008FA08`. All arena
      addresses are computed from pack offsets, not observed — `PIPE-03` carries the check.
      Closed as *no*: the 18 computed-index load sites inside overlays (no text-bearing member
      is unaccounted for; reopen if `PIPE-01`'s extractor finds a member nobody loads).
- [x] **[REC-03]** **The text tables, completely.** DONE 2026-09-20: `research/text-format.md`
      + `research/data/text-sites.tsv` (from `work/rec03/text_sites.py`, whose `--selftest`
      breaks the walk three ways and sees the gate fire). All dialogue is in **event blocks**
      (`u32 n; u32 off[n]`: header, trigger, bytecode, then voice-key/text pairs); map-pack
      child 1 is a table of `{u16 event_id, u16 block_len, u32 off}` + blocks; an `EV` member
      is one bare block, byte-identical to the map copy. Bytecode names text by message index
      (`0x0D` XAMSG, `0x0E` MSG, `0x0F` XA, `0x21` SELECT — SELECT text has no terminator; its
      line count is in executable tables). The rest is `u16` arrays in the executable and the
      `HHON`/`ZUKAN`/`TAKO`/`MUSI` overlays. Only three control words exist: `0x8000` end,
      `0x8001` newline (= next column), `0x8002`+timer page break (voiced lines only); the
      word after each newline/page break is `0x0000`, drawn as glyph 0. **6,183 physical
      sites = 2,977 logical lines = 2,426 distinct strings = 74,584 glyphs**; copies of a
      logical line are always byte-identical. A page is at most 3 columns × 16 glyphs. The
      rewrite list for a grown line and the per-member slack are in the spec.
- [x] **[REC-04]** **The glyph table, derived from this disc.** DONE 2026-09-20:
      `research/font.md` + `research/data/glyph-table.tsv` (1,512 slots, every inked cell read
      by eye; the PSP table was wrong at 9 ids and has nothing above 1023). The font is one TIM
      — `ONMEM.BIN` child 2, 252×224 4bpp used as **four 1-bit planes** of 12×12 cells, 21
      columns — uploaded once at boot to VRAM (768,0) by `onmem_init` → `tim_upload`, then
      only in VRAM. `glyph_draw` (`0x8002BA2C`) maps an id to column/plane/row and emits three
      SPRTs (glyph + two shadows). Ids above 1023 are just more slots of the same sheet.
- [x] **[REC-05]** **Event scripts, as far as translation needs them.** DONE 2026-09-20:
      `research/event-scripts.md` + `research/data/scenes.tsv`, `scene-edges.tsv` (from
      `work/rec05/scenes.py`; its `--selftest` mis-sizes opcodes and watches hundreds of events
      desync). Instructions are `u8 opcode, u8 size_in_words, operands`, dispatched by `ev_run`
      (`0x8002D23C`) through `g_ev_ops`; 36 opcodes in use, Hilltop's PS2 names fit. Branches
      are only JMP / JMPM (current map) / JMPE (`flag >= v`); SELECT writes the choice to
      `g_flags[255]` and JMPE tests it; PROG calls 76 native routines (day/hour reach scripts
      that way; the dinner quiz opens 83 messages by a day-computed index). All 677 events
      walk clean: 2,686 text entries, none dead, 24 SELECTs (+61 in quiz tables), 762
      conditional branches. Event id ÷ 100 is the day; block entry 1 is a condition tree over
      hour/day/flags/map; map-pack child 0 holds placement records with the trigger type. The
      speaker is an operand of XAMSG/XA (actor slot = character), and the 12-byte voice key is
      `{start sector, end sector, channel, file}` into `BOKU_XA.XAM`, verified against the
      disc's XA subheaders for all 2,163 keys. Not in the data, so `TRN-02` needs it from the
      walkthroughs: which real place each map base is, and what individual flags mean.
- [x] **[REC-06]** **Text outside the tables.** DONE 2026-09-20:
      `research/text-outside-events.md` + `research/data/text-arrays.tsv`: **34 arrays, 301
      strings, 4,492 glyphs**, each bounded by walking it the way its reader does (all 58
      `glyph_draw` callers traced; `REC-03`'s 25 hand-set ends all reproduced; its 103-line
      array is really five, three read by `TITLE.OVL`; five more raw arrays found — fortune
      results, bug-sumo hints and ranks, the kite crash banner, yes/no). Six functions draw
      labels from glyph ids hard-coded as **instruction immediates**, four write digits as
      `0x34 + d`, the memory-card title is Shift-JIS assembled in `TITLE.OVL`, and the
      PCload/PCsave strings are dead code. The picture diary's text is only in the page TIMs;
      `nikki_select` (`ZUKAN.OVL`, `0x8007A180`) consumes `NIKKI.SEC`, and only the date strip
      is composed at run time.
- [x] **[REC-07]** **Is there tamper detection on data?** DONE 2026-09-20, `research/integrity.md`:
      **no.** All 85 load sites hand raw reads straight to parsers; no CRC table or polynomial
      exists in any code file; overlays are entered by fixed `jal`. The warning string is the
      stock SCE mod-chip check (drive commands and TOC only, reads no file data). The save
      body has an additive sum in `TITLE.OVL` that covers no text. A patch recomputes nothing.
      Static analysis only — `TXT-04` is where this meets a modified disc.
- [x] **[REC-08]** **Census of Japanese inside textures.** DONE 2026-09-20:
      `research/textures.md` + `research/data/texture-census.tsv` (from `work/rec08/extract.py`).
      2,607 TIM occurrences = **824 distinct images**, every one looked at on a 1:1 sheet;
      **180 carry Japanese, 17 maybe**: 94 picture-diary pages, 48 insect/fish/item book, 18
      signage/labels in backgrounds, 17 title/menu/UI, one each calendar, font, credits.
      Reconciles exactly with jPSXdec's index. **Diary text is baked into the pages** — each
      a 240×192 8bpp TIM: crayon art on top, the day's entry typeset in ruled vertical columns
      on flat paper below, the day numeral composited from 31 tiles in `NIKKI_W.BIN`.
      Difficulty: 129 easy, 20 medium, 41 hard (signage painted into backgrounds, stylised
      covers), 6 unknown.

## Text renderer — the central risk (TECHNICAL § "The central risk")

- [x] **[TXT-01]** **Trace one dialogue line from its id to pixels.** CLOSED as *no*, 2026-09-21
      (Jay: "I can't tell how valuable this is now that we've actually rendered scenes and I've
      played the game with actual translated text"). What the trace was for — proving the id →
      bytes → renderer chain — is proven by `TXT-05`'s renderer drawing days 1–7 from their ids;
      the static findings live in `research/text-renderer.md` and `renderer-runtime.md`.
      Reopen trigger: a line on screen that differs from what its id's bytes say (extract and
      pixels disagreeing) — that is the one thing a trace would still find.
- [x] **[TXT-02]** **What the existing font offers.** DONE 2026-09-20 (`research/font.md`,
      `research/font-candidates.md`): full A–Z/a–z/0–9 and common punctuation in 12×12
      full-width cells, ink widths 1–9 px, left bearings 1–5 px; missing `' " - ~ $ [ ]` and a
      horizontal `( )`; Japanese punctuation drawn for vertical lines. Counted against the
      structural text, arrays and code immediates, **1,333 ids are in use and 179 are free**
      (155 inked-unused + 24 blank; 347 if the sheet grows to its 1,680-slot VRAM ceiling) —
      not the 583 a heuristic scan suggested. English needs about 12 new cells. The font's
      VRAM page is unchanged across five sampled moments; row 240 is in use.
- [x] **[TXT-03]** **Choose how English gets on screen.** RULED 2026-09-20 (Jay, from
      `work/txt06/DECIDE.png`): advance model **(c1)** — the width table with the font sheet's
      Latin cells left untouched, each glyph drawn at its native bearing — ranked best, with
      (c2) re-aligned "very close" second, then fixed 8, then fixed 14. Band: "as little space
      as possible" — **H = 37 at Y = 203, pitch 11, pen y 205**, and the translucent
      ("additive") look is welcome; he is not confident everything fits, so the lint under that
      box decides and reports rather than the band silently widening. The build adopts these
      as defaults (`TXT-05`).
- [x] **[TXT-04]** **The trial: one English line on screen in a rebuilt image.** PASSED on
      PCSX-Redux and on Beetle PSX, 2026-09-20 — **the approach is a go.** `./make.sh trial --line
      'M_H02001.BIN:c1:0:171.0' --text "Hello, Boku!"` (`boku/trial.py`) patches seven EXE words
      (direction, pen position, the `band2` panel: y=168, h=72) and every copy of the opening
      line, in place, 4 sectors, EDC/ECC regenerated; the image boots cold with no RAM pokes,
      `dialog_open` is called with (24, 176, 0), "Hello, Boku!" draws left to right in the band
      with the scene intact above it, the following Japanese lines wrap with their one-cell
      indent, the next-page arrow sits inside the band, and the arrival sequence autoplays to
      the same end as the stock disc. No integrity check fired (`REC-07` held). On Beetle PSX (Mode One's core, retail BIOS, `tools/libretro/`) the same
      image shows the same frame: English, horizontal, in the band.
- [x] **[TXT-05]** **The renderer patch.** The DIALOGUE surface is prototyped and runs on both
      emulators (2026-09-20, `asm/dialogue.asm`, `tools/vwf/build_prototype.py`,
      `research/vwf-prototype.md`): 21 EXE words — direction, pen, the band, line pitch, the
      nine-slot table-lookup advance (no trampoline), the width table and select hooks in
      the dead PC-host island `0x8005CD44…0x8005DCF8` (the heap-raise gap is zeroed by
      `MUSI.OVL`'s whole-sector load, measured 2026-09-23; `boku.build.check_resident`
      refuses any executable edit in the overlay region); every site carries its retail instruction and the
      build refuses unless the `ORIGINAL=1` arm reassembles the EXE byte-identically. The font
      sheet is rebuilt at build time from the contributor's disc with Latin cells
      left-aligned in FREE cells (cells the Japanese script draws are never moved, and a gate
      refuses if one would change), so untranslated pages are unchanged; the typeface is a
      `--font` input. Real lines measured to the pixel against the mock-ups. **More proven since** (`asm/vwf.asm`, `select.asm`, `title.asm`): SELECT menus draw as
      horizontal rows in the band with a cursor beside the row, up/down and ○ working (proven
      on PCSX-Redux via a scripted map change; not yet reached on Beetle — Boku's room is
      sealed on day 1 and the game is tank-controlled); the title / no-file / config screens on
      both emulators; the ORIGINAL gate now covers the EXE and four overlays; the `...` fix.
      `tools/vwf/build_prototype.py --days translation/days` lays real day files in place: **67
      of 764 reviewed lines fit in place, 697 need the reinserter's growth** — so the next step
      is the build moving into `boku build`, applying the VWF EXE words and rebuilt sheet as
      byte edits beside the reinserter and relocation. **Done since (2026-09-20):** that
      integration (`./make.sh build-days` → `boku build --vwf`); SELECT reached on Beetle;
      the em dash and `...`; speaker labels in the original's form — `Uncle「…」`, the four
      bracket glyphs added to the sheet, inserted as text by `boku.build.lay_out_message`
      from what the Japanese drew (`original_marks`), so the renderer is unchanged; the map
      work area raised from `0x6400` to `0x7C00` (`asm/arena.asm`: two bump sites, the
      `map_commit` bound, the swap length) with the stack low-water measured at 4,016 bytes
      on both emulators and the assembler refusing a raise under 1.5× that — `M_H06001`'s 43
      lines now lay out; Jay's band and advance rulings are the build's defaults. Under that
      band the advance model was decided by lint (`TXT-07`): **c2**. **Round 2 (2026-09-20,
      after Jay played it on DuckStation):** the band sat partly below the rows DuckStation
      shows — the game programs all 240 rows but the emulator's default crop stops near row
      232 — so it moved to Y=191 with the next-page marker (two sprites, two sites) moving
      with it; `「『` got a left bearing and `」』` were tightened; the choice cursor was the
      game's hand turned a quarter turn at build time (replaced by the game's own
      right-pointing hand, `TXT-10`); `H06001` (day 15 morning) loaded with child 6 past the old bound; the aunt's
      evening lines drawn from a relocated EV member on Beetle. The card-check and settings
      screens Jay saw in Japanese are `TITLE.OVL` renderer text with no translation rows —
      the array/overlay half of `TRN-04` (308 lines on six surfaces, `boku coverage` lists
      them as `not-event`), not a renderer miss. **Done 2026-09-22:** the controls-help screen (START) and
      the item-name walkers proportional, proven on both emulators; descriptions, captions,
      captions and fishing messages seen on Beetle 2026-09-24, kite names in tests only;
      untranslated text on every hooked menu keeps its original 12/10-px spacing (the
      card-check screen had been drawn at 14); step code in the `dbg_font_init` space, shared
      with the movie loader (`asm/walkers.asm`; the renderer's routines live in the dead 8×8 font, `asm/vwf.asm`; `tests/mips.py` runs the game's walkers on the
      patched EXE). **Done 2026-09-23:** summer-memories labels 0–4 and item descriptions (wrapped
      to their box by the build) proven on both emulators, reached with generated cards /
      pokes; the card screens' two answers (surface 18): the row is written `Yes | No` and the
      build rewrites the drawer's split and count in `TITLE.OVL`, proven on both emulators.
      **Done 2026-09-23:** surfaces 9 (`sysmsg_draw` returns a pixel width and
      its five callers take it), 11 and 25/26 installed and tested instruction by instruction
      in `tests/mips.py`; not reached on screen (the cage HUD needs a caught insect; fishing
      and sumo need days of play). **Bug sumo DONE 2026-09-24:** the hint and rank board drawn as banners
      (`asm/musi_text.asm`), the notebook's names end at the item after them
      (`vwf_name_before_sym`), proven on Beetle; surfaces 25/26 and the debug screen's names are
      unreachable in retail (`research/sumo.md` § The desk's text). **Left to do:** screen
      proof of surfaces 9 and 11, and the bout's names right-aligned in their 96-px field
      (`0x8007D89C`, `0x8007D940`) on screen; the notebook's size badge → `TXT-12`; the insect box DONE 2026-09-24 (`96f45b0`; layout RULED by Jay 2026-09-24): English in
      rows, Japanese in its columns; the grid shows the whole entry (11 px rows from y 16), the
      notebook 8 rows ending in "..."; seen on Beetle with its delete prompt
      (`asm/hhon_resident.asm`, `boku/insect_box.py`); the remaining fixed-pitch
      surfaces 9 (with its return-value change), 11, 25, 26, and summer-memories label 5;
      the stack under a real save, a sumo bout and fishing (measured 2026-09-23 on Beetle:
      free roam 0x228, item menu 0x3DC8 (one 0x3CA8-byte frame in mode 4 / TAKO, never
      coexisting with the level-C scratch — `research/vwf-prototype.md` § "The map work
      area"), insect box 0x350, kite 0x348, forced MUSI 0x320 (not a bout's depth),
      forced mode 15 0xFB0 — none past the 4,016 bytes the map-area raise was sized for).
      Done 2026-09-23: the computed-id `glyph_draw` sites — 59 draw sites, 25 ids proven by
      a path-following scan, the 24 unresolved each named with what it walks
      (`tests/test_real_glyph_sites.py`). Step routines share one width lookup;
      walker island 276/424 bytes used. (Round 3, 2026-09-21: the
      "head drawn over the band" was a misread of a zoom — measured, the head is behind
      the band and the ordering table is stock; the select box now derives from the row
      geometry; a text-only test refuses overlapping `.org`/`.area` blocks, the trap that
      silently reverted one patch during the round.)
      Original row: Per `TXT-03`: armips source in the repo, horizontal
      advance, per-glyph width table, wrapping inside the existing box, free space located in
      the executable (it is exactly `0x80000` bytes — check the tail and dead debug code). Every
      patched site documented with what the original instruction did. Menus and other
      non-dialogue draw paths from `REC-06` are separate sites and are enumerated here, not
      discovered at release — every comparable project needed **one hack per text surface**, and
      every `strlen`-based centring or right-align routine is wrong once widths vary. Free space,
      measured (`research/text-renderer.md`): raising `g_heap_base` frees 1,116 bytes already
      in the file; ~3.1 KB of unreferenced code islands (620 contiguous at `0x80012E04`, the
      712-byte `dbg_font_init`); probably the ~2 KB in-house debug printer. Not available:
      PsyQ `Fnt*` (not linked), the PS-X header (never reaches RAM), zero runs (live BSS). Every injection inside an armips `.area`
      so overflow fails the build. Consider writing the new routine in C (`.importobj`). Harmed: the player.
      **Done 2026-09-24 (`9236d0a`):** the bout's names — the opponent's right-aligned name fits
      at every width; on Boku's row the date reads "Caught 8/9", drawn 8 px further right, and an
      unmarked catch number sits 3 px off the name (worst case seen on Beetle, every fighter
      tested in `tests/test_real_date_labels.py`); surfaces 9 and 11 proven on Beetle, label 5 by
      forcing, 25 and 26 unreachable; the stack under a real save 0xFB0 (= the 4,016 budget),
      under a bout 0x2E8, under fishing none (scratchpad) — `research/vwf-prototype.md` § "The map work area".
- [x] **[TXT-12]** **The exchange notebook's names under the size badge.** DONE 2026-09-24
      (`5e9a924`, `48e573c`; RULED by Jay, §14 and §14.1 — no second face): the notebook draws its
      own shorter names in the normal font — "Miyama Stag", "Giant Stag", "Little Stag", "Saw
      Stag", "Red-leg Stag", "Rhinoceros" — as `arrays.txt` rows `exe@8003D2E0.<n>@exchange`
      (`boku.exchange_notebook`); every other screen keeps the full names. A resident list (an
      index by fighter type, then one name per line) read by `vwf_exchange_entry`. Measured on
      Beetle: the pink badge covers x 140–171 with its shadow, leaving 98 px from x 173; every
      fighter with the pink badge seen clear; Flat (98) and Oni (94) keep their full names.
      Harmed (was): the player.
- [x] **[TRN-12]** **"Stuff" for "Belongings" in every menu.** Jay, 2026-09-24 (§17.9): "a more
      'childish' word". DONE (`cc6adb4`, `431e70d`): the Summer Memories menu, the controls help
      line and the bag's and desk's balloons; Saori's "a lady's belongings" (`E1960.3`) is
      dialogue and keeps it; `test_no_menu_calls_boku_s_things_belongings` holds it; seen on
      Beetle. Harmed (was): the player.
- [x] **[TRN-13]** **The insect box's page pencils: "Prev" / "Next".** DONE 2026-09-24
      (`e5b046f`; Jay's §17.8e): both in the game font, proven on Beetle; the one-font test has no
      exception left. Harmed (was): the player.
- [x] **[TRN-15]** **The bug-trading notebook says "Trade" throughout.** DONE 2026-09-24
      (`06f4c4f`; Jay's §23b): the exchange balloon and the plate beside the two cards' arrow say
      "Trade", matching the cover's "Trading"; the plate widened 10 columns (pairs keep its
      checkerboard's phase) and its sprite width in `MUSI.OVL` follows, checked by its texture
      test; on Beetle. Harmed (was): the player.
- [x] **[TRN-11]** **Jay's 2026-09-24 wording rulings** (`work/review/decisions.html`), all applied 2026-09-24:
      §8b and §9 DONE (`136d26f`, Beetle): the card message "The MEMORY CARD has no
      free blocks." on one row (the two-row machinery removed); "Specimens+Cage" in the menu's
      own font (103 px of 109);
      §10, §15, §17 DONE (`431e70d`, Beetle): records 10.1a, 10.2a, 10.3b
      ("Caught 8/16"), 10.4a, 10.5b ("Worth as many as"); the attendance footer "Have a healthy
      summer!" (Sprout — the game font is 142 px for 104); balloons "Stuff", "Make" ("Make It"
      does not fit) and "Take // Out" in the game font; §19b and §20b DONE (`0017485`): the diary's first page "staying at Uncle's
      house" (glossary 居候 split: "staying at" for Boku, "freeloader" kept in Moe's tease
      `E0832.2`), "Uncle's Pond" for Ojioji Pond. Kept as built: §12a the tanka slashes, §16a
      "Production and Copyright", §11 the beach sign (painted in the game's own glyphs, doubled).
      Harmed: the player.
- [x] **[TXT-06]** **The font.** RULED 2026-09-20 (Jay): "The game sheet is good enough and I
      like using the original if possible." No replacement typeface; the ~12 missing
      punctuation cells are placeholder art today — `TXT-08`. No new dependency.
- [x] **[TXT-08]** **Real glyphs for the punctuation the sheet lacks.** DONE 2026-09-21
      (`tools/vwf/placeholder-glyphs.txt`, `research/vwf-prototype.md` § Round 3): the
      sheet's own `. , : ;` sit on rows 7–8, a row above the Latin baseline, which is the
      floating dot Jay saw; they are redrawn at the sheet's weight on the baseline into free
      cells, `' "` as raised comma shapes, `- — ( ) ~` were already right. The harvest
      candidates (Ark Pixel 12, Galmuri) set lighter dots than the sheet's `?`/`!`, so no
      cell is harvested and no licence is owed; every cell in the file is our own art, and
      the loader refuses any advance that does not cover ink plus shadow. Checked in the
      game beside the sheet's letters. Original row: redraw or harvest (Jay, 2026-09-20).
- [x] **[TXT-09]** **Hold voiced pages long enough to read.** CLOSED as *no* (Jay, 2026-09-22,
      after playing): the game already holds a page — pressing confirm stops auto-advance and
      the line stays up with the voice audible; only the long lines were ever hard, and they
      now fit. Reopen trigger: a playtester who cannot finish reading with confirm held.
- [x] **[TXT-07]** **Measure what each box can hold.** DONE 2026-09-24: every surface's box is in
      `research/data/text-boxes.tsv`, measured on Beetle or read off the code, and enforced by
      the build and `boku lint` — the dialogue band (c2 advance, three lines under Jay's band;
      `research/vwf-prototype.md`); select rows; controls help (three bottom rows); memory-card
      messages (`.3` reworded to one row, Jay 2026-09-24); config and summer-memories labels; item names and their
      one-line versions (Jay, 2026-09-24); descriptions, captions and fishing messages (option
      c, Jay, 2026-09-24); kite names; the tackle screen; the cage HUD (date a row down); the
      fish-catch title (centred, `asm/hud_resident.asm`); the insect box (grid and notebook);
      bug sumo's boxes. `boku lint --encoder cellmap`: 0 errors; `build-days`: 0 refused.
      Harmed (was): the player, by text that overflows; the translators, by limits found late.
- [x] **[TXT-10]** **The hand cursor on button screens.** DONE 2026-09-23: the select passes
      `a3 = 1` to the hand drawer `0x80042B64` (`asm/select.asm`, `SEL_CURSOR_SIDE`), which
      draws the game's own right-pointing hand (ONMEM sprite 0); the build no longer edits the
      shared sprite table or sheet, so every other screen draws the retail hand. Proven on
      Beetle: the `E0112.1` Yes/No, the settings and load Back buttons pointing down as
      retail.
- [x] **[TXT-11]** **Japanese left on the title and save flow.** DONE 2026-09-23:
      `exe@8003D5F0.5` reworded to fit its 265-px box ("There is no file that has finished
      this game."), English on Beetle; the title, load and new-game screens swept on Beetle —
      no text-side Japanese is left (extras `exe@8003DA00.1` is now "Specimens+Cage", `TRN-11`); the rest is textures (`GFX-07`). DuckStation's window title comes from its
      own database by serial (the localized name, on by default); the per-user overrides are in
      `research/tooling-setup.md`.

## Pipeline

- [x] **[PIPE-01]** **Extraction to stable line ids.** DONE 2026-09-20: `./make.sh extract`
      (`boku/archive.py`, `events.py`, `arrays.py`, `sites.py`, `glyphs.py`, `extract.py`) reads
      the import and writes `disc/script/` in about a second, byte-identical across runs and
      hash seeds: `lines.jsonl` (2,987 logical lines — id, kind, speaker, voice key, tokenised
      Japanese, page/column layout, every physical site, capacity facts such as "pages fixed
      by voice"), `scenes/E<id>.json` (where/when, cast, flow graph, hand-overs, dinner-quiz
      days), `arrays.json`, `index.json` (written last, as the completeness marker). One id
      names every copy of a line (EV member, each map-pack copy, exe-resident blocks) and the
      extractor asserts the copies are byte-identical. Gates: the port regenerates all five
      tracked research TSVs byte-for-byte (`./make.sh research-tsv`); decode→encode is exact
      over all 6,193 sites; counts are parsed out of the research notes; and **parse →
      serialise is the identity for all 4 `.SEC` indexes, 1,106 packs, 555 child-1 tables and
      2,352 event blocks**, with `Block.replace_entry` / `BlockTable.replace` as the
      reinserter's primitives. Reviewed twice (`~/.claude/session-notes/boku-ps1/`).
- [x] **[PIPE-02]** **The committed translation format.** RULED 2026-09-20 (Jay: "The tab format
      is fine for now"): the format `translation/days/README.md` documents — one file per day plus
      `shared.txt`; tab-separated line id, speaker, English; `//` page break; `[SEL]` rows with
      `|`-separated fields, the question first; `(voice only)` rows; `#` notes. `boku/translation.py`
      is its loader. Hand-writable, as TECHNICAL § "The translation pipeline" hopes.
- [x] **[PIPE-03]** **Reinsertion.** DONE for what a row can be (2026-09-21). Every physical copy of
      a changed line is rebuilt bottom-up with the original pad bytes carried back (null round
      trip exact); the measured limits refuse with numbers at the boundary (`0x4000` EV block,
      the map work area — now `0x7C00`, `TXT-05` — sector slack, array growth, SELECT line
      count); a member that outgrows its sectors is relocated by rebasing its container into
      the 765-sector arena, re-using runs its own movers vacate (`boku/reinsert.py`,
      `boku/relocate.py`, `research/relocation.md`); proven on Beetle with days 1–7 in the
      image (59 members moved). **What the old text meant by "the whole script fits":** a
      *projection*, not a measurement — the disc's own page sizes inflated by the English-to-
      Japanese ratio of the translated sample, under which 181 of 622 members would outgrow
      their sectors and all of them still place using 456 of the 765 arena sectors. Nothing
      was known about a translation that does not exist yet. **Standing decision (Jay,
      2026-09-21):** if reinsertion ever fails for space, it is solved with engineering (the
      arena, the work area, the allocator), never by shortening the script. Reopen trigger:
      `boku build` refusing a member for space. Closed as *no*: a
      CLI verb for "does it fit?" — the estimate lives in a test; reopen if a contributor
      needs the answer without pytest. Still open in this row: the per-map EV budget and how
      English divides between the lines of the 113 array sites drawn as groups. Earlier estimate,
      now measured at 174 of 622 members (28%) outgrowing, worst 7,688 bytes over: Estimate from the samples' expansion (2.6 chars per glyph, 5.85 px per
      char): **150 of 632 text-bearing members (24%) would outgrow their sectors**, ~95
      sectors in all, worst `M_G16101` at 6,028 bytes over; only 6 maps would also pass
      `0x6400`, and no page needs more than 4 band lines — the container, not the box, is the
      constraint. Also unchecked: the per-map EV budget (10 members in one `0x4000` buffer);
      how English divides between the lines of the 113 array sites drawn as groups.
      Original row: Encode English to glyph indices under the `TXT-05` renderer's
      table, rebuild text tables and every enclosing container and directory when sizes change
      (`REC-01`, `REC-02`), write every duplicated site, following the rewrite list in `research/text-format.md`
      (block offsets → child-1 table → pack offsets → `.SEC` sizes, `EV.SEC`'s being `u16` →
      sector spill into later `.SEC` fields and `g_cd_dir`). Known limit: an event block loads into a **`0x4000`-byte buffer** and overrunning it
      panics ("event buffer over") — the cap on one event's translated text + bytecode. Map packs:
      child 6 must start below `0x6400` (2,664 bytes of head room on the tightest map). Both
      limits were computed, not observed — confirm them in the emulator with the break
      addresses listed in `research/loading-and-memory.md` before relying on them. When a
      scene does not fit, that note's § "Making room" has four untested mechanisms (raise
      `g_heap_top`; raise the `0x6400` constant, three sites; upload map child 3 before the
      swap, ~8 KB on 483 maps; reclaim 5,120 bytes of dead dev path strings).
      Code-file arrays have no slack: relocate the array and patch its `lui`/`addiu` pairs.
      **Growth is this row's problem, never the translation's**
      (README § "Who this is for"): relocate, use the filler sectors (`PIPE-04`), or write new
      packing/compression and its MIPS decoder. Harmed: the player.
- [x] **[PIPE-04]** **Image build.** DONE 2026-09-20: `./make.sh build-days` assembles the VWF
      (`tools/vwf/build_prototype.py --edits-only` → `build/vwf/edits.json`: 80 verified byte
      runs over the EXE, `TITLE.OVL` and the font sheet, plus the cell map) and runs `boku
      build --vwf … --translation translation/days` — layout in the band with the cell-map
      encoder, reinsertion with growth and relocation, EDC/ECC, atomic, deterministic (same
      SHA-1 twice). Days 1–7 + shared: 708 lines laid out, 310 members rebuilt, 53 relocated,
      511 of 765 arena sectors left; re-extraction shows all 708 correct at all 2,264 copies
      and all 2,279 untranslated lines unchanged. `./make.sh patch` then emits PPF + xdelta.
      Deferred nowhere: the 43 refused lines are one member, `M_H06001`, 628 bytes over the
      `0x6400` work-area limit — `PIPE-03`'s "making room" mechanisms, now in `TXT-05`'s queue
      as the next engineering item.
- [x] **[PIPE-05]** **Patch emit and the round-trip gate.** DONE 2026-09-20: `./make.sh patch`
      writes PPF3 + xdelta + `PATCH.json` (size/CRC32/MD5/SHA-1 of base and result), proven
      against Icarus's `applyppf3` and retro-trainer's Rust applier; `./make.sh apply-patch`
      verifies before and after. The round-trip gate — every one of 6,193 sites reinserted
      through the full rebuild reproduces the original image byte for byte — is a standing
      test, and the null build stays identical with the VWF path in place.
- [x] **[PIPE-06]** **Translation lints.** DONE 2026-09-20: `./make.sh lint-translation`
      (`boku/lint.py`): every id exists in the store and at most once across files; SELECT
      options 1:1 in order (the question row is not an option); voiced page count equals the
      disc's; every character encodable by the chosen encoder (`--encoder stock|cellmap`);
      every page fits the band in pixels through `boku/layout` (label reserve on line 1 only;
      pencil rule for lines 4–5); array lines within their site; and the additive-word check
      from the pilot as a WARNING (list-based, "so" dropped for precision). Agrees exactly with
      the reader's `--check` on the shared facts. Run over days 1–7 + shared with the VWF cell
      map: zero page or SELECT errors; **113 lines use an em dash the prototype cell map lacks**
      (`TXT-05`/`TXT-06`: add the glyph); the two sample files that duplicated day 4/6 lines
      were deleted.

## Translation

- [x] **[TRN-01]** **The style guide and the story bible.** DONE 2026-09-20. `translation/bible.md`
      (setting: August 1975, fictional Tsukiyono modelled on Dōshi, Yamanashi; the cast with
      registers; the month day by day; map bases → places), `translation/style-guide.md` — every
      policy question is now a SETTLED ruling with Jay's words ("Basically, I agree with all
      the recommendations"): Uncle/Auntie with some -kun; itadakimasu/gochisōsama kept; puns
      rendered literally with the Japanese showing; a mix of English and Japanese insect
      names; recommended place names and romanisation, no macrons; narrator per the
      recommendation; "Showa 17" as written; labels parsed in the files, presentation in the
      original's style as an early, revisitable default (the one open default, Q7).
      `translation/QUESTIONS.md` is the record of the rulings; three sample scenes under
      `translation/samples/`. `translation/glossary.md` is committed (Jay, 2026-09-20: "commit it").
- [x] **[TRN-02]** **Scene assembly for the translator.** DONE 2026-09-20: `./make.sh packet
      --day N` (`boku/packets.py`, `boku/script_store.py`) writes one local Markdown packet per
      scene under `work/packets/` — where/when, cast by slot, the flow graph as played (SELECT
      options with targets, edge conditions, hand-overs), every line with id/speaker/voiced/the
      Japanese laid out by page and column/capacity facts, the dinner-quiz day context, the
      day's bible entry, the glossary rows whose source term occurs, the settled rulings in
      brief, and the neighbouring scenes' settled English — plus `--for-review`. Deterministic.
      Finishing it found two real parser defects (an en-dash day range that lost day 10's
      context; glossary rows keyed on the wrong column).
- [x] **[TRN-03]** **Design and pilot the agent workflow.** The PILOT is DONE (2026-09-20): all 27
      day-1 scenes plus `E0001` translated by one Fable agent given the whole scene graph, the
      bible, glossary and style guide (`translation/days/day01.txt`, 86 lines, 120 pages, no
      overflow), then reviewed line by line against the Japanese by an independent Fable agent
      (`~/.claude/session-notes/boku-ps1/2026-09-20-day01-review.md`): fidelity essentially
      clean, structure exact, nine one-line problems, all applied. Verdict: the method produced
      the charter's register. Lessons now in `translation/days/README.md`: keep the `# UNSURE`
      flags (four of six drew a finding); the recurring defect is *additive* words the
      Japanese lacks, so the review/lint pass checks for them. The workflow ran for days 2–7 and shared.txt as
      the same three steps per day — one Fable translator with the scene graph and the bible,
      one independent Fable reviewer against the Japanese, one applier — launched by hand, with
      `boku packet` and `boku lint` now covering the packet and the checks; and the result is
      readable in the game (`./make.sh build-days`, `TXT-05`). A `Workflow` script for the
      three steps is worth writing when translation resumes, and needs Jay's opt-in to run.
      Original row: Fable sub-agents under a dynamic
      workflow (needs Jay's opt-in at launch, `AGT-1`): translate → independent review against
      the source → consistency pass against glossary and neighbours → lint. Pilot on one
      in-game day, read the result in the game, fix the workflow before scaling. Apply what
      `RSH-01` found about LLM game-translation failure modes. Harmed: the token budget and the
      player, if the full run repeats a flaw a pilot would have shown.
- [x] **[TRN-06]** **The scene reader.** DONE 2026-09-20: `tools/reader/build.py` (+ `checks.py`)
      renders a static site under gitignored `work/reader/` from `disc/script/` and the
      translation files — 702 pages: every scene in play order with the Japanese as the game
      lays it out (vertical columns, page waits) beside the English, SELECT options linked to
      their branches, edge conditions, hand-overs, the dinner-quiz tables, a day calendar and
      per-character pages — plus `--check` (unknown ids, ids translated twice, SELECT shape,
      voiced page counts). Read-only over the translation files; reviewed and the findings
      applied (`~/.claude/session-notes/boku-ps1/2026-09-20-reader-review.md`). Superseded by `TRN-14`; `tools/reader/` removed 2026-09-24.
- [x] **[TRN-04]** **The full translation run** — DONE 2026-09-27 (Jay: done once his
      reading questions, `TRN-19`, were applied). A status table, not a churning row (Jay,
      2026-09-21: Fable translation is expensive; he spawns "do the next N days" himself when
      the engineering is ready; this row only records where each unit stands). The whole game
      was translated in one session on 2026-09-23 (`TRN-10`); the earlier draft is tag
      `pre-trn10-2026-09-23`. States, in
      order: **undrafted → drafted → reviewed** (an independent agent against the Japanese)
      **→ checked** (Jay has read it, comments applied) **→ rendered** (the lint's pixel fit and
      the page mock-ups say it would display — `TRN-08`) **→ finalized** (Jay has seen it in the
      game, formatted and displayed correctly). Workflow per unit: `boku packet` (`TRN-08`) →
      translator → reviewer → applier → `boku lint` → Jay.

      Each unit's state is `translation/status.tsv` (format: `translation/README.md` §
      status.tsv); `./make.sh reader` shows it on every section. All units are "checked" as of
      2026-09-27: Jay read the whole translation and his comments are applied (3bfc535; his open
      questions are `TRN-19`); days 1–2 were read by Jay in play on an earlier build.

      Original row: everything `REC-03` and `REC-06` found, through the piloted workflow,
      committed scene by scene. Harmed: the player.
- [x] **[TRN-18]** **Jay's own edits restored where the whole-game run overwrote them.** DONE
      2026-09-25 (`b9f3e2e`): every translation edit of Jay's (found by commit message,
      `QUESTIONS.md`, glossary notes and the decisions page — every commit carries a Claude trailer,
      so authorship can't tell) compared with HEAD; the two the `TRN-10` run replaced, `E0175.0`
      and `E0171.1`, restored in his words; `E0341.4` had been restored by `931e0bb`; the rest kept
      or superseded by a later ruling of his. `translation/locked.tsv` (66 ids) is the record:
      `tests/test_locked.py` holds the translation to it, packet parts name the locked words, and
      `save-event` refuses an answer that drops them. Harmed (was): the player, and Jay.
- [x] **[TRN-16]** **A second-pass translator on the `additive-word` lines.** DONE 2026-09-26
      (`761fcf5`): Jay's 166 flagged lines judged in their scenes by three Opus translators given
      the whole `--game` brief, then checked against the Japanese by an independent Opus judge
      (163 accepted, 3 keeps overturned). 153 kept words are recorded as `# VOICE <id>: <word> --
      <why>` notes (boku.lint `VOICE_NOTE`, honoured by the heuristic; `voice-note` warns on one that
      settles nothing); 13 lines rewritten minimally; none touched Jay's locked words.
      lint-translation: additive-word 166 → 0. Harmed (was): the player.
- [x] **[TRN-17]** **An awkward-English sweep of the whole translation.** DONE 2026-09-26
      (`f307f54`): six Opus readers over the whole game in play order (days, shared, arrays, clips,
      movie cues, texture strings) with the maximal packet; three independent Opus judges checked
      229 proposals against the Japanese — 183 accepted, 38 amended, 8 rejected — applied to 221
      lines; nothing touched `locked.tsv`. `E0175.0` page 2 judged and kept ("play here to your
      heart's content" — Jay's to overrule). Closed as no: the uneven renderings of *daisuki*
      (`E2730.0` vs `E2440.0`, `E0640.0`) and *nakanaka* (`E2050.0`) the TRN-16 judge noted were each
      kept for their scene; reopen if Jay's reading flags them. Harmed (was): the player.
- [x] **[TRN-14]** **One reader for the whole translation.** DONE 2026-09-24 (`trn14-reader`):
      `./make.sh reader` writes `work/reader/index.html` from `boku/reader.py` — one linear
      walkthrough of days 1–31 in play order, shared, arrays, clips, movie cues, every typeset
      texture group (original beside English), the diary and the books: 3,337 items; each id one
      click or `c` to copy, lint findings and translators' notes on their items, each unit's
      `TRN-04` state from `translation/status.tsv`. No comment box (Jay). `tools/reader/`,
      `work/reader/` and `work/reader-review/` removed. 2026-09-25 (`7cec03e`): `./make.sh
      build-days` rewrites the reader after every build; its header names the commit and days
      build it was made from, and says in red when that build lacks what the page shows.
      Harmed (was): the translation's reviewer.
- [x] **[TRN-19]** **Jay's 2026-09-27 reading: his rulings on the open questions.** DONE
      2026-09-27 (bb8275c): *ana-ana-bobon* is "oobly-boobly-bon" (item and all seven lines);
      eyesight converted exactly, 4.0 → 20/5 (`E2120.0`), 2.0 → 20/10 (`E2440.2`); Boku's slow
      taunt "You. Pip. Squeak." (`E3042.3`; the uncle's "Wolf... Girl." kept); *bayoyōn* is
      "Bye-yoyooon!"; Saori's books are "love-and-peace-and-life-on-Mars" (`E1960.6`, `E1962.1`).
      Style guide §§ 7 and 11 and the glossary say so; his picks from the whole reading are in
      `translation/locked.tsv`. Harmed (was): the player, at each line.
- [x] **[TRN-08]** **The packet, redone to Jay's spec, and the comparison.** DONE 2026-09-22
      (`~/.claude/session-notes/boku-ps1/2026-09-22-trn08-comparison.md`): `boku packet`
      writes `system.md` once — the day-file format, the whole style guide, the whole
      glossary, `translation/checklist.md`, the day's summary — plus one part per event in the
      day-file shape (Jay's drop list enforced by test); `boku save-event --order` saves a
      directed translator's answers; `./make.sh mockup` draws every page with the sheet's
      glyphs at the band geometry. Days 1–7 + `shared.txt` were re-translated blind and merged
      per line with the held draft (816 rows: 270 identical, 433 old won, 62 new, 51
      combined); the first run's packet filtered the glossary, and a fair re-run of day 5
      through the fixed packet cut the draft's defects from 32 to 13 and won 1 line of 75
      against the reviewed file — the packet makes a cleaner first draft, review still earns
      its place. The translators' remaining packet findings were fixed in the same stretch.
- [x] **[TRN-09]** **The 308 array, menu and overlay lines.** DONE 2026-09-22/23: the arrays
      packet (`./make.sh packet --arrays`, 42 surfaces) and its translation,
      `translation/days/arrays.txt` — 308 rows, reviewed against the Japanese (16 findings,
      all applied). What reaches the screen is `PIPE-07`'s and `TXT-05`'s: the build places
      only what fits each item's own bytes, and `boku lint` names every line it cannot place.
- [x] **[PIPE-07]** **Array English on screen.** DONE 2026-09-24: every code-file array's English
      is on screen. Arrays that outgrow their bytes move whole (`boku.array_relocate`), into
      resident room or into the one overlay that reads them (`overlay_tail`); regions in
      `research/text-renderer.md` § 6. An item the box gives more rows is split into items of
      its own (`boku.row_split`): the help screen's bottom sentence on three rows (`boku.help_screen`, `asm/help_resident.asm`).
      The insect box is written twice into `HHON.OVL` (`boku.insect_box`). Dialogue may draw
      the sheet's symbol cells (`boku.layout.WithSheetSymbols`). Bug sumo's move names and the
      specimen label are left retail, the arrays never drawn — retail shows the move as a banner
      texture, `GFX-12` — (`boku.arrays.UNREACHABLE`; reopen if a retail
      path shows them). `boku lint --encoder cellmap`: 0 errors. `build-days`: 2,971 laid out,
      0 refused. Seen on Beetle. Harmed (was): the player, who saw Japanese menus around English dialogue.
- [x] **[TRN-10]** **The maximal translation run.** DONE 2026-09-23: `./make.sh packet --game`
      (the whole bible, glossary, style guide and checklist, ~29k tokens, then 599 parts in play
      order) translated in ONE session, days 1–31 plus `shared.txt` and `arrays.txt`, then a
      revision pass over the earlier days (`work/revision-notes.md` in its worktree); nine
      independent reviews against the Japanese found 160 problems — days 8–31 "faithful and in
      voice", the losses concentrated in days 1–7 / shared / arrays where the run overwrote
      reviewed work — all applied, with the voice-only subtitles, Jay's "cafeteria" and the TXT-11
      wording restored (his `E0175.0` and `E0171.1` were not restored until `TRN-18`) (`~/.claude/session-notes/boku-ps1/2026-09-23-trn10-review-applied.md`).
      `./make.sh build-days` lays out 2,908 lines and refuses 96. Earlier draft: tag
      `pre-trn10-2026-09-23`.
- [ ] **[TRN-05]** **Play it.** A full playthrough of the patched game looking for wrong-context
      lines, overflow the lints missed, untranslated stragglers, and tone. Findings go back
      through the workflow, not hand-patched around it. Harmed: the player.

## Textures

- [x] **[GFX-01]** **TIM round trip.** DONE 2026-09-20 (`boku/tim.py`, `boku/png.py`,
      `boku/textures.py`; `boku textures export|import`): parse → serialise is the identity for
      all 2,607 TIM occurrences (824 distinct, matching the census exactly); TIM → indexed PNG
      (the CLUT as the palette) → TIM is byte-identical for every distinct image and for the
      most multi-palette ones under each CLUT; an edited PNG imports only through existing
      palette entries (nearest-entry mapping is a separate explicit helper that reports its
      error) and never changes depth, size or VRAM origins; an edit propagates to every
      occurrence (287 for the most-copied minimap) as verified byte edits the image builder
      applies. PNG I/O is stdlib and checked against libpng.
- [x] **[GFX-02]** **Evaluate the redraw path on a sample.** RULED and closed 2026-09-21. The diary
      pages take the programmatic path with the game's own glyphs (Jay, 2026-09-20: "much more
      plausibly reliable than the untested ChatGPT option"; prototype `tools/diary/redraw.py`,
      `research/diary-redraw.md`); every other text-bearing image has its path in
      `research/textures-plan.md` (138 programmatic, 28 redraw, 1 subtitle, 30 stay). The
      pattern from here (Jay, 2026-09-21): a category that meaningfully exists is handled
      together as its own row — `GFX-04`…`GFX-09` — never as churn on one row.
- [x] **[GFX-03]** **Translate the textures.** SUPERSEDED 2026-09-21 by the per-category rows
      `GFX-04`–`GFX-09` (Jay: no churn on one task). The audit that would have been its first
      step is `research/textures-plan.md`; the rules that stay: redrawn images are tracked, a
      subtitled texture is tracked only as text + placement, originals never.
- [x] **[GFX-04]** **The diaries' engineering.** DONE 2026-09-23: entries keyed by page id in
      `translation/textures/diary.txt` (`nikki@NIKKI_072` — `g_diary_pages[day]` picks a page
      at run time), built by the `nikki@` family (`boku/diary.py`, `boku/texture_text.py`):
      each page re-measured on the contributor's dump (`NIKKI_047`'s shading columns excepted
      exactly), `NIKKI_000` refused, every fit refused rather than cut (five lines, a word
      wider than a line, an undrawable character); the date strip stays (Jay, 2026-09-21);
      `./make.sh textures check` is the per-page lint. Proven on Beetle by
      `tests/test_real_texture_text_beetle.py`; how to reach the diary is in
      `research/diary-redraw.md`. All 93 entries since 2026-09-24 (`TRN-04`); the game face draws its own hyphen (`GameFace.HYPHEN_WIDTH`).
- [x] **[GFX-05]** **Is the insect book's body text already a line?** MEASURED 2026-09-21
      (`tools/redux/book-pokes.lua`, `work/gfx05/`): **no — (a)**. The `MZKAN` spreads are
      `ZUKAN.OVL` mode 13 and draw no glyph; `hhon@5328` is drawn only in `HHON.OVL` mode
      10, the insect *box* — `hhon_entry_draw` on its 60-cell grid screen and
      `hhon_text_scroll_v` as the cage label on the hub, neither over a page; one entry per
      insect id 0–59 plus the unseen placeholder (item 60). Also found: `MZKAN0`/`MZKAN1`
      are the **same 9 spreads** lit for night/day (`zukan_insect_book_load`, hour < 19), so
      the book is 9 pages, not 18. `research/textures-plan.md` § "The 26 encyclopedia
      spreads", `research/text-outside-events.md` § "The insect and kite books". Original
      row: one breakpoint at `hhon_entry_draw` with the book open; decides `GFX-06`'s size.
- [x] **[GFX-06]** **The encyclopedia spreads.** DONE 2026-09-23: all 17 spreads (the insect
      book's 9 in both lightings, the kite book's 8) in English from the reviewed draft,
      `translation/textures/books.txt`; names in the game's glyphs (Bean where the band is too
      narrow), header, level and body in Bean (`boku/texture_books.py`,
      `research/texture-recipes.md` § "The books"); a page that does not fit is refused, never
      cut. Proven on Beetle: both books at page 0. Bean's pitch equals its cell height, so
      descenders touch the next line's capitals; the three longest bodies fill the spread.
- [x] **[GFX-07]** **UI plates and the title menu** — 17 programmatic images: `T_TITLE` **first**
      (four menu lines on transparent, outlined with a drop shadow — Jay, 2026-09-20: "needs
      to be translated early"), `T_CONFIG` value plates, the oval action buttons across seven
      atlases (`SUB`, `M_S01100`, `M_S02000`, `MZ00`, `MZ02`, `SAMP`; multi-CLUT — the
      per-region CLUT lives in the drawing code), the record screens (`FS/PK/TK_WAL`),
      `T_MEMORY`'s heading, `TZICON`, the radio-exercise card (`PK_ITM 0x6c`). Split between
      renderer and texture per screen is tabled in `research/textures-plan.md` § UI. Harmed:
      the player, at the first screen. **`T_TITLE` DONE 2026-09-22** (sprite records widened to 128 px).
      **`T_CONFIG` DONE 2026-09-22**: heading, both value panels, the large selected values,
      the controller chart headings (`boku/texture_text.py` `config_screen`,
      `research/texture-recipes.md` § `T_CONFIG`), proven on Beetle by
      `tests/test_real_texture_text_beetle.py`. **`T_MEMORY` heading built 2026-09-22** ("Summer //
      Memories", `memory_album`), proven at texture level only: seeing it on Beetle needs a
      card holding a finished game, and the finished-file marker is not decoded
      (`research/save-format.md`). Remaining: `FS_WAL` (labels laid out against the numbers
      drawn at run time — needs a card that owns the rod); and the small-type pieces — the
      speech-balloon action buttons and stone back buttons (`SUB`, `M_S01100`, `M_S02000`,
      `MZ00`, `MZ02`, `SAMP`, `TZICON`, `T_CONFIG`'s modoru, and `PK_WAL`/`TK_WAL`, which
      hold only such buttons), and the attendance card `PK_ITM 0x6c` (~65 px beside the
      picture, ~6 px footer type) — where the 12 px glyphs cannot fit — RULED 2026-09-23 (Jay, from
      `work/smalltype/DECIDE.md`): balloons widened to take the game's own glyphs (our 7 px
      "Bean" face where an atlas has no room), the attendance card in our 5 px "Sprout", the
      stone Back buttons bigger and bold (the settings chart headings stay rotated — Jay,
      2026-09-24); clear a flat label's whole area before setting type,
      and on textured stone clear only the ink. **DONE 2026-09-23:** the faces tracked (`boku/faces/`),
      the `btn@` family (`boku/texture_buttons.py`, `translation/textures/buttons.txt`); bold
      "Back" on all ten stones; the diary's "Good // night" balloon widened 4 texels; proven on
      Beetle on settings, load and diary (`tests/test_real_texture_buttons.py`). **Balloons DONE
      2026-09-23:** desk `SUB`, bag `PK_WAL`, kite record `TK_WAL`, kite book
      `TZICON`, bug sumo `M_S01100` (balloons, swap plate, Close board), insect box
      `MZ02`/`SAMP`, proven on Beetle — all in the game font except the insect box's page-pencil
      pair in Bean (2026-09-24, Jay's one-font rule, `tests/test_real_texture_buttons.py`). **Attendance card DONE 2026-09-23:** `PK_ITM 0x6c`
      title and footer in Sprout, proven on Beetle in the bag; the insect book's stone Back
      (`MZKAN.BIN` `0x48`) with the other stones. **Records DONE 2026-09-24** (`cc3a016`):
      `FS_WAL` labels and tackle lists (`rec@FS_WAL.*`) with its stone and balloon, the
      bug-record card `rec@M_S01100.*` (all three copies), and the `T_MEMORY` heading proven on
      Beetle with a finished-game card — `tests/test_real_texture_records.py`. (`M_S02000`'s stone
      is never loaded — `research/texture-recipes.md`.)
- [x] **[GFX-08]** **The images with writing, per image** — DONE 2026-09-24, every image built or left by Jay's ruling. RULED (Jay, 2026-09-24,
      `work/review/decisions.html` §21). Left Japanese: the three book covers (`G8-D`, `G8-M`,
      `G8-T` — "not important and conveys the style of the game in Japanese") and the model-kit
      box `M_I19000`. To build, all programmatic (Jay: an image model changed the font and the
      colours; do it ourselves), committed as new pixels:
      **Saori's farewell note** (`M_I14000`, `G8-I14`) DONE 2026-09-24 (`ba552f5`, `7f1e781`): the
      page mapped upright through its fitted corners, the Japanese refilled from the page's own
      pixels along its rules (the blue lines kept), "Goodbye. / You were / a pretty good / guy." —
      "From Saori" written on the rules in the game's glyphs and carried back (print font and "guy"
      accepted by Jay); on Beetle; `research/texture-recipes.md` § `M_I14000`; **the hunting-association
      board** (`G8-I23`) DONE 2026-09-24 (`ee24b05`): a clean plate refilled from the board (the
      starburst's colours and the bullet trail kept), "DANGER!" / "Homes nearby," / "Fire with
      care!" / "Prefectural // Hunting Assn." in the game's glyphs twice as tall and emboldened,
      on Beetle — tall kept (Jay, 2026-09-24); **the keep-out sign** (`G8-I18`, "Don't // come in!") and **the
      bug-trading notebook cover** (`G8-NB`, "Bug // Trading // Notebook") DONE 2026-09-24
      (`8ec5c76`): marker lettering found by colour, painted out, set in the game's glyphs in the
      marker's own colour, on Beetle (`research/texture-recipes.md` § "Marker signs"); **`MITIM`** — the insect cage's sprites (table `KAGO_UV.BIN`)
      DONE 2026-09-24 (`b3331bc`): the two buttons shown when a bug is picked read "Take" and
      "Back" in the game's glyphs (Jay's ruling); the header's rare-bug starburst reads "RARE!" in
      Bean, its own red, all three frames (the game's glyphs are wider than the burst); on Beetle. Harmed: the player who
      examines the thing and reads nothing.
- [x] **[GFX-11]** **The cage's rare-bug starburst says "Wow!" in the game's glyphs.** DONE
      2026-09-25 (`319f0c2`; Jay's §24b): "Wow!" (29 px) in the burst's red over a dark drop shadow,
      running onto the spikes, the Japanese refilled from the burst's own shading; the `badge`
      recipe refuses a word that would leave the 32×24 sprite. All three frames seen on Beetle
      (each lasts 8 video frames); nothing on the cage screen is in Bean any more
      (`research/texture-recipes.md` § "Buttons"). Harmed (was): the player.
- [x] **[GFX-09]** **The beach notice — reworded.** DONE 2026-09-24 (`86cb8a7`): seen on Beetle,
      the board is frontal wood, painted not captioned, in both map variants (`M_C15000`, which
      day 1 loads, and `M_C15100`). `beach_notice` in `boku/texture_text.py` paints
      `translation/textures/signs.txt` — "High tide / No swimming", worded to fit the part of the
      board on screen (Jay, 2026-09-24) — shifting a line left to end on the last visible column
      and refusing one that still does not fit; texture edits inside a map the translation
      rebuilds are carried into the rebuild (`reinsert.plan(carry=…)`). Proven by
      `tests/test_real_texture_text.py` and on Beetle by
      `tests/test_real_texture_text_beetle.py`; `research/texture-recipes.md` § `M_C15`. (The
      30 images that stay Japanese by the charter need no row —
      `research/textures-plan.md` lists them.)
- [x] **[GFX-10]** **The ending's credits card in English.** DONE 2026-09-23: the epilogue's
      closing card (`OTI00.BIN` `0x261f4`, identical in all five packs) reads "Production and
      Copyright / Sony Computer Entertainment Inc." in the game's glyphs; `M28`'s scrolling
      credits are video and stay Japanese. Proven on Beetle on the ending route
      (`tests/test_real_credits_card.py`, `research/texture-recipes.md` § `OTI0n`).
- [x] **[GFX-12]** **Bug sumo's match textures.** DONE 2026-09-30 (`7497cbd`): Jay, from a bout on
      `boku-bug-sumo.mcd` slot 3. The winning-move banner (a heading and 22 ways a bout ends, set
      on their sides: 16 words of `MUSI.OVL` and the veil), the stamina plate (widened to 56 px for
      the game's glyphs, the bars parted 8 px) and the three rank marks are `sumo@` in
      `translation/textures/sumo.txt` (`boku/texture_sumo.py`, `research/texture-recipes.md` §
      "Bug sumo's bout"). Missed because they are 4bpp sprites in 8bpp TIMs and marks in atlases
      with one census note; a sweep of all 278 non-map TIMs at every CLUT and as 4bpp found one
      more, the kite HUD (`GFX-13`). On Beetle: `tests/test_real_texture_sumo.py`. Jay's look and
      wording choices, ruled 2026-09-30 as built: decisions §§ 25–27 (25a, 25.2a "Winning move",
      26a, 27a). Harmed (was): the player,
      in every bout.
- [x] **[GFX-15]** **Bug sumo's banner: the move's English gloss on a third line.** DONE 2026-09-30
      (`e7c66d9`): Jay's 29b (decisions § 29) — each real technique's banner shows "Winning move",
      its name and its gloss (`sumo@move.gloss-N`, with his shorter "backward pivot", "bouncing
      force", "backward pin", "forward pin"); moves with no gloss sit midway. The strips are
      124×23 on the banner's page and the heading moved to the atlas's third page: 26 `MUSI.OVL`
      words plus the move table and the veil (`research/texture-recipes.md` § "The winning-move
      banner"). The gloss sits 11 rows under the name, one closer than the mock-up, since 12 does
      not fit the page. Proven: the patched routines run for all 22 ways a bout ends, and on
      Beetle a King bout ending in Oshidashi shows "frontal push-out" texel for texel
      (`tests/test_real_texture_sumo.py`). Harmed (was): the player who does not know sumo.
- [x] **[GFX-14]** **Bug sumo's move names, as English sumo writes them.** DONE 2026-09-30
      (`43ac1e6`): Jay ruled the Japanese names stay (English coverage uses them), in the standard
      one-word form — the real techniques are one word, capitalised, in `sumo.txt` and `arrays.txt`
      `musi@2C` alike (Gaburiyori, Uwatenage, Abisetaoshi — the game's misspelt 浴びせた押し read as
      abise-taoshi; Ashihiki kept, not ashitori), held by `tests/test_texture_sumo.py`, proven on
      Beetle (`tests/test_real_texture_sumo.py`). The English gloss he asked to consider is held
      as `sumo@move.gloss-N` (glossary § 4b, sourced), not drawn: a third banner line does not fit
      the texture page without moving the heading (about 30 MIPS words), and four glosses are
      wider than a line — mocked up as decisions § 29 (29a name only, built; 29b heading, name,
      gloss; 29c name over gloss). A b or c ruling is a new row. Harmed (was): the player who does
      not know sumo.
- [x] **[GFX-13]** **The kite-flying HUD's three labels.** DONE 2026-09-30 (`eee1d71`): Wind / Speed /
      Altitude in the game's glyphs, `kite@hud.*` in `translation/textures/kite.txt`
      (`boku/texture_kite.py`, `research/texture-recipes.md` § "The kite-flying HUD"); both packs'
      sheets rebuilt, three `TAKO.OVL` records given the new cells, centred where the kanji were;
      `TBG01` loads from hour 15 (`0x80028FC1`). The rest of the kite screen (△ menu, the crash
      banner) was already English. On Beetle: `tests/test_real_texture_kite.py`, both packs.
      Reviewed against the Japanese; Jay's wording: decisions § 28, ruled 28a as built (2026-09-30). Harmed (was):
      the player flying a kite.
- [x] **[FMV-01]** **The movie-subtitle mechanism.** RULED 2026-09-22 (Jay): **E2** — keep
      24-bit, composite the glyphs in software; the implementation is `FMV-04`. MEASURED
      2026-09-21 (`research/movies.md`):
      `g_movie_table` at `0x80029604` maps `MOVIE n` to its `.IKI` — the opening is id 23
      = `M27.IKI` (4,239 frames), the ending id 24 = `M28.IKI` (4,194 frames, unskippable),
      **the only ending movie**. The player (`movie_run`) is a blocking loop: `DecDCTin`
      mode 3 → **24-bit RGB**, slices `LoadImage`d from a DMA callback, never the OT; the
      frame number is in hand every frame (`movie_frame_volume`'s `a0`); the loop idles on
      the ring most of each frame; the font page and CLUTs survive playback. So the GPU
      cannot draw text on the frame as shipped (16-bit words over 3-byte pixels). Three
      ways, costed in § 3–5: **E1** switch playback to 15-bit (37 listed words) and draw
      cues with the VWF renderer into a private OT before the flip — movies band; **E2**
      keep 24-bit and blit 1-bit glyph masks into the slice buffer in `movie_dctout_cb` —
      picture untouched, ~3× the asm, interrupt context; **burn** with jPSXdec (installed;
      ffmpeg cannot decode IKI video) — frames already at the 8-sector ceiling, 45 dB on
      one measured frame, ~16 KB of patch per touched frame (80–135 MB). Cues for E1/E2 live
      in the relocation arena, keyed by frame. Original row: find the per-frame path
      or the burn cost (Jay, 2026-09-20: the opening "definitely needs subtitles", reversing
      TECHNICAL § "What gets translated" row 3; split into three rows 2026-09-21).
- [x] **[FMV-04]** **Subtitles in the movie player (E2).** `research/movies.md` § 3 E2: hook
      `movie_dctout_cb` before its `LoadImage` and blit the current cue's glyph pixels into
      the 24-bit slice buffer (white on the glyph mask, dark on the outline mask); 1-bit
      masks derived at build time from the same PNG the sheet is built from; the frame
      number captured at `movie_frame_volume`; cues per movie as `{start, end, text}` rows
      in a blob in the relocation arena, loaded at `movie_play_entry` into the arena above
      the movie's end address; every patched site carries its retail instruction under the
      `ORIGINAL` gate; `.area`-bounded. Proven in this order: (1) DONE 2026-09-22 — one
      hard-coded cue over frames 120–300, pixel-exact on Redux and Beetle against the
      reference rasteriser, 9.1 ms of the 66.7 ms frame inside a cue, no stall
      (`research/movies.md` § 7); the block has no movie key yet, so the prototype's cue
      plays over every movie reaching frame 120, and `boku build --vwf` carries none of the
      movie sites until (2); the 620-byte island is full — the per-movie select goes in the
      712-byte island at `0x800221CC` or in the loaded block. (2) DONE 2026-09-22 — `translation/movies.txt` keyed by movie file and STR frame
      (`translation/README.md` § movies.txt, `boku.movie_cues`, linted by `boku lint`); per-movie
      select in the `0x800221CC` island by `g_movie_name`; the block carried by `boku build
      --vwf` from `edits.json` `sectors` into `MOVIE_BLOCK_RESERVE` (LBA 1014–1045), which the
      allocator never hands out; `./make.sh build-days` carries the hooks. Redux gate on M27 +
      M60 pixel-exact, one movie's cue never drawn on the other; Beetle exact
      (`research/movies.md` § 8). RULED 2026-09-22 (Jay, watching `build/vwf`): the outline/shadow
      style and the rows (200/214) are good — "the pixels work", not cropped on DuckStation;
      still to check that every cue fits and sits at the right point in the audio (the
      prototype's one cue is mistimed by construction). Note `build/vwf/image.cue` is the
      renderer prototype — sample lines and fixtures (`tools/vwf/prototype-lines.tsv`, the
      "quick brown fox" overflow probe) over real scenes — not a playable build; play
      `build/days/days-*.cue`. (3) DONE 2026-09-23 — the ending `M28` plays in-game with the hook: cues pixel-exact
      on Beetle, length unchanged, the epilogue follows; the block's RAM is rebuilt by the
      game after an in-game movie (`M21` fill test, 1,601 of 1,601 shots identical); Redux
      boots anchored to the title (`research/movies.md` § 9). The Japanese credits scroll
      through the subtitle rows from `M28` frame ~1085 on (`research/movies.md` § 11).
      Harmed: the player, who misses the narration
      that frames the whole game.
- [x] **[FMV-02]** **Translate the movies' narration and songs.** DONE 2026-09-23:
      `translation/movies.txt` — the narration of `M27`, `M28`, `M60`, `M120`, `M260` and the
      the theme song in both places it plays (ruled yes: 6 cues in the opening, 10 in the ending), reviewed against the
      transcripts; an optional per-cue position (`top` / `bottom`,
      `boku.movie_block.POSITIONS`) that the parser and lint check and the block carries; each
      song cue's position measured against the credits; `movie-timing` times the song
      segments too (all pass). `research/movies.md` § 11, `work/movie-review/`.
- [x] **[FMV-06]** **The ending's song cues over the scrolling credits.** RULED (Jay, 2026-09-24,
      §13b): a dark panel, one position throughout. DONE 2026-09-24 (`cbaf192`): every `M28` cue
      at the bottom; song cues carry `panel`, a solid dark tile row behind each line, drawn by
      the unchanged blit — on Beetle the credits are hidden under each line and the pace is
      unchanged (5.008 vs 5.016 STR frames per 20 vsyncs); the Redux M60 fixture carries a panel.
      "Everything in this whole wide world," 2080 → 2299, sung from 153.2 s (Whisper on cut
      audio, `research/movies.md` § 11). Harmed (was): the player, reading English over Japanese names.
- [x] **[FMV-07]** **The adult Boku's narration in the movies takes the narration marks.** Jay,
      2026-09-24. DONE (`069ff63`): the 25 cues over `narration` segments (`M60`, `M120`, `M260`,
      `M27`'s monologue, `M28`'s first line) are wrapped in 『 』 per cue, the songs' are not;
      `movie-timing`'s `cue-marks` check holds both ways; style guide § 9 names `movies.txt` as
      the exception to "translations carry no marks". Harmed (was): the player.
- [x] **[FMV-08]** **`M27`'s on-screen text subtitled.** Jay, 2026-09-24. DONE (`70b54c3`): the
      writing is at `M27` frames 2436–2510 (the review video's 1:38 — it starts at frame 1020);
      one bottom cue with the new `caption` option (checked for reading speed and overlap, never
      retimed to speech). Harmed (was): the player.
- [x] **[FMV-03]** **Finalize the movies' timing.** DONE 2026-09-24 on the "silver" standard
      (Jay, 2026-09-24: close when the details and the mechanism are checked on another instance;
      seeing every movie in the real game is the gold standard, and `FMV-05` stays open for
      that): Jay watched every subtitled movie in `work/movie-review/index.html` — "the timings
      and placements are correct". The list is `research/data/movies.tsv` (`./make.sh movies`);
      the tooling is `./make.sh movie-timing` / `movie-review` (`research/movies.md` § 10–11):
      a cue may drift up to `DRIFT` (2 s) off its speech when reading needs it, one 17 cps limit,
      `M27`'s four fast cues retimed (1221 → 5.0 s). Harmed (was): the player.
- [x] **[FMV-10]** **A see-through panel behind the movie songs.** DONE 2026-09-24 (`78f9034`;
      Jay chose the hatch over the translucent panel): the panel tile is a checkerboard of dark
      (`boku.movie_block.PANEL_MASKS`), painted by `movie_sub_blit`'s own `@@hatch` fast path (576
      of 620 bytes); Redux gate 10/10, Beetle skips no STR frame in `M27` or `M28`; the translucent
      review is kept at `work/movie-review-shade/` (`research/movies.md` § 11). Harmed (was): the player.
- [x] **[FMV-09]** **Jay's §22 movie rulings.** DONE 2026-09-24 (`72e1f71`): 22.1 a panel fills
      both rows of its position; 22.2 `M27`'s song cues at the bottom with `panel`; 22.3 one 『 』
      pair per narrated sentence (`movie_timing._marks`, 11 sentences). The two-row panel made
      the Redux gate drop frames, so a glyph record's byte 1 flags the panel tile `solid` and
      `movie_sub_blit` fills it without the mask walk; gate 10/10, Beetle skips no STR frame in
      `M27` or `M28` (`research/movies.md` § 11). Harmed (was): the player.
- [x] **[FMV-05]** **No subtitles on the opening movie in real play.** CLOSED 2026-09-25: not
      reproduced on the current build. Jay, on DuckStation with `days-20260925T0246Z-0fdd1d70`
      (`./make.sh build-days`): let the game load, Confirm after the Millennium Kitchen logo, START
      at the title, Confirm for New Game — "the subtitles appeared just fine". The 2026-09-23
      playtest that saw none was an earlier build; Beetle had drawn the `M27` cues on the same
      path since then. Reopen if a real play shows the opening without cues. Harmed (was): the
      player, at the opening that frames the game.

## Voice-over — speech with no text on the disc, outside the movies

Jay, 2026-09-22, after playing: the five endings are voice-overs over a still image with no
subtitles — one ending movie, then narration that differs; and the same shape occurs in play
("the second time you interact with the shortcut well the narrator says he thought the well
was suspicious"). What is known: every null-text event entry is an `XA` opcode (`0x0F`, 446
entries; 108 XA nodes in the scene graph — `research/text-format.md`, `research/data/scenes.tsv`),
listed as `(voice only)` rows in the day files so the ids line up; `translation/voice-only.md`
names the worded ones found so far and says the listening pass has not been made; the endings
are `ENDOTI.OVL` (mode `0x10`, entered after `MOVIE 24`) with five packs `OTI00`–`OTI04`, each
a still plus the credits line texture (`research/data/texture-census.tsv` `credits`), and
`ENDOTI` calls `glyph_draw` nowhere (`research/text-outside-events.md`).

- [x] **[VO-01]** **The inventory.** DONE 2026-09-22: `research/data/voice-only.tsv`
      (`./make.sh voice-only`, regenerate-and-diff gate; `research/voice-only.md`): one row per
      event `XA` (115; 63 clips) plus one per `g_xa_clips` record (`BOKU_XA.XCH`, 48 — the
      bug-sumo voices, the day-1 bedtime narration `XCH.34`, the five epilogues
      `XCH.41`–`.45`). Every row `wordless` or an English gist from a Whisper pass
      (whisper.cpp large-v3, a machine tool) read against context: 16 event rows and 46 `XCH`
      rows have words. 446 null entries = stored copies of the 115; 108 = the rows with no
      character speaking. Japanese transcripts under `work/voice/` only.
- [x] **[VO-05]** **Listen to what ASR could not settle.** DONE 2026-09-24 — Jay listened; applied
      (`23b8392`, `72e1f71`, `5b6e910`): `E2330.11` is page turns; `XCH.45` Tsukiyono; `XCH.17` a
      sound of anxiety; `XCH.16` 好調 上々 "going well, first-rate" (a congratulation); the `E0305`
      names; `XCH.42` reworded "just short of 30" (30を前にして is his age); `M27` 41 s the father's
      "Guess it's about had it."; *tsumete* ("packed in") in `M28`; 光のトギ stays "specks of
      light" (Jay: reads right in context); the 12 unreferenced runs identified (`research/
      voice-only.md` § Unreferenced runs; nothing plays them — `VO-08`). Harmed (was): the player.
- [x] **[VO-08]** **How map interactions play voice.** Closed NO, 2026-09-24 (`3d69689`): nothing
      plays the unreferenced `BOKU_XA.XAM` runs. `xa_play` holds the only Setfilter and reads keys
      only from the running event's block or `g_xa_clips`; no key or record on the disc names a
      run; on Beetle, day 3's breakfast plays `E0007`'s shared "gochisosama" and `E0302.6`'s
      jingle, and the orphan takes share no sector with them — takes recorded for their scenes
      and not used. What Jay heard in play is those shared clips, `M27` and `E0814.0` ("sorosoro
      jumyō ka na"), the car `E0504.0`, the laughter `E2204.11`; the well's narration is `E2405.0`,
      a voiced message with text, already in English (`research/voice-only.md` § Nothing plays
      them). Reopen if a run is ever caught in `xa_play`'s key pointer `0x800357AC` in play.
- [x] **[VO-02]** **Subtitles for a voice-only clip in an event.** DONE 2026-09-22
      (`asm/voice.asm`, `research/event-scripts.md` § Voice-only entries): the `XA` handler's
      `talk_set` call becomes `voice_sub_open`, which opens the entry's text (no stock entry
      has any) and raises the band; `event_update` closes both when the clip stops and turns
      pages while ○ holds auto-advance off; page timers come from the clip's length
      (`boku.voice`). The reinserter fills the empty entry in every copy, the edit set records
      the hooks (a build without them refuses subtitle rows), lint checks the fit. Proven on
      Redux (`tests/test_real_voice_subtitle.py`) and Beetle with an `E0184.2` fixture; stock
      round trip unchanged. Covers event `XA` entries only — the native `g_xa_clips` plays
      are `VO-03` and `VO-06`.
- [x] **[VO-03]** **The five endings, the bedtime clip and the credits.** DONE 2026-09-23:
      `ENDOTI` plays `XCH.41` + the ending in `0x80035F42`; movie mode plays `XCH.34` after the
      day-1 diary (`research/event-scripts.md` § Native clips). Subtitles come from
      `translation/clips.txt` (keyed `XCH.nn`, day-file row format), carried in the
      movie-subtitle block (re-read in `ENDOTI`, which overwrites it — 16 vsyncs, only when
      clip English exists) and drawn in the band by `asm/voice.asm` through a hook in
      `xa_play_indexed` that every native clip passes. Proven on Redux
      (`tests/test_real_clip_subtitle.py`) and Beetle. The credits are `OTI0n`'s 276×33
      production/copyright strip, ruled N by `research/textures-plan.md`.
- [x] **[VO-06]** **Subtitles for the bug-sumo voices.** DONE 2026-09-23: bug sumo's mode init
      reads the movie-subtitle block to arena level C's base (untouched through a bout,
      measured on Beetle; `research/sumo.md` § Subtitles); `VO-07`'s ownership rule already
      covers these native clips; the subtitle draws in OT slot 0 and in bug sumo starts 42 px
      right of Boku's portrait (clips laid out to match). Proven on Beetle in a real bout
      (`sumo_bout.py --gong`) and on Redux; `tests/test_real_sumo_voice.py`. Speakers labelled
      by pronoun (Guts, Fat, Specs). Fixed on the way: leaving bug sumo hung on every raised
      build — `SUB.TIM`'s reload ran into the stack (`asm/arena.asm` `sub_tim_floor`,
      `research/loading-and-memory.md` § Leaving a mode; gate `sumo_bout.py --leave`).
- [x] **[VO-07]** **The bedtime voice-over in real play.** DONE 2026-09-23: in play the event
      runner's bit 0 (`0x8003637C`) stays set after the `END` into movie mode / `ENDOTI`, and
      the hooks read it as "an event owns the text", so `XCH.34` and the epilogues never
      opened; `clip_sub_block` no longer tests it and `clip_sub_frame` defers only for an
      event's own subtitle (`clip_sub_owned`). Gated on Beetle down the diary → good-night
      route and the real `E3182` ending (`tests/test_real_clip_subtitle_beetle.py`).
- [x] **[VO-04]** **Translate the voice-overs.** DONE 2026-09-24: every worded row of `VO-01`
      has English — the event clips in place in the day files (`E0305.0`–`.4`, `E0606.0`,
      `E0905.1`, `E1505.0`, `E1861.30`–`.32`, `E2305.0`, `E4052.2`–`.5`; `E0905.0` is the
      bells alone), the native clips in `translation/clips.txt` (`XCH.34`, the epilogues
      `XCH.41`–`.45`, the 40 bug-sumo lines) — reviewed against the transcripts, laid out by the
      build, checked on Beetle through `VO-02` (`E1505.0`, `E0905.1`) and `VO-03`/`VO-06`. Gate:
      `tests/test_voice_only.py` holds the translated set equal to `voice-only.tsv`'s worded
      rows. `E1861.30`–`.32` and `E2305.0` repeat the English of the lines they replay
      (`E1861.0`–`.2`, `E2204.6`). Harmed (was): the player.
- [x] **[VO-09]** **The epilogues' last sentence outlived the picture.** DONE 2026-09-30 (`f0e2774`):
      Jay, from the Summer Memories endings. Pages shared the clip by length over its silent tail,
      so every epilogue's last page was up with the production card (OTI02's and OTI03's only
      then); and VO-03's block re-read had put the voice 42 vsyncs late against `ENDOTI`'s
      pictures. Epilogue rows of `clips.txt` now time each page (from VAD), a timed last page comes
      down by itself, the re-read seeks back to the clip (stock lead, 5 vsyncs), and lint and build
      refuse a page up with the card or unreadably brief. The reader draws each page over its still
      with a timeline; `./make.sh epilogue-review` measures all five on Beetle.
      `research/event-scripts.md` § The epilogue's clock. Gates: `tests/test_clip_subs.py`,
      `tests/test_real_clip_subtitle_beetle.py`; the whole Beetle suite passes after it (227).
      Harmed (was): the player, at the last line of the game.
## Release

- [x] **[REL-01]** **Confirm on the targets.** DONE 2026-09-25: Jay confirmed the release's
      statement as written (`boku/release-notes.md`): developed and played on Beetle PSX (Mode One's
      core) and DuckStation, with XEBRA as the accuracy check, never tested on real hardware (Jay
      has none, 2026-09-21). Reopen if a hardware report arrives. Harmed (was): players on whatever
      was not tested.
- [x] **[REL-02]** **Mode One integration**, in `~/Dev/retro-trainer`. DONE 2026-09-25 (boku-ps1
      `a14f43d`; retro-trainer `7d6b50c` and the pin commit after it): RULED by Jay — Mode One
      does not apply the patch. `./make.sh export-to-mode-one` (`boku.mode_one`) packs `build/days`
      with chdman as retro-trainer's `one/roms/boku.chd` and pins that file's SHA-1 in
      `one/index/boku.sha1`, which Mode One's index compiles in. Measured: chdman is deterministic;
      the CHD boots to the title on Beetle with Mode One's BIOS. Each export re-pins, so Mode One is
      rebuilt (`./one/make.sh ios deploy`, `push-roms`), and a playthrough from another build boots
      fresh keeping its memory card (`SlotMeta.disc_identity`). Harmed (was): Jay, the first player.
- [ ] **[REL-03]** **Public release.** GitHub Release as the primary home. The machinery is built
      (`REL-04`, `ca619fc`): the main download is the xdelta, the `.cue`, four hashes each side,
      plain instructions (extract CHD → hash → patch), credits (README § "Related work") and a
      plain statement of how the translation was made; the PPF is a separate, optional download
      (Jay, 2026-09-25: "if Millennium Kitchen wants we'll remove it") — `release --no-ppf` /
      `publish-release --withdraw-ppf` remove it in one step. Left: create the GitHub repository
      and set `origin`; pick the first version, tag and push it; `./make.sh release`, then
      `./make.sh release-row release/v<version>`, delete the README's UNRELEASED note and put
      the video link at its VIDEO comment, commit and push README.md, then
      `./make.sh publish-release release/v<version> --yes` (`--draft` first if wanted). `REL-01`'s
      sentence on where it has been played is in `boku/release-notes.md`. Listing on romhack.ing /
      romhacking.net is optional and not worth bending anything for (romhack.ing withholds
      machine-assisted translations from web download; Jay, 2026-09-20: the scene's view of AI is
      not an input). Harmed: everyone who is not Jay.
- [x] **[REL-04]** **The release machinery.** DONE 2026-09-25 (`8158ad9`): `./make.sh release`
      refuses anything uncommitted, runs build-days, and writes `release/v<version>/` — xdelta +
      PPF against the Redump base, `PATCH.json`/`README.txt` (four hashes a side), the `.cue`,
      `RELEASE-NOTES.md` (`boku/release-notes.md` + README § "How the translation is made" and §
      "Related work and credit"), one zip carrying them under their real names — after applying
      each patch back through `apply_patch` to the built image. Version: HEAD's `v<version>` tag,
      else a git-describe snapshot that cannot be posted. `./make.sh publish-release DIR` prints
      the `gh release create --verify-tag` line and runs it only with `--yes`. Measured: stock
      xdelta3 reproduces the build; the build is deterministic across two runs; PPF 76.7 MB,
      xdelta 8.1 MB. Harmed (was): everyone who is not Jay.
- [x] **[REL-06]** **"Which version do I have?"** DONE 2026-09-27 (`0b06861`): Jay, 2026-09-27 —
      a player holding a patched image cannot tell v1 from v2. RELEASE-NOTES.md and README.txt name
      the patched `.bin`'s SHA-1 as the version's identity; README § "Which version do I have?" is
      the table (input and patched SHA-1 per version), written by `./make.sh release-row` from the
      posted zip's `PATCH.json`, never by hand; `publish-release --yes` refuses unless the README on
      GitHub's default branch holds that row. Harmed (was): every player of a second release.
- [x] **[REL-05]** **Boku's controller in Mode One, with a Run toggle.** DONE 2026-09-25
      (retro-trainer `7d6b50c`): FF7's layout with only D-pad, ○, ✕, △ and Run — plus Start, kept
      because the title screen advances only on Start (measured on Beetle with Mode One's BIOS; ○
      and ✕ do nothing there). Run is `SlotAction::Throttle`, only in Boku's profile: with it on, Up
      (and Up-diagonals) also holds ✕, folded in Rust (`ControlLayout::apply_throttle`), the toggle
      state held in Swift; unit-tested. On-device checks are retro-trainer PLAN § Next session.
      Harmed (was): Jay, playing on Mode One's controller.
- [x] **[DOC-02]** **README for the player.** DONE 2026-09-30 (`4ce415c`): Jay — the README is the
      project's public face and was "extremely technical". Rewritten for a player: what it is, six
      Beetle screenshots (`./make.sh screenshots` → `docs/screenshots/`; Jay, 2026-09-30: a few are
      fair use — the exception is in `CLAUDE.md`), a video placeholder, getting it, the versions
      table, where it is played (now quoted into the release notes), the charter, how it was made,
      why Jay made it. Contributor content is `TECHNICAL.md`; `tests/test_make_verbs.py` checks
      section and principle citations against the document named; `tests/test_docs.py` checks
      links, images and the unreleased note. Harmed (was): a player arriving from the link.
- [x] **[DOC-01]** **README audited against what was built.** DONE 2026-09-25 (`19f2665`): Status
      describes the state, not 2026-09-20 counts; § "Using it" gives the prerequisites, the import
      step and the verbs by task (build-days, reader, lint-translation, mockup, coverage, textures
      check, packet/save-event, the movie and emulator verbs, test/lint, patch/apply-patch), with
      `./make.sh help` as the verbs' one home. Corrected: the texture, movie and voice-over rows,
      the central-risk section, the reader, Delivery's Mode One bullet (`REL-02`), Contributing and
      Layout; `translation/README.md`, `translation/days/README.md` and the code comments that
      still called the ruled day-file format provisional. `tests/test_make_verbs.py` checks every
      verb cited in a tracked file exists, the usage text lists every verb, and every README §
      citation names a heading. Harmed (was): a contributor or translator starting from the README.
