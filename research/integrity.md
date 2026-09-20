# Does the game check its data? (PLAN `REC-07`)

Static analysis of `SCPS_100.88` and the seven `.OVL` members, on the dump identified in
[disc-recon.md](disc-recon.md). RAM addresses (file offset = RAM − `0x8000F800`; overlays at
`0x80079A08`); symbol names are ours and are listed in
[`symbols/loading.symbols.tsv`](symbols/loading.symbols.tsv). Everything is *measured from code*
unless marked *hypothesis*; nothing here was run. Scratch: `work/rec06/` (`scan_crc.py`,
`savelist.py`; Ghidra decompilation dumps `exe.c`, `title.c`, …).

## Verdict

**Nothing on the disc is verified.** A patch recomputes no checksum and disables nothing:

| what | checked? | a patch must |
|---|---|---|
| files read from `BOKU.BIN` (every `file_load` / `file_load_async`) | no | nothing |
| code overlays | no | nothing |
| the executable itself | no | nothing |
| the disc / console (mod-chip routine) | yes — drive behaviour only, never file contents | nothing; see below for where it can fire |
| memory-card save body | yes — additive byte sum, computed when saving | nothing, unless it changes *what is saved* (it should not) |
| memory-card save title | not checksummed | may change it freely (Shift-JIS, ≤ 64 bytes) |

So a crash after reinsertion is a reinsertion bug (or one of the buffer limits in
[loading-and-memory.md](loading-and-memory.md)), not tamper detection.

## Loaded data: no check anywhere on the path

* `cd_load_sync` (`0x800127C8`) is `DsRead` + `DsReadSync` retried until the *drive* reports
  success, and `file_load_async`'s state machine (`0x800128AC`) is the same in three states.
  Neither touches the buffer. (The PsyQ signature pass names these `Ds*`, i.e. `libds`, where
  [boku-bin.md](boku-bin.md) inferred `Cd*` from argument shape.)
