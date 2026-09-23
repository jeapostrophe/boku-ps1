# The memory-card save, and a corpus of generated saves (PLAN `ENV-06`)

How this game's save is laid out, what decides which ending plays, and how any lane reaches a
given day on either headless emulator in seconds. `boku/save.py` is this note's executable
form; `./make.sh save`, `./make.sh saves` and `./make.sh boot-save` are the commands. RAM
addresses are the running game's; symbol names are ours. *Measured* means read from the code
or run on an emulator on 2026-09-22; *inferred* is said where it applies.

Sources: Jay's first save (a DuckStation card, `…/duckstation/memcards/Boku no Natsuyasumi -
Summer Holiday 20th Century (Japan)_1.mcd`, copied into `work/`, never tracked), the
`TITLE.OVL` decompilation in `work/rec06/title.c`, and Beetle / PCSX-Redux boots.

## A save carries no script text — but a card is still never tracked

The body is progress state only ([integrity.md](integrity.md) checked it against every text
array). The file around the body is not clean, though: the header holds the **title** (the
game's own Shift-JIS strings from `TITLE.OVL`) and the **icon** (pixels copied out of the
executable), and the bytes `save_build` never initialises — `0x20C`–`0x27F`, and everything
after the body up to the block's written length — are whatever the mode arena held. So a card
is regenerated, never committed: `boku save` reads the title strings and the icon from the
contributor's own import, and writes into `work/`.

## The card

A raw 128 KB image (`.mcd` for DuckStation and PCSX-Redux, `.mcr` for Beetle — the same
bytes): 16 blocks of 8 KB, block 0 the directory in 128-byte frames, each ending in the XOR of
its other 127 bytes. Measured on Jay's card and reproduced by `boku.save.write_card` frame
for frame (`tests/test_save.py`):

| frame | content |
|---|---|
| 0 | `"MC"`, zeros, check byte |
| 1–15 | one per data block: `u32 state` (`0x51` first block of a file, `0xA0` free), `u32 size` (`0x2000`), `u16 next` (`0xFFFF`), file name from `+0x0A` |
| 16–35 | broken-sector list: `u32 0xFFFFFFFF`, `u32 0`, `u16 0xFFFF` — none broken |
| 36–62 | zero |
| 63 | "write test" frame — leftover bytes on Jay's card that fail their own check, zero on a card Beetle formats (`InputDevice_Memcard_Format` in beetle-psx-libretro's `mednafen/psx/frontio.c`) and on `write_card`'s. Nothing here reads it |

The file name is `"BISCPS-10088-"` (`TITLE.OVL` `0x80081400`) followed by the slot number
(`sprintf "%s%d"`). One save is one block.

## The save file

`save_build` (`0x8007B100`) lays the block out; `save_verify` (`0x8007A9D4`) checks it on load.

| offset | content |
|---|---|
| `0x000` | `"SC"`, `0x13` (three icon frames), `1` (blocks) |
| `0x004` | title, Shift-JIS, NUL-terminated, ≤ 64 bytes: `save_title_build` (`0x8007AEF4`) = part 0 + slot + part 1 + day + part 2, numbers in full-width digits with no leading zero (`g_save_title_parts` `0x80081444`, `g_save_title_digits` `0x8008141C`; the parts are listed in [text-outside-events.md](text-outside-events.md)) |
| `0x060` | icon CLUT, `0x20` bytes from `0x80028C64` |
| `0x080` | icon frames, `0x180` bytes from `0x80028C64 + *(u32 *)0x80028C58` (= `0x80028C90` on this disc) |
| `0x200` | slot summary, 12 bytes: `{u32 sum, u32 play counter, u8 day, u8 flag, 2 × pad}`; `sum` = byte sum of the 12 with `sum` zeroed (`save_summary_build` `0x8007B044`). `day` is `g_clock.day`, `flag` the byte at `0x80025914` (§ A finished game); the counter comes from a `TITLE.OVL` variable (`0x80081C18`), one less than the body's own play timer in Jay's save; `boku save` writes the body's. The file list ("1) 8月 1日 PLAYTIME …") is drawn from this; the timer counts 60 a second (a timer of 5 × 3600 × 60 lists as `5:00:00`, Beetle) |
| `0x280` | body: the 21 regions below end to end, **3,717 bytes**. Its first 8 bytes are overwritten with `{u32 sum, u32 size}`; `sum` = byte sum of all `size` bytes with `sum` zeroed. What `save_verify` does with them is [integrity.md](integrity.md)'s |

Neither sum covers the header, so the title and icon can change freely. `bytesum`
(`0x8007B014`) is a plain `u8` add into a `u32`.

## The body

`save_gather` (`0x8007B95C`) walks `g_save_regions` (`0x80081410` in `TITLE.OVL`, continuing
through the executable's data) — `{ptr, len, next}` records, copying each until one's `next`
is 0; that last record is not copied. Restoring (`0x8007B8E8`) copies them back.

| body offset | RAM | bytes | what (measured unless marked) |
|---:|---|---:|---|
| 0 | `0x80025908` | 20 | `+0` scratch the body's sum and size overwrite; `+8` u32 **play timer**; `+0xC` the **second-playthrough** byte, the summary's `flag` (§ A finished game) |
| 20 | `0x8003DC28` | 240 | *unknown*; with the next two, differs in most of its bytes between a new game's first dialogue and the end of Jay's day 1 — *inferred:* tables re-rolled each day (insect spawns?) |
| 260 | `0x8003DB38` | 240 | *unknown*, as above |
| 500 | `0x8003DD20` | 240 | *unknown*, as above |
| 740 | `0x8003DE18` | 360 | *unknown* |
| 1100 | `0x8003DB18` | 30 | *unknown* |
| 1130 | `0x8003E058` | 60 | *unknown*; changes during day 1 |
| 1190 | `0x8003E094` | 1 | *unknown* |
| 1191 | `0x8003D278` | 5 | *unknown* |
| 1196 | `0x8003E0B0` | 18 | *unknown* |
| 1214 | `0x8003DF90` | 180 | overlaps `g_insect_book_state` (`0x8003DF92 + 3·id`, [text-outside-events.md](text-outside-events.md)) — *inferred* to be that table |
| 1394 | `0x80035E48` | 256 | **`g_flags`** ([event-scripts.md](event-scripts.md) § Flags) — including the ★ bytes 237/238 and the ending's `g_flags[250]` |
| 1650 | `0x80028FA0` | 16 | **`g_clock`**: `{u8 day, u8 hour, u8 minute, u8, char *map_name, s16 meal[4]}` |
| 1666 | `0x80028FD0` | 4 | a u32 bit set: PROG 44 (`0x80032E50`) sets bit `n − 1` (21 distinct `n` in the scripts; `ending_prepare` sets bit 22) — *meaning unknown* |
| 1670 | `0x80028FD4` | 16 | *unknown* |
| 1686 | `0x80045A10` | 120 | **Boku's cage** — what bug sumo lists: 10 × 12-byte records {u8 type (insect id), size, lost today, size class, catch number, catch day, wins, losses; s32 stat}, field names per boku1-reversing's HUD map (`bokuBugArray`), not decoded here. *Measured* only that sumo reads it: a record poked here changes what the cage does (it hung with guessed fields), one poked at `0x80046F28` does not show |
| 1806 | `0x80046130` | 31 | `g_diary_pages[day]` ([text-outside-events.md](text-outside-events.md) § The picture diary) |
| 1837 | `0x80046F28` | 1800 | the insect **box** (mode 10, `HHON`'s "cage on the desk" — [text-outside-events.md](text-outside-events.md)): 12-byte slots, byte 0 = insect id, 99 = empty; 150 of them *inferred* from the length; the record is `0x80045A10`'s layout (boku1-reversing), not decoded here. Not the cage bug sumo lists |
| 3637 | `0x80047EC0` | 8 | *unknown* |
| 3645 | `0x80046F18` | 12 | *unknown* |
| 3657 | `0x800476C0` | 60 | *unknown* |

**The save holds a RAM pointer**: `g_clock.map_name` is saved and restored as `0x80026C00`
(the current map's name buffer) — what that means for a patch is [integrity.md](integrity.md)'s.

Local flags (`g_lflags` `0x80035C48`, the "has this scene played" bytes) are **not** saved.

## Loading a save always starts the next morning

Measured on Beetle with Jay's card (saved August 1 at 20:12) and three generated ones: after
"load finished" the game plays the dawn cut-in, the rooster and Boku waking, and by the radio
exercises in front of the house `g_clock` reads **the saved day + 1, 07:00**; breakfast
follows with that day's conversation (day 2: the morning-glory question; day 3: the fishing
rod and the corn harvest; day 31: the uncle's sore back). The game only saves at bedtime, so a
save's resolution is a morning — reaching later in a day is a matter of playing on from the
morning's save state.

## A finished game

After the ending (`ENDOTI`) the game asks which file to save to, and writes a save whose
`g_clock.day` — so the summary's `day` — is **31** (measured: the game's own clear save,
written on Beetle after a generated day-31 morning was played through, reads August 31 09:04,
`g_flags[250]` = its epilogue). That day is the whole marker:

* The file lists show a finished file's date **in red**. **Continue** loads it and goes back
  to the title — a finished summer cannot be continued (Beetle).
* **Summer Memories** (the title menu's third item) lists the finished files and opens the
  album for the one chosen: picture diary, insect specimens and cage, kites, items, and
  **エンディング**, which replays `MOVIE 24` and the epilogue of the file's `g_flags[250]`
  (Beetle, a generated finished save with `g_flags[250]` = 2: mode `0x10` with `OTI02`).
  With no finished file it says none has finished the game.
* **New Game** with a finished file on the card sets `0x80025914` = 1 (Beetle): the card
  scan `mc_summary_scan` (`TITLE.OVL` `0x8007B65C`) reads each summary's day and, for one
  ≥ 31 (`sltiu v0, day, 0x1F`), stores 1 there. The byte is saved (body region 0, the
  summary's `flag`), and `PROG 14` copies it into the scripts' result register, where two
  events branch on it — `E0404` and `E1503`: the **second playthrough**. So a finished save
  on a card changes every new game started from that card, and `boku save --cards` never
  puts one beside an unfinished save.

`boku save --finished` writes one (day 31, and `g_flags[250]` from the stars, as
`ending_pick` would have left it); `tests/test_save.py` reads the threshold out of
`mc_summary_scan` and checks the generated epilogue against the game's own clear save.

## Which ending plays

Day 31's `E3182` (`day == 31 & flag[251] == 12`, `flag[251]` being day 31's running scene
counter) plays `MOVIE 24`; after it, `movie_queue_play` calls `ending_prepare` (`0x8002E8EC`)
and switches to mode `0x10`, `ENDOTI.OVL`. Measured from the code:

* **The fifteen ★ are bits of `g_flags[237]` (bits 0–7) and `g_flags[238]` (bits 8–15).**
  `star_set(n)` (`0x800336B8`) ORs bit n in; it is PROG 57, called by 13 events with n = 2–6
  and 8–15 (`E0384` 2, `E0786` 3, `E2303` 4, `E0445` 5, `E1406` 6, `E1754` 8, `E2306` 9,
  `E0710` 10, `E0505` 11, `E2505` 12, `E2207` 13, `E3042` 14, `E2605` 15). `ending_prepare`
  adds bit 1 if `g_flags[75] == 9` (*inferred:* the nine days of morning-glory blooms) and bit
  7 if `g_flags[117] != 0` (*inferred:* all eight kites). Bit 0 is never set.
* **`ending_pick` (`0x8002E848`)** counts the set bits of `flag[237] | flag[238] << 8` and
  writes the epilogue to `g_flags[250]`: **13–15 → 3, 10–12 → 1, 7–9 → 0, 4–6 → 2, 0–3 → 4**.
* `ENDOTI`'s init (`0x80079AF8`) reads `g_flags[250]` = n and loads file `0x9A + n` and XA
  clip `0x29 + n` — the still `OTI0n` and its narration.

The bands are exactly the 0–3 / 4–6 / 7–9 / 10–12 / 13–15 of [xneo] quoted in
`translation/voice-only.md`; matching each band to its epilogue by that source (*inferred*,
not watched): `OTI04` the valley drowned by a dam, `OTI02` the programmer, `OTI00` the
sisters' marriages, `OTI01` the potter, `OTI03` the novelist.

## The generator and the corpus

`./make.sh save --base BASE --out CARD [--day N | --finished] [--stars K | --stars-mask M]
[--flag N=V] [--poke ADDR=HEX] [--slot S]` writes one card. `BASE` is a card (its save in
`--slot`) or a 2 MB main-RAM dump; `--day N` makes the save the evening before (`g_clock` =
N − 1, 20:00), so it wakes on August N; `--finished` makes it a finished game (§ A finished
game); `--stars K` sets star bits 1…K. Every byte it writes is summed as the game sums it;
`tests/test_save.py` rebuilds a save the game wrote from its parsed body and gets the game's
own bytes back for the header, title, icon and body.

`./make.sh saves` writes the **corpus** into `work/saves/corpus/` (with `INDEX.tsv`), one
save per card in slot 1: `day02` … `day31` — every morning from August 2 —,
`ending-oti{4,2,0,1,3}-{00,05,08,11,15}stars`, the morning of August 31 with a star count
inside each of `ending_pick`'s five bands, and `finished-oti…` the same five as finished
games. The ending and finished saves' play timers read the star count in hours. Its base
is a **new game's RAM** at the first dialogue (`work/saves/newgame.ram`, dumped once on
Beetle from your own import by `run_core.py --ram-out`).

What that base means, and it is the limit of the corpus: **the cards are calendar-correct and
story-naive.** Day-keyed scenes (the 362 events whose id names their day, the breakfasts and
dinners) play on their morning; scenes gated on flags an earlier day would have set do not,
until the lane sets those flags with `--flag` (the conditions are in
[`data/scenes.tsv`](data/scenes.tsv)). No flag set of a real playthrough by day N has been
decoded — Jay's day-1 card differs from the new-game base in flags 0, 2, 3, 213 and the diary
page for day 1, which is all one played day showed. The ending cards set the stars that
decide the epilogue, and August 31 is the ending: every scene that day is an automatic link
in `flag[251]`'s chain (`E3171`–`E3182`, 1 → 12), so from the morning the ending comes by
itself. Measured on Beetle with `ending-oti3-15stars`, ○ pressed every 30 frames: loaded at
frame 4300, the chain began 6932, `MOVIE 24` at 13853, `ENDOTI` (`OTI03`) at 30651, the
save-your-file screen at 33608. There is no evening on August 31 to save at, so the morning
is the latest a save can start before the ending.

## Playing a generated save in DuckStation

`./make.sh duckstation-cards` writes the corpus packed for a player into
`work/saves/duckstation/`, from your own import like every save here, with an `INDEX.tsv`
naming each card's slots:

| card | slots |
|---|---|
| `boku-mornings-aug02-aug16.mcd` | 1–15: wake on August 2 … 16 |
| `boku-mornings-aug17-aug31.mcd` | 1–15: wake on August 17 … 31 |
| `boku-endings-by-stars.mcd` | 1–5: the morning of August 31 with 0, 5, 8, 11, 15 stars — one per epilogue band; PLAYTIME reads the stars in hours |
| `boku-finished-game.mcd` | 1–5: the same five as finished games — Summer Memories, and its "ending" replays that band's epilogue |

The file list shows the day a save was **made**, the evening before the morning it wakes
on (`8月16日` wakes on August 17), two files at a time; ↓ walks it.

The game reads **memory card 1 only** — every `MemCard*` call in `TITLE.OVL` passes channel 0
— so a card in slot 2 is never seen. The least fiddly way, which never touches the card you
play on: in DuckStation, right-click the game → **Properties** → **Memory Cards** → Memory
Card 1: **Shared Between All Games**, and **Browse** the shared-card path to one of these
files. That override is this game's only (its own ini under DuckStation's `gamesettings/`);
set Memory Card 1 back to **Use Global Setting** to return to your own card. Change the
setting with the game closed, so the card the game boots with is the one you chose. A game saved
while a test card is in writes to that test card — `./make.sh duckstation-cards` rewrites all
four. (DuckStation keeps a path under its `memcards` folder relative to it —
`MemoryCardSettingsWidget`, which the per-game Properties page reuses.)

## Loading a card headlessly

**Beetle PSX** (where a result is confirmed): memory card 1 is the core's `SAVE_RAM`
(`use_mednafen_memcard0_method` = `libretro`, the default; read in beetle-psx-libretro's
`libretro.c` `retro_get_memory_data`). `run_core.py --memcard CARD` copies the card in after
`retro_load_game`, before the first frame, and never writes the file (it refuses `--state-in`
beside it: a Beetle state carries its own card); `--memcard-out` writes
the card back after the run, which is how a save made in play is captured.

```sh
./make.sh boot-save work/saves/corpus/day05.mcd     # -> work/boot-save/day05/morning.{png,state,ram}
uv run python tools/libretro/run_core.py disc/image.cue --work work/x \
    --state-in work/boot-save/day05/morning.state --frames 600 --shot 600:later
