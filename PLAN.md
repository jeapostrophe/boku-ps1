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

- [ ] **[ENV-01]** **Scaffold the Python project.** `pyproject.toml` under `uv`, a package for the
      tools, `pytest`, a linter, and a root `make.sh` whose verbs are the only documented
      commands (`import`, `test`, later `extract`/`build`/`patch`). README § Layout updated in
      the same commit. Harmed: a contributor who cannot tell how to run anything.
- [ ] **[ENV-02]** **The import step.** Input a `.chd` (via `chdman`) or `.bin/.cue`; verify the
      raw image against the Redump SHA-1 (confirm that value against redump.org itself, not a
      secondary report) and refuse anything else with a message that names both hashes; walk
      ISO9660 over 2352-byte Mode 2 sectors and write `disc/image.img` and `disc/files/`.
      Source path from an argument or env var — no machine-specific default in the repo. Must
      not be defeatable by the case-insensitive-filesystem collision recorded in
      `research/disc-recon.md`. Later rows extend it to write the decoded script. Harmed: every
      contributor — principle 2 in the README makes this the only way anyone gets content.
- [ ] **[ENV-03]** **A PS1 emulator with a debugger on this Mac, and the Mode One core beside
      it.** Need: execution/read/write breakpoints, a VRAM viewer, GPU primitive logging. Jay's machine has no PS1 emulator with a debugger installed today. `RSH-01` §4: **PCSX-Redux** (native Apple Silicon build; mapping breakpoints, VRAM viewer,
      GPU logger, Lua, GDB server, and `-run -testmode -lua_stdout` for a headless smoke gate) for
      finding things, DuckStation for play-testing; no$psx is Win32-only. Separately,
      a way to boot a built image on Beetle PSX (`mednafen_psx`, the core retro-trainer's
      `cores.lock` pins), since that is where results are confirmed. Harmed: `TXT-01`, which
      cannot be done from static analysis alone.
- [ ] **[ENV-04]** **Disassembly project for `SCPS_100.88`.** Ghidra with `ghidra_psx_ldr` and its PsyQ
      signature database (the executable links 1993–97 Sony libraries), load address
      `0x80010000`, so file offset = RAM address − `0x8000F800`. On Apple Silicon Ghidra's
      decompiler natives must be built locally (`support/gradle`, `buildNatives`). The
      Ghidra database embeds the executable, so it lives in `work/`; what is *learned* — symbol
      names, addresses, struct layouts — is exported to a tracked text file so the next agent
      does not start from zero. psyouloveme's RAM map and Ghidra TIM/CD-XA labellers are the
      starting labels. Harmed: every `TXT` and `REC` row.

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
- [ ] **[REC-02]** **What `REC-01` left unexplained in the containers.** Packs, the four
      `.SEC`-indexed sub-archives and "no compression" are measured (`research/boku-bin.md`).
      Still open: the 10 `unknown` members; the role of each child of a map pack (child 1 is
      text — what are the rest, and do any hold offsets into child 1 that move when text
      grows?); the `NIKKI.SEC` consumer; the two unknown words of `g_cd_dir`; the nine
      `file_load` sites with a computed index. Harmed: the reinserter, which must rebuild
      every table that encloses or points into text.
- [ ] **[REC-03]** **The text tables, completely.** Lines are `u16` glyph indices ending `0x8000`
      with `0x8001` newline and `0x8002`+param wait. Establish: the table structure around the
      lines (count + offsets? relative to what?), every control code in use, what ids above 1023
      are (440 of 5,527 candidate lines use one — 127 distinct ids), alignment/padding rules (PS2 pads with `0xCDCD` to 4 bytes), the PSP port's page-break
      sequence `0x8002, arg, 0x0000, next page` whose zero must survive, and
      **which text is duplicated** (hash every 2 KB block of the archive for collisions) — 1,398 of 5,527 candidate lines sit in one MiB, and the PS2
      game copies message files into preloaded blobs that must all be patched. Output: a real
      unique-line and glyph count. Harmed: a player who sees untranslated text from a missed
      copy; the translation budget, which is sized from this count.
