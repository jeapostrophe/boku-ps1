# Sample scenes

Three contrasting scenes translated in full under the policies of
[../style-guide.md](../style-guide.md). They were written so that the rulings in
[../QUESTIONS.md](../QUESTIONS.md) could be made by reading English rather than by reading
arguments; Jay ruled on 2026-09-20 and the samples were re-checked against the settled policy.
Their `#` notes keep the rejected renderings for comparison.

All three have since been folded into the day files, which are the reviewed home of those
lines (`E0404`/`E0406` in [../days/day04.txt](../days/day04.txt), `E0650` in
[../days/day06.txt](../days/day06.txt), `E2805` in [../days/day28.txt](../days/day28.txt),
`E3179`–`E3180` in [../days/shared.txt](../days/shared.txt)); the sample files were deleted so
that no id is translated twice. This README stays for the file format below, which the day
files use.

## File format (provisional — the real one is PLAN `PIPE-01`'s)

One line per message: `line id <TAB> speaker <TAB> English`. The line id is
`E<event>.<message index>` (research/text-format.md § "Proposed line id"). ` // ` is a **page
break**, in the same position as the Japanese one — pages auto-advance in time with the voice
clip (research/text-format.md, control word `0x8002`), so content never moves across a page
boundary. Lines inside a page are not broken here: wrapping belongs to the renderer.
`[SEL]` rows are choice menus, options separated by ` | `. `(voice only)` rows have no text on
the disc and are listed so the ids line up. `#` lines are translator's notes, not script.

There is no Japanese in these files. With an imported disc,
`python3 work/rec05/scenes.py --dump 404 406 650 2805 3179 3180` prints the source beside them.
