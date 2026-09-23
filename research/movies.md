# The movies — player, table, and the two ways to subtitle them (PLAN `FMV-01`)

Measured 2026-09-21 on the Ghidra program (`research/tooling-setup.md` § Ghidra; scratch
decompiles under `work/fmv01/decomp*.txt`) and on headless PCSX-Redux (`work/fmv01/*.lua`,
logs and the `movie.sstate` save state beside them). Every address is a run-time address in
`SCPS_100.88`; names are ours and live in `research/symbols/SCPS_100.88.symbols.tsv`. Nothing
here quotes the disc: frame counts and sector counts are measurements, not content.

What the other notes already say and this one does not repeat: the `.IKI` files are Sony
IKI-variant STR, 320×240, 10 sectors per frame at 2× (`related-projects.md` § jPSXdec index,
`ps1-translation-practice.md` § 0 and § 6); the disc layout (`disc-recon.md`, `boku-bin.md`
§ directory); the `MOVIE` opcode and `END`'s mode switch (`event-scripts.md` § opcodes); the
text renderer and the VWF patch (`font.md`, `text-renderer.md`, `vwf-prototype.md`).

## 1. Which movie is which — `g_movie_table` `0x80029604`

**The list itself lives in `research/data/movies.tsv`** — generated from this section and
§ 2.1 by `./make.sh movies`, which also decodes every movie into `work/movies/*.avi` with
the narration muxed in. Its columns are tabulated at the end of this section.

The `MOVIE` opcode's number is an index into a 27-entry table, 0x18 bytes each: `char *name`
(`\__STR\M*.IKI;1`), `u16 dir_index` (0 in every entry — the player takes the by-name path
because `g_movie_by_name` `0x800295E8` is 1), `u32 channel` (1 in every entry), `u32 frames`
(the stop frame: `movie_get_frame` raises `g_movie_ended` when the STR header's frame number
reaches it), `u16 x, y` (the VRAM origin, 0,0), `u16 disp_w, disp_h` (320×240).

| id | file | stop frame | issued by (`data/scene-edges.tsv`) |
|---|---|---|---|
| 0 | `M27` | 58 | nothing in the events; issuer unread |
| 1 | `M010` | 139 | nothing in the events; issuer unread |
| 2, 3 | `M031`, `M032` | 47 | `E4015` |
| 4, 5 | `M033`, `M034` | 47 | `E4016` |
| 6 | `M050` | 152 | `E4030` |
| 7 | `M080` | 153 | nothing in the events; issuer unread |
| 8 | `M100` | 67 | `E0809` |
| 9 | `M110` | 107 | `E0906` |
| 10 | `M120` | 152 | `E1008` |
| 11 | `M130` | 100 | `E2606`, `E2607` |
| 12 | `M140` | 122 | `E2108` |
| 13 | `M180` | 92 | `E1706`, `E2305` |
| 14 | `M190` | 677 | `E2605` |
| 15 | `M27` | 58 | nothing in the events; issuer unread |
| 16, 17 | `M21`, `M22` | 527, 512 | nothing in the events; issuer unread |
| 18 | `M250` | 227 | `E0607`, `E2306` |
| 19 | `M260` | 347 | nothing in the events; `movie_queue_play` waits 180 vsyncs before it |
| 20 | `M40` | 107 | `E0009`, `E0103`, `E0303`, `E1503`, `E1803`, `E1903`, `E2003`, `E2203`, `E2303`, `E3005` (map `G02`), `E2803` (`I30`) |
| 21 | `M60` | 362 | `E0805` |
| 22 | `M70` | 77 | `E0004`, `E4019`, `E4020`, `E4054` |
| **23** | **`M27`** | **4239** | **the opening**: after the memory-card check the queue holds this one id (measured, `work/fmv01/probe1.log`: `play_one entry=23`) |
| **24** | **`M28`** | **4194** | **the ending**: `E3182` (`event-scripts.md` § END); the only entry whose skip mask is 0 — it cannot be skipped; `movie_queue_play` switches to mode `0x10` after it |
| 25 | `M160` | 157 | `E1406` |
| 26 | `M230` | 92 | `E0182` |

So `M27` is the opening and `M28` the ending, not "the endings" — `ps1-translation-practice.md`
§ 6.1's inference was half right. **There is one ending movie.** How the five epilogues of
`translation/voice-only.md` differ is not in this table: whatever varies must live in mode
`0x10` (record functions `0x80013E54` / `0x80013E74`, unread) or in the events around
`E3182`. Left for `FMV-02`.

Frame numbers in the STR headers are 1-based; jPSXdec's index reports 4244 frames for `M27`
(header frames "1–4239.5/5": five duplicated headers) — the game stops at header frame 4239.

`research/data/movies.tsv`'s columns, and where each is derived from — nothing in it is
typed by hand except the last two, which a regeneration carries across:

| column | derived from |
|---|---|
| `id`, `file`, `stop_frame` | the table above |
| `skippable` | § 2.1's skip masks; mask 0 means it cannot be skipped |
| `frames` | the extent on the disc, at 10 sectors a frame (§ 4) |
| `seconds` | `stop_frame` / 15 (the only home of that number) |
| `shares_file_with` | the other ids playing the same file |
| `issued_by` | `data/scene-edges.tsv` — the same derivation as the table above's last column |
| `what_it_shows`, `notes` | written by hand, from watching the movies |

`tests/test_real_movies.py` refuses a table that has drifted from this section.

## 2. The player

### 2.1 Call chain

`ev_op_movie` `0x800300FC` (opcode `22`) pushes the id into `g_movie_queue` `0x80036560`
(word 0 = count, words 1… = ids; an event's start clears the count in `0x8002CD8C`), copies the
return map name to `g_movie_return_map` `0x80036588`, and sets bit 3 of the event-runner
flags; `END` then switches the game mode. The mode's entry function is **`movie_queue_play`
`0x800139E4`** (measured: it runs with the mode byte `0x800237E0` = `0x0E`; it is word 1 of
the record at `0x80023798`, and `0x80013C58` `movie_queue_volume_init` — per-movie `MOV_VOL`
handling through the byte table `0x800246C4[id]` and the scanner in `loading-and-memory.md` —
is word 2. `game_mode_set`'s decompile reads the record table as `0x800236C8 + 16·mode`, which
would make this mode 13; the measurement wins, so the base or the index is off by one there —
*hypothesis*, not chased). It:

1. `movie_skip_mask_for(g_movie_queue[1])` `0x80034FA4` → `movie_set_skip_mask` `0x800344D8`:
   ids 1–5, 16, 17, 20 → `0x0860`; 24 → 0; every other id → `0x0800` (the pad word the
   player tests is the remapped one at `0x80072766`; `0x0800` is what START produces —
   `tools/redux/boot-to-dialogue.lua` skips the opening with it).
2. `SetDispMask(0)`, `ClearImage` of both 320×240 field buffers (y 0 and 272).
3. **`movie_play_list(g_mode_arena, count, &g_movie_queue[1])` `0x80035004`** — blocking; the
   game's main loop, its OT flip and its `DrawOTag` do not run until every queued movie ends.
4. Clears both buffers again, `PutDispEnv`/`PutDrawEnv` of the field's pair
   (`0x800259AC` / `0x80025950` + parity × 0x78), mode 5 and the map load of
   `g_movie_return_map` (`0x80017DB0`) — or mode `0x0F` when the previous mode was `0x0B`,
   or `0x8002E8EC` + mode `0x10` after id 24.

`movie_play_list`: `DrawSync(0)`, `ResetGraph(1)`, `movie_alloc_buffers(arena)` `0x800344E4`,
then per id: `ResetGraph(1)`, **`movie_play_entry(&g_movie_table[id])` `0x80034594`**,
`DecDCToutCallback(0)`, `StUnSetRing` (`0x800666F0`), `DsControl(CdlPause)`. A return of 2
(skipped) ends the list with −1.

`movie_alloc_buffers` carves the mode arena (`g_mode_arena` `0x800258E0`, the heap bump at
mode entry — `0x801179F4` measured): ring `g_movie_ring` `0x800366D4` = arena (32 sectors ×
0x800), `g_movie_vlc_buf0/1` `0x800366DC/E0` (0x28000 each), `g_movie_img_buf0/1`
`0x800366E4/E8` (`disp_h × 0x30` = 11,520 bytes each: one 16-pixel-wide slice, 240 rows, **3
bytes per pixel**), `g_movie_vlc_table` `0x800366D8` (+0x10000). "Movie End Address" =
`0x8018D3F4` measured; RAM from there to the stack (`0x801FFFF0`) is unused during a movie.

`movie_play_entry` copies the entry into `g_movie_name` `0x80036680`, `g_movie_dir_index`
`0x80036684`, `g_movie_channel` `0x800295EC`, `g_movie_frames` `0x80036688`, `g_movie_x/y`
`0x8003668C/8E`, `g_movie_disp_w/h` `0x800295F0/F2`; sets `g_movie_buf1_y` `0x800295F4` =
`0x110` (272), `g_movie_fade_vol` `0x800366F2` = 0x7F, `g_movie_skip_count` `0x800366F0` =
0xFF ("not skipping"), `g_movie_fade_frame` `0x800366F4` = frames − 3; loops
**`movie_run` `0x80034668`** while it returns 0; restores the CD volume (`cd_volume_set`
`0x800656C0`, the mixer word at `*0x80077E34 + 0x1B0`). Returns 2 when skipped.

### 2.2 `movie_run` — the frame loop (the PsyQ `movie` sample, IKI-flavoured)

Set-up: `DsSearchFile(&g_movie_file 0x80036668, g_movie_name)`; `movie_env_init`
`0x80034A08` fills **`g_movie_env` `0x80036698`** (+0 `vlc[2]`, +8 `vlc_idx`, +0xC `img[2]`,
+0x14 `img_idx`, +0x18 `rect[2]` = (0,0,·,·) and (0,272,·,·), +0x28 `vram_buf`, +0x2C the
slice rect (x, y, **w = 0x18 halfwords**, h), +0x34 `frame_h`, +0x38 `frame_done`);
`movie_stream_start(pos, movie_dctout_cb)` `0x80034A7C` = `DecDCTReset(0)`,
`DecDCToutCallback`, `StSetRing(ring, 32)`, `StSetStream(1, channel, −1, 0, 0)`,
`movie_cd_start(pos)` `0x80034F30` (`DsControl(SetLoc)`, `DsControl(SetMode, 0x80)`,
`VSync(3)`, `DsRead2(pos, 0x1E0)` — `0x1E0` = 2× | XA-ADPCM to SPU | 2340-byte sectors:
**the narration is the XA audio interleaved in the `.IKI`** — ffprobe sees one stereo
37,800 Hz `adpcm_xa` stream — decoded by the CD hardware, faded by `movie_frame_volume`);
`DecDCTvlcBuild(table)`; one `movie_next_frame` to prime `vlc[0]`.

Then, per frame (addresses from `work/fmv01/listing4.txt`):

| step | call | what |
|---|---|---|
| a | `0x800347B4` `DecDCTin(vlc[vlc_idx], 3)` | kicks the MDEC on the VLC-decoded frame. Mode 3: bit 0 set → `and 0xF7FFFFFF` clears bit 27 of the MDEC command → output depth 2 = **24-bit RGB** (`DecDCTin` disassembly `0x80067908`; depths per the MDEC command word); bit 1 → sets bit 25 (the "bit 15" flag, meaningless in 24-bit). |
| b | `0x800347EC` `DecDCTout(img[img_idx], 24·h/2)` | first slice out: 24 halfwords × 240 rows = 16 pixels × 3 bytes. |
| c | `0x800347F4` `movie_next_frame(&env)` `0x80034C2C` | `movie_get_frame` `0x80034CB0` polls `StGetNext` up to 2000× (×2000 outer); on a frame: **`movie_frame_volume(header.frame_no)` `0x800350F8`** (the fade), `g_movie_ended` if ≥ `g_movie_frames`, on a size change `ClearImage` of both VRAM rects and the rect widths = `frame_w · 3 / 2`; then `movie_vlc_decode(sectors, vlc[!vlc_idx])` `0x80067F20` (the game's own VLC → MDEC-code decoder, IKI header; *hypothesis*: a customised `DecDCTvlc`), `StFreeRing`. On timeout: `StGetBackloc`, re-seek. |
| d | `0x80034868` `movie_wait_decoded(&env)` `0x80034E70` | spins on `frame_done` up to 0x800000 iterations ("time out in decoding"), clears it. |
| e | `0x80034870` `VSync(0)` | |
| f | `0x800348B0`…`0x80034930` | `SetDefDispEnv(0, (vram_buf==0)·272, disp_w·3/2, disp_h)`, `isrgb24 = 1` (`0x80034914`), `disp.w = w·2/3` (`0x80034924`), `SetDefDrawEnv` at the other y, `PutDispEnv`, `PutDrawEnv`, `SetDispMask(1)`. |
| g | | `g_movie_ended` → return 1; skip: `pad_read`/`pad_remap` (`0x8005BD9C`, `0x80011B08`), pad ∧ `g_movie_skip_mask` `0x800295F6` → `g_movie_skip_count` = 3, then three fading frames, return 2. |

**`movie_dctout_cb` `0x80034AF4`** runs on DMA1 completion, once per 16-pixel slice: takes
the slice rect, toggles `img_idx`, advances `slice.x` by 24; if the frame is not done, kicks
`DecDCTout` for the next slice, else sets `frame_done`, toggles `vram_buf`, and resets the
slice rect to `rect[vram_buf]`; then **`LoadImage(slice rect, img[previous])`** (`0x80034C14`)
— the picture reaches VRAM by DMA, never through the ordering table. The frame just
completed sits in `rect[!vram_buf]`, and step f displays exactly that one.

Measured on Redux (`work/fmv01/budget.log`, breakpoints kept alive — see
`tooling-setup.md` § PCSX-Redux for the `return true` rule): **4 vsyncs per STR frame**
(371 of 406 frames; 15 took 3, 19 took 5 and one was not classified by the probe — the ring's delivery jitter), **20 slices per
frame**, and between one frame and the next the loop made **8,000–35,000 `StGetNext` polls**.
The loop therefore idles most of each 66.7 ms frame waiting for sectors; Redux exposes no
cycle counter to Lua, so the idle time in milliseconds is unmeasured — *hypothesis*: the
polling alone is ≥ 8,000 call-return-check rounds, i.e. many milliseconds, and a slow frame
is tolerated (the loop waits on the ring, it never drops frames). The VLC decode
(`movie_vlc_decode`, software, ~16 KB per frame) is the only CPU work per frame.

### 2.3 VRAM during a movie — measured (`work/fmv01/states/movie.sstate`, first frame decoded)

`work/fmv01/vram-full/vram-movie-0-0-1024x512.png` (24-bit data viewed as 15-bit, so it looks
like noise): the frame occupies **(0,0)–(479,239) and (0,272)–(479,511)** — the field's own
double-buffer rows, but 480 halfwords wide (320 px × 3 bytes). The font page (768…831,
0…223) and the text CLUT rows (256…271, 256…263) hash identically in four states — before
the movie, in it, and the two post-movie states of `work/txt01-emu` (`sstate_vram.py` rects
`768,0,64,224` → `e5e83ab09c6e6563`, `256,256,16,8` → `6a2773b046fc3fd0`) — and the code
touches VRAM only through those two rects and their `ClearImage`s. **The font and its CLUTs
survive the movie untouched.** The display env is the same y pair as the field's but 24-bit
and 480 wide; `movie_queue_play` restores the field's pair afterwards. No ordering table is
built or drawn during a movie (`movie_run`'s callees contain no `DrawOTag`; the main loop is
suspended); `g_ot`, `g_prim_next` and `g_text_layer` are left as they were.

The current frame number is known every frame — it is the STR header's number, passed as
`a0` to `movie_frame_volume` and compared with `g_movie_frames`; it is not stored anywhere.

## 3. Engine path — what a subtitle hook costs

The reason no PS1 game draws text over FMV with the GPU: the frame is **24-bit** in VRAM and
the GPU draws 16-bit words. A 12×12 glyph sprite would land 8 pixels wide, and every word
that straddles a pixel boundary corrupts one channel of a neighbour (measured nothing; this
is arithmetic on 3 bytes per pixel vs 2 per word). Two engine designs avoid it:

### E1 — play the movie in 15-bit and draw with the existing renderer (small)

Switch the decoder and display to 15-bit, then the frame is an ordinary 320×240 16-bit
buffer that `glyph_draw`/the VWF path can draw on. Words in `movie_run` and friends:

* `0x800347B8` `li a1,0x3` → `li a1,0x0` (`DecDCTin` mode 0: bit 27 stays set → depth 3 = 15-bit; bit 25 clear).
* `0x80034894`–`0x800348A8` and `0x800348D0`–`0x800348E4`: the two `disp_w·3/2` (SetDefDispEnv / SetDefDrawEnv widths) → `move a3,v0` + nops.
* `0x80034914` `sb v1,0x29(sp)` (`isrgb24 = 1`) → `sb zero,0x29(sp)`; `0x80034924` `sh v0,0x1c(sp)` (`disp.w = w·2/3`) → `nop`.
* `0x80034A54` `li v0,0x18` → `li v0,0x10` (slice width 16 halfwords = 16 pixels; `DecDCTout`'s size and `LoadImage`'s rect follow from it).
* `movie_get_frame`: `0x80034D80`–`0x80034D94`, `0x80034DC8`–`0x80034DDC` (the two `ClearImage` widths) and `0x80034E14`–`0x80034E2C` (the env rect widths) → `move` + nops.
* Frame number: `0x80034D00` `jal movie_frame_volume` → `jal` our `movie_subtitle_frame`, which stores `a0` and tail-calls the original.
* Draw: `0x80034870` `jal VSync` → `jal` our `movie_subtitle_draw`, which (i) looks up the cue for the stored frame in the current movie's table (the id is `g_movie_queue[1]` for a one-movie queue; for lists hook `movie_play_entry` and store `(a0 − 0x80029604) / 0x18`), (ii) points `g_ot` current (`0x8002593C`) at a private OT and `g_prim_next` (`0x800258F0`) at a private primitive buffer in the movie arena (both unused during a movie; save and restore around `movie_play_list`), (iii) runs the VWF string draw for one or two lines (`asm/vwf.asm`, `vwf-prototype.md` § the draw path) and `text_emit_tpage`, (iv) `SetDefDrawEnv(0, (vram_buf==0)·272, 320, 240)` — the buffer step f is about to display — `PutDrawEnv`, `DrawOTag`, `DrawSync(0)`, then `VSync(0)` and returns. 37 patched words by the list above (the width fix-ups are runs of 6–7) plus a routine of a few hundred bytes.

Cost: **the movies lose 24-bit colour** — 15-bit output is the MDEC truncating 8→5 bits per
channel with no dithering; dark gradients and fades (the opening's car interior, every fade
to black) are expected to band — predicted from the bit depth, not measured (the measurement
is one dark frame decoded, truncated 8→5 bits per channel, PSNR against the 24-bit decode).
That is the whole price; everything else is reuse.

### E2 — keep 24-bit and composite in software (Eight-Mansions' way, larger)

Hook `movie_dctout_cb` before its `LoadImage` (`0x80034C14`): for the slice about to be
uploaded (`img[previous]`, 48-byte rows, pixel (x, y) at `y·48 + x·3`, slice pixel origin
`slice.x / 1.5`), blit the cue's glyph pixels whose x falls in the slice's 16 columns —
white where the glyph mask is set, dark where the outline mask is set. Needs 1-bit glyph
masks in RAM (the sheet is in VRAM only after boot — `font.md` § How it reaches VRAM; built
from the same glyphs as the sheet, 14×14 so the outline has its margin, 6 KB for the VWF
set — § 7), per-slice clipping of glyphs that straddle a slice boundary, and a
frame-number hook as in E1. Runs in DMA-interrupt context — a few hundred pixel writes per
slice — while the CPU is otherwise polling the ring. No display or decoder word changes;
the picture is untouched outside the glyphs. **Built and measured: § 7.**

### Common to both

* **Where the cues live.** Not in the EXE: the heap-raise gap has 1,116 − 812 = 304 bytes
  after `vwf_advance` (`vwf-prototype.md` § free space) and the dead islands total ~3 KB
  (`text-renderer.md` § 6) — enough for the hook code, not for ~10 minutes of narration.
  So the cues and the glyph masks are a block on the disc, read at `movie_play_entry`
  into RAM above the movie's end address with the game's own reader: as built, § 7 and
  § 8.
* **Frame budget.** Either hook adds work that is small next to the VLC decode and sits in a
  loop that measurably idles (§ 2.2); the loop waits on the ring rather than dropping frames,
  so an overrun degrades to a late frame, not a glitch.
* **Testing.** Redux plays the movies headless (§ 2.2's numbers came from it) but its
  screenshots go black in this display mode (`tooling-setup.md` § PCSX-Redux), so a frame is
  read from the slice buffers in RAM (§ 7); Beetle is the confirmation target as always.

## 4. Burn path — what re-encoding costs

Tooling, measured:

* **ffmpeg cannot decode the video.** `-f psxstr` demuxes an `.IKI` (finds the video and the
  XA audio) but its `mdec` decoder rejects every IKI frame ("Decode error rate 1 exceeds
  maximum" on `M010`, zero frames out), and it has no MDEC/STR encoder at all
  (`ps1-translation-practice.md` § 6.4). Audio is fine: `ffmpeg -f psxstr -i M27.raw -map
  0:a:0 x.wav` gives the narration for transcription (`work/fmv01/opening-first20s.wav`).
* **jPSXdec v2.1 beta rev4378 is now installed** at `~/Dev/dist/jpsxdec/jpsxdec_v2.1-beta/`
  (zip sha256 `e11787a2e05b6a4b6ee07972439e50da9e6798f0ca505e748f4969b3d91cd45b`; runs on the
  Homebrew OpenJDK 21). It indexes the raw slice of `M27` as plain IKI (`Iki` bitstream, no
  Panekit obfuscation — the practice note's open question), decodes with `-q psx`, and its
  `-replaceframes` re-encodes IKI in place.

The constraint, measured on the sectors (`work/fmv01/M27.raw`, `M28`): a frame's slot is 10
sectors — up to 8 video, 1 audio (every 8th sector), the rest null. **The opening's frames
sit at the ceiling**: 3,912 of 4,239 use all 8 video sectors, max frame size 16,128 bytes =
8 × 2016 exactly, median 16,020. The ending: 3,448 of 4,194 at 8 chunks, median 15,840. A
subtitled frame has no spare bytes; jPSXdec re-quantises until it fits (and the IKI encoder
does not expand into null sectors — practice note § 6.2).

Quality, measured on header frame 601 of the opening (a dark car-interior shot;
`work/fmv01/burn-test.py`, both sides decoded with `-q psx`, PSNR over RGB):

| replacement | fits | PSNR vs the original decode, rows 0–199 (no text) | whole frame vs the original decode | whole frame vs the subtitled input |
|---|---|---|---|---|
| the unchanged decode re-encoded | 16,100 / 16,128 B | 49.5 dB | 50.0 dB | — |
| two 13-px lines, white with a 1-px black outline | 16,116 / 16,128 B | **45.0 dB** | not measured (the text rows differ by design) | 43.4 dB |
| same with `size-limit="original non-zero"` | 16,016 B | 44.9 dB | not measured | 43.4 dB |

So one subtitled frame costs about 4.5 dB against the rest of the picture on this frame —
visible only in a side-by-side (`work/fmv01/frame601-sub.png`). Unmeasured: bright, busy or
fast frames (where 16 KB is already tight), `partial-replace` (the Galerians note says it
flickers), and the whole-movie batch time (one `-replaceframes` pass scans the 100 MB file
in ~4 s; per-frame encode time was not timed).

Consequences that do not depend on quality:

* **Patch size.** Every touched frame rewrites 8 × 2048 bytes ≈ 16 KB. Opening + ending are
  8,433 frames; at 60 % of frames carrying text that is ≈ 80 MB of PPF, at 100 % ≈ 135 MB —
  against a few KB for the engine path.
* **Disc image.** In place: each replaced sector keeps its sync, header and subheader and gets
  new user data with EDC/ECC regenerated (jPSXdec `CdSector2352.rebuildRawSector`; if our
  pipeline writes the sectors, `boku/edc.py`). No LBA moves, nothing relocates. The build
  step would be: slice the file from the image, `-replaceframes`, splice the sectors back.
* **Authoring.** The look is fixed at encode time (any font, no VWF constraints); every timing
  or wording change re-encodes every affected frame; the decode and the reference video for
  timing must come from jPSXdec (`-vf avi:mjpg -psxav`), not ffmpeg.

## 5. The trade-off, for Jay's `[MINE: product]`

| | E1 15-bit + GPU text | E2 24-bit + software blit | burn with jPSXdec |
|---|---|---|---|
| picture | movies drop to 15-bit (banding in gradients) | untouched | ~4.5 dB lost on every subtitled frame (measured on one frame) |
| code | 37 words + a few hundred bytes; reuses the VWF renderer | 4 words + 620 bytes in one dead island (§ 7), runs in the DMA callback, needs glyph masks in RAM | none |
| data | cue blob in the relocation arena (KB) | same + masks | 16 KB per touched frame in the patch (tens of MB) |
| typography | the game's 12×12 sheet through the VWF path | same | any font, any size, any outline — fixed at encode time |
| re-timing a line | edit the blob | edit the blob | re-encode the frames |
| risk | the mode switch touches display/decoder words (all listed above) | interrupt-context timing; slice straddling | none new; jPSXdec is a beta |
| unmeasured | how much 15-bit bands (§ 3) | the blit on hardware timing; a cue over a bright, busy frame by eye (§ 7 has Redux and Beetle, pixel-exact) | bright/busy frames, `partial-replace` flicker, batch encode time (§ 4) |

Recommendation: the engine path. Between the two, E2 is the faithful one — it leaves the
picture exactly as shipped and its cost is assembly, which this project has already paid for
harder things — and E1 is the fallback if E2's callback timing misbehaves on hardware-like
timing. The burn path is what to reach for only if no assembly is wanted; its price is paid
on every frame with text, forever, and in patch size.

## 6. Probe notes (Redux)

`work/fmv01/movie-probe.lua` (first attempt), `budget-probe.lua` (the numbers above),
`pc-probe.lua`, `mode-probe.lua`, `stall-probe2.lua`. Two lessons recorded in
`tooling-setup.md` § PCSX-Redux: a breakpoint callback must `return true` to keep firing,
and the STR player streams fine headless (the earlier "the smoke run skipped it" was
`boot-to-dialogue.lua` pressing START, not an emulator limit).

## 7. E2 as built — one cue, measured on the opening (`FMV-04` milestone 1, 2026-09-22)

`asm/movie.asm` (included by `vwf.asm`, so every prototype build carries it), the block
encoder and reference rasteriser `boku/movie_block.py`, the probe `tools/redux/movie-sub.lua`,
the gate `tests/test_real_movie_subtitle.py` (two Redux boots; `./make.sh emu-test`). The cue
is a placeholder — two lines of the game's own first narration line over STR frames 120–300 —
hard-coded in `build_prototype.py`. That block carried no movie key, so the cue was drawn
over every movie whose frames reached 120, and `boku build --vwf` carried none of these
sites; both are milestone 2's, § 8, which also moved the loader and the block. What follows
is milestone 1 as measured, with § 8's changes named where they apply.

**Sites** (retail word → patched; the `ORIGINAL` arm carries each stock word):

| where | address | stock | now |
|---|---|---|---|
| `movie_play_entry`, before the frame loop | `0x8003462C`, `0x80034630` | `addiu a1,a1,-3` / `sw a1,0x66F4(v0)` | `jal movie_sub_load` with the `addiu` as its delay slot; the routine makes the store, then reads the block |
| `movie_get_frame` | `0x80034D00` | `jal movie_frame_volume` | `jal movie_sub_frame`: keeps `a0` at `movie_sub_frame_no`, jumps on |
| `movie_dctout_cb` | `0x80034C14` | `jal LoadImage` | `jal movie_sub_blit`: paints the cue into the slice, jumps on with `a0`, `a1`, `ra` intact |

**Where the code is.** The island `0x80012E04…0x80013070` (`text-renderer.md` § 6 candidate
2) held all three routines in milestone 1 — 620 of 620 bytes. Since § 8 it holds
`movie_sub_frame_no`, `movie_sub_frame` and `movie_sub_blit` (484 bytes; the addresses are the
build's, in `edits.json` → `movie_subtitles.islands`), and the loader is in the second
island. The island is not assembled under `ORIGINAL` (dead retail code has no stock
claim to check, and restating it would put 620 bytes of the executable in the repo). Its
deadness, inferred in `text-renderer.md`, is now measured on one path: an execution
breakpoint over the range logged **0 hits** from boot through the title, the card check and
the opening to STR frame 400 on the stock disc, where the same breakpoint over
`cd_load_sync` logs 181,076 (`tooling-setup.md` § PCSX-Redux). Everything after the opening
is still inference.

**The block.** RAM `0x801C0000` (above the arena's end under `arena.asm`'s raise, 250 KB under
the stack's low-water mark), read from filler sectors written Form 1 (milestone 1: LBA
1040–1042 by `build_prototype.py` alone; § 8: the reserve at LBA 1014, through the edit set).
Layout: `boku/movie_block.py`'s docstring. 6,000
bytes: 112 of header, cue rows and lines, then 92 records × 64 — the whole VWF glyph set,
each an advance byte and two 14×14 masks (§ 3's "18 bytes per glyph" was the 12×12 estimate;
the outline needs a pixel of margin, and 64 makes the index a shift). The loader is
`cd_load_sync`'s sequence for a fixed sector — `DsIntToPos`, `DsRead(loc, 3, dst, 0x80)`,
`DsReadSync` — bounded at eight attempts, after which it zeroes the magic; a block without
the magic (an image built with the hooks and no block, or filler) plays every movie
untouched. Cost at each movie's start: on Beetle the patched run's frame 5600 is the stock
run's 5575–5578, **22–25 frames (~0.4 s) later**; on Redux 11–12 vsyncs.

**The blit.** For the frame number the hook holds, every cue in range, every line, every
glyph whose 14 columns meet the slice's 16: rows `y − 1 …`, columns clipped to the slice,
white where the glyph bit is set, else the renderer's dark shadow (0x18, 0x18, 0x14) where
the outline bit is. `s0`–`s4` on the stack; `t`, `v`, `a` and `at` caller-saved, as
`LoadImage` treats them from the same site. **Which frame the number names**, measured on
Redux (`work/fmv04/patched-vwf-fmv04/dumps/k199.txt`): decoded frame k is header frame k + 1,
and while its slices upload the hook's number is k + 1 for the first 18 and k + 2 for the
last two — the next header arrives mid-frame — so a cue's first and last frames change on a
slice boundary, 1/15 s early; for frames 60 and 400 all twenty slices saw one number. The
gate predicts per slice from the number the hook recorded, so it is exact; a viewer cannot
see it.

**Measured.** Redux, `tools/redux/movie-sub.lua` on the stock and the built image
(`work/fmv04/stock/`, `work/fmv04/patched-vwf-fmv04/`, `redux.log` and `dumps/` in each):

* Decoded frame 199 from the built image equals the stock decode plus **exactly** the 3,255
  pixels `boku.movie_block.render` predicts, no more; frames 59 and 399 are byte-identical
  to stock (`test_real_movie_subtitle.py`; red on purpose with the six pixel stores made
  `nop`s: "3255 pixels differ … (62,200) want 181814", got the frame's own pixel).
* Polls between frames (§ 2.2's measure), STR frames 100–340: outside the cue, stock 11,618
  and built 11,575 on average; inside it, **stock 14,741 → built 6,351** (medians 17,761 →
  2,549) — the two-line blit uses most of the frame's idle — and **4 vsyncs per STR frame on
  every one of the 240 frames on both images**: no late frame.
* Cycles in `movie_sub_blit`, entry to its `LoadImage` (`work/fmv04/cycles.lua`,
  `PCSX.getCPUCycles`): outside the cue **~2,020 per frame** (20 × the magic-and-count exit,
  101 each); inside it **309,000 per frame** (the worst slice 21,950) — **9.1 ms of the 66.7
  ms frame** at 33.87 MHz for 79 glyphs on two lines, drawn per pixel with no row skipping
  beyond an empty mask row. If that ever shows as a late frame, the first savings are a
  per-glyph ink row range in the record and a per-row skip of clipped-empty masks.
* Beetle (`tools/libretro/run_core.py`, START 3300, CIRCLE 3600, no skip):
  `work/fmv04/beetle/frame-05600.png` shows both lines over the valley; it equals
  `work/fmv04/beetle-stock-fine/frame-05575.png` outside the text, and all 3,255 text pixels
  are exactly white or (0x18,0x18,0x14). The block and the island are in its RAM
  (`work/fmv04/beetle2/mid.state`, `movie_sub_frame_no` = 382 at frame 6000).

**What contact with the code changed in § 3.** The masks are 14×14 and 6 KB, not 18 bytes
and 4 KB; the code fills one island exactly, so E1's "few hundred bytes × 3" was right and
there is no room in it for the per-movie selection; a line header must be halfword-aligned
(the first build stalled at frame 120 on an odd `lhu`); and the frame number is per slice,
not per frame. The block's home (relocation arena, read at `movie_play_entry`) is as § 3
said, at a fixed sector for now.

## 8. Keyed by movie, carried by `boku build` (`FMV-04` milestone 2, 2026-09-22)

What changed from § 7: the cues come from a committed file, the block keys them by movie,
the loader picks the playing movie's out of it, and the block and the hooks travel in the
edit set, so `./make.sh build-days` carries movie subtitles. Code: `boku/movie_cues.py`
(the file's one parser and its rules), `boku/movie_block.py` (the block, `select` and
`render` as the loader's and blit's reference model), `asm/movie.asm`,
`tools/vwf/build_prototype.py` (`movie_block_for`, `movie_sector_edit`), `boku/build.py`
(`EditSet.sectors`), `boku/relocate.py` (`MOVIE_BLOCK_RESERVE`); the gate is
`tests/test_real_movie_subtitle.py`.

**The cue file** is `translation/movies.txt`, one row `movie <TAB> first <TAB> last <TAB>
English`; its format is `translation/README.md` § "movies.txt" and nowhere else. The key is
the movie *file* (`M27`), not the `MOVIE` id: `g_movie_table`'s entries that play one file
share one name string (§ 1: ids 0, 15 and 23 all point at `0x8002A32C`), and all play it
from frame 1, the first two stopping at 58, so a cue shows under whichever reaches its
frames. A cue's last frame may be at most the largest
`stop_frame` of the file's ids in `data/movies.tsv`. `boku lint` checks every rule in the
cell map the build installs (never the stock 14-px cells — no movie draws those), and the
font build refuses a file the lint would fail.

**The per-movie select.** `movie_play_entry` stores the entry's name pointer to
`g_movie_name` `0x80036680` (`0x800345EC`) before the hooked pair at `0x8003462C`, so the
loader needs no id: after the read it scans the block's movie rows for `g_movie_name`
and copies the matching row's cue offset and count into the block's header
(`boku/movie_block.py`'s docstring has the layout); no row leaves the count 0. `movie_sub_blit` reads its
cue list from +8 instead of +8's old fixed start — one instruction more. The block is
re-read and re-selected at every movie, so a previous movie's selection never survives
into the next. `movie_sub_frame_no` does still hold the previous movie's last frame when the
next one starts, and by § 2.2's call order is never read that way: `movie_run`'s priming
`movie_next_frame` stores the new movie's first frame number before the first slice is
uploaded (inferred from the order, not measured at the first frame). The name pointers are
read out of the contributor's own executable at build time
(`boku.movie_block.movie_names`), never typed.

**The second island.** The loader and the select moved to `dbg_font_init` `0x800221CC…
0x80022494` (712 bytes; `text-renderer.md` § 6: never called — no `jal`, data word or `lui`
pair names it; its bounds re-read: it opens `addiu sp,sp,-0xD0` and ends `jr ra` / `addiu
sp,sp,0xD0` at `0x8002248C`, the debug printer starting at `0x80022494`). They take 228
bytes of it. **Measured dead on one path**, as § 7's island was: an execution breakpoint
over all 712 bytes logged **0 hits** from boot through the title, the card check and the
opening to STR frame 400 on the stock disc (`work/fmv04/island2-stock.log`,
`BOKU_ISLAND_RANGE=800221CC,2C8`). After the opening it is inference, like the first.

**The carrier: reserved sectors.** The block cannot be a `BOKU.BIN` member without a new
`g_cd_dir` entry, and the executable needs a fixed LBA it was assembled against, so the
block lives in the top 32 sectors of the relocation arena, **LBA 1014–1045**
(`MOVIE_BLOCK_RESERVE`, 64 KB), and the allocator's arena stops below it (`DEFAULT_ARENA` =
LBA 281–1013, 733 sectors; `relocation.md` § Where the room is). The font build writes the
block into `edits.json` as its one `sectors` entry — `{lba, new, reason}`, whole sectors —
and `boku build --vwf` applies it beside the relocations as a `SectorEdit` over filler,
refusing any sector write outside the reserve and any LBA written twice. The hooks and both
islands are now ordinary words of the exported executable; the `MOVIE_SUBTITLES=0` pass is
gone. `encode_block` refuses a block larger than the reserve. The days build of 2026-09-22
relocates 60 members and leaves 479 of the 733 sectors; with no cues yet the block is 3
sectors, the header and the 92 glyph records.

**Measured.** Redux (`./make.sh emu-test`, the fixture cues on `M27` and `M60`, both over
frames 120–300, built through `build_prototype.py --edits-only` and `boku build --vwf`;
`M60` played in the opening's place by rewriting the table entry `movie_play_entry` is
handed, `movie-sub.lua` `BOKU_PLAY_NAME`): on both movies the frame inside the cue is the
stock decode plus exactly that movie's predicted text (3,409 and 2,116 pixels), the frames
outside are byte-identical to stock, and the hook's frame number is the player's. Red on
purpose with the select's `bne` made a `nop` (every movie takes the first row, `M60`'s):
"633 of M60's pixels are drawn over M27" and "3163 pixels of M27 k199 differ". Beetle
(`work/fmv04/beetle-m2/`, a state at frame 3000 with the same table entry poked by
`tools/vwf/state_poke.py --word`, then START/CIRCLE and a shot every 5 frames): every
patched shot that matches a stock shot outside the text rows and differs inside them — 84
on `M27`, 83 on `M60` — is that stock shot plus exactly its own movie's text, with none of
the other's; the patched run is 25 frames behind the stock one, the block's read (§ 7 says
22–25).

**Observed, not chased:** two of eleven headless Redux boots that night never reached the
opening by vsync 6000 (`strframes=0`), one on the stock image and one on a patched one, and
the same command passed on a rerun. Other lanes were running Redux at the same time.
*Hypothesis*, unchecked: the runs share Redux's memory cards (`run_core.py` keeps Beetle's
per work directory; where Redux keeps its own was not looked at), and the card check read
another run's save.
