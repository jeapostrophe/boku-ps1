# Related projects — what the four Boku repos know (research agent report, 2026-09-19)

> Raw sub-agent report, lightly framed. **[SRC]** = read in source, **[WEB]** = web fetch, **[INF]** = inference.
> Scratchpad paths in it are session-local and gone; re-clone the repos to follow a citation.

All four repos cloned and read, plus three bonus repos I found along the way. Web research was done by a sub-agent (its search budget hit 200/200, so a few sources stayed unreachable — flagged below).

**Clones lived at** `<session scratchpad>/repos/` (`esp`, `hilltop`, `pleonex`, `pleonex-wiki`, `psyou`, plus `hts`, `minimoni`, `timvisor`). Extracted Weblate PO corpus at `.../scratchpad/po/`.

Throughout: **[SRC]** = I read the source/file myself. **[WEB]** = from the web sub-agent's fetches. **[INF]** = my inference.

---

# 1. `pleonex/Boku-no-Natsuyasumi` — PSP port tooling

## Identity
- **Target**: Boku no Natsuyasumi Portable (PSP, UCJS10038). Tool named **Bokuract**. [SRC]
- **Language/licence**: C# / Mono, `TargetFrameworkVersion v4.5`, **GPL-3.0**. Wiki separately **CC-BY 4.0** (`pleonex-wiki/_Footer.md`). [SRC]
- **History**: 43 commits, 2014-12-14 → **2015-08-15**. Dormant 11 years; **archived 2025-09-05** [WEB]. Mirror exists at `Darkmet98/Boku-no-Natsuyasumi` [WEB].
- **Maturity**: **extraction only**. Every `Write`, `Import`, `Export` in `Packs/Pack.cs`, `Packs/GZip.cs`, `Packs/CdIndex.cs`, `Packs/CdData.cs`, `Scripts/Script.cs` is `throw new NotImplementedException()`. There is no reinsertion path at all. [SRC]
- **Build friction**: depends on `libgame` as a git submodule (`.gitmodules` → `pleonex/libgame`) which is **not vendored** (`Bokuract/libgame/` is empty), plus `Mono.Addins 1.2` and a checked-in `Ionic.Zlib.dll`. `extract.sh` is just `mono Bokuract/Bokuract/bin/Debug/Bokuract.exe data/`. [SRC]
- **The wiki is the valuable artifact, not the code.**

## Formats documented

**`cdimg0.img` + `cdimg.idx`** (master archive) — `pleonex-wiki/Pack-file-cdimg.md` + `Packs/CdIndex.cs::Read`/`ReadEntry`: [SRC]
```
cdimg.idx header:  0x00 magic "DFI\0"   (CdIndex.Type == "DFI")
                   0x04 u32 unknown (probably file count)
                   0x08 8 bytes padding
FAT entry (0x10):  0x00 u16 type        0 = file, 1 = folder
                   0x02 u16 flag        files: 0 = last file, else 1
                                        folders: number of entries
                   0x04 u32 name offset RELATIVE to this entry's offset
                   0x08 u32 offset      × 0x800  (CdIndex.Padding)
                   0x0C u32 size        absolute byte size
Name table:        null-terminated strings
```
Wiki says subfiles inside `cdimg0.img` are padded to `0x8000`; the code multiplies offsets by `0x800`. Note the discrepancy. `CdData.GiveFormat` rebuilds the tree by recursing `entry.SubEntries - 1` times per folder. [SRC]

**Generic "Pack"** — `pleonex-wiki/Pack-files.md` + `Packs/Pack.cs::Read(withNames)`: [SRC]
```
0x00  Int32   file count
0x04  entries  8 bytes {u32 offset, u32 size}  — unnamed variant
              12 bytes {u32 offset, u32 size, u32 nameOffset} — named variant
 x    null-terminated names (named variant only)
 x    file data
```
Entries with `offset == 0 || size == 0` are skipped. Unnamed files are synthesised as `<parent>_<i>.dat`.

**Which files are packs** — `Packs/PackValidation.cs`, arrays `SupportedFilesWithSubName` / `SupportedFilesNoSubName`. This doubles as a **PSP disc file listing**: [SRC]
- *Named*: `startup.bin`, `full_pack.bin`, `all_tex.bin`, `jumbo.bin`, `*.mrg`, `saveload.bin`, `day.bin`, `*.pack`, `*.pack_`, `model_pack.bin`, `map/models/day*/day*.bin`, `*.mpk`, `map/models/se/smap.bin`, `map/models/test.pack/test.mdl`, `map/models/system/saveload_*.bin`
- *Unnamed*: `font.bin`, `map/models/animlist.bin`, `map/models/title/title.bin`, `map/models/title/memory.bin`, `models/title/config.bin.gzx`
- Commented-out (superseded by `ScriptValidation`): `*/cdimg0.img/map/gz`, `map/gz/*/M_*.bin` — **note the `M_*` map-file naming, same as PS2.**

**Compression** — `pleonex-wiki/GZip-compression.md` + `Packs/GZip.cs`: `.gz` = plain gzip; `.gzx` = `u32 decompressed size` then plain gzip. `GZipValidation.TestByData` sniffs `u16 @ 0x04 == 0x8b1f`. [SRC]

**Script text** — `pleonex-wiki/Script-text-files.md` + `Scripts/Script.cs::ReadScript`/`ParseScript`: [SRC]

Path: `cdimg0.img/map/gz/<named pack>` → each member is gzip → decompressed is an **unnamed pack** → **`Files[1]`, the *second* file, is the dialogue blob.**
```
0x00  u32   block count
0x04  BlockInfo[8]: u16 id, u16 length, u32 offset
 x    Block: u32 (element count × 2)
            ElementInfo[8]: u32 → null-terminated name, u32 → data
            (offsets relative to block start)
```
`ParseScript` **skips the first 3 elements** and then walks `i += 2` (name, data pairs).

**Text encoding — the single most important finding.** Not Shift-JIS. 16-bit LE **glyph indices**: [SRC] (`Script.Dialog.ParseText`)
```
0x0000            null terminator
0x0001 … 0x0400   glyph index into font/table.txt
0x8000            end of dialogue
0x8001            newline
0x8002            wait; next u16 is the duration
0xFFFF            (also terminates, per Script.ParseScript's while loop)
```

**Table** — `font/table.txt`, 1047 lines of `NNNN = <char>`; loaded into `char[1024]` by `Scripts/Table.cs` (embedded resource `Bokuract.Scripts.table.txt`). Generated by `font/tablegenerator.py` from an explicit list of **Shift-JIS ranges**: `0x8140+11, 0x8151, 0x8158, 0x815B+2, … 0x824F+10 (digits), 0x8260+26 (A-Z), 0x8281+26 (a-z), 0x829F+79 (hiragana), 0x8340+63 & 0x8380+16 & 0x8392+5 (katakana)`, then a hand-filled kanji block from index 279 up. So **the glyph order is Shift-JIS collation order**, which is why it looks Shift-JIS-adjacent but isn't. [SRC]

