# Voice with no text on the disc (PLAN `VO-01`, `FMV-02`)

Measured 2026-09-22 on the dump of [disc-recon.md](disc-recon.md). What each clip *says* is
[`data/voice-only.tsv`](data/voice-only.tsv)'s `said` column, in English; the Japanese heard
lives only under `work/voice/` (CLAUDE.md). How the English reaches the screen is `VO-02`
(events), `VO-03` (the endings) and `FMV-04` (movies); what the translation files are is
[translation/voice-only.md](../translation/voice-only.md).

## Where speech without text comes from

`__STR/BOKU_XA.XAM` (LBA 54417, 96,453 sectors) is 16-way interleaved XA, 37.8 kHz 4-bit
mono, 4,032 samples a sector. Three things name clips in it, all with the same 12-byte key
`{u32 start, u32 end, u8 channel, u8 file, u16 0}` ([event-scripts.md](event-scripts.md) §
Voice key):

| source | rows | distinct clips | what |
|---|---:|---:|---|
| event `XA` instructions (opcode `0x0F`) | 115 | 63 | a voice or sound played with no text; every null text entry is named by exactly one |
| `g_xa_clips` (`BOKU_XA.XCH`, `u32 48` + 48 keys, loaded by `xa_init` `0x8002AFB4` — [loading-and-memory.md](loading-and-memory.md)) | 48 | 48 | clips native code plays by index: the boys' bug-sumo lines, the first night's narration, the five epilogues |
| event `XAMSG` keys | — | 2,100 | voiced lines *with* text; not in this table (no key is shared with an `XA`; the two sets are the 2,163 of event-scripts.md) |

`./make.sh voice-only` writes one row per event `XA` (`line_id` `E<event>.<message>`, the id
the day files' `(voice only)` rows carry) and one per `g_xa_clips` record (`XCH.<index>`).

**Nothing else in the XAM is a clip.** Every file-2/3 audio sector is named by one of those
keys except 257 sectors in 13 short runs (§ Unreferenced runs lists the 12 of 4 sectors
or more). File number 1 (9,370 sectors)
is mastering filler, not content: 2-sector gaps between clips, and at the tail each channel's
last 100 sectors (10.67 s) repeated until the file ends — measured byte-identical at a lag of
exactly 100 sectors on all 14 channels that have a tail. Whisper over the tail therefore
"hears" the end of an epilogue four times over.

### Reconciling the counts quoted elsewhere

* **115** `XA` instructions = 115 distinct null-text messages (every one reachable, each
  named once); they play **63** distinct keys, so `same_clip_as` names the rows sharing one.
* **446** null-text entries ([text-format.md](text-format.md)) counts *stored copies*: the
  same event block sits in several map variants. `copies` is that count per row, and it sums
  to 446 (a test counts it from the blocks independently).
* **108** ([event-scripts.md](event-scripts.md) § Speakers) is the rows whose `speaker` is
  `VOICE` — no character's mouth moves (slot 255, or slot 22, which names no one). The other
  7 flap a group's mouths: 5 `ALL`, 1 `GUTS+FAT+MEGANE`, 1 `BOKU+GUTS+FAT+MEGANE`.

### Columns

| column | from |
|---|---|
| `line_id`, `node` | the message and the instruction's pc (`boku.events`); `XCH.nn` and `BOKU_XA.XCH[n]` for `g_xa_clips` |
| `day` | the event id's day (`EventWorld.when`); blank for ids that carry none and for events whose condition names its own day |
| `speaker`, `slot` | `EventWorld.speaker` and operand `@6`; `-` for `g_xa_clips`, which has no operand |
| `xa_file`, `channel`, `start`, `end` | the key; `start`/`end` are sectors of `BOKU_XA.XAM` |
| `sectors`, `seconds` | the clip's own sectors, both ends included: `(end − start) / 16 + 1`, × 4,032 / 37,800 |
| `copies` | stored block copies of the event holding this null entry (1 for `g_xa_clips`) |
| `same_clip_as` | other rows with an identical key |
| `said`, `notes` | **by hand**, carried across a regeneration: `wordless` or an English gist |

## Unreferenced runs

File-2/3 audio no key names (sector ranges of `BOKU_XA.XAM`, channel = `start % 16`). Whether
native code plays any of them by a computed key is not known; nothing on the disc holds
their keys (a scan of the executable and every `BOKU.BIN` member for key-shaped records
found only `g_xa_clips`).

| sectors | file | heard (plain pass; none of these was decoded gated) |
|---|---:|---|
| 3387–3643 | 2 | words: "maybe it's reaching the end of its life" — the same words the plain pass hears over the opening movie's music at 41 s |
| 10652–10748 | 2 | nothing (stock line) |
| 10721–10945, 10813–10957 | 3, 2 | words: "thank you for the meal" (two takes) |
| 28925–29005 | 3 | words: "huh?" |
| 29041–29361 | 3 | words: "what's this?" |
| 61999–62463 | 2 | laughter |
| 76910–77134 | 3 | a word, uncertain ("welt") |
| 88162–88738, 88276–88324, 88787–90131, 89437–89533 | 3, 3, 2, 3 | nothing (stock lines) |

`XCH.00`–`XCH.40` (the bug-sumo voices) sit in the same region as the first three, so these
may be spare takes the game never names.

## The movies' audio and the frame a cue keys to

`./make.sh voice-only` also decodes the audio of the movies `movies.tsv` marks `VOICE`
(`M27`, `M28`, `M60`, `M120`, `M260`) from the `.IKI` extent with ffmpeg's `psxstr` demuxer
to `work/voice/movies/<file>.wav`. Measured on all five: slot *j* (10 sectors, 0-based) of the
extent carries STR header frame *j* + 1, and the last 5 slots repeat the stop frame
([movies.md](movies.md) § 1). The first audio sector is extent sector 7, and ffmpeg puts the
audio's t = 0 there (its packets are stamped 0, 0.0533, 0.1067 s — 8 sectors apart — on
`M120`). So a time *t* seconds into that WAV is on screen as header frame
`floor(15 (t + 7/150)) + 1`, computed exactly (`boku.voice.header_frame`) — the number
`FMV-04`'s hook compares. Frame values in `work/voice/` use it.

