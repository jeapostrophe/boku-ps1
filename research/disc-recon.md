# Disc recon — what the PS1 disc looks like (2026-09-19)

First-look findings from throwaway scripts. **Superseded where they overlap by
[boku-bin.md](boku-bin.md)** (the archive's directory and member map, PLAN `REC-01`). Every claim here was measured on the
dump below; anything marked *hypothesis* was not. Open questions are PLAN `REC-*`
rows, not this file.

## The dump

| | |
|---|---|
| Game | ぼくのなつやすみ / Boku no Natsuyasumi (SCEI / Millennium Kitchen, 2000), **SCPS-10088** |
| Source | `Boku no Natsuyasumi - Summer Holiday 20th Century (Japan).chd` — CHD v5. The `.chd` file's own SHA-1 is `5223868970ec3970d353b3447fb213ddfda541af`, but a CHD is not canonical (the same disc compresses differently per `chdman` version); `chdman info` reports internal `SHA1` `7ee18b72…` / `Data SHA1` `c3dc335e…`. The hash that identifies the dump is the extracted image's, below. |
| Extracted image | one track, `MODE2/2352`, 280,170 sectors, 658,959,840 bytes, no CD-DA |
| Image SHA-1 / MD5 | `5959bf7d9835d0a60aeb0143e2d0fc564bfea9fa` / `ee044864753c75ce0aea4ba777735fcd` (the one home for this value — cite it, don't copy it) — matches the Redump entry as reported in [related-projects.md](related-projects.md) §7(c); re-verify against redump.org directly (PLAN `ENV-02`) |

## Filesystem (30 entries)

| LBA | bytes | file | XA attr |
|---:|---:|---|---|
| 23 | 524,288 | `SCPS_100.88` — PS-X EXE, load `0x80010000`, text size `0x7f800`, entry `0x80049154`, SP `0x801ffff0` | Form 1 |
| 279 | 68 | `SYSTEM.CNF` — `BOOT = cdrom:\SCPS_100.88;1`, `TCB = 4`, `EVENT = 10`, `STACK = 801ffff0` | Form 1 |
| 1046 | 109,303,808 | `BOKU.BIN` — the whole game's data, 53,371 sectors | Form 1 |
| 54417 | 197,535,744 | `__STR/BOKU_XA.XAM` — XA audio (voices) | Form 2 |
| 150870… | — | `__STR/M*.IKI` ×25 — STR video (`M27`, `M28` are ~86 MB each) | Form 2 |

Sector 280 is the `__STR` directory. Sectors 281–1045 (765 sectors) belong to no file; the
practice survey measured them as zero-filled Form 2 filler (submode `0x20`), with 150 more at
the end of the disc — candidate expansion space if nothing seeks there (PLAN `PIPE-04`).

## `BOKU.BIN` has no header; its index is in the executable

`BOKU.BIN` starts with zeros (110 all-zero sectors overall). The executable carries a
table of ~300 **development-time path names** starting near file offset `0x808`:
`\_DATA\EV.BIN`, `\_DATA\NIKKI.BIN` and `NIKKI_W.BIN` (nikki = the picture diary),
`\_DATA\MI00.BIN`…`MI60.BIN`, `\_DATA\SBP*.TIM`, `\_DATA\M_FILES.BIN`, `H_FILES.BIN`,
`MUSIDATA.BIN`, `T_TITLE.BIN`, `T_MEMORY.BIN`, `T_CONFIG.BIN`, plus format strings
`\..\MAP\BIN\M_%s.BIN`, `\..\MDL\DATA\BIN\H_%02d_%02d.BIN`, `\..\EVT\BIN\EV%04d.BIN`.
*Hypothesis:* each name pairs with an offset/size record into `BOKU.BIN`, and
`M_FILES`/`H_FILES`/`EV` are sub-archives indexed by those format strings.

The first non-zero byte of `BOKU.BIN` is at `0x4800` (sector 9), and what starts there is the
engine family's **pack** format, measured: `u32 count = 4`, then `{u32 offset, u32 size}` pairs
`(0x24, 0x83a4) (0x83c8, 0x2ff0) (0xb3b8, 0x1c) (0xb3d4, 0x1280)` — each offset + size is the
next offset — and the first member is itself a pack of 8. So `BOKU.BIN` is a run of sector-positioned members, at least some of which are packs, with
no directory at its head. The directory is measured now: three parallel arrays in the executable (`g_cd_dir`), and no
second copy in the archive — see [boku-bin.md](boku-bin.md).

## Text is 16-bit glyph indices, not Shift-JIS — and the PSP table decodes it

The executable's only Shift-JIS is developer-facing debug text (`(PCload):ファイル(%s)が
ロードできません!!` sits beside `PCload:No file!` and a `C:\CD_IMAGE` path — PC dev-host
loading, not something a player sees; `イベントバッファオーバー`) and the standard mod-chip
warning. A Shift-JIS scan of
`BOKU.BIN` finds only noise. (The executable does hold *glyph-encoded* text, which this
Shift-JIS scan could not see — [boku-bin.md](boku-bin.md).)

Scanning `BOKU.BIN` for runs of little-endian `u16` in `1..0x4ff` ended by `0x8000`
(allowing `0x8001` and `0x8002 <param>` inside) finds **5,527 candidate lines / 54,600
glyphs**, 851 distinct ids (the scan's own ceiling is `0x4ff` = 1279, so it says nothing
about the highest id in use). Decoding with the PSP port's glyph table
(`font/table.txt` in pleonex/Boku-no-Natsuyasumi, decimal index → character) gives
clean Japanese:

```
0x118988   おじ「じゃあ、いただきまーす」
0x1192bc   おじ「ごちそうさまでした」
0x2ba4974  おじ「名前は？」
```

So: the control codes documented for the PSP port and the PS2 sequel (`0x8000` end,
`0x8001` newline, `0x8002` wait + u16) hold on PS1; the glyph order is shared with the
PSP port at least for kana and common kanji; speaker labels are inline text before
`「`. Not yet known: ids above 1023, which the 1024-entry PSP table cannot hold — **440 of the
5,527 lines use one, 127 distinct ids**, so this is ~8% of lines, not an oddity — the full control-code set, the table structure around the lines, and how
many of the 5,527 are duplicates (1,398 of them sit in the second MiB alone). Duplicates turned out to be most of it: **2,078 distinct strings**, 1,016 of them present
in more than one member ([boku-bin.md](boku-bin.md)).

## Textures

A 4-byte-aligned scan finds ~2,900 TIM-like headers in `BOKU.BIN` (140 sector-aligned);
jPSXdec's index in psyouloveme/boku1-reversing counts 2,606 TIMs there plus one in the
executable. Which of them carry Japanese text is PLAN `REC-08`.

## Trap worth remembering

macOS's filesystem is case-insensitive: extracting the game's `BOKU.BIN` next to a disc
image named `boku.bin` silently overwrites the image. The image is `disc/image.img`
for that reason.
