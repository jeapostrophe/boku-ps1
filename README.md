# boku-ps1

An English translation patch for the PlayStation original of *Boku no Natsuyasumi* (ぼくのなつやすみ,
SCEI / Millennium Kitchen, 2000, **SCPS-10088**) — built in the open, tools and translation both.

## Status

**The whole game is translated and the build carries all of it; what is left is playing it,
Jay's read of the script, and the release.** The open work is [PLAN.md](PLAN.md).

* **Text.** The game draws English left to right, proportionally, in its own glyph sheet, in a
  translucent three-line band under the scene, with speaker labels in the original's
  `Uncle「…」` form and choice menus as rows beside the game's own hand. Every event of the 31
  days, the day-independent events, and the menus, books and screens are translated and
  reviewed against the Japanese by a second agent; where each unit stands is
  [translation/status.tsv](translation/status.tsv). A line that outgrows its space is
  relocated, never cut.
* **Textures.** Every image that carries Japanese has a ruled path
  ([research/textures-plan.md](research/textures-plan.md)); the picture diary, the two
  encyclopedias, the title and menu plates, the buttons, the records and the signs are set in
  English at build time from your import.
* **Movies and voices.** The narrated movies and the theme song are subtitled inside the video
  frames; the voice clips with no text on the disc — the five epilogues, the first night's
  narration, bug sumo, voice-only lines in events — are subtitled in the band. The voices
  themselves stay Japanese.
* **Where it is seen.** Each piece is confirmed on Beetle PSX (the core Mode One runs) wherever
  play can reach it, most on PCSX-Redux too, and Jay plays the builds on DuckStation. Not yet done: a full
  playthrough, confirmation on the release targets, and the release itself.

## Why the PS1 version

A PSP port exists, has a finished Spanish patch, and re-targeting that patch to English would
be the shorter road. This project takes the longer one on purpose (Jay, 2026-09-19): the PSP
port letterboxes and stretches the 4:3 painted backgrounds to 16:9, and the original's layering
of the character models over those backgrounds is better. The PS1 game is the one worth
playing, so it is the one worth translating.

## Principles

1. **The whole repo is public.** The fan-translation norm is to work in private and post a
   finished patch. Here the tools, the format notes, the translation and its history are all
   in the repo, and pull requests with better ideas, options or styles are welcome.
2. **The repo contains none of the original game.** No image, no extracted files, no Japanese
   script, no ripped textures. Everything taken from the disc is regenerated locally by the
   *import step* from a dump you own, into gitignored directories. One deliberate exception
   (Jay, 2026-09-20): textures **redrawn** in English are new images and are committed; whether
   a redraw of a copyrighted image carries the original's copyright is arguable, and the
   project takes that chance. Textures that merely get subtitles composited onto the original
   pixels are *not* committed — the repo holds the subtitle text and placement, and the build
   composites them onto your import.
3. **Translation is keyed by line id.** Committed translation files hold English plus context
   notes written for this project, keyed by stable ids; the Japanese for an id exists only in
   your local import. Agents translate on those ids directly. For reading it as a script there is a
   read-only reader (`./make.sh reader`, PLAN `TRN-14`); there is no editable projection of the script to
   keep in sync, and no `.po`/Weblate layer.
4. **Quality over throughput.** Reverse engineering and translation run on the strongest
   available model even where that makes the project slower.
5. **Reproducible from a verified dump.** One command takes a Redump-verified image to a
   patched image with a known checksum; the released patch is that build's output.

## Who this is for, and what kind of translation it is

**A translation, not a localization** (Jay, 2026-09-20). The audience is the person who would
otherwise play this with Google Translate open, or screenshot a text box and ask Claude what it
says — someone who wants *this* game, overtly Japanese as it is, and needs the words. It is
not an attempt to bring the game to a wider audience. So Japanese-isms stay: Boku is called
"Boku" (English can't keep the word's you/I/little-boy ambiguity, but it can keep the name),
and the style guide decides the rest in that spirit. The voices stay Japanese for the same
reason — it is a choice, not a limitation: the intended experience is a film
with subtitles, not a dub, and that suits a work this rooted in its place.

Nothing is cut to fit. Older projects that found "the script does not fit" were hand-writing
assembler; if English outgrows its space, the answer here is engineering — relocation, the
disc's unused sectors, new packing or compression routines — not a shorter translation.

## How the translation is made

