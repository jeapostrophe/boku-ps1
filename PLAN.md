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
by dependency, and the project's pace is set by Fable throughput, which Jay has accepted.

**Classes and ids spent so far:** `ENV-01`–`ENV-04` environment · `RSH-01`–`RSH-02` research ·
`REC-01`–`REC-08` recon of formats · `TXT-01`–`TXT-07` text renderer · `PIPE-01`–`PIPE-06`
pipeline · `TRN-01`–`TRN-06` translation · `GFX-01`–`GFX-03` textures · `REL-01`–`REL-03` release.

**Dependency order.** `ENV` → `REC` and `TXT` (parallel; `TXT-04` is the project's go/no-go
trial) → `PIPE` → `TRN` → `GFX` → `REL`. `RSH` informs all of it and comes first.

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

- [ ] **[TXT-01]** **Trace one dialogue line from its id to pixels.** The static half is DONE
      (2026-09-20, `research/text-renderer.md`, `research/symbols/text-renderer.symbols.tsv`):
      direction is an **argument** — `dialog_open(x, y, vertical, text)` (`0x8002BD30`) is the
      only writer of `g_text_flags & 0x10`, and its two callers (`msg_open`, the ant-count
      message) pass literals: x = 297, y = 22, vertical = 1. Of 26 text surfaces, 20 are
      already horizontal at fixed pitch, 4 vertical (dialogue, SELECT, two `HHON.OVL`
      walkers), 2 draw one glyph per row. The dialogue "box" is a 60-px strip down the right
      edge, so horizontal text needs the panel re-placed as a band (`g_dlgbox_x` + two
      instructions in `dialog_panel_draw`). There is no page logic in code — "3 × 16" is an
      authoring convention — and voice sync is only the `0x8002` frame operand counting down.
      A table-lookup advance fits in place in 9 instruction slots at `0x8002BF5C` with no
      trampoline; left bearings or a variable-width SELECT need real hooks. **The emulator half
      is mostly DONE too** (`research/renderer-runtime.md`, scripts under `tools/redux/`): RAM
      equals the file once the EXE is loaded (frame ~720; entered at ~835 — the BIOS shell
      crosses the same addresses earlier), so file addresses are run-time addresses; the
      opening line is `E0171.0`; `dialog_open` is always called with (297, 22, 1); the strip is
      x = 265–319, opaque grey, and scenes are composed for the left 260 px; in-RAM the
      horizontal patch works, and a band with independent y/h (`band2`, Y=168, H=72) keeps
      the scene visible, opaque or translucent; at 14-px pitch English is legible but far too
      wide, at 8 px letters collide; the heap-raise gap saw 0 writes in 12,000 frames; the
      debug printer is never called; voiced pages turn on 30 Hz timers and ○ switches to manual
      paging; the font's VRAM page is unchanged across five sampled moments (row 240 is in
      use). **Left to do:** the primitive-buffer peak outside cutscenes (53,288 of 78,000 bytes
      seen), paging of unvoiced `MSG` lines, the two `MUSI` call sites — all need parts of the
      game a scripted cold boot does not reach (a prepared memory card or save state would
      open them). Harmed: `TXT-05`, where a buffer overrun or a missed surface would land.
- [x] **[TXT-02]** **What the existing font offers.** DONE 2026-09-20 (`research/font.md`,
      `research/font-candidates.md`): full A–Z/a–z/0–9 and common punctuation in 12×12
      full-width cells, ink widths 1–9 px, left bearings 1–5 px; missing `' " - ~ $ [ ]` and a
      horizontal `( )`; Japanese punctuation drawn for vertical lines. Counted against the
      structural text, arrays and code immediates, **1,333 ids are in use and 179 are free**
      (155 inked-unused + 24 blank; 347 if the sheet grows to its 1,680-slot VRAM ceiling) —
      not the 583 a heuristic scan suggested. English needs about 12 new cells. The font's
      VRAM page is unchanged across five sampled moments; row 240 is in use.
