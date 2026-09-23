# translation/

The English, and everything a translator reads before writing it. Licence: CC BY-SA 4.0
(`LICENSE-translation`). The day files and their format are [days/README.md](days/README.md);
the provisional sample format is [samples/README.md](samples/README.md); the voice and
register are [style-guide.md](style-guide.md) and [bible.md](bible.md); names are
[glossary.md](glossary.md); open questions for Jay are [QUESTIONS.md](QUESTIONS.md); speech
with no text on the disc is [voice-only.md](voice-only.md).

## movies.txt

The subtitles drawn over the movies (PLAN `FMV-02` writes them, `FMV-04` draws them). One
cue per row, tab-separated:

```
movie <TAB> first frame <TAB> last frame <TAB> English
M27	120	300	Far away, I could see the village | of Sagi-no-sato at the foot of the mountain...
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
* **English** is drawn centred near the bottom of the picture, white with a dark outline,
  in the same proportional font as the dialogue, at most **two lines** of at most 318
  pixels each. ` | ` breaks the line where you put it; without one the text is wrapped at
  the width. A literal `|` cannot be drawn. In the ending (`M28`) the Japanese credits scroll
  up through those rows from about frame 1085 to the end, so a cue there is drawn over them
  (`research/movies.md` § 9).
* `#` lines and blank lines are notes. There is no Japanese in this file, as in the day
  files: the transcripts of the narration stay under `work/`.

`./make.sh movie-timing` checks each cue's timing against the reviewed transcripts of the
narration (and `--write` fixes what moving its frames can fix); `./make.sh movie-review`
shows every cue on Beetle, with a video of it over the voice (`research/movies.md` § 10).
`./make.sh lint-translation` checks every row — a known movie, frames inside it (the last
frame any id playing the file shows), no two cues of one movie overlapping, no more than two
lines, no line wider than the band, every character in the font — measured in the font the
build installs (so run `./make.sh build-days` once first; without it the pixel rules are a
warning that they were not measured). `./make.sh build-days` refuses a file the lint
would fail, naming the row, because every cue goes into every days build. Nothing is cut
to fit: a cue too long for two lines becomes two cues.

## clips.txt

Subtitles for the voice clips the game plays from its own code rather than from an event —
the table `BOKU_XA.XCH`, clips `XCH.00`–`XCH.47`
([research/data/voice-only.tsv](../research/data/voice-only.tsv) says what each one says):
the first night's narration going to sleep (`XCH.34`), the five epilogues (`XCH.41`–`.45`)
and the bug-sumo voices (`XCH.00`–`.40`; drawn once PLAN `VO-06` is done). A day file's row,
keyed by the clip:

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