```

`boot-save` drives the title menu with `tools/libretro/boot-to-save.press` (continue → slot 1
→ yes; the file carries each frame's meaning), stops at frame 6000 (the radio exercises), and
**fails (exit 11) unless `g_clock` reads the save's day + 1** — at the title the clock reads
August 1 14:00, which is what a missed press or a refused save leaves. Any other
`run_core.py` option passes through (`--image build/days/image.cue`, `--frames`, `--shot`,
`--state-out`). A boot is ~15–20 s; resuming the morning state is under a second.

**PCSX-Redux**: `-memcard1 PATH` (read in pcsx-redux `src/main/main.cc`; it overrides the
`Mcd1` setting). Redux **writes the card back** when the game saves, so give it a copy. Its
menu timings are its own (GPU vsyncs): measured with a generated day-25 card,

```sh
cp work/saves/corpus/day25.mcd work/redux-card.mcd
BOKU_WORK=$PWD/work/redux-save BOKU_FRAMES=5000 BOKU_SHOT_AT=4800 \
BOKU_INPUT="2430:START:5;2590:DOWN:5;2660:CIRCLE:5;3050:CIRCLE:5;3150:CIRCLE:5" \
    tools/redux/run-on-image.sh disc/image.cue drive.lua -memcard1 $PWD/work/redux-card.mcd
