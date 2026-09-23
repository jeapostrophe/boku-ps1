# boku-ps1 — Plan

The **live task list only** — open work, nothing else. What the project is and how it is laid
out: [README.md](README.md). What has been learned: [research/](research/). Rules for agents:
[CLAUDE.md](CLAUDE.md). History of completed work: git.

**Conventions.** Every item carries a stable id, assigned once, never renumbered, never reused;
cite items as `PLAN TXT-01`, never by line. An item names **who is harmed** if it is not done —
a player, a contributor, or a future agent reasoning from a false claim; no harmed party, no
item. Items that wait on a decision that is Jay's say so literally: `[MINE: product]`,
`[MINE: contract]`, `[MINE: dependency]`. Completed rows are marked `[x]` with what was actually
true, committed, and deleted at the next triage. A row is a lead, not a spec: re-derive its
claims against the disc and `HEAD` before working it. No time estimates — sections are ordered
by dependency, and the project's pace is set by top-tier model throughput (Opus 5.5 since 2026-09-22, `CLAUDE.md` § Model tiers), which Jay has accepted.

**Classes and ids spent so far:** `ENV-01`–`ENV-06` environment · `RSH-01`–`RSH-02` research ·
`REC-01`–`REC-08` recon of formats · `TXT-01`–`TXT-08` text renderer · `PIPE-01`–`PIPE-06`
pipeline · `TRN-01`–`TRN-09` translation · `GFX-01`–`GFX-09` textures · `FMV-01`–`FMV-04`
movies · `VO-01`–`VO-04` voice-over · `REL-01`–`REL-03` release.

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
      keyed on Japanese `msgid`s it is superseded by README principles 2 and 3. Its unanswered
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

## Recon — where every piece of Japanese lives

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
      overlays load at `0x80079A08`–`0x8008F3A4` (`MUSI.OVL` has 10 bytes free). All arena
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

