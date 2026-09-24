# translation/

The English, and everything a translator reads before writing it. Licence: CC BY-SA 4.0
(`LICENSE-translation`). The day files and their format are [days/README.md](days/README.md);
the provisional sample format is [samples/README.md](samples/README.md); the voice and
register are [style-guide.md](style-guide.md) and [bible.md](bible.md); names are
[glossary.md](glossary.md); open questions for Jay are [QUESTIONS.md](QUESTIONS.md); speech
with no text on the disc is [voice-only.md](voice-only.md).

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
   style-guide label) leaves the file untouched and says why: send the message back and ask
   for the block again. Never edit an answer by hand to make it save.
3. At the end of each day, `./make.sh lint-translation` over the day's file; fit on screen is
   the lint's, not the translator's, so a page too long is not sent back.
4. After the last part, the revision pass: ask the session whether it wants to revise a day
   now that it has seen the whole game; for each part it revises, it answers with the whole
   block again and the same `save-event` command replaces the old one.

Days 1–7, `shared.txt` and `arrays.txt` already hold reviewed English, and a whole-game run
replaces those blocks as it reaches them: tag the tree first, as `TRN-08` did, and compare.
Every answer still goes through the independent review against the Japanese
(`./make.sh packet --like FILE --for-review`) before it counts as reviewed.

## movies.txt

The subtitles drawn over the movies (PLAN `FMV-02` writes them, `FMV-04` draws them). One
cue per row, tab-separated:

```
movie <TAB> first frame <TAB> last frame <TAB> English [<TAB> options]
M27	120	300	Far away, I could see the village | of Sagi-no-sato at the foot of the mountain...
M28	1044	1158	The flowers, too, that bloom across | this wide meadow,	panel
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

* **id** is `XCH.` and the clip's two-digit number. Every worded clip already has a row with
  no English; a row without English is listed so the ids line up and draws nothing.
* **speaker** is for the reader of the file; it is not drawn.
* **English** is drawn in the dialogue band while the clip plays, with no speaker label, in
  pages split by ` // ` wherever you put them; each page stays up for its share of the clip,
  shared by length, and the last until the clip ends. An epilogue is half a minute to fifty
  seconds of narration, so give it as many pages as it needs.

`./make.sh lint-translation` checks every row — a clip the table has, every page inside the
band — and `tools/vwf/build_prototype.py` refuses a file it would fail.
