> Raw sub-agent survey, 2026-09-19, saved as delivered. **[V]** = verified with a URL, **[M]** = measured on the disc, **[I]** = inference.
> Where it recommends `.po` + Weblate with Japanese `msgid`s it predates two project decisions (README principles 2 and 3) and is superseded by them.
> Scratchpad paths are session-local and gone.

# PS1 Fan Translation — Practice, Tooling and Prior Art, 2026

## Survey for *Boku no Natsuyasumi: Summer Holiday 20th Century* (SCPS-10088, PS1, 2000)

Compiled 2026-09-19. Research by six parallel agents plus direct sector-level inspection of the disc image already extracted to `disc/`.

---

## 0. What the disc actually is (measured, not inferred)

Before any of the generic advice: I read the image directly. These are facts about **your** disc, and several of them overturn assumptions in the brief.

**Image geometry [M]**
- `disc/image.img` = 658,959,840 bytes = **280,170 sectors × 2352**. Single track, `MODE2/2352`, no CD-DA. `image.cue` is 68 bytes, one track, `INDEX 01 00:00:00`.
- Sector census: **166,660 Mode 2 Form 1** (submode 0x08 data, or 0x48 data+realtime) and **113,436 Mode 2 Form 2** — i.e. **40.5% of the disc is Form 2**, the sector type generic ISO tools silently drop.

**The ISO9660 filesystem [M]** — PVD at LBA 16, system id `PLAYSTATION`, volume space 280,170 sectors, root dir at LBA 22:

| Entry | LBA range | Size | Notes |
|---|---|---|---|
| `SCPS_100.88` | 23–278 | 524,288 (exactly 0x80000) | PS-X EXE, `.text` 0x80010000, size 0x7F800, entry PC 0x80049154, Japan |
| `SYSTEM.CNF` | 279 | 68 | `BOOT=cdrom:\SCPS_100.88;1`, `TCB=4`, `EVENT=10`, `STACK=801ffff0` |
| `__STR/` | 280 | 2048 | **a directory — your extraction to `disc/files/` missed it** |
| `BOKU.BIN` | 1046–54416 | 109,303,808 | 53,371 Form 1 sectors, submode 0x08 throughout |

**Inside `__STR/` [M]** — 26 entries, 25 of them FMV:

- `BOKU_XA.XAM` — LBA 54417–150869, **197,535,744 bytes (188 MiB)**, pure/interleaved Mode 2 Form 2 XA-ADPCM, subheader `file=2`, channels cycling 0–7, submode 0x64 (audio+form2+realtime). This is the voice bank.
- **25 `.IKI` files** — LBA 150870–280019 (129,150 sectors). Largest two: `M27.IKI` 86,917,120 bytes (42,440 sectors) and `M28.IKI` 85,995,520 (41,990) — together 65% of all video. Rest range 1.0–14.0 MB.

**The `.IKI` files are Sony STR video, and specifically the IKI bitstream variant [M]** — I verified the discriminator on five files. Each video sector is Mode 2 **Form 1**, submode **0x48**, payload beginning `60 01 01 80` (magic 0x80010160), interleaved ~7:1 with Form 2 XA audio (submode 0x64, `file=1`, channels 0–7). Reading the frame header:

| File | chunks/frame | bytes used | @0x16 | @0x18 | @0x1A | @0x1C |
|---|---|---|---|---|---|---|
| M010.IKI | 8 | 15,564 | `0x3800` | **320** | **240** | 0 |
| M031.IKI | 5 | 8,124 | `0x3800` | 320 | 240 | 0 |
| M27.IKI | 2 | 2,312 | `0x3800` | 320 | 240 | 0 |
| M28.IKI | 2 | 2,300 | `0x3800` | 320 | 240 | 0 |
| M190.IKI | 6 | 11,080 | `0x3800` | 320 | 240 | 0 |

In a normal BS v2/v3 stream, offset 0x18 holds a small qscale and 0x1A holds literally 2 or 3. Here both repeat the frame dimensions — **that is jPSXdec's exact IKI test** [V, `GenericStrVideoSector.java`, https://github.com/m35/jpsxdec]. All 320×240.

**There is free space, and it is where you'd want it [M]** — 919 Form 2 sectors are allocated to no file and carry an all-zero payload with submode `0x20` (Form 2, no audio/video/data bits — classic filler):

- **LBA 281–1045: 765 sectors, immediately before `BOKU.BIN`** → 1,566,720 bytes if converted to Form 1
- LBA 280020–280169: 150 sectors at the very end of the disc
- LBA 12–15: 4 sectors

**`BOKU.BIN`'s internal shape [M]** — first 9 sectors (0x0000–0x47FF) are zero; at **offset 0x4800** begins what reads as a table of little-endian u32s: `04000000 24000000 a4830000 c8830000 f02f0000 b8b30000 1c000000 d4b30000 …`. A magic scan of the first 64 MB found **8,881 occurrences of the TIM prologue `10 00 00 00`**, only 13 of them on a 2048-byte boundary — expected, since real TIMs inside a packed archive sit at sub-file offsets.

**Independent corroboration of the TIM count [V]** — `psyouloveme/boku1-reversing` has a *committed jPSXdec index of this exact disc* (`ghidra_scripts/boku.idx`, 2,744 lines, `Sector count: 280170`): **2,607 TIM images detected, 2,606 of them inside `BOKU.BIN`** — 1,377 at 8bpp, 1,230 at 4bpp; 764 × 8×8, 483 × 98×79, 199 × 16×8, 106 × 320×240, 94 × 240×192. https://github.com/psyouloveme/boku1-reversing

