# Moving a member of `BOKU.BIN`

`PIPE-03`'s hard half. When a translated member no longer fits the sectors the disc gave
it, it has to be written somewhere else and everything that addresses it has to be
rewritten. This note is what "everything that addresses it" is, measured from the
executable's own instructions, and what the room costs.

`research/boku-bin.md` owns the archive's shape (`g_cd_dir`, the four `.SEC` sub-archives,
their record layouts and slot numbers) and `research/text-format.md` owns the bottom-up
rewrite list for a line that grows and the per-member slack statistics. Neither is
repeated here. `research/ps1-translation-practice.md` § 0 owns the filler measurement and
§ 1.4 the rule that the image's length may never change. This note owns one thing: **what
happens when step 6 of that rewrite list fires.**

## Two ways a member is addressed, and they cost differently

Disassembled from `disc/files/SCPS_100.88` with `llvm-mc -triple=mipsel -disassemble`
(`research/tooling-setup.md` § "armips" explains why that decoder and not Ghidra's).
`$16` below is `g_cd_dir` itself: `lui $16, 0x8002; addiu $16, $16, 0x4698` →
`0x80024698`, and `lw … 4($16)` / `lw … 8($16)` fetch the `lba[]` and `size[]` pointers.

### A `.SEC`-indexed member: `container_lba + record.sector`, computed every load

`map_select` (`0x80017450`), at `0x800174DC`:

```
800174DC  lw    $5, 4($16)      # $5 = g_cd_dir_lba
800174E0  lhu   $3, 12($18)     # the record's `sector`, zero-extended from 16 bits
800174E4  lw    $2, 572($5)     # lba[143]  -- M_FILES.BIN
800174E8  lw    $6, 8($18)      # the record's `size`
800174EC  addu  $2, $2, $3
800174F0  sw    $2, 576($5)     # lba[144] = lba[143] + sector
800174F8  lw    $2, 8($16)      # $2 = g_cd_dir_size
80017500  sw    $6, 576($2)     # size[144] = record.size
```

`event_select` (`0x80019D2C`) does the same at `0x80019D7C` with `lw $2, 116($4)` →
`sw $2, 120($4)`, i.e. slots 29 → 30, and reads its `size` with `lhu` because `EV.SEC`'s
is a `u16`. `model_select` (`0x80018620`) does it at `0x800186C0` with `172` → `176`,
slots 43 → 44. All three read `sector` with **`lhu`**.

So three facts, and they are the whole design:

1. A record's `sector` is **relative to the container's own `g_cd_dir` LBA**, not absolute.
2. It is **unsigned 16 bits**: a member may sit at most 65,535 sectors above that LBA, and
   **never below it** — there is no sign. `boku.reinsert._sec_edit` refuses a member the
   field cannot reach, before anything is written.
3. Nothing checks the container's extent. A record may point outside `BOKU.BIN` entirely.

The free space is *below* the archive, so rule 2 bites on every real relocation: the
member wants to go where its container's base cannot reach. The answer is to **rebase the
container** — lower `lba[container]` and add the same delta to every record's `sector`,
which leaves every unmoved member exactly where it is. One `u32` in the executable, plus
a rewrite of a `.SEC` member that is already being rewritten for the `size` fields.
`boku.relocate.sector_fields` emits every record, not only the moved one, for that reason.

**`size[container]` is deliberately left alone.** No reader in this toolchain uses it —
`map_select` takes only the LBA, and our own member map reads the `.SEC` sibling — and
`cd_dir_size` (`0x80012D64`) has 21 call sites whose indexes `research/boku-bin.md` does
not enumerate, whose callers "use it to bump-allocate the next buffer". After a rebase
neither the old value nor a recomputed one describes where the records sit, and a
recomputed one would span the arena *plus* every member below the container — tens of
thousands of sectors. The old value is the one the retail game ran with, so it stays.

### A top-level member: its two directory words, and nothing else

`g_cd_dir.lba[i]` is an **absolute disc LBA** — `cd_dir_pos` (`0x80012CFC`) hands it to
`CdIntToPos` and `cd_load_sync` reads `(size + 0x7FF) >> 11` sectors straight into the
destination with no fix-up (`research/boku-bin.md` § "Loader"). A top-level member may
therefore be placed at **any** sector of the disc; relocating one is exactly two `u32`
writes in `SCPS_100.88` (`boku.reinsert.directory_edits`).

That `\_DATA` files are never looked up through ISO 9660 — they cannot be, the retail disc
has no `\_DATA` — is measured in `research/boku-bin.md` § "The table is the dev image's
layout, and parts of it are stale", together with the two things that *are* opened by path
(`\__STR\BOKU_XA.XAM` via `xa_init`, and the movie player's conditional `CdSearchFile`).
Neither can reach a relocated member, because neither names one.

## Where the room is

The arena is the **765 zero-filled Form 2 filler sectors at LBA 281–1045**, between the
`\__STR` directory record and `BOKU.BIN`, measured in `research/ps1-translation-practice.md`
§ 0 along with the 150 at the end of the disc and 4 more at LBA 12–15.
`boku.relocate.unclaimed_runs` re-derives the two large runs from the image's own
filesystem rather than trusting the constants, and a test on the real dump holds the two
together.

Only the 281–1045 run is allocated from. The tail run is ~279,000 sectors past the
containers — far outside a `u16` record — and a top-level member placed there would fall
outside the contiguous span the archive is read back through, so it is counted as reserve
and left alone.

**Writing there converts the sector from Form 2 to Form 1**, because the game's loader
reads Form 1 user data and nothing else. `DiscWriter.write_data_sector` is the conversion;
it refuses any sector whose user bytes are not all zero, since that is the only thing
separating filler nobody owns from a channel of XA audio.

**There is no room inside `BOKU.BIN` itself.** Its members tile it exactly at both levels
(`research/boku-bin.md` § "The member map"), so an order-preserving sector-aligned layout
has zero slack to redistribute. The only space a growing member can be given is space that
was never in the archive.

## "Does anything seek there?" — answered, on Beetle PSX

`PLAN PIPE-04` and `research/ps1-translation-practice.md` § "Open questions" both made the
arena conditional on proving nothing seeks it. Measured 2026-09-20:

`M_H02001` — the map the first dialogue of the game is drawn over — was **relocated to LBA
281**, its 80 old sectors at LBA 32437 zeroed, the `M_FILES` container rebased from its own
LBA down to 281 (`lba[143]` only, see above), and the first line replaced with the marker
*"MOVED TO THE FILLER SECTORS"*. Cold-booted headless on Beetle PSX
(`tools/libretro/run_core.py`, the `boot-to-dialogue.press` schedule), the arrival scene
loads and the marker is drawn in the
dialogue band at frame 5850 — `work/pipe03b/beetle/first-dialogue.png`, against
`work/pipe03b/beetle-stock/first-dialogue-stock.png` from the same frame of the stock disc.

The old home being **zero** in the built image is what makes that a proof rather than a
coincidence: had the game still been reading LBA 32437 it would have loaded 160 KB of
zeros. Verified directly — `disc/image.img` has 138,391 non-zero bytes there and
`work/pipe03b/build/image.img` has 0, while LBA 281 goes the other way.

Two caveats this does **not** settle: it is one emulator, not hardware (a real drive's
read-ahead across the Form 2 → Form 1 boundary is untested), and it is one map. The
standing gate in `tests/test_real_reinsert.py` covers the byte-level half on every build.

## Does it fit?

Estimated 2026-09-20 from the samples' measured expansion — **2.63 English characters per
Japanese glyph** (`research/font-candidates.md` § 3, least squares through 80 sample pages)
at **5.85 px per character** in the 272-px dialogue band (`research/vwf-prototype.md`,
`boku.layout.DIALOGUE_BAND`), charging 7 characters of inline speaker label to every page
and keeping each message's page count, which the voice timing fixes:

| | |
|---|---|
| message-bearing members | 622 |
| members that outgrow their sectors | **174 (28 %)** |
| bytes of growth in all | 545,024 |
| worst member | `M_G16101`, **7,688 bytes** over its allocation (71 → 75 sectors) |
| sectors those members would **ask the arena for** | **10,860** |
| sectors they abandon | 10,627 |
| **net** new sectors the disc must find | **233** |
| arena | 765 |

So the disc has the room — 233 net against 765, with 532 to spare — **and the allocator as
built cannot use it.** `boku.relocate` gives a moved member a whole new allocation and
never re-uses the sectors a relocation vacates, so it asks for 10,860 and refuses at 765.
That policy is right for one member and wrong for 174, and closing the gap means a real
re-layout of `BOKU.BIN` rather than a bump allocator: `Capacity` reports `needed` and `net`
separately so the shortfall can be told apart from the disc's. Nothing in this unit is
wasted by that change — the addressing, the rebase and the sector writer are the same
either way.

(`PLAN PIPE-03`'s earlier estimate said 150 members, ~95 sectors and 6,028 bytes for
`M_G16101`. The difference is this model charging the label on every page and wrapping at
46 characters a line; the shape of the answer is the same and the row's numbers are the
older ones.)

## What still cannot move

* **An event block is still capped at `0x4000`** and a map pack's child 6 must still start
  below `0x6400` less the work area (`research/loading-and-memory.md` § "The short answer
  for the reinserter"). Relocation buys sectors, not RAM, and on the tightest map the two
  windows barely overlap: about 1,000 bytes separate `M_H06001`'s sector slack from its
  work-area head room, which is all the room there is in which it relocates *and* still
  loads. `M_G16101` wants more than its head room under the estimate above — it is one of
  the six maps `PLAN PIPE-03` already expects to need that note's § "Making room" too.
* **Code-file arrays** are not members and do not relocate this way; `research/text-format.md`
  has their `lui`/`addiu` patch.
* **The image's length**, which `research/ps1-translation-practice.md` § 1.4 says may never
  change and PPF structurally cannot grow. Everything here is in-place: sectors that
  already exist, converted from filler.
* **`NIKKI`**, whose selector rewrites slot 149 *itself* rather than a `.SEC` twin
  (`research/loading-and-memory.md`), and the overlays, which may only be extended at their
  end. Neither is text-bearing today; both would need their own reading before being moved.