- [ ] **[REC-04]** **The glyph table, derived from this disc.** Find the font sheet(s) — cell size,
      bit depth, where they are loaded — and build the index → character table from the sheet
      itself, using Shift-JIS collation order as the generator and the PSP table only as a
      cross-check (it is GPL-3.0 and 1024 entries; this game exceeds 1024 — the Korean PSP
      patch's table has 2,020 codes; indices 0–293 match on 285 of 294 positions across the PSP
      and PS2 games, the rest being transcription ambiguities).
      OCR of the sheet (Hilltop used KanjiTomo) beats typing kanji. Record whether the
      sheet contains Latin letters, digits and punctuation, at what widths. Harmed: the
      extractor (wrong characters), and `TXT-02`.
- [ ] **[REC-05]** **Event scripts, as far as translation needs them.** The PS2 sequel's per-map
      bytecode has `MSG`, `XAMSG` (voiced line), `SELECT` (choices) and flow opcodes, with the
      first three table entries being code rather than text. Decode enough of the PS1
      equivalent to recover the **flow graph of each scene** — this line is followed by that one,
      a choice here offers these options and each leads there — plus which lines are voiced and
      what map/day/condition triggers the scene. Flow opcodes must be understood; the rest need
      not be. Harmed: translation
      quality — a line translated without its conversation is translated badly.
- [ ] **[REC-06]** **Text outside the tables.** Strings in the executable that a player can see
      (its Shift-JIS load/save messages are PC dev-host debug printfs, not these — the real
      failure path is still to be found), the memory-card save title (the BIOS
      requires Shift-JIS), and anything drawn by a path other than the dialogue renderer —
      menus, the insect list, item names, the clock/calendar. Harmed: a player who meets
      Japanese in a menu of an otherwise finished patch.
- [ ] **[REC-07]** **Is there tamper detection on data?** The executable's warning string is the
      stock mod-chip check, not a data check — but the PS2 sequel CRCs the first `0x80` bytes of
      every file (CRC-16/CCITT-FALSE) and crashes on mismatch. Establish whether the PS1 game
      checks anything, before a reinsertion is blamed for a crash it did not cause. Harmed:
      whoever debugs `TXT-04`.
- [ ] **[REC-08]** **Census of Japanese inside textures.** Extract every TIM (~2,600) to PNG under
      `work/`, build contact sheets, and classify which contain Japanese text and what kind —
      the picture diary, signage, title/menu art, the insect book. Output: a tracked list of
      texture ids with a category and no pixels. This sizes `GFX` and tells `REC-06` which
      "text" is really art. Harmed: the texture phase, which cannot be evaluated without it.

## Text renderer — the central risk (README § "The central risk")

- [ ] **[TXT-01]** **Trace one dialogue line from its id to pixels.** First question (`research/
      renderer-prior-art.md` §2, §8): does the print routine take a **direction argument**? The
      PS2 sequel's did — its menus went horizontal with one `li reg, 0` each and only the
      dialogue path needed rewriting. Then: who reads the `u16`s, how a
      glyph index becomes a texture coordinate, whether glyphs are drawn as sprites per
      character or composed into a VRAM texture, where the pen position lives, where the
      vertical advance (possibly a per-character function's *return value*, not a constant) and the column step (the family's `base_x − column × spacing` pattern)
      are computed, and what owns the box geometry. Output: `research/text-renderer.md` with
      addresses and symbol names. Harmed: every other row in this section.
- [ ] **[TXT-02]** **What the existing font offers.** From `REC-04`: are there Latin glyphs, are
      they full-width cells only, is the cell size workable for English at this resolution, and
      how many glyph slots can be repurposed without breaking untranslated text during
      development. Harmed: `TXT-03`, which is decided on this evidence.
