# Bug sumo: the cage, the fighters, and reaching a bout (PLAN `ENV-08`)

What an insect record is, how bug sumo (mode 7, `MUSI.OVL`) turns one into a fighter, and how
a generated save reaches a bout. `boku/sumo.py` is this note's executable form; `boku save
--bug` and `./make.sh sumo-bout` are the commands. *Measured* means run on Beetle on
2026-09-23; *read* means taken from the code (the `MUSI.OVL` decompilation in `work/rec06/`);
*inferred* is said where it applies. psyouloveme/boku1-reversing's RAM map (`bokuBugArray`)
was the lead for the cage's address; nothing here is copied from it.

## The insect record

Twelve bytes, the same layout in every table of insects: Boku's **cage** (`0x80045A10`, 10
records, the one bug sumo lists — [save-format.md](save-format.md) § The body), the insect
**box** on the desk (`0x80046F28`), the bug in Boku's hand at the desk (`0x8003E098`), and the
three boys' rosters (below). `MUSI` copies records between them field by field
(`0x8007C424`), so one layout serves all.

| byte | field | how it is known |
|---:|---|---|
| 0 | **type** — the insect id of the name list `exe@8003D2E0`; 99 = empty slot | measured: 27 showed the saw stag beetle's name |
| 1 | **size** in mm | measured: 68 showed "68mm"; drives the stats (below) |
| 2 | in a boy's roster, the rank from which he fields it (`MUSI` `0x8007C2C8` skips records whose `+2` is below `0x8003D278`); 0 in Boku's hand | read; measured 0 once taken out |
| 3 | rewritten when a bug is taken out of the cage | measured. It is **not** the badge beside the name: a 255 mm rhinoceros beetle with 0 here shows the crown, a 40 mm saw stag with 2 shows none — the badge follows the size |
| 4 | catch number, printed after the name | measured |
| 5 | the day it was caught ("caught August *n*") | measured |
| 6, 7 | wins, losses | measured ("14 wins 3 losses") |
| 8 | **training** (our name): at the bout's start the fighter's HP rises by `+8 // 10` percent (`MUSI` `0x80081018`) | read; measured (+25 % for 250) |
| 9–11 | 0 in every record seen | — |

The three 240-byte saved regions `0x8003DC28`, `0x8003DB38` and `0x8003DD20` are the boys'
rosters: 20 records each, chosen by `0x8008EF86` = 0, 1, 2 (`MUSI` `0x80081238`); the first
record whose rank `+2` has been reached is the opponent (*read*; which boy is which index is
not decoded).

## From a record to a fighter

`sumo_species` (`MUSI` `0x80081358`) maps the type to a stat row: types 23–30 (the eight
beetles, `exe@8003D2E0` lines 23–30) are rows 0–7, types 56–60 rows 8–12. Types 56–59 share
the names of 23, 24, 27 and 30 through `g_insect_name_remap` (text-outside-events.md) — the
females (measured for 57: the bout screen draws the giant stag with ♀; 56, 58, 59 *inferred*);
60 is the **mantis**.