* All **85 call sites** (77 `file_load` + 8 `file_load_async`, EXE and overlays — the 40 in
  boku-bin.md were the EXE's alone) hand the buffer straight to a parser, a TIM uploader or a
  jump. No site computes anything over the bytes first.
* **No CRC exists in any code file.** No CRC-16 (`0x1021`, `0x8408`, `0xA001`, `0x8005`) or
  CRC-32 (`0xEDB88320`, `0x04C11DB7`) table, as `u16` or `u32`, in the EXE or `BOKU.BIN`; no such
  polynomial as an instruction immediate in the EXE or any overlay. There is no analogue of the
  PS2 sequel's side table: with no CRC code there is nothing to consume one, and
  `g_cd_dir` has no per-file field beyond LBA, size and name (its fourth pointer is `NULL` —
  loading-and-memory.md § "`g_cd_dir`'s two unknown words").
* A pattern search of the decompilation for accumulate-in-a-loop functions (`x += *p`,
  `x ^= …`, shift-and-xor) finds one real checksum in game code — the save file's, below — plus
  `libcard`'s own directory-frame XOR inside the PsyQ library. *Limit of this search:* Ghidra
  recovered 1,622 functions in the EXE after prologue seeding; code reached only through
  pointers and lacking a stack frame could be missed. The 85 load sites were all read, so a
  check would have to be far from any load to have escaped.
* Overlays are loaded to `g_overlay_base` and entered by `jal` to link-time addresses inside
  them (`BUMPER` `0x80079F78`, `TITLE` `0x8007F818`, `TAKO` `0x8007A100`, `MUSI` `0x8007BE60`,
  `HHON` `0x80079B40`, `ENDOTI` `0x80079AF8`). No size, magic or sum is tested. (A different
  constraint follows: code inside an overlay cannot move — loading-and-memory.md.)
* `EVVER.BIN` is not a version check. It is the map-variant selector (`map_variant_name`
  `0x80030CD0`).

## The mod-chip routine

The Shift-JIS warning at `0x800480C4` and its English twin at `0x80048070`
("SOFTWARE TERMINATED / CONSOLE MAY HAVE BEEN MODIFIED / CALL 1-888-780-7690") belong to the
stock SCE library check, linked between `crt0` and the C library:

* `antimod_region` (`0x80049210`) reads the BIOS region letter at `0xBFC7FF52`: `'E'` sets the
  state to 0 — **check skipped entirely**; `'A'` selects the English text; anything else
  (including `'J'`) selects the Japanese text.
* `antimod_run` (`0x8004927C`) is a 20-state machine that talks to the CD controller registers
  directly (`antimod_cd_send` `0x80049D88`, `antimod_cd_poll` `0x80049BB4`), using the command
  table `g_antimod_cmds` (`0x80068B00`): `Getstat`, `GetTN`, `GetTD`, `Setloc`, `SeekP`,
  `Setmode`, `Init`, `Mute`, `Play`, `Test 0x19` (sub-functions from the parameter byte: `04`
  start and `05` read the SCEx counters), `Pause`, `ReadTOC`, `GetID`. In order: `GetTN`;
  `Init`; `GetTD` of the lead-out (or of track 2 when the disc has more than one track), i.e.
  the end of the data track; compute the position **half-way to it**; `ReadTOC` (an "unknown
  command" error from an old drive is tolerated); `GetID`; `Setloc` there; `Setmode 1`;
  `SeekP`; `Mute`; `Play`; `Test 04`; wait 200 vblanks; `Test 05`; `Pause`.
* It fails — `antimod_fail` (`0x80049E78`): stop callbacks and sound, clear the screen, print
  the message through `Krom2RawAdd` (`antimod_print` `0x80049FE4`), `exit()` — in two cases:
  `GetID` reports an error after `ReadTOC`, or the SCEx counter read in mid-disc is non-zero
  (a chip injecting the licence string where a real disc has none).
* It is called **once**, blocking, from `sys_init` (`0x80011E80`) before anything is loaded.
  Single caller each for `antimod_region` and `antimod_run`.

**It reads no file and no part of the EXE.** Its only disc-derived inputs are the TOC values
(track count, last track time) used to pick the seek target. A patched image with the same
track layout presents the same inputs; an image that grew would move the target, still inside
the data track.

Where it can fire, for whoever debugs `TXT-04`: on real hardware with an old non-stealth
mod-chip (true of the unpatched disc too), and on an emulator whose `GetID` / `Test 04/05`
emulation answers wrongly. *Not measured:* whether Beetle PSX passes it — but the unpatched
game has to pass the same routine, so if the original boots there, so does a patch. If it ever
has to go, clearing the state is enough: `antimod_run` returns immediately when
`g_antimod_state` (`0x80068B58`) is 0, which is exactly what a European BIOS does.

`Krom2RawAdd`'s two callers are therefore both failure screens — this one and
`sjis_panic_print` ("event buffer over", [font.md](font.md)). The guess in font.md that the
second caller was the memory-card title is wrong; the title never goes through the BIOS font
in the game's own code.

## Memory-card saves

All card I/O is in `TITLE.OVL` through `libmcrd` (`MemCardReadFile` / `MemCardWriteFile` /
`MemCardCreateFile` / `MemCardGetDirentry` / `MemCardFormat`); the EXE's only card call is
`MemCardStart`. File name: `BISCPS-10088-` + slot number (`sprintf "%s%d"`).

`save_build` (`0x8007B100`) writes, into the mode arena:

| offset | content |
|---|---|
| `0x000` | `"SC"`, `0x13` (3 icon frames), `1` block |
| `0x004` | title, Shift-JIS, built by `save_title_build` (`0x8007AEF4`) — see [text-outside-events.md](text-outside-events.md) |
| `0x060` | icon CLUT (0x20) and `0x080` three icon frames (0x180), copied from `0x80028C64` |
| `0x200` | 12-byte slot summary `{u32 sum, u32 play counter, u8 day, u8 flag, …}`, `sum` = `bytesum` of the 12 bytes with `sum` zeroed (`save_summary_build` `0x8007B044`) |
| `0x280` | body: `{u32 sum, u32 size, data[size]}` |

The body is gathered by `save_gather` (`0x8007B95C`) from a linked list of `{ptr, len, next}`
records starting at `g_save_regions` (`0x80081410`, continuing through the EXE's data): **21
regions, 3,717 bytes** of game state. `sum` is `bytesum` (`0x8007B014`, a plain `u8` add) over
`size` bytes from the start of the body with the `sum` field zeroed. `save_verify`
(`0x8007A9D4`) requires `size` to equal the list's total and `sum` to match; otherwise it
re-reads, and after four tries reports a load failure.

Consequences:

* The header — title, icon — is **outside** both sums. Changing the title strings costs nothing.
* **No saved region overlaps a text array** (checked against
  [`data/text-arrays.tsv`](data/text-arrays.tsv): the nearest are `0x8003D278`+5, which ends
  before `exe@8003D2E0`, and `0x80046130`+31, which ends before `exe@80046158`). Saves carry
  no text, so Japanese and patched saves are interchangeable as far as text goes.
* The `size` test means a patch must not add, remove or resize a saved region — relocating a
  *saved* variable would need its list record updated, and would still load old saves, since
  the file stores values, not addresses. *Hypothesis, not checked:* none of the 21 regions
  holds a RAM pointer that a relocation could invalidate; they are small counters, flag arrays
  and the 31-byte diary page list.
