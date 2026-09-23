# Speech with no text on the disc (QUESTIONS Q11, ruled 2026-09-20)

The ruling: these sequences **are translated, now, into tracked files under this directory**;
how the English reaches the screen is decided later, and **engine-drawn subtitles are the
preferred delivery**, re-encoded FMV frames the alternative. Jay: *"let's go with (b); we'll
figure out later whether we put subtitles in the FMV or do it within the engine. Within engine
is better."* The PLAN row for the delivery work is the orchestrator's; this file only says
what the sequences are. Style: the narrator's voice is style guide § 6; everything else
follows the speaker's register in the bible.

There is no text layer for any of these — no message on the disc, no line id. Ids below are
the events that *surround* them; the translation files will be keyed by movie or clip and
time, a format `PIPE-01` does not yet define. Transcribing needs a listener (or an ASR pass
checked by one).

## The frame of the game — first-class

| sequence | where it plays | what is known |
|---|---|---|
| **Opening monologue** (the adult narrator) | the FMV that runs before the first event; `E0001` (`MAP I16`, one text narration line, `E0001.0`) is the first thing with text | **`__STR/M27.IKI`**, movie id 23 in the table at `0x80029604`: 4,239 frames at 15 fps ≈ 4 min 43 s, its narration the XA audio interleaved in the file (`research/movies.md` § 1, § 2.2). The number → name table for every movie is there too |
| **The five epilogues** (the adult narrator; the payoff of the game) | entered from `E3182` (day 31, `flag[251]==12`): `MOVIE 24` → `END` → game-mode switch (`0x80011A98(14)`, `research/event-scripts.md` § `END`); which of the five plays is chosen by the ★ count of bible § 2 / § 4 (0–3 / 4–6 / 7–9 / 10–12 / 13–15 [xneo]) — the valley drowned by a dam; a programmer at an electronics firm; the sisters' marriages; a potter like his uncle; a novelist | `MOVIE 24` is **`__STR/M28.IKI`**, the one ending movie, the same for every ending; the five epilogues are what follows it — mode `0x10`, `ENDOTI.OVL`, a still from `OTI00`–`OTI04` with narration over it and no text (Jay, 2026-09-22, from playing). The five narrations are `g_xa_clips` records `XCH.41`–`.45` (research/voice-only.md); which still goes with which, and the credits, are PLAN `VO-03`; the narration's transcription and translation `VO-04` |

## Other speech-bearing voice-only clips — same ruling, lower priority

108 `XA` (voice-only) nodes exist across the events (`research/data/scenes.tsv`). Most are
wordless — the howl (`E0405`, `E1306`, `E1905`), laughs, Ken-bō, Nora. The ones with words,
from bible § 8 item 10:

| sequence | ids |
|---|---|
| Radio calisthenics (the daily FMV; the announcer's patter) | every morning; `E0605.3`, `E2720.1` refer to it |
| Television programmes | `E0305` (5 clips), `E4052` (8 clips) |
| The August 15 broadcast (the end-of-war anniversary) | `E1505` |
| The monk's sutra | `E1203` (4 clips, slot 255) |
| The whale dream (day 15) and the sunflower dream (day 29) | around `E1506` and `E2907`; the dream clips' own ids are not pinned |
| Moe reading the English letter aloud | `E2330.11` — already English; nothing to translate (style guide § 16) |

The listening pass was made 2026-09-22 (ASR, read against the scenes):
[research/data/voice-only.tsv](../research/data/voice-only.tsv) marks every clip `wordless` or
gives its gist in English, and [research/voice-only.md](../research/voice-only.md) § What was
found summarises it. Corrections to the table above: the radio calisthenics movies (`M21`,
`M22`) have no voice (Jay's watch, `movies.tsv`); the monk's sutra (`E1203`) was not
transcribable and is marked a style call; the sunflower dream is the movie `M260`, and no
`XA` or `g_xa_clips` clip is the whale dream; `E2330.11`
had no speech the ASR could find. New with words: the evening news items and the August 6 /
9 / 15 broadcasts, three voices on Saori's recorder (`E1861.30`–`.32`), `E2305.0`, the
bug-sumo voices and the first night's narration (`XCH.00`–`.40`, `XCH.34` — clips native code
plays, not event lines).