Each row has base stats at `MUSI.OVL` `0x80079E3C` (8 bytes: `u16` HP, `u8` STR, DEF0, DEF1,
then three bytes copied unscaled — the debug screen's SPD and SICL are the first two) and a
**typical size** at `0x80079EA4`. `sumo_stats` (`0x80081380`) moves every scaled stat by the
bug's distance from that size:

    v = base << 4;   stat = v ± (v // 100) × |size − typical|      (+ above, − below)

HP stays in sixteenths in a word (`fighter +8`); STR and the DEFs are stored `>> 4` in a
**byte** — so past a species' limit a bigger bug *wraps* to a weakling. `SumoTables.max_size`
is the largest size before any byte stat wraps; the mantis row (HP 200, STR 120) is the
strongest by far. Measured: the fighter the game built (`0x8008F018`: `+8` HP, `+0xC` HP
before training, `+0x10` STR, `+0x12` DEF0, `+0x13` DEF1) equalled `boku.sumo`'s prediction
for a 255 mm rhinoceros beetle, a 243 mm giant stag and a 40 mm saw stag (below its typical 55,
so stats fall); `tests/test_real_sumo_bout.py` holds it.

A **maxed** bug (`boku.sumo.maxed`, `boku save --bug NAME`) is its species at `max_size`, with
training 250 (`NAME:SIZE` keeps the training). The mantis (60) can be put in the cage, but
no bout with one has been tried. The cage prints three-digit sizes into the two-digit column ("25[5]m"); give
`NAME:SIZE` for a tidier card.

## Reaching a bout

In play: bug sumo is `E4025`, examining the table at the secret base (`A18`), before 18:00,
on a day other than 15 and before 28, once `g_flags[25]` = 2 and `g_flags[30]` > 0 — or with
`g_flags[168]` set (`research/data/scenes.tsv`). It opens the **desk**: the insect exchange
notebook, the cage, the photo ("release a bug"). ○ on the cage shows the first bug; ○, LEFT,
○ ("出す") takes it out; RIGHT scrolls to the **drum** (the ring), UP and ○ ("虫を置く") put it
down against the boy's bug, and the bout begins ("△で虫をたたく" — tap your bug with △).
`0x8008EF84` is 1 while a bout runs (measured, one run).

`./make.sh saves` writes `sumo-maxed-cage` (and `./make.sh duckstation-cards`
`boku-bug-sumo.mcd`): the morning of August 10 with those flags and ten maxed beetles in the
cage. In DuckStation: walk to the secret base and examine the table.

**Headlessly** (`./make.sh sumo-bout CARD`, `tools/libretro/sumo_bout.py`), measured:

* The dawn movie after a load hands over to the field: pointing `g_movie_return_map`
  (`0x80036588`) at `A18` during it (frame 5100 after `boot-to-save.press`) lands in the
  secret base. Also poking the next-event pair (`0x80036359`/`5A` = 1, 4025), as
  `tools/redux/to-sumo.lua` does on Redux at the hand-over, hung Beetle at the field's load
  every time (before, at and after the hand-over frame; from a save and from a new game's
  intro).
* Forcing mode 7 by writing `mode_set`'s variables from the field did not switch mode.
* So Boku is placed instead: the loaded map's zone table (`*0x80026BFC`: `u32 n`, n × 36 bytes,
  four corners whose low halves are `x, z` in Boku's units ÷ 16) and placement table (`*0x80026C18`)
  give `E4025`'s three examine zones and the point to face (`ev_scan_triggers` `0x800204E0`:
  inside the zone, within `0x300` of the angle to the point, ○). Boku's `x`, `z` and angle
  (`0x80026C58`, `+8`, `+0x12`) are written to a zone's centre ~1200 frames after arriving; the
  first zone lies within Megane's reach, where ○ talks to him instead.
* The desk, cage and drum presses then follow; `sumo-bout` checks the fighter against
  `boku.sumo` and saves `bout.state`, ~12,100 frames from power-on.
* The bout flag rising is both bugs on the drum (`0x8008EF84`/`85` = 1/1), not yet the fight:
  RIGHT moves the hand to the **gong** (desk cursor `0x8008EF78` = 6) and ○ strikes it
  (the desk's input routine, `MUSI` `0x8007C77C`, case 6), which plays a boy's clip and starts the fight;
  the rest of the bout plays its clips by itself (measured: four more in ~1,000 frames, the
  maxed bug winning). △ only zooms the view. `sumo-bout --gong` does this.


## The mantis and the shortcut

Guts's "secret weapon" is a mantis, and beating it is what opens the secret shortcut. The
chain runs on `g_flags` 64, 65, 68, 69, 70 and bug sumo's saved **stage** byte `0x8003D27A`
(read from `MUSI`'s code; each step marked *measured* was watched on Beetle):

| step | what changes |
|---|---|
| Guts's rhinoceros beetle (type 30, 55 mm; `MUSI` `0x8008083C`) beaten at stage 1 | flag 64 = 1, stage 2 (read; what raises 64 to the 2 `E1650` wants is not traced) |
| `E1650` (A18, flag 64 = 2, 65 = 0) and `E1750` (65 = 2, 68 = 0): the weapon announced, the challenge made | flags 65, 68 (from the scene table's conditions; the setters are not traced) |
| next visit to the desk at stage 2 with flag 68 = 1 | the opponent is forced to Guts, flag 68 = 2 (measured) |
| the **rank board** ("虫ランク", left of the drum) set to **キング** (King) against Guts (`0x8008EF86` = 0) at stage 2, flag 68 ≠ 0 (or after August 27 with flag 65 = 2), flag 69 = 0, no King bout yet today (`0x8003DD1B`) and no mantis already out (`0x8003DE14`) | the mantis (type 60, 80 mm; the screen reads 255 wins) replaces Guts's first bug (`MUSI` `0x80081898`; measured), flag 68 = 2 |
| the bout won (`0x8008EF82` = 3) | flag 69 = 1, stage 3; leaving the desk sets stage 4 and queues `E1754` (`g_ev_next` = 1754; measured) |
| `E1754`: Guts leads the boys from the base to the tool store (`A07`) and down the shortcut | flag 70 = 1, Boku at its far end, `E02` (measured) |

After that, examining the spot by the tool store (`E4057`, `A07`, flag 70 > 0) takes the
shortcut to `E02`. A maxed giant stag (female) beat the mantis in about 450 frames of △.

`./make.sh saves` writes `sumo-mantis-ready` (the state before the King bout) and
`shortcut-open` (as a Beetle run left it after `E1754`) — their flags and stage are
`boku.save`'s `MANTIS_FLAGS` and `SHORTCUT_FLAGS` — as slots 2 and 3 of `boku-bug-sumo.mcd`. In play with `sumo-mantis-ready`: at the desk take a
bug out, set the rank board to King, put the bug on the drum, ring the gong (right of the drum),
tap with △. `./make.sh sumo-bout CARD --mantis` does that on Beetle and follows `E1754` to
`E02`, ~17,800 frames from power-on.

## The well on the shortcut

The shortcut's well is **`E08`** (the bible's "hole in the cave"; the old well of `B06`,
`E8062`/`E0809`, is another one). Examining it (`E2405`) the first time shows a close-up of
the shaft (`I12`) and nothing is said; the second time, the close-up again, then the narrator —
**`E2405.0`**, a voiced message *with* text ("this hole seems to lead somewhere… so I
thought"; its key spans 816 sectors of the 16-way interleave, 51 its own, ~5.4 s; the playing
flag stayed up 383 frames) — and Boku climbs down to `E09`. Measured on Beetle with
`./make.sh examine CARD E08 2405`, which logs every clip `xa_play` starts and names the message
whose disc key it is (in RAM a key's `start` carries `BOKU_XA.XAM`'s disc address, 54,417, and
its `+10` is 1).

`B06`'s well, for the record: with flag 36 = 0 (before the uncle's gossip, `E0705`) `E8062`
shows its line with no voice; with 36 = 1, `E0809` plays `MOVIE 8` (`M100`, 4.5 s, no speech —
Whisper hears nothing but the echo) and no clip.

## Subtitles for the boys' voices (PLAN `VO-06`)

Every clip bug sumo plays goes through `xa_play_indexed`, so `VO-03`'s hook sees it; what
`asm/voice.asm` needed was a home for the words and a frame that draws them. Measured on
Beetle, 2026-09-23, with the maxed cage:

* **Where the words live.** `MOVIE_SUB_BLOCK` is bug sumo's own memory (event-scripts.md §
  Native clips). Mode 7 is a level-B mode: `g_arena_cur` is `0x801E7AC0` from the end of its
  init to the end of a bout and never moves; a sentinel written over **level C's base
  (`0x801F7650` under the map-area raise) to `0x801FE000`** at the switch to mode 7 was
  untouched through the desk, a whole fight and sixty more presses -- the stack stays above
  it too. Level C's first `0x6000` bytes are `bg_swap_in`'s scratch, holding nothing between
  map changes. So `g_modes[7]`'s init calls `sumo_sub_init` instead of `MUSI`'s init: that
  init, then the movie-subtitle block (7 sectors today) from the disc to level C's base,
  read on every entry, while the screen is still loading. The assembly refuses a block
  larger than those `0x6000` bytes.
* **Who owns the text.** The runner's flags (`0x8003637C`) read 5 all through a bout: bit 0,
  "an event owns the text", stays set by `E4025`, which is suspended -- `MUSI` never calls
  `event_update` or the dialogue renderer. `clip_sub_owned` (`VO-07`) leaves a native clip's
  subtitle to the main loop whatever the bit says, and `clip_sub_block` does not test it.
* **Where it draws.** `MUSI`'s init sets the mode's vsync count to 0, so the main loop runs
  at 60 Hz. A bout adds its HUD sprites to ordering-table slot 0 -- Boku's portrait 44 × 44 at
  (18, 161), the opponent's at (255, 38), the gong -- and its text to slot 1, so the subtitle
  draws in slot 0 (text in front of its band, both in front of the HUD text) and its pen
  starts `boku.clip_subs.SUMO_PEN_INDENT` (42) px right of the band's, clear of the portrait,
  which a slot-0 prim added earlier still covers. Clips are laid out 42 px narrower
  accordingly (`clip_box`).
* `./make.sh sumo-bout CARD --gong` is the gate: the gong's clip must open its subtitle from
  level C's base with the band up, and it must be down when the clip ends (`--leave` then
  leaves bug sumo: loading-and-memory.md § Leaving a mode). `tools/redux/sumo-clip.lua`
  reaches the desk on PCSX-Redux from a cold boot and plays a clip by the same call.

