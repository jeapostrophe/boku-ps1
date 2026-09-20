# Sample scenes — DRAFT, for Jay to react to

Three contrasting scenes translated in full under the *recommended* policies of
[../style-guide.md](../style-guide.md). They exist so that the rulings in
[../QUESTIONS.md](../QUESTIONS.md) can be made by reading English rather than by reading
arguments. Nothing here is settled.

| file | events | what it exercises |
|---|---|---|
| [family-E0404-E0406.txt](family-E0404-E0406.txt) | `E0404`, `E0406` — day 4, after dinner: shaved ice on the veranda side of the house | the mealtime set phrases, `-kun`, Uncle/Auntie self-reference, a choice menu, Shirabe's bossy register, a repeat branch |
| [kids-E0650.txt](kids-E0650.txt) | `E0650` — first meeting with all three boys at the secret base | rough-boy register, nicknames, `-chan`, the "Fat" joke whose Japanese glosses an English word |
| [narrator-E2805-E3180.txt](narrator-E2805-E3180.txt) | `E2805` — day 28, the fever night; `E3179`–`E3180` — day 31, the goodbye | the adult narrator against the child, `Onii-chan`, an invented mimetic, the house-rule callback |

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
