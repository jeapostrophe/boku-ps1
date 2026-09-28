# Day files

One file per in-game day, `dayNN.txt`, holding every line of every event that can occur on
that day — event ids `E<dd>xx` (day = id ÷ 100) in the order the game plays them, plus any
day-independent event the day's flow hands over to, named in the file's header. Written by
the translation agents (README § "How the translation is made"); reviewed against the
Japanese by a second agent; then played. Licence: CC BY-SA 4.0 (`LICENSE-translation`).

The format is § Format below (ruled by Jay, PLAN `PIPE-02`; `boku/translation.py` loads it).
That section is addressed to
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
  "poem" and pronounced "Shirabe".`
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
  `# VOICE E0121.3: just -- translates dake` records that a word like "just" or "really",
  which the lint flags when the Japanese has no matching intensifier, was looked at and kept:
  it translates something, or it is how this speaker talks. It sits directly above its row.
  If you rewrite a line, keep its note only while the word is still there and still right.
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
  game puts its numbers: `Caught {month}/{day}`, `August {day}`.
* **The card screens' two answers** (`title@7A78.0`, the Japanese "hai" and "iie" side by
  side) are one row written `Yes | No`: the first answer, ` | `, the second. The build places
  the second where the Japanese one began and tells the drawer where the first ends; the two
  share the row's five letters.
* **Words that stay.** A part may end with a list headed "Words that stay": words Jay chose
  for some of its lines. Keep each exactly as written in that line's English and translate
  the rest of the line around it; an answer that drops one is sent back.
* **Nothing is shortened to fit.** Translate the whole of what is said.

## The files

There is no Japanese in these files, notes included (`boku save-event` refuses an answer
that holds any). A page that does not fit the band is not the translator's to flag: `./make.sh
lint-translation` measures every page and `./make.sh mockup` draws it. `./make.sh reader`
shows every line with its Japanese beside it and the lint's findings on the lines they are
about.

Each unit's state (undrafted to finalized) is [../status.tsv](../status.tsv), defined in
`translation/README.md` § status.tsv; the table below says what each file holds and where it
began.

| file | holds | began |
|---|---|---|
| `day01.txt`–`day31.txt` | each day's events, `E<dd>xx`, in play order, and any day-independent event its day hands over to (`day01.txt` holds `E0001`) | day 1: the PLAN `TRN-03` pilot (2026-09-20); days 2–7 the same workflow; all 31 days, day 1 again among them, the `TRN-10` whole-game session (2026-09-23) |
| [shared.txt](shared.txt) | the day-independent events (§ shared.txt) | the `TRN-03` pilot, extended as later days reached more of them, completed by `TRN-10` |
| [arrays.txt](arrays.txt) | the lines outside every event — memory-card and save messages, the title and config screens, the controls help, item, kite, fish and insect names and descriptions, captions, the insect book, bug sumo, the kite and diary menus (`research/text-outside-events.md`); keyed by the extract's `<file>@<offset>.<item>` ids | PLAN `TRN-09`; `./make.sh packet --arrays` makes its packet, and `boku lint` says which lines the build cannot place |

## shared.txt

Not every line a player reads on a given day has that day's id. The bath, the fridge, the
bookshelf, the dinner quiz and its answer, the night rule on the path, the diary at bedtime and
the sixty-odd "examine" descriptions around the house have no day at all. [shared.txt](shared.txt)
holds every such event — no day in its id, or a day its entry condition ignores — so that each
is translated once, however many days reach it; `boku save-event` sends a part with no day
there. Its header says what it holds and why.

## Lessons from the pilot

The translator's "unsure" flags are worth keeping: on day 1, four of the six lines flagged
drew a reviewer finding, so a flag is a real signal of where to look first. The recurring
defect class was *additive* — adverbs, verbs and intensifiers the Japanese does not have
("gave up and surrendered" for one verb, "terribly ... rather" for a bare "cruel and funny",
"flew" for "drawn") — so the review and lint pass checks each line for words not in the
source, not only for words missing from it.