## The desk's text (PLAN `TXT-05`, `PIPE-07`)

What bug sumo draws from its own arrays and the insect names, measured on Beetle on
2026-09-23 with the days build (shots under `work/surf/`; the exchange notebook reached by
writing a boy's offered bug to `0x8003DE18`, a cage-format record, before ○ on it).

* **The button hint** (`musi@348`, "△で虫をたたく" when the bug is on the drum):
  `musi_hint_draw` `0x8007C604` draws 7 cells from x 120 at y 156 over a board of two 64 × 52
  sprites at x 97 and 161 (`MUSI.OVL`'s 22-byte records `0x8007A4CC`, `0x8007A4E4`, added
  at `g_ot + 0x2240`). The English is drawn by `asm/musi_text.asm` (`vwf_sumo_hint`),
  centred on x 161, and the board widened by repeating a slice of the left half's plain
  frame and paper (u + 24, at most 32 wide at a time) until it holds the line with the
  retail 22-px margins; "△: tap your bug" (97 px) makes it 142 wide. The widened frame
  shows no seam on Beetle.
* **The rank board** (`musi@358`, 弱い / 強い / キング, state 4 — LEFT from the drum):
  `musi_rank_draw` `0x8007EDB0` draws rows 16 px apart from y 85, each centred on x 108.
  The paper is x 82..134; "Weak", "Strong", "King" (31, 42, 27 px) are drawn centred there
  by `vwf_sumo_rank`, the board unchanged.
* **The bout's names** (`MUSI` `0x8007D35C` Boku's fighter at the bottom, `0x8007D670` the
  opponent at the top; measured 2026-09-24 with every fighter's widest case poked into the
  bug in hand `0x8003E098` and the opponent's roster record). The opponent's name is
  right-aligned to end at x 282 (266 before a sex mark at 270), the catch number at 285 and
  the badge 26 px (crown) or 36 px (pink "BIG!") left of the name, so it moves with it:
  "Red-legged Stag Beetle" with the pink badge starts the row at x 102, over the ring,
  clear of everything. Boku's row grows from the left: the badge (record `+3`: 1 crown,
  2 pink) at a fixed x, the name at x 18, 43 or 55 after it, then the sex mark at the
  name's end (its sprite keeps 5 px of its own margin) and the number 15 px on — or, with
  no mark (the types outside the two tables at `0x80045B1C`), the number at the name's
  end, which `asm/musi.asm` moves 3 px on so an English letter does not touch it. The caught date is right-aligned against the screen's edge on the same
  row: "Date caught 8/31" started at x 184 and "Red-legged Stag Beetle" ran into it, so the
  label is "Caught" (`arrays.txt`'s NOTE) and `asm/musi.asm` ends it at x 304 instead of 296;
  with the pink badge, a two-digit number and August 31 the row ends at 217 and the date
  starts at 222. `tests/test_real_date_labels.py` runs the row for every fighter and badge.
* **The exchange notebook** (`0x8007E670`: the offered bug, and the one in hand if any)
  draws a name at x 175 and the item after it — the sex mark, then the catch number at
  0x11E — at a fixed x 271: a Japanese name is 8 cells, 96 px, and ends there. Each of its
  three name calls (`0x8007E6E4`, `E8E0`, `EA48`) now goes to `vwf_name_before_sym`
  (`asm/walkers.asm`), which measures the name off screen as `MUSI` measures its
  right-aligned names and ends it at x 271. The page's paper starts at x 124 with binder
  holes at x 129..134, so a name has 145 px; "Red-legged Stag Beetle" (144) covers the top
  hole and stays readable. **A size badge** (record byte 3 = 1, the crown at x 0x90; = 2,
  a pink badge at 0x8C) sits left of the name at x 140..168 and leaves 103 px: every sumo
  beetle's name but "Oni", "Flat" and "Saw" runs over it then (seen: "Red-legged" over the
  pink badge).
* **The move names** (`musi@2C`, surfaces 25 and 26 of text-renderer.md) are never shown
  in retail: `0x80085580`, the side-by-side pair, is called only from `MUSI`'s update under
  `0x80025938 == 1`, a word nothing but `sw zero` at `0x80011FF0` stores
  (vwf-prototype.md § "The quiz rate"), and `0x80085240`, the other, has no `jal`, `j`,
  data word or `lui` pair in `MUSI` or the executable. The same holds for the debug
  screen's names at `0x8008E8AC` and `0x8008EC7C` (state 9, `0x8008E3E4`, entered on
  START under that word). Their walkers stay installed and tested (`tests/test_real_walkers.py`),
  but the build writes nothing for the array: its English stays in `arrays.txt`, the retail
  bytes stay, the lint reports each row as `unreachable` and coverage leaves them out
  (`boku.arrays.UNREACHABLE`, 2026-09-24; 690 bytes of relocation room freed). **Reopen**
  when a retail path is found that shows them: then drop the entry and the array moves and
  draws as before.