**Font** — `pleonex-wiki/Font-&-Table.md`: two sheets **merged as PIM2 inside `startup.bin`**. `font/font1.png` is 512×512 4bpp. Given `char[1024]`, that's **32×32 grid of 16×16 glyphs = 1024 per sheet** [INF — the wiki doesn't state cell size; I read the PNG and counted]. The wiki's second font image URL points at `GriffithVIII/Boku-no-Natsuyasumi` which now **404s** (I verified with curl).

**Images** — `Docs/readimage.asm`, a Spanish-annotated MIPS disassembly of the PSP loader at `0x08837E5C`: `memcmp`s `"PIM2"` (string at `0x0890B970`), falls through to `"TIM2"` (`0x0890B978`). Header fields it decodes: `+0x05` byte (0 → data at `+0x10`, else `+0x80`), `+0x06` u16 version, then in the picture header `+0x0C` u16 image-data offset, `+0x14` u16 width, `+0x16` u16 height, `+0x08` u32 data size, `+0x12` byte `&0x3F` (pixel format), `+0x18` u32 `>>0x14 &0x3F`, `+0x1C` u32 `>>0x13 &0xF`. Also handles a sub-format whose first three bytes are `0x42 0x55 0x56` = **`"BUV"`** — the same `.buv` UV-table files Hilltop handles on PS2 (`TIM2.readBUV`, `IMG_BUV_SPECIALS`). `Docs/cmpbytes.asm` annotates the byte-compare helper. [SRC]

## Pipeline
`Bokuract.exe <folder>` → walks `cdimg0.img`, auto-detects formats via the `FormatValidation` classes, writes everything out; scripts export as **XML** (`Program.ExtractFolder`: `subfile.Format.Export(filepath + ".xml")`, elements `<Script Name>/<Dialog DialogID>/<Text>`). **No reinsert, no rebuild.** [SRC]

---

# 2. `HilltopWorks/BokuNoNatsuyasumi2` — PS2 sequel, English (the richest repo)

## Identity
- **Target**: Boku no Natsuyasumi 2 (PS2), executable `SCPS_150.26` = serial **SCPS-15026**. Confirmed by the shipped Ghidra project: `boku.rep/idata/00/00000000.prp` has `<STATE NAME="NAME" ... VALUE="SCPS_150.26"/>`. [SRC]
- **Licence**: **none** (no LICENSE file; README is one line, the repo name). All-rights-reserved by default — **ask before reusing code**. [SRC]
- **History**: 64 commits, 2023-01-08 → **2023-11-11**. Patch released **2023-11-01** via Patreon [WEB]. Complete and shipped.
- **Contents**: Python toolchain, a 1837-line armips file with **447 `.org` patch sites**, the full Weblate PO corpus (24 MB `boku.rep.zip` is a Ghidra project; 11.5 MB `boku-no-natsuyasumi-2.zip` is the translations), edited PNG/PSD graphics, and a `.pnach` for PCSX2.

## Disc / container formats

**`boku2.idx` + `boku2.img`** — `UNPACK.py::getIDX`, `getFileNames`: [SRC]
```
DIR_START = 0x10, DIR_END = 0x8140, IDX_ENTRY_SIZE = 0x10
entry: u16 is_dir, u16 dir_info, u32 filename_offset, u32 sector_offset (×0x800), u32 filesize
FILENAMES_START = 0x8140, null-terminated names, in entry order
```
**This is the same layout as the PSP's `cdimg.idx`** — same 0x10 entry, same field order, same `×0x800`. Only the `DFI\0` magic differs (Hilltop doesn't check one). `packIMG` rewrites offset/size in place at `x*0x10 + 0x18` and pads each file to `0x800`.

**`boku2.crc` — anti-tamper.** `UNPACK.py::getCRCdict`, `crc16`, `crcFile`, `setCRC`, `updateCRCs`: [SRC]
```
header: u32 n_entries, u32 dir_start, u32 dir_size, u32 crc_data_offset, u32 crc_data_size
dir entry (0x20): u16, u16 entry_number, u16 type, u16 entry_number_2, then name string
crc array: u16 per entry
```
The CRC is **CRC-16/CCITT-FALSE** (`init 0xFFFF`, `poly 0x1021`) over **only the first 0x80 bytes** of each file. Hilltop both recomputes them *and* NOPs the check in the ELF (`scps_150.26.asm`, `; Removing the CRC Check` → `.org 0x1bff98`), then **reuses the freed CRC region as scratch space** to host `font_kerning.bin` and the sumo subtitle blob. [SRC] He describes this as an anti-tamper mechanism that crashes the game if you edit anything [WEB, video transcript].

**`map/*.bin` map packs** — `UNPACK.py::unpackMap`: [SRC]
```
u32 header_ID (usually 0xE)   ← almost certainly the entry count
u32 header_length (usually 0x80)  ← first data offset
entries from +4: {u32 offset, u32 size}   (type 1, 8 bytes)
                 or 0xC bytes             (type 0)
offset == 0 → null entry
```
Extracted as `0.bin`, `1.bin`, …; repack pads components to 0x10. **`1.bin` is always the MSG/event file**; `0.bin` and `6.bin` hold graphics coordinates (patched by `map.asm`).

**MSG format** — `MSG_notes.txt` + `MSG.py::unpackMapMSG`, `readMSG`, `repackMsg`, `splitMsg`: [SRC]
```
MAP_MODE (map/*/1.bin):
  u32 numTables
  table entry (0xC): u32 magic1, u16 tableSize, u16 magic2, u32 tableOffset
  table: u32 n_entries; n_entries × u32 offset (relative to table start); 0 = null
MSG_MODE (standalone *.msg): u32 n_entries; n_entries × {u32 offset, u32 size}
OFFSET_ONLY_MODE (on_mem_event children): u32 n_entries; n_entries × u32 offset
```

**Text encoding — identical control codes to the PSP.** `MSG.py::convertRawToText` / `convertTextToRaw`: [SRC]
```
u16 LE glyph index into font.txt (1058 entries)
0x8000  {STOP}/END
0x8001  newline
0x8002  {WAIT=xxxx} + u16 param   — or a hard {BREAK} in "alt mode"
0xCDCD  padding, appended when a line's byte length % 4 == 2
```
`ALT_NEWLINE_FILES` (`turi_info.msg`, `phot_info.msg`, `okan_info.msg`, `item_info.msg`, `insect_menu.msg`, `fishing.msg`, `fish_info.msg`) reinterpret `0x8002` as a break. `SJIS_FILES = ["system\\~saveload\\2.bin"]` — exactly **one** file is real Shift-JIS.