**The English script is written by AI agents** — Claude, the strongest model available, not a
sentence-at-a-time machine translation (PLAN § *Translation*). The event scripts are decoded so a
translator sees a whole scene as the game plays it — which line follows which, where the choices branch — along
with the speakers, and is given the whole story bible, style guide and glossary first and then
the scenes one after another, a day's worth or the whole game in play order (`./make.sh
packet`, `translation/README.md`). The box limits are not handed to it: the
lint measures every page and `./make.sh mockup` draws them. A second agent reviews against the
Japanese, and then it gets played.
Scenes are readable in order outside the game, the Japanese beside the English, in a reader
built for this project rather than a generic localization platform (`./make.sh reader`). The project
is made for Jay and his friends and published for anyone who wants it; everything that
produced the script is here to inspect, and pull requests that improve it are welcome.

The engineering does not care who wrote the English. The translation files are the only
interface between the script and the build, so someone who wants to do a hand translation —
or one into another language — should be able to replace those files and get a patch with
all of the reverse engineering already done. That is an aspiration: this project will not
test it, so expect to find the places where it quietly assumed its own workflow.

## What gets translated

| | Content | Plan |
|---|---|---|
| 1 | Text drawn by the game's own renderer — dialogue, menus, item and insect names | **The priority.** |
| 2 | Japanese text inside textures — the picture diary, the encyclopedias, menu plates and buttons, signs | After 1. Each image's path is in [research/textures-plan.md](research/textures-plan.md). The ones translated are **programmatic**: the Japanese is painted out of its panel and the English set in the game's own glyphs (or one of the project's two small pixel faces where the space is too small), at build time from your import, so only the English is committed ([translation/textures/](translation/textures/README.md)). The rest stay Japanese by the charter or by Jay's ruling — a shop sign is a shop sign; the book covers convey the game's style. |
| 3 | Narration and songs inside the movies (`__STR/*.IKI`: the opening `M27`, the one ending movie `M28`, and three more) | In scope since 2026-09-20 — Jay, after playing: the opening "definitely needs subtitles". The player draws 24-bit frames straight into VRAM, so the subtitles are composited into each frame by a hook in the player (`asm/movie.asm`, ruled 2026-09-22 over burning them in — [research/movies.md](research/movies.md)), keyed by movie and frame from `translation/movies.txt`. |
| 4 | Voices (`__STR/BOKU_XA.XAM`) | **Kept Japanese on purpose** — subtitles, not a dub (see above). |
| 5 | Voice-overs with no text — the five endings (a still with narration over it, after the one ending movie) and voice-only clips in play, such as the narrator at the well | In scope since 2026-09-22 (Jay, from playing): subtitled in the dialogue band while the clip plays ([research/voice-only.md](research/voice-only.md); the English is in the day files and `translation/clips.txt`). |

## The central risk was vertical text

The original draws all its dialogue top to bottom in a narrow strip down the right of the
screen (Jay, from playing it), and a 512 KB MIPS executable decides that. The fallbacks were,
cheapest first: bend the renderer to advance horizontally with a per-glyph width table; the
same with a replacement glyph sheet; or leave it alone and draw a subtitle overlay on top. The
first held. The text stepper already had a horizontal mode, direction is an *argument* (the
dialogue is vertical because two call sites pass a literal 1), and the 12×12 font sheet already
has A–Z, a–z and the digits; the punctuation it lacks is drawn for this project. The renderer
patches (`asm/`, armips) draw each text surface proportionally — one hook per surface, as every
comparable project needed — and the dialogue panel became the band under the scene. The detail
is [research/text-renderer.md](research/text-renderer.md) and
[research/vwf-prototype.md](research/vwf-prototype.md). The PS2 sequel's English patch and the
PSP port's Spanish patch converted vertical text the same way in their versions of this engine
([research/renderer-prior-art.md](research/renderer-prior-art.md)).

## What the disc looks like

One Mode 2 data track: a PS-X EXE (`SCPS_100.88`), one 104 MiB headerless archive
(`BOKU.BIN`, whose directory is three arrays inside the executable), XA voice audio and STR video. Game text is
**not Shift-JIS**: it is 16-bit indices into the font sheet with `0x8000`-range control codes —
the same scheme, and at least largely the same glyph order, as the PSP port and the PS2 sequel.
Details, measurements and what is still unknown: [research/disc-recon.md](research/disc-recon.md)
and [research/boku-bin.md](research/boku-bin.md) (the archive's 1,302 members, mapped).

## How the build works

Import → extract to line ids → the committed translation files → the build → a patched image →
a patch. The build lays each line out in its box's pixels, rebuilds every copy of it and every
container around it, relocates a member that outgrows its sectors, typesets the textures,
assembles the renderer and movie hooks, and regenerates each touched sector's EDC/ECC. The
standing gate is the null round trip: every text site reinserted unchanged through the full
rebuild reproduces the original image byte for byte. How the containers grow is
[research/relocation.md](research/relocation.md).

## Using it

Every recurring command is a verb of `./make.sh`. **`./make.sh help` is the full list**, with
what each verb does and where its switches are; most take `--help`. It needs `uv` (which
installs Python and the Python tools on first use) and, for a CHD, `chdman` (MAME's —
`brew install rom-tools`). `build-days` needs armips; the emulator verbs — and `saves` and
`duckstation-cards`, which boot a new game on Beetle once to start from — need PCSX-Redux or
the Beetle PSX core and a retail BIOS: [research/tooling-setup.md](research/tooling-setup.md)
says how to set those up. `./make.sh help` names what the other verbs need.

### The import step

It comes first, once:

```
./make.sh import path/to/your-dump.chd      # or .cue / .bin / .img, or set BOKU_DISC
./make.sh extract                           # the decoded script, into disc/script/
```

`import` verifies the image against the Redump checksum (recorded in
[research/disc-recon.md](research/disc-recon.md) § "The dump") and refuses anything else, then
writes `disc/image.img`, `disc/image.cue`, `disc/manifest.json` and the extracted files under
`disc/files/`; `extract` writes the script as line ids and per-scene flow graphs. Everything
that reads the game needs them, and nothing they write is ever committed.

### The verbs, by task

| to | run |
|---|---|
| build the game in English and play it | `./make.sh build-days`, then load `build/days/days-<stamp>-<hash>.cue` — named by the revision, so a play report can say what it tested |
| start from any day | `./make.sh duckstation-cards`: memory cards that start any morning from August 2 to 31, August 31 with the stars for each of the five endings, a finished game (Summer Memories), and bug-sumo saves ([research/sumo.md](research/sumo.md)); `INDEX.tsv` beside them lists every slot, and [research/save-format.md](research/save-format.md) § "Playing a generated save in DuckStation" says how to put one in slot 1 without touching your own card. `saves` writes the same saves a card each for the headless tools, `save` one card from parameters |
| read the translation | `./make.sh reader` → `work/reader/index.html`: the whole translation in play order, the Japanese beside the English, each id one key to copy, the lint's findings on their lines. `build-days` rewrites it, and its header says which build it was read against |
| check the translation | `./make.sh lint-translation` (ids, choice menus, page counts, fit in pixels, movie cues); `./make.sh mockup` (every page drawn at the band's geometry, no emulator); `./make.sh coverage` (per day, what the build did with every line); `./make.sh textures check` (the texture strings typeset, and what each refused) |
| translate | `./make.sh packet` and `./make.sh save-event` — the workflow is [translation/README.md](translation/README.md) |
| time and see the movie subtitles | `./make.sh movies` (decode to `work/movies/`), `./make.sh movie-timing` (each cue against the transcripts), `./make.sh movie-review` (each cue on Beetle, with the narration) |
| drive an emulator | `./make.sh smoke` (boot on both headless emulators), `boot-save`, `examine`, `sumo-bout` (Beetle from a generated save) |
| test | `./make.sh test`, `./make.sh lint`; `./make.sh emu-test` for the tests that boot an emulator |
| make a patch | `./make.sh patch --modified build/days/image.img` (PPF + xdelta + both sides' hashes into `build/patch/`); `./make.sh apply-patch DUMP PATCH --out FILE` applies one, checking both hashes. |
| cut a release | tag `v<version>` and push it, then `./make.sh release` (both patches, hashes, notes and a zip into `release/v<version>/`) and `./make.sh publish-release release/v<version> --yes` |
| play on Mode One | `./make.sh export-to-mode-one` (packs `build/days` as Mode One's `boku.chd` and pins its SHA-1; then rebuild Mode One) |

## Layout

```
README.md            what the project is (this file)
PLAN.md              the only task ledger — open work, by stable id
CLAUDE.md            rules for agents working here
LICENSE              MIT — all tools and patches' source
LICENSE-translation  CC BY-SA 4.0 — the English script and the context notes
make.sh              every recurring command (./make.sh help)
boku/                the Python package behind the verbs; boku/faces/ holds the two small pixel
                     faces drawn for this project (Bean, Sprout)
asm/                 armips source for the executable and overlay patches
tests/               pytest; the disc-dependent tests skip when there is no import
tools/               the renderer build and page mock-ups (vwf/), headless PCSX-Redux and Beetle
                     PSX drivers (redux/, libretro/), Ghidra symbol scripts, the texture census
                     and plan, the diary redraw prototype
translation/         the English and what a translator reads first (translation/README.md)
research/            what has been learned: formats, prior art, practice. One subject per file
                     (two are raw research-agent reports, framed as such at the top)
research/data/       the tables a note would otherwise list; glyph-table.tsv and text-boxes.tsv
                     are kept by hand, the rest are regenerated by the verbs ./make.sh help names
disc/       (ignored)  your import: image.img, image.cue, manifest.json, files/, script/
reference/  (ignored)  third-party material kept locally — see below
work/       (ignored)  scratch, and everything derived from the game: translator packets, page
                       mock-ups, the reader, saves, decoded movies and voices, review pages
build/      (ignored)  the renderer's edit set (vwf/), the days build (days/), the patch (patch/),
                       and what the lower-level verbs write (trial/, image/)
release/    (ignored)  cut releases, one release/v<version>/ each (./make.sh release)
```

## Delivery

* **Public release:** a patch against the Redump-verified image, via GitHub Releases, with the
  base and result checksums stated. Never an image. Tag the commit `v<version>`, push the
  tag, then `./make.sh release` (writes `release/v<version>/`) and `./make.sh publish-release
  release/v<version> --yes`. The release page quotes this README's § "How the translation is
  made" and § "Related work and credit" whole; what a release holds and checks is
  `boku/release.py`'s docstring.
* **Mode One** (`~/Dev/retro-trainer/one`), the phone frontend Jay plays on: it does not apply
  the patch. `./make.sh export-to-mode-one` packs the built image as its `one/roms/boku.chd`
  and pins that file's SHA-1 in its index (`boku/mode_one.py` says how). It runs PS1 on Beetle
  PSX, so the build must be confirmed on that core.

## Reference material

Kept locally under `reference/`, not redistributed here:

* **jooey's FAQ/Walkthrough**, v0.36 (2002-11-24) — an English account of the game's events,
  used as story context for translation. It is on GameFAQs under the PlayStation game
  "Boku no Natsuyasumi" (<https://gamefaqs.gamespot.com>, search the title); save the text
  version as `reference/gamefaqs-guide.txt`.
* **Action Button's review of the game** (Tim Rogers, six hours, English) —
  <https://www.youtube.com/watch?v=779coR-XPTw>. Its auto-generated transcript is long-form
  context on the story, characters and feel; fetch it with `yt-dlp` to
  `reference/youtube-779coR-XPTw-transcript.txt`.
* **xneo.jp's Japanese walkthrough** — <https://xneo.jp/bokunatsu/> → `reference/xneo/`.
  Day-by-day events in the game's own vocabulary.

## Related work and credit

None of these target the PS1 original's text, and all of them made this project's first day
shorter. What each one knows is written up in
[research/related-projects.md](research/related-projects.md).

* [pleonex/Boku-no-Natsuyasumi](https://github.com/pleonex/Boku-no-Natsuyasumi) — PSP port
  extraction tools and a format wiki; its glyph table is what first decoded the PS1 script.
* [HilltopWorks/BokuNoNatsuyasumi2](https://github.com/HilltopWorks/BokuNoNatsuyasumi2) — the
  PS2 sequel's complete English patch toolchain.
* [GriffithVIII/Boku-no-Natsuyasumi-ESP](https://github.com/GriffithVIII/Boku-no-Natsuyasumi-ESP) —
  the PSP port's Spanish patch (TraduSquare).
* [psyouloveme/boku1-reversing](https://github.com/psyouloveme/boku1-reversing) — PS1 original:
  Ghidra scripts, a jPSXdec index of the disc, and a RAM map from speedrunning.
* [KendritPy/Boku_ESP_JP](https://github.com/KendritPy/Boku_ESP_JP) and
  [snake7594/boku-natsu-portable-kr-patch](https://github.com/snake7594/boku-natsu-portable-kr-patch) —
  PSP port: a precise dialogue-format spec, and a 2,020-code character table.

How PS1 translation is done in general — tools, patch formats, case studies, release norms —
is surveyed in [research/ps1-translation-practice.md](research/ps1-translation-practice.md).

## Contributing

You need your own dump of the game. After the import step you have everything the project has.
Translation changes are edits to the id-keyed files; say in the PR what you were looking at in
the game. Disagreements about style are welcome — the translation's style guide is
[translation/style-guide.md](translation/style-guide.md), and it can be argued with like any
other file.

## Licence

Tools, scripts and assembly patches: [MIT](LICENSE). The English translation and the context
notes: [CC BY-SA 4.0](LICENSE-translation). *Boku no Natsuyasumi* is © Sony Interactive
Entertainment; this project distributes none of it and is not affiliated with Sony or
Millennium Kitchen.