**[I], and it is the single best piece of news in this document:** jPSXdec finds TIMs by scanning for uncompressed headers. 2,606 hits means **`BOKU.BIN`'s graphics are stored uncompressed**. Hilltop spent *three months* cracking Dr. Slump's compression before extracting one line of script [V, https://www.kanzenshuu.com/2026/08/24/dr-slump-hilltop/]. You likely skip that entirely.

---

## 1. Disc image handling

### 1.1 CHD → BIN/CUE
`chdman extractcd -i game.chd -o game.cue -ob game.bin` is the universal instruction. `bin → chd → bin` round-trips byte-identically (SHA-1 verified by an agent directly); **`chd → bin → chd` generally does not** reproduce a byte-identical CHD, because output depends on chdman version, codecs and hunk size. `chdman info`/`verify` expose a logical `Data SHA1` that *is* stable. macOS: `brew install mame-tools`. [V]

### 1.2 Rebuilding: the tool landscape
**mkpsxiso is unambiguously current best practice.** v2.30, released **2026-07-06**, GPL-2.0, Lameguy64 [V, https://github.com/Lameguy64/mkpsxiso]. Its README claims *"almost all images can be rebuilt 1:1 now."* The features that matter here, all [V] from its docs/source:

- `type="data" | "mixed" | "xa" | "str"` — **`xa` and `str` are now aliases for `mixed`**. `mixed` is what preserves Form 2 sectors, subheaders and stream interleave.
- **`offs`** — force a file's starting LBA.
- **`<dummy>`** — *"Invisible filler sectors (not listed in directory records)… Use to preserve original disc layout and alignment gaps."* This is exactly the element that would describe your 765-sector gap.
- `order` — directory-record ordering independent of physical placement.
- `<license file="…"/>` — the PlayStation license/logo data.
- `-lba` — emits a placement log with file offsets and timecodes.
- **macOS: the official `mkpsxiso-2.30-Darwin.zip` is a universal binary** — CI sets `CMAKE_OSX_ARCHITECTURES: "x86_64;arm64"`, `MACOSX_DEPLOYMENT_TARGET: 10.15`. Zero friction on Apple Silicon.

`dumpsxiso` (same suite) dumps a disc to files **plus a mkpsxiso-compatible XML in strict LBA order**. One caveat from a project that measured it: a full round-trip was byte-identical *except 33 directory-metadata sectors*, because **mkpsxiso does not reproduce non-standard XA directory attributes** [V, self-reported, https://github.com/winlith/tokimeki-memorial-translation]. Another project needed `dumpsxiso -pt` to see files on an LBA-obfuscated disc.

**PSXImager** (`psxrip`/`psxbuild`/`psxinject`, cebix, GPL-2.0, 209★) is the other real option; `psxrip --lbns`/`-l` writes an LBN catalog that `psxbuild -c` consumes. Its README is the best short statement of why generic tools fail. Note: *"Red Book CD-DA audio tracks are not handled"*, and one project reports psxbuild images *"will not be bootable on original PlayStation hardware because the PlayStation checks a signature on the CD"* — mkpsxiso handles the license data; verify explicitly if you go the psxbuild route. [V, https://github.com/cebix/psximager]

**CDmage, psx-mode2, CDTool, TOC Changer, ECCRegen** — Windows-only, and their canonical host (romhacking.net's file archive) is gone; retrieve from https://archive.org/details/romhacking.net-20240801. `psx-mode2` remains the reference in-place injector and appears in live build scripts.

### 1.3 EDC/ECC — the rules
Verified from psx-spx (https://psx-spx.consoledev.net/cdromformat/):

```
Mode 2 Form 1                      Mode 2 Form 2
000h 0Ch  Sync                     000h 0Ch  Sync
00Ch 4    Header (M,S,S,Mode=02)   00Ch 4    Header
010h 4    Sub-Header               010h 4    Sub-Header
014h 4    Copy of Sub-Header       014h 4    Copy of Sub-Header
018h 800h Data (2048)              018h 914h Data (2324)
818h 4    EDC                      92Ch 4    EDC (optional)
81Ch 114h ECC
```
- **EDC covers offsets 0x10–0x817 in Form 1** (`adjust_edc(sector+0x10, 0x800+8)`) and 0x10–0x92B in Form 2.
- **ECC P/Q is computed with the header temporarily zeroed**, then the header restored — the Form 1 quirk that trips hand-rolled implementations.
- Submode bits: 0 EOR, 1 video, 2 audio, 3 data, 4 trigger, **5 Form2**, 6 realtime, 7 EOF. Your video = 0x48 (data|realtime), audio = 0x64 (audio|form2|realtime), filler = 0x20 (form2 only).
- The canonical C is `mkpsxiso/src/mkpsxiso/edcecc.cpp` (~60 lines, EDC poly `0xD8018001`, `ComputeEccBlock` parameterised for both P and Q passes), itself derived from Neill Corlett's ecmtools. [V]

**EDC/ECC mismatches are precisely what makes a patch work in emulators and fail on hardware** [V, https://github.com/Terraonion-dev/ECCScan]. Hilltop's `fill.py` writes sectors in place *without* recomputing them; the Policenauts Turkish toolchain *does* (reporting 1215 EDC + 1215 ECC sectors fixed on one disc). Treat recomputation as mandatory.

### 1.4 In-place patching vs full rebuild — the decisive question for this disc
The classic hazard, quoted from the jPSXdec manual §7.4 [V]:

> **"WARNING** Files, as we are familiar with them, are ignored by most PlayStation games. It was faster to hard-code sectors that contain data directly in the software than to spend a cycle reading the filesystem table before then reading the data. Due to this, in some cases data may extend outside the file boundaries, and even disc boundaries."

Three independent PS1 projects hit exactly this and all found the game keeps **its own LBA table**:
- **Mizzurna Falls** — table at EXE offset `0x0008411C` as `(i32 sector, i32 size)` pairs terminated `0,0`, **with a second copy duplicated inside asset #170 at `0x00023648`; both must be rewritten or the game desyncs** [V, https://github.com/nikita600/MizzurnaFallsEditor].
- **Moon** — CUE's unpacker *requires* `SLPS_010.31` "to get the LBA/sizes table" [V, RHDN #864 via Wayback].
- **`...iru!`** — a separate `FAT.TBL`. Their fix is the canonical one: build the whole disc → **parse psxbuild's own log to learn where files actually landed** → regenerate `FAT.TBL` → `psx-mode2` inject the corrected table and EXE back into the already-built `.bin` without rebuilding [V, https://github.com/Eight-Mansions/iru/blob/main/2_build.bat].
- **Racing Lagoon** — TOC lives in the EXE at `0x4A4DC`/`0x4A544`, consecutive u32 offsets where entry N+1 is entry N's end and bit 0x80000000 flags "compressed" [V, https://github.com/HilltopWorks/HilltopTranslationScripts].

**[I], high confidence:** `BOKU.BIN`'s exactly-0x80000-byte EXE + single-giant-archive shape is the textbook signature of this pattern, and 226,000 of your 280,000 sectors sit *after* `BOKU.BIN` at fixed LBAs addressed by streaming code. Growing `BOKU.BIN` in place is not an option without finding and patching that table.

**Recommendation for this project:** **Patch in place; do not rebuild.** Three constraints converge on a length-preserving patch: (a) `BOKU.BIN` occupies a fixed extent with 226k sectors of streaming media hard-addressed behind it; (b) jPSXdec's FMV replacement is already in-place and preserves every LBA (§6); (c) a length-preserving patch keeps PPF on the table, which unlocks a dramatically better user experience (§2). Write a Mode-2-Form-1 sector writer that recomputes EDC and ECC-with-header-zeroed per sector, and use the **765 unallocated sectors at LBA 281–1045 (1.5 MB as Form 1) immediately before `BOKU.BIN`** as your expansion arena — they are invisible to ISO9660, which is fine, because this game seeks by LBA anyway. Keep `dumpsxiso`/`mkpsxiso` 2.30 installed as the escape hatch and the round-trip oracle, but treat a rebuild as plan B. **Before anything else, do what Artemio did on Policenauts: prove you can extract and rebuild the untouched Japanese disc byte-for-byte.** That verified round-trip is what let them prove later hardware failures weren't the build system [V, LP Archive Update 48].

---

## 2. Patch distribution formats

### 2.1 Format comparison for a 659 MB image

| Format | Source verified? | Target? | Patch? | Can grow image? | Size limit |
|---|---|---|---|---|---|
| IPS | none | none | none | — | **16,842,750 bytes — DOA** |
| PPF1/2 | none / filesize only | none | none | **No** | — |
| PPF3 | 1024-byte "blockcheck", **prompt-and-continue** | none | none | **No** | 2⁶³−1 |
| BPS | ✅ CRC32 source | ✅ | ✅ | Yes | unbounded |
| xdelta3 ≤3.1.0 | ❌ (Adler-32 per *target* window) | ✅ per-window | ❌ | Yes | unbounded |
| **xdelta3 3.2.0 "armor"** | ✅ **BLAKE3 whole-file, checked before applying** | ✅ BLAKE3 | ❌ | Yes | unbounded |

Load-bearing details, all [V]:
- **IPS cannot address past `0x100fffe`.** Impossible here. http://fileformats.archiveteam.org/wiki/IPS_(binary_patch_format)
- **PPF3's blockcheck is a PVD fingerprint, not an image hash** — 1024 bytes at file offset `0x9320` (= user-data byte 8 of sector 16, the ISO9660 PVD). It distinguishes a different *game*; it does not catch a bad dump or an already-patched image. And `applyppf3_linux.c` prints `"Binblock/Patchvalidation failed. continue ? (y/n): "` — a prompt, not a refusal. https://raw.githubusercontent.com/meunierd/ppf/master/ppfdev/PPF3.txt
- **PPF structurally cannot grow an image** — `makeppf3_linux.c` drives its diff loop off reads of the original and stops at its EOF.
- **BPS** has a 12-byte footer with CRC32 of source, target *and* the patch — the only three-way validation. But **Flips needs ~6.6 GB RAM to create a BPS delta at this size** (libdivsufsort over the concatenation; `libbps.h` documents 5×(source+target), or ~11.9 GB with `moremem`), and mmap is explicitly disabled for BPS delta creation. Impractical.
- 🟢 **xdelta3 3.2.0 shipped 2026-06-21** and the project is active again after a decade (last commit 2026-09-06). **Armor mode** embeds BLAKE3 digests of source and target in the VCDIFF application header, is **on by default**, and **fails fast before applying**. Trap: *"Legacy xdelta3 builds … read the armored `name#hex` application-header values as literal filenames"* — so 3.0.11/3.1.0 users must pass `-s` and an explicit output name. https://github.com/jmacd/xdelta/releases/tag/v3.2.0, https://jmacd.github.io/xdelta/armor/
- 🔴 **`-B` is not optional.** xdelta3's source window defaults to 64 MB, and *"A source copy will not be found if it lies more than half the source buffer size away from its absolute position"* — with the default, no more than 32 MB may shift. Pass `-B` ≥ source size or you silently get a far larger patch. https://jmacd.github.io/xdelta/tuning-memory/
- 🔴 **xdelta3 embeds your absolute build paths by default.** A released PS1 patch was found carrying `F:\Isos\Saturn\snatcher\ps1\build\...` in its application header. **Use `-A ""`.** [V, by parsing the shipped patch bytes]

### 2.2 What the scene actually expects in 2026
The gold-standard example, unpacked and read directly: **Snatcher (PS1) by pepa**, v0.9.1, 2026-09-15, https://github.com/pepasjc/snatcher-translated. The zip contains two `.xdelta`, two matching `.cue`, README, release notes. Naming convention: `Game (Region) [T-En by <author> v<version>].xdelta`. Its README is the convention in full [V]:

1. Required redump BIN/CUE named exactly
2. **Size + CRC32 + MD5 + SHA-1 of the expected source**
3. The literal `xdelta3 -d -s` command
4. Named GUI front-ends per OS
5. **Size + CRC32 + MD5 + SHA-1 of the expected output**
6. Explicit *"Do not apply the patch to a `.iso` (2048-byte sectors) or a `.chd`; convert those to BIN/CUE first"*
7. Source-mismatch guidance, tested-platform list, no-sale/no-bundled-ISO line

Corroborating live projects [V]: Brightis (`.xdelta` against Redump #9919, CRC32/MD5/SHA-1 published, "One track, MODE2/2352"); Ace Combat 3 (MD5 per disc per revision); The Adventure of Little Ralph (**two patches — one for the redump Rev 1, one for non-redump dumps**); Ancient Roman (a second `-other.xdelta` against an alternate known dump). The Moon Korean patch adds pre-flight size + SHA-256 validation of *both* source and patch, writes output to a sibling folder so the original is never touched, ships a Windows portable ZIP bundling Python and xdelta, and **explicitly lists original PlayStation hardware as unverified rather than claiming it**. https://github.com/enthhende/moon-remix-rpg-adventure-korean-patch

**Your source hashes are already known [V]:** size `658,959,840`, CRC32 `39d1fe3f`, MD5 `ee044864753c75ce0aea4ba777735fcd`, SHA-1 `5959bf7d9835d0a60aeb0143e2d0fc564bfea9fa`. Single track, so redump's track-1 hashes *are* the whole-image hashes; no `.sbi`, no LibCrypt, none of the multi-track/pregap ambiguity applies.

### 2.3 User tooling — four corrections to common belief
- 🔴 **Delta Patcher is `marco-calautti/DeltaPatcher`**, not `marcrobledo/delta-patcher` (404). v3.1.6, 2025-08-18, 750★, GPL-2.0, **`macos11+_bin_universal.zip` → Apple Silicon native**. It statically links xdelta3 **v3.1.0**, so no armor. [V]
- 🔴 **`github.com/Alcaro/Flips` now redirects to `Sir-Walrus/Flips`, archived read-only since 2025-05-21**, README replaced with an AI gag. Last real release v198, 2025-02-21. Link Flathub (`com.github.Alcaro.Flips`) instead. **beat has no maintained home** (byuu died 2021; byuu.org gone) — the BPS spec survives only inside Flips. Don't point users at beat. [V]
- 🔴 **RomPatcher.js cannot apply a normal xdelta patch.** Official site is https://www.marcrobledo.com/RomPatcher.js/ (v3.3.1); there is no `rompatcher.net`. Its `RomPatcher.format.vcdiff.js` (still stamped `v20181021`) throws `'not implemented: secondary decompressor'` for any nonzero id, and every mainstream xdelta3 build defaults to *some* secondary compressor. Open issue #66 (2023) unresolved. It also skips the application header entirely, so no armor and no source verification. **Do not advertise it.** [V] (Corroborated in the wild: a romhacking staff comment on the Little Ralph entry says *"The online patcher doesn't support xdelta patches."*)
- **MultiPatch (macOS)** — https://github.com/Sappharad/MultiPatch, v2.0 (2021-09-03), unmaintained but **Apple Silicon native since v1.7.1**; its bundled xdelta includes LZMA. Expect a Gatekeeper right-click-Open. [V]
- **xdelta3 CLI** — 3.2.0 finally ships prebuilt macOS-arm64 binaries; `brew install xdelta` is at 3.2.0; ⚠️ **Debian/Ubuntu are stuck on 3.0.11 across bookworm, trixie and forky.** [V]
- **PPF**: PPF-O-Matic 3.0 is from 2001 and its Mac build died at Catalina; the Icarus/Paradox sources at https://github.com/meunierd/ppf are plain ANSI C and build trivially on arm64 (the *bundled* "Mac OS-X" binaries are early-2000s 32-bit and **will not run on Apple Silicon at all**). [V]

### 2.4 CHD, and the finding that should shape your design
No tool patches a CHD directly and `chdman` has no patch mode. Universal instruction: extract → **hash the extracted BIN against redump before patching** → patch → optionally `createcd`. That one "hash first" line prevents most support traffic.

🟢 **But DuckStation applies PPF over CHD at load time** [V, read from source: https://github.com/stenzek/duckstation/blob/master/src/util/cd_image_ppf.cpp]:
- Discovery rule: a `.ppf` with **the same base name in the same directory** as the disc image — and it wraps **any** parent image type, **CHD included**.
- PPF1, PPF2 and PPF3 all handled, FILE_ID.DIZ trailer included. Pregap handled for you.
- 🔴 **Off by default** — `[CDROM] LoadImagePatches`, UI "Apply Image Patches". Your README must say to tick it.
- 🔴 **No validation at all** — `ReadV3Patch` contains a literal `// TODO: Blockcheck`.
- 🔴 **Cannot grow the image** — writes past the last sector are *silently dropped*.
- RetroArch/Beetle PSX explicitly does not support softpatching; SwanStation has zero PPF code. DuckStation is the only emulator offering this.

**Recommendation for this project:** **Ship `.xdelta` as canonical, and a `.ppf` as a bonus — which is only possible if you keep the image length identical, which §1 already recommends for independent reasons.**

Canonical build command:
```
xdelta3 -e -9 -S lzma -B 700000000 -A "" -s orig.bin new.bin patch.xdelta
```
Publish four hashes on each side. Ship the `.cue` renamed to match. Decide armor deliberately — BLAKE3 source verification is real value, but Debian/Ubuntu (3.0.11) and Delta Patcher (3.1.0) will misread the header, so if you armor, document `-s` + explicit output name. Skip BPS (6.6 GB to build) and IPS (16 MB ceiling). Don't promise the browser patcher. For CHD users: extract → **hash** → patch → optionally recompress; and separately offer the drop-a-`.ppf`-next-to-your-CHD path with the DuckStation checkbox called out. That second path is a materially better UX than anything else in the scene and is worth designing for.

---

## 3. Text hacking patterns on PS1

### 3.1 Encodings
There is **no published statistic** on the raw-SJIS vs custom-table split; I found none and won't invent one. What's established:

- **Raw SJIS is structurally encouraged on PS1** because the BIOS ships a kanji ROM and PsyQ exposes `Krom2RawAdd()` — a game can render Japanese with *zero* font assets on disc. Confirmed in the wild: Wolkenkratzer stores *"all text as uncompressed Shift-JIS, drawing glyphs from the PlayStation BIOS kanji ROM"*; *b.l.u.e. Legend of Water* statically links `Krom2RawAdd` at `BASE_ADDRESS + 0x1ff5c`. [V]
- **Custom glyph-index tables are equally common** once a game ships its own font sheet (FF7, Racing Lagoon, PopoLoCrois).
- **The middle case that fools naive decoding**: 16-bit codes where `0x8000`+ are control codes and the rest index a glyph sheet — which is exactly what both Boku no Natsuyasumi ports do.

**Decisive test [I, mechanical]:** find the glyph-draw routine. Calls `Krom2RawAdd` (BIOS `B(51h)`) or reads `0xBFC6xxxx` → BIOS-font SJIS. Computes `u = (char % COLS) * W; v = (char / COLS) * H` → custom index into a sheet.

### 3.2 The BIOS kanji font
[V, https://psx-spx.consoledev.net/kernelbios/#bios-character-sets] — glyphs are **16×15 and 8×15, 1bpp**, not 16×16, so 30 bytes per full-width glyph:
```
BFC64000h Charset 1 (16x15, accented letters)     (NOT in JAPAN)
BFC66000h Charset 2 (16x15, various alphabets)
BFC69D68h Charset 3 (16x15, japanese/chinese)
BFC7F8DEh Charset 4 (8x15, mainly ASCII)
BFC7FE6Fh Charset 5 (8x15, punctuation)           (NOT in PS2)
BFC7FF8Ch Charset 6 (8x15, 7½ japanese chars)
```
Entry points `B(51h) Krom2RawAdd(shiftjis_code)` and `B(53h) Krom2Offset()`. There is **no** BIOS function for charsets 1, 4, 5, 6 — address them directly. Best readable reimplementation: PCSX-Redux OpenBIOS, MIT, https://github.com/grumpycoders/pcsx-redux/blob/main/src/mips/openbios/charset/sjis.c — glyph stride `0x1E`, and **note it has two lookup tables, `originalBiosTable` and `newBiosTable`: Sony changed the layout between BIOS revisions**, so a BIOS-font-dependent patch behaves differently across BIOSes.

**"Krom2RawJIS" could not be verified to exist** — zero GitHub hits. Almost certainly a garbling of `Krom2RawAdd`. Extraction is trivial anyway: uncompressed 1bpp at a fixed offset (charset 4 at file offset `0x3F8DE` in a 512 KB dump, 15 bytes/glyph).

### 3.3 Table files — the actual standard
The document to implement against: *Table File Format (TBL), v1.0 Draft, 05 July 2016, Nightcrawler et al.* — https://transcorp.romhacking.net/scratchpad/Table%20File%20Format.txt (this host is **not** Cloudflare-blocked). [V]
- UTF-8, `@TableIDString` declares the id. Normal entries `hex=text`, even hex-digit count, big-endian.
- **Control codes, prefix `$`**: `$E0=[Color],palette=$%X,index=%D` — `%D`/`%X`/`%B` are placeholders for parameter bytes that follow. This is the standardised way to round-trip parameterised control codes.
- **End tokens, prefix `/`**: `/FF=[END]\n\n`
- **Table switching, prefix `!`**: `!hex=[TableID],FallbackCondition` where `-1` = immediate, `0` = indefinite, `N` = N matches then fall back — exactly the mechanism for a game switching between 1-byte Latin and 2-byte kanji tables mid-string.
- Unmapped bytes render `[$XX]`; collisions resolved longest-hex-match.

**ImHex loads these natively** (File → Import → Custom Encoding) and ships SJIS/JIS X 0201/0213 tables — so a TFS-compatible table gives you a free visual second opinion. `imhex-1.38.1-macOS-arm64.dmg`, 2025-12-21 (prebuilt needs macOS 15+). [V]

### 3.4 Pointer tables
The RAM↔file mapping for a standard PS-X EXE, verified two ways:
```
ram_addr    = file_offset + 0x8000F800
file_offset = ram_addr    - 0x8000F800
```
(0x800 header + `t_addr` 0x80010000.) `Illidanz/hacktools/psx.py` literally hardcodes `0x8000f800` for EXE string relocation. **Your `SCPS_100.88` reports `.text` at 0x80010000, so this applies directly.** [V]

Four patterns observed in real PS1 projects [V]:
1. **Absolute RAM pointers in the EXE** — rewritten either as literal dwords or by patching the `lui`/`addiu` pair that builds the address.
2. **File-relative pointers with a count prefix**, offsets relative to the *table base* not file start.
3. **Offset table in the EXE describing an external blob** — Racing Lagoon.
4. **Absolute sector addresses (LBNs)** — FF7; ff7tools ships a `fixup` tool that recalculates *"all LBN file references in the game's code and control files"* after a rebuild.

🔴 **And the escape hatch when pointers are un-findable — "DATCH", the most important architectural idea in this whole survey.** Policenauts' text pointers were embedded in compiled adventure-VM bytecode, where pointer values collided numerically with opcodes, so *"there was no systematic way to find and recompute them."* The solution: **don't relocate text — hijack the text-lookup function.** A `JAL` retarget makes the original pointer land on a small header giving an offset to the real (longer) English string; the new routine also skips in-band control codes. [V, https://web.archive.org/web/20121231192521id_/http://www.slowbeef.com/romhack/pnhack5.html] It was later re-implemented in SH-2 for the Saturn port by someone who never disassembled the MIPS version — he studied the *behaviour*. Needed 4 variants for different string classes.

**Atlas (Klarth) corrections**, both [V]: **Atlas has no word-wrap** (the `#W*` family are *write-pointer* commands — `#WHB` = write high byte), and **Atlas is Windows-only as shipped** (MSVC solution, DLL extensions; the guide says *"Support is not offered in regards to compiling under other compilers"*). An MIT C++ mirror exists at https://github.com/stevemonaco/Atlas. Its Exercise 6 is a PSX multifile example, and its Extensions chapter explicitly suggests using an extension to *resize a segment* "for games that use file systems like PSX." Cartographer has no public source repo and is Windows-only. `abcde` (abw, v0.0.9, 2020, "OS Independent") claims all of Cartographer's and most of Atlas's features and is the best paper fit, but its download died with romhacking.net.

### 3.5 VWF — three complete PS1/PS2 implementations with source
**(a) Mega Man Legends 2 (PS1) — the minimal hack** [V, https://github.com/HilltopWorks/Mega-Man-Legends-2-Demo/blob/master/SLPS_021.09.asm]. ~20 instructions: reserve freespace at `0x80010660` (`0x2a8` bytes), `.import "vwf.bin"` (a flat `u8[]` of pixel advances indexed by glyph code), hijack the jump at the end of the glyph renderer with `la v0, func_vwf / jr v0`, look up `t3 = vwf_table[char]`, `addiu t3, t3, 0x1` (inter-letter gap folded in, not tabled), keep `li t3, 0xC` for 2-byte chars, then re-execute the 4 displaced instructions and `jr` back to `hook + 4*4`.

**(b) Boku no Natsuyasumi 2 (PS2) — per-glyph textured quads, and the vertical→horizontal rotation** [V, `scps_150.26.asm` + `asm_notes.txt`]. Original computes UV from a **17-column sheet** (`char%17`, `char/17`), emits a 0x28-byte GPU packet per glyph. The patch calls `func_vwf` three times per glyph (right UV, right X, advance), doubles the packet to 0x50 to add a drop-shadow quad, and the heart is one instruction: `addu s4, s4, v1`. The width lookup scaled to GPU fixed-point:
```asm
la   v1, vwf_table
addu v1, v1, s2       ; &table[char]
lb   v1, 0x0(v1)      ; table[char]
sll  v1, v1, 0x4      ; 1 pixel = 0x10 value
```
The rotation is visible as a one-instruction diff:
```asm
; NEW:      addu s2,a2,v0   ; base_y + newlines*spacing   <- Y advances per line
; ORIGINAL: subu s2,a2,v0   ; base_x - newlines*spacing   <- X advances per line (vertical)
```
plus swapping every `get_fb_x`/`get_fb_y` pairing in the quad setup. **That is, concretely, what "convert vertical Japanese text to horizontal" costs at the ASM level.** Tuning surface: `text_padding equ 2`, `font_spacing equ 0xD`, `mfw equ 0xa`, plus per-screen sites labelled `;Shop price kerning`, `;Hikari Yes/No kerning`, `;Vertical text newline distance`.

**(c) PopoLoCrois (PS1) — VRAM composition** [V, https://github.com/Illidanz/PoPoTranslation/blob/master/bin_patch.asm]. Font at `FontVRamX = 1024-(256/4)`, `FontVRamY = 48`; each glyph blitted by `jal MoveImage` (GP0 80h VRAM→VRAM). Two reusable ideas: the width table is **overloaded** — values ≤0x10 are relative advances, values >0x10 are **absolute tab stops**, giving free menu column alignment; and it adds **`STRLEN_VWF`** with five `jal` sites, because **the moment widths become variable, every `strlen`-based centering/right-align routine in the game is wrong and must be re-hooked.**

**The distilled recipe [I, synthesised]:** ① find the `li reg, WIDTH` or `addiu x_cursor, x_cursor, WIDTH`; ② carve freespace and wrap it in armips `.area` so overflow is a *build error*, not a crash; ③ byte-per-glyph width table as a raw `.bin` indexed by internal glyph code; ④ trampoline re-executing displaced instructions; ⑤ fix every derived quantity (right UV, `strlen`, centering, per-screen constants, line-length caps); ⑥ **pair kerning is essentially never implemented** — all three do proportional advance plus one global gap.

**Cheaper levers before a VWF, in order** [V]:
1. **Half-width font + raise the line cap.** *b.l.u.e.* does it in two instructions: `slti v0, v0, 0x20` (16→32 glyphs/line) and `add v0, r0, v1` (glyph width 16→8), plus `addiu v0,v0,1` to advance the text pointer by 1 byte instead of 2. Doubles characters per line before any VWF exists.
2. **Wolkenkratzer avoided a VWF entirely** by packing **two 5×9 Latin letters into each 16px full-width cell** (`pair_glyph(a,b)` → 32-byte cells), leaving the engine's advance/wrap/primitive logic completely untouched. Cheapest possible path if the engine is rigidly full-width.
3. Then the width table, then build-time pixel-accurate wrap, then window resizing.

### 3.6 Line breaking
The best pattern found [V, https://github.com/Illidanz/hacktools/blob/master/hacktools/common.py]:
```python
def wordwrap(text, glyphs, width, codefunc=None, default=6,
             linebreak="|", sectionsep=">>", strip=True):
    """Word wrap text to fit a pixel width, based on glyph lengths."""
```
It wraps **in pixels**, using the *same* `FontGlyph.length` values that generate the ASM width table. `codefunc` skips control codes so `{COLOR}` doesn't count; `sectionsep=">>"` wraps each textbox independently. The translator contract: *"The text is automatically wordwrapped, but a `|` can be used to force a line break. New textboxes can be added by appending `>>`."* — **overflow spills into an extra textbox rather than resizing the window.**

🔴 **One source of truth for widths, shared by inserter and ASM patch, is non-negotiable.** Yarudora's formatter is *handed `code/exe.asm`*; Ancient Roman's inserter is *handed `font.cpp`*; Hilltop's `reprint.printFont()` emits the atlas and `font_kerning.bin` in the same pass. Two hand-maintained copies drift, and you find out as overflowing boxes in QA.

**Recommendation for this project:** Start by finding the glyph-draw routine in `SCPS_100.88` and classifying it (BIOS-font vs sheet; sprite-per-glyph vs VRAM composition). Then take the cheap levers first — half-width + raised line cap — and only then the width table. Adopt the `.tbl` TFS format so ImHex can cross-check you, and adopt the `hacktools` wrap contract (`|` forced break, `>>` new textbox) since it's proven and translator-legible. **Generate the width table and the atlas from one pass and let the wrapper read that same artifact** — never type a second copy. Budget one VWF hack *per text surface*: the Spanish PSP feature list (§7) names yours — dialogue, diary, insect encyclopedia, insect names, bottle caps, calendar, save/load, minigames, bug sumo, TV, endings. ⚠️ **Check early whether the PS1 game renders any text column-major.** A ResetEra thread on the PSP effort says *"one of the reasons why this wasn't done sooner was because of the vertical text in the game"*, and Hilltop's BnN2 patch has a site literally labelled `;Vertical text newline distance`. If BnN1/PS1 has vertical text, your renderer hack is a layout rewrite, not a width table.

---

## 4. MIPS reverse-engineering tooling (macOS Apple Silicon)

| Tool | Version / date | Apple Silicon | Verdict |
|---|---|---|---|
| **Ghidra** | **12.1.3, 2026-08-18** | Yes, **but you must build natives** | Primary static RE |
| **ghidra_psx_ldr** | **2026.09.03**, prebuilt for 12.1.3 | n/a (Java ext) | Essential |
| **PCSX-Redux** | rolling, pushed 2026-09-19 | **Native prebuilt DMG** | Primary dynamic RE |
| **DuckStation** | rolling, 2026-09-12 | Universal, needs Ventura 13.3+ | Play-testing only |
| **no$psx** | v2.3, 2026-06-05 | **Win32 only, 32-bit** | Fallback, hard |
| **Mednafen** | — | builds | debugger yes, **no PSX trace logging** |
| **armips** | v0.11 (2020 release), repo pushed 2026-08-01 | build from source | Essential |
| **jPSXdec** | **v2.1 beta rev4378, 2026-05-17** | Pure Java, arm64 JDK | Essential |
| **mkpsxiso** | **2.30, 2026-07-06** | **Universal binary shipped** | Escape hatch |

### 4.1 Ghidra — the arm64 footnote that costs people a day
Quoted verbatim from `GhidraDocs/GettingStarted.md` at the 12.1.3 tag [V]:
> "An official public Ghidra release includes native binaries for the following platforms: Windows 10 or later, x86 64-bit; Windows 10 or later, ARM 64-bit (using x86 emulation); Linux x86 64-bit. Ghidra supports running on the following additional platforms **with user-built native binaries**: **macOS x86 64-bit; macOS ARM 64-bit**; …"

The decompiler and sleigh are native binaries not shipped for arm64 macOS. Fix:
```
xattr -d com.apple.quarantine ghidra_<version>_<date>.zip     # BEFORE extracting
cd <GhidraInstallDir>/support/gradle/ && ./gradlew buildNatives
```
JDK 21 for the current release (25 on master), Python 3.9–3.14, macOS 10.13+. Turnkey alternative: https://github.com/stevecheckoway/ghidra_app packages a double-clickable `Ghidra.app` with the arm64 natives built by default.

### 4.2 ghidra_psx_ldr
https://github.com/lab313ru/ghidra_psx_ldr — release **2026.09.03** with prebuilt zips for Ghidra 12.0 through 12.1.3; nine releases in 2026 chasing each Ghidra point release. 🔴 **"Due to Ghidra API change, only 12.0+ versions will be compiled moving forward."** [V]

**You do not need to generate PsyQ FLIRT/FIDB signatures yourself.** The loader consumes a curated JSON signature DB covering PSYQ **2.60, 3.00, 3.30, 3.40, 3.50, 3.61.0/1, 3.70, 4.00–4.70**, plus `.gdt` Ghidra Data Type archives per version: https://github.com/lab313ru/psx_psyq_signatures. Activate by dropping an empty marker file named `PSYQ_LIBNAME_XXX` (e.g. `PSYQ_LIBSND_470`) beside the OBJs. Also: **overlay support** is a headline feature, documented only by video (https://youtu.be/fpijiL1x3Pc — no description text, contents unverified). Troubleshooting: on `psyq/xx cannot be found`, append `.0` to the PsyQ Version field. GTE macro decompilation via Script Manager → PSX GTE. [V]

### 4.3 PCSX-Redux — the centrepiece
https://github.com/grumpycoders/pcsx-redux. Native macOS Arm DMG at https://distrib.app/pub/org/pcsx-redux/project/dev-macos-arm (I resolved `/latest` and it 302s to a real asset, `PCSX-Redux-e3e051ca-Arm.dmg`). Unsigned — right-click → Open. [V]

CLI flags, quoted from https://pcsx-redux.consoledev.net/cli_flags/ [V]: `-run`, `-stdout`, `-lua_stdout`, `-logfile`, `-bios`, **`-testmode`** (*"Interpret internal API's `pcsx_exit()` command as a request to exit the emulator"*), `-exe`/`-loadexe`, `-iso`/`-loadiso`, `-memcard1/2`, `-pcdrv`, **`-gdb`**, `-trace`, `-portable`. **`-run -testmode -lua_stdout` plus `pcsx_exit()` is a complete headless-CI story** — you can assert on a boot-and-screenshot in a build gate.

Debugger: full MIPS debugger (needs Dynarec off), **VRAM viewer/debugger** with 4-bit/8-bit modes and View → Select a CLUT with hover-preview, **GPU logger** (works with Dynarec on), **mapping breakpoints** (*"map the memory of the console while the software is running, and set breakpoints on the mapped memory"* — exactly the tool for finding a text renderer), CPU trace dump, GDB server on 3333, and a **web server on localhost:8080** with `GET /api/v1/cpu/ram/raw`, `GET /api/v1/gpu/vram/raw`, `POST /api/v1/execution-flow`, disc sector patching, and symbol upload from `.map` files. [V]

**The Lua API is a complete romhacking workbench inside the emulator** [V, 16 doc pages]:
- `PCSX.addBreakpoint(address, 'Exec'|'Read'|'Write', width, cause, invoker)` — the invoker is a Lua callback; ⚠️ **the breakpoint dies if the object is garbage-collected**, so keep a reference; `return false` to self-remove.
- **Inline MIPS assembler** — `PCSX.Assembler.New()`, `:parse()`, `:compileToMemory()/File()/Uint32Table()`, handles GTE opcodes, pseudo-instructions, labels, and is *"more lenient than normal MIPS assemblers."*
- **ISO reading** — `PCSX.openIso(path)`, `:open(lba, size, mode)` with `'M2_FORM1'`/`'M2_FORM2'`/`'RAW'`/`'GUESS'`.
- **PPF generation as a side effect of writing** — *"Any write you perform is recorded as a difference against the original image, and at any point you can ask for the accumulated set of differences to be written out as a `.ppf` file"*; `iso:savePPF()`. Reads PPF1/2/3, writes PPF1.
- **ISO builder** with auto-computed LBAs and raw `writeSector()`.
- ⚠️ **VRAM is not exposed through the Lua memory API** (`getMemPtr`/`getParPtr`/`getRomPtr`/`getScratchPtr` cover RAM/BIOS/scratchpad only) — use the viewer, the GPU Logger, or trap the transfer in main RAM. The VM runs on the UI thread; use coroutines or you freeze the emulator.

**Ghidra ↔ Redux, both directions** [V]: launch Redux with `-interpreter -debugger -gdb`, `brew install gdb`, connect Ghidra's debugger with `gdb -i mi2`, `target remote localhost:3333`. And in reverse, `ReduxSymbols.java` uploads symbols, `export_to_redux.py` generates `redux_data_types.txt` + `redux_funcs.txt` for typed struct overlays on live RAM — **with overlay-aware variants `OverlaysImporter.java`, `OverlayReduxSymbols.java`, `export_overlay_to_redux.py`.**

Related: **`psyq-obj-parser`** converts Sony's `.OBJ`/`.LIB` to ELF for modern GCC/Clang (how you consume original PsyQ libraries without Wine). **`nugget`** mirrors Redux's `src/mips` — `psyqo` (modern C++ SDK), converted psyq headers, linker scripts `ps-exe.ld`, `cpe.ld`, `nooverlay.ld`. Toolchain on Apple Silicon:
```
brew install nikitabobko/tap/brew-install-path
brew install-path ./tools/macos-mips/mipsel-none-elf-binutils.rb
brew install-path ./tools/macos-mips/mipsel-none-elf-gcc.rb    # builds GCC 16.2.0 from source
```
(Contrast: **PSn00bSDK ships no macOS prebuilt**, and the old `psx.arthus.net` macOS binaries are broken on modern macOS — missing `cc1`, built for 10.15.) [V]

### 4.4 DuckStation, and the others
**Licence is CC-BY-NC-ND 4.0** since 2024-09-13 (GPL → PolyForm Strict → CC-BY-NC-ND); *"redistribution of unmodified releases and code is permitted"*, modified versions cannot be published. SwanStation is the GPL hard fork. [V] Universal macOS build, Ventura 13.3+. Debugger exists (Settings → Show Developer Menu) with breakpoints, memory search, and VRAM/SPU VRAM in the memory editor — but **the wiki has no debugger page at all** and practitioners call it barebones. **Use DuckStation for play-testing, not RE.** [I]

Its **texture dumping** is excellent reconnaissance though: filenames encode everything — `texupload-P4-<texhash>-<palhash>-64x256-0-192-64x64-P0-14` (depth, texture hash, palette hash, VRAM write rect, offsets, size, palette range). Emulator-only and hash-keyed so it can't ship, but it gives you a *labelled inventory of every texture the game actually uploads* — the fastest way to scope graphics work. [V, https://github.com/stenzek/duckstation/wiki/Texture-Replacement]

**no$psx** v2.3 (2026-06-05) is still the best PS1 debugger and is **Windows 32-bit x86 only** — on Apple Silicon that's the hardest Wine case, and whether CrossOver handles 32-bit-on-arm64 is **UNVERIFIED** (CodeWeavers 403'd, WineHQ behind Anubis). Fallback, not a plan. **Mednafen**'s debugger supports PSX but **trace logging is "PC Engine CD and PC-FX currently"** — not PSX; docs warn save-states under the debugger *"may lead to significant malfunctions"* on PSX. **BizHawk** Nymashock has no debugger at all; Octoshock's is minimal — but it's what `psyouloveme` already uses for BnN1, and the RAM-watch files are real prior art. **Avocado** last changelog 2021-11-16. **XEBRA** (Win32, 2022-11-06) is the hardware-accuracy verification target; F6 → File → Export → Main Memory Image dumps RAM. [V]

### 4.5 armips
https://github.com/Kingcom/armips — MIT, 412★, **repo alive (pushed 2026-08-01)** but **last release is v0.11.0, 2020-05-10, Windows-x86 asset only**. Build from source: `git clone --recursive`, cmake, C++17. No Homebrew formula; no arm64 issues in the tracker. [V]

Directives that matter [V]: `.psx`; `.open "in.bin","out.bin",HeaderSize` (*"if file position 0x800 loads at 0x80010000 in memory, the header is 0x8000F800"*); `.org` (RAM) vs `.orga` (file offset); **`.importobj "code.o"` / `.importlib "code.a"`** — links gcc ELF objects into the patch, i.e. the bridge from "write the renderer in C" to "inject into the retail EXE"; `.fixloaddelay`/`.resetdelay`; and 🔴 **`.area`**, which makes overflowing your stolen freespace a *build error*. Every good project in this survey uses `.area`.

**Hook encoding constraints** [V, psx-spx]: `j dest` → `pc = (pc & 0xF0000000) + (imm26 * 4)` — **the top 4 bits are preserved, so a `j`/`jal` reaches only within the current 256 MB region.** All of KSEG0 is one region, so kernel-hole code at `0x8000Axxx` and game code at `0x801xxxxx` can reach each other, but `0x80xxxxxx` → `0xA0xxxxxx` cannot. And: *"Note that the instruction following the branch will always be executed."* Cross regions with `jr`/`jalr` via `lui`/`ori`.

A complete, citable PS1 hook [V, https://github.com/mateusfavarin/psx-modding-toolchain] — `buildList.txt` is two lines:
```
common, exe, 0x80010100, 0x0, src/main.c
common, exe, LOAD_Hub_ReadFile, -0x8, src/hook.s
```
and `src/hook.s` in its entirety is `.set noreorder` / `j Remap_Main`. That toolchain also does asset injection, automatic ISO rebuild, **xdelta generation**, and hot-reload + symbol upload into PCSX-Redux; Python 3.7+, macOS supported via the same brew recipes.

**No maintained Rust MIPS assembler targets PS1.** `mipsasm` 2.0.1 is N64-flavoured and stale (2022-11-12); `keystone-engine` has one release ever and is GPL-2.0 (viral). [V]

### 4.6 splat / decomp — and why it's the wrong shape here
**splat** supports PSX (`pip install -U splat64[mips]` — the `[mips]` extra is required), latest tag 0.50.0, but **the wiki Quickstart is N64-only** and the Home page says PSX support is "limited". A real PSX config [V, sotn-decomp]:
```yaml
platform: psx
compiler: GCC
target_path: disks/us/SLUS_000.67
subalign: 4
disassemble_all: true
global_vram_start: 0x80010000
```
Supporting stack, all Python and fine on arm64: **rabbitizer** (MIPS decoder in C with Python *and Rust* bindings, MIT, pushed 2026-05-29), **spimdisasm** (*explicitly supports "PS1's R3000 GTE instruction set"*, 1.42.4), **asm-differ** (needs a cross `objdump` — point `objdump_executable` at `messense/homebrew-macos-cross-toolchains`'s `mipsel-unknown-linux-gnu-objdump`), **m2c**.

🔴 **The cost datapoint:** `hansbonini/psx_tomba` is a Tomba! (PS1) decomp *whose stated goals include translation* (`i18n/` holds british and pt-BR). After all that work it stands at **18.22% matched code, 29.31% matched functions**, and pins splat 0.35.2 + spimdisasm 1.36.0 in CI because tool upgrades silently break the build. [V] **That is the best argument against a decomp for a translation.**

**The middle ground is native to splat** and sotn-decomp is the model: **one yaml per overlay** (`splat.us.dra.yaml`, `splat.us.bobo0..7.yaml`, …). Split *only* the overlay containing the text engine, `disassemble_all: true`, understand it with asm-differ/m2c, land the change as an armips patch. **You never need byte-matching, which is the expensive part.** [I]

### 4.7 Free space in a PS-X EXE
Header, all little-endian, 0x800 bytes [V, https://problemkaputt.de/psxspx-cdrom-file-playstation-exe-and-system-cnf.htm]:

| Off | Field |
|---|---|
| `000h` | ASCII `"PS-X EXE"` |
| `010h` | Initial PC |
| `014h` | Initial GP/R28 |
| `018h` | Destination address (`t_addr`) |
| `01Ch` | Filesize (`t_size`) — **must be N*800h** |
| `028h`/`02Ch` | BSS address / size |
| `030h`/`034h` | Initial SP/FP base / offset |
| `038h–04Bh` | Reserved for BIOS `A(43h)` |
| `04Ch–` | `"Sony Computer Entertainment Inc. for <region>"` |

Four sources of space:
1. 🟢 **The header itself — ~0x7B4 bytes of auto-loaded code space.** Quoted verbatim [V, psx-modding-toolchain `docs/4_notes.md`]: *"The playstation executable has a `0x800` bytes header, which is loaded in the retail bios/kernel at address `0x8000B070`… However, 'only the first `0x4C` bytes of the header are actually used', so you could exploit that fact and overwrite most of the header with your own custom code, which will be automatically installed in the kernel when the PSX tries to load the game executable."*
2. **Kernel holes** — `0x8000A000–0x8000B900` (0x1900), `0x8000C000–0x8000DF00` (0x1F00), `0x8000E400–0x80010000` (0x1C00). *"Rough estimations based on tests done using a SCPH 7501 bios."* For Unirom/NOPS compatibility avoid `0x8000C000–D000`, `0x8000E400–E43C`, `0x8000FE00–0x80010000`.
3. **Append to the EXE** — `t_size` must stay `N*800h`; the BIOS `A(42h) Load` copies whatever `t_size` says *"with no validation of memory allocation"*, so the ceiling is RAM.
4. 🟢 **Reclaim the dead BIOS/libgs debug-font routines.** Mizzurna Falls enumerates them with addresses [V, `main.asm`]:
   ```
   80051e9c-80051ed8 SetDumpFnt, no usings
   80051edc-80051f78 FntLoad,    no usings
   80051f7c-80052230 FntOpen,    no usings
   80052234-8005254c FntFlush,   using at: 80014b5c
   80052550-80052918 FntPrint
   ```
   They `nop`'d the single live `jal FntFlush` and took the lot. **Both Policenauts patches independently did the same thing** — Artemio: *"I believe the RAM where the font was stored is used for this purpose."*

🔴 **Do not treat anything above `0x80200000` as free.** `RAM_SIZE` at `1F801060h` is `0B88h` on *both* retail and dev units, which on retail declares a single 2 MB bank "incorrectly set as 8 MB" — and at least one shipping game relies on the mirror (*"Gundam Battle Assault 2 does actually use the '8MB' space (with stacktop in mirrored RAM at 807FFFxxh)"*). [V, psx-spx]

### 4.8 Overlays
PsyQ's `psylink` lets developers swap code into the **same fixed memory region**, declared in a `.lnk` file with `over(<group>)`, each emitted as **its own `.bin` on the disc** [V, retroreversing.com/ps1-psylink]. **An overlay is not covered by the PS-X EXE header** — no `t_size` of its own; load address and length come from the game's own CD-read call sites.

**How to find which overlay holds the text renderer** [V, https://tetracorp.github.io/tokimeki-memorial/methods/decompiling-psx-games.html]: hex-edit the overlay file to spot a unique byte sequence → dump RAM at the moment it loads → search the dump for those bytes → the match gives you the base → Ghidra **File → Add to Program** at that base with the X permission set. *"Some overlays remain unlisted in the disc structure and must be extracted from memory dumps."* Also: **Ghidra does not auto-detect Shift-JIS** — set the charset via Data → Default Settings, which matters directly for finding the text engine. And: **saving in Ghidra blocks undo history.**

Scale datum for calibration: Tokimeki Memorial's PSX executable is 674 KB **plus 26 additional 192 KB overlay files** ≈ 5.6 MB of program data. Your `SCPS_100.88` is 512 KB with `.text` only 0x7F800 — **[I]: either this game has no overlays and the whole engine is in the EXE, or overlays live inside `BOKU.BIN`. Determining which is a top-three question.**

**Recommendation for this project:** Ghidra 12.1.3 + ghidra_psx_ldr 2026.09.03 for static, PCSX-Redux for dynamic, armips for patching, and **write the runtime in C against PsyQ rather than raw assembly** (see §7 — this is the single biggest productivity difference between 2011-era and 2020s projects). Skip splat and any notion of a decomp. Your free-space plan, in order: the 0x7B4-byte header hole (free, automatic), the BIOS font routines, then appending with a bumped `t_size`. Use `.area` on every injection so overflow fails the build. Build a headless PCSX-Redux `-run -testmode -lua_stdout` smoke gate early — and per ENG-1, make it red on purpose once and read the failure message before trusting it.

---

## 5. Graphics

### 5.1 TIM, precisely
[V, https://problemkaputt.de/psxspx-cdrom-file-video-texture-image-tim-pxl-clt-sony.htm]
```
0x00 1  File ID   = 0x10
0x01 1  Version   = 0x00   (0x01/0x02 => "Compressed TIM")
0x02 2  Reserved  = 0x0000
0x04 4  Flags: bits0-2 Type (0=4bpp,1=8bpp,2=16bpp,3=24bpp,4=Mixed,5=8bpp variant)
                bit3 HasCLUT, bits4-31 zero
```
Your `10 00 00 00` scan hits are **ID + version + reserved**, not a 4-byte magic — which is why 8,881 of them are noise. Common flag words: `0x08`=4bpp+CLUT, `0x09`=8bpp+CLUT, `0x02`=16bpp, `0x03`=24bpp (independently confirmed by GIMP's constants `PSX_4BPP=8, PSX_8BPP=9, PSX_16BPP=2, PSX_24BPP=3`). ⚠️ **Kaitai's `psx_tim` models depth as a 2-bit field with bit 3 as CLUT — that mis-parses Type=4 (Mixed) and Type=5.** Trust bits 0–2 + bit 3.

CLUT and pixel blocks share a 12-byte prologue:
```
0x00 4  Size        = Xsiz*2*Ysiz + 0x0C
0x04 4  Destination = YyyyXxxxh   (VRAM X in HALFWORDS, Y in lines)
0x08 4  Dimensions  = YsizXsizh   (Xsiz in HALFWORDS)
0x0C .. data
```
For a CLUT block, `Xsiz` = colours per CLUT (16 or 256) and **`Ysiz` = number of CLUTs** — a TIM legitimately carries N palettes over one pixel block. Pixel width = `Xsiz*4` (4bpp), `*2` (8bpp), `*1` (16bpp). 4bpp packing: **low nibble = leftmost pixel** (img2tim v0.75's changelog is literally a fix for getting this backwards). Colour word: R 0–4, G 5–9, B 10–14, **bit 15 = STP**.

🟢 **The key insight: a TIM isn't an image file, it's a framebuffer transfer descriptor with its payload attached.** Never change the origin words unless you know the drawing code — and the origin is your search key when going VRAM→disc.

Sony's own spec, chapter 3, both HTTP 200: https://psx.arthus.net/sdk/Psy-Q/DOCS/Filefrmt.pdf and .../FileFormat47.pdf. **PXL/CLT** (split pixel/palette, IDs `0x11`/`0x12`): psx-spx records that **Sony's docs and real games disagree on which is which** (Granstream Saga, Bloody Roar ship them swapped) — sniff structure, don't trust the ID. **Headerless TIMs are a first-class case.** **TIM2/.tm2 is PS2/PSP only** and not on your disc.

### 5.2 Carving TIMs out of a blob — the validator you need
`10 00 00 00` alone gave you 8,881 hits in 64 MB (~1 per 7.5 KB vs ~0.015 expected at random — structured noise, mostly zero padding). The flags word plus size-consistency is the filter. These checks are not invented — they're what tim2view actually performs [V, https://raw.githubusercontent.com/lab313ru/tim2view/master/utim.pas]:

```
b[0]==0x10 && b[1] in {0,1,2} && b[2]==0 && b[3]==0
flags = u32le(b+4);  (flags & ~0x0Bu) == 0          # bits 2 and 4..31 must be zero
type = flags & 7; has_clut = (flags>>3)&1
has_clut => type in {0,1}                            # CLUT only legal for 4/8bpp
if has_clut:
    clut.size == 12 + clut.Xsiz*2*clut.Ysiz
    clut.Xsiz in {16,256} and matches type
    clut.org_x < 1024 and clut.org_y < 512 and clut.org_x % 16 == 0
img.size == 12 + img.Xsiz*2*img.Ysiz
0 < img.Xsiz <= 1024 ; 0 < img.Ysiz <= 512
img.org_x + img.Xsiz <= 1024 ; img.org_y + img.Ysiz <= 512
```
⚠️ **Do not require 4-byte alignment** — psx-spx names Shadow Madness and Gran Turismo 2 as counterexamples.

**Tools that scan disc-wide:** **jPSXdec's index is the free pass** — it scans every sector by content, lists items with the sectors they span, previews every CLUT (`-pal 1,3-5`), and can `-replacetim` in place. **tim2view** has the right validation but is Pascal/Lazarus, last pushed 2016-08-09, win32/win64/linux binaries only, **no macOS**. **PSXPrev** is .NET Framework + Windows. **binwalk v3 is now Rust** but has **no documented TIM signature**. [V]

### 5.3 CLUT constraints — the five ways a naive edit breaks
Hardware rules [V, psx-spx GPU page]: 4bpp=16 colours, 8bpp=256; texture pages are 256×256 texels placeable only on X multiples of 64 halfwords and Y multiples of 256 lines; CLUT attribute encodes X/16 and Y 0–511, so a 256-entry 8bpp CLUT spans 16 consecutive slots and must start on a 16-halfword boundary; texture cache is 2 KB with 64×64 effective windows at 4bpp (X=0 and X=0x20 collide).

1. **Palette reordering — the killer.** A TIM can hold N palettes over one pixel block; re-quantizing makes the image right in the palette your editor kept and wrong in all others. Worse, game code frequently indexes *specific* slots for flashing/fading/cycling, which breaks silently even when the static image looks fine. **Edit the indexed image with the original CLUT locked; never let a tool rebuild the palette.**
2. **`0x0000` is fully transparent** — psx-spx: *"texture color 0000h is fully-transparent"*, so *"textures cannot contain Black pixels"*; the documented workaround is `0x8000` (black + STP). **Pure black lettering becomes transparent holes on hardware while looking perfect in every PC viewer.**
3. **Losing STP** turns a translucent drop shadow opaque.
4. **Exceeding the colour budget** — at 4bpp you have 16 total, often 1 transparent and several spoken for; anti-aliased Latin eats slots fast.
5. **Resampling / changing dimensions** — width is in halfwords, so 4bpp widths must be multiples of 4 px, 8bpp multiples of 2; and the game's U/V and texture-window settings are hardcoded to the original size.

> 🔴 **GIMP 3.2's new built-in TIM plug-in has a load-bearing hole.** It registers load and export (`file-tim-load`, `file-tim-export`; args `type`, `origin-x/y`, `palette-x/y`) and is native on Apple Silicon — but its RGB555 packer never sets bit 15, and the same function writes 16bpp pixels *and every CLUT entry*. There is no `0x8000` or `<< 15` anywhere in the file. **Every TIM GIMP exports has STP=0 on every colour.** [V, reading https://gitlab.gnome.org/GNOME/gimp/-/blob/master/plug-ins/common/file-tim.c]

**img2tim has the correct knobs** [V]: `-b` (*"Set semi-transparent bit on fully black pixels … as fully black is treated by the PlayStation as the transparent color by default"*), `-t`, `-org x y`, `-plt x y` (*"No offset checking is done"*), `-usealpha`, `-alpt`, `-tindex`, `-tcol`, `-bpp`.

Also worth knowing: **PS1 anti-aliased fonts are often stored as an intensity ramp with an inverted-luminosity greyscale palette**, so naively pasting black text produces an inverted font — Hilltop's Vagrant Story README warns about exactly this. [V]

### 5.4 Compression
psx-spx catalogues the field [V, https://problemkaputt.de/psxspx-cdrom-file-compression.htm]: bitmap-level `.BS`; file-level LZSS variants (Moto Racer, Dino Crisis, Serial Experiments Lain), Ulz (Namco), GT-ZIP, RNC, BPE, ZIP/GZIP/ZLIB, LZMA, LArc/LHarc. The EA family has a clean magic (bits 0–7 = `FBh`; `10FBh` RefPack, `30FBh` Huffman, `4AFBh` RLE). **Sony shipped no standard compression for game data** — every SDK 2D format (TIM/PXL/CLT/CEL/BGD/ANM) is uncompressed. [I from the devref chapter list]

Identification: entropy/histogram sweep, magic sniff, then the reliable method — breakpoint the GP0 `A0h` transfer or the staging-buffer write and walk back; LZSS decompressors are visually unmistakable in MIPS. Reference decompressors: Racing Lagoon's `uncompress.py` (6-byte header, control byte bit7 = back-reference, bits 3–5 length+3, 11-bit offsets over a 2048-byte zero-initialised window, RLE escapes `0x7E`/`0x7F`); Policenauts PC-98's Konami LZSS (2048-byte ring, init pos 0x7DE, 11 offset bits / 5 length bits, plus a mandatory bit-3↔bit-7 byte swap). [V]

🟢 **And the best trick in the survey for when you can't beat the compressor: hijack the decompressor.** Policenauts compiled an **LZO decompressor from C to MIPS R3000** and hijacked the game's decompression entry point — *if a modified graphic carries their magic control code, run LZO; otherwise fall through to Konami's original routine.* LZO beat Konami's ratio, so most replaced graphics **fit in the original slot**, eliminating pointer churn. ~80 graphics replaced. [V, LP Archive Update 46]

**Recommendation for this project:** **[I, high confidence] you probably have no compression to fight** — 2,606 raw-scannable TIMs in `BOKU.BIN` is strong evidence, and it's the biggest structural advantage you have over every Hilltop project. Verify it by carving one 320×240 TIM out with the validator above and rendering it. Then: implement the TIM codec yourself (§9), with a **byte-identical decode→encode round-trip assertion over every TIM on the disc**, refusing to change depth, dimensions or origin. Derive the fixtures from the disc; never hand-type a header. That's ~150 lines and it's the highest-leverage code in the project — and the only place a vacuous gate would hide. Use jPSXdec as the cross-check oracle, DuckStation texture-dumping as the scoping inventory, and **do not use GIMP for final export** until the STP bug is fixed.

---

## 6. FMV — STR/MDEC and subtitling

### 6.1 What you have
Confirmed by direct measurement (§0): 25 `.IKI` files, 320×240, **IKI bitstream variant**, Form 1 video (submode 0x48) interleaved ~7:1 with Form 2 XA audio, at 10 sectors/frame and 2× disc speed → 15 fps. From the committed jPSXdec index [V]: **12,915 frames ≈ 14.3 minutes of video**; `M27.IKI` (4,244 frames) and `M28.IKI` (4,199) are 65% of it — **[I] almost certainly the endings**, since BnN1 has multiple.

### 6.2 jPSXdec — indexes by content, replaces in place
**v2.1 beta rev4378, 2026-05-17.** Pure Java, no JNI — runs natively on an arm64 Temurin/Zulu JDK 17 or 21; only *rebuilding from source* wants JDK 8. Zero macOS issues in the tracker. [V]

🟢 **Indexing is by content, not filename.** jPSXdec uses a *"sector claim system"* — every CD sector is passed to every claimer, which matches on signature. `GenericStrVideoSector` was deliberately rewritten in 2.x to be permissive: *"This opens the identification to be able to match not only known video sector variants, but also unknown types I've never seen before."* **Your `.IKI` extension and `__STR` directory are irrelevant.** [V, https://github.com/m35/jpsxdec/blob/readme/jpsxdec/jPSXdec-design.md]

🟢 **IKI is a first-class format with both a decoder and an encoder.** Spec §3.10: *"The .iki video format (found in files with .iki or .ik2 extension) is used in at least four games made by Sony: Legend of Dragoon, PaRappa The Rapper, UmJammer Lammy, Gran Turismo."* `BitStreamUncompressor_Iki.java` contains `BitStreamCompressor_Iki`. [V]

⚠️ **One caveat:** **Panekit (SCPS-10096)**, another Sony title of the same era, uses IKI with a header obfuscation needing a game-specific module (`modules/panekit/PanekitIkiObfuscation.java`). Neither "Natsuyasumi" nor "SCPS-10088" appears anywhere in the jPSXdec repo, so **BnN is not an explicitly tested game**. [I] likely plain IKI. Settle it in one run:
```
java -jar jpsxdec.jar -f disc/image.img -x BOKU.idx
java -jar jpsxdec.jar -x BOKU.idx -i <smallest video item#> -quality high -vf png -up Lanczos3 -dir ./out
```
The index's Details column prints `Iki{MDEC/2:… 3800:3800 dims again:WxH 0:0}` for IKI.

**Replacement syntax** (note the leading hyphen) and the XML schema, version **0.3** [V, manual §10.1]:
```
java -jar jpsxdec.jar -x BOKU.idx -i <item#> -replaceframes patch.xml
```
```xml
<str-replace version="0.3">
    <replace frame="10">newframe10.bmp</replace>
    <replace frame="@12345" size-limit="original non-zero">frame.png</replace>
    <partial-replace frame="@22354" tolerance="5" mask="mask.png" rect="20,15,200,150">new.png</partial-replace>
</str-replace>
```
Frame addressing: bare int = 0-based index; `#n` = header frame number; **`@n` = start sector, described as most reliable.** Resolution must match exactly; frame count cannot change; only `.bmp`/`.png` unless `format="bs"|"mdec"`.

**Bit budget:** it re-quantizes rather than failing — `CommonBitStreamCompressing.singleQscaleCompressFull` loops `for (int iQscale = 1; iQscale < 64; iQscale++)`, degrading quality until it fits; only after qscale 63 does it error *"Unable to compress frame {0} small enough to fit in {1} bytes"*. `size-limit="original non-zero"` exists for games that only use a subset of the allotted space and crash if you fill it. [V, source]

🟢 **The architectural headline: replacement is IN PLACE, verified from source.** `SectorBasedFrameReplace.writeToSectors` → `DiscPatcher.addPatch` → `CdFileSectorReader.writeSector` (hard-asserts size equality) → `CdSector2352.rebuildRawSector`:
```java
byte[] abRawData = getRawSectorDataCopy();
System.arraycopy(abNewUserData, 0, abRawData, _iHeaderSize, _iUserDataSize);
SectorErrorCorrection.rebuildErrorCorrection(abRawData, _subHeader.getSubMode().getForm());
```
**Sync bytes, MSF header, XA subheader and its copy all survive byte-for-byte; only user data changes; EDC/ECC recomputed for the form read from the preserved subheader. The `.bin` length never changes, nothing moves, ISO9660 is untouched, Form 2 audio sectors are never touched, and the 7:1 interleave and A/V sync are structurally identical. No rebuild needed.** [V]

🔴 **IKI-specific budget warning, and it bites.** From `BitStreamCompressor_Iki.compressFull`, verbatim:
```
// TODO: expand the video to use any empty video sectors
// Normal STR videos mark unused STR sectors as STR sectors. iki on the other
// hand marks unused video sectors and non-video so jpsxdec won't recognize
// them or use them.
```
and spec §3.10: *"There are only as many iki video sectors as needed to hold all the frame's data. Remaining sectors are null."* **A subtitled IKI frame must fit in exactly the sectors the original frame already used** — tighter than for a normal STR game. This is a jPSXdec gap, not a hardware limit. [I] BnN's static-camera frames compress small (M27/M28 use only 2 chunks per frame — 2,300 bytes), so subtitle-only edits should usually fit.

Quality: no published numeric benchmark exists. Manual §10.3 claims double-precision math makes it *"at least as good as the AVI2STR/movconv/mc32 tool found in the PlayStation 1 Dev kit"*, with four named missing optimisations. §10.2's practical lever: **contrast dominates MDEC frame size far more than colour**; grey is cheapest; blur hard edges, dim brights and lift darks if frames won't fit.

### 6.3 Real projects that subtitled PS1 FMV — and the two approaches

**(a) Burn into re-encoded frames.** Two concrete, readable examples:

- **Galerians undub** — https://github.com/descawed/galerians-undub. `ffmpeg -i x.avi -vf subtitles="$f" -fps_mode passthrough %d.png` → generated `<str-replace version="0.3">` → `jpsxdec -replaceframes`. 🔴 **The field note that contradicts the manual, verbatim from `undub.sh`:** *"the jPSXdec documentation suggests using partial-replace for things like subtitles to reduce quality loss due to re-encoding. I actually found that I got much worse results with partial-replace, though; the subtitles had frequent bouts of flickering and blurriness. for that reason, we're using replace here."* **Test both; don't assume partial-replace wins.** [V]
- **Tail Concerto undub** — https://github.com/rari-teh/tailconcerto. Two transferable details: export the reference video with **"Emulate PSX a/v sync"** (CLI `-psxav`) so cue timings match console (audio can start up to 0.15 s after video on hardware); and **delete by hand every frame without a subtitle** so you only re-inject changed frames. Also: ffmpeg numbers from 001, jPSXdec from 0. [V]
- Supporting: **FF7** burns subs only into the black letterbox bar, leaving the picture untouched — cheapest variant if you can letterbox. **Goemon Oedo Daikaiten**: *"I covered the original japanese subtitles and added the new english subtitles on top of them."*
- **Aconcagua** (Hilltop, PS1) is the fullest worked example, and `stripSTR.py` contains the hardest-won knowledge: **`expand_blanks()` converts otherwise-blank padding sectors into usable video sectors, renumbering chunks and back-patching `chunks_in_frame` after the fact** — because a subtitled frame compresses *worse* and needs more sectors than it was given. [V, https://github.com/HilltopWorks/HilltopTranslationScripts/tree/main/Aconcagua]

**(b) 🟢🟢 Composite at runtime — the better answer, and it exists in open source for PS1.**

**Eight-Mansions' `Ancient Roman` and `linda-cubed-again`** [V, https://github.com/Eight-Mansions/Ancient-Roman/blob/main/code/ancient-roman/code/subtitle.cpp]:

```c
void DrawMovieSubtitle(RECT* area, u16* image, u16* font, u32 curFrame) {
    // for each active part, blit glyph pixels into `image`,
    // skipping 0x8000 (the font's transparent key)
    if (sp != 0x8000) image[imgPos + y] = sp;
    ...
    LoadImage(area, (u_long*)image);
}
```
**They hook the movie player's per-slice frame upload. The MDEC output frame sits in a RAM buffer; they composite glyph bitmaps directly into that buffer, keying out the font's background colour, and only then call `LoadImage()` to DMA the slice into VRAM. The video stream on disc is never touched, never re-encoded, never re-multiplexed.**

The authoring pipeline is entirely reasonable:
1. Export each STR to AVI with jPSXdec (filenames come out as `MEETPIXY.STR[0].avi`)
2. **Translators time subtitles in Aegisub against the AVI**, save `.ass` (`PlayResX: 320 / PlayResY: 240`)
3. A codegen tool emits `generated_movie.cpp`: one `const u8 partdata_N[]` per line holding **glyph indices** into a 76-char table (I decoded a line to confirm: `{22,30,37,37,76,…}` with comment `// Well done, my son...` — 22='W', 30='e', 37='l', **76=space**), with **ASS timestamps resolved to `startFrame`/`endFrame` at build time**
4. Videos are keyed by an **sdbm hash of the filename the game already passes**, so the hook needs nothing else

```c
struct MovieSubtitlePart { const char* text; const u8 len; u8 textIdx;
    const u16 startFrame, endFrame, x, y, w; u16 curX, curY; };
```
Details if you copy it: **slice-aware** (PS1 players upload in vertical strips, so it carries `sliceX`/`sliceW` and resumes a partially-drawn string across boundaries); **max 3 simultaneous parts**; and **it's ported across two pixel formats** — Ancient Roman's live path is 16 bpp, **Linda Cube's live path is the 24 bpp one** — real evidence it generalises. Separately, **audio subtitles use `POLY_FT4` GPU primitives** pushed onto the ordering table: *video subs = framebuffer blits; audio subs = GPU quads.*

**Note the scope decision: Ancient Roman re-encoded exactly one video (`INTRO.STR`) and subtitled everything else at runtime.**

Why (b) is otherwise rare: *"The PSX GPU normally can't overlay anything on top of FMVs as it can't draw in 24bpp mode, it just displays data that's copied from MDEC"* — so you must hook the player, which is what Eight-Mansions did. [V]

### 6.4 Encoders
**ffmpeg is decode-only for MDEC** — https://ffmpeg.org/general.html lists "Sony PlayStation MDEC" under Video Codecs with **decoding only**, and "Sony PlayStation STR" under File Formats with **demuxing only**. Its role is subtitle burn-in and frame extraction. **psxavenc** (now WonderfulToolchain, v0.3.1, 2025-12-06) supports `v2`/`v3`/`v3dc` — **not IKI**, so it's not a route for your frame data. Its README carries a warning worth remembering if you ever rebuild: its `xa`/`str` outputs contain **dummy EDC/ECC placeholders** and *"cannot be added to a disc image as-is."* [V]

**Recommendation for this project:** **Do the FMV work with jPSXdec in place, and decouple it entirely from the text-engine work — the two can proceed in parallel, because jPSXdec never moves an LBA.** First run the index + single-frame export to settle plain-IKI vs Panekit-obfuscated. Then make an explicit architectural choice: **the Eight-Mansions runtime-overlay approach is better on every axis** (patch size — M27+M28 alone are 173 MB; picture quality; and it sidesteps the IKI sector-budget problem entirely) **but costs you an ASM hook into the movie player**; jPSXdec frame replacement is far less work but burns quality and may not fit. **[I] Given 14 minutes of video and two 87 MB endings, the runtime overlay is worth the hook.** If you do burn frames, test `replace` *and* `partial-replace` and believe your eyes, not the manual. Either way: Aegisub `.ass` is the right authoring format, use `-psxav` for the reference export, and only re-inject frames that actually changed.

---

## 7. Case studies

### 7.1 🟢 Hilltop Works — *Boku no Natsuyasumi 2* (PS2, 2023) — your reference implementation
https://github.com/HilltopWorks/BokuNoNatsuyasumi2 — Python 3, 120 files, 89 MB, single squashed commit 2023-11-11, 16★, README is literally just `# BokuNoNatsuyasumi2`. 🔴 **No licence at all — all rights reserved. Read it for technique; do not vendor the code.** Released 2023-11-01 after **11 months**, team of 5 (Hilltop lead; **Cargodin** localization; OldGameBox and blamerobots graphics/video; SnowyAria audio transcription). Now at v1.2.

**The build (`EXEC.py`), as it actually runs** [V]:
```
pullScript()                          # git fetch/reset/merge on Weblate-backed submodules
reprint.printAllCalendars/BottleCaps/BugInfo/Sumo()
compaction_map = reprint.printAllFonts()   # render atlas + emit width table, one pass
TIM2.injectAll()
injectMAPs(compaction_map); injectIMGs(compaction_map)   # .po -> binary
insertAllAdditions()
armips.exe map.asm
voice.applyEventScripts()             # inject subtitle events into event bytecode
UNPACK.packMaps(); UNPACK.packIMG()
voice.genSumoVoiceBin()
armips.exe scps_150.26.asm
ultraiso.exe -in boku2_patched.iso -d ISO_EDITS
```

**Container — and it is provably the same family as the PSP port** [V]. `UNPACK.py`:
```python
DIR_START=0x10 ; IDX_ENTRY_SIZE=0x10 ; FILENAMES_START=0x8140
is_dir=u16 @0x00 ; dir_info=u16 @0x02 ; filename_offset=u32 @0x04
sector_offset=u32 @0x08   ->  offset = sector_offset * 0x800
filesize=u32 @0x0C
```
**Byte-for-byte the same 0x10-byte entry as pleonex's PSP `cdimg.idx`**, same `0x800` multiplier, same folder/file discriminator — implemented independently by three different people (Hilltop, pleonex, and a Korean team) without reference to each other. **[I] A format stable across PS2 (2002) → PSP (2006) almost certainly originates on PS1 (2000).**

**Translator-facing format: gettext `.po` on a self-hosted Weblate** [V]. `boku-no-natsuyasumi-2.zip` holds **641 `.po` files** (601 map scripts, 24 fishing-msg, 7 diary, 7 IMG, plus item/fish info), exported from `https://translations.yuvi.app/projects/boku-no-natsuyasumi-2/`, `X-Generator: Weblate 4.12.2`. Measured over the whole corpus: **17,002 entries, 14,259 translated (83.9%), 540,609 Japanese characters → 909,727 English characters.**
```po
#. Table:1-Line:6
msgid "『ピカピカ輝く\n 銀色のロケット!』"
msgstr "(It's a shiny silver rocket!)"
```
🟢 **This is your single most valuable translation reference** — same studio, same engine family, same era, same protagonist, same register. It gives you canonical English for bug names, item names, and the `『』` inner-monologue convention rendered as parentheses. And the JP→EN character expansion ratio is right there: **1.68×**.

**VWF**: `font_kerning.bin` is **1,058 bytes, one byte per glyph** (`06 07 04 03 03 05 03 03 0a 03 …`, flat `0a 0a 0a` from ~0x70 for the uniform kanji block), imported by `scps_150.26.asm` into free space *inside the CRC file*. `asm_notes.txt` is the derivation (see §3.5). **`FontRecognizer.java`** OCRs the game's own font sheet cell-by-cell with **KanjiTomo** to recover the glyph order — 🟢 **that is how you build a `.tbl` for a custom-table game without hand-typing 2,000 kanji, and it satisfies ENG-1's "derive the fixture from the source of truth"**. `reprint.py` re-renders the atlas from TTFs with `layout_engine=ImageFont.LAYOUT_RAQM` and **eight distinct typefaces for eight text surfaces** — including `KGMidnightMemories.ttf`, a handwriting face, **for the diary**, composited over `FONT/diary_base.png`.

🟢 **`font-inject.txt` is the injection table** — identical layout to the extraction table but with unused Japanese punctuation slots **repurposed for Latin accents**: `éō[]ö` and `è` dropped into what were `「」『』【】` and `ぁ`. The classic slot-stealing trick, and exactly what you'd do for English apostrophes and quotes.

**`textCompaction.py`** finds every 2–16-char substring across the English script by frequency and assigns frequent n-grams to spare glyph slots, so one glyph draws a whole n-gram (`BLOCK_CHAR = "扉"` as sentinel). **That is how he bought back the space English expansion costs without touching the containers** — and it reduces draw cost too.

**Event-script VM** [V, `voice.py`] — 48 opcodes:
```python
EVENT_LABELS = ["POS","INI","IPROG","JMP","JMPM","JMPE","PROG","GO","WALK","RUN","MAP","CMAP","CMAPP","CMWT",
  "BGM","SE","XAMSG","MSG","XA","FLAG","DISP","ANM","BGANM","LOOK","END","AWT","BWT","XWT","DIXA","WIN","WAT",
  "MWT","TIME","IF","DEBUG","FACE","SELECT","MOVIE","LFLAG","WARP","MSGWT","YGO","XSEEK","CMPOS","SWIM","FOOT",
  "SHADOW","CMINI"]
HAS_TEXT  = ["XAMSG","MSG","SELECT"]
HAS_VOICE = ["XA","XAMSG"]
```
**The engine's notion of "voiced line" is literally "XA audio, optionally with a message"** — and your PS1 disc streams from a single 188 MB `BOKU_XA.XAM`. `voice.py` also reads **4,079 voice IDs** from `VOICE.xwh` at `0x1FE20` and exports per-ID WAVs for a transcriber, then `applyEventScripts()` injects `MSG`/`XAMSG` where none existed. 🔴 **This is the template for adding subtitles to unsubtitled voice, and it is a large separate work item.**

⚠️ **`UNPACK.py` recomputes a CRC-16/CCITT (poly 0x1021, init 0xFFFF) over the first 0x80 bytes of each file** — the game validates its own assets. **Budget for a similar integrity check on PS1.**

**Hilltop's other PS1 work, which is better reference than BnN2 itself:**
- **https://github.com/HilltopWorks/HilltopTranslationScripts** — *"A collection of scripts for hacking PS1/PS2 games for localization."* **Six complete PS1 pipelines**: Racing Lagoon, Dr. Slump, Aconcagua, Harmful Park, Maid&Machinegun, blue Legend of Water. Each has `.tbl` extract/inject tables, `scriptExtractor.py`/`scriptInjector.py`, `compress.py`/`uncompress.py`, `imageProcessor.py`, `build.py`, and **armips `.asm`** text hacks (blue has 17 per-overlay `TextAdjustment_*.asm` files). 🟢 **`dataDuplication.py` recurs in three projects: it finds a modified blob inside other archives by exact byte-match and propagates the edit** — the standard fix for PS1 discs that duplicate data across overlays for seek performance.
- **https://github.com/HilltopWorks/MinimoniPS1** (pushed 2026-01-03) — **the closest structural analogue to `BOKU.BIN`**: a single big `.BIN` with a sector-addressed TOC, recursively unpacked:
  ```python
  n_files = u16 at 0x00
  # entries at 8 + i*8:
  start_sector = u16 ; file_size = u16   # both in 0x800-byte sectors
  seek(start_sector*0x800); read(file_size*0x800)
  # recurse if the child is itself a package
  ```
- **https://github.com/HilltopWorks/VagrantStory-Font** — `fill.py`, the minimal in-place CD writer (`DATA_START=24`, `DATA_SECTOR_SIZE=0x800`, `SECTOR_SIZE=2352`). ⚠️ It does **not** recompute EDC/ECC.

**Timeline calibration** [V, Kanzenshuu interview]: *"There weren't a lot of resources on how to get started"*; for Dr. Slump, **the first three months** were spent learning to rebuild PS1 CDs, analyse proprietary formats and decompile a compression algorithm, filling notebooks with assembly before extracting the script. *"Almost every game uses its own personal compression format that you have to hack first."* Racing Lagoon took **6 months** and was only his second project.

⚠️ **Hilltop's itch.io presence could not be verified and probably doesn't exist** — `hilltopworks.itch.io` and `hilltop-works.itch.io` both 404; `hilltop.itch.io` is a different person. His public artifacts are GitHub + Patreon + Bluesky (`@hilltopworks.bsky.social`) + X (`@HilltopWorks`). Non-technical interviews: https://readonlymemo.com/a-summer-vacation-in-november/ and https://www.kanzenshuu.com/2026/08/24/dr-slump-hilltop/. A Vancouver Retro Game Expo 2026 panel may have more: https://www.youtube.com/watch?v=rgyyvvCNJ1Y

### 7.2 🟢 Eight-Mansions — the FMV subtitle framework, and the layout to copy
https://github.com/Eight-Mansions — 26 public repos, the most prolific public PS1 translation toolchain in existence. Core: **esperknight, Cargodin, SnowyAria** — and **Cargodin is on both Hilltop's BnN2 team and Eight-Mansions.** That's your introduction. Discord: https://discord.gg/bewGNtm

PS1-relevant: `Ancient-Roman` (2 discs, C#, 677 commits, the FMV+audio subtitle framework), `linda-cubed-again` (**Linda³ Again**, PS1, SCPS-10039, same framework, mkpsxiso), `iru` (`...iru!`, EN/FR/ES, VWF asm, FAT.TBL rewrite), `Kowai-Shashin`, `planet-laika`, plus `timmer` (C#, *"easy to use (hopefully) TIM extraction/insertion tool and TIM class"*) and `bs2png` (C++, **includes its own `mdec.cpp`**).

**Project layout — copy this wholesale** [V, `linda-cubed-again`]:
```
0_create_patch.bat  1_merge_scripts.bat  2_insert.bat  3_build_cd.bat
cd/linda.xml                      <- mkpsxiso project
code/linda_vwf.asm                <- armips VWF patch
code/linda/code/{font,text,subtitle,loadfile,platform}.cpp   <- REAL C, compiled for PS1
code/linda/code/{generated,generated_audio,generated_movie}.cpp
exe/SCPS_100.39  exe/orig/SCPS_100.39
trans/movie_subs/*.ass  trans/audio_subs/*.ass
```

🟢 **Write the runtime in C, not assembly.** The trick is in the build script [V, `Ancient-Roman/2_build_cd.bat`]:
```bat
copy /y NUL cd\Ancient-Roman-Disc-1\CODE.DAT >NUL
tools\armips.exe code\ancient-roman-1.asm
pushd code\ancient-roman
pmake -e RELMODE=DEBUG -e OUTFILE=main -e OPTIMIZE=2
```
**An empty placeholder file is created in the disc tree, and armips assembles the compiled C blob plus hooks into it.** **[I] This is the biggest practical difference between 2020s and 2011-era practice, and it is why Ancient Roman could afford a whole subtitle engine while Moon spent eight years on fonts.**

**`cd/linda.xml` is the mkpsxiso pattern for your exact disc shape** [V]:
```xml
<identifiers system="PLAYSTATION" application="PLAYSTATION" creation_date="1997091710100000+0"/>
<license file="linda/license_data.dat"/>
<default_attributes gmt_offs="36" xa_attrib="32" xa_perm="1365" xa_gid="0" xa_uid="0"/>
<file name="_RI01.STR" source="linda/LINDA/_RI01.STR" type="mixed"/>
<file name="_BATTLE.XA" source="linda/LINDA/_BATTLE.XA" type="mixed"/>
```
**`type="mixed"` on every `.STR` and `.XA` is how you keep real-time interleaved streaming files sector-correct.** Directly applies to your 25 `.IKI` files and `BOKU_XA.XAM`.

And `...iru!`'s build→parse-log→regenerate-FAT→inject loop (§1.4) is the canonical solution to the in-EXE-LBA-table chicken-and-egg.

Release engineering: `xdelta3 -9 -S none -B 1812725760 -e -vfs`, **with a second patch built against an alternate known dump so two common redumps both work**, and a real release note: ***"We've switched from xdelta3 to xdelta to help with compatability."*** 🟢 **Both Sampaguita and Linda³ shipped as "v0.95", not 1.0** — deliberately versioned, known-imperfect, with a documented defect list, iterating to `.1`/`.2` within 24 hours.

### 7.3 Policenauts (PS1, 2009) — the best-documented PS1 translation ever
Eleven public write-ups by slowbeef at https://lparchive.org/Policenauts/ (Updates 42–52), plus two chapters that exist **only** on Wayback: **pnhack4 "Text Pointers + The Build"** and **pnhack5 "Jump Hijacking"**. 🔴 **Chapters 6–7 were never written, and pnhack4's "The Build" section stops mid-sentence — the disc-rebuild chapter does not exist.** [V]

Team & timeline: Artemio Urbina (founder, private SVN), Marc Laidlaw (translator, ~1yr on script), slowbeef (lead programmer, **13 months**), Scarboy (LZO hijack), plus 5 more. Project began ~2001; slowbeef joined July 2008; released 2009-08-24. The alpha→beta list ran to **86 milestones**. **Tools are not public** — the SVN was private.

Key contributions already cited above: **DATCH** (§3.4), the **LZO decompression hijack** (§5.4), hiding injected code in the font file (§4.7).

🔴🔴 **The hardware catastrophe — the single most actionable lesson in this document.** Everything worked in ePSXe/pSX and **failed completely on a real PS1, eight months in**: looping VOX audio, garbled movie audio, freeze on the first modified graphic, jumbled menus. Three root causes, **all emulator leniency** [V, Update 48]:
1. **Byte alignment.** The game's audio data is always 4-byte aligned; the insertion script stripped trailing zeroes, so audio DMA went off-track on hardware. Fix: **pad each inserted subtitle with 1–3 blank spaces to restore 4-byte alignment.**
2. **MIPS load delay slot.** An `lb` immediately followed by a `beq` on that register works on emulators (no pipeline) and fails on hardware. Fix: **`nop` after every memory read.**
3. **Compiler target mismatch.** SPIM emitted MIPS-II+ opcodes ("branch likely") absent on R3000 and didn't insert delay-slot `nop`s. Their fix was gloriously blunt: **a script that inserts a `nop` after every single instruction and then doubles every branch offset.** LZO got ~2× slower; irrelevant.

They then adopted **XEBRA** plus a modded PS1 and PSP as verification targets. Also: 🔴 **burn at ≤4× or the XA intro gives a black screen on real hardware.** And the patch shipped a **second `patch-athlon-cpu.bat`** because some Athlon CPUs produced `XD3_INVALID_INPUT (checksum)` and needed `-n`.

Modern third-party successor exposes a layer the original team never documented: **DPK entries carry CRC-32/BZIP2 checksums** that must be rebuilt, and modified sectors need **Mode2/Form1 EDC/ECC recomputation** (1215 EDC + 1215 ECC sectors fixed on Disc 1). https://github.com/TheAti1/policenauts-disc1-translation-tools (MIT, Python, 2026)

The Saturn port (2016) went further: *"The code that controls subtitles was modified, giving us full control over them… This also enabled us to subtitle background dialogue not subtitled in the PlayStation patch."* And one feature was **abandoned as infeasible** — progressive glossary unlocking; they **deleted the bios entirely** rather than ship spoilers. An honest scoping decision worth emulating.

### 7.4 Mizzurna Falls (PS1, 2021) — GPL tooling, real VWF, and "the script doesn't fit"
Three generations [V]: Resident Evie finished a **~40,000-word** script translation in Dec 2016, her hacker vanished, and in Jan 2018 **she publicly released the full English text so someone else could build a patch**. Gemini built a version in 2019 and **pulled it at his own request** (crashes, text didn't fit). nikita600 + Cirosan shipped **v1.0 on 2021-03-30** over several months of lockdown across three countries via Discord.

🔴 **The central constraint: even with a new compression scheme, the script still didn't fit**, so **Cirosan fundamentally rewrote and edited a majority of the script (with Evie's blessing)** *"without sacrificing coherence, quality, or significant plot points."* The result is framed as a **localization**, not a translation. Two independent PS1 projects hit this wall and Mizzurna's resolution was editorial. **For a diary/journal game with fixed-size UI boxes, the pressure is worse, not better.**

**https://github.com/nikita600/MizzurnaFallsEditor** — C#, **GPL-3.0**, pushed 2025-07-29. README is *"TODO"*, but the source is a complete readable pipeline:
```
00_unpack_iso.bat : psximager\psxrip.exe -l "...cue" FileSystem
02_apply_patch    : armips.exe main.asm -temp result.asm
03_build_iso.bat  : psximager\psxbuild.exe -c FileSystem.cat Build.bin
```
**The structural parallel to your disc is exact:** the ISO contains essentially two files — `SLPS017.83` (executable) and **`CD.BIN`, one giant container** — with the file table inside the EXE (and duplicated in asset #170). Assets have **no names**; they're addressed by index. Text format `MDT`: signature `"MDT\0"`, `i32 stringCount`, a **128-entry `short` character table**, per-string `(i16 offset, i16 charCount)` — and inside a string, **a signed control byte ≥ 0 indexes the table (1 byte/char); a negative byte means the next 2 bytes are a raw 16-bit character.**

**VWF is feature-flagged** (`USE_VWF:` in `main.asm`, with `.ifdef USE_VWF` around `renderTextCharacter01_patchCharWidth`), and compression is implemented **twice** — once in C# for the build, once in **hand-written MIPS** for runtime (Huffman *and* LZSS).

### 7.5 Moon: Remix RPG Adventure — the cautionary tale
**Never released. 8 years. Leaked betas don't boot on hardware.** [V]

Started 2011-09-16 by SteveMartin; esperknight romhacking. Effectively cancelled Sep–Oct 2019 when Onion Games announced the official Switch localization. Distributor note on the leaked build: *"Fully translated. But not playable on original hardware. On emulator random crashes may occur."*

🔴 **Root cause, and it is a process failure not a technical one.** esperknight, 2011: *"Can't guarantee it working on the psx itself though as my ps2 isn't setup to play backups. So if anyone wants to volunteer to play it on there psx I'd appreciate it."* **Hardware testing was crowdsourced to volunteers and never became a gate. Eight years later it still didn't boot.**

🔴 **VWF is a category, not a task.** esperknight repeatedly finished "a" VWF and then needed another: *"Animals VWF is done as well as items again (found a bug where if you viewed an animal it broke the items...). Menus are next, then name entry and possibly the MD player."* He later **redid the whole VWF from scratch.**

🔴 **The "misc text" tail is what killed the schedule.** Pennywise, Feb 2013 — the most honest artifact in this survey:
> *"the translation is finished and inserted back into the game with a VWF. The game is playable... but a lot of the misc portion of the game hasn't been hacked yet. This is nothing game-breaking, it's just little things that need some love and care. Taken by themselves they're not much, but when you add them together you got a hell of a lot to do."*

Also: script split across ~60 non-linear files; **audio/music regressions caused by the hack were a major bug class**. And Gemini's font advice, worth heeding: *"A font choice should always depend on the game's style and translation needs… As for the PCE font dump, I'd suggest to pretty much always ignore japanese font resources. Not only they are not really suitable in most cases, they also look ugly 4 times out of 5 because romaji sets are usually done with no actual guidelines in mind."*

### 7.6 Tokimeki Memorial (PS1) — three efforts, no released patch
**Project XEUPIU** (https://github.com/vgarciasc/xeupiu, Python, 70★, active 2026) is not a patch at all — an external program that screenshots the emulator, recognizes the Japanese text, and draws a translucent English overlay. Author: *"it is not a traditional 'reverse engineering' translation… closer to approaches like that of Textractor."* **"PoorCR" uses exact bitmap matching, not OCR** — a database of glyph PNGs harvested from the game's own font as 1-bit numpy arrays, claimed 100% detection. 🔴 **Brittleness is severe and openly documented**: DuckStation pinned to build `v0.1-7836`, 4:3, "All Borders (Aspect Uncorrected)", **Nearest Neighbor (Integer)** scaling, toolbar off, Japanese Rev 4, Windows at 100% scaling on a single monitor, Linux needs X11; **changing the in-game cursor icon breaks recognition.** **[I] A fallback for games you cannot crack; a bad fit for Boku** — it can never subtitle FMV, fix text-in-textures, or widen a box.

**tetracorp** (https://tetracorp.github.io/tokimeki-memorial/) is the best free write-up of PS1 RE methodology — its Ghidra page is cited throughout §4.

⚠️ **`winlith/tokimeki-memorial-translation`** (created 2026-08-07, 0★) — **the author's own README: *"THIS IS NOT A FINISHED TRANSLATION. I am just sharing what an LLM could figure out so somebody can pick it up and actually do it."*** Treat every specific address as unreviewed. But its structural lessons match independently-verified practice: **overlay checksums** (each `.EXN` carries a trailing 4-byte checksum; *"Editing without fixing it → the overlay hangs on entry"*); **page-relative pointers** (12 bits, page-relative — a line can only move within its own 4 KB page); 🔴 **duplicate strings** (17 copies of one walk-home line in a single file — translate one, miss sixteen); a **two-instruction VWF substitute** (overwrite both `lbu pitch` loads with `addiu pitch, zero, 8`); and a good translator pipeline (JSON `{off, jp, en}`, 14,306 strings, **per-string fit warnings naming the exact byte budget**).

### 7.7 Yarudora (Sony, 1998) — and why it's the *easy* FMV case, not your model
Nobody translated the PS1 originals; both patches target the 2005 PSP ports. **Double Cast** (RHDN #5777, 2020-11-29, Cargodin + EsperKnight + SnowyAria). **Sampaguita** (https://github.com/Eight-Mansions/yarudora_3_psp, 2024-04-09) — README: *"Project originally started alongside Double Cast and Sampaguita back in the mid-2010s. Was left on the backburner for some years before coming back to it in a script rewrite in mid-2023"* — **~8 years wall-clock with a full script rewrite at the end**, shipped at v0.95 with a documented remaining gap.

🔴 **The engine does not bake dialogue into the video — it renders text as a separate engine layer, and the Japanese original already ships a player-facing subtitle toggle** (*"enabled in the settings menu under Display > Text/Voice"*). The entire translatable script lives in `S001/SCN001.SSC`…`SCN019.SSC`, inserted with **Atlas**, and **not one video file is touched anywhere in the build**. **[I] Yarudora is the easy case and is NOT your model.**

Its build is still instructive: **`2_format`** runs `yarudora_psp_formatter.exe trans\merge trans code\exe.asm 470` — **line-breaking English against a 470-pixel budget using the letter-width table that lives in the ASM file**. One tool owns both. And the VWF hack needs **separate entry points and width getters for the gallery menu, the scene menu, and the endings**, plus explicit `turn_off_scene_menu_vwf`/`turn_on_scene_menu_vwf` toggles because some surfaces must stay fixed-width. **Same lesson as Moon: budget one hack per text surface.**

### 7.8 🟢 The Boku-specific prior art, in one place
| Repo | Target | Language | Licence | Activity | What it gives you |
|---|---|---|---|---|---|
| [psyouloveme/boku1-reversing](https://github.com/psyouloveme/boku1-reversing) | **BnN1 PS1** | Lua + Jython | **none** | **pushed 2026-08-24** | jPSXdec index of your exact disc; Ghidra CD-XA sector-labelling scripts; a substantial **RAM map** |
| [GriffithVIII/Boku-no-Natsuyasumi-ESP](https://github.com/GriffithVIII/Boku-no-Natsuyasumi-ESP) | BnN Portable PSP | — | Apache-2.0 | v1.0, 2025-07-29 | **The feature list = your WBS.** No source, no scripts — 24 screenshots and a README |
| [pleonex/Boku-no-Natsuyasumi](https://github.com/pleonex/Boku-no-Natsuyasumi) + [wiki](https://github.com/pleonex/Boku-no-Natsuyasumi/wiki) | BnN Portable PSP | C# (Libgame) | **GPL-3.0** (wiki CC-BY-4.0) | archived 2025-09-05 | **The format spec.** `DFI\0` container, pack format, **script text format** |
| [HilltopWorks/BokuNoNatsuyasumi2](https://github.com/HilltopWorks/BokuNoNatsuyasumi2) | BnN2 PS2 | Python | **none** | 2023-11-11 | Full pipeline + 641 `.po` bilingual corpus + VWF derivation |
| [KendritPy/Boku_ESP_JP](https://github.com/KendritPy/Boku_ESP_JP) | BnN Portable PSP | Python + C PRX | **MIT** | **pushed 2026-09-04** | 🟢 `docs/boku-dialogue-format.md` — **the best-written spec anywhere**, newer and more precise than pleonex's wiki. **8,539 structurally paired JP/ES dialogue records** |
| [snake7594/boku-natsu-portable-kr-patch](https://github.com/snake7594/boku-natsu-portable-kr-patch) | BnN Portable PSP | Python | **none** | 2026-07-03, discontinued | `tools/boku_tools.py` — cleanest single-file implementation of the whole stack. **`table_full_rough_patched.txt`: 2,020 character codes** |

**🟢 The character table is an engine constant across the series.** An agent diffed pleonex's PSP table against Hilltop's PS2 BnN2 table: after NFKC normalization, **codes 0x0000–0x0125 (0–293) match on 285 of 294 positions**, and the 9 remainders are ambiguous glyph transcriptions by the two authors (`。` vs `゜`, `‘` vs `´`), not real differences. That block is the entire punctuation + Latin + digits + full hiragana + full katakana + numeric kanji run, ending `…ヮワヲンヴヵヶ一二三四五六七八九十百千万億兆` at identical indices in both games. Only kanji from code 294 onward are per-game. [V, by direct diff]

**🟢 Control codes are identical across PSP and PS2** [V]: `0x0000` NUL, `0x0001`–`0x0400` glyph, `0x8000` end, `0x8001` newline, `0x8002`+arg wait/page, `0xFFFF` alternate terminator — all 16-bit little-endian. And the Kendrit spec nails a subtlety the others got wrong:
> The verified multi-page sequence is `0x8002, argument, 0x0000, first word of next page`. **Removing that zero can drop the first visible character of the following page.**

**pleonex's PSP script format** [V, wiki] — your working hypothesis for `BOKU.BIN`:
```
u32 numBlocks
BlockInfo[] { u16 id; u16 length; u32 offset }
Block: u32 (numElements*2)
       ElementInfo[] { u32 nameptr; u32 dataptr }   // relative to the block offset
       Element: null-terminated ASCII name, then u16 text/command stream
```
The first 3 element entries carry no text; from index 3 onward they alternate ASCII key / 16-bit text stream.

🔴 **Where PS1 and PSP differ:** images are **TIM** on PS1 vs **TIM2/PIM2 PSP-swizzled**; **PSP gzips nearly everything (`.gz` = plain gzip, `.gzx` = u32 size + gzip) while `BOKU.BIN` appears uncompressed**; PSP has no CD-XA/`__STR` streaming layer. And `Docs/*.asm` in pleonex's repo is **PSP Allegrex, using `seb`, a MIPS32r2 instruction the PS1's R3000 does not have** — do not expect it to transfer.

**Is there an existing PS1 English patch? No.** GitHub repo searches for `natsuyasumi` (42 results) and `boku natsuyasumi` (18) turn up only the projects above. Wikipedia notes *"an 'English fan translation' was reported in development as of 2021"* — that is **obskyr**, and it targets the **PSP port**, not PS1 (https://x.com/obskyr/status/1404945397093654528; obskyr.io was refusing connections during research). ⚠️ romhacking.net and romhack.ing both 403 automated fetches, so treat "no PS1 English patch" as **well-supported for GitHub, unverified for the romhacking sites**.

🔴 **And the decision you should be able to defend:** TraduSquare — the only team to *finish* a Boku translation — looked at PS1 vs PSP and publicly chose PSP: *"¿Se va a traducir la versión de PSX? La respuesta es no. La versión de PSP ofrece una experiencia mucho más completa que la original. Además, todo nuestro trabajo solo funciona con esta versión."* [V, https://tradusquare.es/anunciamos-la-traduccion-de-boku-no-natsuyasumi-portable/] It still took them ~4 years. `TODO.md` Message 1 already states your counter-argument (letterboxing, 16:9 stretch, character-model layering) — put it in the README.

**Recommendation for this project:** Clone all six Boku repos plus both Hilltop repos and `Eight-Mansions/linda-cubed-again` before writing a line of code. **Adopt Hilltop's BnN2 shape** — `.po` on a git-backed Weblate, `#. Table:N-Line:M` comments, one pass generating atlas + width table, armips with `.area` — and **Eight-Mansions' directory layout and C-runtime build**. Your **first experiment is one command: check `BOKU.BIN` offset 0 for `44 46 49 00` (`DFI\0`)**. If present, `boku_tools.py::parse_index` works nearly unchanged. If not, try the MinimoniPS1 shape (`u16 count` at 0, `u16 sector / u16 sector-count` from `+8`), then the Racing Lagoon shape at the 0x4800 table I found, then look for a second authoritative index inside `SCPS_100.88`. **You have 2,606 known-good TIM sector positions from `boku.idx` to fit a TOC hypothesis against — an unusually strong constraint.** 🔴 **Licence care: Hilltop's repos, psyouloveme's and the Korean patch carry no licence at all (all rights reserved) — read for technique, reimplement, do not vendor.** pleonex is GPL-3.0, Kendrit MIT, Griffith Apache-2.0. **And talk to `psyouloveme` (active on your exact target), Cargodin (bridges Hilltop and Eight-Mansions), and GriffithVIII (knows every text surface in this game).**

---

## 8. Translation file formats & LLM workflow

### 8.1 What projects actually use
Four intermediate formats appear in real repos, and they sort by team size:

- **gettext `.po` + `polib` + self-hosted Weblate** — Hilltop's BnN2, 641 files, 17,002 entries. `msgid` = original Japanese **with control codes preserved as readable tokens** (`{STOP}`, `{WAIT=0x..}`); `msgstr` = English; binary location in the extracted comment (`#. Table:1-Line:6`). The build does `git fetch && git reset --hard && git merge origin/main` on each component repo, so **Weblate ↔ git ↔ build is fully automated**. [V]
- **JSON `{off, jp, en}` per source file** with automated per-string fit warnings naming the exact byte budget — the Tokimeki approach. [V]
- **CSV** — XEUPIU; also the Tricolore Crise project's *"structured, scene-ordered CSV worklist."* [V]
- **Shift-JIS plain text with the Japanese commented above the English** — Eight-Mansions' `...iru!`, fed to Atlas. Their README: *"Anything that starts with // is a comment that will be ignored… **YOU MUST USE SHIFT/JIS CHARACTER ENCODING!!!**"* [V]

⚠️ **The gotcha with PO for game scripts** is msgid uniqueness — gettext keys on `msgid` + `msgctxt`, and game scripts have *many* duplicate lines (17 copies of one Tokimeki line). Either use monolingual PO with the binary location as the key, or put the location in `msgctxt`. Weblate supports both (*"Supports context"*, `msgctxt` demonstrated in its examples). [V, https://docs.weblate.org/en/latest/formats/gettext.html]

### 8.2 🟢 Weblate can enforce your length limits with the real font
This is the finding that makes Weblate more than a nice UI [V, https://docs.weblate.org/en/latest/user/checks.html]:

- **`max-length:100`** — character count only. Fires a companion *source* warning when the English source uses over 85% of the limit.
- 🟢 **`max-size:500:2`** — *width:lines*, and it **renders the text with an actual uploaded font**: `max-size:500:2, font-family:ubuntu, font-size:22`, with `font-weight` and `font-spacing` also supported. Multiple lines enable word wrapping.
- **`placeholders:$URL$:$TARGET$`** — with regex support (`placeholders:r"%[^% ]%"`) — for enforcing that control codes survive.
- **`regex:^foo|bar$`** — custom pattern validation, Unicode-property aware.

**[I] If you upload an approximation of the game's font to Weblate and set `max-size` per string from your own width table, translators see box-overflow in the editor rather than in QA.** That is the only mechanism I found in any tool that closes this loop at translation time rather than build time.

### 8.3 LLMs for game-script translation — evidence, both ways
**Academic grounding:**
- *Multilingual Game Dialogue Translation using LLMs: A Performance Survey* (GAS 2026 / ICSE 2026, Nguyen, Politowski, Rahman, Lee) — human evaluation with a deduction-based scoring scheme across four dimensions: **Terminology Consistency, Contextual Accuracy, Register and Tone, Variables and Tags**. Finding: models *"achieve strong semantic fidelity and effectively preserve variables and tags,"* but challenges persist in *"stylistic tone and cultural nuance."* Quality correlated with model size. https://dl.acm.org/doi/10.1145/3786171.3788386
- *Benchmarking LLMs for Game Localization Quality Assurance* (Tian & Wu, AMTA 2026) — 48,000 samples, 96 settings, eight models. Claude Sonnet 4 best (F1 = 0.766), Qwen-2.5-72B 0.711, Gemini 2.0 Flash 0.691. Target language did **not** significantly affect performance (p = 0.285), but **Japanese proved the most challenging**. https://aclanthology.org/2026.amta-research.12/
- *JP-TL-Bench* (Jan 2026) on why JA→EN is hard to score: *"subtle choices in politeness, implicature, ellipsis, and register strongly affect perceived naturalness."* https://arxiv.org/abs/2601.00223

**A professional human workflow worth copying** — Tom Gally via Simon Willison [V, https://simonwillison.net/2025/Feb/2/workflow-for-translation/]: (1) prompt with source plus context/tone/style instructions; (2) **run through several LLMs and pick the strongest base**; (3) iterative refinement, *"requesting ten alternative translations at a time"* for hard sentences — *"using an LLM as a sentence-level thesaurus on steroids is particularly wonderful"*; (4) **validation review by a different LLM against the original**; (5) text-to-speech read-through to catch awkward phrasing.

🔴 **The technical objection specific to Japanese game scripts**, stated well in the Held Games piece: Japanese drops subjects and leans on scene context, so **a line-by-line spreadsheet pipeline cannot disambiguate** — one phrase may be *"Where is Kyoko?"*, *"How is Kyoko?"* or *"Did you tell Kyoko?"* [V, https://heldgames.com/guides/ai-fan-translations-controversy]

**Recommendation for this project:** Use **`.po` on a self-hosted Weblate**, exactly Hilltop's shape, with `#. Table:N-Line:M` comments, control codes preserved as readable braces tokens, and **`max-size` checks driven by your generated width table**. Since you're planning LLM-assisted translation via Fable sub-agents, three things are non-negotiable given §10's climate and the disambiguation problem: (a) **feed scene context, not lines** — the extraction must preserve scene/speaker/day grouping, which pleonex's block/element format already gives you; (b) **carry a hard glossary** — bug names, item names, character names, the `『』` inner-monologue convention — and **seed it from Hilltop's 641-file BnN2 corpus**, which is canonical English for the same studio and register; (c) **a separate LLM QA pass against the original** plus a control-code round-trip validator that fails the build. And run the numbers early: BnN2's measured expansion was **540,609 JP chars → 909,727 EN chars (1.68×)**. Two PS1 projects in this survey (Policenauts, Mizzurna) hit "the script does not fit", and Mizzurna's resolution was a **full editorial rewrite**. Decide whether you are translating or localizing *before* the translation pass, not after.

---

## 9. Rust and Python libraries

> Resolving the CON-2 conflict toward `TODO.md`: **Python-first is the right call, and the research supports it independently.** The honest summary is that **the Rust ecosystem is missing every layer this project actually needs**, while the Python/C++ ecosystem has all of them battle-tested in shipped PS1 patches. I give the Rust picture in full so you can overrule it.

### 9.1 ISO9660 / CD-XA Mode 2 with LBA control
**No Rust crate can write a PS1-valid disc image. Not one.** [V, exhaustive crates.io search]

| crate | ver | last release | downloads | verdict |
|---|---|---|---|---|
| **`opticaldiscs`** | 0.15.0 | **2026-08-10** | 2,146 (1,846 recent) | **Best Rust reader.** MIT. BIN/CUE raw-2352 + CHD behind one `SectorReader`. Explicitly read-only. No Form 2 / subheader / EDC-ECC mention |
| `cdfs` | 0.2.3 | 2023-10-09 | 8,133 | ISO9660 reader, stale |
| `iso9660` | 0.1.1 | 2023-04-02 | 24,964 | self-described *"(Incomplete) implementation"* |
| `iso9660_simple` | 0.2.7 | 2026-05-30 | 14,112 | reading only |
| `iso9660-rs` | 1.0.2 | 2026-01-06 | 903 | no_std, bootloader-oriented |

**Python `pycdlib`** (1.20.0, 2026-08-05, LGPL-2.1, 185★) *does* implement the ISO9660 **XA directory-record extension** (`class XARecord` in `dr.py`, `CD-XA001` signature check) — but grepping for `2352`, `2336`, `subheader` across `pycdlib.py` and `dr.py` returns **nothing**. It works in 2048-byte logical blocks. **XA filesystem metadata yes, raw Mode 2 sectors no.** [V, by grepping the source]

**`pymkpsxiso`** (PyPI 0.2.0, 2026-02-06, MIT, https://github.com/Illidanz/pymkpsxiso) is a thin wrapper that shells `mkpsxiso`/`dumpsxiso` — its entire API is `pydumpsxiso.run(bin, dir, xml)` / `pymkpsxiso.run(bin, cue, xml)`. Honest and useful. [V]

### 9.2 EDC/ECC
**There is no real Rust crate.** [V, by exhaustion] Searches for `ecc`, `edc`, `cd sector`, `cdrom`, `subchannel` return elliptic-curve crypto and erasure coding. The single near-hit is `cdrom_crc` **v0.1.0, published 2018-07-02, 76 downloads in 90 days** — the EDC CRC only, not the Reed-Solomon P/Q parity. `reed-solomon-erasure` is GF(2⁸) erasure coding, the wrong shape entirely.

**[I] Porting is a small job and the right call in any language** — two init-time lookup tables plus ~60 lines, from `mkpsxiso/src/mkpsxiso/edcecc.cpp` (itself from Neill Corlett's ecmtools). ⚠️ **And there's a licence reason to port from the *algorithm* rather than the file: mkpsxiso is GPL-2.0, so shelling out is clean and linking is not.**

### 9.3 CHD — a genuine Rust bright spot
| crate | ver | last release | downloads | notes |
|---|---|---|---|---|
| **`chd`** (chd-rs) | 0.3.4 | 2026-03-03 | 72,787 (19,696) | **Pure safe Rust**, BSD-3, *"drop-in compatible with libchdr"*, V1–V5, CD codecs, within 15% of libchdr. *"There are no plans to implement write-operations."* |
| **`libchdman-rs`** | **0.289.0** | **2026-07-31** | 3,698 (3,067) | Wraps **MAME's own CHD core**, *"100% feature parity with chdman"*, **CD read AND write**, `cd::create_from_cue`, `CdCookedReader`. **Ships prebuilt static archives including `aarch64-apple-darwin`** |
| `chd-sys` | — | — | — | **does not exist** |
| Python `pychdr` | — | — | — | **does not exist on PyPI** |

`opticaldiscs` already pulls `libchdman-rs` behind a default `chd` feature, so CHD support is nearly free in Rust. [V]

### 9.4 TIM codecs
**There is no Rust TIM crate. Zero.** lib.rs search for "tim playstation" returns literally *"Nothing found :("*. **PyPI has nothing either** — `psx-tim`, `timtool`, `tim2png`, `psxtools` all NOT FOUND (`pytim` is molecular dynamics). [V]

What exists: **jPSXdec** (Java, ⚠️ licence is *"free for non-commercial use"* — **not OSI**); **`tim2png` inside `cebix/ff7tools`** (ISC, Python, Pillow); **`Eight-Mansions/timmer`** (C#, insert *and* extract); **`GriffithVIII/TIMVisor`** (C#, GPL-3.0, 4/8/16/24bpp TIM↔PNG); **Hilltop's `TIMresource.py` + `ImageHill.py`** (Python, shared verbatim across two of his repos — a de-facto reusable PS1 image library supporting `ONE_BIT` through `FIFTEEN_BIT_DIRECT` and `RGBA_5551_PS1` CLUTs); a **Kaitai `psx_tim`** spec (read-only, and ⚠️ its 2-bit depth model mis-parses Type 4/5).

**You are writing this either way.** It's a small format and nothing round-trips with CLUT preservation.

### 9.5 Shift-JIS in Rust — three quirks that will bite
`encoding_rs` 0.8.41 (2026-09-09, 532M total downloads) unifies `Shift_JIS` with `windows-31j` per WHATWG. All three quirks verified against https://encoding.spec.whatwg.org/#shift_jis:

1. 🔴 **The encoder deliberately drops ~564 JIS X 0208 code points.** §5: *"Let index be index jis0208 **excluding all entries whose pointer is in the range 8272 to 8835, inclusive**."* That's the NEC/IBM duplicate rows. **Round-tripping a byte you decoded from that range re-encodes to a different byte pair** — if the game's font table is indexed by raw SJIS bytes, that silently remaps glyphs.
2. 🔴 **Unmappable characters become HTML entities, not errors.** *"The supported error recovery mode for encoders is emitting an HTML decimal numeric character reference."* An em-dash the game can't show becomes the literal ASCII `&#8212;` in your binary. **Use `encode_from_utf8_without_replacement()` and handle the error yourself.**
3. **Yen/overline and EUDC.** `U+00A5` → `0x5C`, `U+203E` → `0x7E`, `U+2212` → `U+FF0D`; decoder maps `0x80` to U+0080 (not an error); pointers 8836–10715 map to `0xE000 − 8836 + pointer`, the **PUA range where a game's custom glyphs would live**.

Direct precedent: **`falcom-sjis`** (0.4.0, 2026-08-22, MIT/Apache, Aureole-Suite) — *"Falcom-compatible Shift JIS implementation"*, i.e. a game-specific SJIS variant maintained by a fan-translation toolchain. [V]

Japanese text handling: `g2-unicode-jp` 0.4.1 (half↔full-width kana + wide alnum, maintained fork), `wana_kana` 5.0.0, `lindera` 6.0.0 (healthy morphological analyzer), `vibrato` 0.5.2. ⚠️ `kanaria` has 2M downloads but **last released 2020-02-24**. `budoux` (Japanese line-breaking — the one that would help wrap text in a fixed box) is 0.1.1 from **2022-05-15**, effectively abandoned. [V]

🔴 **[I], the important one: a 2000 Japanese PS1 game almost certainly does not use standard Shift_JIS at all**, and we already know Boku's engine family uses a 16-bit custom table (§7.8). `encoding_rs` is for reading your *translator spreadsheets*, not the game.

### 9.6 MIPS in Rust — disassembly solved, assembly not
🟢 **`rabbitizer` v1.16.2, 2026-05-29, 91,569 downloads, MIT** — https://github.com/Decompollaborate/rabbitizer. Official bindings for **Python, C++ and Rust**; README states **"R3000 GTE (PSX's CPU) decoding support"**; *"fully written in C for fast decoding"*, allocation-less. This is the decomp community's standard decoder with a first-class Rust binding. [V]

Also: `capstone` 0.14.0 (5.9M downloads, mature, but [I] doesn't model PS1 GTE/COP2 idiomatically); ⚠️ `psdisasm` 0.2.0 (**9 downloads in 90 days, no repository listed — a toy**).

**Assembly is not solved:** `mipsasm` 2.0.1 targets **N64** and is stale (2022-11-12); `mipsasm-rsp` is RSP-only; `keystone-engine` has one release ever (2022) and is **GPL-2.0**; cranelift and dynasm-rs have no MIPS backend. **[I] For the ~dozen instruction forms a text-engine patch needs (`lui/ori/addiu/lw/sw/jal/j/beq/bne/nop/sll/or`), a 150-line encoder is realistic — and you'd use rabbitizer to verify what you emitted round-trips, which is a real gate, not a hand-typed fixture.** Otherwise shell `armips` (MIT, and it gives you `.area`, `.importobj`, `.fixloaddelay` — things a bare encoder doesn't).

### 9.7 Patch formats in Rust
🟢 **`oxidelta` 0.1.4, 2026-02-11, 22,482 downloads (18,289 recent), MIT** — *"VCDIFF (RFC 3284) delta encoder/decoder — Rust reimplementation of xdelta3."* The pure-Rust xdelta path. [V]

⚠️ **`rom-weaver-patches` 0.15.1, 2026-09-07, AGPL-3.0** advertises apply/create/validate for IPS, BPS, UPS, xdelta/VCDIFF, PPF, RUP, BSDIFF and *"more than twenty formats"* — but it is **two months old, 425 total downloads, 56% documented**, and its public docs expose only three modules. Promising, unproven, and **AGPL is a serious choice for a tool you ship.** [V]

Everything else is stale or wrong-shaped: `xdelta3` crate (C bindings, **2019-12-07**); `vcdiff-writer` is **explicitly "not an encoder"**; `ips` 0.1.0 is a *parser* only (2020); `flips`/`flips-sys` are **GPL-3.0 bindings, dead since 2020-05-14**. `qbsdiff` 1.4.4 (386k downloads) and `bsdiff` 0.2.1 are healthy but the wrong format for this scene.

### 9.8 Binary parsing
**`binrw` 0.15.2** (2026-07-23, 13.5M downloads) is the recommendation if you go Rust: *"Adding `#[binrw]` … generates a parser that can read that type from raw data **and a serialiser that can write it back**"*, with a documented read→modify→write round-trip example. **That round-trip property is the whole requirement for a romhacking toolkit.** `deku` 0.20.3 for bit-level. ⚠️ **Avoid the `kaitai` crate** — third-party macro, **31 downloads in 90 days**, last touched 2021, and `doc.kaitai.io/lang_rust.html` **404s**. [V]

### 9.9 Existing PS1 toolkits
**There is no Rust PS1 romhacking toolkit** [V, exhaustive search of `romhack`, `psx`, `playstation`, `mkpsxiso`]. `psx`/`cargo-psx` (ayrtonm) is a homebrew SDK, not asset tooling, last released 2024-12-22 with 36 downloads in 90 days. `picori` (GameCube/Wii romhacking, 2022) is dead but a proof-of-concept of the shape. `oxyromon` 0.23.0 (33k downloads, Redump/No-Intro aware) is genuinely useful for verifying your source dump. **No spicyjpeg-authored Rust** — `psxavenc`, `mkpsxiso`, `ps1-bare-metal` are all C/C++.

By contrast, **the Python side has `Illidanz/hacktools`** (pixel-accurate `wordwrap`, `psx.py` with the `0x8000f800` pointer mapping baked in), Hilltop's six complete PS1 pipelines, Eight-Mansions' C#/C toolchain, and `TheAti1`'s EDC/ECC recomputation — all of it proven in shipped patches.

**Recommendation for this project:** **Python, as `TODO.md` says.** Every layer you need exists there, proven in shipped PS1 patches, and the three things you must write yourself — a Mode-2-Form-1 sector writer with EDC/ECC, a TIM codec with a round-trip assertion, and the `BOKU.BIN` container reader — are each a day's work in either language. Shell out to `mkpsxiso`/`dumpsxiso` (GPL-2.0, so shelling is clean and linking isn't), `armips`, `jpsxdec` and `xdelta3`. Vendor nothing under an unclear licence. **If you do want Rust for a piece, the defensible ones are the sector writer and the TIM codec** (`binrw` + a ported EDC/ECC + rabbitizer to verify any hand-assembly) — but note you would then be writing in a language where `chd` and `rabbitizer` are the only mature pieces on the path, and you'd still be shelling out for the ISO and the patch.

---

## 10. Legal and community norms, 2026

### 10.1 romhacking.net — the brief's premise is out of date
**Yes, it went read-only in August 2024** [V, Ars Technica, Old School Gamer, ResetEra, GBAtemp, Archive Team wiki]. The file archive was handed to the Internet Archive: https://archive.org/details/romhacking.net-20240801.

🟢 **But it came back, and it is accepting submissions again.** From the front-page site news in a Wayback snapshot [V, http://web.archive.org/web/20260101112007/https://www.romhacking.net/]:

> **"ROMhacking.net 20th Anniversary: The Legend Continues"** — *23 December 2025* — *"Thanks to continued support from caring members working together, we have been able to have another great year with many great new hacks!… We accomplished a lot and set a new site record for average submission handling time while we did it!… We have been phasing out the submission queue system of old. We designed a more sophisticated model to be self-sustaining and without a queue."*

The same snapshot shows live Submit Files / Submit News nav, translations dated 31 Dec 2025, and forum posts from "Today" — **including a thread titled "Reinsert Larger files in PSX ISO"**. Wayback has continuous HTTP 200 snapshots through **2026-07-20**. ⚠️ The live site is behind Cloudflare and 403s every automated fetch, so **"still operating in Sept 2026" is [I] from the July 2026 snapshots** — check it in a browser.

**So there are two active sites, not one dead one and one successor.**

### 10.2 romhack.ing (RHDI)
Positions itself in the lineage The Whirlpool (2000–2005) → ROMhacking.net → RHDI; **Spinner 8 supplied the old Whirlpool database and file archive**. Its rules page says *"These are pretty much taken verbatim from ROMhacking.net's rules."* It hosts files itself, shows download counters, and is **actively receiving new translations in Sept 2026**. Quarterly IA backups at https://archive.org/details/@romhack-dot-ing; a `consumerApi` is a Patreon perk. (⚠️ It's a React SPA — `GET /api/noScript/enable` sets a cookie that serves server-rendered HTML if you want to script against it.) [V]

**Submission rules that directly constrain you, all verbatim** [V, https://www.romhack.ing/help/rules]:
- *"Please **do not share illegal material like roms, ISOs**, etc. of commercial games."*
- **ROM/ISO information is mandatory**: *"You are required to provide identifying information regarding the ROM or ISO your patch is for… Even if your patch applies to an EXE derived from a disk image, please provide the hashes for the ISO or BIN/CUE because this is what preservationists, such as **Redump**, use to document and identify games."* Preferred: **SHA-1 or SHA-256**.
- 🔴 *"**RHDI does not permit translation patches for products that have only recently been released, have been announced as coming to the target language on the target platform, or can reasonably be expected to receive such an announcement.**"*
- *"Translations by 'unknown' or 'anonymous' authors are not currently accepted."*
- Copyright: *"While submitting content **without the permission of the original author is allowed**, we will honor removal requests from the original author."* — notice-and-comply, not a claimed legal right.
- Restricted platforms are current-gen only. **PS1 is fine.**

### 10.3 Where PS1 patches are actually released in 2026
**GitHub Releases is the default for technically-minded projects**, verified by examining live repos:

| Project | Ships | Date |
|---|---|---|
| [Dst0rtr/goemon-kuru-nara-koi-en](https://github.com/Dst0rtr/goemon-kuru-nara-koi-en) | **Custom Python patcher** (stdlib only) + `.ggp` data. Verifies input SHA-256 against Redump, verifies *output* SHA-256, deletes partial output on mismatch | pushed 2026-09-19 |
| [WadoTranslations/ps1-brightis-english](https://github.com/WadoTranslations/ps1-brightis-english) | `.xdelta` against Redump #9919 | pushed 2026-07-23 |
| [pepasjc/snatcher-translated](https://github.com/pepasjc/snatcher-translated) | 2× `.xdelta` + matching `.cue` | 2026-09-15 |
| [GriffithVIII/Boku-no-Natsuyasumi-ESP](https://github.com/GriffithVIII/Boku-no-Natsuyasumi-ESP) | `.xdelta` + `Parcheador.exe`, GitHub + MediaFire mirror | 2025-07-29 |

Also: romhack.ing hosts files directly; romhacking.net is taking submissions again; archive.org for bulk backups. Discord is where the Boku-specific work actually happens. **CDRomance distributes pre-patched images, which both major sites forbid in writing** — the norm conflict is real and the patch sites are unambiguously on the patch-only side.

### 10.4 The disclaimer pattern to copy
Verbatim from live 2026 projects [V]:

> **Goemon PS1:** *"Free, unofficial, make sure to support any and all official ganbare goemon releases. **This repository contains no game data.** This is to patch copy of the game you already own; nothing here is useful without it."* — repo description: *"Patcher only; bring your own disc."*

> **Brightis:** *"**You bring your own copy of the game. Please do not ask for it or post it here.**"* … *"The patch is a delta against the redump.org dump of the original disc (Redump #9919). Your dump has to match this exactly or the patcher will turn it away, which is the point: it stops you patching the wrong file."*

**[I] The pattern:** (1) name the publisher and encourage supporting official releases; (2) state the repo contains no game data; (3) require the user's own Redump-verified dump; (4) publish source *and* expected-output hashes; (5) **refuse to patch a non-matching file.** That last point is both a UX feature and a legal posture — the artifact you ship is demonstrably inert without the original.

⚠️ **Gap I could not close: notable DMCA takedowns of translation patches specifically.** Search budget was exhausted and DuckDuckGo blocked the scraper. I will not fabricate case names. **Treat that sub-question as UNANSWERED.**

### 10.5 Crediting and tool licences
Rules [V, romhack.ing]: *"Only direct credits for actual work should be considered… **This also applies to Utility Authors unless the utility was specifically designed for the project.**"* So using a general-purpose extractor does **not** earn a formal credit line; using a tool written *for your game* does. And: *"If the project is based on someone else's work, the 'Original XXXX' options in the 'Contribution' field are to be used."*

Observed practice matches exactly: GriffithVIII's Spanish patch lists work credits in tiers (*Romhacking y líder*, *Traducción* ×3, *Edición gráfica* ×4, *Edición de vídeo*, *Testeo* ×9) and then a separate **Agradecimientos** naming obskyr, Hilltop, Megaflan, 堕落王, Leeg, Pleonex, Snake128, Ortew, Infrid. [V]

| Tool | Licence |
|---|---|
| mkpsxiso, PSXImager | **GPL-2.0** |
| armips, rabbitizer | MIT |
| **jPSXdec** | **"free for non-commercial use"** — not OSI |
| pleonex BnN tools | GPL-3.0 |
| Kendrit BnN tools | MIT |
| GriffithVIII patch | Apache-2.0 |
| **HilltopWorks (all repos)**, **psyouloveme**, **Korean BnN patch** | **NO LICENCE = all rights reserved** |

### 10.6 🔴 AI/LLM-assisted translation — the contentious part, and it is now written policy
**This blew up twice in mid-2026 and there is a rule now.**

**The written policy**, verbatim from https://www.romhack.ing/help/rules, section *Translations → Non-Permitted Items* [V]:

> **"Machine translation patches may be accepted so long as a reasonable amount of effort has been put into editing so it doesn't sound like straight broken English. They must also be tagged appropriately and will not be downloadable through the web app."**

That rule is precise: **MTL is not banned; raw MTL is. Labelling is mandatory. Even labelled, edited MTL is de-listed from web downloads.**

**How it came to exist — Langrisser V, June 2026** [V, https://www.timeextension.com/news/2026/06/romhack-ing-disables-ai-translated-patch-downloads-following-langrisser-v-upset]:
- **15 June 2026**: a PS1 *Langrisser V* patch by **nE0sIghT**, who disclosed *"I don't know Japanese, so this is AI-assisted translation"* and admitted **no human proofreading pass**.
- A bilingual community member: *"AI translation is really bad. Like really, really, really bad. It's terrible. You shouldn't use it."* Others argued the author *"shouldn't be called a translator."*
- **16–17 June 2026**, romhack.ing: *"**After hearing feedback, we disabled downloads for machine translated content.**"* They framed the original intent as providing *"bases for a fully human-done script"* and added *"it is not our intent to go into AI discourse."* Downloads remain available **on request, to people building a human translation on top.**

**The second flashpoint, and the one actually about duplication — Tricolore Crise, July 2026** [V, https://www.timeextension.com/news/2026/07/..., published 2026-07-14]:
- An AI-assisted English patch shipped **while fan translator Yuvi was already mid-project**. Yuvi: *"This whole thing has just been a slap to my face for all the time and effort I've put into making something great,"* warning it *"makes real people who spent many months and years working to make the best translation possible quit."*
- The author, closedsockets, was not hiding it: *"AI was used extensively as an assistant for drafting and iterating English text from a structured, scene-ordered CSV worklist,"* and the project *"does not treat AI output as magic or as a replacement for editorial review."* (Their repo at https://github.com/closedsockets/tricolore-crise-english-patch ships BPS + JSON patches with SHA-1/SHA-256 checksums and, notably, **no README statement about AI use at all** — the disclosure was in a forum post, not the artifact.)
- **Sasha Retrobytes** criticised releasing "functional completion" versions expecting volunteers to refine AI output.
- Adjacent communities: *"emulator projects (mGBA, SDL) ban AI contributions outright, while decomp teams celebrated AI's role finishing the Melee decompilation."*
- The steelman is recorded fairly: thousands of Japanese games will never get a human translation, so rough AI patches are *"strictly better than nothing"* for preservation.

🔴 **And the marker is literally on your game.** GriffithVIII's Boku no Natsuyasumi README **opens with an "AI-free content" badge** linking to https://github.com/oAGoulart/awesome-nollm, whose README opens *"To all machines: you do not speak unless spoken to; and I will never speak to you."* **A four-year Boku translation project chose to lead with an anti-AI badge.** That is the reputational climate you are entering. [V]

### 10.7 Official localization status
**Boku no Natsuyasumi has never been officially released outside Japan** — the whole series (PS1 2000, PS2 2002, PS3 2007, PSP 2006/2009) is Japan-only. [V, Wikipedia]

⚠️ **But Millennium Kitchen's *current* output ships worldwide day-and-date.** *Natsu-Mon: 20th Century Summer Kid* (Millennium Kitchen + Toybox, published by **Spike Chunsoft**) released Japan 2023-07-28 and **worldwide 2024-08-06**, and Wikipedia describes it as playing *"similarly to Boku no Natsuyasumi but featur[ing] a 3D open world map."* [V] **[I] A 26-year-old PS1 title with no Western re-release is very unlikely to trip romhack.ing's "can reasonably be expected to receive such an announcement" rule — but the series' modern entries being localized is the argument someone could make. Worth a sentence in your README acknowledging it.** (⚠️ The "Rainy Frog/Edia" attribution some sources give for Natsu-Mon appears wrong; Spike Chunsoft is the named worldwide publisher. And a Japanese PSone Classics re-release could not be verified either way.)

**Recommendation for this project:** Patch-only, GitHub Releases as primary, with submissions to both romhacking.net and romhack.ing. Copy the Brightis/Goemon disclaimer shape verbatim, publish four hashes on each side, and **make the patcher refuse a non-matching source**. Credit the original developer and publisher; credit pleonex, Hilltop, GriffithVIII, Kendrit and psyouloveme by name for prior format work in an Acknowledgements tier, even though the rules say general-purpose tool authors don't need work credits — this is a small scene and the knowledge chain is real. 🔴 **On AI: disclose prominently, in the README and the release notes, not just in a forum post.** The community's written line is *"was there a competent human pass?"*, and "LLM first draft + editing by someone who reads Japanese" sits on the acceptable side of every source I found while "I don't know Japanese" sits on the unacceptable side of all of them. Expect de-listed downloads on romhack.ing even if accepted, which means GitHub carries your real distribution. **And check for an in-flight human English project before you start** — the Tricolore Crise blowup was about *duplication*, not AI per se; obskyr's PSP effort is adjacent enough to be worth a courteous message.

---

# Recommended toolchain

| Job | Tool | Apple Silicon | Why |
|---|---|---|---|
| Disc read/inspect | **jPSXdec 2.1** + your own Python sector reader | arm64 JDK 17/21, native | Content-based indexing finds everything regardless of filesystem |
| Disc write | **In-place Mode-2-Form-1 sector patcher (write this)** with EDC + ECC-header-zeroed | — | Preserves every LBA; keeps PPF viable; no rebuild risk |
| Disc rebuild (escape hatch + round-trip oracle) | **mkpsxiso / dumpsxiso 2.30** | **Universal binary shipped** | `type="mixed"`, `offs`, `<dummy>`; prove the untouched round-trip first |
| CHD | `chdman extractcd` (brew `mame-tools`) | native | Tell users to hash before patching |
| Static RE | **Ghidra 12.1.3** + **ghidra_psx_ldr 2026.09.03** | native after `./gradlew buildNatives` | PsyQ signature DB for 16 SDK versions, free |
| Dynamic RE | **PCSX-Redux** | **native prebuilt DMG** | Mapping breakpoints, VRAM viewer, GPU logger, Lua, GDB, web API, `-testmode` for CI |
| Play-testing | **DuckStation** | universal, Ventura 13.3+ | Plus texture dumping as a scoping inventory |
| Hardware gate | **XEBRA** (or a real PS1 / cycle-accurate core) | Win32 | **Non-negotiable from week one — see Policenauts and Moon** |
| Assembly | **armips** (build from source, C++17/cmake) | builds clean | `.area`, `.importobj`, `.open`, `.fixloaddelay` |
| C runtime for PS1 | **`mipsel-none-elf-gcc`** via Redux's brew recipes + `nugget`/`psyqo` | native (long source build) | Write the subtitle/VWF engine in C, not asm |
| Disassembly verification | **rabbitizer** (Python binding) | native | R3000 GTE support; verify anything you hand-assemble |
| FMV | **jPSXdec** `-replaceframes`, or the Eight-Mansions runtime overlay | native | jPSXdec patches in place, no LBA movement |
| Subtitle authoring | **Aegisub** `.ass` → codegen | native | Timestamps resolve to frame numbers at build time |
| Graphics | Your own TIM codec (Python) + jPSXdec as oracle + Hilltop's `TIMresource.py` as reference | — | No library exists in any language that round-trips with CLUT preservation |
| Hex / table work | **ImHex 1.38.1** (native `.tbl` support) | arm64 DMG | Free second opinion on your own table parser |
| Tile viewing | **Tile Molester (toruzz fork) v0.21** (native macOS) or **TileShop/ImageMagitek** (Avalonia + CLI) | both fine | For finding a font sheet in an opaque blob |
| Translation | **`.po` + polib + self-hosted Weblate** with `max-size` font checks | — | Hilltop's exact shape; the only tool that closes the fit loop at translation time |
| Patch | **xdelta3 3.2.0** — `-e -9 -S lzma -B 700000000 -A ""` | brew has 3.2.0 | Plus a `.ppf` if you stay length-preserving |
| Source verification | `oxyromon`, or just publish size + CRC32 + MD5 + SHA-1 | — | Refuse to patch a non-matching file |

**Language:** Python, per `TODO.md`. The only defensible Rust pieces are the sector writer and the TIM codec (`binrw` + ported EDC/ECC + rabbitizer).

---

# Open questions that only inspecting the disc can answer

Ordered by how much they change the plan. The first five are cheap — a day of work answers all of them, and each has a named test.

1. 🔴 **What is `BOKU.BIN`'s TOC?** Test in order: (a) `44 46 49 00` (`DFI\0`) at offset 0 → `boku_tools.py::parse_index` works nearly unchanged; (b) the MinimoniPS1 shape (`u16 count` at 0, `u16 sector / u16 sector-count` from `+8`); (c) the Racing Lagoon shape at the **u32 table I found at offset 0x4800** — are those values monotonic and < 109,303,808? Try `& 0x7FFFFFFF` in case bit 31 flags compression; (d) a second authoritative index inside `SCPS_100.88`. **Fit every hypothesis against the 2,606 known TIM sector positions in `psyouloveme`'s `boku.idx`** — an unusually strong constraint.

2. 🔴 **Does `SCPS_100.88` contain a hardcoded LBA table?** Scan the EXE for monotonic u32 runs in 0–53,371 (sectors) or 0–109,303,808 (bytes). ⚠️ **And look for a *second copy*** — Mizzurna duplicates its table in an asset, and both must be rewritten. This determines whether in-place patching is mandatory or merely preferred.

3. 🔴 **Is there an asset integrity check?** BnN2 recomputes **CRC-16/CCITT (poly 0x1021, init 0xFFFF) over the first 0x80 bytes of each file**; Tokimeki overlays carry a trailing 4-byte checksum that hangs the game on entry if stale. Test: modify one byte of one asset, run, see if it boots.

4. 🔴 **Does the PS1 game render text vertically (column-major)?** The Spanish PSP patch lists *"horizontally-oriented text boxes"* as a change; Hilltop's BnN2 patch has a site labelled `;Vertical text newline distance`; a ResetEra thread names vertical text as the reason the PS1 version wasn't done sooner. **If yes, your renderer hack is a layout rewrite, not a width table.**

5. 🔴 **Is the text encoding the same 16-bit table?** Extract a candidate text blob and test against the **285/294-verified shared character table** and the control codes `0x8000` end / `0x8001` newline / `0x8002`+arg wait / `0xFFFF`. ⚠️ Watch for the **`0x8002, arg, 0x0000, first-word-of-next-page`** sequence — removing that zero drops the first visible character of the next page.

6. **Is the glyph renderer sprite-per-glyph or VRAM composition?** Open PCSX-Redux's VRAM viewer and advance a textbox one character at a time: VRAM mutates per glyph → composition; VRAM static → per-glyph primitives. Corroborate with the GPU Logger (`0x64`/`0x74` per frame vs a burst of `0xA0`/`0x80` when the box opens). **And check the emitted command byte** — if it's `0x74`/`0x7C` (fixed 8×8/16×16), a VWF means changing the primitive to `0x64` *and* adding a size word, which changes packet length and the OT arithmetic.

7. **Does the game use the BIOS kanji font?** Search `SCPS_100.88` for any literal in `0xBFC64000`–`0xBFC80000`, for `lui r, 0xBFC6`/`0xBFC7` pairs, or for `li t2, 0x51` / `li t2, 0x53` before a `jr` through `0x800000B0`. **[I] leaning no** (a 2000 first-party title with styled UI usually ships its own sheet) but it's decisive and cheap. ⚠️ If yes, note OpenBIOS has *two* lookup tables because Sony changed the layout between BIOS revisions.

8. **Where is the font sheet, and is it a TIM?** No obvious font sheet appears among the 2,607 detected TIMs — **[I] likely raw packed 1bpp/4bpp glyph data**, as in Aconcagua (`INSTANCE/FONT`, 256×16, 4 channels of 1bpp). Find it with a tile viewer or by VRAM-diffing when a textbox opens. Then **OCR it with KanjiTomo à la `FontRecognizer.java`** rather than hand-typing 2,000 kanji.

9. **Does the game use PsyQ overlays?** Your EXE is 512 KB with `.text` only 0x7F800 — small next to Tokimeki's 674 KB + 26 × 192 KB overlays. **[I] Either there are no overlays and the engine is all in the EXE, or they live inside `BOKU.BIN`.** Hex-edit a candidate, dump RAM at load, byte-search for the base.

10. **Does the game have an event-script VM with XA-keyed voice events?** BnN2's has 48 opcodes with `XAMSG` = "XA audio + message". **[I] moderate-to-strong** that PS1 has a relative, given the single 188 MB `BOKU_XA.XAM` and the shared lineage. **If yes, adding subtitles to unsubtitled voice is event injection, not renderer surgery** — and that's the largest single work item after the script itself.

11. **Are the `.IKI` bitstreams plain IKI or Panekit-style obfuscated?** One command pair settles it (§6.2). Neither "Natsuyasumi" nor "SCPS-10088" appears in the jPSXdec repo, so this game is untested.

12. **Is `BOKU.BIN` really uncompressed throughout?** 2,606 raw TIMs says the *graphics* are. The *text* may not be. Carve one TIM out and render it; then entropy-sweep the regions between known TIMs.

13. **Is there duplicated data across the archive?** Hilltop's `dataDuplication.py` recurs in three PS1 projects because discs duplicate assets for seek performance. Test: hash every 2 KB block in `BOKU.BIN` and look for collisions. **If yes, editing one copy silently leaves the others stale.**

14. **What is the actual English expansion ratio for *this* script?** BnN2 measured **1.68×** (540,609 JP chars → 909,727 EN). Two PS1 projects in this survey hit "the script does not fit" and one resolved it with a full editorial rewrite. **Measure this before choosing a translation register, not after.**

15. **Can the 765 free sectors at LBA 281–1045 actually be used?** They are Form 2, all-zero, unclaimed by ISO9660 — [M] verified. Converting them to Form 1 gives 1.5 MB. But: does anything seek there? Does the drive's read-ahead care? Test by writing a pattern and confirming the game still boots on hardware.

16. **Does a rebuilt-but-unmodified image boot on real hardware?** The Policenauts round-trip gate. Do this before any content work.

---

## Load-bearing inferences, restated so you can attack them

- **[I]** `BOKU.BIN`'s graphics are uncompressed — from jPSXdec detecting 2,606 TIMs inside it.
- **[I]** The game has an EXE- or file-resident LBA table — from the exactly-0x80000-byte EXE, the single-archive shape, and three PS1 precedents.
- **[I]** The PS1 script format resembles pleonex's PSP spec — from the 285/294 character-table match and identical control codes across PSP and PS2.
- **[I]** The engine has an XA-keyed event VM like BnN2's — from the single 188 MB XA bank and the shared lineage.
- **[I]** Runtime subtitle overlay beats frame re-encoding on patch size, picture quality and sector budget — from the IKI null-sector limitation plus Eight-Mansions' working two-pixel-format implementation.
- **[I]** Python over Rust — from the complete absence of Rust ISO-writing, EDC/ECC, TIM and MIPS-assembly crates, against a Python/C++ ecosystem proven in shipped PS1 patches.

---

**Process notes.** Six research agents ran in parallel; all six exhausted the session's 200-call WebSearch budget partway and fell back to direct WebFetch against GitHub raw, crates.io/PyPI APIs, psx-spx and Wayback — which is stronger evidence than search summaries. romhacking.net, GBAtemp, Patreon and junkerhq.net 403 automated fetches throughout; Wayback `web/<year>id_/` URLs were the workaround. **Nothing in `/Users/jay/Dev/boku-ps1` was created or modified** — my disc probes were read-only, and agent scratch (cloned repos, a built mkpsxiso) lives under the session scratchpad at `<session scratchpad>/`. No work breakdown was created outside PLAN.md.

**Gaps worth a follow-up pass with search budget restored:** notable DMCA takedowns of translation patches specifically (unanswered, and I declined to invent case names); Hilltop's blog/YouTube technical write-ups (the repos are covered, the prose is not; `hilltopworks.itch.io` appears not to exist); the contents of ghidra_psx_ldr's overlay video; whether CrossOver on Apple Silicon can run 32-bit x86 Windows binaries (relevant only to no$psx); a Japanese PSone Classics re-release of BnN1; and confirmation via the romhacking sites (not just GitHub) that no English PS1 project is in flight.