**Event-script bytecode** — `voice.py::EVENT_LABELS`, `readEvent`, `readEventList`: [SRC]
```
event: u8 opcode, u8 size/2, body
48 opcodes: POS INI IPROG JMP JMPM JMPE PROG GO WALK RUN MAP CMAP CMAPP CMWT
            BGM SE XAMSG MSG XA FLAG DISP ANM BGANM LOOK END AWT BWT XWT DIXA
            WIN WAT MWT TIME IF DEBUG FACE SELECT MOVIE LFLAG WARP MSGWT YGO
            XSEEK CMPOS SWIM FOOT SHADOW CMINI
HAS_TEXT  = XAMSG, MSG, SELECT
HAS_VOICE = XA, XAMSG
```
`readEventList` takes the first 2 table entries as init blocks, entry index 2 as the **event code start**, and entries from index 3 onward as messages. **This mirrors pleonex's "the first 3 element entries don't contain text data" on PSP exactly.** Dumps in `MAP_SCRIPTS/*.txt` (32 files, e.g. `M_A11000.txt`) show the disassembly interleaved with the dialogue.

Voice IDs live in `IMG_RIP/SE/VOICE.xwh` at offset `0x1FE20`, `0xFEF` null-terminated ASCII names (`voice.py::getVoiceList`). [SRC]

## Fonts and VWF

