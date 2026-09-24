# Day files

One file per in-game day, `dayNN.txt`, holding every line of every event that can occur on
that day — event ids `E<dd>xx` (day = id ÷ 100) in the order the game plays them, plus any
day-independent event the day's flow hands over to, named in the file's header. Written by
the translation agents (README § "How the translation is made"); reviewed against the
Japanese by a second agent; then played. Licence: CC BY-SA 4.0 (`LICENSE-translation`).

The format is the samples' provisional one ([../samples/README.md](../samples/README.md) —
the real one is PLAN `PIPE-01`'s), written out in § Format below. That section is addressed to
the translator and is quoted whole into every translator packet (`boku packet`), so it states
the format and nothing the tools measure: fit on screen is `boku lint`'s job, and page mock-ups
are `./make.sh mockup`'s.

## Format

* **One row per line of the script:** `line id <TAB> speaker <TAB> English`, in the order the
  packet gives them. Every id the packet lists is returned, once, and no other.
* **` // ` is a page break**, in the same place as the Japanese one and the same number of
  them. Nothing moves across a break: each page is what is on screen while that part is being
  said. Inside a page, write the English as one run; the tools break it into lines.
* **The speaker column** holds the English label of style guide § 9, which lists them. A
  chorus — no label on screen, several people speaking — lists its members, comma-separated:
  `Shirabe, Moe, Aunt`. A message nobody speaks (an examine description, "Got the fishing rod.") carries
  `(unlabelled)`; narration carries `Narrator`.
* **No quotation marks around speech.** The marks the Japanese draws around a line are put back
  by the renderer. Quotation marks around a word named inside a line are fine: `It's written
  "poem" and read "Shirabe".`
* **`[SEL]` rows are choice menus**: the options separated by ` | `, as many as the Japanese
  has and in its order. When the menu opens with a question, the question is the first field.
* **`(voice only)` rows** have no text on the disc and are listed so the ids line up. Return
  them as they are, unless you are asked for the clip's words: then write the English after a
  second tab, split into pages with ` // ` wherever you like; it is shown as a subtitle while
  the clip plays, with no speaker label. The clips the game plays outside any event — the
  epilogues, the first night's narration — are rows of `translation/clips.txt` in the same
  form, keyed `XCH.nn` (`translation/README.md` § clips.txt).
* **`#` lines are not script.** `# --- E0121: …` opens an event and says where it happens;
  `# NOTE E0121.3: …` is a translator's note on a rendering (a pun, a choice a reviewer should
  know about); `# UNSURE E0121.3: …` flags a line you are not sure of, so that the reviewer
  looks there first. A note is English too: no Japanese anywhere in the file, notes
  included — romanise a word you need to quote (*satoyama*, *daikichi*).
* **The menus, books and screens** (`arrays.txt`) use the same rows. A line nobody speaks
  carries `(unlabelled)`; a menu is a `[SEL]` row; `# --- exe@8003D2E0: …` opens a list the
  way `# --- E0121` opens an event. A game glyph the English sits beside — a button, the
  dashed rule — is written `{G:n}` (its id in `research/data/glyph-table.tsv`) or as the
  character the sheet draws (○ × ↓); either is that one cell of the game's own sheet. A line
  of dialogue may name a button the same way, by the character (`Try pressing the ○ button`).
* **The memory card's save title** (`title@sjis:188`) marks where the game puts the slot
  number and the day: `Boku's Memories {slot} August {day}`. The console's card screen
  shows it in full-width letters, at most 64 bytes with the widest slot and day (the lint
  says when it is over).
* **A label the code draws glyph by glyph** (`exe@code:…`, `title@code:…`) is placed one
  character per glyph the function draws, runs separated by ` / ` where it draws a number
  in between; more characters than it draws are left in Japanese (`not-placeable`). The
  two date labels are redrawn around their English instead, and their rows mark where the
  game puts its numbers: `Date caught {month}/{day}`, `August {day}`.
* **The card screens' two answers** (`title@7A78.0`, the Japanese "hai" and "iie" side by
  side) are one row written `Yes | No`: the first answer, ` | `, the second. The build places
  the second where the Japanese one began and tells the drawer where the first ends; the two
  share the row's five letters.
* **Nothing is shortened to fit.** Translate the whole of what is said.

## The files

There is no Japanese in these files, notes included (`boku save-event` refuses an answer
that holds any). A page that does not fit the band is not the translator's to flag: `boku lint
--encoder cellmap` measures every page and `./make.sh mockup` draws it, so the reader's *over*
column, which counts `# OVERFLOW` notes, counts only notes someone added by hand. With an
imported disc,
`python3 work/rec05/scenes.py --dump 171 184` prints the source beside them.

A unit's state is one of **undrafted → drafted → reviewed → checked → rendered → finalized**:
drafted by a translator; reviewed by an independent agent against the Japanese; checked once Jay
has read it and his comments are applied; rendered once our own layout says every page would
display (`boku lint --encoder cellmap`'s pixel fit, and the page mock-ups `./make.sh mockup` draws);
finalized once he has seen it in the game, formatted and displayed correctly. `PLAN.md` `TRN-04` holds the table.

| file | events | status |
|---|---|---|
| [day01.txt](day01.txt) | `E0103`–`E0190` (27 events, 85 lines), `E0001` | PLAN `TRN-03` pilot, translated and reviewed against the Japanese (2026-09-20) |
| `arrays.txt` | the lines outside every event — memory-card and save messages, the title and config screens, the controls help, item, kite, fish and insect names and descriptions, captions, the insect book, bug sumo, the kite and diary menus (308 lines on 42 surfaces: 34 arrays, six labels spelled out in code, the save title and one message the program holds; `research/text-outside-events.md`); keyed by the extract's `<file>@<offset>.<item>` ids | PLAN `TRN-09`: not yet written. `./make.sh packet --arrays` makes its packet; the build places a line only where its English fits the array's own bytes (most will not until the fixed-pitch surfaces are rebuilt, PLAN `TXT-05`), and `boku lint` says which |
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
