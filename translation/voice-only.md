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
| **The five epilogues** (the adult narrator; the payoff of the game) | entered from `E3182` (day 31, `flag[251]==12`): `MOVIE 24` → `END` → game-mode switch (`0x80011A98(14)`, `research/event-scripts.md` § `END`); which of the five plays is chosen by the ★ count of bible § 2 / § 4 (0–3 / 4–6 / 7–9 / 10–12 / 13–15 [xneo]) — the valley drowned by a dam; a programmer at an electronics firm; the sisters' marriages; a potter like his uncle; a novelist | `MOVIE 24` is **`__STR/M28.IKI`**, 4,194 frames ≈ 4 min 40 s, the one entry the player refuses to skip; `M27.IKI` is the opening, not an ending (`research/movies.md` § 1). **The table holds a single ending movie**, so whatever differs between the five epilogues is not in the video — it must be in the mode the game enters after it (`0x10`) or the events around `E3182`; that code has not been read |

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

Everything else in the 108 should be listened to once and recorded here as wordless or
added to the table; that pass has not been made.
