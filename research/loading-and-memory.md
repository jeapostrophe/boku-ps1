# Where loaded data goes, and how far it can grow (PLAN `REC-02` leftovers, `PIPE-03`'s unknowns)

Static analysis of `SCPS_100.88` and the seven `.OVL` members on the dump identified in
[disc-recon.md](disc-recon.md). RAM addresses (file offset = RAM − `0x8000F800`; overlays at
`0x80079A08`); symbol names are ours — [`symbols/loading.symbols.tsv`](symbols/loading.symbols.tsv).
*Measured* means read from code or computed from the disc's bytes; nothing here was run, and
every absolute arena address below is **computed** from pack offsets and `g_cd_dir_size`
(`work/rec06/arena.py`), not observed. Containers and the directory:
[boku-bin.md](boku-bin.md). Block and text formats: [text-format.md](text-format.md).

## The short answer for the reinserter

| what grows | hard limit (measured in code) | tightest case on the disc |
|---|---|---|
| a **map pack**'s children 0–5 (child 1 is the text) | the offset of child 6 — the word at pack `+0x34` — must be **≤ `0x6400`**, or `map_commit` executes `break`. Stricter in practice: `+0x34` + 12 × (child 0's animated-object count) ≤ `0x6400`, because the game uses the bytes from `+0x34` on as a work area once the pack is live. | `M_H06001`: **2,664 bytes** left (child 1 there is 10,576 bytes). `M_H24200` 2,804, `M_H24100` 3,084, `M_G15200` 3,496, `M_G15000` 3,544 (child 1: 11,992). p10 8,160 · median 12,624. |
| a whole map pack | sector-rounded size ≤ 128 sectors (262,144 bytes): the load buffer runs into the field mode's arena after `0x40400` bytes | largest is `M_H24100`, 220,156 bytes = 108 sectors. Never binding before the row above. |
| an **`EV.BIN` member** | none of its own. The members demand-loaded for one map share **one `0x4000`-byte buffer**, at most 10 of them, each costing its 4-aligned size — and the last one its sector-rounded size in the overflow test | *not bounded statically.* A day-only bound (below) already reaches 16,604 of 16,384 on `M_D07100`, so the shipped game sits near the limit on at least one map. **Treat `EV` growth as unsafe until measured.** |
| a text array in the EXE or an overlay | no slack at all, and **code after it cannot move** — overlays are entered by link-time `jal`s from the EXE | `MUSI.OVL` fills its region to within 10 bytes |
| `.SEC` / `g_cd_dir` fields | as in text-format.md § "What a reinserter rewrites" | — |

*Assumption, not a measurement:* English at one glyph per letter is about twice the glyph
count of the Japanese. If so the first row will bind on the
text-heavy maps, so `PIPE-03` needs one of the mechanisms in § "Making room".

## RAM map

| range | size | what | how known |
|---|---:|---|---|
| `0x80010000`–`0x80072670` | 402,032 | EXE text + data (file bytes `0x800`–`0x62E70`; last non-zero byte is at `0x80072669`) | header, `crt0_start` |
| `0x80072670`–`0x80079A08` | 29,592 | bss, zeroed by `crt0_start` (`0x80049154`) | measured |
| `0x80079A08`–`0x8008F3A4` | 88,476 | **overlay region** — `g_overlay_base` (`0x80068AF4`). One overlay at a time, loaded by the mode's init. `InitHeap` is also pointed here, but no `malloc` is linked: the PsyQ heap is never used. | measured |
| `0x8008F3A4`–`0x801F41F4` | 1,461,840 | **fixed arena**, laid out once at boot by bump allocation from `g_heap_top` (`0x80068AF0`, initial value `0x8008F3A4`) | computed |
| `0x801F41F4`–stack | ≈ 15,868 to `0x801F7FF0` | level-C mode arena (field). `bg_swap_in` uses `0x6000` bytes here as scratch, i.e. up to `0x801FA1F4` | computed |
| …–`0x801FFFF0` | — | stack, top from the EXE header and `SYSTEM.CNF`. The `0x8000` "stack size" (`0x80068BA8`) only feeds the unused `InitHeap`; nothing guards it. `main` zeroes `g_heap_top`…`0x801FFFC0` before anything else. | measured |