- [ ] **[TXT-03]** **Choose how English gets on screen.** `[MINE: product]` — between (1) patch
      the renderer to horizontal + variable width using the game's font, (2) the same with a
      replacement glyph sheet, (3) leave the renderer alone and draw a subtitle overlay. A fourth lever worth mocking up
      if the engine is rigidly full-width: two narrow Latin letters packed per 16-pixel cell,
      which needs no renderer change at all. Brought
      to Jay with `TXT-01`/`TXT-02` evidence and a mock-up of each viable option in a real box.
      The decision is recorded in README § "The central risk". Harmed: the player, by
      whichever option is chosen blind.
- [ ] **[TXT-04]** **The trial: one English line on screen in a rebuilt image.** By the crudest
      means that work — in-place sector patch, full-width letters if that is all the font has,
      vertical if it must be. It proves the chain text table → image → emulator end to end, on
      Beetle PSX as well as the debugging emulator, and flushes out `REC-07`. **This is the
      go/no-go for the approach.** Harmed: the whole project, if the pipeline is built before
      this is known to work.
- [ ] **[TXT-05]** **The renderer patch.** Per `TXT-03`: armips source in the repo, horizontal
      advance, per-glyph width table, wrapping inside the existing box, free space located in
      the executable (it is exactly `0x80000` bytes — check the tail and dead debug code). Every
      patched site documented with what the original instruction did. Menus and other
      non-dialogue draw paths from `REC-06` are separate sites and are enumerated here, not
      discovered at release — every comparable project needed **one hack per text surface**, and
      every `strlen`-based centring or right-align routine is wrong once widths vary. Free space,
      cheapest first: the PS-X EXE header past `0x4C`, unused PsyQ debug-font routines
      (`FntLoad`/`FntPrint`…), then growing `t_size`. Every injection inside an armips `.area`
      so overflow fails the build. Consider writing the new routine in C (`.importobj`). Harmed: the player.
- [ ] **[TXT-06]** **The font.** If `TXT-03` needs a replacement sheet: a font under SIL OFL (or
      drawn for the project) so the repo stays fully open, rendered to the engine's cell format
      by a tool in the repo, with the width table generated from the same render.
      `[MINE: product]` for the typeface itself. Harmed: the player (legibility at 320×240 on
      a phone screen in Mode One is the hard case) and the repo's licence cleanliness.
- [ ] **[TXT-07]** **Measure what each box can hold.** For every box geometry the game uses:
      lines × pixel width under the new renderer. Output is data the translation lints and the
      translation agents both consume. Harmed: the player, by text that overflows; the
      translators, by limits discovered after the fact.

## Pipeline

- [ ] **[PIPE-01]** **Extraction to stable line ids.** An id names a line by where it lives
      (file, table, index), not by its content or a running number, so ids survive a
      translation edit and mean the same thing on every contributor's machine; duplicated
      copies (`REC-03`) share one id with many sites. The import step writes the Japanese, with
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
      (`REC-01`, `REC-02`), write every duplicated site. **Growth is this row's problem, never the translation's**
      (README § "Who this is for"): relocate, use the filler sectors (`PIPE-04`), or write new
      packing/compression and its MIPS decoder. Harmed: the player.
- [ ] **[PIPE-04]** **Image build.** Patch sectors in place and keep the image length identical
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

- [ ] **[TRN-01]** **The style guide and the story bible.** The charter is settled (README
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
      work is a whole scene as a flow graph, with speakers, choices and branches, the box
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
      preservation, so this is ours: decode → encode is byte-identical over **every** TIM on
      the disc (fixtures derived from the disc, never typed), depth/size/origin never change,
      shared palettes are not modified and edits map to existing entries, wired into
      extract/reinsert and covered by the `PIPE-05` gate. Harmed: `GFX-03`.
- [ ] **[GFX-02]** **Evaluate the redraw path on a sample.** Three textures of different kinds
      from `REC-08` (scoped with DuckStation's texture dump as a second inventory): have an image model (Jay's proposal: ChatGPT) redraw them in English in
      the original style, quantise back to the original CLUT, and look at them in the game.
      If that fails, the fallback is Claude-drawn subtitles composited onto the texture.
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
