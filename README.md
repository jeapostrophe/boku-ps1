# boku-ps1

An English translation patch for the PlayStation original of *Boku no Natsuyasumi* (ぼくのなつやすみ,
SCEI / Millennium Kitchen, 2000, **SCPS-10088**) — built in the open, tools and translation both.

> **Status, 2026-09-20: the approach works.** A patched disc image boots — on PCSX-Redux and on
> Beetle PSX, the core Mode One uses — and draws English left to right in a band under the
> scene (`./make.sh trial`). The archive, text format, event scripts, font, renderer, memory
> map and textures are decoded and written up under [research/](research/): the script is
> 2,977 lines / ~75,000 glyphs, 180 textures carry Japanese, and the game checks nothing it
> loads. **Days 1–7 of the script play in English on Beetle PSX**
> (`./make.sh build-days`): proportional text in a translucent three-line band under the
> scene (inside the rows every emulator shows), speaker labels in the original's `Uncle「…」`
> form, page arrows, choice menus with the game's own hand pointing at the row; 757 of 761
> lines laid out and reinserted, members relocated where they grew, the map work area raised
> so the biggest scene fits. Each build names its cue by revision
> (`build/days/days-<stamp>-<hash>.cue`) so a play report can say what it tested. The rest of the script waits on that being played and
> judged. Ruled 2026-09-20: the game's own font with a width table, the smallest band, the
> tab-separated day files as the format, and the programmatic redraw for the diary pages;
> every texture that carries Japanese has a chosen path ([research/textures-plan.md](research/textures-plan.md)).

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
   read-only scene reader (PLAN `TRN-06`); there is no editable projection of the script to
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
with the speakers, the style guide, the glossary, and the story of the day, and is handed a
day's scenes one after another (`./make.sh packet`). The box limits are not handed to it: the
lint measures every page and `./make.sh mockup` draws them. A second agent reviews against the
Japanese, and then it gets played.
Scenes will be readable in order outside the game, with alternatives side by side, in a
small reader built for this project rather than a generic localization platform. The project
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
| 2 | Japanese text inside textures (197 images; the picture diary is 94 of them) | After 1. Three paths, chosen per image in [research/textures-plan.md](research/textures-plan.md): **programmatic** (138 — blank the flat panel and typeset the English with the game's own glyphs; the diary, the encyclopedia spreads, the UI plates), **redraw** (28 — stylised lettering, book covers, the farewell note on the log), **subtitle** composited beside the object (1). 30 stay Japanese by the charter — a shop sign is a shop sign. |
| 3 | Narration inside the movies (`__STR/M27.IKI`, the opening; `M28.IKI`, the one ending movie) | In scope since 2026-09-20 — Jay, after playing: the opening "definitely needs subtitles". The player draws 24-bit frames straight into VRAM, so the subtitles are composited into each frame by a hook in the player (`asm/movie.asm`, ruled 2026-09-22 over burning them in — [research/movies.md](research/movies.md) § 5, § 7); proven with one cue over the opening on both emulators. Left: the cue file, its carrier in the build, the narration itself (PLAN `FMV-02`–`FMV-04`). |
| 4 | Voices (`__STR/BOKU_XA.XAM`) | **Kept Japanese on purpose** — subtitles, not a dub (see above). |
| 5 | Voice-overs with no text — the five endings (a still with narration over it, after the one ending movie) and voice-only clips in play, such as the narrator at the well | In scope since 2026-09-22 (Jay, from playing). Inventory, mechanism and translation: PLAN § Voice-over (`VO-01`–`VO-04`). |

## The central risk: the game writes vertically

The original draws all dialogue top-to-bottom in pre-placed boxes (Jay, from playing it; the
renderer itself has not been read yet). The boxes stay where they
are; how text is drawn inside them is what has to change, and that means changing — or working
around — the renderer in a 512 KB MIPS executable. The fallbacks, cheapest first:

1. The game's font already has Latin glyphs: patch the renderer to advance horizontally with a
   per-glyph width table and wrap inside the existing box.
2. It doesn't, or they are unusable: the same patch plus a replacement glyph sheet made from a
   redistributable (SIL OFL) font.
3. The renderer can't reasonably be bent: leave it alone and add a hand-written subtitle
   overlay drawn on top of the normal interface.

First good news (2026-09-20, static analysis, `research/font.md`): the game's text stepper
already has a **horizontal mode** behind a flag bit, and its 12×12 font sheet already contains
A–Z, a–z, digits and most punctuation — full-width, so a width table is still needed, and the
Japanese punctuation is drawn for vertical lines. And direction turns out to be an *argument*: dialogue is vertical because two call sites pass
a literal 1 (`research/text-renderer.md`). Twenty of the game's 26 text surfaces are already
horizontal. What is left is real but bounded: the dialogue panel is a narrow strip down the
right edge and has to become a band, SELECT menus and two overlay screens are hard-coded
vertical, and a width table has to be hooked in. The first half of that has now been seen running: `PLAN TXT-04`'s trial image draws
horizontal English in a bottom band on both emulators. The width table is the next piece.

Both the PS2 sequel's English patch and the PSP port's Spanish patch hit vertical text in
their versions of this engine and converted it to horizontal with a variable-width font, so
(1)/(2) have precedent in the family — but neither is this executable, and what the PS1
renderer actually does is PLAN § *Text renderer*.

## What the disc looks like

One Mode 2 data track: a PS-X EXE (`SCPS_100.88`), one 104 MiB headerless archive
(`BOKU.BIN`, whose directory is three arrays inside the executable), XA voice audio and STR video. Game text is
**not Shift-JIS**: it is 16-bit indices into the font sheet with `0x8000`-range control codes —
the same scheme, and at least largely the same glyph order, as the PSP port and the PS2 sequel.
Details, measurements and what is still unknown: [research/disc-recon.md](research/disc-recon.md)
and [research/boku-bin.md](research/boku-bin.md) (the archive's 1,302 members, mapped).

## The approach

1. **Recon** the archive, the text tables, the event scripts and the textures until every
   piece of Japanese on the disc has a known home.
2. **Reverse-engineer the text renderer** and settle how English gets on screen.
3. **Trial**: one English line, on screen, in a rebuilt image.
4. **Pipeline**: import → extract to ids → translation files → reinsert → image → patch, with
   an unchanged round trip reproducing the original image byte for byte as the standing gate.
5. **Translate** with agents that are given the story, the scene, the speakers and the box
   limits — then review, then play it.
6. **Textures**, then release.

## The import step

```
./make.sh import path/to/your-dump.chd      # or .cue / .bin / .img, or set BOKU_DISC
```

It verifies the image against the Redump checksum (recorded in
[research/disc-recon.md](research/disc-recon.md) § "The dump") and refuses anything else,
then writes `disc/image.img`, `disc/image.cue`, `disc/manifest.json` and the extracted files
under `disc/files/`. `./make.sh extract` then writes the decoded script and per-scene flow graphs under
`disc/script/`. Nothing else
in the repo works without it, and nothing it writes is ever committed. It needs `uv`, and
`chdman` (from MAME) for CHD input.

## Layout

```
README.md            what the project is (this file)
PLAN.md              the only task ledger — open work, by stable id
CLAUDE.md            rules for agents working here
LICENSE              MIT — all tools and patches' source
LICENSE-translation  CC BY-SA 4.0 — the English script and the context notes
make.sh              every recurring command: import, extract, movies, packet, save-event, mockup, build-days, patch, apply-patch, save(s), boot-save, test, emu-test, lint, smoke
boku/                the Python package: import, extract, movies, trial, build (text and
                     texture recipes), patch, apply-patch, save
asm/                 armips source for the executable patches
tests/               pytest; the disc-dependent tests skip when there is no import
tools/               Ghidra scripts, headless PCSX-Redux and Beetle PSX runners, the VWF prototype build
                     and the page mock-ups drawn with its font (tools/vwf/mockup.py)
translation/         the English: story bible, style guide, open questions, samples, the day
                     files, movies.txt, the movie subtitles (translation/README.md), and
                     textures/, the strings the build typesets into textures
research/            what has been learned: formats, prior art, practice. One subject per file
                     (two are raw research-agent reports, framed as such at the top).
research/data/       the tables a note would otherwise have to list: the script walk, the
                     texture census and plan, and movies.tsv — what every FMV id plays,
                     which `./make.sh movies` regenerates and a test diffs. glyph-table.tsv
                     is the one kept by hand, not generated (research/font.md)
disc/        (ignored)  your import: image.img, image.cue, manifest.json, files/, script/
reference/   (ignored)  third-party material kept locally — see below
work/        (ignored)  scratch: dumps, traces, contact sheets, Ghidra projects, translator
                        packets (work/packets/), page mock-ups (work/mockup/); saves/ the
                        generated memory-card corpus (research/save-format.md)
build/       (ignored)  patched files, patched image, the patch
```

Tools are Python, managed with `uv`; assembly patches are armips.

## Delivery

* **Public release:** a patch against the Redump-verified image, via GitHub Releases, with the
  base and result checksums stated. Never an image.
* **Mode One** (`~/Dev/retro-trainer/one`): its patcher takes IPS/UPS/BPS/PPF and pins the
  post-patch SHA-1 in its index, and it runs PS1 on Beetle PSX — so the build must be
  deterministic, must emit PPF, and must be confirmed on that core.

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
the game. Disagreements about style are welcome — the translation's style guide will be a file
in this repo, and it can be argued with like any other.

## Licence

Tools, scripts and assembly patches: [MIT](LICENSE). The English translation and the context
notes: [CC BY-SA 4.0](LICENSE-translation). *Boku no Natsuyasumi* is © Sony Interactive
Entertainment; this project distributes none of it and is not affiliated with Sony or
Millennium Kitchen.