The EXE header's `t_size` is `0x7F800`, so the BIOS loader also writes the file's zero tail over
`0x80072670`–`0x8008F800`; all of it is bss, overlay region or arena and is re-initialised.

**RAM is full.** There is no allocator with free space to ask: every buffer is a constant
offset from the previous one.

### The fixed arena, in order

`sys_init` (`0x80011E80`) takes the first four rows; `boot_load_resident` (`0x8001218C`) the
rest. A resident file whose init function returns a pointer is **truncated in RAM** at that
pointer: its trailing TIM has been uploaded to VRAM and the next file is loaded over it.

| computed address | size | content | pointer kept at |
|---|---:|---|---|
| `0x8008F3A4` | `0x800` | scratch | `g_scratch800` `0x800258C4` |
| `0x8008FBA4` | 2 × `0x8000` | ordering tables | `g_ot` `0x80025948` |
| `0x8009FBA4` | 2 × `0x130B0` | primitive buffers | `g_prim_buf` `0x800258E8` |
| `0x800C5D04` | 580 | `BOKU_XA.XCH` (6) | `g_xa_clips` `0x80035798` |
| `0x800C5F48` | 19,104 kept | `ONMEM.BIN` (153) up to child 2 (the font TIM — [font.md](font.md)) | several |
| `0x800CA9E8` | 5,168 | `EVVER.BIN` (31) | `g_evver` `0x800278E8` |
| `0x800CBE18` | 8,272 kept | `SUB.BIN` (224) up to child 3 | `0x800258D8` (child 2) |
| `0x800CDE68` | 1,596 | `EV.SEC` (30) | `0x800278B0` |
| `0x800CE4A4` | 8,884 | `M_FILES.SEC` (144) | `0x80026BD4` |
| `0x800D0758` | 924 | `H_FILES.SEC` (44) | `0x80027568` |
| `0x800D0AF4` | 600 | `MUSIDATA.BIN` (130) | `g_musidata` `0x800278F0` |
| `0x800D0D4C` | 2,776 kept | `FS00.BIN` (34) up to child 2 | `0x80028860` |
| `0x800D1824` | 1,744 | `MOV_VOL.BIN` (128) | `g_mov_vol` `0x800287A0` |
| `0x800D1EF4` | 220 | `KAGO_UV.BIN` (52), after `NUMBER.TIM` and `MITIM.BIN` were loaded here and uploaded | `g_kago_uv` `0x800477E0` |
| `0x800D1FD0` | `0x8980` | three insect-cage work buffers | `0x800478B0`… |
| `0x800DA950` | 11,108 | `KAGO.BIN` (50) | `0x800477DC` |
| `0x800DD4B4` | 16,704 kept | `MDLTIM.RTM` (53) up to child 1 | `0x800287A8` |
| `0x800E15F4` | `0x6400` | sound work | `0x8002859C` |
| `0x800E79F4` | 2 × `0x4000` | **`EV` member buffers** | `g_ev_buf` `0x80027808` |
| `0x800EF9F4` | 10 × `0x4000` | slots: insect models `MI%02d.BIN`, demo keys | `g_slot4000` `0x800278F8` |
| `0x801179F4` | `0x6400` | **"A": the live map's children 0–5** | `g_map_live` `0x800258D0` |
| `0x8011DDF4` | `0x96000` | model pool, 40 × `0x3C00`, `H_FILES` members, compacted on free | `g_model_pool` `0x80026C50` |
| `0x801B3DF4` | `0x6400` | **"B": where every map pack is loaded** — the pack runs on through the next two rows | `g_map_load` `0x800258D4` |
| `0x801BA1F4` | `0x8000` | saved VRAM CLUT rows of the other map | `g_bg_clut_save` `0x800258C8` |
| `0x801C21F4` | `0x32000` | saved VRAM background of the other map, 8 strips × `0x6000` | `g_bg_save` `0x800258C0` |
| `0x801F41F4` | — | end of the fixed arena | `g_arena_lvl_c_init` `0x800258DC` |