## Text renderer — the central risk (README § "The central risk")

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
- [ ] **[TXT-05]** **The renderer patch.** The DIALOGUE surface is prototyped and runs on both
      emulators (2026-09-20, `asm/dialogue.asm`, `tools/vwf/build_prototype.py`,
      `research/vwf-prototype.md`): 21 EXE words — direction, pen, the band, line pitch, the
      nine-slot table-lookup advance (no trampoline), heap start raised to make room for the
      width table in the measured-dead gap; every site carries its retail instruction and the
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
      with it; `「『` got a left bearing and `」』` were tightened; the choice cursor is the
      game's own hand turned a quarter turn at build time (nothing tracked) so it points at
      the row; `H06001` (day 15 morning) loaded with child 6 past the old bound; the aunt's
      evening lines drawn from a relocated EV member on Beetle. The card-check and settings
      screens Jay saw in Japanese are `TITLE.OVL` renderer text with no translation rows —
      the array/overlay half of `TRN-04` (308 lines on six surfaces, `boku coverage` lists
      them as `not-event`), not a renderer miss. **Left to do:** the two `HHON.OVL`
      walkers, the 20 fixed-pitch surfaces and their arrays, the 23 computed-id `glyph_draw`
      sites (not covered by the free-cell gate); and watching the heap gap and stack under
      the four overlays / a save / menus, sumo and fishing. (Round 3, 2026-09-21: the
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
- [ ] **[TXT-07]** **Measure what each box can hold.** Measured for the dialogue band on the running prototype
      (`research/vwf-prototype.md`): 272 px usable (296 to the screen edge), ~46 characters a
      line at 5.85 px, 4 clean lines a page, lines 4–5 must end before x ≈ 262 for the
      next-page pencil, and overflow is clipped silently at x = 319 — the engine never wraps,
      so the inserter breaks lines and `PIPE-06` measures them in pixels. **Under Jay's band
      (H=37, pitch 11, three lines; now at Y=191 so every row is inside what DuckStation's
      default crop shows — the game programs all 240 rows, the crop stops near 232, and the
      stock next-page marker reached 230; line 3 ends before 238 px for the marker), days 1–7
      + shared, 764 rows: advance model c1 (sheet untouched) needs a 4th line on 68 pages, a
      5th on 8 and overflows 3 SELECT rows; c2 (cells re-aligned) leaves 4 pages
      (`E0771.0`, `E0772.1`, `E0773.2`, `E4028.11`) — 757 of 761 lines laid out. Jay ranked
      c1 > c2 with "lint decides fit" (2026-09-20), so the build is c2; c1 stays behind
      `--advance-model c1`.** Still to measure:
      every other surface. Original row — for every box geometry the game uses:
      lines × pixel width under the new renderer (today: a page is at most 3 columns × 16
      glyphs, `research/text-format.md`; mock-up measurements of band height, line pitch —
      minimum 12 for the game's glyphs, 13 for Galmuri9 — and characters per line per font are
      in `research/font-candidates.md`; the whole-game fit there is an estimate from 80 sample
      pages, so `PIPE-06`'s page-length lint is the real gate). Also: every other text surface
      steps a fixed 12 px, so left-aligned narrow cells look gappy there until each surface
      gets its own advance — that is `TXT-05`'s surface list. Output is data the translation lints and the
      translation agents both consume. Harmed: the player, by text that overflows; the
      translators, by limits discovered after the fact.

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
      is its loader. Hand-writable, as the README's aspiration asks.
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
      applied (`~/.claude/session-notes/boku-ps1/2026-09-20-reader-review.md`).
- [ ] **[TRN-04]** **The full translation run** — a status table, not a churning row (Jay,
      2026-09-21: Fable translation is expensive; he spawns "do the next N days" himself when
      the engineering is ready; this row only records where each unit stands). **Waits on
      `TRN-08`**: changing the packet and its format invalidates every state below (Jay,
      2026-09-21) — days 1–7 and shared are held as the *first draft*, tag
      `first-draft-2026-09-21`, to be re-translated through the new packet and compared. States, in
      order: **undrafted → drafted → reviewed** (an independent agent against the Japanese)
      **→ checked** (Jay has read it, comments applied) **→ rendered** (the lint's pixel fit and
      the page mock-ups say it would display — `TRN-08`) **→ finalized** (Jay has seen it in the
      game, formatted and displayed correctly). Workflow per unit: `boku packet` (`TRN-08`) →
      translator → reviewer → applier → `boku lint` → Jay.

      | unit | state | note |
      |---|---|---|
      | `day01.txt`–`day07.txt` | reviewed | first draft merged per line with a blind re-translation through the `TRN-08` packet, both reviewed against the Japanese (2026-09-22); Jay's comments kept |
      | `shared.txt` (76 events) | reviewed | the same merge; includes the coverage nine |
      | days 8–31 + their day-independent events | undrafted | 24 day files; run in batches Jay sizes |
      | arrays / menus / overlays (308 lines) | undrafted | `TRN-09` |
      | diary entries (94), encyclopedia spreads, textures | undrafted | `GFX-04`, `GFX-06`; new text with no line ids |
      | movie narration | undrafted | `FMV-02`; no text on the disc — transcribed from the audio |

      Original row: everything `REC-03` and `REC-06` found, through the piloted workflow,
      committed scene by scene. Harmed: the player.
- [ ] **[TRN-08]** **The packet, redone to Jay's spec — the comparison.** The engineering is
      DONE (2026-09-22): `boku packet` writes `system.md` once plus one part per event in the
      day-file shape (Jay's drop list enforced by test), `boku save-event` saves a directed
      translator's answers, `parse_rulings` returns every style-guide section, `boku lint`
      warns `em-dash`, and `./make.sh mockup` draws every page with the sheet's glyphs at the
      band geometry. **Comparison run DONE 2026-09-22** (`~/.claude/session-notes/boku-ps1/
      2026-09-22-trn08-comparison.md`): days 1–7 + `shared.txt` re-translated blind through
      the packet, reviewed against the Japanese and judged per line against the held draft —
      816 rows: 270 identical, 433 old won, 62 new won, 51 combined; the merge is committed,
      lints with 0 errors and draws 0 red mock-up lines. The judges traced most of the new
      draft's losses to one packet defect: `system.md` carried only the glossary rows whose
      Japanese the unit matched, not the whole glossary the spec names (Jay, 2026-09-22) —
      being fixed with the translators' other packet findings. Left: after that fix, one day
      re-translated through the corrected packet and judged the same way, so the packet is
      judged on its spec rather than on the defect. Harmed: the translator and Jay.
- [ ] **[TRN-09]** **The 308 array, menu and overlay lines** — the first thing every player sees:
      the memory-card and save/load messages (32), the title and config labels, the controls
      help, item names and descriptions, the 57 insect names, photo captions, kite names
      (`exe@…`, 201), the insect book (`hhon@…`, 62), bug sumo (`musi@…`, 37), title (5), kite
      workshop (2), the "write the diary and sleep?" prompt (`zukan@…`). `boku coverage` lists
      them as `not-event`; `boku lint` already checks array byte sizes. Needs an array packet
      (`TRN-08`) and, on screen, `TXT-05`'s fixed-pitch surfaces. Jay saw these in Japanese
      after START on 2026-09-20. Harmed: the player, before the first line of dialogue.
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
- [ ] **[GFX-04]** **The rest of the diaries** — 93 pages after the prototyped one, programmatic
      with the game's glyphs. Moved here from `research/diary-redraw.md` (it was a plan hiding
      in a research note): (1) the entries need their own keyed home in `translation/`, keyed
      by **page id** (`NIKKI_048`), not day — `g_diary_pages[day]` picks a page at run time and
      the same page can serve different days; (2) per-page wrapping with a refusal, as a lint
      the build runs — five lines of ~32 game glyphs, nothing shortened to fit; (3) **the date
      strip stays as it is** — RULED (Jay, 2026-09-21): keep the Japanese month/day symbols
      with the composited numeral, "fun and simple to understand", which also leaves
      `nikki_date_upload` untouched; (4) `NIKKI_047`'s shading differs and still redraws —
      re-run `measure` on any contributor's import before a bulk run; (5) `NIKKI_000` is the
      unused dummy and must be skipped deliberately; (6) each page is stored once, so 94
      independent edits and no propagation. The 94 entries are new English (`TRN-04`'s
      table). Harmed: the player, who writes a diary every night.
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
- [ ] **[GFX-06]** **The encyclopedia spreads** — 9 insect pages (`MZKAN0/1`: the same 9 in
      two lightings, one layout, type on flat white beside the photo; each English page
      written to both packs) and 8 kite (`TZKAN`, flat cream): programmatic; blank the page
      area, keep the photo/kite panel, re-rule under the header, reflow the vertical body to
      horizontal (the diary's answer applies). Every field is pixels (`GFX-05`). Text:
      species name (glossary § 4a), family, size, food, body; kite name, difficulty, how to
      build. Harmed: the player who opens the book.
- [ ] **[GFX-07]** **UI plates and the title menu** — 17 programmatic images: `T_TITLE` **first**
      (four menu lines on transparent, outlined with a drop shadow — Jay, 2026-09-20: "needs
      to be translated early"), `T_CONFIG` value plates, the oval action buttons across seven
      atlases (`SUB`, `M_S01100`, `M_S02000`, `MZ00`, `MZ02`, `SAMP`; multi-CLUT — the
      per-region CLUT lives in the drawing code), the record screens (`FS/PK/TK_WAL`),
      `T_MEMORY`'s heading, `TZICON`, the radio-exercise card (`PK_ITM 0x6c`). Split between
      renderer and texture per screen is tabled in `research/textures-plan.md` § UI. Harmed:
      the player, at the first screen. **`T_TITLE` DONE 2026-09-22**: `translation/textures/ui.txt` →
      `boku/texture_text.py` `title_menu`, sprite records widened to 128 px
      (`research/texture-recipes.md` § `T_TITLE`), proven on Beetle by
      `tests/test_real_title_menu_beetle.py`. Remaining: `T_CONFIG`, the action-button
      atlases, `FS/PK/TK_WAL`, `T_MEMORY`, `TZICON`, `PK_ITM 0x6c`.
- [ ] **[GFX-08]** **The redraws** — 28 images an artist or an image model repaints, quantised back
      to the original CLUT and committed as new pixels: three book covers consistently across
      their 21 animation frames; four close-up screens — **Saori's farewell note on the log**
      (`M_I14000`, the one plot-bearing string with no line id; subtitle is the fallback), the
      hunting-association board, the keep-out sign (the model-kit box `M_I19000` stays —
      Jay, 2026-09-22: the narrator says what it is); the result badges
      (`MITIM`), the bug-swap notebook cover, the brush-lettered plaque. Harmed: the player
      who examines the thing and reads nothing.
- [ ] **[GFX-09]** **The beach notice, as a subtitle** — the one image (`M_C15100`) painted into a
      background at an angle where a redraw means repainting the scene; an English caption
      composited beside it at build time, tracked as text + placement only. Harmed: the
      player at the beach. (The 30 images that stay Japanese by the charter need no row —
      `research/textures-plan.md` lists them.)

## Movies

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
      README row 3; split into three rows 2026-09-21).
- [ ] **[FMV-04]** **Subtitles in the movie player (E2).** `research/movies.md` § 3 E2: hook
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
      `build/days/days-*.cue`. (3) The ending. Harmed: the player, who misses the narration
      that frames the whole game.
- [ ] **[FMV-02]** **Translate the movies' narration.** The opening monologue and whatever
      the other movies say (`translation/voice-only.md`; Q11 (b)) — by Jay's watch
      (2026-09-22, `movies.tsv`) only five movies have voice: `M27` (opening, with a song),
      `M28` (ending with the credits and a song), `M60` (fireworks), `M120` (the satellite),
      `M260` (the sunflower-field dream); the other 20 are wordless; the five epilogues are
      not movies — `VO-03`. Transcribed 2026-09-22: timed Japanese per movie in
      `work/voice/reviewed/<file>.ja.tsv` (1-based header frames; audio t = 0 is extent
      sector 7, `research/voice-only.md`), songs marked `song`; left: translated and reviewed like a day file,
      keyed by movie and frame (`FMV-01`: 15 fps, header numbers 1-based). Harmed: the
      player.
- [ ] **[FMV-03]** **Finalize the movies one by one.** The list is
      `research/data/movies.tsv` — one row per `MOVIE` id (27; 25 files), generated by
      `./make.sh movies` (2026-09-22), which also decodes every movie with its narration into
      `work/movies/*.avi` for watching; `what_it_shows` is the hand column Jay fills from
      watching (the stairs movies and the other oddities go there). A movie is finalized when
      its row says what it shows and its cues (`FMV-02`) are timed to that picture through
      `FMV-04`'s hook, checked in the game — Jay's finalized state. Harmed: the player.

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
- [ ] **[VO-05]** **Listen to what ASR could not settle.** `E2330.11` (Moe reading the English
      letter? no speech found), the words marked `?` in the `M27`/`M28` and potter/dam
      transcripts, the well narration Jay heard (not an `XA`/`XCH` clip; `E8062` is text), and
      whether any of the 12 unreferenced `BOKU_XA.XAM` runs with words is played. Needs an ear
      — the model cannot hear. Harmed: the player (a wrong or missing subtitle); the
      translator, working from a guessed word.
- [ ] **[VO-02]** **Subtitles for a voice-only clip in an event.** Fable (RE): the `XA`
      handler `0x8002F588` plays the voice and draws nothing; `XAMSG` plays a voice and
      draws a page. Find the cheapest way to give an `XA` entry text — whether a non-null
      text pointer on an `XA` entry already draws (the entry layout has the slot,
      `research/text-format.md` `off[4+2i]`), or the opcode must become `XAMSG` and what
      else differs (page timing, the hold — `TXT-09`), so that a `(voice only)` row in a day
      file that carries English becomes a subtitle through the existing reinserter and
      band. Measured on the well. Harmed: the player.
- [ ] **[VO-03]** **The five endings and the credits.** Fable (RE): how `ENDOTI` picks and
      plays an epilogue (the ★ count → `OTI0n`, decoded by `ENV-06`; the narration's keys are `g_xa_clips` 41–45, `VO-01`), what the credits
      are — texture (`OTI0n`'s credits line is one), code, or the ending movie — and how
      much text that is; then how to draw subtitles there, since `ENDOTI` draws no glyphs:
      the dialogue renderer called from the overlay, or `FMV-04`'s composite. Harmed: the
      player, at the payoff of the game.
- [ ] **[VO-04]** **Translate the voice-overs.** The worded rows of `VO-01`, transcribed and
      translated like a day file — the `(voice only)` rows gain English in place, and the
      epilogues get their own file keyed by ending and time — reviewed against the
      Japanese, then checked in the game through `VO-02`/`VO-03`. Harmed: the player.

## Release

- [ ] **[REL-01]** **Confirm on the targets.** Beetle PSX (Mode One's core) and DuckStation are
      the play targets; Jay has **no way to test on real hardware** (2026-09-21), so the
      accuracy check is XEBRA and the release says plainly that hardware was not tested.
      Harmed: players on whatever was not tested.
- [ ] **[REL-02]** **Mode One integration**, in `~/Dev/retro-trainer`: the PPF as a
      `provisioning.ron` step against the Redump base SHA-1, a `PATCHES.md` provenance entry,
      the post-patch SHA-1 pinned in its index, the CHD source path in its provisioning
      scripts. Harmed: Jay, the first player.
- [ ] **[REL-03]** **Public release.** GitHub Release as the primary home: both patch
      formats, the `.cue`, four hashes each side, plain instructions (extract CHD → hash →
      patch), credits (README § "Related work"), and a plain statement of how the translation was made.
      GitHub is the distribution. Listing on romhack.ing / romhacking.net is optional and not
      worth bending anything for (romhack.ing withholds machine-assisted translations from web
      download; Jay, 2026-09-20: the scene's view of AI is not an input). Harmed: everyone who is not Jay.