```

— file list at ~3000, "load finished" ~3600, radio exercises ~4800 (the file list read
"8月24日", so the card loaded; the clock was not read on Redux).

## Reaching the scenes other lanes asked for

| target | how | status |
|---|---|---|
| title screen | cold boot, frame ~3200 on Beetle (`boot-to-dialogue.press`), ~2400 on Redux | measured |
| title menu | START at 3300 → menu by ~3600: new game, **continue**, summer memories, **settings** (DOWN ×3) | menu measured; settings screen not opened |
| memory-card screens | continue with any card: "checking the memory card" ~3950, file list ~4100, "load this file?" after ○, "load finished" | measured. With no `--memcard` Beetle's card is formatted and empty (`InputDevice_Memcard_Format`), so the no-card and unformatted-card messages need a card made that way on purpose — not shot |
| START in play | after breakfast, START shows the controls help. Day 3: resume `boot-save`'s `morning.state`, breakfast ends ~6000 frames later | measured |
| the insect box | in play, **△ opens the desk** (the "sub screen": net, cage, items, fishing gear, kites); the cage is the green box. From the item cursor, RIGHT ×2 reaches the net | desk measured; the cursor path to the cage not |
| summer memories (the title menu's third item) | a finished save (§ A finished game): `boku-finished-game.mcd` or `./make.sh save --finished`. START, DOWN ×2, ○, ○ on the file, ○ on "yes"; the album is up ~1300 frames after the file is chosen | measured on both emulators (`tools/vwf/shoot-menus.sh`), and Beetle 2026-09-23 |
| the ending | `ending-oti*` (a morning of August 31; ~9,500 frames of ○ to `MOVIE 24`, § The generator and the corpus), or at once from a finished save's Summer Memories → エンディング (DOWN ×4, ○) | measured on Beetle 2026-09-23 |
| bug sumo | **no card needed, PCSX-Redux**: `tools/redux/to-sumo.lua` points the intro's return to the field at `E4025` with that event's flags met (the script's header lists the pokes), and the event enters mode 7 itself ~300 vsyncs later; the script saves the state `sumo-desk`. It reaches the **desk** (insect notebook and Boku's cage, ○ opens it), empty on a new game. A **bout** needs a beetle in Boku's cage (`0x80045A10`, the table above), and a record poked by hand (type 30, the rhinoceros beetle, with guessed fields) hung the game when the cage opened. Beetle PSX has no breakpoint to redirect at, so the same route there needs `--poke` timed into the intro movie | desk measured; bout not reached |
| the well on the shortcut path | the story bible puts "the secret shortcut" on days 17–18 (`E1754`); a `day19`-or-later card, with its flags set by `--flag` from `scenes.tsv` | not reached |
| any map, day 1 | during a new game's opening movie, poke a three-character map base into `g_movie_return_map` (`0x80036588`): the movie ends in that map, its variant chosen by the clock as usual. `run_core.py --poke 5300:0x80036588=43313500` with `boot-to-dialogue.press` is `C15`, the path to the beach, by frame ~6000 ([texture-recipes.md](texture-recipes.md) § `M_C15`) | measured for `C15` |
| the uncle's evening call (`exe@80029920`, system event 8) | any day's card with `./make.sh boot-save CARD`, then `--poke 6100:0x80019E08=08000224`: the chooser `0x80019DEC` gets `addiu v0, zero, 8` instead of `jal 0x8001933C`, so the event fires as soon as the morning's script ends (~frame 7500 on day 5), the kitchen and both pages follow; shots every 40 frames from 7300 | measured on Beetle 2026-09-23 |
| bedtime, end of day 1 | only by playing day 1 from a new game (`boot-to-dialogue.press`). Poking `g_clock.hour` does not skip ahead: set to 20:50 after breakfast on day 3 (`run_core.py --poke`), 50 s later it read 17:00 and the map was still its morning variant — the clock is driven from elsewhere | not reached |

## Open

* The unnamed regions above, and a real playthrough's flag set by day — what would make the
  corpus story-correct. Not needed for reaching a day.
* `0x80028FD0`'s bits; what `E0404` and `E1503` do differently on a second playthrough.
* Which in-game clock drives `g_clock` (the poke result above).