`SUB.TIM`'s, `T_*`'s and the other big files' destinations are the mode arena (next section).

### Modes and the three arena levels

`g_modes` (`0x800236BC`) has 18 records `{update, init, vsync, void **arena_base}`. `mode_set`
(`0x80011A98`) resets `g_arena_cur` (`0x800258E0`) to `*arena_base`, so **entering a mode frees
everything above its level**, and a mode's loads bump-allocate from there with
`g_arena_cur += cd_dir_size(i)`:

| level | base | bytes to `0x801F7FF0` | modes | cost of entering |
|---|---|---:|---|---|
| A `0x800258F4` | `0x801179F4` | 919,036 | 0, 1 `BUMPER`, 2 `TITLE`, 8, 11–13 `ZUKAN` (the diary), 14, 16 `ENDOTI` | the live map, the model pool and both map halves are overwritten |
| B `0x800258F8` | `0x801B3DF4` | 279,036 | 3, 4 (menus), 6 `TAKO`, 7 `MUSI`, 10 `HHON`, 15 `TITLE` (saving from the game) | the other-map half and the saved background are overwritten; A and the models survive |
| C `0x800258FC` | `0x801F41F4` | 15,868 | 5 (field), 9, 17 | nothing |

## Map packs

1. `map_load` / `map_load_async` (`0x80017534` / `0x8001756C`): `map_select(name)`, then
   `file_load(144, *g_map_load)`. The **whole pack lands at B** — it overruns B's `0x6400` bytes
   into `g_bg_clut_save` and `g_bg_save` by design, destroying the saved background of the map
   before last. `ev_list_init` (`0x80019C54`) reads the pack's children 0 and 1 *here*, while
   the previous map is still live.
2. `map_commit` (`0x8001770C`), when the pack's first word is non-zero:
   `if (pack[+0x34] > 0x6400) break;` then `bg_swap_in` (`0x8001E46C`) walks child 6 strip by
   strip from the last to the first — `StoreImage` the old background out of VRAM into scratch
   at `g_arena_cur`, `LoadImage` the new strip, copy the old strip to `g_bg_save + k·0x6000` —
   which is safe in place only because child 6 starts below B + `0x6400` and (*inferred, not
   asserted by the code*) a strip of the new TIM is never longer than `0x6000`. Then `mem_swap(A, B, 0x6400)` and the pack's first word at
   B is cleared. With no pack loaded (walking back through a door) `bg_swap_back`
   (`0x8001E65C`) swaps VRAM with the saved copy and A with B, with no disc access.
3. `map_init` (`0x800177F8`) reads children 0–5 **from A**. Child 6's address there (A +
   `pack[+0x34]`) no longer holds a TIM; `map_anim_init` (`0x8002A3A4`) returns it as a work
   array of 12-byte records, one per animated object listed in child 0. If that ran past A +
   `0x6400` it would write into the model pool. Largest count on the disc: 14.

So: **everything but child 6 must fit in `0x6400` bytes including the 60-byte pack table**, with
the work-area allowance. Per-map head room: `work/rec06/mapstats2.py`.

### The role of each child

