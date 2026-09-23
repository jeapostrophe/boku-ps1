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
