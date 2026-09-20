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

| file | events | status |
|---|---|---|
| [day01.txt](day01.txt) | `E0103`–`E0190` (27 events, 85 lines), `E0001` | PLAN `TRN-03` pilot, translated and reviewed against the Japanese (2026-09-20) |

## Lessons from the pilot

The translator's "unsure" flags are worth keeping: on day 1, four of the six lines flagged
drew a reviewer finding, so a flag is a real signal of where to look first. The recurring
defect class was *additive* — adverbs, verbs and intensifiers the Japanese does not have
("gave up and surrendered" for one verb, "terribly ... rather" for a bare "cruel and funny",
"flew" for "drawn") — so the review and lint pass checks each line for words not in the
source, not only for words missing from it.
