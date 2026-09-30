# translation/

The English, and everything a translator reads before writing it. Licence: CC BY-SA 4.0
(`LICENSE-translation`). The day files and their format are [days/README.md](days/README.md);
the three sample scenes the style rulings were read from, since folded into the day files, are
[samples/README.md](samples/README.md); the voice and
register are [style-guide.md](style-guide.md) and [bible.md](bible.md); names are
[glossary.md](glossary.md); open questions for Jay are [QUESTIONS.md](QUESTIONS.md); speech
with no text on the disc is [voice-only.md](voice-only.md); the words Jay chose for particular
lines, which no pass rewrites without him, are [locked.tsv](#lockedtsv).

To read the whole translation in order — every day's events, the day-independent events, the
menus and screens, the clips, the movie subtitles and every typeset texture beside its original —
run `./make.sh reader` and open `work/reader/index.html` (never tracked: it is the Japanese and the
game's pixels). `j`/`k` step through it, `c` copies the current item's id for a comment; the
lint's findings sit on the items they are about, and each section shows its unit's state from
[status.tsv](#statustsv). `./make.sh build-days` rewrites the page after every build. Its header
names the commit and the days build it was made from, and says so in red when that build lacks
what the page shows: a translation file saved after the build began, or code or translation
committed since the build's commit.

## Translating the whole game

Jay, 2026-09-23: one translator session is given everything — the story bible, the style
guide, the glossary and the checklist, whole — and then the game one event at a time in play
order, so every line is written knowing all that came before it, and a revision pass can
follow with the whole game in view.

```
./make.sh packet --game          # writes work/packets/game/ (never tracked: it is the Japanese)
```

* `system.md` is the first message (or the system prompt): the day-file format, then the four
  documents whole. About 95,000 characters, ~29,000 tokens.
* `order.txt` has one row per part, in the order to give them: the event id or surface key,
  a tab, and the translation file its answer is saved into (`day08.txt`, `shared.txt`,
  `arrays.txt`, …). All 31 days, each day's events in its day file's order where one exists,
  each day-independent event on the day its id names (`E1006` on day 10) when its condition
  allows that day, else at the first day that can reach it (the examine texts, the bath, the
  dinner quiz: day 1); then the menus, books and screens. The first part of each day says "Day N begins".
* `<key>.md` is each part (`exe@code:…` is saved as `exe@code_….md`). Together about 470,000
  characters, ~186,000 tokens; the English answers add ~77,000 more (measured against days
  1–7; all figures 2026-09-23), so a whole-game session is ~300,000 tokens and needs a
  1M-context model.
* Not in it: `clips.txt` and `movies.txt`. Their source is a transcript of the audio under
  `work/voice/`, not the disc's text, and their rows are keyed by clip and frame, not by event.

The orchestrator (a script, or a parent agent that never translates) drives the session:

1. Send `system.md`. Then for each row `KEY<TAB>FILE` of `order.txt`, in order: send
   `KEY.md` as the next message, take the reply, and save it:
   `./make.sh save-event KEY --answer reply.txt --into translation/days/FILE --order work/packets/game/order.txt`.
   The reply is the fenced block; prose around it is ignored.
2. A refusal (an id missing or extra, Japanese left in a row or a note, a speaker that is not a
   style-guide label, a line that drops Jay's words from [locked.tsv](#lockedtsv)) leaves the
   file untouched and says why: send the message back and ask for the block again. Never
   edit an answer by hand to make it save.
3. At the end of each day, `./make.sh lint-translation` over the day's file; fit on screen is
   the lint's, not the translator's, so a page too long is not sent back.
4. After the last part, the revision pass: ask the session whether it wants to revise a day
   now that it has seen the whole game; for each part it revises, it answers with the whole
   block again and the same `save-event` command replaces the old one.

Every unit already holds reviewed English ([status.tsv](#statustsv)), and a new whole-game run
replaces each block as it reaches it: tag the tree first, as `TRN-10` did
(`pre-trn10-2026-09-23`), and compare.
Every answer still goes through the independent review against the Japanese
(`./make.sh packet --like FILE --for-review`) before it counts as reviewed. A finding against
words in [locked.tsv](#lockedtsv) is not applied: it goes to Jay.

## locked.tsv

The words Jay chose for particular lines: what he wrote or dictated into a line, a name he
heard, a wording he picked from options put to him about that line (`work/review/decisions.html`).
They are not the policy — a style-guide or glossary ruling binds every line and lives in those
documents — but the words of one line, which a pass working from the Japanese cannot rediscover:
held only in a day file, they are replaced by the next pass that rewrites the line. A wording
accepted "as built", with no choice of words, is not a lock.

```
id <TAB> match <TAB> words <TAB> source
E0175.0	phrase	This is the Sorano house, and I'm your Uncle Yusaku.	Jay, 2026-09-21 (73d7fb7); ...
btn@MITIM.take_out	line	Take	Jay, 2026-09-24 (decisions § 21 G8-MITIM: "it should just be 'Take'")
M27	phrase	specks of light	Jay, 2026-09-24 (decisions § 22: "specks of light" stays)
```

* **id** is a line id of the day files or `clips.txt`, a texture string id
  (`translation/textures/`), or a movie file (`M27`), held by any one of its cues. An id may have
  several rows, one per phrase.
* **match** is `line` when Jay chose the line's whole English (a button, a label, a menu row):
  it must be exactly the words. It is `phrase` when he chose part of a line: the words must
  appear in it, not as part of a longer word ("Take" is not held by "Takeout"), and the rest of
  the line may still be revised around them. The tanka's `phrase` is its " / ": Jay chose the
  slashes, not the words.
* **words** as the line's file writes them — pages joined by ` // `, options by ` | ` — held in
  every copy if a line is translated twice.
* **source** is whose, when and where it was recorded. English only, as the translation files.

What holds it: `tests/test_locked.py` fails when a line loses its words (so `./make.sh test`
catches a hand edit or a sweep), every packet part names the locked words of its lines under
"Words that stay", and `./make.sh save-event` refuses an answer that drops them. Changing a
lock is Jay's call: change the line and its row together, with his ruling as the source. Every
new ruling of his on a line's words gets a row in the same commit that applies it.

## movies.txt

The subtitles drawn over the movies (PLAN `FMV-02` writes them, `FMV-04` draws them). One
cue per row, tab-separated:

```
movie <TAB> first frame <TAB> last frame <TAB> English [<TAB> options]
M27	1105	1213	『The heat of that day was as if all the workings | of life on earth had become tangled and snarled,
M27	3034	3258	All the flowers that bloom across | this wide meadow,	panel
```

* **movie** is the file the movie plays — the `file` column of
  [research/data/movies.tsv](../research/data/movies.tsv): `M27` is the opening, `M28` the
  ending, `M60` the fireworks. A cue belongs to the file, not to a `MOVIE` id: the three
  ids that play `M27` all start at its frame 1, two of them stopping at frame 58, so a cue
  shows under whichever of them reaches its frames.
* **first frame, last frame** are the movie's own frame numbers, both shown: 1-based, 15 a
  second, so the frame at `m:ss.s` into the movie is `1 + 15 × seconds`, rounded. The
  decoded movies `./make.sh movies` writes to `work/movies/*.avi` play at the same 15 fps
  with the narration, which is what to time against. The player may change a cue a
  fifteenth of a second early (`research/movies.md` § 7) — no one can see it.
* **English** is drawn centred near the bottom of the picture (or the top: **options**),
  white with a dark outline, in the same proportional font as the dialogue, at most **two
  lines** of at most 318 pixels each. ` | ` breaks the line where you put it; without one the text is wrapped at
  the width. A literal `|` cannot be drawn.
* **options** are optional, space-separated. `caption` marks a cue that translates writing
  in the picture rather than speech (`M27`'s written thought, FMV-08): `movie-timing` holds
  it to the reading rate, the shortest time and overlap but to no speech, and `--write`
  never moves its frames; it takes no narration marks. `panel` draws a dark panel two
  lines tall behind the cue, for text over busy writing such as the theme song's staff
  credits (FMV-06, FMV-09). A position is `bottom` (the default, what an empty field means)
  or `top`, the same two rows mirrored to the top of the picture, for a picture with
  something under the bottom rows (no cue uses it now; `research/movies.md` § 11).
* The adult Boku's narration — the cues over transcript segments of kind `narration` — is
  marked as the dialogue marks narration (style guide § 9): one pair per sentence, `『` at
  the start of its first cue and `』` at the end of its last, none on the cues between.
  Other cues (the song, the father's line, captions) carry none. `movie-timing` checks it
  (`cue-marks`), and the marks are not counted toward a cue's reading rate.
* `#` lines and blank lines are notes. There is no Japanese in this file, as in the day
  files: the transcripts of the narration stay under `work/`.

`./make.sh movie-timing` checks each cue's timing against the reviewed transcripts of the
narration and the song (and `--write` fixes what moving its frames can fix); `./make.sh movie-review`
shows every cue on Beetle, with a video of it over the voice (`research/movies.md` § 10).
`./make.sh lint-translation` checks every row — a known movie, frames inside it (the last
frame any id playing the file shows), no two cues of one movie overlapping, no more than two
lines, no line wider than the band, every character in the font, known options —
measured in the font the build installs (so run `./make.sh build-days` once first; without
it the pixel rules are a warning that they were not measured). `./make.sh build-days` refuses a file the lint
would fail, naming the row, because every cue goes into every days build. Nothing is cut
to fit: a cue too long for two lines becomes two cues.

## clips.txt

Subtitles for the voice clips the game plays from its own code rather than from an event —
the table `BOKU_XA.XCH`, clips `XCH.00`–`XCH.47`
([research/data/voice-only.tsv](../research/data/voice-only.tsv) says what each one says):
the first night's narration going to sleep (`XCH.34`), the five epilogues (`XCH.41`–`.45`)
and the bug-sumo voices (`XCH.00`–`.40`, laid out 42 px narrower: bug sumo starts its pen
right of Boku's portrait — `boku.clip_subs.clip_box`). A day file's row, keyed by the clip:

```
XCH.34	Narrator	And so the first day of that summer vacation came to an end.
```

* **id** is `XCH.` and the clip's two-digit number. Every worded clip has a row; a row
  without English draws nothing.
* **speaker** is for the reader of the file; it is not drawn.
* **English** is drawn in the dialogue band while the clip plays, with no speaker label, in
  pages split by ` // ` wherever you put them; each page stays up for its share of the clip,
  shared by length, and the last until the clip ends. An epilogue is half a minute to fifty
  seconds of narration, so give it as many pages as it needs.
* **times**, after a third tab, are optional: one number per page, the second of the clip's
  audio at which that page gives way — to the next page, or the last to nothing.

  ```
  XCH.45	Narrator	Within some 15 years ... // a huge dam ... // Nothing is left ...	5.3 12.2 24.2
  ```

  A row with times is not shared by length. **Every epilogue has them**: its clip ends in
  seconds of silence, so pages shared by length run late, and its picture changes to the
  production card before the clip ends (`research/event-scripts.md` § The epilogue's clock).
  Time a page to the pause before its sentence in `work/voice/xch/xch4n-*.wav` (`./make.sh
  voice-only` decodes them; second 0 is the clip's first sample), and the last page to a
  little before the card.

`./make.sh lint-translation` checks every row — a clip the table has, every page inside the
band, times that fit the pages and rise, and, of a row with several pages or with times, no
page up for less than 1.5 s or asking more than 17 characters a second; an epilogue's page
still up when the production card comes is an error — and `./make.sh build-days` refuses a
file it would fail. The reader draws each epilogue page over the still it meets, with a
timeline of pages against pictures, from the same layout; `./make.sh epilogue-review` plays
all five on Beetle and compares.

## status.tsv

Where each unit of the translation stands — PLAN `TRN-04`'s ladder, and the one home of its
table. One row per unit the reader walks, tab-separated, after a header row:

```
unit <TAB> state <TAB> date <TAB> note
day01	reviewed	2026-09-23	the TRN-10 whole-game session, ...
```

* **unit** is a day file's name (`day01`–`day31`), `shared`, `arrays`, `clips`, `movies`, or a
  texture unit: `screens` (`ui.txt`, `signs.txt`, `buttons.txt`, `records.txt`), `diary`,
  `books` (`boku.reader.TEXTURE_UNITS`; a new texture file is a unit by its own name).
* **state** is one of `undrafted`, `drafted`, `reviewed` (an independent agent against the
  Japanese), `checked` (Jay has read it, his comments applied), `rendered` (the lint's pixel
  fit and the page mock-ups say it would display), `finalized` (Jay has seen it in the game,
  formatted and displayed correctly).
* **date** is when the unit reached that state, `YYYY-MM-DD`; **note** says how.

A test holds this file to the units the translation files make, both ways: a new day file or
texture file fails it until it is given a row, and a row for a unit nothing walks fails it too.
English and ids only.