| child | content | points into child 1? |
|---|---|---|
| 0 | `u32 n`, `n` × `0x14`-byte **event placements** — `s16` at `+0x12` is the event id, **negative = "load from `EV.BIN`"** — then the map header (`map_child0_parse` `0x8001727C`): a `0x14`-byte header, a `u32` count + 8-byte records, a `u8` count + variable-length animated-object records, then 4-aligned counted sections (10-, 11-, 10-, 9-word records) | **by event id only**, never by offset (`ev_list_step` finds the block with `0x80019A30`, a walk of child 1's table). Agrees with the statistics in text-format.md. |
| 1 | event table and blocks (text-format.md) | — |
| 2 | `u32 n` + records, handed to `map_anim_init` | no |
| 3 | optional TIM 98×79, uploaded by `map_init` to the VRAM position in `SUB.BIN` child 2 `+0xE8…0xF2` | no |
| 4 | optional; pointer kept at `0x80027924`; **consumer not read** | *hypothesis:* no (REC-03's statistics) |
| 5 | optional 12-byte records, count = size / 12, kept at `g_vol_recs` `0x800286FC` — the same records as a section of `MOV_VOL.BIN` | no |
| 6 | background TIM | no |

When child 1 grows, the reinserter rewrites the pack table (`offset` of children 2–6, child 1's
`size`), keeps 4-alignment, and checks the limit above. Nothing inside a sibling changes.

## `EV.BIN` members

`ev_list_step` (`0x80019DEC`) runs once per placement of the *incoming* map. For a negative id
that passes `ev_placement_ok` (`0x80030784`) it calls `event_select`, then
`file_load_async(30, g_ev_cursor)`, advances `g_ev_cursor` (`0x800278EC`) by the 4-aligned
size, and **after issuing the read** tests
`g_ev_buf[other] + 0x4000 <= dst + sectors × 0x800` → `sjis_panic_print("event buffer over")`.
`g_ev_loaded` caps the number at 10 per map. The two `0x4000` buffers alternate between the
live and the incoming map.

`ev_placement_ok` admits a placement when the id's hundreds (`id / 100`) are 0, above 39, or
equal to today's date — so **`E0607` is "day 6"** — and then runs the stub block's entry 1
(the "trigger/actor data" of text-format.md) as a condition script. Ignoring the script, the
worst day per map (`work/rec06/evstats.py`) is `M_D07100` / `M_D07000`: 10 members, cursor
16,232, peak test value 16,604 > 16,384. The scripts must exclude at least one of those in
practice; **how much head room really exists is an emulator question** (below).

## Overlays

All seven load to `g_overlay_base` = `0x80079A08` and are called at link-time addresses. The
region is sized for `MUSI.OVL`:

| overlay (index) | bytes | free to `0x8008F3A4` | loaded by mode |
|---|---:|---:|---|
| `BUMPER` (8) | 2,000 | 86,476 | 1 |
| `ENDOTI` (28) | 1,832 | 86,644 | 16 |
| `ZUKAN` (265) | 13,968 | 74,508 | 11, 12, 13 (`0x800138E4`) |
| `HHON` (42) | 27,660 | 60,816 | 10 |
| `TAKO` (239) | 30,806 | 57,670 | 6 |
| `TITLE` (244) | 34,532 | 53,944 | 2, 15 |
| `MUSI` (129) | 88,466 | **10** | 7 |

An overlay may therefore be **extended at its end** (raise `g_cd_dir_size`; new arrays or code
go there and the `lui`/`addiu` pairs are repointed) — except `MUSI`. *Hypothesis:* no overlay
uses memory past its file end as bss; a `lui`-pair scan finds no genuine access there, only
stale-register artefacts. The field modes load no overlay, so the region holds whatever ran
last; it is not a home for code that must persist.

## Other destinations

* `H_FILES` members → `g_model_pool`, in `0x3C00` units (allocator in `0x80018CA0`): no text.
* Insect models `MI%02d.BIN` → `g_slot4000[k]` (largest `MI60` is loaded by `MUSI` itself).
* BGM banks (`SAMP.BIN`, `SBGM%02d.BGM`) are staged **at B** by `bgm_bank_load` (`0x8001DE0C`)
  and copied out — one more reason B's tail is never stable.
* Everything loaded by a mode (`SUB.TIM`, `T_TITLE`/`T_CONFIG`/`T_MEMORY`, `TZKAN`, `PK_*`,
  `TK_*`, `FS_WAL`, `FISH00`, `NIKKI.SEC`, a diary page…) goes to `g_arena_cur`.

## The nine computed-index `file_load` sites

| site | index | loads | to |
|---|---|---|---|
| `0x80019204` (`kabu_load`) | 45 + n (0–4) | `KABU_0n.KBD`; 1000 bytes copied to `0x80035F50` | `g_arena_cur` |
| `0x8001DE78` (`bgm_bank_load`) | 163 + n | `SAMP.BIN`, `SBGM01`…`15.BGM` | B |
| `0x80020E38` (`demo_start`) | 11 + n | `DEMO_0n.KEY` | `g_slot4000[0]` |
| `0x8003AD04` | 39 + table `0x8003DAC0[k]` | `FS05.BIN`, `FS06.BIN` (fishing) | `g_arena_cur` |
| `0x8003AE88` | 35 + fish (0–2) | `FS01`…`FS03.BIN` | `g_arena_cur` |
| `0x800406B8` (`insect_model_load`) | 54 + n | `MI%02d.BIN` | `g_arena_cur`, then a slot |
| async `0x8001A0D0` | 54 + n | `MI%02d.BIN` | B |
| `0x80040E10` (`pack_menu_load`) | 160 + n | `PK_ITM` / `PK_PHO` / `PK_WAL` | `0x80047E4C` |

`0x8003ADD0` (index 38, `FS04.BIN`) and `0x80043C0C` (41, `FS_WAL.BIN`) in boku-bin.md's list
are constants. The overlays add 19 more computed sites (`MUSI` 11, `HHON` 3, `TAKO` 2,
`ENDOTI` 1, `ZUKAN` 2 — one is the diary desk sheet `Z_A0n` / `Z_N0n`, 266 + n before 19:00 and
272 + n after). *The other 18 were not read.* The text-bearing members cannot be among them:
map packs and `EV` members are reached only through slots 144 and 30, whose load sites are all
constant-index.

## The ten `unknown` members

| member | what it is | consumer |
|---|---|---|
| `BOKU_XA.XCH` (6) | `u32 48`, 48 × 12-byte XA clip records | `xa_init` `0x8002AFB4` → `g_xa_clips` |
| `DEMO_00`…`04.KEY` (11–15) | attract-mode replay: `char map[8]`, day at `+8`, hour `+9`, flags, then pad-input records from `+0xC` | `demo_start` `0x80020DA0` |
| `EVVER.BIN` (31) | **map-variant selector**: 9 `u32` offsets by area letter (`'A'`…), each a table of `{char name[3], …, u32 day_mask (bit 31 = also run a condition), char set[4], char suffix[]}`; appends the variant digits to a 3-character map base | `map_variant_name` `0x80030CD0` |
| `KAGO_UV.BIN` (52) | `u32 18`, sprite UV/size records for the insect-cage UI | `0x80042ABC`, `0x80042B28` via `g_kago_uv` |
| `MOV_VOL.BIN` (128) | sections `"MOV\0", u32 movie_id`, then 12-byte volume records; a map's child 5 has the same records | `0x8001E300` scans `g_mov_vol` for the section; records read through `g_vol_recs` |
| `MUSIDATA.BIN` (130) | 60 × 10 bytes of insect stats (`+7` = class 0/1/2) | `g_musidata`, 8 sites |

None holds text.

## `g_cd_dir`'s two unknown words, and the `NIKKI.SEC` consumer

* `+0x0C` (`0x800246A4`, `NULL`) is a **fourth parallel array that the build did not emit**;
  `cd_dir_attr` (`0x80012DBC`) would index it and has no caller. The struct is
  `{count, lba*, size*, attr* = NULL, name*}` and ends there.
* `0x800246AC` is **not part of the directory**. It is a separate `u32` (`g_title_hold`): the
  title mode's update (`0x800131A8`) skips `TITLE.OVL`'s per-frame function while it is
  non-zero. Zero in the file; no writer found in any code file (*hypothesis:* a debug switch).
* `nikki_select` (`ZUKAN.OVL` `0x8007A180`) loads `NIKKI.SEC` (150) into the mode arena on
  every call, finds the record whose `id` equals its argument, and rewrites **slot 149 itself**
  — `lba[149] = g_nikki_lba + sector`, `size[149] = size`,
  `name[149] = sprintf("…NIKKI_%02d.TIM")` — then `file_load_async(149)`. Unlike the other three
  sub-archives the virtual file is the container's own slot, which is why `cage_init` saves
  `lba[149]` in `g_nikki_lba` (`0x80048018`) at boot. What the ids mean:
  [text-outside-events.md](text-outside-events.md) § "The picture diary".

## Making room

Proposals 1 and 2 are done and measured (2026-09-20; `asm/vwf.asm`, `asm/arena.asm`,
[vwf-prototype.md](vwf-prototype.md) § "The map work area" holds the numbers: the stack's
low-water mark, the margin the two raises leave, and the guard the assembler applies).
3 and 4 remain proposals.

1. **Every buffer address derives from one word.** Raising the initial `g_heap_top`
   (`0x80068AF0`) by N opens N bytes at `0x8008F3A4` that nothing else uses, and costs N of the
   margin at the top: `0x801FFFF0 − (0x801F41F4 + 0x6000)` = 24,060 bytes less the real stack
   depth. That is the natural home for relocated arrays and new renderer code. *Done: the
   width table and hook bodies live there.*
2. **`0x6400` is a constant in three places** (`boot_load_resident`'s two bumps and
   `map_commit`'s test and swap length). Raising it by Δ costs 2Δ of the same margin. *Done:
   raised to `0x7C00`; an exhaustive immediate scan of the EXE and all seven overlays found no
   fourth site (the `0x6400` at `0x80012308` is the sound work buffer's size).*
3. **Child 3 is 8,286 bytes of every tight map** and is uploaded once by `map_init`. Uploading
   it in `map_commit`, before the swap, would let it live after child 6 and return 8 KB of the
   `0x6400` to text. 483 of 555 maps have one.
4. 5,120 bytes of dev-time path strings (`0x800101D8`–`0x800115D8`, directory indices 3–277)
   are referenced only through `g_cd_dir_name` by the PC-host path, which is dead
   (`g_pc_host` is cleared by `sys_init` and never set). The pointer array itself must stay —
   the four `*_select` functions write into it — and indices 279–304 are live (`.IKI` names
   go to `DsSearchFile`).

## Not settled statically — as emulator questions

* **Arena addresses.** Break at `0x800123D0` (end of `boot_load_resident`); read the pointers
  in the table above. Expect `*0x800258D0 = 0x801179F4`, `*0x800258D4 = 0x801B3DF4`,
  `*0x800258DC = 0x801F41F4`.
* **`EV` head room.** Break at `0x8001A004` (after `file_load_async(30, …)` in `ev_list_step`)
  and log `*0x800278EC − g_ev_buf[*0x80024784 ^ 1]` and `*0x800278E4` per map across a
  playthrough; the maximum is the real figure. Start with `M_D07100` on days 22–31.
* **Stack depth.** *Measured* on one route (boot → day 1 → three map changes → SELECT → day
  2) with `tools/vwf/stack-probe.lua` on PCSX-Redux and a sentinel fill on Beetle:
  [vwf-prototype.md](vwf-prototype.md) § "The map work area". Menus, bug sumo and fishing are
  unwalked.
* **Work-area overrun.** Watch writes to `*0x800258D0 + 0x6400` (first word of the model pool)
  from `map_init`'s callees; should never fire on the shipped disc.
* [tooling-setup.md](tooling-setup.md) reports RAM under PCSX-Redux not matching the file at
  `0x80010000`. Statically the file is self-consistent at its header's load address — `crt0`'s
  bss bounds, every `jal` and every `lui` pair agree with it — so that finding is about the
  emulator session, not about relocation. Break at `0x80049154` and read `0x80049154` itself.