## The listening pass

`./make.sh voice-only --transcribe` runs whisper.cpp large-v3, Japanese, twice over every
clip and movie ([tooling-setup.md](tooling-setup.md) § XA): once plain and once behind the
Silero voice-activity gate. They fail in opposite directions, which is why both:

* **Plain, over a clip with no speech, Whisper invents a stock line** — the closing phrases
  of subtitled web video ("thanks for watching", "please subscribe", a subtitler's credit)
  over a sound effect, music or near-silence. 34 of the 63 event clips drew one; the gated
  pass left 31 of those empty and heard a cat's mew or the stock line again in the rest.
* **Gated, a shout under half a second is dropped** — `XCH.06`'s one-word cheer (0.34 s)
  came back empty gated and correct plain.
* Without `-mc 0` (no text carried between 30 s windows) large-v3 locked onto one line and
  repeated it for the rest of `M28`'s song; the tool always passes it.

A row was marked by reading both passes against the scene around it (the lines before and
after in play order, from `disc/script/`). Speech Whisper transcribed cleanly in both passes
is taken as speech; a stock line plain and nothing gated is taken as wordless; the rest was
decided from context and says so in `notes`.

### What was found (2026-09-22)

* **Event `XA` rows: 16 of 115 have words** (16 distinct clips: 12 broadcasts and 4
  voices): the high-school baseball commentary and results on the television (`E0305.0`–`.4`,
  day 3; 3.8 minutes), the August 6 / 9 / 15 news (`E0606.0`, `E0905.1`, `E1505.0`), the
  evening news items and a drama narrator's line (`E4052.2`–`.5`), three voices on Saori's
  recorder (`E1861.30`–`.32`), and one remembered line about the vice-principal's buried
  treasure (`E2305.0`). The other 99 are wordless: laughter, the howl, Ken-bō, Nora, the
  camera, doors, jingles, bath and drink sounds, the monk's sutra (not transcribed; liturgy).
  One row needs an ear: `E2330.11` and the four rows sharing its clip, which translation/voice-only.md takes
  for Moe reading the English letter aloud — no speech was found in Japanese or English.
* **`g_xa_clips`: 46 of 48 have words.** `XCH.00`–`.32` and `.35`–`.40` are the bug-sumo
  lines (challenge, trade, cheer, win, lose, in the boys' voices; 39 clips), `XCH.33` a cheer; `XCH.34` is the
  adult narrator's "and so the first day of that summer vacation came to an end" — the
  voice-over going to sleep on day 1 that opened `VO-01`; **`XCH.41`–`.45` are the five
  epilogues** (28–49 s each; which is which is in `said`). `XCH.46`/`.47` are a click and
  beeps. `ENDOTI` plays `41 +` the ending number in `0x80035F42` (`0x80079BE4`;
  [event-scripts.md](event-scripts.md) § Native clips); `ENDOTI.OVL` holds no key.
* **Movies**: `M27` is 60 s of music, the opening monologue from 70 s to 181 s (16 segments; one
  short voice at 41 s is uncertain),
  then the theme song from 202 s; `M28` is music, one narrated sentence at 64–69.5 s, then the
  theme song and the credits; `M60`, `M120`, `M260` are one to three narrated sentences each
  (`M120`'s sentence runs on past the movie's end). The songs are transcribed and marked
  `song`; whether they are subtitled is a translation call.
* **Not found**: the well narration Jay heard (PLAN `VO-01`) is not any `XA` or `g_xa_clips`
  clip; the well's examine event (`E8062`) is an unvoiced `MSG` with text.

Where the Japanese is: `work/voice/voice-only.asr.tsv` (both passes and the neighbouring
lines, per row), `work/voice/reviewed/` (the corrected transcripts), `work/voice/movies/`
(`<file>.asr.tsv` / `.vad.asr.tsv`, timed, with 1-based frames).
