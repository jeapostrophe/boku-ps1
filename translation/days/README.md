# Day files

One file per in-game day, `dayNN.txt`, holding every line of every event that can occur on
that day — event ids `E<dd>xx` (day = id ÷ 100) in the order the game plays them, plus any
day-independent event the day's flow hands over to, named in the file's header. Written by
the translation agents (README § "How the translation is made"); reviewed against the
Japanese by a second agent; then played. Licence: CC BY-SA 4.0 (`LICENSE-translation`).

The format is the samples' provisional one ([../samples/README.md](../samples/README.md) —
the real one is PLAN `PIPE-01`'s): `line id <TAB> speaker <TAB> English`; ` // ` is a page
break in the same position as the Japanese one (voiced lines keep the disc's page count and
order — pages auto-advance with the voice clip); `[SEL]` rows are choice menus, options
separated by ` | `; `(voice only)` rows have no text on the disc and are listed so the ids line
up; `#` lines are scene headers and translator's notes, not script. The speaker column is the
English label of style guide § 9, or the members of a chorus ("Shirabe, Moe, Aunt") where the
disc's speaker operand is a group. A page that cannot fit the dialogue band (4 lines of ~46
characters, `research/vwf-prototype.md` § TXT-07) is translated in full anyway and flagged
`# OVERFLOW` for the engineering side (PLAN `PIPE-06`); nothing is shortened to fit.

There is no Japanese in these files. With an imported disc,
`python3 work/rec05/scenes.py --dump 171 184` prints the source beside them.

A unit's state is one of **undrafted → drafted → reviewed → checked → rendered → finalized**:
drafted by a translator; reviewed by an independent agent against the Japanese; checked once Jay
has read it and his comments are applied; rendered once our own layout says every page would
display (`boku lint --encoder cellmap`'s pixel fit, and the page mock-ups of `PLAN` `TRN-08`);
finalized once he has seen it in the game, formatted and displayed correctly. `PLAN.md` `TRN-04` holds the table.

| file | events | status |
|---|---|---|
| [day01.txt](day01.txt) | `E0103`–`E0190` (27 events, 85 lines), `E0001` | PLAN `TRN-03` pilot, translated and reviewed against the Japanese (2026-09-20) |
| [shared.txt](shared.txt) | 76 day-independent events (158 rows: 89 text, 36 menus, 33 voice-only): every one day 1 can reach, the nearest outdoors, those days 2–7 handed the day files, and the nine `boku coverage` found no day file had asked for (Ken-bo's fur, the sisters' room, the far waters, the beach, Saori's camp) | PLAN `TRN-03` pilot, translated and reviewed against the Japanese (2026-09-20); the extension verified against the scene data and `EVVER.BIN` the same day; the coverage nine translated and reviewed against the Japanese the same day |

## shared.txt

Not every line a player reads on a given day has that day's id. The bath, the fridge, the
bookshelf, the dinner quiz and its answer, the night rule on the path, the diary at bedtime and
the sixty-odd "examine" descriptions around the house have no day at all, and a player who
finishes day 1 in the game meets them in Japanese unless they are translated with it. So
[shared.txt](shared.txt) holds every day-independent event that day 1 can reach — an event with
no day in its id, sitting in a map variant loaded on August 1 (`EVVER.BIN`), with an entry
condition day 1 satisfies, at a place the day-1 flow can walk to (the house and grounds for
certain; whether day 1 can leave the gate is untested, the header sets out the evidence each
way, and the nearest outdoor one-liners are translated on the assumption that it can). It is
written in the day files' format with two
additions the day files did not need: a `[SEL]` whose first row is the question lists the
question as the first option, and a message with no speaker on the disc — the examine
descriptions, "It's locked." — carries `(unlabelled)` in the speaker column. Later days reach
more day-independent events; they go into this file, not into a day file, so that each event
is translated once — the breakfast chorus (E0006/E0007), the pots drying behind the workshop
(E8054), the beehive beats (E4038/E4039), the beetle trees (E8063) and the kite menu on the
hill (E4026) are there from days 2–7, each with the header stating when it can fire.

## Lessons from the pilot

The translator's "unsure" flags are worth keeping: on day 1, four of the six lines flagged
drew a reviewer finding, so a flag is a real signal of where to look first. The recurring
defect class was *additive* — adverbs, verbs and intensifiers the Japanese does not have
("gave up and surrendered" for one verb, "terribly ... rather" for a bare "cruel and funny",
"flew" for "drawn") — so the review and lint pass checks each line for words not in the
source, not only for words missing from it.
