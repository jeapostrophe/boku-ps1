# boku-ps1

An English translation patch for the PlayStation original of *Boku no Natsuyasumi* (ぼくのなつやすみ,
SCEI / Millennium Kitchen, 2000, **SCPS-10088**) — built in the open, tools and translation both.

> **Status, 2026-09-19: project start.** The disc has had a first look
> ([research/disc-recon.md](research/disc-recon.md)): the script is readable, nothing is
> extracted by a real tool yet, and nothing has been translated. Open work is
> [PLAN.md](PLAN.md). No English translation of the PS1 original was found, released or in progress — GitHub
> searched thoroughly, the romhacking sites could not be (they block automated fetches) ([research/related-projects.md](research/related-projects.md) §7(d)).

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
sentence-at-a-time machine translation. The plan (none of it is built yet — PLAN § *Translation*): the event scripts get decoded so a
translator sees a whole scene as the game plays it — which line follows which, where the choices branch — along
with the speakers, the box limits, the style guide, the glossary, and long-form context on the
game and its story. A second agent reviews against the Japanese, and then it gets played.
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
| 2 | Japanese text inside textures (the picture diary is the likely bulk) | After 1. Try image-model redraws in the original style; fall back to drawing subtitles onto the texture. |
| 3 | Text inside FMVs (`__STR/*.IKI`) | Out of scope. Reopen only if subtitling textures turns out to extend cheaply to STR frames. |
| 4 | Voices (`__STR/BOKU_XA.XAM`) | **Kept Japanese on purpose** — subtitles, not a dub (see above). |

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

Both the PS2 sequel's English patch and the PSP port's Spanish patch hit vertical text in
their versions of this engine and converted it to horizontal with a variable-width font, so
(1)/(2) have precedent in the family — but neither is this executable, and what the PS1
renderer actually does is PLAN § *Text renderer*.

## What the disc looks like

One Mode 2 data track: a PS-X EXE (`SCPS_100.88`), one 104 MiB headerless archive
(`BOKU.BIN`; its directory is not in the archive's head and is probably in the executable), XA voice audio and STR video. Game text is
**not Shift-JIS**: it is 16-bit indices into the font sheet with `0x8000`-range control codes —
the same scheme, and at least largely the same glyph order, as the PSP port and the PS2 sequel.
Details, measurements and what is still unknown: [research/disc-recon.md](research/disc-recon.md).

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

*Not built yet (PLAN `ENV-02`).* The contract: you point it at your own dump
(`.chd` or `.bin/.cue`); it verifies the image against the Redump checksum
(recorded in [research/disc-recon.md](research/disc-recon.md) § "The dump"), and writes the image, the extracted files
and the decoded script under `disc/`. Nothing else in the repo works without it, and nothing it
writes is ever committed. It needs `chdman` (from MAME) for CHD input.

## Layout

```
README.md            what the project is (this file)
PLAN.md              the only task ledger — open work, by stable id
CLAUDE.md            rules for agents working here
LICENSE              MIT — all tools and patches' source
LICENSE-translation  CC BY-SA 4.0 — the English script and the context notes
research/            what has been learned: formats, prior art, practice. One subject per file
                     (two are raw research-agent reports, framed as such at the top).
disc/        (ignored)  your import: image.img, files/, decoded script
reference/   (ignored)  third-party material kept locally — see below
work/        (ignored)  scratch: dumps, traces, contact sheets, Ghidra projects
build/       (ignored)  patched files, patched image, the patch
```

Tools are Python, managed with `uv`; assembly patches are armips. Code directories appear here
as they are created.

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