- Sheet: `bk_font.tms` → `GFX/bk_font.tms_0x80_0-B copy.png`, **512×1024**, cells **22×22**, **23 columns × 46 rows = 1058 glyphs**. Confirmed three ways: `reprint.py` (`N_COLUMNS = 23`, `CELL_WIDTH = 22`), `FontRecognizer.java::main` (`decode("src/font1.png", 22,22, 46, 23, WHITE_ON_BLACK)`), and `font_kerning.bin` being **exactly 1058 bytes** — one width byte per glyph. [SRC]
- **`FontRecognizer.java`** OCRs the ripped sheet cell-by-cell with **KanjiTomo** to auto-build the character table. Reusable trick. [SRC]
- Tables: `font.txt` (extraction), `font-inject.txt` (insertion — Latin/accented chars overwriting kana/kanji cells), `font-inject-menus.txt`, `font-inject-simon.txt` (a distinct typeface for one character's dialogue), plus `-print.txt` variants. `reprint.py::FONTS` renders the sheet from TTFs with PIL: `IwataMaruGothicW55-D.ttf` (base, 19pt), `Gen Jyuu Gothic Monospace Bold.ttf` (menus, 18pt, forced monospace 10), `OldStandardTT-Regular.ttf` (Simon, 22pt). `printFont` writes each glyph's measured bounding-box width straight into `font_kerning.bin`. [SRC]
- **`textCompaction.py` — MTE taken to its limit.** Mines the translated POs for repeated substrings (length 2–16), scores each `frequency × (len−1) × 2` bytes saved, **renders the winning phrase as a multi-cell image into rows 15–45 of the sheet**, replaces occurrences with the single sentinel glyph `扉`, encodes it as one u16 (`val = column + row*23`), and writes the whole phrase's pixel width into the kerning table (`assert string_width < 256`). The dictionary entry is literally a picture of the phrase. [SRC]

## ASM hacks — `scps_150.26.asm` (armips, `.ps2`, `.erroronwarning on`) [SRC]

Two `.open` blocks: `ISO_EDITS\boku2.crc` at `0x6fc7b0` (imports `font_kerning.bin` at `+0x16374` and `VOICE\sumo_msg.bin`) and `ISO_EDITS\scps_150.26` at `0xFF000`.

- **VWF for main dialogue**: the glyph-draw routine `0x001fdeac–0x1fdf54` is replaced by a jump into free debug space at `text_loop_space = 0x00290538`; `vwf_table = 0x0712b24`, `func_vwf = 0x028eb34`. The width lookup is `lbu v1, vwf_table[char]` then `sll v1, v1, 0x4` — **1 pixel = 0x10 in GS subpixel units**. Advance patched at `set_kerning = 0x1fdf58` → `addu s4, s4, v1` (was a constant). Constants: `text_padding 2`, `font_spacing 0xD`, `base_x 0x330`, `base_y 0xAA`, drop shadow at `(0x20, 0x10)` drawn as a second quad (`gpu_call += 0x50` instead of `0x28`).
- **Vertical → horizontal text.** `asm_notes.txt` preserves the original routine beside the hack: original computes `subu s2, a2, v0 ; s2 = base_x - (newlines*spacing)` — i.e. **columns advancing leftwards**, classic Japanese vertical layout — and the hack changes it to `addu s2, a2, v0 ; s2 = base_y + (newlines*spacing)`. Dozens of menus were converted individually (`;Keep/Release options vert->hori`, `;Hikari Yes/No verti->hori`, `; Hori text kerning updates`, `.org 0x0015a4bc ;Vertical text newline distance`). **This is the single biggest engineering cost in the project.**
- Menu font forced monospace at `mfw equ 0xa`; glyph texel size changed 23→22 at `0x018077c`/`0x0180794`/`0x01807d0`/`0x01807e4` (each marked `EMULATOR PATCH THIS`).
- **Sumo subtitles**: a new `voice_and_sub` routine hooked in at `.org 0x001CF15C` (`jal voice_and_sub` over the original `jal sumo_voice`); it decodes BCD-ish digits out of `current_sumo_voice_id` (`0x0354c68`) into `text_file_idx = group*17 + entry`, sets yellow via `set_color = 0x0015a2d0`, and calls `print = 0x0015a3f8` at `(0x110, 0x4E)`.
- `CRC_HERE.pnach` — PCSX2 patch re-fixing the same texel constants for upscaled rendering (`gametitle=Boku no Natsuyasumi 2 English Patch`, "DO NOT USE IF NOT UPSCALING").
- `map.asm` — a second armips file patching graphics coords/dimensions inside `MAP_RIP_EDITS\M_D09000\{0,6}.bin` and `M_D09100`.

## Images
- **TIM2**, located by raw magic scan for `"TIM2"` (`TIM2.py::findTIM2s`). `.tm2`/`.tms`; `PALETTE_START 0xa0`, `GRAPHIC_START 0x500`, `TEX_SIZE 0x8800`. Some textures pair with `.buv` UV tables (`readBUV`, `IMG_BUV_SPECIALS` hard-codes offsets inside `root.bin` and `fish_on_mem.bin`). A `.arn` extension appears (`phot_20.tm2.arn`) — compressed [INF]. [SRC]
- **`resource.py` is a full PS1 TIM library** — its header comment literally reads `#Contains a number of resources for using PS1 image files`, with `TIM_ID = 0x10`, classes `TIM`/`CLUT`/`PXL`, RGB555 pack/unpack, `PNG_to_TIM`, `injectPNG` (diff-based, maps changed pixels to existing CLUT entries). **Directly reusable for the PS1 game.** [SRC]

## Pipeline — `EXEC.py::build` [SRC]
```
pullScript()          git fetch/reset the Weblate translation repos
reprint.printAllCalendars / printAllBottleCaps / printAllBugInfo / printSumo
compaction_map = reprint.printAllFonts()      ← renders glyph sheet + kerning
TIM2.injectAll()                              ← PNG → TIM2
injectMAPs(compaction_map) / injectIMGs(...)  ← PO → binary MSG
insertAllAdditions()                          ← ADDS/*.bin blobs at fixed offsets
armips.exe map.asm
voice.applyEventScripts()
UNPACK.packMaps("MAP_RIP_EDITS","ISO_EDITS\map")
UNPACK.packIMG("IMG_RIP_EDITS","ISO_EDITS")
voice.genSumoVoiceBin()
armips.exe scps_150.26.asm
ultraiso.exe -in <iso> -d ISO_EDITS           ← file replacement, not a rebuild
```
**Intermediate format: gettext `.po`, hosted on Weblate** (`translations.yuvi.app/projects/boku-no-natsuyasumi/...`), read/written with `polib`. Comments carry the address: `#. Table:0-Line:4`. [SRC]

## Text volume (I extracted and counted the PO corpus) [SRC]
- **641 `.po` files**: **601 map scripts** (`M_A01000` … `M_Z…`, prefixes A0–A3, B0–B4, C0–C1, D0–D1, E0–E1, F0–F1, G0, I0–I1, Z0) + **24 IMG `.msg`** + diary/on_mem_event/saveload.
- **17,002 entries, ~540,000 Japanese characters**, 14,259 translated (**83.9%**) in the committed snapshot.

## Gotchas explicitly encoded in the tools [SRC]
- `false_positives` — ~130 hand-listed garbage strings the naive scanner produces from non-text blocks. Scanning for text *will* produce noise.
- `BUGGED_LINES` — 6 lines the game mis-renders, fixed by substitution.
- `MENU_TEXT_EXCEPTIONS` — shop/quiz menus embedded in *map* scripts that must be encoded with the **menu** font table, not the dialogue one. Prices, item names, the whole beetle-advice list.
- `\xCD\xCD` padding when a line's byte length ≡ 2 (mod 4).
- `fixFishOnMem()` — `fishing.msg` is **duplicated** into a preloaded blob `fish/img/fish_on_mem.bin` at `0x438d0`, with its size at `0x90`. Assets get copied per-scene to avoid seeks; you must patch every copy.
- `ADDS/*.bin` — hand-built binary blobs written at fixed offsets into `diary.bin` (`0x80`) and `system/saveload.bin` (`0x100`, `0x180`, `0x700`). Expansion by hand.
- **Diary pages are graphics, not text.** `GFX/diaries.txt` (1059 lines) is *rendered* onto diary page images by `reprint.printAllDiary`. Same for bug info (`bug_info.txt`), bottle caps (`bottle_caps.txt`, 25 dinosaur names), calendars.
- Insect names: `system/submenu/insect/insect_name.msg`; nicknames `nick_name_a.msg`/`nick_name_b.msg`; memos `memo_name.msg`.

---

# 3. `GriffithVIII/Boku-no-Natsuyasumi-ESP` — Spanish PSP patch

- **Target**: Boku no Natsuyasumi Portable (PSP, UCJS10038), **Spanish**, TraduSquare. **Apache-2.0**. 16 commits, 2025-07-26 → 2026-08-04. [SRC]
- **Contains no tools and no source.** I checked the whole history (`git log --all --pretty=format: --name-only`): README, LICENSE, 24 screenshots, a banner. Nothing else has ever been committed. [SRC]
- Release **v1.0, 2025-07-29** [WEB]; distributed as `bokuES-v1.0.xdelta` + a `Parcheador.exe` GUI applied to a Japanese ISO, output `*_ES.iso`. Only one version ever shipped. [SRC README, WEB]
- **Claimed feature set** (README, *Características* / *Mejoras*): 100% script, graphics, insect names, cutscene subs, minigames, save data; **widened menus**; **VWF**; and exe-level *additions*: subtitles on the TV, in beetle sumo, for Boku while catching bugs, in the endings and misc scenes; **redistributed bug-collection board**; **horizontally-oriented text boxes**. [SRC]
- Credits thank **Hilltop, Pleonex, obskyr, Megaflan, Leeg, Snake128, Ortew, Infrid**. The three scenes are connected. [SRC]
- **Technical devlog exists**: tradusquare.es, 2025-06-19, *"Mis primeras vacaciones de verano"* [WEB]. Two technical sections: **(1) vertical→horizontal** — found via PPSSPP's graphics debugger, the box position was tied to the text position; fix was **swapping the X-axis variable with the Y-axis variable**, given as MIPS `li v1,0x1D ;# Axis X` / `li v0,0x1F7 ;# Axis Y`. **(2) VWF** — glyphs were originally fixed 16px; his routine reads the glyph ID, **adds it to a width-table base** (worked example: table at `0x200`, `A = 0x10` → read `0x220`), and adds that to a running accumulator. Font redrawn by IlDucci. The devlog does **not** cover subtitles, file formats, ISO rebuilding or menu widening.
- Space for the new code came from his own **`GriffithVIII/PSP_ELFHandler`** — a CLI that expands a PSP ELF, target size must be a multiple of `0x800` [WEB].
- He also wrote **`GriffithVIII/TIMVisor`** — a **PS1 TIM** viewer/converter, C#/.NET 6, **GPL-3.0**, supports 4/8/16/24bpp with PNG↔TIM import/export. Not used on the PSP project but directly relevant to yours. [SRC — I cloned and read it]
- The 2021 TraduSquare announcement **explicitly rules out the PS1 version**: *"¿Se va a traducir la versión de PSX? La respuesta es **no**… todo nuestro trabajo solo funciona con esta versión."* [WEB]

---

# 4. `psyouloveme/boku1-reversing` — **the PS1 original** (but not translation)

- **Target: the PS1 original, SCPS-10088.** **No licence file.** 16 commits, 2023-08-28 → **2026-08-24 (actively maintained)**. Contributors psyouloveme + TheTedder. [SRC]
- **Purpose is speedrunning/RE, not localisation.** I grepped the whole repo — **zero** font, text, script, dialogue or Shift-JIS work. [SRC]

## `ghidra_scripts/boku.idx` — a jPSXdec v1.00 index of a real dump [SRC]
Header: `Sector size:2352 | Sector count:280170`. Totals: **29 File, 2607 Tim, 80 XA, 25 Video**.

**The complete PS1 disc file list** (this is the thing to diff your own dump against):
```
SCPS_100.88          sectors     23–278        524,288 B   (main EXE, 0x80000)
SYSTEM.CNF           sector     279                 68 B
    [gap: sectors 280–1045, 766 sectors unaccounted — padding/dummy]
BOKU.BIN             sectors   1046–54416  109,303,808 B   (≈104 MiB — the whole game)
__STR/BOKU_XA.XAM    sectors  54417–150869 197,535,744 B   Mode 2 Form 2
__STR/M010.IKI  M031 M032 M033 M034 M050 M080 M100 M110 M120 M130 M140 M160
      M180 M190 M21 M22 M230 M250 M260 M40 M60 M70 M27 M28   (24 .IKI, all Form 2)
      largest: M27.IKI 86,917,120 B (4244 frames), M28.IKI 85,995,520 B (4199 frames)
```
Every file's size is an exact multiple of 2048 and exactly `(end-start+1)×2048` — everything is sector-aligned. [SRC, I verified arithmetically]

Structural facts I derived from the index: [SRC]
- **`.IKI` are ordinary PSX STR video**, all 320×240, `Sectors/Frame:10/1`, disc speed 2×, 52–4244 frames.
- **`BOKU_XA.XAM` uses all 16 CD-XA channels**, mono, 37800 Hz, 4-bit ADPCM, sector stride 16 — jPSXdec split it into 55 streams.
- **2607 TIMs found by raw scan**, 2606 inside `BOKU.BIN` and **1 inside the EXE** (`SCPS_100.88[0]`, sector 73 offset 1104, 16×48, 1 palette, 4bpp). Dimension histogram, top entries: `483× 98×79 8bpp`, `323× 8×8 4bpp`, `189× 16×8 4bpp`, `173× 8×8 4bpp`, `94× 240×192 8bpp`, `86/85/52/45× 8×8 4bpp` (other palette counts), `80× 128×88 8bpp`, `63× 48×64 4bpp`, `45× 40×64 4bpp`, `40+30+20+11× 320×240 8bpp`, `21× 64×16 4bpp`, `18× 252×188 8bpp`, plus a few wide ones: `8× 720×240 8bpp`, `8× 472×256 8bpp`, `7× 586×256 8bpp`.
- **There is no `.idx` file on the PS1 disc.** Unlike PSP (`cdimg.idx`) and PS2 (`boku2.idx`), the directory for `BOKU.BIN` must be inside `BOKU.BIN` itself or in the EXE.

## Other contents [SRC]
- `ghidra_scripts/import_boku_jpsxdec.py` — parses a jPSXdec `.idx` (pipe-delimited: `#:i | ID | Sectors:s-e | Type | Start Offset | Dimensions WxH | Palettes | Bpp`), skips lines containing `Path:`, handles `Type:Tim` only, and creates Ghidra labels `<file_id>_TIM_<addr>`. `PSX_SECTOR_SIZE = 0x930`.
- `label_sectors.py` — labels raw 0x930 CD-XA sectors in Ghidra; `CDXA_MAGIC = "00 ff ff ff ff ff ff ff ff ff ff 00"`.
- `cdxa_sector_header.py`, `cdxa_constants.py`, `psx_data_types.py`, `psx_dt_constants.py` — Ghidra data types for CD-XA subheaders and for TIM (categories `/psy-q_reference/TIM`, `/xentax_reference`, `/jpsxdec_reference`): `x_TIMFileHeader`, `x_TIMFileCLUTHeader`, `TIMFilePixelDataHeader`, `CLUT4Bit`/`CLUT8Bit`, `FrameBufferPixelData4Bit`/`8Bit`.
- `bizhawk/scripts/boku_hud.lua` (46 KB) — **a de-facto MainRAM map**: `GameMode 0x237e0` (3=menu opening, 4=menu, 5=game, 7=sumo), `Day 0x028fb0`, `Hour 0x028FA1`, `Minute 0x028FA2`, `MapCurrent 0x26c00`, `MapNext 0x26c08`, `FrameCount 0x028850`, `Luck 0x3dd1d`, `StoryEvents 0x035f35`, `bugStructSize 0xc`, bug arrays `0x3db38/0x3dc28/0x3dd20/0x3de18/0x45a10/0x46f28`, on-screen bugs `0x02806c` with `struct_size 0x58`, sumo `0x3d278/0x3d279/0x8f028/0x8f098`, pause `0x0246b8`, **last CD position `0x025A40–0x025A42`** (useful for correlating RAM to disc sectors). Watch files `boku_bugs_and_stuff.wch` and `boku_sumo_record.wch` add more labelled addresses (`NextScreenPointer 0x026BD0`, `CurrentScreenPointer 0x026BE0`).

---

# 5. Bonus repos I found (not in your list, high value)

**`HilltopWorks/HilltopTranslationScripts`** — *"A collection of scripts for hacking PS1/PS2 games for localization"*, **no licence**, HEAD 2022-12-19. Six complete PS1 toolchains: **Aconcagua, Dr. Slump, Harmful Park, Maid & Machinegun, Racing Lagoon, b.l.u.e. Legend of Water**. This is the closest thing to a template for a PS1 project by the same author. [SRC]
- PS1 ASM is **armips `.psx`** (`Racing Lagoon/main.asm`: `.psx / .open "EXTRACT\SYSTEM.BIN\SYSTEM.BIN.0012", 0x8009c1d8`).
- ISO rebuild is **mkpsxiso with an XML** (`blue/build.py`: `subprocess.call(['mkpsxiso.exe','BLUE.xml'])`; `Harmful Park/build.py`: `MKPSXISO='mkpsxiso.exe'`, `XML="HarmfulParkBuild.xml"`; `Aconcagua/execute.py` builds both discs).
- Tables are `.tbl` (`sjis.tbl` for games that *do* use Shift-JIS, plus per-game `ExtractTable.tbl` / `InjectTable.tbl` pairs with control codes like `00={END}`, `0A={NEWLINE}`, `4031={CROSS}`).
- `dataDuplication.py` recurs in several projects — a **propagation tool** for assets duplicated per-scene.
- `Dr. Slump/lineBreak.py` — a standalone word-wrap helper that counts control symbols correctly.

**`HilltopWorks/MinimoniPS1`** (2026-01-02, no licence) — a **recent, small, complete PS1 pipeline**: [SRC]
- `MiniMoni.py::replaceFile` patches the `.bin` **in place at the sector level**: `DATA_START = 24`, `SECTOR_SIZE = 2352`, `DATA_SECTOR_SIZE = 0x800` — seek `(startSector + x)*2352 + 24`, write 2048 bytes. No ISO rebuild needed as long as the replacement fits. (Caveat: this does not recompute EDC/ECC. Fine on emulators; verify on hardware. [INF])
- `TIMresource.py` is the same PS1 TIM library as `hilltop/resource.py` plus STP (semi-transparency) modes.
- `ImageHill.py` — a broader image library (PXL/CLUT readers for 1/2/4/8/15/24/32-bit, BMP, TIM extract/inject, grid convert/inject for sprite sheets).

**`GriffithVIII/TIMVisor`** — GPL-3.0, C#/.NET 6, PS1 TIM ↔ PNG, 4/8/16/24bpp, with a README documenting the format. [SRC]

---

# 6. Hilltop's public methodology [WEB — sub-agent read the pages and pulled auto-transcripts]

Channel is just **"Hilltop"**: https://www.youtube.com/@hilltopworks. **There is no blog or website** (`hilltopworks.com` etc. have no DNS record). Patreon https://www.patreon.com/hilltopworks is the patch distribution channel. **There is no Boku 2 technical video** — the GitHub repo *is* the record.

**Game Hacking Playlist** — https://www.youtube.com/playlist?list=PLMnvGn69IU8AfGrhxcnvLEaDXRizQdHrJ
| Video | URL | Date |
|---|---|---|
| What it takes to fan-translate a video game (Dr. Slump) | https://www.youtube.com/watch?v=0tUxVSms4Q4 | 2022-12-04 |
| Racing Lagoon Hacking Deep Dive | https://www.youtube.com/watch?v=-WkW2jGP538 | 2023-03-10 |
| Conquering the mountain — how Aconcagua was translated | https://www.youtube.com/watch?v=Nwh-b6AUY5I | 2023-03-10 |
| **An exhaustive look at extracting graphics from PS1 and PS2 games** (95 min) | https://www.youtube.com/watch?v=lePKUCYakqM | 2023-06-06 |
| An introduction to hacking video games with Ghidra | https://www.youtube.com/watch?v=qCEZC3cPc1s | 2024-01-03 |
| **How to Romhack: Mega Man Legends 2** (60 min, his most comprehensive) | https://www.youtube.com/watch?v=S0RmHFpdf-Y | 2024-06-16 |
| How to translate a ROM (Cardcaptor Sakura/WonderSwan) | https://www.youtube.com/watch?v=XDg73E1n5-g | 2025-12-30 |
| Romhacking & Translation Live Panel — Vancouver Retro Game Expo | https://www.youtube.com/watch?v=rgyyvvCNJ1Y | 2026-07-04 |

Boku 2 release trailer: https://www.youtube.com/watch?v=z5uvUo1g_aw (2023-11-01). Interview: https://readonlymemo.com/hilltop-works-next-fan-translation-ps2-rpg/ (2023-11-19).

**Methodology distilled** (his stated pipeline, verbatim): *"identify all the text and graphics data… program an extractor… then an injector… make sure that we're updating all of the file directories the game is looking at… and rebuild the game disc."*

- **Disc triage**: eliminate `SYSTEM.CNF`, the `SLPS/SCPS_xxx.xx` EXE, `DUMMY.DAT`, `.XA`, `MOVIE/*.STR`; what's left is data. *"These files are bigger than two megabytes, 2 megabytes being the entire memory size of the PlayStation 1 — that tells us that these aren't individual files but entire directories."*
- **Finding the directory**: scan for `0x800` sector boundaries and search the EXE for that little-endian address; or spot the arithmetic — *"if we add up the first two numbers… it gives us a number very very close to the third — file location and data sizes, it's a directory."* **A set high bit in a pointer (`8B0C6000` vs `0B0C6000`) means compressed.**
- **Decompressors**: diff compressed-vs-decompressed in RAM, or set a read breakpoint on the compressed data / write breakpoint on the output buffer and disassemble. He's met LZSS, RLE and byte-pair. Critical: **the compressor is never in the ROM — you must write it yourself.**
- **Text location**: relative searching with **Monkey-Moore**, wildcards on for two-byte encodings, with the character order derived from the ripped font sheet. Racing Lagoon had ~3000 glyphs transcribed by hand.
- **VWF**: *"you might think… we change the cells being rendered… that doesn't solve the problem, because the game will print the glyph and then move forward 12 pixels. What we have to do is change the amount that the cursor is moving forward."* Method: load-breakpoint the text buffer to find the glyph printer, discover its advance, re-lay the sheet left-aligned, generate the width table in Python by bounding-boxing each cell, hijack a store to jump to injected asm.
- **LBA, not filenames**: *"It is specifying files based on their sector number… the PS1 is really just kind of like a fancy CD player."* The EXE holds **12-byte entries `{LBA, size, unknown}`**; because final LBAs aren't knowable in advance the build is **two-pass** (build → read LBAs → rewrite the EXE table → build again). One inserted dummy sector crashed MML2 on boot.
- **PS1 graphics facts worth writing down**: *"just by looking at a TIM it's actually impossible to know for certain how to correctly rip an image"* (STP blending is a runtime decision). **TIM's PXL `W` is in 16-bit VRAM units — multiply by 4 for 4bpp, 2 for 8bpp.** Palette heuristics: 2 bytes/colour, high bit usually set, 0x20 or 0x200 bytes total, *"palettes tend to start and end with pure white, pure black, or pure transparent — `FFFF`, `8000`, or `0000`"*. Re-insert by nearest-existing-entry (sum of squares over RGBA); **avoid modifying palettes, images share them.**
- **Toolchain, named**: Ghidra + PSX loader (*"xrefs — the most powerful and important feature"*; he re-analyses his own patched binary to verify his asm), **armips**, **no$psx** (read/write breakpoints + GPU debugger), **PCSX-Redux** (VRAM viewer), PCSX2 + pnach, **BizHawk RAM Search**, **Monkey-Moore**, **jPSXdec**, **mkpsxiso/dumpsxiso** (Lameguy64), UltraISO (PS2 only), **Delta Patcher/xdelta** to ship, Tile Molester / 010 Editor, Photoshop, Python (PIL/numpy/cv2/scipy/**polib**), Git + Weblate. Hardware: *"I just have a PS1 with an ODE, with an XStation, for testing. I don't have a dev kit. You typically don't need one."*
- Starting-point document he credits every time: **slowbeef's Policenauts technicals**, https://lparchive.org/Policenauts/Update%2050/

---

# 7. Synthesis

## (a) What most likely transfers to the PS1 original

**Tier 1 — bet on these.**
1. **The 16-bit glyph-index text stream with `0x8000`/`0x8001`/`0x8002` control codes.** Identical in the PSP port of Boku 1 (pleonex, `Script.ParseText`) and in the PS2 sequel (Hilltop, `MSG.convertRawToText`) — two different platforms, five years apart, two independent reverse-engineers. The PSP release is a *port of the PS1 game*; the odds that this encoding originated on PS1 and was carried forward are very high. **Text is not Shift-JIS.**
2. **The MSG container shape**: `u32 count` + offset table + data, `0` = null entry, offsets relative to table start. Present in both. On PS2 it's `map/<name>/1.bin`; on PSP it's `Files[1]` of the inner pack. **The "second element/file is the text" convention appears in both.**
3. **"First three table entries are not text"** — pleonex's wiki and Hilltop's `voice.py::readEventList` independently say the same thing. Expect entry 0/1 = init blocks, entry 2 = event bytecode, entries 3+ = messages.
4. **An event bytecode alongside the text, per map**, with opcodes like `MSG`, `XAMSG`, `SELECT`, `MAP`, `CMAP`, `WAT`, `ANM`, `END` (PS2 list in §2). On PS1 this is what would drive `BOKU_XA.XAM` playback — the `XAMSG`/`XA` opcodes exist precisely for XA-voiced dialogue, and the PS1 disc is *dominated* by XA.
5. **Simple packs**: `u32 count` + 8-byte `{offset,size}` entries. PSP's `Pack.cs` and PS2's `unpackMap` are the same idea; `BOKU.BIN` almost certainly opens with one.
6. **Map naming `M_<letter><digits>`** — used on PS2 (601 files, `M_A01000`…`M_Z…`) and referenced in pleonex's commented-out PSP rule (`map/gz/*/M_*.bin`).

**Tier 2 — plausible, verify.**
7. The **`0x10`-byte directory entry** `{u16 is_dir, u16 dir_info, u32 nameOff, u32 sectorOff×0x800, u32 size}` — byte-identical between PSP `cdimg.idx` and PS2 `boku2.idx`. But **the PS1 disc has no `.idx` file**, so if this format is there it lives at the head of `BOKU.BIN` or in the EXE. Look for `DFI\0` or a bare count.
8. **Glyph table ordering.** Both PSP `table.txt` and PS2 `font.txt` start with the same Shift-JIS-collation punctuation run, then `0-9 A-Z a-z`, then hiragana, katakana, kanji. They diverge in detail (PSP index 2 = `。`, PS2 index 2 = `゜`; PSP 13/17 = `ー`/`｜`, PS2 13/17 = `|`/`―`) — so **the order is a family resemblance, not a fixed table.** `pleonex/font/tablegenerator.py` gives you a ready-made Shift-JIS-range generator to bootstrap a guess.
9. **Vertical text.** PS2 dialogue was drawn vertically (original `base_x - newlines*spacing`) and the PSP version needed the same fix independently. **Expect the PS1 original to render dialogue top-to-bottom, right-to-left.** Budget for this as the single largest ASM task.
10. **CRC anti-tamper.** PS2 has `boku2.crc` + an in-EXE check. Whether Millennium Kitchen did this in 2000 is unknown — but if `BOKU.BIN` has a table of 16-bit values near its head, check CRC-16/CCITT over the first 0x80 bytes before assuming it's something else.

**Tier 3 — do NOT assume.**
11. **Compression.** PSP uses stock **gzip** (`.gz`/`.gzx`) — that's a *PSP-era* choice; a 2000 PS1 game would not link zlib. PS2 map packs read as raw. Expect either no compression or a custom LZSS/RLE on PS1. Hilltop's high-bit-in-pointer tell is the thing to look for.
12. **Image format**: PS1 is **TIM** (`0x00000010` magic), not TIM2/PIM2/GIM. jPSXdec already proved 2606 TIMs sit uncompressed inside `BOKU.BIN`.
13. **Font cell geometry**: PS2 22×22 / 23 cols; PSP 16×16 / 32 cols. PS1 will be its own thing — likely 4bpp, 12×12 or 16×16, in a TIM.

## (b) Tools you can reuse or port

| Tool | Path / repo | Language | Licence | Verdict |
|---|---|---|---|---|
| `resource.py` (PS1 TIM read/write, CLUT, PNG↔TIM inject) | `hilltop/resource.py` | Py3 + PIL/numpy | **none** | **Best single reuse.** Ask permission. |
| `TIMresource.py` + `ImageHill.py` (same, newer, + STP modes, grid sheets) | `minimoni/` | Py3 | **none** | Newer than the above; same author. |
| `MSG.py` text codec (`readFont`, `convertRawToText`, `convertTextToRaw`) | `hilltop/MSG.py` | Py3 + polib | **none** | Port the control-code logic verbatim; re-derive offsets. |
| `textCompaction.py` (multi-char glyph MTE) | `hilltop/textCompaction.py` | Py3 | **none** | Only if PS1 tables are size-locked. |
| `FontRecognizer.java` (KanjiTomo OCR of a glyph sheet → table) | `hilltop/FontRecognizer.java` | Java + KanjiTomo | **none** | **Do this early** — it's how you get a PS1 table without transcribing 1000+ kanji. |
| Six complete PS1 pipelines (armips + mkpsxiso + tbl) | `HilltopWorks/HilltopTranslationScripts` | Py3 + armips | **none** | Structural template. |
| PS1 in-place sector patching | `minimoni/MiniMoni.py::replaceFile` | Py3 | **none** | Avoids ISO rebuild entirely for same-or-smaller files. |
| `tablegenerator.py` (Shift-JIS range → index table) | `pleonex/font/tablegenerator.py` | Py2/3 | **GPL-3.0** | Trivial, safe to reuse. |
| Bokuract (PSP extractor) | `pleonex/Bokuract` | C#/Mono 4.5 | **GPL-3.0** | **Don't port.** Extraction-only, needs an unvendored `libgame`, and the formats are PSP-specific. The **wiki** is the asset. |
| TIMVisor (PS1 TIM ↔ PNG GUI/CLI) | `GriffithVIII/TIMVisor` | C# .NET 6 | **GPL-3.0** | Cleanest licence of the bunch; good for eyeballing TIMs. |
| jPSXdec index + Ghidra labellers | `psyou/ghidra_scripts/` | Jython 2 | **none** | Use as-is; `boku.idx` is already your disc. |
| External | jPSXdec (M35), Ghidra + PSX loader, **armips**, **mkpsxiso/dumpsxiso**, xdelta3/Delta Patcher, no$psx, PCSX-Redux, BizHawk+Octoshock, Monkey-Moore, Weblate + polib | | | |

**Licence reality**: everything from Hilltop is unlicensed (all rights reserved). pleonex and GriffithVIII are GPL-3.0 — which means if you vendor their code your tools become GPL-3.0. Cleanest path for a Rust toolchain (STK-1): **reimplement from the documented formats** (the wiki is CC-BY, facts aren't copyrightable) and cite. Message Hilltop for permission on `resource.py`/`MSG.py` if you want to lift directly.

## (c) Concrete hypotheses to test first, in order

1. **Confirm the dump.** `SCPS_100.88` = 524,288 B, `SYSTEM.CNF` = 68 B, `BOKU.BIN` = 109,303,808 B, `__STR/` with `BOKU_XA.XAM` + 24 `.IKI`. Redump: 280,170 sectors / 658,959,840 B, CRC32 `39d1fe3f`, MD5 `ee044864753c75ce0aea4ba777735fcd`, SHA-1 `5959bf7d9835d0a60aeb0143e2d0fc564bfea9fa`, **1 data track, Mode 2, no CD-DA, no LibCrypt** [WEB]. Serial also confirmed by psxdatacenter and `niemasd/GameDB-PSX/games/SCPS-10088/` [SRC via gh]. Re-release **SCPS-91232** "PlayStation the Best", 2001-06-14, **bit-identical content** [WEB].
2. **Hexdump `BOKU.BIN` offset 0.** Test in order: (a) `DFI\0` magic; (b) `u32 count` then 0x10-byte entries `{u16,u16,u32,u32,u32}` with sector-offset×0x800; (c) `u32 count` then 8-byte `{offset,size}`; (d) `u32 id` + `u32 header_length` then 8-byte entries (the PS2 map-pack shape). Validate with the arithmetic test: does `offset[n] + size[n] ≈ offset[n+1]`?
3. **If the head of `BOKU.BIN` isn't a directory, the LBA table is in the EXE.** Load `SCPS_100.88` into Ghidra at `0x80010000` (read `SYSTEM.CNF` for the true load address) and search for the little-endian sector number `1046` (`0x416`) or for 12-byte `{LBA, size, ?}` records — Hilltop's MML2 finding. Cross-check against the live RAM CD-position fields psyou documented (`0x025A40–42`).
4. **Prove the text encoding before anything else.** Pick a short in-game line you can see, e.g. a yes/no prompt. Hypothesis: it's a run of u16 LE values all `< 0x0500`, terminated by `00 80`, with `01 80` at every visible line break. **Grep `BOKU.BIN` for the byte pair `01 80` followed within ~200 bytes by `00 80`** — dense clusters are dialogue tables. Then check that each table is preceded by a `u32 count` + u32 offset array.
5. **Find the glyph sheet.** Run jPSXdec's TIM scan and eyeball the 4bpp candidates; a font sheet is a large, regular grid of small marks. Candidates from the index: the 8bpp `720×240`, `586×256`, `472×256`, `240×192` entries, and the 4bpp `64×144` near the very start of `BOKU.BIN` (sectors 1077–1079). Note the **one TIM inside the EXE** (16×48, 4bpp) — that's likely a tiny always-resident glyph set (digits?).
6. **OCR the sheet into a table** with FontRecognizer/KanjiTomo, then sanity-check index 0 = space, 1 = `、`, and the `0-9 A-Z a-z` run — if those land where PSP/PS2 put them, you have the mapping and can decode every line immediately.
7. **Confirm the vertical-text renderer.** In no$psx or PCSX-Redux, breakpoint on the glyph sheet's VRAM region while a dialogue box draws; look for a `base_x - (newlines * spacing)` pattern in the caller. If it's there, plan the axis swap now — it's the long pole.
8. **Locate the advance constant** (the fixed glyph width added to the cursor per character) and note whether there's any spare 256+ bytes of aligned zero space in the EXE for a width table. `SCPS_100.88` is exactly 0x80000 — check the tail for padding.
9. **Check for a CRC/anti-tamper table** near the head of `BOKU.BIN` or in the EXE before you edit anything: CRC-16/CCITT-FALSE over first 0x80 bytes, per the PS2 precedent.
10. **Compression check**: are any pointers in the directory missing their top bit while others have it set? (`8xxxxxxx` = compressed, Hilltop's tell.) If everything decompresses to itself, celebrate.
11. **Audio/video need no work**: jPSXdec already handles `.IKI` (plain STR) and `BOKU_XA.XAM` (plain CD-XA) generically. If you want subtitled cutscenes, that's Aconcagua-style per-frame PNG re-encode via jPSXdec's `<str-replace>` XML — Hilltop's `Aconcagua/SrtXmlGenerator.py` is the template.
12. **Rebuild strategy**: prefer `minimoni`-style **in-place sector patching** of the `.bin` while your edits fit; fall back to `dumpsxiso` → edit → `mkpsxiso` (two-pass, rewriting the EXE's LBA table) if you need to grow files. Ship as **xdelta**.
13. **Text volume planning**: PS2 has ~17,000 entries / ~540k JP chars across 601 map scripts. The PS1 original is a smaller game; **plan for roughly half** [INF], i.e. 8–10k lines. Use Weblate + `.po` exactly as Hilltop did — it's proven on this exact engine family.
14. **Expect non-text text**: the PS2 diary, bug info, bottle caps, calendars and shop signage are **baked into images**. On PS1, the diary (絵日記) is a core mechanic — assume its pages are TIMs to be re-drawn, not strings to be replaced.

## (d) Existing or in-progress English translation of the PS1 original

**None exists, and none is verifiably in progress as of 2026-09-19.** [WEB, with my own GitHub verification]

| Project | Target | Status | URL |
|---|---|---|---|
| Hilltop Works — **Boku no Natsuyasumi 2** | **PS2 sequel** | **RELEASED 2023-11-01**, English | https://github.com/HilltopWorks/BokuNoNatsuyasumi2 · https://www.timeextension.com/news/2023/11/the-long-awaited-english-fan-patch-for-boku-no-natsuyasumi-2-is-out-now |
| GriffithVIII / TraduSquare — *Mis vacaciones de verano* | **PSP port** | **RELEASED v1.0, 2025-07-29**, Spanish | https://github.com/GriffithVIII/Boku-no-Natsuyasumi-ESP/releases/tag/v1.0 · https://tradusquare.es/proyectos/boku-no-natsuyasumi/ |
| **obskyr** — *My Summer Vacation* | **PSP port** | Announced 2021-06-15, **never released, no public update** | https://www.nintendolife.com/news/2021/06/my_summer_vacation_by_the_makers_of_attack_of_the_friday_monsters_is_getting_an_english_translation · https://x.com/obskyr/status/1404945397093654528 (obskyr.io unreachable) |
| GriffithVIII English PSP patch | PSP | **Unconfirmed** — claimed in a Sept-2025 forum thread only | https://retrogametalk.com/threads/is-a-boku-no-natsuyasumi-psp-ps1-english-port-being-worked-on.14665/ |
| **PS1 original, any language** | SCPS-10088 | **NONE FOUND** | — |

Supporting evidence:
- **TraduSquare explicitly declined the PS1 version**: *"¿Se va a traducir la versión de PSX? La respuesta es no… todo nuestro trabajo solo funciona con esta versión."* (2021-10-15).
- The 2021 "holy grail" press wave (PC Gamer, ResetEra) was about the **PSP port**; the ResetEra thread's last post is 2021-09-14, and it already flags the **vertical-text problem** as requiring "entirely new text boxes".
- GitHub repo search for `natsuyasumi` returns **6 real projects** — the four you listed plus two unrelated Godot/inspired-by projects. Code search for `SCPS_100.88` returns 5 hits: `niemasd/GameDB-PSX`, `psyouloveme/boku1-reversing`, and cheat databases. [SRC, I ran these via `gh api`]
- A DuckStation text-hook request for the PS1 game exists and is dead: https://github.com/0xDC00/scripts/issues/445 (opened 2024-05-02, no replies).
- **`BOKU.BIN` has zero public format documentation** — no unpacker, no QuickBMS script, no wiki page, no forum thread. The only published information about its interior is jPSXdec's raw TIM scan.
- DataCrystal has **no page** for the game; ResHax returns **0 results**; no Japanese technical documentation found.
- **Don't be misled** by the Oct-2025 headline *"a cult classic Japanese PS1 title is getting its first official English release thanks to a popular fan translation team"* — that's **Milano's Oddjob Collection** (XSEED + Implicit Conversions + Hilltop), not Boku no Natsuyasumi.

**Negative-result caveats** (these are "not found", not "proven absent"): **romhacking.net** is Cloudflare-403 from this environment (I confirmed this myself with curl — it serves a JS challenge), **PSXDEV.net has been offline since October 2025**, MobyGames and reddit are bot-walled, and the session's WebSearch budget hit 200/200 partway through. A patch listed only on romhacking.net or announced only on Discord would not have surfaced.

**Best contacts if you want prior art**: **psyouloveme** (active Aug 2026, the only PS1-original RE prior art, already uses jPSXdec→Ghidra), **TheTedder**, the speedrun.com/boku moderators, and **Hilltop** (has shipped 10+ PS1 patches and the PS2 sequel; his Boku 2 tooling is the closest existing thing to what you need).

---

**No PLAN.md items were opened or closed; no work breakdown was created outside PLAN.md.** Nothing was written to the project — all artifacts are in the session scratchpad.