- [ ] **[TXT-03]** **Choose how English gets on screen.** `[MINE: product]` — **the evidence is
      in: look at `work/txt06/DECIDE.png`** (local; built by `work/txt06/`, described in
      `research/font-candidates.md`). Recommendation on the table: horizontal band + the in-place
      9-slot width table + Latin cells left-aligned in a sheet rebuilt at build time from the
      contributor's disc (the bearing hook is then unnecessary); estimated fit over all 3,484
      pages, three lines at 272 px: 57% at today's fixed 14 px, 99.3% with a width table on the
      untouched sheet, ~100% re-aligned. Also Jay's: opaque vs translucent band, and band
      height (72 rows = 4 lines; a 46-row band at Y=194 holds 3 and shows 26 more scene rows).
      Original row — between (1) patch
      the renderer to horizontal + variable width using the game's font, (2) the same with a
      replacement glyph sheet, (3) leave the renderer alone and draw a subtitle overlay. A fourth lever worth mocking up
      if the engine is rigidly full-width: two narrow Latin letters packed per 16-pixel cell,
      which needs no renderer change at all. Brought
      to Jay with `TXT-01`/`TXT-02` evidence and a mock-up of each viable option in a real box.
      The decision is recorded in README § "The central risk". Harmed: the player, by
      whichever option is chosen blind.
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
- [ ] **[TXT-05]** **The renderer patch.** Per `TXT-03`: armips source in the repo, horizontal
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
- [ ] **[TXT-06]** **The font.** If `TXT-03` needs a replacement sheet: a font under SIL OFL (or
      drawn for the project) so the repo stays fully open, rendered to the engine's cell format
      by a tool in the repo, with the width table generated from the same render.
      `[MINE: product]` for the typeface itself — shortlist with licences verified at source
      (`research/font-candidates.md`, `reference/fonts/SOURCES.md`): **Galmuri9** (OFL; same
      9/6-px cap/x-height as the game's Latin, 51 chars per line, has every glyph needed)
      recommended, then the game's own glyphs re-aligned (44), Ark Pixel 12 (45), Pixel
      Operator (42). Harmed: the player (legibility at 320×240 on
      a phone screen in Mode One is the hard case) and the repo's licence cleanliness.
- [ ] **[TXT-07]** **Measure what each box can hold.** For every box geometry the game uses:
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

- [ ] **[PIPE-01]** **Extraction to stable line ids.** Ids per `research/text-format.md`: `E<event id>.<message
      index>` for event text — one id, all its physical sites, since copies of an (event,
      index) pair are byte-identical in all 2,686 cases; **the extractor asserts that
      invariant** rather than assuming it — and `<file>@<original offset>.<item>` for the
      code-file arrays, plus forms for labels built from instruction immediates and for the
      Shift-JIS save title (proposal in `research/text-outside-events.md`). Ids survive translation edits and are the same on every machine. The import step writes the Japanese, with
      `REC-05`'s scene/order/speaker/choice/voiced context, under `disc/`. Harmed: contributors
      — an unstable id scheme invalidates every open PR.
- [ ] **[PIPE-02]** **The committed translation format.** `[MINE: contract]` — English and
      project-written context notes only, keyed by id, one file per scene so diffs and PRs are
      local, plain text that merges well, room for more than one candidate English per line. Our
      own format, designed for agents and `TRN-06` — not `.po`/Weblate (Jay, 2026-09-20) — but
      still plain enough that a person could write a whole translation in it by hand: the files
      are the build's only interface to the script (README § "How the translation is made"). No
      Japanese (README principles 2–3). Harmed: every contributor, and the agents that read and write it at scale.
- [ ] **[PIPE-03]** **Reinsertion.** Encode English to glyph indices under the `TXT-05` renderer's
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
- [ ] **[PIPE-04]** **Image build.** The core exists (2026-09-20): `boku/edc.py` regenerates EDC/ECC —
      gated by recomputing **all 280,170 sectors of the real disc** with 0 mismatches — and
      `DiscWriter.write_file_bytes` patches a byte range inside a file's extent, validating
      every sector before writing the first; `boku trial` builds atomically into `build/` and
      proves diff ≡ manifest and a byte-identical null build. **Left to do:** the general build
      that applies a whole translation (it needs `PIPE-03`), and growth beyond a file's
      extent. Original row: Patch sectors in place and keep the image length identical
      (`RSH-01` §1.4): 226,000 sectors of XA/STR sit behind `BOKU.BIN` at positions the
      executable addresses directly, and PPF cannot grow an image. Own Mode 2 Form 1 sector
      writer that regenerates EDC and ECC (ECC computed with the header zeroed) — wrong EDC/ECC
      is what works in emulators and fails on hardware. If text outgrows its files, the
      candidate arena is the 765 filler sectors before `BOKU.BIN`, *after* proving nothing seeks
      there. `mkpsxiso`/`dumpsxiso` 2.30 stay installed as the escape hatch. Output is deterministic:
      same inputs, same image hash. Harmed: Mode One, which pins that hash; hardware users, if
      EDC/ECC is wrong.
- [ ] **[PIPE-05]** **Patch emit and the round-trip gate.** Emit xdelta (what the scene expects; `xdelta3 -e -9 -S lzma -B <≥ image size> -A ""` —
      the default 64 MB window silently bloats the patch and the default header leaks build
      paths) and PPF3 (Mode One's patcher; DuckStation also applies a same-named `.ppf` beside
      a CHD), stating size, CRC32, MD5 and SHA-1 of base and result. None of the
      stock appliers reliably refuses a wrong base (PPF3's check is prompt-and-continue,
      DuckStation's is unimplemented, xdelta3 before 3.2.0 does not verify the source), so our
      own apply command verifies the base hash first and the instructions lead with hashing.
      The standing gate for the whole pipeline: import → extract → reinsert with **no**
      translation applied reproduces the original image byte for byte; made red on purpose
      once, per `ENG-1`, by perturbing one line. Harmed: everyone downstream of a reinserter
      that silently corrupts.
- [ ] **[PIPE-06]** **Translation lints.** Every id present exactly once; control codes (waits,
      choice structure) match the source line's; every character encodable; every line within
      its box per `TXT-07` — the fix for an overflow is another page or box, never a shorter
      translation. Runs in `make.sh test` so a PR cannot merge a line that overflows.
      Harmed: the player; the maintainer reviewing PRs by eye.

## Translation

- [ ] **[TRN-01]** **The style guide and the story bible.** DRAFTED 2026-09-20 by an agent that
      read the whole script, the 34 arrays, jooey's guide, the Action Button transcript
      (delegated, spot-checked) and 26 gathered web sources (`reference/SOURCES.md`):
      `translation/bible.md` (setting — August 1975, fictional Tsukiyono modelled on Dōshi,
      Yamanashi; cast with registers; the month day by day; map bases → places),
      `translation/style-guide.md`, three full sample scenes under `translation/samples/`
      (English only, keyed by line id), and **`translation/QUESTIONS.md` — eleven rulings that
      are Jay's, each with options, an example and a recommendation. This row is waiting on
      those.** `translation/glossary.md` is written but uncommitted: it lists the Japanese of
      57 insect names and 48 dinner dishes, and whether word lists count as game content is
      Jay's call `[MINE: contract]` (the mechanical alternative is keying those rows by array
      index). Facts that change engineering: pages auto-advance with the voice, so **page
      count and order per message are fixed**; there is no name entry or substitution beyond
      three ant-count digits; the opening narration and all five epilogues are **voice only,
      with no text on the disc** (QUESTIONS Q11 — subtitling them would be new renderer
      work). Original row: The charter is settled (README
      § "Who this is for": translate, don't localize; Japanese-isms stay; "Boku" is "Boku"); this
      row turns it into rulings — honorifics, name order and romanisation, how dialect and
      children's speech are carried, food/insect/fish/item glossary, what is left in Japanese —
      plus the bible: setting (rural Japan, August 1975, a nine-year-old and the adult narrator he
      became), every character with voice and register. Sources, all under `reference/`: the
      decoded script, jooey's walkthrough, the Action Button transcript (fetched), xneo.jp's
      Japanese walkthrough (to fetch), and a search for more long-form Japanese accounts of the
      story. Tracked, CC BY-SA, and the thing contributors argue with. `[MINE: product]` on
      rulings the charter does not decide. Harmed: the player — consistency across
      thousands of lines comes from this file or from nowhere.
- [ ] **[TRN-02]** **Scene assembly for the translator.** From `REC-05`: each unit of translation
      work is a whole scene as a flow graph (`work/rec05/scenes.py --dump` already renders one
      locally; the 83 dinner-quiz lines need "this is day d's question" as context; map base →
      place name and flag meanings come from the walkthroughs, not the disc), with speakers, choices and branches, the box
      limits, the bible and glossary, the day's events from the walkthroughs, and neighbouring
      scenes' settled English. Err toward too much context — the model has the window for it.
      Harmed: translation quality.
- [ ] **[TRN-03]** **Design and pilot the agent workflow.** Fable sub-agents under a dynamic
      workflow (needs Jay's opt-in at launch, `AGT-1`): translate → independent review against
      the source → consistency pass against glossary and neighbours → lint. Pilot on one
      in-game day, read the result in the game, fix the workflow before scaling. Apply what
      `RSH-01` found about LLM game-translation failure modes. Harmed: the token budget and the
      player, if the full run repeats a flaw a pilot would have shown.
- [ ] **[TRN-06]** **The scene reader.** A small local tool (Jay, 2026-09-20: easier to make and
      better to use than Weblate) that renders a scene in play order from `TRN-02`'s graph:
      Japanese from the local import beside the English, candidate translations and reviewer
      notes side by side, branches navigable. Read-only over the translation files — edits go
      through the files and the agents, so there is no second representation to keep in sync.
      Built when `TRN-03`'s pilot has output to read. Harmed: Jay, who otherwise can only judge
      the translation by playing to each line.
- [ ] **[TRN-04]** **The full translation run.** Everything `REC-03` and `REC-06` found, through
      the piloted workflow, committed scene by scene. Harmed: the player.
- [ ] **[TRN-05]** **Play it.** A full playthrough of the patched game looking for wrong-context
      lines, overflow the lints missed, untranslated stragglers, and tone. Findings go back
      through the workflow, not hand-patched around it. Harmed: the player.

## Textures

- [ ] **[GFX-01]** **TIM round trip.** No TIM library in any language round-trips with CLUT
      preservation, so this is ours (`work/rec08/` has a working decoder to start from). From
      the census: all TIMs are 4bpp/16 or 8bpp/256 with CLUTs; the CLUT block's VRAM origin is
      non-zero in 758 of them and must be carried; 488 images have several CLUTs (up to 21)
      assigned per screen region; and an edit must propagate to every duplicate (one minimap
      has 287 copies). Requirements: decode → encode is byte-identical over **every** TIM on
      the disc (fixtures derived from the disc, never typed), depth/size/origin never change,
      shared palettes are not modified and edits map to existing entries, wired into
      extract/reinsert and covered by the `PIPE-05` gate. Harmed: `GFX-03`.
- [ ] **[GFX-02]** **Evaluate the redraw path on a sample.** Three textures of different kinds
      from `REC-08` — the census suggests `NIKKI_001`, `T_TITLE` `0x14`, `M_I18000` — (scoped with DuckStation's texture dump as a second inventory): have an image model (Jay's proposal: ChatGPT) redraw them in English in
      the original style, quantise back to the original CLUT, and look at them in the game.
      If that fails, the fallback is Claude-drawn subtitles composited onto the texture. A third
      path to weigh for the 94 diary pages, which are over half the work: their text sits in
      ruled columns on flat paper under the drawing, so a program can blank that panel, redraw
      rules for horizontal lines and typeset the English — no image model, exact palette, and
      the entry text lives in the translation files like any other line.
      `[MINE: product]` on which path, per texture category. Harmed: the player, by whichever
      path is chosen without looking.
- [ ] **[GFX-03]** **Translate the textures** per `GFX-02`, category by category, recording for
      each texture id what was done. Redrawn images are tracked (README principle 2);
      a subtitled texture is tracked only as its subtitle text and placement, composited onto
      the contributor's import at build time; originals are never tracked. Harmed: the player.

## Release

- [ ] **[REL-01]** **Confirm on the targets.** Beetle PSX (Mode One's core), DuckStation, and a
      hardware-accuracy check — real hardware if Jay has a way to run it `[MINE: product]`,
      otherwise XEBRA. State plainly in the release what was *not* tested.
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
